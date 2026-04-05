"""LSF cluster tools for claudechic's in-process MCP server.

Provides cluster job management (list, status, submit, kill, watch) as MCP
tools that share the same process as agent communication tools.  Because
they run in-process, the ``cluster_watch`` tool can directly notify agents
when jobs complete or fail via ``_send_prompt_fire_and_forget``.

All LSF commands auto-detect whether ``bsub`` is available locally; if not,
they are forwarded through SSH to the configured login node.

Configuration (env vars with claudechic CONFIG fallback):
    LSF_SSH_TARGET   / cluster.ssh_target          (default: submit.int.janelia.org)
    LSF_PROFILE      / cluster.lsf_profile         (default: /misc/lsf/conf/profile.lsf)
    CONDA_ENVS_DIRS  / cluster.conda_envs_dirs     (default: "")
    —                / cluster.watch_poll_interval  (default: 30 seconds)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
from typing import Any, Callable

from claude_agent_sdk import tool

from claudechic.config import CONFIG
from claudechic.tasks import create_safe_task

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

#: Always injected into every submitted command string so that
#: Python output is visible in real-time via LSF log files.
PYTHONUNBUFFERED_VAR = "PYTHONUNBUFFERED=1"

#: Continuation lines in ``bjobs -l`` have ≥26 leading spaces; section
#: headers like RUNLIMIT have only 1.
_LSF_CONTINUATION_MIN_INDENT = 10

#: Terminal LSF job statuses that indicate a job has finished.
_TERMINAL_STATUSES = frozenset({"DONE", "EXIT"})


def _cluster_config() -> dict[str, Any]:
    """Read cluster config section from ``~/.claude/.claudechic.yaml``."""
    return CONFIG.get("cluster", {})


def _get_ssh_target() -> str:
    return os.environ.get(
        "LSF_SSH_TARGET",
        _cluster_config().get("ssh_target", "submit.int.janelia.org"),
    )


def _get_lsf_profile() -> str:
    return os.environ.get(
        "LSF_PROFILE",
        _cluster_config().get("lsf_profile", "/misc/lsf/conf/profile.lsf"),
    )


def _get_conda_envs_dirs() -> str:
    return os.environ.get(
        "CONDA_ENVS_DIRS",
        _cluster_config().get("conda_envs_dirs", ""),
    )


def _get_watch_poll_interval() -> int:
    return int(_cluster_config().get("watch_poll_interval", 30))


# ---------------------------------------------------------------------------
# SSH-vs-local execution layer
# ---------------------------------------------------------------------------


def _lsf_available() -> bool:
    """Return True if bsub is reachable in the current PATH."""
    return shutil.which("bsub") is not None


def _ssh_control_path() -> str:
    """Return the ControlPath for SSH multiplexing.

    Uses a persistent socket under ``~/.ssh/sockets/`` so that all SSH
    calls to the login node share one TCP connection instead of opening
    a new one per ``_run_lsf()`` invocation.  This is critical for
    ``cluster_watch`` which polls every 30 s per job.
    """
    socket_dir = os.path.expanduser("~/.ssh/sockets")
    os.makedirs(socket_dir, mode=0o700, exist_ok=True)
    return os.path.join(socket_dir, "%r@%h-%p")


def _run_lsf(cmd: str, timeout: int = 60) -> tuple[str, str, int]:
    """Run an LSF command string and return (stdout, stderr, returncode).

    When LSF is available locally (``bsub`` in PATH), runs the command
    directly via bash.  Otherwise, wraps it in an SSH call to the
    configured login node and sources the LSF profile first so that
    ``bjobs``/``bsub`` are available.

    SSH connection multiplexing (``ControlMaster``) is enabled so that
    repeated calls reuse a single persistent TCP connection, avoiding
    the SSH session flood that polling watchers would otherwise cause.
    """
    if _lsf_available():
        full_cmd = cmd
    else:
        ssh_target = _get_ssh_target()
        lsf_profile = _get_lsf_profile()
        control_path = _ssh_control_path()
        escaped = cmd.replace('"', '\\"')
        full_cmd = (
            f'ssh'
            f' -o ControlMaster=auto'
            f' -o ControlPath={control_path}'
            f' -o ControlPersist=600'
            f' {ssh_target}'
            f' "source {lsf_profile} && {escaped}"'
        )

    result = subprocess.run(
        full_cmd,
        shell=True,
        executable="/bin/bash",
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


# ---------------------------------------------------------------------------
# bjobs parsers
# ---------------------------------------------------------------------------


def _parse_bjobs_wide(output: str) -> list[dict[str, Any]]:
    """Parse ``bjobs -w`` text output into a list of structured job dicts.

    Expected column order (LSF 10.x)::

        JOBID  USER  STAT  QUEUE  FROM_HOST  EXEC_HOST  JOB_NAME  SUBMIT_TIME

    ``SUBMIT_TIME`` is always 3 space-separated tokens (e.g. ``Mar 15 17:53``).
    ``JOB_NAME`` cannot contain spaces in LSF, so splitting on whitespace is
    safe.
    """
    jobs: list[dict[str, Any]] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("JOBID"):
            continue
        if "No unfinished job" in stripped or "not found" in stripped.lower():
            continue

        parts = stripped.split()
        if len(parts) < 7:
            continue

        jobs.append(
            {
                "job_id": parts[0],
                "user": parts[1],
                "status": parts[2],
                "queue": parts[3],
                "from_host": parts[4],
                "exec_host": parts[5],
                "job_name": parts[6],
                "submit_time": " ".join(parts[7:]),
            }
        )
    return jobs


def _collapse_lsf_lines(output: str) -> str:
    """Collapse LSF's wrapped continuation lines into single logical lines.

    ``bjobs -l`` wraps long field values at a fixed column width (26 leading
    spaces).  Section headers like ``RUNLIMIT`` and ``MEMLIMIT`` are indented
    with only 1 space.  We only collapse lines whose leading indent is at
    least ``_LSF_CONTINUATION_MIN_INDENT`` spaces, preserving section headers
    as separate lines.

    LSF always breaks at a character boundary, so we join with an empty
    string (no added space) so that split words and paths are correctly
    reconstructed.
    """
    lines = output.splitlines()
    collapsed: list[str] = []
    for line in lines:
        leading = len(line) - len(line.lstrip(" "))
        if leading >= _LSF_CONTINUATION_MIN_INDENT and collapsed:
            collapsed[-1] += line.strip()
        else:
            collapsed.append(line)
    return "\n".join(collapsed)


def _parse_bjobs_detail(output: str, job_id: str) -> dict[str, Any]:
    """Parse ``bjobs -l <job_id>`` verbose output into a structured dict."""
    text = _collapse_lsf_lines(output)

    def _first(pattern: str, default: Any = None) -> Any:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else default

    job_name = _first(r"Job Name <([^>]+)>")
    status = _first(r"Status <([^>]+)>")
    queue = _first(r"Queue <([^>]+)>")
    command = _first(r"Command <([^>]+)>")
    exec_host = _first(r"Started \d+ Task\(s\) on Host\(s\) <([^>]+)>")
    submit_time = _first(
        r"(\w{3} \w{3} \s*\d+ \d+:\d+:\d+ \d+):\s+Submitted"
    )

    cpu_time_seconds: int | None = None
    cpu_m = re.search(r"CPU time used is ([\d.]+) seconds", text)
    if cpu_m:
        cpu_time_seconds = int(float(cpu_m.group(1)))

    mem_gb: float | None = None
    mem_m = re.search(r"\bMEM: ([\d.]+) Gbytes", text)
    if mem_m:
        mem_gb = float(mem_m.group(1))

    max_mem_gb: float | None = None
    max_mem_m = re.search(r"MAX MEM: ([\d.]+) Gbytes", text)
    if max_mem_m:
        max_mem_gb = float(max_mem_m.group(1))

    run_limit_min: float | None = None
    runlimit_m = re.search(r"RUNLIMIT\s+([\d.]+)\s+min", text)
    if runlimit_m:
        run_limit_min = float(runlimit_m.group(1))

    return {
        "job_id": job_id,
        "job_name": job_name,
        "status": status,
        "queue": queue,
        "exec_host": exec_host,
        "submit_time": submit_time,
        "cpu_time_seconds": cpu_time_seconds,
        "mem_gb": mem_gb,
        "max_mem_gb": max_mem_gb,
        "run_limit_min": run_limit_min,
        "command": command,
    }


# ---------------------------------------------------------------------------
# Core operations (sync — called via asyncio.to_thread from MCP tools)
# ---------------------------------------------------------------------------


def _list_jobs() -> list[dict[str, Any]]:
    """List all running/pending jobs for the current user."""
    stdout, stderr, rc = _run_lsf("bjobs -w 2>&1")
    if rc != 0 and "No unfinished job" not in stdout:
        raise RuntimeError(f"bjobs failed (rc={rc}): {stderr or stdout}")
    return _parse_bjobs_wide(stdout)


def _get_job_status(job_id: str) -> dict[str, Any]:
    """Get detailed status for one LSF job."""
    stdout, stderr, rc = _run_lsf(f"bjobs -l {job_id} 2>&1")
    if rc != 0:
        raise RuntimeError(
            f"bjobs -l {job_id} failed (rc={rc}): {stderr or stdout}"
        )
    if "is not found" in stdout or f"Job <{job_id}> is not found" in stdout:
        raise ValueError(f"Job {job_id} not found")
    return _parse_bjobs_detail(stdout, job_id)


def _submit_job(
    queue: str,
    cpus: int,
    walltime: str,
    command: str,
    job_name: str = "",
    gpus: int = 0,
    stdout_path: str = "",
    stderr_path: str = "",
) -> dict[str, Any]:
    """Build bsub invocation, submit, and return ``{job_id, message}``."""
    # Auto-inject --no-capture-output into conda run so Python output
    # streams live to LSF log files instead of being buffered until exit.
    if "conda run" in command and "--no-capture-output" not in command:
        command = re.sub(r"\bconda run\b", "conda run --no-capture-output", command)

    # Build environment-variable prefix
    env_parts = [PYTHONUNBUFFERED_VAR]
    conda_envs = _get_conda_envs_dirs()
    if conda_envs and "conda run" in command:
        env_parts.append(f"CONDA_ENVS_DIRS={conda_envs}")
    env_prefix = " ".join(env_parts)
    full_command = f"{env_prefix} {command}"

    # Build bsub invocation
    parts: list[str] = ["bsub"]
    parts += ["-q", queue]
    parts += ["-n", str(cpus)]
    parts += ["-W", walltime]
    if gpus > 0:
        parts += ["-gpu", f"'num={gpus}:mode=exclusive_process'"]
    if job_name:
        safe_name = job_name.replace("'", "")
        parts += ["-J", f"'{safe_name}'"]
    if stdout_path:
        parts += ["-o", stdout_path]
    if stderr_path:
        parts += ["-e", stderr_path]

    escaped_cmd = full_command.replace("'", "'\\''")
    parts.append(f"'{escaped_cmd}'")

    bsub_cmd = " ".join(parts)
    stdout, stderr, rc = _run_lsf(bsub_cmd, timeout=30)
    if rc != 0:
        raise RuntimeError(
            f"bsub failed (rc={rc}):\n"
            f"  CMD:    {bsub_cmd}\n"
            f"  STDOUT: {stdout.strip()}\n"
            f"  STDERR: {stderr.strip()}"
        )

    m = re.search(r"Job <(\d+)>", stdout)
    if not m:
        raise RuntimeError(
            f"bsub succeeded (rc=0) but could not parse job ID.\n"
            f"  STDOUT: {stdout.strip()}"
        )
    return {"job_id": m.group(1), "message": stdout.strip()}


def _kill_job(job_id: str) -> dict[str, Any]:
    """Kill a running/pending LSF job."""
    stdout, stderr, rc = _run_lsf(f"bkill {job_id} 2>&1", timeout=30)
    if rc != 0:
        raise RuntimeError(
            f"bkill {job_id} failed (rc={rc}): {stderr or stdout}"
        )
    return {
        "success": True,
        "message": stdout.strip() or f"Job {job_id} signal sent.",
    }


# ---------------------------------------------------------------------------
# Watch mechanism — extensible condition system
# ---------------------------------------------------------------------------


async def _watch_lsf_exit(job_id: str, poll_interval: int) -> dict[str, Any]:
    """Poll ``bjobs -l`` until the job reaches a terminal status.

    Returns the final job detail dict (with ``status`` in
    ``_TERMINAL_STATUSES``).  If the job disappears from LSF (e.g.
    cleaned up), returns a synthetic dict with ``status="UNKNOWN"``.
    """
    while True:
        await asyncio.sleep(poll_interval)
        try:
            detail = await asyncio.to_thread(_get_job_status, job_id)
        except (RuntimeError, ValueError):
            # Job disappeared from LSF — treat as completed
            return {"job_id": job_id, "status": "UNKNOWN", "job_name": None}

        status = detail.get("status", "")
        if status in _TERMINAL_STATUSES:
            return detail


async def _run_watch(
    job_id: str,
    condition: str,
    caller_name: str | None,
    send_notification: Callable,
    find_agent: Callable,
    poll_interval: int,
) -> None:
    """Dispatch to the appropriate watch condition and notify on completion.

    This is the entry point for the background watch task.  It runs the
    condition checker, builds a human-readable notification message, and
    delivers it to the calling agent via ``send_notification``.

    Args:
        job_id: LSF job ID to watch.
        condition: Watch condition name (currently only ``"lsf_exit"``).
        caller_name: Name of the agent that requested the watch.
        send_notification: ``_send_prompt_fire_and_forget`` from mcp.py.
        find_agent: ``_find_agent_by_name`` from mcp.py.
        poll_interval: Seconds between polling attempts.
    """
    # Dispatch to condition handler
    if condition == "lsf_exit":
        detail = await _watch_lsf_exit(job_id, poll_interval)
    else:
        log.error(f"Unknown watch condition: {condition}")
        return

    # Build notification message
    status = detail.get("status", "UNKNOWN")
    job_name = detail.get("job_name") or "unnamed"

    if status == "DONE":
        summary = f"Job {job_id} ({job_name}) completed successfully."
    elif status == "EXIT":
        summary = f"Job {job_id} ({job_name}) FAILED (EXIT)."
    else:
        summary = f"Job {job_id} ({job_name}) ended with status: {status}."

    # Append resource usage if available
    parts = [summary]
    cpu = detail.get("cpu_time_seconds")
    mem = detail.get("max_mem_gb")
    if cpu is not None:
        hours = cpu / 3600
        parts.append(f"CPU time: {hours:.1f}h")
    if mem is not None:
        parts.append(f"Peak memory: {mem:.1f} GB")

    message = " ".join(parts)

    # Deliver notification to the calling agent
    if caller_name:
        agent, error = find_agent(caller_name)
        if agent is not None:
            send_notification(agent, message, caller_name="cluster-watch")
            log.info(f"Watch notification sent to '{caller_name}': {message}")
        else:
            log.warning(
                f"Watch: agent '{caller_name}' not found, "
                f"cannot deliver notification for job {job_id}"
            )
    else:
        log.info(f"Watch: {message} (no caller to notify)")


# ---------------------------------------------------------------------------
# MCP tool response helpers
# ---------------------------------------------------------------------------


def _text_response(text: str, *, is_error: bool = False) -> dict[str, Any]:
    """Format a text response for MCP."""
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result


def _json_response(data: Any) -> dict[str, Any]:
    """Format a JSON-serializable object as an MCP text response."""
    import json

    return _text_response(json.dumps(data, indent=2))


def _error_response(text: str) -> dict[str, Any]:
    """Format an error response for MCP."""
    return _text_response(text, is_error=True)


# ---------------------------------------------------------------------------
# MCP tool definitions
# ---------------------------------------------------------------------------


@tool(
    "cluster_jobs",
    "List all running and pending LSF cluster jobs for the current user.",
    {},
)
async def cluster_jobs(args: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """List jobs via ``bjobs -w``."""
    try:
        jobs = await asyncio.to_thread(_list_jobs)
        return _json_response(jobs)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "cluster_status",
    "Get detailed status for a specific LSF cluster job.",
    {"job_id": str},
)
async def cluster_status(args: dict[str, Any]) -> dict[str, Any]:
    """Get detailed job info via ``bjobs -l``."""
    job_id = args["job_id"]
    try:
        detail = await asyncio.to_thread(_get_job_status, job_id)
        return _json_response(detail)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "cluster_submit",
    (
        "Submit a job to the LSF cluster. "
        "PYTHONUNBUFFERED=1 is always prepended. "
        "CONDA_ENVS_DIRS is set automatically when the command contains 'conda run'. "
        "--no-capture-output is automatically injected into 'conda run' so that "
        "Python output streams live to LSF log files instead of being buffered."
    ),
    {
        "queue": str,
        "cpus": int,
        "walltime": str,
        "command": str,
        "job_name": str,
        "gpus": int,
        "stdout_path": str,
        "stderr_path": str,
    },
)
async def cluster_submit(args: dict[str, Any]) -> dict[str, Any]:
    """Submit a job via ``bsub``."""
    try:
        result = await asyncio.to_thread(
            _submit_job,
            queue=args["queue"],
            cpus=args["cpus"],
            walltime=args["walltime"],
            command=args["command"],
            job_name=args.get("job_name", ""),
            gpus=args.get("gpus", 0),
            stdout_path=args.get("stdout_path", ""),
            stderr_path=args.get("stderr_path", ""),
        )
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


@tool(
    "cluster_kill",
    "Kill a running or pending LSF cluster job.",
    {"job_id": str},
)
async def cluster_kill(args: dict[str, Any]) -> dict[str, Any]:
    """Kill a job via ``bkill``."""
    job_id = args["job_id"]
    try:
        result = await asyncio.to_thread(_kill_job, job_id)
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))


def _make_cluster_watch(
    caller_name: str | None = None,
    send_notification: Callable | None = None,
    find_agent: Callable | None = None,
):
    """Create the ``cluster_watch`` tool with notification wiring.

    This is a factory (like ``_make_tell_agent``) because the watch tool
    needs ``caller_name`` and references to ``_send_prompt_fire_and_forget``
    and ``_find_agent_by_name`` from ``mcp.py``.  These are injected to
    avoid circular imports.

    Args:
        caller_name: Name of the agent that will use this tool.
        send_notification: ``_send_prompt_fire_and_forget`` from mcp.py.
        find_agent: ``_find_agent_by_name`` from mcp.py.
    """

    @tool(
        "cluster_watch",
        (
            "Watch a cluster job and get notified when it finishes. "
            "Starts a background poller — returns immediately. "
            "The notification will be delivered as a message to your agent. "
            "Condition 'lsf_exit' (default): notify when the job reaches DONE or EXIT status."
        ),
        {"job_id": str, "condition": str},
    )
    async def cluster_watch(args: dict[str, Any]) -> dict[str, Any]:
        """Start watching a job for a condition."""
        job_id = args["job_id"]
        condition = args.get("condition", "lsf_exit")

        if condition != "lsf_exit":
            return _error_response(
                f"Unknown condition '{condition}'. "
                f"Currently supported: 'lsf_exit'"
            )

        if send_notification is None or find_agent is None:
            return _error_response(
                "Watch not available: notification wiring not configured."
            )

        poll_interval = _get_watch_poll_interval()

        create_safe_task(
            _run_watch(
                job_id=job_id,
                condition=condition,
                caller_name=caller_name,
                send_notification=send_notification,
                find_agent=find_agent,
                poll_interval=poll_interval,
            ),
            name=f"watch-job-{job_id}",
        )

        return _text_response(
            f"Watching job {job_id} for condition '{condition}' "
            f"(polling every {poll_interval}s). "
            f"You will be notified when the condition is met."
        )

    return cluster_watch
