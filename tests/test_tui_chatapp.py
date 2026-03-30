"""Layer 4: TestChatApp with Textual Pilot API.

Tests claudechic's TUI headlessly using Textual's App.run_test() + Pilot API.
Uses the mock_sdk fixture from claudechic to prevent real Claude SDK connections.

This provides the "Playwright for TUI" infrastructure that enables:
- App startup verification
- MCP tool registration verification
- /agent command testing
- Widget state verification
- Future guardrail E2E testing

Reuses patterns from claudechic's own test_app_ui.py.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# SDK mock fixture (mirrors claudechic/tests/conftest.py)
# ---------------------------------------------------------------------------


async def _empty_async_gen():
    """Empty async generator for mocking receive_response."""
    return
    yield  # noqa: unreachable


async def _wait_for_workers(app):
    """Wait for all background workers to complete."""
    await app.workers.wait_for_complete()


async def _submit_command(app, pilot, command: str):
    """Submit a slash command, handling autocomplete properly."""
    from claudechic.widgets import ChatInput

    input_widget = app.query_one("#input", ChatInput)
    input_widget.text = command
    await pilot.pause()

    # Hide autocomplete if active
    if input_widget._autocomplete and input_widget._autocomplete.display:
        input_widget._autocomplete.action_hide()
        await pilot.pause()

    input_widget.action_submit()
    await pilot.pause()


@pytest.fixture
def mock_sdk():
    """Patch SDK to not actually connect.

    Mirrors the fixture from claudechic/tests/conftest.py.
    Patches both app.py and agent.py imports.
    """
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.query = AsyncMock()
    mock_client.interrupt = AsyncMock()
    mock_client.get_server_info = AsyncMock(return_value={"commands": [], "models": []})
    mock_client.set_permission_mode = AsyncMock()
    mock_client.receive_response = lambda: _empty_async_gen()
    mock_client._transport = None

    from claudechic.file_index import FileIndex

    mock_file_index = MagicMock(spec=FileIndex)
    mock_file_index.refresh = AsyncMock()
    mock_file_index.files = []

    with ExitStack() as stack:
        stack.enter_context(
            patch.dict("claudechic.analytics.CONFIG", {"analytics": {"enabled": False}})
        )
        stack.enter_context(
            patch("claudechic.app.ClaudeSDKClient", return_value=mock_client)
        )
        stack.enter_context(
            patch("claudechic.agent.ClaudeSDKClient", return_value=mock_client)
        )
        stack.enter_context(
            patch("claudechic.agent.FileIndex", return_value=mock_file_index)
        )
        stack.enter_context(
            patch("claudechic.app.FileIndex", return_value=mock_file_index)
        )
        yield mock_client


# ---------------------------------------------------------------------------
# Template MCP tools path
# ---------------------------------------------------------------------------

TEMPLATE_MCP = Path(__file__).resolve().parent.parent / "template" / "mcp_tools"


def _get_tool_name(tool) -> str | None:
    """Get name from a tool (works with real SdkMcpTool or mock)."""
    return getattr(tool, "name", None) or getattr(tool, "_tool_name", None)


# ---------------------------------------------------------------------------
# Layer 4 Tests: TUI with Textual Pilot API
# ---------------------------------------------------------------------------


class TestChatAppStartup:
    """Verify ChatApp starts headlessly and mounts expected widgets."""

    @pytest.mark.asyncio
    async def test_app_mounts_core_widgets(self, mock_sdk):
        """ChatApp starts and mounts ChatInput, AgentSection, StatusFooter."""
        from claudechic.app import ChatApp
        from claudechic.widgets import ChatInput, AgentSection, StatusFooter

        app = ChatApp()
        async with app.run_test():
            assert app.query_one("#input", ChatInput)
            assert app.query_one("#agent-section", AgentSection)
            assert app.query_one(StatusFooter)

    @pytest.mark.asyncio
    async def test_app_has_initial_agent(self, mock_sdk):
        """ChatApp creates one initial agent on startup."""
        from claudechic.app import ChatApp

        app = ChatApp()
        async with app.run_test():
            assert len(app.agents) == 1
            assert app._agent is not None
            assert app.active_agent_id is not None

    @pytest.mark.asyncio
    async def test_app_initial_permission_mode(self, mock_sdk):
        """Initial permission mode is 'default'."""
        from claudechic.app import ChatApp

        app = ChatApp()
        async with app.run_test():
            assert app._agent.permission_mode == "default"


class TestMCPToolRegistration:
    """Verify MCP tools are registered when mcp_tools/ directory is present."""

    @pytest.mark.asyncio
    async def test_discover_tools_during_server_creation(self, mock_sdk, tmp_path):
        """When mcp_tools/ exists in cwd, tools are discovered during server creation."""
        from claudechic.mcp import discover_mcp_tools

        # Create a mock mcp_tools/ with a simple tool
        mcp_dir = tmp_path / "mcp_tools"
        mcp_dir.mkdir()
        (mcp_dir / "simple.py").write_text(
            "def get_tools(**kwargs):\n    return ['simple_tool']\n"
        )

        tools = discover_mcp_tools(mcp_dir, caller_name="test")
        assert "simple_tool" in tools

    @pytest.mark.asyncio
    async def test_discover_cluster_tools_in_context(self, mock_sdk, tmp_path):
        """LSF tools are discovered when lsf.py is in mcp_tools/."""
        from claudechic.mcp import discover_mcp_tools

        mcp_dir = tmp_path / "mcp_tools"
        mcp_dir.mkdir()
        shutil.copy(TEMPLATE_MCP / "_cluster.py", mcp_dir / "_cluster.py")
        shutil.copy(TEMPLATE_MCP / "lsf.py", mcp_dir / "lsf.py")
        (mcp_dir / "lsf.yaml").write_text("ssh_target: \"\"\nwatch_poll_interval: 5\n")

        with patch("subprocess.run", return_value=MagicMock(stdout="", stderr="", returncode=0)):
            tools = discover_mcp_tools(
                mcp_dir,
                caller_name="test",
                send_notification=lambda *a, **kw: None,
                find_agent=lambda n: (None, "not found"),
            )

        tool_names = [_get_tool_name(t) for t in tools]
        assert "cluster_jobs" in tool_names
        assert "cluster_submit" in tool_names


class TestAgentCommands:
    """Test /agent commands through the TUI."""

    @pytest.mark.asyncio
    async def test_agent_list_command(self, mock_sdk):
        """'/agent' lists current agents without crashing."""
        from claudechic.app import ChatApp

        app = ChatApp()
        async with app.run_test() as pilot:
            assert len(app.agents) == 1
            await _submit_command(app, pilot, "/agent")
            # Should not crash; still one agent
            assert len(app.agents) == 1

    @pytest.mark.asyncio
    async def test_agent_create_command(self, mock_sdk):
        """'/agent foo' creates a new agent."""
        from claudechic.app import ChatApp

        app = ChatApp()
        async with app.run_test() as pilot:
            assert len(app.agents) == 1
            await _submit_command(app, pilot, "/agent new-agent")
            await _wait_for_workers(app)
            assert len(app.agents) == 2
            names = [a.name for a in app.agents.values()]
            assert "new-agent" in names

    @pytest.mark.asyncio
    async def test_agent_close_command(self, mock_sdk):
        """'/agent close' closes the current agent."""
        from claudechic.app import ChatApp

        app = ChatApp()
        async with app.run_test() as pilot:
            # Create a second agent first
            await _submit_command(app, pilot, "/agent to-close")
            await _wait_for_workers(app)
            assert len(app.agents) == 2

            # Close it
            await _submit_command(app, pilot, "/agent close")
            await _wait_for_workers(app)
            await pilot.pause()
            assert len(app.agents) == 1

    @pytest.mark.asyncio
    async def test_cannot_close_last_agent(self, mock_sdk):
        """Cannot close the last remaining agent."""
        from claudechic.app import ChatApp

        app = ChatApp()
        async with app.run_test() as pilot:
            assert len(app.agents) == 1
            await _submit_command(app, pilot, "/agent close")
            await _wait_for_workers(app)
            assert len(app.agents) == 1

    @pytest.mark.asyncio
    async def test_agent_switch_keybinding(self, mock_sdk):
        """Ctrl+1/Ctrl+2 switches between agents."""
        from claudechic.app import ChatApp

        app = ChatApp()
        async with app.run_test() as pilot:
            await _submit_command(app, pilot, "/agent second")
            await _wait_for_workers(app)
            await pilot.pause()
            assert len(app.agents) == 2

            ids = list(app.agents.keys())
            # Should be on second agent (just created)
            assert app.active_agent_id == ids[1]

            # Switch to first
            await pilot.press("ctrl+1")
            await pilot.pause()
            assert app.active_agent_id == ids[0]

            # Switch to second
            await pilot.press("ctrl+2")
            await pilot.pause()
            assert app.active_agent_id == ids[1]


class TestPermissionModeCycle:
    """Test permission mode cycling through the TUI."""

    @pytest.mark.asyncio
    async def test_shift_tab_cycles_modes(self, mock_sdk):
        """Shift+Tab cycles through permission modes."""
        from claudechic.app import ChatApp

        app = ChatApp()
        async with app.run_test() as pilot:
            assert app._agent.permission_mode == "default"

            await pilot.press("shift+tab")
            assert app._agent.permission_mode == "bypassPermissions"

            await pilot.press("shift+tab")
            assert app._agent.permission_mode == "acceptEdits"

            await pilot.press("shift+tab")
            assert app._agent.permission_mode == "plan"

            await pilot.press("shift+tab")
            assert app._agent.permission_mode == "default"

    @pytest.mark.asyncio
    async def test_footer_reflects_permission_mode(self, mock_sdk):
        """StatusFooter shows current permission mode."""
        from claudechic.app import ChatApp
        from claudechic.widgets import StatusFooter

        app = ChatApp()
        async with app.run_test() as pilot:
            footer = app.query_one(StatusFooter)
            assert footer.permission_mode == "default"

            await pilot.press("shift+tab")
            assert footer.permission_mode == "bypassPermissions"


class TestClearCommand:
    """Test /clear command through TUI."""

    @pytest.mark.asyncio
    async def test_clear_removes_messages(self, mock_sdk):
        """/clear removes all chat messages from view."""
        from claudechic.app import ChatApp
        from claudechic.widgets import ChatMessage

        app = ChatApp()
        async with app.run_test() as pilot:
            chat_view = app._chat_view
            assert chat_view is not None

            # Mount fake messages
            chat_view.mount(ChatMessage("Test 1"))
            chat_view.mount(ChatMessage("Test 2"))
            await pilot.pause()

            await _submit_command(app, pilot, "/clear")
            await _wait_for_workers(app)
            await pilot.pause()

            messages = list(chat_view.query(ChatMessage))
            assert len(messages) == 0
