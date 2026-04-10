"""Shared cluster infrastructure for LSF and SLURM backends.

Underscore-prefixed — skipped by MCP discovery, importable by backends.
Zero claudechic imports. Dependencies: stdlib + pyyaml.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Protocol

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
# Path normalization helpers
# ---------------------------------------------------------------------------


def _normalize_local_path(p: str) -> str:
    """Normalize a LOCAL path for prefix matching.

    - Convert backslashes to forward slashes (FIRST — so ~ and $VAR work on Windows)
    - Expand ~ and environment variables (safe: uses local env)
    - Strip trailing slashes (except bare "/")
    """
    forward = p.replace("\\", "/")
    expanded = os.path.expandvars(os.path.expanduser(forward))
    return expanded.rstrip("/") if expanded != "/" else expanded


def _normalize_cluster_path(p: str) -> str:
    """Normalize a CLUSTER path for prefix matching.

    - Strip trailing slashes (except bare "/")
    - NO env var expansion (local $HOME != cluster $HOME)
    - NO tilde expansion (local ~ != cluster ~)
    - NO backslash conversion (cluster paths are always POSIX)
    """
    return p.rstrip("/") if p != "/" else p


# ---------------------------------------------------------------------------
# PathMapper
# ---------------------------------------------------------------------------


class PathMapper:
    """Bidirectional path translation between local and cluster filesystems.

    Maintains two sorted rule lists — one sorted by local prefix length
    (for to_cluster lookups) and one by cluster prefix length (for to_local
    lookups). An empty rule list means all paths pass through unchanged.

    All returned paths use forward slashes, even on Windows. Windows APIs
    accept forward slashes natively.
    """

    def __init__(self, path_map: list[dict[str, str]] | None = None):
        rules = []
        for entry in (path_map or []):
            local_val = entry.get("local", "")
            cluster_val = entry.get("cluster", "")
            if not local_val or not cluster_val:
                raise ValueError(
                    f"path_map entry must have non-empty 'local' and 'cluster' keys, "
                    f"got: {entry!r}"
                )
            local = _normalize_local_path(local_val)
            cluster = _normalize_cluster_path(cluster_val)
            rules.append((local, cluster))
        # Two sorted views — each direction matches against the correct prefix
        self._rules_by_local: list[tuple[str, str]] = sorted(
            rules, key=lambda r: len(r[0]), reverse=True,
        )
        self._rules_by_cluster: list[tuple[str, str]] = sorted(
            rules, key=lambda r: len(r[1]), reverse=True,
        )

    # -- helpers --

    @staticmethod
    def _prefix_matches(path: str, prefix: str) -> bool:
        """Check if *path* starts with *prefix* on a ``/`` boundary."""
        if path == prefix:
            return True
        return path.startswith(prefix + "/")

    @property
    def has_rules(self) -> bool:
        """Return True if any path mapping rules are configured."""
        return bool(self._rules_by_local)

    def to_cluster(self, local_path: str) -> str:
        """Translate a local path to a cluster path."""
        normalized = _normalize_local_path(local_path)
        for local_prefix, cluster_prefix in self._rules_by_local:
            if self._prefix_matches(normalized, local_prefix):
                return cluster_prefix + normalized[len(local_prefix):]
        return normalized  # passthrough (backslashes already converted)

    def to_local(self, cluster_path: str) -> str:
        """Translate a cluster path to a local path.

        Returns forward-slash paths on all platforms.
        """
        normalized = _normalize_cluster_path(cluster_path)
        for local_prefix, cluster_prefix in self._rules_by_cluster:
            if self._prefix_matches(normalized, cluster_prefix):
                return local_prefix + normalized[len(cluster_prefix):]
        return normalized  # passthrough (trailing slashes stripped)


def _create_path_mapper(config: dict) -> PathMapper:
    """Create a PathMapper from the config's path_map key."""
    path_map = config.get("path_map")
    if path_map is not None and not isinstance(path_map, list):
        raise TypeError(
            f"path_map must be a list of {{local, cluster}} dicts, "
            f"got {type(path_map).__name__}: {path_map!r}"
        )
    log_access = config.get("log_access", "auto")
    if log_access not in ("auto", "local", "ssh"):
        raise ValueError(
            f"log_access must be 'auto', 'local', or 'ssh', got: {log_access!r}"
        )
    return PathMapper(path_map)


def _translate_status_paths(
    detail: dict[str, Any], path_mapper: PathMapper,
) -> dict[str, Any]:
    """Translate cluster paths in a job status dict to local paths.

    Mutates *detail* in-place and returns it for convenience.
    """
    for key in ("stdout_path", "stderr_path", "execution_cwd"):
        val = detail.get(key)
        if val and isinstance(val, str):
            detail[key] = path_mapper.to_local(val)
    return detail


def _resolve_cwd(config: dict, path_mapper: PathMapper) -> str:
    """Determine the effective cluster CWD for job submission.

    Priority: config["remote_cwd"] > path_mapper.to_cluster(os.getcwd()) > os.getcwd()
    """
    remote_cwd = config.get("remote_cwd")
    if remote_cwd:
        return remote_cwd
    return path_mapper.to_cluster(os.getcwd())


# ---------------------------------------------------------------------------
# Config readiness check
# ---------------------------------------------------------------------------


def _check_config_readiness(config: dict) -> str:
    """Check if cluster config is ready for use.

    Returns:
        ``"ready"``, ``"incomplete"``, or ``"needs_setup"``.
    """
    ssh_target = config.get("ssh_target", "")
    has_local = shutil.which("bsub") is not None or shutil.which("sbatch") is not None

    if not ssh_target and not has_local:
        return "needs_setup"
    # Jinja placeholder means the template hasn't been filled in yet
    if ssh_target and "{{" in ssh_target:
        return "needs_setup"
    if ssh_target and not config.get("path_map"):
        return "incomplete"
    return "ready"


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


def _resolve_log_path(
    log_path: str,
    execution_cwd: str | None,
) -> str:
    """Resolve a log file path on the cluster filesystem.

    1. If absolute (starts with "/"), return as-is.
    2. If relative, prepend execution_cwd.

    Returns a cluster path string (not Path — may not be valid locally).
    Uses startswith("/") instead of os.path.isabs() because cluster
    paths are always POSIX and os.path.isabs() fails on Windows.
    """
    if log_path.startswith("/"):
        return log_path
    if execution_cwd:
        return f"{execution_cwd}/{log_path}"
    return log_path


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


# ---------------------------------------------------------------------------
# LogReader strategy pattern
# ---------------------------------------------------------------------------


class LogReader(Protocol):
    """Strategy for reading log file contents."""

    def read_tail(self, cluster_path: str, tail: int) -> str | None:
        """Read last `tail` lines of a log file (0 = full file).

        Args:
            cluster_path: The log file path on the cluster filesystem.
            tail: Number of lines from the end (0 = all).

        Returns:
            File contents as a string, or None if unavailable.
        """
        ...


class LocalLogReader:
    """Read logs from local/mounted filesystem.

    Translates cluster paths to local paths via PathMapper before reading.
    """

    def __init__(self, path_mapper: PathMapper | None = None):
        self._path_mapper = path_mapper

    def read_tail(self, cluster_path: str, tail: int) -> str | None:
        local_path = cluster_path
        if self._path_mapper:
            local_path = self._path_mapper.to_local(cluster_path)
        return _read_tail(Path(local_path), tail)


class SSHLogReader:
    """Read logs via SSH when no shared filesystem is available.

    Uses the cluster path directly — no translation needed since the
    SSH command runs on the cluster.
    """

    def __init__(self, ssh_target: str, profile: str | None = None):
        self._ssh_target = ssh_target
        self._profile = profile

    def read_tail(self, cluster_path: str, tail: int) -> str | None:
        if not self._ssh_target:
            return None
        safe_path = shlex.quote(cluster_path)
        if tail > 0:
            cmd = f"tail -n {tail} {safe_path}"
        else:
            cmd = f"cat {safe_path}"
        try:
            stdout, stderr, rc = _run_ssh(
                cmd, self._ssh_target, profile=self._profile, timeout=30,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        if rc != 0:
            log.debug(
                "SSH log read failed (rc=%d) for %s: %s",
                rc, cluster_path, stderr.strip(),
            )
            return None
        return stdout


class AutoLogReader:
    """Try local filesystem first, fall back to SSH.

    This is the default strategy (log_access: auto).
    """

    def __init__(self, local: LocalLogReader, ssh: SSHLogReader):
        self._local = local
        self._ssh = ssh

    def read_tail(self, cluster_path: str, tail: int) -> str | None:
        content = self._local.read_tail(cluster_path, tail)
        if content is not None:
            return content
        log.debug(
            "Local log read failed for %s, falling back to SSH", cluster_path,
        )
        return self._ssh.read_tail(cluster_path, tail)


def _create_log_reader(
    config: dict,
    path_mapper: PathMapper | None = None,
    profile: str | None = None,
) -> LogReader:
    """Create the appropriate LogReader based on config['log_access'].

    Args:
        config: The tool config dict.
        path_mapper: For local path translation.
        profile: Scheduler profile script (e.g., LSF profile path).

    Modes:
        "auto"  -- try local first, fall back to SSH (default)
        "local" -- local filesystem only (NFS/SMB mount required)
        "ssh"   -- always read via SSH (no shared filesystem)
    """
    mode = config.get("log_access", "auto")
    ssh_target = config.get("ssh_target", "")

    local = LocalLogReader(path_mapper)
    ssh = SSHLogReader(ssh_target, profile)

    if mode == "local":
        return local
    elif mode == "ssh":
        return ssh
    else:  # "auto"
        return AutoLogReader(local, ssh)


def _read_logs(
    job_id: str,
    get_job_status_fn,
    tail: int = 100,
    log_reader: LogReader | None = None,
    path_mapper: PathMapper | None = None,
) -> dict[str, Any]:
    """Read stdout/stderr log files for a cluster job.

    Args:
        job_id: The cluster job ID.
        get_job_status_fn: Function to get job details (returns dict).
        tail: Number of lines from the end (0 = full log).
        log_reader: Strategy for reading log contents.
        path_mapper: For translating display paths in the response.
    """
    detail = get_job_status_fn(job_id)
    stdout_log_path = detail.get("stdout_path")   # cluster path
    stderr_log_path = detail.get("stderr_path")    # cluster path
    execution_cwd = detail.get("execution_cwd")    # cluster path

    result: dict[str, Any] = {
        "job_id": job_id,
        "stdout": "",
        "stderr": "",
        "log_paths": {"stdout": stdout_log_path, "stderr": stderr_log_path},
        "found": False,
    }

    for stream in ("stdout", "stderr"):
        raw_path = detail.get(f"{stream}_path")
        if not raw_path:
            continue
        # Resolve relative paths (stays on cluster filesystem)
        resolved = _resolve_log_path(raw_path, execution_cwd)

        if log_reader is not None:
            # Reader handles transport (local+translation, SSH, or auto)
            content = log_reader.read_tail(resolved, tail)
        else:
            # Legacy fallback: direct local read
            content = _read_tail(Path(resolved), tail)

        if content is not None:
            result[stream] = content
            result["found"] = True
            # Return local path to the model if we have a mapper
            display_path = (
                path_mapper.to_local(resolved) if path_mapper else resolved
            )
            result["log_paths"][stream] = display_path

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


def _error_response(text: str, hint: str | None = None) -> dict[str, Any]:
    """Format an error response for MCP."""
    msg = text
    if hint:
        msg += f"\n\nHint: {hint}"
    return _text_response(msg, is_error=True)


def _error_with_hint(message: str, hint_type: str = "path") -> dict[str, Any]:
    """Return an error response with a cluster_setup workflow hint."""
    hints = {
        "path": "Path may not be configured correctly. Run the cluster_setup workflow.",
        "connection": "Cluster connection failed. Run the cluster_setup workflow.",
        "first_use": "Cluster tools are not yet configured. Run the cluster_setup workflow.",
    }
    return _error_response(message, hint=hints.get(hint_type, hints["path"]))
