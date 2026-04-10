"""SLURM cluster tools — MCP plugin.

Provides cluster job management (list, status, submit, kill, logs, watch)
for SLURM schedulers. Discovered by claudechic's MCP discovery seam.

Zero claudechic imports. Dependencies: stdlib + pyyaml + claude_agent_sdk.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from mcp_tools._cluster import (
    _check_config_readiness,
    _create_log_reader,
    _create_path_mapper,
    _create_safe_task,
    _error_response,
    _json_response,
    _load_config,
    _read_logs,
    _resolve_cwd,
    _run_ssh,
    _run_watch,
    _text_response,
    _translate_status_paths,
)

#: Terminal SLURM job statuses.
_TERMINAL_STATUSES = frozenset({
    "COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL",
})


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _get_config() -> dict:
    return _load_config(Path(__file__))


def _get_ssh_target(config: dict) -> str:
    return config.get("ssh_target", "")


def _get_watch_poll_interval(config: dict) -> int:
    return int(config.get("watch_poll_interval", 30))


# ---------------------------------------------------------------------------
# SLURM command execution
# ---------------------------------------------------------------------------


def _run_slurm(cmd: str, config: dict, timeout: int = 60) -> tuple[str, str, int]:
    """Run a SLURM command, locally or via SSH."""
    ssh_target = _get_ssh_target(config)
    return _run_ssh(cmd, ssh_target=ssh_target, timeout=timeout)


# ---------------------------------------------------------------------------
# squeue / scontrol parsers
# ---------------------------------------------------------------------------


def _parse_squeue(output: str) -> list[dict[str, Any]]:
    """Parse pipe-delimited squeue output into structured job dicts."""
    jobs: list[dict[str, Any]] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("JOBID"):
            continue

        parts = stripped.split("|")
        if len(parts) < 7:
            continue

        jobs.append(
            {
                "job_id": parts[0].strip(),
                "job_name": parts[1].strip(),
                "status": parts[2].strip(),
                "time": parts[3].strip(),
                "time_limit": parts[4].strip(),
                "nodes": parts[5].strip(),
                "nodelist_reason": parts[6].strip(),
            }
        )
    return jobs


def _parse_scontrol_job(output: str, job_id: str) -> dict[str, Any]:
    """Parse ``scontrol show job <id>`` Key=Value output."""
    # scontrol uses Key=Value pairs separated by spaces and newlines
    kv: dict[str, str] = {}
    for token in re.split(r'\s+', output):
        if '=' in token:
            key, _, value = token.partition('=')
            kv[key] = value

    # Extract resource usage if available
    cpu_time_seconds: int | None = None
    cpu_raw = kv.get("CPUTimeRAW")
    if cpu_raw and cpu_raw.isdigit():
        cpu_time_seconds = int(cpu_raw)

    max_mem_gb: float | None = None
    max_rss = kv.get("MaxRSS")
    if max_rss:
        # MaxRSS can be in K, M, or G
        m = re.match(r"([\d.]+)([KMG])?", max_rss)
        if m:
            val = float(m.group(1))
            unit = m.group(2) or "K"
            if unit == "K":
                max_mem_gb = val / (1024 * 1024)
            elif unit == "M":
                max_mem_gb = val / 1024
            elif unit == "G":
                max_mem_gb = val

    return {
        "job_id": job_id,
        "job_name": kv.get("JobName"),
        "status": kv.get("JobState"),
        "partition": kv.get("Partition"),
        "exec_host": kv.get("NodeList"),
        "submit_time": kv.get("SubmitTime"),
        "start_time": kv.get("StartTime"),
        "end_time": kv.get("EndTime"),
        "cpu_time_seconds": cpu_time_seconds,
        "max_mem_gb": max_mem_gb,
        "command": kv.get("Command"),
        "stdout_path": kv.get("StdOut"),
        "stderr_path": kv.get("StdErr"),
        "execution_cwd": kv.get("WorkDir"),
        "time_limit": kv.get("TimeLimit"),
    }


# ---------------------------------------------------------------------------
# Core operations (sync — called via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _list_jobs(config: dict) -> list[dict[str, Any]]:
    cmd = 'squeue -u $USER --format="%i|%j|%T|%M|%l|%D|%R"'
    stdout, stderr, rc = _run_slurm(cmd, config)
    if rc != 0:
        raise RuntimeError(f"squeue failed (rc={rc}): {stderr or stdout}")
    return _parse_squeue(stdout)


def _get_job_status(job_id: str, config: dict) -> dict[str, Any]:
    stdout, stderr, rc = _run_slurm(f"scontrol show job {job_id}", config)
    if rc != 0:
        raise RuntimeError(
            f"scontrol show job {job_id} failed (rc={rc}): {stderr or stdout}"
        )
    if "Invalid job id" in stdout or "Invalid job id" in stderr:
        raise ValueError(f"Job {job_id} not found")
    return _parse_scontrol_job(stdout, job_id)


def _submit_job(
    partition: str,
    cpus: int,
    time_limit: str,
    command: str,
    config: dict,
    path_mapper=None,
    job_name: str = "",
    mem: str = "",
    gpus: int = 0,
    stdout_path: str = "",
    stderr_path: str = "",
) -> dict[str, Any]:
    """Build sbatch invocation, submit, and return {job_id, message}."""
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

    # Resolve CWD via path mapper
    cwd = _resolve_cwd(config, path_mapper)

    # Build sbatch invocation
    parts: list[str] = ["sbatch"]
    parts += [f"--partition={partition}"]
    parts += [f"--ntasks={cpus}"]
    parts += [f"--time={time_limit}"]
    parts += [f"--chdir={shlex.quote(cwd)}"]
    if mem:
        parts += [f"--mem={mem}"]
    if gpus > 0:
        parts += [f"--gres=gpu:{gpus}"]
    if job_name:
        parts += [f"--job-name={job_name}"]
    if stdout_path:
        parts += [f"--output={stdout_path}"]
    if stderr_path:
        parts += [f"--error={stderr_path}"]

    # Use --wrap for inline commands
    escaped_cmd = command.replace('"', '\\"')
    parts.append(f'--wrap="{escaped_cmd}"')

    sbatch_cmd = " ".join(parts)
    stdout, stderr, rc = _run_slurm(sbatch_cmd, config, timeout=30)
    if rc != 0:
        raise RuntimeError(
            f"sbatch failed (rc={rc}):\n"
            f"  CMD:    {sbatch_cmd}\n"
            f"  STDOUT: {stdout.strip()}\n"
            f"  STDERR: {stderr.strip()}"
        )

    m = re.search(r"Submitted batch job (\d+)", stdout)
    if not m:
        raise RuntimeError(
            f"sbatch succeeded (rc=0) but could not parse job ID.\n"
            f"  STDOUT: {stdout.strip()}"
        )
    return {"job_id": m.group(1), "message": stdout.strip()}


def _kill_job(job_id: str, config: dict) -> dict[str, Any]:
    stdout, stderr, rc = _run_slurm(f"scancel {job_id}", config, timeout=30)
    if rc != 0:
        raise RuntimeError(
            f"scancel {job_id} failed (rc={rc}): {stderr or stdout}"
        )
    return {
        "success": True,
        "message": stdout.strip() or f"Job {job_id} cancelled.",
    }


# ---------------------------------------------------------------------------
# MCP tool definitions
# ---------------------------------------------------------------------------


def get_tools(**kwargs) -> list:
    """Return SLURM cluster MCP tools for registration."""
    caller_name = kwargs.get("caller_name")
    send_notification = kwargs.get("send_notification")
    find_agent = kwargs.get("find_agent")

    @tool(
        "cluster_jobs",
        "List all running and pending SLURM cluster jobs for the current user.",
        {},
    )
    async def cluster_jobs(args: dict[str, Any]) -> dict[str, Any]:
        config = _get_config()
        try:
            jobs = await asyncio.to_thread(_list_jobs, config)
            readiness = _check_config_readiness(config)
            if readiness != "ready":
                data = {"jobs": jobs, "setup_needed": "run cluster_setup workflow"}
                return _json_response(data)
            return _json_response(jobs)
        except Exception as e:
            return _error_response(str(e))

    @tool(
        "cluster_status",
        (
            "Get detailed status for a specific SLURM cluster job. "
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
            _translate_status_paths(detail, path_mapper)
            readiness = _check_config_readiness(config)
            if readiness != "ready":
                detail["setup_needed"] = "run cluster_setup workflow"
            return _json_response(detail)
        except Exception as e:
            return _error_response(str(e))

    @tool(
        "cluster_submit",
        (
            "Submit a job to the SLURM cluster. "
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
            "partition": str,
            "cpus": int,
            "time_limit": str,
            "command": str,
            "job_name": str,
            "mem": str,
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
                partition=args["partition"],
                cpus=args["cpus"],
                time_limit=args["time_limit"],
                command=args["command"],
                config=config,
                path_mapper=path_mapper,
                job_name=args.get("job_name", ""),
                mem=args.get("mem", ""),
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
        "Kill a running or pending SLURM cluster job.",
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
            "Read stdout/stderr log files for a SLURM cluster job. "
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
            log_reader = _create_log_reader(config, path_mapper, profile=None)
            result = await asyncio.to_thread(
                _read_logs,
                job_id,
                lambda jid: _get_job_status(jid, config),
                tail,
                log_reader=log_reader,
                path_mapper=path_mapper,
            )
            readiness = _check_config_readiness(config)
            if readiness != "ready":
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
