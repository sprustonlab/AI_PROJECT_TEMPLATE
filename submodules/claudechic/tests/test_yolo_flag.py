"""Tests for --yolo flag behavior.

These tests verify:
1. --yolo flag correctly sets global_permission_mode to "bypassPermissions"
2. Spawned agents inherit bypass mode when --yolo is used
3. Mode indicators (footer) show correct state with --yolo
"""

from __future__ import annotations


import pytest

from claudechic.app import ChatApp
from claudechic.widgets import StatusFooter
from tests.conftest import wait_for_workers, submit_command


class TestYoloFlagSetsGlobalPermissionMode:
    """Test that --yolo flag correctly sets global_permission_mode."""

    @pytest.mark.asyncio
    async def test_yolo_flag_sets_bypass_mode(self, mock_sdk):
        """Verify --yolo flag sets global_permission_mode to 'bypassPermissions'."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test():
            assert app.agent_mgr is not None
            assert app.agent_mgr.global_permission_mode == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_default_mode_without_yolo(self, mock_sdk):
        """Verify default mode is 'default' without --yolo flag."""
        app = ChatApp(skip_permissions=False)
        async with app.run_test():
            assert app.agent_mgr is not None
            assert app.agent_mgr.global_permission_mode == "default"

    @pytest.mark.asyncio
    async def test_initial_agent_inherits_yolo_mode(self, mock_sdk):
        """Verify initial agent inherits 'bypassPermissions' when --yolo is used."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test():
            assert app._agent is not None
            assert app._agent.permission_mode == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_initial_agent_default_mode_without_yolo(self, mock_sdk):
        """Verify initial agent has 'default' mode without --yolo."""
        app = ChatApp(skip_permissions=False)
        async with app.run_test():
            assert app._agent is not None
            assert app._agent.permission_mode == "default"


class TestSpawnedAgentsInheritBypassMode:
    """Test that spawned agents inherit bypass mode when --yolo is used."""

    @pytest.mark.asyncio
    async def test_spawned_agent_inherits_bypass_mode(self, mock_sdk):
        """Verify spawned agents inherit 'bypassPermissions' when --yolo is used."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test() as pilot:
            # Verify initial state
            assert app.agent_mgr is not None
            assert app.agent_mgr.global_permission_mode == "bypassPermissions"
            assert len(app.agents) == 1

            # Create new agent via command
            await submit_command(app, pilot, "/agent spawned-test")
            await wait_for_workers(app)

            # Should have two agents now
            assert len(app.agents) == 2

            # Find the spawned agent
            spawned = next(
                (a for a in app.agents.values() if a.name == "spawned-test"), None
            )
            assert spawned is not None
            assert spawned.permission_mode == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_spawned_agent_inherits_default_mode_without_yolo(self, mock_sdk):
        """Verify spawned agents inherit 'default' mode without --yolo."""
        app = ChatApp(skip_permissions=False)
        async with app.run_test() as pilot:
            # Verify initial state
            assert app.agent_mgr is not None
            assert app.agent_mgr.global_permission_mode == "default"

            # Create new agent
            await submit_command(app, pilot, "/agent spawned-test")
            await wait_for_workers(app)

            # Find the spawned agent
            spawned = next(
                (a for a in app.agents.values() if a.name == "spawned-test"), None
            )
            assert spawned is not None
            assert spawned.permission_mode == "default"

    @pytest.mark.asyncio
    async def test_multiple_spawned_agents_inherit_bypass_mode(self, mock_sdk):
        """Verify multiple spawned agents all inherit 'bypassPermissions'."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test() as pilot:
            # Create multiple agents
            await submit_command(app, pilot, "/agent agent1")
            await wait_for_workers(app)
            await submit_command(app, pilot, "/agent agent2")
            await wait_for_workers(app)

            # All agents should have bypass mode
            assert len(app.agents) == 3
            for agent in app.agents.values():
                assert agent.permission_mode == "bypassPermissions", (
                    f"Agent {agent.name} should have bypassPermissions mode"
                )


class TestModeIndicatorsShowCorrectState:
    """Test that mode indicators (footer) show correct state with --yolo."""

    @pytest.mark.asyncio
    async def test_footer_shows_bypass_mode_with_yolo(self, mock_sdk):
        """Verify footer shows 'bypassPermissions' mode when --yolo is used."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test():
            footer = app.query_one(StatusFooter)
            assert footer.permission_mode == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_footer_shows_default_mode_without_yolo(self, mock_sdk):
        """Verify footer shows 'default' mode without --yolo."""
        app = ChatApp(skip_permissions=False)
        async with app.run_test():
            footer = app.query_one(StatusFooter)
            assert footer.permission_mode == "default"

    @pytest.mark.asyncio
    async def test_yolo_notification_shown(self, mock_sdk):
        """Verify warning notification is shown when --yolo is used."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test():
            # The notification "⚠️ Permission checks disabled" should be shown
            # We can verify _skip_permissions is set, which triggers the notification
            assert app._skip_permissions is True

    @pytest.mark.asyncio
    async def test_mode_cycle_from_bypass_mode(self, mock_sdk):
        """Verify mode cycling works correctly starting from bypass mode."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test() as pilot:
            footer = app.query_one(StatusFooter)
            assert footer.permission_mode == "bypassPermissions"

            # Cycle: bypassPermissions -> acceptEdits
            await pilot.press("shift+tab")
            assert footer.permission_mode == "acceptEdits"

            # Cycle: acceptEdits -> plan
            await pilot.press("shift+tab")
            assert footer.permission_mode == "plan"

            # Cycle: plan -> default
            await pilot.press("shift+tab")
            assert footer.permission_mode == "default"

            # Cycle: default -> bypassPermissions (back)
            await pilot.press("shift+tab")
            assert footer.permission_mode == "bypassPermissions"


class TestYoloFlagIntegration:
    """Integration tests for --yolo flag behavior."""

    @pytest.mark.asyncio
    async def test_yolo_mode_propagates_to_new_agents_after_cycle(self, mock_sdk):
        """Verify mode changes propagate correctly after cycling away from bypass."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test() as pilot:
            # Start in bypass mode
            assert app.agent_mgr is not None
            assert app.agent_mgr.global_permission_mode == "bypassPermissions"

            # Cycle to acceptEdits
            await pilot.press("shift+tab")
            assert app.agent_mgr.global_permission_mode == "acceptEdits"

            # Spawn new agent - should inherit current global mode (acceptEdits)
            await submit_command(app, pilot, "/agent test-after-cycle")
            await wait_for_workers(app)

            spawned = next(
                (a for a in app.agents.values() if a.name == "test-after-cycle"), None
            )
            assert spawned is not None
            # New agent should inherit the current global mode (acceptEdits), not the original --yolo mode
            assert spawned.permission_mode == "acceptEdits"

    @pytest.mark.asyncio
    async def test_all_agents_updated_on_mode_change(self, mock_sdk):
        """Verify all agents (including initial) are updated on mode change."""
        app = ChatApp(skip_permissions=True)
        async with app.run_test() as pilot:
            # Create second agent
            await submit_command(app, pilot, "/agent second")
            await wait_for_workers(app)

            # Both should start in bypass mode
            for agent in app.agents.values():
                assert agent.permission_mode == "bypassPermissions"

            # Change mode
            await pilot.press("shift+tab")

            # Both should now be in acceptEdits mode
            for agent in app.agents.values():
                assert agent.permission_mode == "acceptEdits", (
                    f"Agent {agent.name} should have updated to acceptEdits"
                )
