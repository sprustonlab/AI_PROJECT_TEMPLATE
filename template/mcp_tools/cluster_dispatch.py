"""Cluster tools -- unified lazy-dispatch MCP plugin.

Always registers 6 tools (cluster_jobs, cluster_status, cluster_submit,
cluster_kill, cluster_logs, cluster_watch). Each tool reads config fresh
at call time, dispatching to the correct backend (LSF or SLURM) or
returning "not configured" / "unsupported backend" guidance.

This replaces the old per-backend get_tools() registration model so that
tools are always visible and config changes take effect without restart.

Zero claudechic imports. Dependencies: stdlib + pyyaml + claude_agent_sdk.
"""

from __future__ import annotations

import asyncio
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
    _run_watch,
    _text_response,
    _translate_status_paths,
)

# Supported backends -- lazy imports at dispatch time
_BACKENDS = ("lsf", "slurm")


# ---------------------------------------------------------------------------
# Config (read fresh every call)
# ---------------------------------------------------------------------------


def _load_dispatch_config() -> dict:
    """Load cluster config from the sibling cluster.yaml file."""
    return _load_config(Path(__file__).parent / "cluster.py")


def _not_configured_response() -> dict[str, Any]:
    """Return guidance for unconfigured cluster tools."""
    return _text_response(
        "Cluster tools are not configured -- run cluster_setup to choose "
        "a backend (lsf or slurm) and configure SSH access."
    )


def _unsupported_backend_response(backend: str) -> dict[str, Any]:
    """Return error for unsupported backend."""
    return _error_response(
        f"Unsupported cluster backend: {backend!r}. "
        f"Supported backends: {', '.join(_BACKENDS)}. "
        f"Run cluster_setup to reconfigure."
    )


# ---------------------------------------------------------------------------
# Backend dispatch helpers
# ---------------------------------------------------------------------------


def _get_backend_module(backend: str):
    """Return the backend module for the given backend name, or None.

    Uses importlib to load sibling modules so this works both as a real
    package (mcp_tools._lsf) and via spec_from_file_location in tests.
    """
    import importlib.util
    import sys

    module_name = f"mcp_tools._{backend}"
    if module_name in sys.modules:
        return sys.modules[module_name]

    # Resolve sibling file: _lsf.py or _slurm.py next to this file
    sibling = Path(__file__).parent / f"_{backend}.py"
    if not sibling.exists():
        return None

    spec = importlib.util.spec_from_file_location(module_name, sibling)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# MCP tool definitions -- always registered
# ---------------------------------------------------------------------------


def get_tools(**kwargs) -> list:
    """Return 6 cluster MCP tools for registration (always)."""
    caller_name = kwargs.get("caller_name")
    send_notification = kwargs.get("send_notification")
    find_agent = kwargs.get("find_agent")

    @tool(
        "cluster_jobs",
        "List all running and pending cluster jobs for the current user.",
        {},
    )
    async def cluster_jobs(args: dict[str, Any]) -> dict[str, Any]:
        config = _load_dispatch_config()
        backend = config.get("backend", "")
        if not backend:
            return _not_configured_response()
        if backend not in _BACKENDS:
            return _unsupported_backend_response(backend)
        mod = _get_backend_module(backend)
        try:
            jobs = await asyncio.to_thread(mod._list_jobs, config)
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
            "Get detailed status for a specific cluster job. "
            "Paths in the response (stdout_path, stderr_path, execution_cwd) "
            "are translated to local paths."
        ),
        {"job_id": str},
    )
    async def cluster_status(args: dict[str, Any]) -> dict[str, Any]:
        config = _load_dispatch_config()
        backend = config.get("backend", "")
        if not backend:
            return _not_configured_response()
        if backend not in _BACKENDS:
            return _unsupported_backend_response(backend)
        mod = _get_backend_module(backend)
        job_id = args["job_id"]
        try:
            path_mapper = _create_path_mapper(config)
            detail = await asyncio.to_thread(mod._get_job_status, job_id, config)
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
            "Submit a job to the cluster. "
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
        config = _load_dispatch_config()
        backend = config.get("backend", "")
        if not backend:
            return _not_configured_response()
        if backend not in _BACKENDS:
            return _unsupported_backend_response(backend)
        mod = _get_backend_module(backend)
        try:
            path_mapper = _create_path_mapper(config)
            readiness = _check_config_readiness(config)
            if readiness == "needs_setup":
                return _json_response(
                    {
                        "setup_needed": "run cluster_setup workflow",
                        "message": "Cluster tools are not yet configured.",
                    }
                )

            # Build kwargs based on backend
            submit_kwargs: dict[str, Any] = {
                "command": args["command"],
                "config": config,
                "path_mapper": path_mapper,
                "job_name": args.get("job_name", ""),
                "gpus": args.get("gpus", 0),
                "stdout_path": args.get("stdout_path", ""),
                "stderr_path": args.get("stderr_path", ""),
            }
            if backend == "lsf":
                submit_kwargs["queue"] = args["queue"]
                submit_kwargs["cpus"] = args["cpus"]
                submit_kwargs["walltime"] = args["walltime"]
            elif backend == "slurm":
                submit_kwargs["partition"] = args.get(
                    "queue", args.get("partition", "")
                )
                submit_kwargs["cpus"] = args["cpus"]
                submit_kwargs["time_limit"] = args.get(
                    "walltime", args.get("time_limit", "")
                )
                submit_kwargs["mem"] = args.get("mem", "")

            result = await asyncio.to_thread(mod._submit_job, **submit_kwargs)
            if readiness == "incomplete":
                result["setup_needed"] = "run cluster_setup workflow"
            return _json_response(result)
        except Exception as e:
            return _error_response(str(e))

    @tool(
        "cluster_kill",
        "Kill a running or pending cluster job.",
        {"job_id": str},
    )
    async def cluster_kill(args: dict[str, Any]) -> dict[str, Any]:
        config = _load_dispatch_config()
        backend = config.get("backend", "")
        if not backend:
            return _not_configured_response()
        if backend not in _BACKENDS:
            return _unsupported_backend_response(backend)
        mod = _get_backend_module(backend)
        job_id = args["job_id"]
        try:
            result = await asyncio.to_thread(mod._kill_job, job_id, config)
            return _json_response(result)
        except Exception as e:
            return _error_response(str(e))

    @tool(
        "cluster_logs",
        (
            "Read stdout/stderr log files for a cluster job. "
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
        config = _load_dispatch_config()
        backend = config.get("backend", "")
        if not backend:
            return _not_configured_response()
        if backend not in _BACKENDS:
            return _unsupported_backend_response(backend)
        mod = _get_backend_module(backend)
        job_id = args["job_id"]
        tail = args.get("tail", 100)
        try:
            path_mapper = _create_path_mapper(config)
            profile = config.get("lsf_profile") if backend == "lsf" else None
            log_reader = _create_log_reader(config, path_mapper, profile=profile)
            result = await asyncio.to_thread(
                _read_logs,
                job_id,
                lambda jid: mod._get_job_status(jid, config),
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

    @tool(
        "cluster_watch",
        (
            "Watch a cluster job and get notified when it finishes. "
            "Starts a background poller -- returns immediately. "
            "Notification delivered as a message to your agent."
        ),
        {"job_id": str},
    )
    async def cluster_watch(args: dict[str, Any]) -> dict[str, Any]:
        config = _load_dispatch_config()
        backend = config.get("backend", "")
        if not backend:
            return _not_configured_response()
        if backend not in _BACKENDS:
            return _unsupported_backend_response(backend)

        if send_notification is None or find_agent is None:
            return _error_response(
                "Watch not available: notification wiring not configured."
            )

        mod = _get_backend_module(backend)
        job_id = args["job_id"]
        poll_interval = int(config.get("watch_poll_interval", 30))

        # Determine terminal statuses based on backend
        if backend == "lsf":
            terminal_statuses = frozenset({"DONE", "EXIT"})
        else:
            terminal_statuses = frozenset(
                {
                    "COMPLETED",
                    "FAILED",
                    "CANCELLED",
                    "TIMEOUT",
                    "OUT_OF_MEMORY",
                    "NODE_FAIL",
                }
            )

        _create_safe_task(
            _run_watch(
                job_id=job_id,
                terminal_statuses=terminal_statuses,
                get_job_status_fn=lambda jid: mod._get_job_status(jid, config),
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

    return [
        cluster_jobs,
        cluster_status,
        cluster_submit,
        cluster_kill,
        cluster_logs,
        cluster_watch,
    ]
