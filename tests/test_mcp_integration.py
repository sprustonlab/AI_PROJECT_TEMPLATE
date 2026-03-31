"""Layer 2: MockApp MCP Integration Tests.

Tests the full pipeline: discover_mcp_tools() → get_tools() → tool execution → response format.

Uses the MockApp/MockAgent pattern from claudechic's test_mcp_ask_agent.py to verify
that cluster MCP tools can be discovered, registered, and called with mocked subprocess.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudechic.mcp import (
    discover_mcp_tools,
    set_app,
    _find_agent_by_name,
    _send_prompt_fire_and_forget,
)

# ---------------------------------------------------------------------------
# Template mcp_tools path
# ---------------------------------------------------------------------------

TEMPLATE_MCP = Path(__file__).resolve().parent.parent / "template" / "mcp_tools"


def _get_tool_name(tool) -> str | None:
    """Get name from a tool (works with real SdkMcpTool or mock)."""
    return getattr(tool, "name", None) or getattr(tool, "_tool_name", None)


async def _call_tool(tool, args: dict):
    """Call a tool handler (works with real SdkMcpTool or mock)."""
    handler = getattr(tool, "handler", None)
    if handler is not None:
        return await handler(args)
    return await tool(args)


# ---------------------------------------------------------------------------
# MockApp / MockAgent (from claudechic test_mcp_ask_agent.py pattern)
# ---------------------------------------------------------------------------


class MockAgent:
    """Minimal agent mock for MCP tool testing."""

    def __init__(self, name: str):
        self.name = name
        self.id = name
        self.session_id = f"session-{name}"
        self.cwd = "/tmp"
        self.status = "idle"
        self.worktree = None
        self.client = True  # truthy → appears connected
        self.received_prompt = None

    @property
    def analytics_id(self) -> str:
        return self.session_id or self.id

    async def send(self, prompt: str) -> None:
        self.received_prompt = prompt


class MockAgentManager:
    """Minimal agent manager mock."""

    def __init__(self):
        self.agents: dict[str, MockAgent] = {}
        self.active: MockAgent | None = None

    def add(self, agent: MockAgent) -> None:
        self.agents[agent.name] = agent
        if self.active is None:
            self.active = agent

    def find_by_name(self, name: str) -> MockAgent | None:
        return self.agents.get(name)

    def __len__(self) -> int:
        return len(self.agents)


class MockApp:
    """Minimal app mock for MCP integration testing."""

    def __init__(self):
        self.agent_mgr = MockAgentManager()

    def run_worker(self, coro):
        """Mock run_worker — close coroutine to avoid warnings."""
        coro.close()


@pytest.fixture
def mock_app():
    """Create MockApp and register it with the MCP module."""
    app = MockApp()
    set_app(app)  # type: ignore
    return app


# ---------------------------------------------------------------------------
# Discovery integration tests
# ---------------------------------------------------------------------------


class TestDiscoverClusterTools:
    """Test discover_mcp_tools() with the real template mcp_tools/ directory."""

    def _discover_with_mock_subprocess(self, mcp_dir: Path, **extra_kwargs) -> list:
        """Run discover_mcp_tools with mocked subprocess to prevent real SSH/cluster calls."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
            return discover_mcp_tools(
                mcp_dir,
                caller_name="TestAgent",
                send_notification=lambda *a, **kw: None,
                find_agent=lambda name: (None, "not found"),
                **extra_kwargs,
            )

    def test_discover_lsf_tools(self, tmp_path):
        """discover_mcp_tools finds LSF tools from a directory with lsf.py + _cluster.py."""
        # Set up a mini mcp_tools/ with just LSF files
        mcp_dir = tmp_path / "mcp_tools"
        mcp_dir.mkdir()

        # Copy _cluster.py and lsf.py from template
        import shutil
        shutil.copy(TEMPLATE_MCP / "_cluster.py", mcp_dir / "_cluster.py")
        shutil.copy(TEMPLATE_MCP / "lsf.py", mcp_dir / "lsf.py")

        # Create a minimal lsf.yaml config
        (mcp_dir / "lsf.yaml").write_text(
            "ssh_target: \"\"\nlsf_profile: /misc/lsf/conf/profile.lsf\nwatch_poll_interval: 5\n"
        )

        tools = self._discover_with_mock_subprocess(mcp_dir)
        assert len(tools) == 6, f"Expected 6 LSF tools, got {len(tools)}"

        # Verify tool names
        names = [_get_tool_name(t) for t in tools]
        assert "cluster_jobs" in names
        assert "cluster_status" in names
        assert "cluster_submit" in names
        assert "cluster_kill" in names
        assert "cluster_logs" in names
        assert "cluster_watch" in names

    def test_discover_slurm_tools(self, tmp_path):
        """discover_mcp_tools finds SLURM tools from a directory with slurm.py + _cluster.py."""
        mcp_dir = tmp_path / "mcp_tools"
        mcp_dir.mkdir()

        import shutil
        shutil.copy(TEMPLATE_MCP / "_cluster.py", mcp_dir / "_cluster.py")
        shutil.copy(TEMPLATE_MCP / "slurm.py", mcp_dir / "slurm.py")

        (mcp_dir / "slurm.yaml").write_text(
            "ssh_target: \"\"\nwatch_poll_interval: 5\n"
        )

        tools = self._discover_with_mock_subprocess(mcp_dir)
        assert len(tools) == 6, f"Expected 6 SLURM tools, got {len(tools)}"

        names = [_get_tool_name(t) for t in tools]
        assert "cluster_jobs" in names
        assert "cluster_watch" in names

    def test_discover_both_backends(self, tmp_path):
        """Both LSF and SLURM tools discovered when both present."""
        mcp_dir = tmp_path / "mcp_tools"
        mcp_dir.mkdir()

        import shutil
        for f in ["_cluster.py", "lsf.py", "slurm.py"]:
            shutil.copy(TEMPLATE_MCP / f, mcp_dir / f)
        (mcp_dir / "lsf.yaml").write_text("ssh_target: \"\"\nwatch_poll_interval: 5\n")
        (mcp_dir / "slurm.yaml").write_text("ssh_target: \"\"\nwatch_poll_interval: 5\n")

        tools = self._discover_with_mock_subprocess(mcp_dir)
        assert len(tools) == 12, f"Expected 12 tools (6 LSF + 6 SLURM), got {len(tools)}"

    def test_cluster_helper_preloaded(self, tmp_path):
        """_cluster.py is pre-loaded into sys.modules before tool files import it."""
        mcp_dir = tmp_path / "mcp_tools"
        mcp_dir.mkdir()

        import shutil
        shutil.copy(TEMPLATE_MCP / "_cluster.py", mcp_dir / "_cluster.py")
        shutil.copy(TEMPLATE_MCP / "lsf.py", mcp_dir / "lsf.py")
        (mcp_dir / "lsf.yaml").write_text("ssh_target: \"\"\nwatch_poll_interval: 5\n")

        self._discover_with_mock_subprocess(mcp_dir)

        # _cluster should be in sys.modules
        assert "mcp_tools._cluster" in sys.modules


# ---------------------------------------------------------------------------
# Tool execution tests (mocked subprocess)
# ---------------------------------------------------------------------------


class TestToolExecution:
    """Test individual tool handlers with mocked subprocess."""

    @pytest.fixture(autouse=True)
    def _setup_tools(self, tmp_path):
        """Discover LSF tools into self.tools for each test."""
        mcp_dir = tmp_path / "mcp_tools"
        mcp_dir.mkdir()

        import shutil
        shutil.copy(TEMPLATE_MCP / "_cluster.py", mcp_dir / "_cluster.py")
        shutil.copy(TEMPLATE_MCP / "lsf.py", mcp_dir / "lsf.py")
        (mcp_dir / "lsf.yaml").write_text(
            "ssh_target: \"\"\nlsf_profile: /misc/lsf/conf/profile.lsf\nwatch_poll_interval: 5\n"
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
            self.tools = discover_mcp_tools(
                mcp_dir,
                caller_name="TestAgent",
                send_notification=lambda *a, **kw: None,
                find_agent=lambda name: (None, "not found"),
            )
        self.tool_map = {_get_tool_name(t): t for t in self.tools}

    @pytest.mark.asyncio
    async def test_cluster_jobs_returns_mcp_format(self):
        """cluster_jobs returns proper MCP response format."""
        bjobs_output = (
            "JOBID   USER    STAT  QUEUE      FROM_HOST   EXEC_HOST   JOB_NAME   SUBMIT_TIME\n"
            "123456  moharb  RUN   gpu        login01     gpu-0042    train_v3   Mar 28 14:30\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=bjobs_output, stderr="", returncode=0
            )
            tool = self.tool_map["cluster_jobs"]
            result = await _call_tool(tool, {})

        # Verify MCP response format
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert "isError" not in result

        # Verify parsed content
        data = json.loads(result["content"][0]["text"])
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["job_id"] == "123456"
        assert data[0]["status"] == "RUN"

    @pytest.mark.asyncio
    async def test_cluster_status_returns_mcp_format(self):
        """cluster_status returns proper MCP response with job details."""
        bjobs_l_output = (
            "Job <123456>, Job Name <train_v3>, User <moharb>,\n"
            "                     Status <RUN>, Queue <gpu>,\n"
            "                     Command <python train.py>\n"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=bjobs_l_output, stderr="", returncode=0
            )
            tool = self.tool_map["cluster_status"]
            result = await _call_tool(tool, {"job_id": "123456"})

        assert "content" in result
        data = json.loads(result["content"][0]["text"])
        assert data["job_id"] == "123456"
        assert data["job_name"] == "train_v3"
        assert data["status"] == "RUN"

    @pytest.mark.asyncio
    async def test_cluster_submit_returns_job_id(self):
        """cluster_submit returns MCP response with job ID."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="Job <999999> is submitted to queue <gpu>.",
                stderr="",
                returncode=0,
            )
            tool = self.tool_map["cluster_submit"]
            result = await _call_tool(tool, {
                "queue": "gpu",
                "cpus": 4,
                "walltime": "2:00",
                "command": "python train.py",
            })

        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert data["job_id"] == "999999"

    @pytest.mark.asyncio
    async def test_cluster_kill_returns_success(self):
        """cluster_kill returns success MCP response."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="Job <123456> is being terminated",
                stderr="",
                returncode=0,
            )
            tool = self.tool_map["cluster_kill"]
            result = await _call_tool(tool, {"job_id": "123456"})

        assert "isError" not in result
        data = json.loads(result["content"][0]["text"])
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_cluster_jobs_error_returns_iserror(self):
        """When bjobs fails, cluster_jobs returns isError=True."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="", stderr="Connection refused", returncode=1
            )
            tool = self.tool_map["cluster_jobs"]
            result = await _call_tool(tool, {})

        assert result.get("isError") is True
        assert "content" in result

    @pytest.mark.asyncio
    async def test_cluster_watch_without_wiring_returns_error(self, tmp_path):
        """cluster_watch without notification wiring returns graceful error."""
        # Discover with send_notification=None to test graceful degradation
        mcp_dir = tmp_path / "mcp_tools_watch"
        mcp_dir.mkdir()
        import shutil
        shutil.copy(TEMPLATE_MCP / "_cluster.py", mcp_dir / "_cluster.py")
        shutil.copy(TEMPLATE_MCP / "lsf.py", mcp_dir / "lsf.py")
        (mcp_dir / "lsf.yaml").write_text(
            "ssh_target: \"\"\nwatch_poll_interval: 5\n"
        )
        with patch("subprocess.run", return_value=MagicMock(stdout="", stderr="", returncode=0)):
            unwired_tools = discover_mcp_tools(mcp_dir)  # No kwargs → None for all
        watch = [t for t in unwired_tools if _get_tool_name(t) == "cluster_watch"][0]
        result = await _call_tool(watch, {"job_id": "123456"})
        assert result.get("isError") is True
        assert "not available" in result["content"][0]["text"].lower()


# ---------------------------------------------------------------------------
# kwargs wiring verification
# ---------------------------------------------------------------------------


class TestKwargsWiring:
    """Verify kwargs from discover_mcp_tools reach get_tools correctly."""

    def test_send_notification_wired(self, tmp_path):
        """When send_notification is provided, cluster_watch should be fully wired."""
        mcp_dir = tmp_path / "mcp_tools"
        mcp_dir.mkdir()

        import shutil
        shutil.copy(TEMPLATE_MCP / "_cluster.py", mcp_dir / "_cluster.py")
        shutil.copy(TEMPLATE_MCP / "lsf.py", mcp_dir / "lsf.py")
        (mcp_dir / "lsf.yaml").write_text(
            "ssh_target: \"\"\nwatch_poll_interval: 5\n"
        )

        mock_notify = MagicMock()
        mock_find = MagicMock(return_value=(MockAgent("test"), None))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
            tools = discover_mcp_tools(
                mcp_dir,
                caller_name="TestAgent",
                send_notification=mock_notify,
                find_agent=mock_find,
            )

        # cluster_watch should now be wirable (not returning error)
        watch = [t for t in tools if _get_tool_name(t) == "cluster_watch"]
        assert len(watch) == 1
        # The watch tool was created with real send_notification
        # When called, it should NOT return "not available" error
        # (it would try to create a task instead)
