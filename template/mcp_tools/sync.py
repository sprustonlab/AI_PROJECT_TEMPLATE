"""Cluster sync tool — MCP plugin.

Provides rsync-based code synchronization from local project to cluster.
Useful when the project lives on a local filesystem path that is not
visible on the cluster via network mounts.

Zero claudechic imports. Dependencies: stdlib + pyyaml + claude_agent_sdk.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from mcp_tools._cluster import (
    _error_response,
    _json_response,
    _load_config,
    _text_response,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _get_sync_config() -> dict:
    """Load sync.yaml config."""
    return _load_config(Path(__file__))


def _get_cluster_config() -> dict:
    """Load lsf.yaml (or slurm.yaml) for ssh_target and remote_cwd."""
    # Try LSF first, then SLURM
    lsf_path = Path(__file__).parent / "lsf.yaml"
    slurm_path = Path(__file__).parent / "slurm.yaml"
    for p in [lsf_path, slurm_path]:
        if p.exists():
            return _load_config(p.with_suffix("").with_suffix(".py"))
    return {}


def _resolve_remote_path(sync_config: dict, cluster_config: dict) -> str | None:
    """Determine the remote destination path for rsync.

    Priority:
    1. sync.yaml remote_project_path (explicit)
    2. cluster config remote_cwd (from cluster_setup)
    3. Auto-detect: ssh to get $HOME + project directory name
    """
    explicit = sync_config.get("remote_project_path", "")
    if explicit:
        return explicit

    remote_cwd = cluster_config.get("remote_cwd", "")
    if remote_cwd:
        project_name = Path(os.getcwd()).name
        return f"{remote_cwd}/{project_name}"

    return None


def _get_ssh_target(cluster_config: dict) -> str:
    return cluster_config.get("ssh_target", "")


def _build_rsync_command(
    local_path: str,
    remote_path: str,
    ssh_target: str,
    excludes: list[str],
    delete: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Build the rsync command as a list of arguments."""
    cmd = [
        "rsync",
        "-avz",
        "--progress",
    ]

    if dry_run:
        cmd.append("--dry-run")

    if delete:
        cmd.append("--delete")

    # Use .gitignore for excludes
    gitignore = Path(local_path) / ".gitignore"
    if gitignore.exists():
        cmd.extend(["--filter", ":- .gitignore"])

    for pattern in excludes:
        cmd.extend(["--exclude", pattern])

    # SSH options for multiplexing
    socket_dir = os.path.expanduser("~/.ssh/sockets")
    ssh_opts = (
        f"ssh -o ControlMaster=auto "
        f"-o ControlPath={socket_dir}/%r@%h-%p "
        f"-o ControlPersist=600"
    )
    cmd.extend(["-e", ssh_opts])

    # Source (trailing slash = contents of directory)
    cmd.append(f"{local_path}/")

    # Destination
    cmd.append(f"{ssh_target}:{remote_path}/")

    return cmd


def _run_rsync(cmd: list[str], timeout: int = 300) -> tuple[str, str, int]:
    """Execute rsync and return (stdout, stderr, returncode)."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


# ---------------------------------------------------------------------------
# MCP tool definitions
# ---------------------------------------------------------------------------


def get_tools(**kwargs) -> list:
    """Return sync MCP tools for registration."""

    @tool(
        "cluster_sync",
        (
            "Sync project code from local machine to the cluster via rsync. "
            "Use this when the project lives on a local path not visible on "
            "the cluster (no NFS/SMB mount). Reads sync config from "
            "mcp_tools/sync.yaml and cluster target from lsf.yaml/slurm.yaml. "
            "First run defaults to dry-run mode (preview only). Pass "
            "dry_run=false to perform the actual sync. "
            "Respects .gitignore and additional excludes from sync.yaml."
        ),
        {
            "dry_run": bool,
        },
    )
    async def cluster_sync(args: dict[str, Any]) -> dict[str, Any]:
        sync_config = _get_sync_config()
        cluster_config = _get_cluster_config()

        ssh_target = _get_ssh_target(cluster_config)
        if not ssh_target:
            return _error_response(
                "No ssh_target configured. Run the cluster_setup workflow first."
            )

        remote_path = _resolve_remote_path(sync_config, cluster_config)
        if not remote_path:
            return _error_response(
                "Cannot determine remote sync path. Set remote_project_path "
                "in mcp_tools/sync.yaml or remote_cwd in your cluster config."
            )

        local_path = os.getcwd()
        excludes = sync_config.get("extra_excludes", [])
        delete = sync_config.get("delete_extra", False)

        # Determine dry_run: explicit arg > config default
        dry_run = args.get("dry_run")
        if dry_run is None:
            dry_run = sync_config.get("dry_run_first", True)

        cmd = _build_rsync_command(
            local_path=local_path,
            remote_path=remote_path,
            ssh_target=ssh_target,
            excludes=excludes,
            delete=delete,
            dry_run=dry_run,
        )

        try:
            # Ensure remote directory exists
            mkdir_cmd = (
                f"ssh -o BatchMode=yes -o ConnectTimeout=5 "
                f"{ssh_target} 'mkdir -p {remote_path}'"
            )
            subprocess.run(
                mkdir_cmd, shell=True, capture_output=True, timeout=30,
            )

            stdout, stderr, rc = await asyncio.to_thread(
                _run_rsync, cmd, 300,
            )
        except subprocess.TimeoutExpired:
            return _error_response("rsync timed out after 300 seconds.")
        except Exception as e:
            return _error_response(f"rsync failed: {e}")

        if rc != 0:
            return _error_response(
                f"rsync failed (rc={rc}):\n{stderr.strip()}"
            )

        mode = "DRY RUN (preview)" if dry_run else "SYNC COMPLETE"
        result = {
            "status": "dry_run" if dry_run else "synced",
            "mode": mode,
            "local_path": local_path,
            "remote_path": f"{ssh_target}:{remote_path}",
            "delete_extra": delete,
            "output": stdout.strip() if stdout else "(no changes)",
        }

        if dry_run:
            result["hint"] = (
                "This was a dry run. Call cluster_sync with dry_run=false "
                "to perform the actual sync."
            )

        return _json_response(result)

    return [cluster_sync]
