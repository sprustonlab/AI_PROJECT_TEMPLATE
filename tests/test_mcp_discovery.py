"""Tests for MCP tool discovery via discover_mcp_tools().

Tests the discovery mechanism in claudechic/mcp.py that scans mcp_tools/,
loads eligible .py files, and calls get_tools() on each.

We import discover_mcp_tools by loading claudechic.mcp with its heavy
dependencies (claude_agent_sdk, claudechic.*) stubbed out via mock modules.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Import discover_mcp_tools from claudechic/mcp.py with stubbed deps
# ---------------------------------------------------------------------------
_CLAUDECHIC_MCP = (
    Path(__file__).resolve().parent.parent
    / "submodules" / "claudechic" / "claudechic" / "mcp.py"
)


def _import_discover_fn():
    """Import discover_mcp_tools from mcp.py with heavy dependencies stubbed.

    Stubs claude_agent_sdk and claudechic.* so we can import the module
    without needing the real SDK or full claudechic package installed.
    """
    # Stub heavy dependencies that mcp.py imports at module level
    stubs_needed = [
        "claude_agent_sdk",
        "claudechic",
        "claudechic.analytics",
        "claudechic.config",
        "claudechic.features",
        "claudechic.features.worktree",
        "claudechic.features.worktree.git",
        "claudechic.tasks",
    ]
    saved = {}
    for name in stubs_needed:
        saved[name] = sys.modules.get(name)
        if name not in sys.modules:
            stub = ModuleType(name)
            # claude_agent_sdk needs 'tool' and 'create_sdk_mcp_server'
            if name == "claude_agent_sdk":
                stub.tool = lambda *a, **kw: (lambda fn: fn)
                stub.create_sdk_mcp_server = MagicMock()
            # claudechic.config needs CONFIG dict
            if name == "claudechic.config":
                stub.CONFIG = {}
            # claudechic.analytics needs 'capture'
            if name == "claudechic.analytics":
                stub.capture = MagicMock()
            # claudechic.tasks needs 'create_safe_task'
            if name == "claudechic.tasks":
                stub.create_safe_task = MagicMock()
            # claudechic.features.worktree.git needs many symbols
            if name == "claudechic.features.worktree.git":
                for attr in [
                    "FinishPhase", "FinishState", "ResolutionAction",
                    "clean_gitignored_files", "determine_resolution_action",
                    "diagnose_worktree", "fast_forward_merge", "finish_cleanup",
                    "get_cleanup_fix_prompt", "get_finish_info",
                    "get_finish_prompt", "start_worktree",
                ]:
                    setattr(stub, attr, MagicMock())
            sys.modules[name] = stub

    try:
        spec = importlib.util.spec_from_file_location(
            "claudechic.mcp", _CLAUDECHIC_MCP
        )
        assert spec and spec.loader, f"Could not load spec for {_CLAUDECHIC_MCP}"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.discover_mcp_tools
    finally:
        # Restore original sys.modules state
        for name in stubs_needed:
            if saved[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved[name]


discover_mcp_tools = _import_discover_fn()


# ---------------------------------------------------------------------------
# Helper to write a .py file in a directory
# ---------------------------------------------------------------------------


def _write_py(directory: Path, name: str, content: str) -> Path:
    f = directory / name
    f.write_text(content, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEmptyAndMissing:
    """Discovery with empty or nonexistent mcp_tools/."""

    def test_empty_dir_returns_empty(self, mcp_tools_dir):
        """Empty mcp_tools/ → empty tool list."""
        tools = discover_mcp_tools(mcp_tools_dir)
        assert tools == []

    def test_missing_dir_returns_empty(self, tmp_path):
        """Nonexistent mcp_tools/ → empty tool list (no crash)."""
        tools = discover_mcp_tools(tmp_path / "nonexistent")
        assert tools == []


class TestUnderscoreFiles:
    """Underscore-prefixed files are pre-loaded but not discovered as tools."""

    def test_underscore_files_skipped_for_tools(self, mcp_tools_dir):
        """_helper.py is pre-loaded into sys.modules but not called for get_tools."""
        _write_py(mcp_tools_dir, "_helper.py", """\
HELPER_VALUE = 42

def get_tools(**kwargs):
    # This should NOT be called — underscore files are skipped
    return [lambda: "should_not_appear"]
""")
        tools = discover_mcp_tools(mcp_tools_dir)
        assert tools == [], "Underscore files should not contribute tools"

    def test_underscore_files_preloaded_in_sys_modules(self, mcp_tools_dir):
        """_helper.py should be importable as mcp_tools._helper after discovery."""
        _write_py(mcp_tools_dir, "_helper.py", "HELPER_VALUE = 99\n")
        discover_mcp_tools(mcp_tools_dir)
        assert "mcp_tools._helper" in sys.modules
        assert sys.modules["mcp_tools._helper"].HELPER_VALUE == 99

    def test_init_py_ignored(self, mcp_tools_dir):
        """__init__.py is skipped entirely (not pre-loaded)."""
        _write_py(mcp_tools_dir, "__init__.py", "X = 1\n")
        tools = discover_mcp_tools(mcp_tools_dir)
        assert tools == []


class TestToolDiscovery:
    """Test tool loading from public .py files."""

    def test_files_without_get_tools_skipped(self, mcp_tools_dir):
        """Files without get_tools() are silently skipped."""
        _write_py(mcp_tools_dir, "notool.py", "X = 42\n")
        tools = discover_mcp_tools(mcp_tools_dir)
        assert tools == []

    def test_file_with_get_tools_loaded(self, mcp_tools_dir):
        """File with get_tools() has its tools collected."""
        _write_py(mcp_tools_dir, "mytool.py", """\
def get_tools(**kwargs):
    return ["tool_a", "tool_b"]
""")
        tools = discover_mcp_tools(mcp_tools_dir)
        assert tools == ["tool_a", "tool_b"]

    def test_broken_file_skipped_others_load(self, mcp_tools_dir):
        """A broken file is skipped; other files still load."""
        _write_py(mcp_tools_dir, "broken.py", "raise RuntimeError('boom')\n")
        _write_py(mcp_tools_dir, "good.py", """\
def get_tools(**kwargs):
    return ["good_tool"]
""")
        tools = discover_mcp_tools(mcp_tools_dir)
        assert tools == ["good_tool"]

    def test_syntax_error_skipped(self, mcp_tools_dir):
        """A file with syntax errors is skipped."""
        _write_py(mcp_tools_dir, "bad_syntax.py", "def broken(\n")
        _write_py(mcp_tools_dir, "ok.py", """\
def get_tools(**kwargs):
    return ["ok_tool"]
""")
        tools = discover_mcp_tools(mcp_tools_dir)
        assert tools == ["ok_tool"]

    def test_get_tools_exception_skipped(self, mcp_tools_dir):
        """If get_tools() raises, that file is skipped."""
        _write_py(mcp_tools_dir, "exploder.py", """\
def get_tools(**kwargs):
    raise ValueError("nope")
""")
        _write_py(mcp_tools_dir, "fine.py", """\
def get_tools(**kwargs):
    return ["fine_tool"]
""")
        tools = discover_mcp_tools(mcp_tools_dir)
        assert tools == ["fine_tool"]


class TestKwargsPassthrough:
    """Verify kwargs are passed to get_tools()."""

    def test_kwargs_forwarded(self, mcp_tools_dir):
        """All kwargs from discover_mcp_tools are passed to get_tools()."""
        _write_py(mcp_tools_dir, "kwarg_echo.py", """\
def get_tools(**kwargs):
    # Return kwargs as a tool (for inspection)
    return [kwargs]
""")
        mock_notify = lambda: None
        mock_find = lambda: None
        tools = discover_mcp_tools(
            mcp_tools_dir,
            caller_name="TestAgent",
            send_notification=mock_notify,
            find_agent=mock_find,
        )
        assert len(tools) == 1
        kw = tools[0]
        assert kw["caller_name"] == "TestAgent"
        assert kw["send_notification"] is mock_notify
        assert kw["find_agent"] is mock_find


class TestAlphabeticalOrder:
    """Files are loaded in sorted (alphabetical) order."""

    def test_alphabetical_load_order(self, mcp_tools_dir):
        """Tools from alpha.py come before those from zeta.py."""
        _write_py(mcp_tools_dir, "zeta.py", """\
def get_tools(**kwargs):
    return ["z_tool"]
""")
        _write_py(mcp_tools_dir, "alpha.py", """\
def get_tools(**kwargs):
    return ["a_tool"]
""")
        _write_py(mcp_tools_dir, "mid.py", """\
def get_tools(**kwargs):
    return ["m_tool"]
""")
        tools = discover_mcp_tools(mcp_tools_dir)
        assert tools == ["a_tool", "m_tool", "z_tool"]


class TestNonPyFilesSkipped:
    """Non-Python files and subdirectories are ignored."""

    def test_non_py_files_ignored(self, mcp_tools_dir):
        """YAML, txt, and other files are not loaded."""
        (mcp_tools_dir / "config.yaml").write_text("key: value\n", encoding="utf-8")
        (mcp_tools_dir / "README.txt").write_text("hello\n", encoding="utf-8")
        tools = discover_mcp_tools(mcp_tools_dir)
        assert tools == []

    def test_subdirectories_ignored(self, mcp_tools_dir):
        """Subdirectories are not traversed (flat namespace only)."""
        sub = mcp_tools_dir / "subdir"
        sub.mkdir()
        _write_py(sub, "nested.py", """\
def get_tools(**kwargs):
    return ["nested_tool"]
""")
        tools = discover_mcp_tools(mcp_tools_dir)
        assert tools == []


class TestMultipleFiles:
    """Multiple tool files are aggregated."""

    def test_tools_aggregated_from_multiple_files(self, mcp_tools_dir):
        """Tools from all valid files are combined into one list."""
        _write_py(mcp_tools_dir, "a.py", """\
def get_tools(**kwargs):
    return ["a1", "a2"]
""")
        _write_py(mcp_tools_dir, "b.py", """\
def get_tools(**kwargs):
    return ["b1"]
""")
        tools = discover_mcp_tools(mcp_tools_dir)
        assert tools == ["a1", "a2", "b1"]
