"""Tests for AgentManager permission mode handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudechic.agent_manager import AgentManager


@pytest.fixture
def options_factory():
    """Mock options factory for AgentManager."""

    def factory(**kwargs):
        mock = MagicMock()
        for k, v in kwargs.items():
            setattr(mock, k, v)
        return mock

    return factory


@pytest.fixture
def mock_agent_connect():
    """Mock Agent.connect to avoid SDK connection."""
    with patch("claudechic.agent.Agent.connect", new_callable=AsyncMock):
        yield


class TestGlobalPermissionModeInitialization:
    """Test global_permission_mode initialization from CONFIG."""

    def test_default_permission_mode_from_config(self, options_factory):
        """Verify global_permission_mode reads from CONFIG."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "acceptEdits"},
        ):
            manager = AgentManager(options_factory)
            assert manager.global_permission_mode == "acceptEdits"

    def test_default_permission_mode_fallback(self, options_factory):
        """Verify default is 'default' when not in CONFIG (fresh install behavior)."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {},
            clear=True,
        ):
            manager = AgentManager(options_factory)
            assert manager.global_permission_mode == "default"

    def test_default_permission_mode_explicit_bypass(self, options_factory):
        """Verify bypassPermissions is read correctly from CONFIG."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "bypassPermissions"},
        ):
            manager = AgentManager(options_factory)
            assert manager.global_permission_mode == "bypassPermissions"

    def test_default_permission_mode_plan(self, options_factory):
        """Verify plan mode is read correctly from CONFIG."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "plan"},
        ):
            manager = AgentManager(options_factory)
            assert manager.global_permission_mode == "plan"


class TestAgentInheritance:
    """Test that agents inherit global_permission_mode."""

    def test_create_unconnected_inherits_permission_mode(self, options_factory):
        """Verify create_unconnected() sets agent.permission_mode from global."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "acceptEdits"},
        ):
            manager = AgentManager(options_factory)
            agent = manager.create_unconnected("test", Path("/tmp"))

            assert agent.permission_mode == "acceptEdits"

    def test_create_unconnected_inherits_bypass_mode(self, options_factory):
        """Verify create_unconnected() inherits bypassPermissions."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "bypassPermissions"},
        ):
            manager = AgentManager(options_factory)
            agent = manager.create_unconnected("test", Path("/tmp"))

            assert agent.permission_mode == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_create_inherits_permission_mode(
        self, options_factory, mock_agent_connect
    ):
        """Verify create() sets agent.permission_mode from global."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "plan"},
        ):
            manager = AgentManager(options_factory)
            agent = await manager.create("test", Path("/tmp"))

            assert agent.permission_mode == "plan"

    @pytest.mark.asyncio
    async def test_create_inherits_bypass_mode(
        self, options_factory, mock_agent_connect
    ):
        """Verify create() inherits bypassPermissions."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "bypassPermissions"},
        ):
            manager = AgentManager(options_factory)
            agent = await manager.create("test", Path("/tmp"))

            assert agent.permission_mode == "bypassPermissions"


class TestSetGlobalPermissionMode:
    """Test set_global_permission_mode() behavior."""

    @pytest.mark.asyncio
    async def test_updates_global_permission_mode(self, options_factory):
        """Verify set_global_permission_mode() updates self.global_permission_mode."""
        manager = AgentManager(options_factory)
        # Default is now 'default' for fresh install (safe mode)
        assert manager.global_permission_mode == "default"

        await manager.set_global_permission_mode("acceptEdits")

        assert manager.global_permission_mode == "acceptEdits"

    @pytest.mark.asyncio
    async def test_calls_set_permission_mode_on_all_agents(self, options_factory):
        """Verify set_global_permission_mode() calls set_permission_mode on all agents."""
        manager = AgentManager(options_factory)

        # Create some mock agents
        agent1 = MagicMock()
        agent1.set_permission_mode = AsyncMock()
        agent2 = MagicMock()
        agent2.set_permission_mode = AsyncMock()

        manager.agents = {"a1": agent1, "a2": agent2}

        await manager.set_global_permission_mode("plan")

        agent1.set_permission_mode.assert_awaited_once_with("plan")
        agent2.set_permission_mode.assert_awaited_once_with("plan")

    @pytest.mark.asyncio
    async def test_notifies_observer(self, options_factory):
        """Verify set_global_permission_mode() notifies the observer."""
        manager = AgentManager(options_factory)

        mock_observer = MagicMock()
        manager.manager_observer = mock_observer

        await manager.set_global_permission_mode("acceptEdits")

        mock_observer.on_global_permission_mode_changed.assert_called_once_with(
            "acceptEdits"
        )

    @pytest.mark.asyncio
    async def test_no_observer_notification_when_none(self, options_factory):
        """Verify set_global_permission_mode() works without observer."""
        manager = AgentManager(options_factory)
        manager.manager_observer = None

        # Should not raise
        await manager.set_global_permission_mode("plan")

        assert manager.global_permission_mode == "plan"

    @pytest.mark.asyncio
    async def test_updates_all_agents_with_different_modes(self, options_factory):
        """Verify all agents get updated even if they had different modes."""
        manager = AgentManager(options_factory)

        # Create agents with different initial modes
        agent1 = MagicMock()
        agent1.permission_mode = "default"
        agent1.set_permission_mode = AsyncMock()

        agent2 = MagicMock()
        agent2.permission_mode = "acceptEdits"
        agent2.set_permission_mode = AsyncMock()

        manager.agents = {"a1": agent1, "a2": agent2}

        await manager.set_global_permission_mode("bypassPermissions")

        assert manager.global_permission_mode == "bypassPermissions"
        agent1.set_permission_mode.assert_awaited_once_with("bypassPermissions")
        agent2.set_permission_mode.assert_awaited_once_with("bypassPermissions")

    @pytest.mark.asyncio
    async def test_empty_agents_dict(self, options_factory):
        """Verify set_global_permission_mode() works with no agents."""
        manager = AgentManager(options_factory)
        manager.agents = {}

        mock_observer = MagicMock()
        manager.manager_observer = mock_observer

        await manager.set_global_permission_mode("plan")

        assert manager.global_permission_mode == "plan"
        mock_observer.on_global_permission_mode_changed.assert_called_once_with("plan")
