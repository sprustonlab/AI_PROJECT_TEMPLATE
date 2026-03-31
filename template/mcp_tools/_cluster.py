"""Shared cluster infrastructure for LSF and SLURM backends.

Underscore-prefixed — skipped by MCP discovery, importable by backends.
Zero claudechic imports. Dependencies: stdlib + pyyaml.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _load_config(tool_file: Path) -> dict:
    """Read config from a YAML sibling of the given tool file.

    Example: _load_config(Path("mcp_tools/lsf.py"))
             reads mcp_tools/lsf.yaml
    """
    try:
        import yaml
    except ImportError:
        return {}
    config_path = tool_file.with_suffix(".yaml")
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


# ---------------------------------------------------------------------------
# Task helper
# ---------------------------------------------------------------------------


def _create_safe_task(coro, *, name=None):
    """asyncio.create_task with exception logging."""
    task = asyncio.create_task(coro, name=name)

    def _on_done(t):
        if not t.cancelled() and t.exception():
            log.error("Task %s failed: %s", t.get_name(), t.exception())

    task.add_done_callback(_on_done)
    return task


# ---------------------------------------------------------------------------
# SSH execution
# ---------------------------------------------------------------------------


def _ssh_control_path() -> str:
    """Return ControlPath for SSH multiplexing.

    Uses a persistent socket under ~/.ssh/sockets/ so all SSH calls to the
    login node share one TCP connection.
    """
    socket_dir = os.path.expanduser("~/.ssh/sockets")
    os.makedirs(socket_dir, mode=0o700, exist_ok=True)
    return os.path.join(socket_dir, "%r@%h-%p")


def _run_ssh(
    cmd: str,
    ssh_target: str,
    profile: str | None = None,
    timeout: int = 60,
) -> tuple[str, str, int]:
    """Run a command locally or via SSH, return (stdout, stderr, rc).

    If ssh_target is empty, runs locally. Otherwise wraps in SSH with
    connection multiplexing. If profile is given, sources it first.
    """
    if not ssh_target:
        full_cmd = cmd
    else:
        control_path = _ssh_control_path()
        escaped = cmd.replace('"', '\\"')
        prefix = f"source {profile} && " if profile else ""
        full_cmd = (
            f'ssh'
            f' -o ControlMaster=auto'
            f' -o ControlPath={control_path}'
            f' -o ControlPersist=600'
            f' {ssh_target}'
            f' "{prefix}{escaped}"'
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
# Log reading
# ---------------------------------------------------------------------------


def _resolve_log_path(log_path: str, execution_cwd: str | None) -> Path:
    """Resolve a log file path, expanding $HOME and relative paths."""
    expanded = os.path.expandvars(log_path)
    p = Path(expanded)
    if p.is_absolute():
        return p
    if execution_cwd:
        cwd_expanded = os.path.expandvars(execution_cwd)
        return Path(cwd_expanded) / p
    return p


def _read_tail(path: Path, tail: int) -> str | None:
    """Read the last *tail* lines of a file, or all lines if tail is 0.

    Returns None if the file does not exist or cannot be read.
    """
    try:
        with open(path) as f:
            if tail <= 0:
                return f.read()
            lines = f.readlines()
            return "".join(lines[-tail:])
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _read_logs(
    job_id: str,
    get_job_status_fn,
    tail: int = 100,
) -> dict[str, Any]:
    """Read stdout/stderr log files for a cluster job.

    Uses get_job_status_fn to extract log paths, then reads locally (NFS).
    """
    detail = get_job_status_fn(job_id)
    stdout_log_path = detail.get("stdout_path")
    stderr_log_path = detail.get("stderr_path")
    execution_cwd = detail.get("execution_cwd")

    result: dict[str, Any] = {
        "job_id": job_id,
        "stdout": "",
        "stderr": "",
        "log_paths": {"stdout": stdout_log_path, "stderr": stderr_log_path},
        "found": False,
    }

    if stdout_log_path:
        resolved = _resolve_log_path(stdout_log_path, execution_cwd)
        content = _read_tail(resolved, tail)
        if content is not None:
            result["stdout"] = content
            result["found"] = True
            result["log_paths"]["stdout"] = str(resolved)

    if stderr_log_path:
        resolved = _resolve_log_path(stderr_log_path, execution_cwd)
        content = _read_tail(resolved, tail)
        if content is not None:
            result["stderr"] = content
            result["found"] = True
            result["log_paths"]["stderr"] = str(resolved)

    return result


# ---------------------------------------------------------------------------
# Watch mechanism
# ---------------------------------------------------------------------------


async def _run_watch(
    job_id: str,
    terminal_statuses: frozenset[str],
    get_job_status_fn,
    caller_name: str | None,
    send_notification,
    find_agent,
    poll_interval: int,
) -> None:
    """Poll job status until terminal, then notify the calling agent.

    Args:
        job_id: Cluster job ID to watch.
        terminal_statuses: Set of status strings that mean "finished".
        get_job_status_fn: Sync function(job_id) -> detail dict.
        caller_name: Name of the agent that requested the watch.
        send_notification: Notification callback from claudechic.
        find_agent: Agent lookup callback from claudechic.
        poll_interval: Seconds between polling attempts.
    """
    # Poll until terminal
    while True:
        await asyncio.sleep(poll_interval)
        try:
            detail = await asyncio.to_thread(get_job_status_fn, job_id)
        except (RuntimeError, ValueError):
            detail = {"job_id": job_id, "status": "UNKNOWN", "job_name": None}
            break

        status = detail.get("status", "")
        if status in terminal_statuses:
            break

    # Build notification message
    status = detail.get("status", "UNKNOWN")
    job_name = detail.get("job_name") or "unnamed"

    if status in ("DONE", "COMPLETED"):
        summary = f"Job {job_id} ({job_name}) completed successfully."
    elif status in ("EXIT", "FAILED"):
        summary = f"Job {job_id} ({job_name}) FAILED ({status})."
    else:
        summary = f"Job {job_id} ({job_name}) ended with status: {status}."

    parts = [summary]
    cpu = detail.get("cpu_time_seconds")
    mem = detail.get("max_mem_gb")
    if cpu is not None:
        hours = cpu / 3600
        parts.append(f"CPU time: {hours:.1f}h")
    if mem is not None:
        parts.append(f"Peak memory: {mem:.1f} GB")

    message = " ".join(parts)

    # Deliver notification
    if caller_name and send_notification and find_agent:
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
# Response helpers
# ---------------------------------------------------------------------------


def _text_response(text: str, *, is_error: bool = False) -> dict[str, Any]:
    """Format a text response for MCP."""
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result


def _json_response(data: Any) -> dict[str, Any]:
    """Format a JSON-serializable object as an MCP text response."""
    return _text_response(json.dumps(data, indent=2))


def _error_response(text: str) -> dict[str, Any]:
    """Format an error response for MCP."""
    return _text_response(text, is_error=True)
