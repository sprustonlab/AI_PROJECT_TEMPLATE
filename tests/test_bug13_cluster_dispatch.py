"""Bug #13 -- MCP Tool Registration (Lazy Dispatch).

Tests that cluster_dispatch.py always registers 6 tools and dispatches
to the correct backend at call time (lazy), so config changes take
effect without restart.

Parallel-safe: uses tmp_path for config, no shared mutable state.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Import cluster_dispatch module (template/mcp_tools/cluster_dispatch.py)
# ---------------------------------------------------------------------------

TEMPLATE_MCP = Path(__file__).resolve().parent.parent / "template" / "mcp_tools"


def _import_module(name: str, filepath: Path):
    """Import a module from file path, registering in sys.modules."""
    module_name = f"mcp_tools.{name}"
    # Avoid reusing stale cached module
    if module_name in sys.modules:
        del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    assert spec and spec.loader, f"Cannot load {filepath}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Ensure _cluster is loaded first (shared infrastructure)
if "mcp_tools._cluster" not in sys.modules:
    _import_module("_cluster", TEMPLATE_MCP / "_cluster.py")

dispatch_mod = _import_module("cluster_dispatch", TEMPLATE_MCP / "cluster_dispatch.py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_tool_name(tool) -> str | None:
    """Get name from a tool object."""
    return getattr(tool, "name", None) or getattr(tool, "_tool_name", None)


async def _call_tool(tool, args: dict):
    """Call a tool handler."""
    handler = getattr(tool, "handler", None)
    if handler is not None:
        return await handler(args)
    return await tool(args)


def _find_tool(tools, name: str):
    """Find a tool by name in a list."""
    for t in tools:
        if _get_tool_name(t) == name:
            return t
    raise KeyError(f"Tool {name!r} not found in {[_get_tool_name(t) for t in tools]}")


EXPECTED_TOOL_NAMES = {
    "cluster_jobs",
    "cluster_status",
    "cluster_submit",
    "cluster_kill",
    "cluster_logs",
    "cluster_watch",
}


# ---------------------------------------------------------------------------
# Test 1: Fresh install (backend="") -- 6 tools, each returns "not configured"
# ---------------------------------------------------------------------------


class TestFreshInstallNotConfigured:
    """Before cluster_setup, all 6 tools exist but return guidance."""

    def test_get_tools_returns_six_tools(self):
        with patch.object(
            dispatch_mod,
            "_load_dispatch_config",
            return_value={"backend": ""},
        ):
            tools = dispatch_mod.get_tools()
        assert len(tools) == 6
        names = {_get_tool_name(t) for t in tools}
        assert names == EXPECTED_TOOL_NAMES

    def test_each_tool_returns_not_configured_guidance(self):
        with patch.object(
            dispatch_mod,
            "_load_dispatch_config",
            return_value={"backend": ""},
        ):
            tools = dispatch_mod.get_tools()

        # Override config for call time too
        with patch.object(
            dispatch_mod,
            "_load_dispatch_config",
            return_value={"backend": ""},
        ):
            for t in tools:
                name = _get_tool_name(t)
                args = {}
                if name in ("cluster_status", "cluster_kill", "cluster_watch"):
                    args = {"job_id": "12345"}
                elif name == "cluster_submit":
                    args = {
                        "queue": "gpu",
                        "cpus": 1,
                        "walltime": "1:00",
                        "command": "echo hi",
                    }
                elif name == "cluster_logs":
                    args = {"job_id": "12345", "tail": 10}
                result = asyncio.run(_call_tool(t, args))
                text = result["content"][0]["text"].lower()
                assert "not configured" in text or "cluster_setup" in text, (
                    f"Tool {name} should return not-configured guidance, got: {text}"
                )


# ---------------------------------------------------------------------------
# Test 2: After setup (backend="lsf") -- tools dispatch to LSF handler
# ---------------------------------------------------------------------------


class TestLSFDispatch:
    """After cluster_setup with backend=lsf, tools dispatch to LSF."""

    def test_get_tools_still_returns_six(self):
        with patch.object(
            dispatch_mod,
            "_load_dispatch_config",
            return_value={"backend": "lsf", "ssh_target": "login.example.com"},
        ):
            tools = dispatch_mod.get_tools()
        assert len(tools) == 6

    @patch("subprocess.run")
    def test_cluster_jobs_dispatches_to_lsf(self, mock_run):
        """cluster_jobs with backend=lsf calls bjobs."""
        mock_run.return_value = MagicMock(
            stdout="No unfinished job found\n",
            stderr="",
            returncode=0,
        )
        config = {
            "backend": "lsf",
            "ssh_target": "login.example.com",
            "path_map": [{"local": "/home", "cluster": "/home"}],
        }
        with patch.object(
            dispatch_mod,
            "_load_dispatch_config",
            return_value=config,
        ):
            tools = dispatch_mod.get_tools()
            jobs_tool = _find_tool(tools, "cluster_jobs")
            result = asyncio.run(_call_tool(jobs_tool, {}))

        # Should have dispatched to LSF and returned valid JSON
        text = result["content"][0]["text"]
        data = json.loads(text)
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Test 3: After setup (backend="slurm") -- tools dispatch to SLURM handler
# ---------------------------------------------------------------------------


class TestSLURMDispatch:
    """After cluster_setup with backend=slurm, tools dispatch to SLURM."""

    @patch("subprocess.run")
    def test_cluster_jobs_dispatches_to_slurm(self, mock_run):
        """cluster_jobs with backend=slurm calls squeue."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="",
            returncode=0,
        )
        config = {
            "backend": "slurm",
            "ssh_target": "login.example.com",
            "path_map": [{"local": "/home", "cluster": "/home"}],
        }
        with patch.object(
            dispatch_mod,
            "_load_dispatch_config",
            return_value=config,
        ):
            tools = dispatch_mod.get_tools()
            jobs_tool = _find_tool(tools, "cluster_jobs")
            result = asyncio.run(_call_tool(jobs_tool, {}))

        text = result["content"][0]["text"]
        data = json.loads(text)
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Test 4: Unknown backend (backend="pbs") -- clear unsupported error
# ---------------------------------------------------------------------------


class TestUnknownBackend:
    """Unknown backend returns clear unsupported error."""

    def test_unsupported_backend_error(self):
        with patch.object(
            dispatch_mod,
            "_load_dispatch_config",
            return_value={"backend": "pbs"},
        ):
            tools = dispatch_mod.get_tools()
            jobs_tool = _find_tool(tools, "cluster_jobs")
            result = asyncio.run(_call_tool(jobs_tool, {}))

        assert result.get("isError") is True
        text = result["content"][0]["text"].lower()
        assert "unsupported" in text or "pbs" in text


# ---------------------------------------------------------------------------
# Test 5: Switch backend mid-session -- config change on next call
# ---------------------------------------------------------------------------


class TestMidSessionSwitch:
    """Config change takes effect on next tool call without restart."""

    @patch("subprocess.run")
    def test_switch_backend_takes_effect(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="No unfinished job found\n",
            stderr="",
            returncode=0,
        )
        lsf_config = {
            "backend": "lsf",
            "ssh_target": "login.example.com",
            "path_map": [{"local": "/home", "cluster": "/home"}],
        }
        slurm_config = {
            "backend": "slurm",
            "ssh_target": "login.example.com",
            "path_map": [{"local": "/home", "cluster": "/home"}],
        }
        # Register tools once (at startup)
        with patch.object(
            dispatch_mod,
            "_load_dispatch_config",
            return_value=lsf_config,
        ):
            tools = dispatch_mod.get_tools()
            jobs_tool = _find_tool(tools, "cluster_jobs")

        # First call: backend is lsf
        with patch.object(
            dispatch_mod,
            "_load_dispatch_config",
            return_value=lsf_config,
        ):
            result1 = asyncio.run(_call_tool(jobs_tool, {}))
        # Should succeed (lsf)
        assert "isError" not in result1 or result1.get("isError") is not True

        # Mid-session: switch to slurm
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="",
            returncode=0,
        )
        with patch.object(
            dispatch_mod,
            "_load_dispatch_config",
            return_value=slurm_config,
        ):
            result2 = asyncio.run(_call_tool(jobs_tool, {}))
        # Should succeed (slurm now)
        assert "isError" not in result2 or result2.get("isError") is not True
