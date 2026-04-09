"""LSF cluster tools — MCP plugin.

Provides cluster job management (list, status, submit, kill, logs, watch)
for IBM LSF schedulers. Discovered by claudechic's MCP discovery seam.

Zero claudechic imports. Dependencies: stdlib + pyyaml + claude_agent_sdk.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from mcp_tools._cluster import (
    _check_config_readiness,
    _create_log_reader,
    _create_path_mapper,
    _create_safe_task,
    _error_response,
    _error_with_hint,
    _json_response,
    _load_config,
    _read_logs,
    _resolve_cwd,
    _run_ssh,
    _run_watch,
    _text_response,
)

#: Always injected into every submitted command so Python output is
#: visible in real-time via LSF log files.
PYTHONUNBUFFERED_VAR = "PYTHONUNBUFFERED=1"

#: Continuation lines in ``bjobs -l`` have >=26 leading spaces.
_LSF_CONTINUATION_MIN_INDENT = 10

#: Terminal LSF job statuses.
_TERMINAL_STATUSES = frozenset({"DONE", "EXIT"})


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _get_config() -> dict:
    return _load_config(Path(__file__))


def _get_ssh_target(config: dict) -> str:
    return config.get("ssh_target", "")


def _get_lsf_profile(config: dict) -> str:
    return config.get("lsf_profile", "/misc/lsf/conf/profile.lsf")


def _get_watch_poll_interval(config: dict) -> int:
    return int(config.get("watch_poll_interval", 30))


# ---------------------------------------------------------------------------
# LSF command execution
# ---------------------------------------------------------------------------


def _lsf_available() -> bool:
    """Return True if bsub is reachable in the current PATH."""
    return shutil.which("bsub") is not None


def _run_lsf(cmd: str, config: dict, timeout: int = 60) -> tuple[str, str, int]:
    """Run an LSF command, locally or via SSH."""
    if _lsf_available():
        return _run_ssh(cmd, ssh_target="", timeout=timeout)
    ssh_target = _get_ssh_target(config)
    profile = _get_lsf_profile(config)
    return _run_ssh(cmd, ssh_target=ssh_target, profile=profile, timeout=timeout)


# ---------------------------------------------------------------------------
# bjobs parsers
# ---------------------------------------------------------------------------


def _parse_bjobs_wide(output: str) -> list[dict[str, Any]]:
    """Parse ``bjobs -w`` text output into structured job dicts."""
    jobs: list[dict[str, Any]] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("JOBID"):
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
    """Collapse LSF's wrapped continuation lines into single logical lines."""
    lines = output.splitlines()
    collapsed: list[str] = []
    for line in lines:
        leading = len(line) - len(line.lstrip(" "))
        if leading >= _LSF_CONTINUATION_MIN_INDENT and collapsed:
            collapsed[-1] += line.lstrip(" ")
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
    stdout_path = _first(r"Output File <([^>]+)>")
    stderr_path = _first(r"Error File <([^>]+)>")
    execution_cwd = _first(r"Execution CWD <([^>]+)>")

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
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "execution_cwd": execution_cwd,
    }


# ---------------------------------------------------------------------------
# Core operations (sync — called via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _list_jobs(config: dict) -> list[dict[str, Any]]:
    stdout, stderr, rc = _run_lsf("bjobs -w 2>&1", config)
    if rc != 0 and "No unfinished job" not in stdout:
        raise RuntimeError(f"bjobs failed (rc={rc}): {stderr or stdout}")
    return _parse_bjobs_wide(stdout)


def _get_job_status(job_id: str, config: dict) -> dict[str, Any]:
    stdout, stderr, rc = _run_lsf(f"bjobs -l {job_id} 2>&1", config)
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
    config: dict,
    path_mapper=None,
    job_name: str = "",
    gpus: int = 0,
    stdout_path: str = "",
    stderr_path: str = "",
) -> dict[str, Any]:
    """Build bsub invocation, submit, and return {job_id, message}."""
    if path_mapper is None:
        from mcp_tools._cluster import PathMapper
        path_mapper = PathMapper()

    # Translate log paths from local to cluster
    if stdout_path:
        stdout_path = path_mapper.to_cluster(stdout_path)
    if stderr_path:
        stderr_path = path_mapper.to_cluster(stderr_path)

    # Auto-create log dirs on local filesystem (skip if ssh-only)
    log_access = config.get("log_access", "auto")
    for lp in [stdout_path, stderr_path]:
        if lp and log_access != "ssh":
            local_dir = Path(path_mapper.to_local(lp)).parent
            local_dir.mkdir(parents=True, exist_ok=True)

    # Inject conda-run helpers for live output
    if "conda run" in command and "--no-capture-output" not in command:
        command = re.sub(r"\bconda run\b", "conda run --no-capture-output", command)
    if "conda run" in command and "PYTHONUNBUFFERED" not in command:
        command = re.sub(r"\bconda run\b", f"{PYTHONUNBUFFERED_VAR} conda run", command)

    # Build environment prefix
    conda_envs = config.get("conda_envs_dirs", "")
    env_parts: list[str] = []
    if conda_envs and "conda run" in command:
        env_parts.append(f"CONDA_ENVS_DIRS={conda_envs}")
    if env_parts:
        full_command = f"{' '.join(env_parts)} {command}"
    else:
        if "conda run" not in command:
            full_command = f"{PYTHONUNBUFFERED_VAR} {command}"
        else:
            full_command = command

    # Resolve CWD via path mapper (uses -cwd flag, not cd injection)
    cwd = _resolve_cwd(config, path_mapper)

    # Build bsub invocation
    parts: list[str] = ["bsub"]
    parts += ["-q", queue]
    parts += ["-n", str(cpus)]
    parts += ["-W", walltime]
    parts += ["-cwd", shlex.quote(cwd)]
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
    stdout, stderr, rc = _run_lsf(bsub_cmd, config, timeout=30)
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


def _kill_job(job_id: str, config: dict) -> dict[str, Any]:
    stdout, stderr, rc = _run_lsf(f"bkill {job_id} 2>&1", config, timeout=30)
    if rc != 0:
        raise RuntimeError(
            f"bkill {job_id} failed (rc={rc}): {stderr or stdout}"
        )
    return {
        "success": True,
        "message": stdout.strip() or f"Job {job_id} signal sent.",
    }


# ---------------------------------------------------------------------------
# MCP tool definitions
# ---------------------------------------------------------------------------


def get_tools(**kwargs) -> list:
    """Return LSF cluster MCP tools for registration."""
    caller_name = kwargs.get("caller_name")
    send_notification = kwargs.get("send_notification")
    find_agent = kwargs.get("find_agent")

    @tool(
        "cluster_jobs",
        "List all running and pending LSF cluster jobs for the current user.",
        {},
    )
    async def cluster_jobs(args: dict[str, Any]) -> dict[str, Any]:
        config = _get_config()
        try:
            jobs = await asyncio.to_thread(_list_jobs, config)
            result = _json_response(jobs)
            readiness = _check_config_readiness(config)
            if readiness:
                data = {"jobs": jobs, "setup_needed": f"run cluster_setup workflow"}
                return _json_response(data)
            return result
        except Exception as e:
            return _error_response(str(e))

    @tool(
        "cluster_status",
        (
            "Get detailed status for a specific LSF cluster job. "
            "Paths in the response (stdout_path, stderr_path, execution_cwd) "
            "are translated to local paths."
        ),
        {"job_id": str},
    )
    async def cluster_status(args: dict[str, Any]) -> dict[str, Any]:
        config = _get_config()
        job_id = args["job_id"]
        try:
            path_mapper = _create_path_mapper(config)
            detail = await asyncio.to_thread(_get_job_status, job_id, config)
            # Translate cluster paths to local paths for display
            for key in ("stdout_path", "stderr_path", "execution_cwd"):
                if detail.get(key):
                    detail[key] = path_mapper.to_local(detail[key])
            return _json_response(detail)
        except Exception as e:
            return _error_response(str(e))

    @tool(
        "cluster_submit",
        (
            "Submit a job to the LSF cluster. "
            "Paths in log path arguments (stdout_path, stderr_path) are "
            "automatically translated between local and cluster filesystems "
            "if path_map is configured. Working directory defaults to the "
            "translated current directory (or remote_cwd if set). "
            "NOTE: Paths inside your command string are NOT automatically "
            "translated -- use relative paths or cluster-side absolute paths "
            "in the command. "
            "IMPORTANT: If the response contains setup_needed='needs_setup', "
            "STOP and automatically run cluster_setup phase='diagnose' before "
            "retrying. If 'incomplete', ask the user if they want to run "
            "cluster_setup first."
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
        config = _get_config()
        try:
            path_mapper = _create_path_mapper(config)
            readiness = _check_config_readiness(config)
            if readiness == "needs_setup":
                return _json_response({
                    "setup_needed": "run cluster_setup workflow",
                    "message": "Cluster tools are not yet configured.",
                })

            result = await asyncio.to_thread(
                _submit_job,
                queue=args["queue"],
                cpus=args["cpus"],
                walltime=args["walltime"],
                command=args["command"],
                config=config,
                path_mapper=path_mapper,
                job_name=args.get("job_name", ""),
                gpus=args.get("gpus", 0),
                stdout_path=args.get("stdout_path", ""),
                stderr_path=args.get("stderr_path", ""),
            )
            if readiness == "incomplete":
                result["setup_needed"] = "run cluster_setup workflow"
            return _json_response(result)
        except Exception as e:
            return _error_response(str(e))

    @tool(
        "cluster_kill",
        "Kill a running or pending LSF cluster job.",
        {"job_id": str},
    )
    async def cluster_kill(args: dict[str, Any]) -> dict[str, Any]:
        config = _get_config()
        job_id = args["job_id"]
        try:
            result = await asyncio.to_thread(_kill_job, job_id, config)
            return _json_response(result)
        except Exception as e:
            return _error_response(str(e))

    @tool(
        "cluster_logs",
        (
            "Read stdout/stderr log files for an LSF cluster job. "
            "Log paths are automatically translated from cluster paths to "
            "local paths via path_map. Logs can be read from mounted "
            "filesystems or via SSH depending on log_access config "
            "(default: auto -- tries local first, falls back to SSH). "
            "Returns the last `tail` lines (default 100; 0 = full log). "
            "IMPORTANT: If the response contains setup_needed, handle it "
            "the same as cluster_submit (auto-run setup for 'needs_setup', "
            "ask for 'incomplete')."
        ),
        {"job_id": str, "tail": int},
    )
    async def cluster_logs(args: dict[str, Any]) -> dict[str, Any]:
        config = _get_config()
        job_id = args["job_id"]
        tail = args.get("tail", 100)
        try:
            path_mapper = _create_path_mapper(config)
            log_reader = _create_log_reader(
                config, path_mapper,
                profile=config.get("lsf_profile"),
            )
            result = await asyncio.to_thread(
                _read_logs,
                job_id,
                lambda jid: _get_job_status(jid, config),
                tail,
                log_reader=log_reader,
                path_mapper=path_mapper,
            )
            readiness = _check_config_readiness(config)
            if readiness:
                result["setup_needed"] = "run cluster_setup workflow"
            return _json_response(result)
        except Exception as e:
            return _error_response(str(e))

    # cluster_watch needs notification wiring — graceful degradation
    cluster_watch = _make_cluster_watch(
        caller_name, send_notification, find_agent
    )

    return [
        cluster_jobs,
        cluster_status,
        cluster_submit,
        cluster_kill,
        cluster_logs,
        cluster_watch,
    ]


def _make_cluster_watch(caller_name, send_notification, find_agent):
    """Create cluster_watch tool with notification wiring."""

    @tool(
        "cluster_watch",
        (
            "Watch a cluster job and get notified when it finishes. "
            "Starts a background poller — returns immediately. "
            "Notification delivered as a message to your agent."
        ),
        {"job_id": str},
    )
    async def cluster_watch(args: dict[str, Any]) -> dict[str, Any]:
        config = _get_config()
        job_id = args["job_id"]

        if send_notification is None or find_agent is None:
            return _error_response(
                "Watch not available: notification wiring not configured."
            )

        poll_interval = _get_watch_poll_interval(config)

        _create_safe_task(
            _run_watch(
                job_id=job_id,
                terminal_statuses=_TERMINAL_STATUSES,
                get_job_status_fn=lambda jid: _get_job_status(jid, config),
                caller_name=caller_name,
                send_notification=send_notification,
                find_agent=find_agent,
                poll_interval=poll_interval,
            ),
            name=f"watch-job-{job_id}",
        )

        return _text_response(
            f"Watching job {job_id} (polling every {poll_interval}s). "
            f"You will be notified when it finishes."
        )

    return cluster_watch
