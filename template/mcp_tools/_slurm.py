"""SLURM cluster backend -- internal functions.

Provides cluster job management (list, status, submit, kill, logs, watch)
for SLURM schedulers. Imported by cluster_dispatch.py for lazy dispatch.

Underscore-prefixed -- skipped by MCP discovery.
Zero claudechic imports. Dependencies: stdlib + pyyaml.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from mcp_tools._cluster import (
    _load_config,
    _resolve_cwd,
    _run_ssh,
)

#: Terminal SLURM job statuses.
_TERMINAL_STATUSES = frozenset(
    {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "TIMEOUT",
        "OUT_OF_MEMORY",
        "NODE_FAIL",
    }
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _get_config() -> dict:
    return _load_config(Path(__file__).parent / "cluster.py")


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
    for token in re.split(r"\s+", output):
        if "=" in token:
            key, _, value = token.partition("=")
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
        raise RuntimeError(f"scancel {job_id} failed (rc={rc}): {stderr or stdout}")
    return {
        "success": True,
        "message": stdout.strip() or f"Job {job_id} cancelled.",
    }
