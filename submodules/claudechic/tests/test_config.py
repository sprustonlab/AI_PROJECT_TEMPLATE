"""Tests for config.py - configuration management.

Note: Because config.py loads CONFIG at import time using module-level globals,
we test the behaviors indirectly:
1. Direct inspection of _load() function behavior via code review
2. Integration tests via AgentManager (which reads CONFIG)
3. Verification of CONFIG values post-import

The actual config loading is validated through the test_agent_manager_permissions.py
tests which verify AgentManager correctly reads default_permission_mode from CONFIG.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestConfigModuleValues:
    """Test that CONFIG has correct values after module import."""

    def test_config_has_default_permission_mode_key(self):
        """Verify CONFIG contains default_permission_mode key."""
        from claudechic.config import CONFIG

        assert (
            "default_permission_mode" in CONFIG
            or CONFIG.get("default_permission_mode") == "default"
        ), "CONFIG should have default_permission_mode set"

    def test_config_has_analytics_section(self):
        """Verify CONFIG contains analytics section with required keys."""
        from claudechic.config import CONFIG

        assert "analytics" in CONFIG, "CONFIG should have analytics section"
        assert "id" in CONFIG["analytics"], "analytics should have id"
        assert "enabled" in CONFIG["analytics"], "analytics should have enabled"

    def test_config_has_worktree_section(self):
        """Verify CONFIG contains worktree section."""
        from claudechic.config import CONFIG

        assert "worktree" in CONFIG or CONFIG.setdefault("worktree", {}), (
            "CONFIG should have worktree section"
        )


class TestDefaultPermissionModeValue:
    """Test the default_permission_mode constant in config.py.

    The specification requires:
    - Fresh installs should default to "default" mode (safe)
    - Existing configs preserve their values
    """

    def test_fresh_install_default_is_safe_mode(self):
        """Verify the fresh install config uses 'default' permission mode.

        Per specification in 00_specification.md:
        - Fresh installs should start in 'default' mode (permission checking)
        - NOT 'bypassPermissions' (which skips checks)
        """
        # Read the actual config.py source to verify the default
        from pathlib import Path

        config_source = Path(__file__).parent.parent / "claudechic" / "config.py"
        source_code = config_source.read_text()

        # Verify the fresh install config sets "default" mode
        assert '"default_permission_mode": "default"' in source_code, (
            "Fresh install config should set default_permission_mode to 'default'"
        )

        # Verify it's NOT using bypassPermissions as default
        # (Look for the fresh install block, not existing config handling)
        lines = source_code.split("\n")
        in_fresh_install_block = False
        for i, line in enumerate(lines):
            if "New install" in line or "new_install = True" in line:
                in_fresh_install_block = True
            if in_fresh_install_block and "default_permission_mode" in line:
                assert '"default"' in line, (
                    f"Fresh install should use 'default' mode, found: {line}"
                )
                break

    def test_existing_config_fallback_is_default_mode(self):
        """Verify existing configs without permission_mode default to 'default'.

        This handles upgrade scenarios where older configs don't have the key.
        """
        from pathlib import Path

        config_source = Path(__file__).parent.parent / "claudechic" / "config.py"
        source_code = config_source.read_text()

        # The setdefault call should use "default"
        assert 'setdefault("default_permission_mode", "default")' in source_code, (
            "Missing default_permission_mode should fallback to 'default'"
        )


class TestAgentManagerConfigIntegration:
    """Integration tests verifying AgentManager reads config correctly.

    These tests verify the complete flow from CONFIG to AgentManager.
    """

    def test_agent_manager_uses_config_default(self):
        """Verify AgentManager initializes from CONFIG."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "default"},
        ):
            from claudechic.agent_manager import AgentManager

            manager = AgentManager(MagicMock())
            assert manager.global_permission_mode == "default", (
                "AgentManager should read 'default' mode from CONFIG"
            )

    def test_agent_manager_respects_bypass_config(self):
        """Verify existing bypass config is respected."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "bypassPermissions"},
        ):
            from claudechic.agent_manager import AgentManager

            manager = AgentManager(MagicMock())
            assert manager.global_permission_mode == "bypassPermissions", (
                "AgentManager should respect bypassPermissions from existing config"
            )

    def test_agent_manager_respects_acceptedits_config(self):
        """Verify existing acceptEdits config is respected."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "acceptEdits"},
        ):
            from claudechic.agent_manager import AgentManager

            manager = AgentManager(MagicMock())
            assert manager.global_permission_mode == "acceptEdits"

    def test_agent_manager_respects_plan_config(self):
        """Verify existing plan config is respected."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "plan"},
        ):
            from claudechic.agent_manager import AgentManager

            manager = AgentManager(MagicMock())
            assert manager.global_permission_mode == "plan"

    def test_agent_manager_fallback_when_key_missing(self):
        """Verify AgentManager falls back to 'default' when key is missing."""
        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {},
            clear=True,
        ):
            from claudechic.agent_manager import AgentManager

            manager = AgentManager(MagicMock())
            assert manager.global_permission_mode == "default", (
                "AgentManager should fallback to 'default' when key missing"
            )


class TestAgentInheritance:
    """Test that agents inherit global_permission_mode."""

    def test_create_unconnected_inherits_default_mode(self):
        """Verify create_unconnected() inherits 'default' mode."""
        from pathlib import Path

        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "default"},
        ):
            from claudechic.agent_manager import AgentManager

            manager = AgentManager(MagicMock())
            agent = manager.create_unconnected("test", Path("/tmp"))

            assert agent.permission_mode == "default", (
                "Agent should inherit 'default' permission mode"
            )

    def test_create_unconnected_inherits_bypass_mode(self):
        """Verify create_unconnected() inherits bypassPermissions when configured."""
        from pathlib import Path

        with patch.dict(
            "claudechic.agent_manager.CONFIG",
            {"default_permission_mode": "bypassPermissions"},
        ):
            from claudechic.agent_manager import AgentManager

            manager = AgentManager(MagicMock())
            agent = manager.create_unconnected("test", Path("/tmp"))

            assert agent.permission_mode == "bypassPermissions", (
                "Agent should inherit bypassPermissions from existing config"
            )


class TestConfigLoadFunction:
    """Test the _load() function's behavior through code inspection.

    Since _load() runs at import time with global paths, we verify
    the function's logic by inspecting the source code structure.
    """

    def test_load_function_handles_missing_file(self):
        """Verify _load() creates config when file doesn't exist."""
        from pathlib import Path

        config_source = Path(__file__).parent.parent / "claudechic" / "config.py"
        source_code = config_source.read_text()

        # Verify there's a branch for when config doesn't exist
        assert "if CONFIG_PATH.exists():" in source_code, (
            "_load() should check if CONFIG_PATH exists"
        )
        assert "else:" in source_code, "_load() should have else branch for new install"
        assert "new_install = True" in source_code, (
            "_load() should set new_install flag"
        )

    def test_load_function_preserves_existing_config(self):
        """Verify _load() reads existing config without overwriting."""
        from pathlib import Path

        config_source = Path(__file__).parent.parent / "claudechic" / "config.py"
        source_code = config_source.read_text()

        # Verify existing configs are loaded, not overwritten
        assert "yaml.safe_load(f)" in source_code, (
            "_load() should read existing config with yaml.safe_load"
        )

        # Verify setdefault is used (doesn't overwrite existing values)
        assert "setdefault(" in source_code, (
            "_load() should use setdefault to preserve existing values"
        )

    def test_load_function_migrates_old_config_path(self):
        """Verify _load() handles migration from old config path."""
        from pathlib import Path

        config_source = Path(__file__).parent.parent / "claudechic" / "config.py"
        source_code = config_source.read_text()

        # Verify old path migration logic exists
        assert "_OLD_CONFIG_PATH" in source_code, (
            "Should have _OLD_CONFIG_PATH for migration"
        )
        assert "_OLD_CONFIG_PATH.rename(CONFIG_PATH)" in source_code, (
            "Should rename old config to new path"
        )
        assert "_OLD_CONFIG_PATH.unlink()" in source_code, (
            "Should remove old config if both exist"
        )


class TestConfigSaveFunction:
    """Test the _save() function's behavior."""

    def test_save_function_writes_atomically(self):
        """Verify _save() uses atomic write pattern."""
        from pathlib import Path

        config_source = Path(__file__).parent.parent / "claudechic" / "config.py"
        source_code = config_source.read_text()

        # Verify atomic write pattern (tempfile + rename)
        assert "tempfile.mkstemp" in source_code, (
            "_save() should use tempfile for atomic write"
        )
        assert "os.replace" in source_code, (
            "_save() should use os.replace for atomic rename"
        )


class TestVimMigration:
    """Test vim -> vi-mode migration logic."""

    def test_vim_migration_logic_exists(self):
        """Verify vim to vi-mode migration code exists."""
        from pathlib import Path

        config_source = Path(__file__).parent.parent / "claudechic" / "config.py"
        source_code = config_source.read_text()

        # Verify migration from vim to vi-mode
        assert '"vim" in config' in source_code, "Should check for legacy 'vim' key"
        assert 'config["vi-mode"]' in source_code or "vi-mode" in source_code, (
            "Should migrate to 'vi-mode' key"
        )
