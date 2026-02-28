"""Tests for Agent permission functionality."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
from contextlib import ExitStack

from claudechic.agent import Agent


async def empty_async_gen():
    """Empty async generator for mocking receive_response."""
    return
    yield  # noqa: unreachable - makes this an async generator


@pytest.fixture
def mock_sdk_for_agent():
    """Create a mock SDK client for agent tests."""
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.query = AsyncMock()
    mock_client.interrupt = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.set_permission_mode = AsyncMock()
    mock_client.receive_response = lambda: empty_async_gen()
    mock_client._transport = None

    # Mock FileIndex to avoid subprocess issues
    from claudechic.file_index import FileIndex

    mock_file_index = MagicMock(spec=FileIndex)
    mock_file_index.refresh = AsyncMock()
    mock_file_index.files = []

    with ExitStack() as stack:
        stack.enter_context(
            patch("claudechic.agent.ClaudeSDKClient", return_value=mock_client)
        )
        stack.enter_context(
            patch("claudechic.agent.FileIndex", return_value=mock_file_index)
        )
        # Patch get_claude_pid_from_client to avoid process introspection
        stack.enter_context(
            patch("claudechic.processes.get_claude_pid_from_client", return_value=None)
        )
        yield mock_client


class TestPermissionModes:
    """Tests for PERMISSION_MODES set."""

    def test_bypassPermissions_in_modes(self):
        """Verify 'bypassPermissions' is in PERMISSION_MODES."""
        assert "bypassPermissions" in Agent.PERMISSION_MODES

    def test_all_expected_modes_present(self):
        """Verify all expected permission modes are present."""
        expected = {"default", "acceptEdits", "plan", "planSwarm", "bypassPermissions"}
        assert Agent.PERMISSION_MODES == expected

    def test_permission_modes_is_set(self):
        """Verify PERMISSION_MODES is a set (not list/tuple)."""
        assert isinstance(Agent.PERMISSION_MODES, set)


class TestConnectPermissionMode:
    """Tests for SDK notification after connect."""

    @pytest.mark.asyncio
    async def test_set_permission_mode_called_after_connect_if_not_default(
        self, mock_sdk_for_agent, tmp_path
    ):
        """Verify set_permission_mode is called AFTER connect if mode != 'default'."""
        agent = Agent("test", tmp_path)
        agent.permission_mode = "acceptEdits"

        from claude_agent_sdk import ClaudeAgentOptions

        options = ClaudeAgentOptions(permission_mode="default")
        await agent.connect(options)

        # Verify connect was called first
        mock_sdk_for_agent.connect.assert_called_once()

        # Verify set_permission_mode was called with the correct mode
        mock_sdk_for_agent.set_permission_mode.assert_called_once_with("acceptEdits")

    @pytest.mark.asyncio
    async def test_set_permission_mode_not_called_if_default(
        self, mock_sdk_for_agent, tmp_path
    ):
        """Verify set_permission_mode is NOT called if permission_mode == 'default'."""
        agent = Agent("test", tmp_path)
        agent.permission_mode = "default"  # Default mode

        from claude_agent_sdk import ClaudeAgentOptions

        options = ClaudeAgentOptions(permission_mode="default")
        await agent.connect(options)

        # Verify connect was called
        mock_sdk_for_agent.connect.assert_called_once()

        # Verify set_permission_mode was NOT called
        mock_sdk_for_agent.set_permission_mode.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_permission_mode_called_with_plan_mode(
        self, mock_sdk_for_agent, tmp_path
    ):
        """Verify set_permission_mode works with 'plan' mode."""
        agent = Agent("test", tmp_path)
        agent.permission_mode = "plan"

        from claude_agent_sdk import ClaudeAgentOptions

        options = ClaudeAgentOptions(permission_mode="default")
        await agent.connect(options)

        mock_sdk_for_agent.set_permission_mode.assert_called_once_with("plan")

    @pytest.mark.asyncio
    async def test_set_permission_mode_called_with_bypassPermissions(
        self, mock_sdk_for_agent, tmp_path
    ):
        """Verify set_permission_mode works with 'bypassPermissions' mode."""
        agent = Agent("test", tmp_path)
        agent.permission_mode = "bypassPermissions"

        from claude_agent_sdk import ClaudeAgentOptions

        options = ClaudeAgentOptions(permission_mode="default")
        await agent.connect(options)

        mock_sdk_for_agent.set_permission_mode.assert_called_once_with(
            "bypassPermissions"
        )


class TestSetPermissionModeMethod:
    """Tests for Agent.set_permission_mode() method."""

    @pytest.mark.asyncio
    async def test_updates_permission_mode_field(self, mock_sdk_for_agent, tmp_path):
        """Verify set_permission_mode updates the permission_mode field."""
        agent = Agent("test", tmp_path)
        assert agent.permission_mode == "default"

        await agent.set_permission_mode("acceptEdits")
        assert agent.permission_mode == "acceptEdits"

        await agent.set_permission_mode("plan")
        assert agent.permission_mode == "plan"

    @pytest.mark.asyncio
    async def test_calls_sdk_if_session_exists(self, mock_sdk_for_agent, tmp_path):
        """Verify set_permission_mode calls SDK if session exists."""
        agent = Agent("test", tmp_path)

        from claude_agent_sdk import ClaudeAgentOptions

        options = ClaudeAgentOptions(permission_mode="default")
        await agent.connect(options)

        # Clear the call from connect
        mock_sdk_for_agent.set_permission_mode.reset_mock()

        # Set a session_id (simulating active session)
        agent.session_id = "test-session-123"

        await agent.set_permission_mode("acceptEdits")

        # Should call SDK since session exists
        mock_sdk_for_agent.set_permission_mode.assert_called_once_with("acceptEdits")

    @pytest.mark.asyncio
    async def test_does_not_call_sdk_if_no_session(self, tmp_path):
        """Verify set_permission_mode does NOT call SDK if no session exists."""
        agent = Agent("test", tmp_path)
        agent.client = MagicMock()
        agent.client.set_permission_mode = AsyncMock()
        agent.session_id = None  # No session

        await agent.set_permission_mode("acceptEdits")

        # Should NOT call SDK since no session
        agent.client.set_permission_mode.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_call_sdk_if_no_client(self, tmp_path):
        """Verify set_permission_mode does NOT call SDK if no client exists."""
        agent = Agent("test", tmp_path)
        agent.client = None
        agent.session_id = "test-session-123"

        # Should not raise even with no client
        await agent.set_permission_mode("acceptEdits")
        assert agent.permission_mode == "acceptEdits"

    @pytest.mark.asyncio
    async def test_no_change_if_same_mode(self, tmp_path):
        """Verify set_permission_mode does nothing if mode unchanged."""
        agent = Agent("test", tmp_path)
        agent.permission_mode = "acceptEdits"
        agent.client = MagicMock()
        agent.client.set_permission_mode = AsyncMock()
        agent.session_id = "test-session"

        await agent.set_permission_mode("acceptEdits")

        # Should NOT call SDK since mode is unchanged
        agent.client.set_permission_mode.assert_not_called()

    @pytest.mark.asyncio
    async def test_notifies_observer(self, tmp_path):
        """Verify set_permission_mode notifies observer when mode changes."""
        agent = Agent("test", tmp_path)
        mock_observer = MagicMock()
        agent.observer = mock_observer

        await agent.set_permission_mode("plan")

        mock_observer.on_permission_mode_changed.assert_called_once_with(agent)

    @pytest.mark.asyncio
    async def test_does_not_notify_observer_if_unchanged(self, tmp_path):
        """Verify observer is NOT notified if mode unchanged."""
        agent = Agent("test", tmp_path)
        agent.permission_mode = "acceptEdits"
        mock_observer = MagicMock()
        agent.observer = mock_observer

        await agent.set_permission_mode("acceptEdits")

        mock_observer.on_permission_mode_changed.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_mode_raises(self, tmp_path):
        """Verify invalid permission mode raises AssertionError."""
        agent = Agent("test", tmp_path)

        with pytest.raises(AssertionError, match="Invalid permission mode"):
            await agent.set_permission_mode("invalid_mode")


class TestSetPermissionModeLocal:
    """Tests for Agent._set_permission_mode_local() method."""

    def test_updates_field_without_sdk_call(self, tmp_path):
        """Verify _set_permission_mode_local updates field without SDK call."""
        agent = Agent("test", tmp_path)
        agent.client = MagicMock()
        agent.client.set_permission_mode = AsyncMock()
        agent.session_id = "test-session"

        agent._set_permission_mode_local("plan")

        assert agent.permission_mode == "plan"
        # Should NOT call SDK
        agent.client.set_permission_mode.assert_not_called()

    def test_notifies_observer(self, tmp_path):
        """Verify _set_permission_mode_local notifies observer."""
        agent = Agent("test", tmp_path)
        mock_observer = MagicMock()
        agent.observer = mock_observer

        agent._set_permission_mode_local("acceptEdits")

        mock_observer.on_permission_mode_changed.assert_called_once_with(agent)

    def test_invalid_mode_raises(self, tmp_path):
        """Verify invalid mode raises AssertionError."""
        agent = Agent("test", tmp_path)

        with pytest.raises(AssertionError, match="Invalid permission mode"):
            agent._set_permission_mode_local("not_a_valid_mode")

    def test_does_not_notify_if_unchanged(self, tmp_path):
        """Verify observer is NOT notified if mode unchanged."""
        agent = Agent("test", tmp_path)
        agent.permission_mode = "plan"
        mock_observer = MagicMock()
        agent.observer = mock_observer

        agent._set_permission_mode_local("plan")

        mock_observer.on_permission_mode_changed.assert_not_called()
