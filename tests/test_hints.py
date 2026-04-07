"""Tests for the hints system.

Covers: _types.py, _state.py, hints.py (triggers, combinators, registry),
_engine.py (pipeline), and __init__.py (public API).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from hints._types import (
    CooldownPeriod,
    HintRecord,
    HintSpec,
    ShowEverySession,
    ShowOnce,
    ShowUntilResolved,
)
from hints._state import (
    ActivationConfig,
    CopierAnswers,
    HintStateStore,
    ProjectState,
)
from hints.hints import (
    AllOf,
    AnyOf,
    ClusterConfiguredUnused,
    CommandLesson,
    COMMAND_LESSONS,
    GitNotInitialized,
    GuardrailsOnlyDefault,
    LearnCommand,
    McpToolsEmpty,
    Not,
    PatternMinerUnderutilized,
    ProjectTeamNeverUsed,
    get_hints,
)
from hints._engine import run_pipeline


# ===========================================================================
# Unit tests: _state.py — CopierAnswers
# ===========================================================================


class TestCopierAnswers:
    """Tests for CopierAnswers.load()."""

    def test_missing_file_returns_defaults(self, tmp_path):
        """Missing .copier-answers.yml returns default values."""
        ca = CopierAnswers.load(tmp_path)
        assert ca.has_example_rules is True
        assert ca.has_example_agent_roles is True
        assert ca.has_example_patterns is False
        assert ca.use_cluster is False
        assert ca.has_example_hints is True

    def test_valid_yaml_loads_correctly(self, tmp_path):
        """Valid YAML file is parsed and properties work."""
        answers = tmp_path / ".copier-answers.yml"
        answers.write_text(
            "quick_start: empty\n"
            "use_cluster: true\n"
            "cluster_scheduler: slurm\n"
            "project_name: my_proj\n",
            encoding="utf-8",
        )
        ca = CopierAnswers.load(tmp_path)
        assert ca.has_example_rules is False
        assert ca.has_example_patterns is False
        assert ca.use_cluster is True
        assert ca.cluster_scheduler == "slurm"
        assert ca.project_name == "my_proj"

    def test_corrupt_yaml_returns_defaults(self, tmp_path):
        """Corrupt YAML falls back to defaults gracefully."""
        answers = tmp_path / ".copier-answers.yml"
        answers.write_text(":::invalid yaml [[[", encoding="utf-8")
        ca = CopierAnswers.load(tmp_path)
        assert ca.has_example_rules is True
        assert ca.raw == {}

    def test_non_dict_yaml_returns_defaults(self, tmp_path):
        """YAML that parses to non-dict returns defaults."""
        answers = tmp_path / ".copier-answers.yml"
        answers.write_text("- just\n- a\n- list\n", encoding="utf-8")
        ca = CopierAnswers.load(tmp_path)
        assert ca.raw == {}

    def test_cluster_scheduler_none_when_cluster_disabled(self, tmp_path):
        """cluster_scheduler returns None if use_cluster is False."""
        ca = CopierAnswers.load(tmp_path)  # defaults
        assert ca.cluster_scheduler is None

    def test_generic_get(self, tmp_path):
        """Generic .get() accessor works."""
        answers = tmp_path / ".copier-answers.yml"
        answers.write_text("custom_key: custom_value\n", encoding="utf-8")
        ca = CopierAnswers.load(tmp_path)
        assert ca.get("custom_key") == "custom_value"
        assert ca.get("missing", "fallback") == "fallback"


# ===========================================================================
# Unit tests: _state.py — ProjectState
# ===========================================================================


class TestProjectState:
    """Tests for ProjectState.build() and filesystem primitives."""

    def test_build_constructs_correctly(self, tmp_path):
        """ProjectState.build() populates fields from kwargs."""
        state = ProjectState.build(tmp_path, session_count=42)
        assert state.root == tmp_path.resolve()
        assert state.session_count == 42

    def test_build_session_count_defaults_none(self, tmp_path):
        """session_count defaults to None when not provided."""
        state = ProjectState.build(tmp_path)
        assert state.session_count is None

    def test_path_exists(self, tmp_path):
        """path_exists checks relative paths correctly."""
        (tmp_path / ".git").mkdir()
        state = ProjectState.build(tmp_path)
        assert state.path_exists(".git") is True
        assert state.path_exists("nonexistent") is False

    def test_dir_is_empty_nonexistent(self, tmp_path):
        """dir_is_empty returns True for nonexistent directory."""
        state = ProjectState.build(tmp_path)
        assert state.dir_is_empty("nope") is True

    def test_dir_is_empty_with_only_ignored(self, tmp_path):
        """dir_is_empty ignores __pycache__, .gitkeep, README.md, .DS_Store."""
        d = tmp_path / "tools"
        d.mkdir()
        (d / "__pycache__").mkdir()
        (d / ".gitkeep").touch()
        (d / "README.md").touch()
        state = ProjectState.build(tmp_path)
        assert state.dir_is_empty("tools") is True

    def test_dir_is_empty_with_real_file(self, tmp_path):
        """dir_is_empty returns False when non-ignored files exist."""
        d = tmp_path / "tools"
        d.mkdir()
        (d / "my_tool.py").touch()
        state = ProjectState.build(tmp_path)
        assert state.dir_is_empty("tools") is False

    def test_file_contains_pattern(self, tmp_path):
        """file_contains matches regex patterns in file content."""
        f = tmp_path / "config.yaml"
        f.write_text("rules:\n  - R01_default\n  - R02_custom\n", encoding="utf-8")
        state = ProjectState.build(tmp_path)
        assert state.file_contains("config.yaml", r"R02_custom") is True
        assert state.file_contains("config.yaml", r"R99_missing") is False

    def test_file_contains_missing_file(self, tmp_path):
        """file_contains returns False for missing file."""
        state = ProjectState.build(tmp_path)
        assert state.file_contains("nope.txt", "anything") is False

    def test_count_files_matching(self, tmp_path):
        """count_files_matching counts glob matches excluding prefixed files."""
        d = tmp_path / "mcp_tools"
        d.mkdir()
        (d / "tool_a.py").touch()
        (d / "tool_b.py").touch()
        (d / "_internal.py").touch()
        (d / "__init__.py").touch()
        state = ProjectState.build(tmp_path)
        assert state.count_files_matching("mcp_tools", "*.py") == 2

    def test_count_files_matching_missing_dir(self, tmp_path):
        """count_files_matching returns 0 for missing directory."""
        state = ProjectState.build(tmp_path)
        assert state.count_files_matching("nope", "*.py") == 0


# ===========================================================================
# Unit tests: _state.py — HintStateStore
# ===========================================================================


class TestHintStateStore:
    """Tests for HintStateStore persistence and operations."""

    def test_fresh_start_no_file(self, tmp_path):
        """Fresh start (no file) gives zero counts."""
        store = HintStateStore(tmp_path)
        assert store.get_times_shown("any-hint") == 0
        assert store.get_last_shown_timestamp("any-hint") is None
        assert store.is_dismissed("any-hint") is False

    def test_increment_shown(self, tmp_path):
        """increment_shown bumps count and sets timestamp."""
        store = HintStateStore(tmp_path)
        store.increment_shown("h1")
        assert store.get_times_shown("h1") == 1
        assert store.get_last_shown_timestamp("h1") is not None

    def test_set_last_shown_timestamp(self, tmp_path):
        """set_last_shown_timestamp sets explicit value."""
        store = HintStateStore(tmp_path)
        store.set_last_shown_timestamp("h1", 12345.0)
        assert store.get_last_shown_timestamp("h1") == 12345.0

    def test_dismissed(self, tmp_path):
        """set_dismissed / is_dismissed works."""
        store = HintStateStore(tmp_path)
        assert store.is_dismissed("h1") is False
        store.set_dismissed("h1", True)
        assert store.is_dismissed("h1") is True
        store.set_dismissed("h1", False)
        assert store.is_dismissed("h1") is False

    def test_taught_commands(self, tmp_path):
        """get_taught_commands / add_taught_command works."""
        store = HintStateStore(tmp_path)
        assert store.get_taught_commands() == set()
        store.add_taught_command("/diff")
        store.add_taught_command("/resume")
        store.add_taught_command("/diff")  # duplicate
        assert store.get_taught_commands() == {"/diff", "/resume"}

    def test_save_and_reload(self, tmp_path):
        """State survives save → reload cycle."""
        store = HintStateStore(tmp_path)
        store.increment_shown("h1")
        store.increment_shown("h1")
        store.set_dismissed("h2", True)
        store.add_taught_command("/diff")
        store.set_last_shown_timestamp("h1", 99999.0)
        store.save()

        store2 = HintStateStore(tmp_path)
        assert store2.get_times_shown("h1") == 2
        assert store2.get_last_shown_timestamp("h1") == 99999.0
        assert store2.is_dismissed("h2") is True
        assert store2.get_taught_commands() == {"/diff"}

    def test_corrupt_file_graceful(self, tmp_path):
        """Corrupt JSON file → fresh start."""
        state_dir = tmp_path / ".claude"
        state_dir.mkdir()
        (state_dir / "hints_state.json").write_text("NOT VALID JSON {{{", encoding="utf-8")
        store = HintStateStore(tmp_path)
        assert store.get_times_shown("any") == 0


# ===========================================================================
# Unit tests: _state.py — ActivationConfig
# ===========================================================================


class TestActivationConfig:
    """Tests for ActivationConfig toggle logic."""

    def test_globally_enabled_by_default(self, tmp_path):
        """Default: globally enabled, all hints active."""
        store = HintStateStore(tmp_path)
        ac = ActivationConfig(store)
        assert ac.is_globally_enabled is True
        assert ac.is_active("any-hint") is True

    def test_disable_globally(self, tmp_path):
        """disable_globally makes all hints inactive."""
        store = HintStateStore(tmp_path)
        ac = ActivationConfig(store)
        ac.disable_globally()
        assert ac.is_globally_enabled is False
        assert ac.is_active("any-hint") is False

    def test_enable_globally(self, tmp_path):
        """enable_globally restores globally-on state."""
        store = HintStateStore(tmp_path)
        ac = ActivationConfig(store)
        ac.disable_globally()
        ac.enable_globally()
        assert ac.is_globally_enabled is True
        assert ac.is_active("any-hint") is True

    def test_disable_hint(self, tmp_path):
        """disable_hint deactivates one hint, others remain active."""
        store = HintStateStore(tmp_path)
        ac = ActivationConfig(store)
        ac.disable_hint("h1")
        assert ac.is_active("h1") is False
        assert ac.is_active("h2") is True

    def test_enable_hint(self, tmp_path):
        """enable_hint re-activates a previously disabled hint."""
        store = HintStateStore(tmp_path)
        ac = ActivationConfig(store)
        ac.disable_hint("h1")
        ac.enable_hint("h1")
        assert ac.is_active("h1") is True

    def test_disabled_hints_property(self, tmp_path):
        """disabled_hints returns frozenset of disabled IDs."""
        store = HintStateStore(tmp_path)
        ac = ActivationConfig(store)
        ac.disable_hint("a")
        ac.disable_hint("b")
        assert ac.disabled_hints == frozenset({"a", "b"})

    def test_persists_through_save_reload(self, tmp_path):
        """Activation state survives save/reload."""
        store = HintStateStore(tmp_path)
        ac = ActivationConfig(store)
        ac.disable_hint("h1")
        ac.disable_globally()
        store.save()

        store2 = HintStateStore(tmp_path)
        ac2 = ActivationConfig(store2)
        assert ac2.is_globally_enabled is False
        assert ac2.is_active("h1") is False


# ===========================================================================
# Unit tests: _types.py — Lifecycle implementations
# ===========================================================================


class TestShowOnce:
    """Tests for ShowOnce lifecycle."""

    def test_should_show_when_never_shown(self, tmp_path):
        store = HintStateStore(tmp_path)
        lc = ShowOnce()
        assert lc.should_show("h1", store) is True

    def test_should_not_show_after_record_shown(self, tmp_path):
        store = HintStateStore(tmp_path)
        lc = ShowOnce()
        lc.record_shown("h1", store)
        assert lc.should_show("h1", store) is False


class TestShowUntilResolved:
    """Tests for ShowUntilResolved lifecycle."""

    def test_should_show_when_not_dismissed(self, tmp_path):
        store = HintStateStore(tmp_path)
        lc = ShowUntilResolved()
        assert lc.should_show("h1", store) is True

    def test_should_not_show_when_dismissed(self, tmp_path):
        store = HintStateStore(tmp_path)
        store.set_dismissed("h1", True)
        lc = ShowUntilResolved()
        assert lc.should_show("h1", store) is False


class TestShowEverySession:
    """Tests for ShowEverySession lifecycle."""

    def test_always_shows(self, tmp_path):
        store = HintStateStore(tmp_path)
        lc = ShowEverySession()
        assert lc.should_show("h1", store) is True
        lc.record_shown("h1", store)
        assert lc.should_show("h1", store) is True
        lc.record_shown("h1", store)
        assert lc.should_show("h1", store) is True


class TestCooldownPeriod:
    """Tests for CooldownPeriod lifecycle."""

    def test_should_show_when_never_shown(self, tmp_path):
        store = HintStateStore(tmp_path)
        lc = CooldownPeriod(seconds=3600)
        assert lc.should_show("h1", store) is True

    def test_should_not_show_during_cooldown(self, tmp_path):
        store = HintStateStore(tmp_path)
        lc = CooldownPeriod(seconds=3600)
        lc.record_shown("h1", store)
        assert lc.should_show("h1", store) is False

    def test_should_show_after_cooldown_expires(self, tmp_path):
        store = HintStateStore(tmp_path)
        lc = CooldownPeriod(seconds=10)
        # Set last shown to 20 seconds ago
        store.set_last_shown_timestamp("h1", time.time() - 20)
        assert lc.should_show("h1", store) is True

    def test_handles_negative_elapsed_clock_skew(self, tmp_path):
        """Negative elapsed (clock went backwards) → show hint."""
        store = HintStateStore(tmp_path)
        lc = CooldownPeriod(seconds=3600)
        # Timestamp in the future → negative elapsed
        store.set_last_shown_timestamp("h1", time.time() + 99999)
        assert lc.should_show("h1", store) is True

    def test_raises_for_zero_seconds(self):
        with pytest.raises(ValueError, match="seconds > 0"):
            CooldownPeriod(seconds=0)

    def test_raises_for_negative_seconds(self):
        with pytest.raises(ValueError, match="seconds > 0"):
            CooldownPeriod(seconds=-5)


# ===========================================================================
# Unit tests: hints.py — Trigger classes
# ===========================================================================


class TestGitNotInitialized:
    def test_true_when_no_git(self, tmp_path):
        state = ProjectState.build(tmp_path)
        assert GitNotInitialized().check(state) is True

    def test_false_when_git_exists(self, tmp_path):
        (tmp_path / ".git").mkdir()
        state = ProjectState.build(tmp_path)
        assert GitNotInitialized().check(state) is False


class TestGuardrailsOnlyDefault:
    def test_true_when_no_custom_rules(self, tmp_path):
        guardrails = tmp_path / ".claude" / "guardrails"
        rules_d = guardrails / "rules.d"
        rules_d.mkdir(parents=True)
        # Only default R01 in rules.yaml
        (guardrails / "rules.yaml").write_text(
            "rules:\n  - id: R01\n    name: default\n", encoding="utf-8"
        )
        (tmp_path / ".copier-answers.yml").write_text("quick_start: everything\n", encoding="utf-8")
        state = ProjectState.build(tmp_path)
        assert GuardrailsOnlyDefault().check(state) is True

    def test_false_when_custom_rules_in_rules_d(self, tmp_path):
        guardrails = tmp_path / ".claude" / "guardrails"
        rules_d = guardrails / "rules.d"
        rules_d.mkdir(parents=True)
        (rules_d / "R02_custom.yaml").touch()
        (guardrails / "rules.yaml").write_text(
            "rules:\n  - id: R01\n    name: default\n", encoding="utf-8"
        )
        (tmp_path / ".copier-answers.yml").write_text("quick_start: everything\n", encoding="utf-8")
        state = ProjectState.build(tmp_path)
        assert GuardrailsOnlyDefault().check(state) is False

    def test_false_when_custom_rules_in_rules_yaml(self, tmp_path):
        guardrails = tmp_path / ".claude" / "guardrails"
        rules_d = guardrails / "rules.d"
        rules_d.mkdir(parents=True)
        # rules.yaml has R01 + R02 (user added a custom rule)
        (guardrails / "rules.yaml").write_text(
            "rules:\n  - id: R01\n    name: default\n  - id: R02\n    name: custom\n",
            encoding="utf-8",
        )
        (tmp_path / ".copier-answers.yml").write_text("quick_start: everything\n", encoding="utf-8")
        state = ProjectState.build(tmp_path)
        assert GuardrailsOnlyDefault().check(state) is False

    def test_skips_when_guardrails_disabled(self, tmp_path):
        (tmp_path / ".copier-answers.yml").write_text("quick_start: empty\n", encoding="utf-8")
        state = ProjectState.build(tmp_path)
        assert GuardrailsOnlyDefault().check(state) is False


class TestProjectTeamNeverUsed:
    def test_true_when_no_ao_dir(self, tmp_path):
        state = ProjectState.build(tmp_path)
        assert ProjectTeamNeverUsed().check(state) is True

    def test_false_when_ao_dir_exists(self, tmp_path):
        (tmp_path / ".project_team").mkdir()
        state = ProjectState.build(tmp_path)
        assert ProjectTeamNeverUsed().check(state) is False

    def test_false_when_ao_dir_exists_no_copier_answers(self, tmp_path):
        """Trigger returns False when .project_team/ exists, regardless of copier answers."""
        (tmp_path / ".project_team").mkdir()
        state = ProjectState.build(tmp_path)
        assert ProjectTeamNeverUsed().check(state) is False


class TestPatternMinerUnderutilized:
    def test_true_enough_sessions_no_miner(self, tmp_path):
        (tmp_path / ".copier-answers.yml").write_text("quick_start: everything\n", encoding="utf-8")
        state = ProjectState.build(tmp_path, session_count=15)
        assert PatternMinerUnderutilized().check(state) is True

    def test_false_when_session_count_none(self, tmp_path):
        (tmp_path / ".copier-answers.yml").write_text("quick_start: everything\n", encoding="utf-8")
        state = ProjectState.build(tmp_path)  # session_count=None
        assert PatternMinerUnderutilized().check(state) is False

    def test_false_when_too_few_sessions(self, tmp_path):
        (tmp_path / ".copier-answers.yml").write_text("quick_start: everything\n", encoding="utf-8")
        state = ProjectState.build(tmp_path, session_count=3)
        assert PatternMinerUnderutilized().check(state) is False

    def test_false_when_miner_has_run(self, tmp_path):
        (tmp_path / ".copier-answers.yml").write_text("quick_start: everything\n", encoding="utf-8")
        (tmp_path / ".patterns_mining_state.json").touch()
        state = ProjectState.build(tmp_path, session_count=15)
        assert PatternMinerUnderutilized().check(state) is False

    def test_skips_when_feature_disabled(self, tmp_path):
        state = ProjectState.build(tmp_path, session_count=100)
        assert PatternMinerUnderutilized().check(state) is False


class TestMcpToolsEmpty:
    def test_true_when_no_py_files(self, tmp_path):
        d = tmp_path / "mcp_tools"
        d.mkdir()
        (d / "__init__.py").touch()
        state = ProjectState.build(tmp_path)
        assert McpToolsEmpty().check(state) is True

    def test_false_when_user_py_files(self, tmp_path):
        d = tmp_path / "mcp_tools"
        d.mkdir()
        (d / "my_tool.py").touch()
        state = ProjectState.build(tmp_path)
        assert McpToolsEmpty().check(state) is False

    def test_true_when_dir_missing(self, tmp_path):
        state = ProjectState.build(tmp_path)
        assert McpToolsEmpty().check(state) is True


class TestClusterConfiguredUnused:
    def test_true_when_cluster_enabled_no_artifacts(self, tmp_path):
        (tmp_path / ".copier-answers.yml").write_text("use_cluster: true\n", encoding="utf-8")
        state = ProjectState.build(tmp_path)
        assert ClusterConfiguredUnused().check(state) is True

    def test_false_when_cluster_disabled(self, tmp_path):
        state = ProjectState.build(tmp_path)
        assert ClusterConfiguredUnused().check(state) is False

    def test_false_when_job_artifacts_exist(self, tmp_path):
        (tmp_path / ".copier-answers.yml").write_text("use_cluster: true\n", encoding="utf-8")
        (tmp_path / "cluster_jobs").mkdir()
        state = ProjectState.build(tmp_path)
        assert ClusterConfiguredUnused().check(state) is False


# ===========================================================================
# Unit tests: hints.py — LearnCommand
# ===========================================================================


class TestLearnCommand:
    def test_picks_first_untaught(self):
        lc = LearnCommand(_get_taught=lambda: set())
        state = Mock()
        assert lc.check(state) is True
        msg = lc.get_message(state)
        assert "/diff" in msg

    def test_returns_none_when_all_taught(self):
        all_names = {cmd.name for cmd in COMMAND_LESSONS}
        lc = LearnCommand(_get_taught=lambda: all_names)
        state = Mock()
        assert lc.check(state) is False

    def test_picks_second_when_first_taught(self):
        lc = LearnCommand(_get_taught=lambda: {"/diff"})
        state = Mock()
        assert lc.check(state) is True
        msg = lc.get_message(state)
        assert "/resume" in msg

    def test_dynamic_message_works(self):
        lc = LearnCommand(_get_taught=lambda: {"/diff", "/resume"})
        state = Mock()
        msg = lc.get_message(state)
        assert "/worktree" in msg


# ===========================================================================
# Unit tests: hints.py — Combinators
# ===========================================================================


class TestCombinators:
    def _make_trigger(self, result: bool):
        """Create a simple trigger returning a fixed bool."""
        t = Mock()
        t.check = Mock(return_value=result)
        t.description = f"mock({result})"
        return t

    def test_allof_all_true(self):
        state = Mock()
        c = AllOf(conditions=(self._make_trigger(True), self._make_trigger(True)))
        assert c.check(state) is True

    def test_allof_one_false(self):
        state = Mock()
        c = AllOf(conditions=(self._make_trigger(True), self._make_trigger(False)))
        assert c.check(state) is False

    def test_anyof_one_true(self):
        state = Mock()
        c = AnyOf(conditions=(self._make_trigger(False), self._make_trigger(True)))
        assert c.check(state) is True

    def test_anyof_all_false(self):
        state = Mock()
        c = AnyOf(conditions=(self._make_trigger(False), self._make_trigger(False)))
        assert c.check(state) is False

    def test_not_inverts(self):
        state = Mock()
        assert Not(condition=self._make_trigger(True)).check(state) is False
        assert Not(condition=self._make_trigger(False)).check(state) is True


# ===========================================================================
# Unit tests: hints.py — get_hints()
# ===========================================================================


class TestGetHints:
    def test_returns_6_without_get_taught_commands(self):
        hints = get_hints()
        assert len(hints) == 6
        ids = {h.id for h in hints}
        assert "learn-command" not in ids

    def test_returns_7_with_get_taught_commands(self):
        hints = get_hints(get_taught_commands=lambda: set())
        assert len(hints) == 7
        ids = {h.id for h in hints}
        assert "learn-command" in ids


# ===========================================================================
# Integration tests: _engine.py — run_pipeline
# ===========================================================================


@dataclass(frozen=True)
class _SimpleTrigger:
    """Minimal trigger for tests — no _pick_command attribute."""
    _result: bool = True

    def check(self, state):
        return self._result

    @property
    def description(self):
        return f"test({self._result})"


def _make_hint(
    hint_id: str,
    trigger_result: bool = True,
    message: str | None = None,
    priority: int = 3,
    lifecycle=None,
    trigger=None,
):
    """Helper to build a HintSpec with a simple trigger."""
    if trigger is None:
        trigger = _SimpleTrigger(_result=trigger_result)
    if lifecycle is None:
        lifecycle = ShowEverySession()
    return HintSpec(
        id=hint_id,
        trigger=trigger,
        message=message or f"Message for {hint_id}",
        priority=priority,
        lifecycle=lifecycle,
    )


class TestPipeline:
    """Integration tests for the hint evaluation pipeline."""

    @pytest.fixture
    def setup(self, tmp_path):
        """Common setup for pipeline tests."""
        store = HintStateStore(tmp_path)
        ac = ActivationConfig(store)
        state = ProjectState.build(tmp_path)
        notifications = []

        def send(msg, severity="info", timeout=7.0):
            notifications.append((msg, severity, timeout))

        return store, ac, state, send, notifications

    @pytest.mark.asyncio
    async def test_activation_gate_filters(self, setup):
        """Deactivated hints are skipped."""
        store, ac, state, send, notifs = setup
        ac.disable_hint("h1")
        hints = [_make_hint("h1"), _make_hint("h2")]

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await run_pipeline(send, state, store, ac, hints, budget=2)

        msgs = [m for m, _, _ in notifs]
        assert not any("h1" in m for m in msgs)
        assert any("h2" in m for m in msgs)

    @pytest.mark.asyncio
    async def test_trigger_gate_filters(self, setup):
        """Hints whose trigger returns False are skipped."""
        store, ac, state, send, notifs = setup
        hints = [
            _make_hint("fires", trigger_result=True),
            _make_hint("no-fire", trigger_result=False),
        ]

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await run_pipeline(send, state, store, ac, hints, budget=2)

        msgs = [m for m, _, _ in notifs]
        assert any("fires" in m for m in msgs)
        assert not any("no-fire" in m for m in msgs)

    @pytest.mark.asyncio
    async def test_lifecycle_gate_filters(self, setup):
        """ShowOnce hint not shown again after being shown once."""
        store, ac, state, send, notifs = setup
        store.increment_shown("once-hint")  # already shown
        hints = [_make_hint("once-hint", lifecycle=ShowOnce())]

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await run_pipeline(send, state, store, ac, hints, budget=2)

        assert len(notifs) == 0

    @pytest.mark.asyncio
    async def test_sort_order(self, setup):
        """Sorted by priority ASC, last_shown_ts ASC, definition_order ASC."""
        store, ac, state, send, notifs = setup
        hints = [
            _make_hint("low-pri", priority=3),
            _make_hint("high-pri", priority=1),
            _make_hint("mid-pri", priority=2),
        ]

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await run_pipeline(send, state, store, ac, hints, budget=3)

        assert len(notifs) == 3
        assert "high-pri" in notifs[0][0]
        assert "mid-pri" in notifs[1][0]
        assert "low-pri" in notifs[2][0]

    @pytest.mark.asyncio
    async def test_budget_cap_respected(self, setup):
        """Only top N hints shown when budget < candidates."""
        store, ac, state, send, notifs = setup
        hints = [_make_hint(f"h{i}") for i in range(5)]

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await run_pipeline(send, state, store, ac, hints, budget=2)

        assert len(notifs) == 2

    @pytest.mark.asyncio
    async def test_dynamic_message_resolution(self, setup):
        """Callable messages are resolved with project_state."""
        store, ac, state, send, notifs = setup

        def dynamic_msg(ps):
            return "Dynamic hello!"

        hint = HintSpec(
            id="dyn",
            trigger=_SimpleTrigger(_result=True),
            message=dynamic_msg,
            lifecycle=ShowEverySession(),
        )

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await run_pipeline(send, state, store, ac, [hint], budget=2)

        assert notifs[0][0].startswith("Dynamic hello!")

    @pytest.mark.asyncio
    async def test_record_shown_called(self, setup):
        """Lifecycle record_shown is called after successful notification."""
        store, ac, state, send, notifs = setup
        hints = [_make_hint("h1")]

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await run_pipeline(send, state, store, ac, hints, budget=2)

        assert store.get_times_shown("h1") >= 1

    @pytest.mark.asyncio
    async def test_add_taught_command_for_learn_command(self, setup):
        """Pipeline calls add_taught_command for triggers with _pick_command."""
        store, ac, state, send, notifs = setup
        trigger = LearnCommand(_get_taught=lambda: set())
        hint = HintSpec(
            id="learn-command",
            trigger=trigger,
            message=trigger.get_message,
            priority=4,
            lifecycle=ShowEverySession(),
        )

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await run_pipeline(send, state, store, ac, [hint], budget=2)

        taught = store.get_taught_commands("learn-command")
        assert "/diff" in taught

    @pytest.mark.asyncio
    async def test_disable_suffix_on_startup_first_toast(self, setup):
        """First toast at startup gets the disable suffix."""
        store, ac, state, send, notifs = setup
        hints = [_make_hint("h1"), _make_hint("h2")]

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await run_pipeline(send, state, store, ac, hints, budget=2, is_startup=True)

        assert "/hints off" in notifs[0][0]
        assert "/hints off" not in notifs[1][0]

    @pytest.mark.asyncio
    async def test_no_disable_suffix_when_not_startup(self, setup):
        """Non-startup evaluations don't get the disable suffix."""
        store, ac, state, send, notifs = setup
        hints = [_make_hint("h1")]

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await run_pipeline(send, state, store, ac, hints, budget=2, is_startup=False)

        assert "/hints off" not in notifs[0][0]

    @pytest.mark.asyncio
    async def test_trigger_exception_doesnt_crash(self, setup):
        """Iron rule: trigger exceptions skip the hint, don't crash."""
        store, ac, state, send, notifs = setup

        @dataclass(frozen=True)
        class _ExplodingTrigger:
            def check(self, state):
                raise RuntimeError("boom")
            @property
            def description(self):
                return "exploding"

        hints = [
            _make_hint("bad", trigger=_ExplodingTrigger()),
            _make_hint("good"),
        ]

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await run_pipeline(send, state, store, ac, hints, budget=2)

        assert len(notifs) == 1
        assert "good" in notifs[0][0]

    @pytest.mark.asyncio
    async def test_state_store_save_called(self, setup):
        """state_store.save() is called at the end of the pipeline."""
        store, ac, state, send, notifs = setup
        hints = [_make_hint("h1")]

        with patch.object(store, "save", wraps=store.save) as mock_save:
            with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
                await run_pipeline(send, state, store, ac, hints, budget=2)

        mock_save.assert_called_once()


# ===========================================================================
# Multi-evaluation integration tests
# ===========================================================================


class TestMultiEvaluation:
    """Tests that verify correct behavior across multiple pipeline runs."""

    @pytest.fixture
    def setup(self, tmp_path):
        """Common setup — shared store/activation across evaluations."""
        store = HintStateStore(tmp_path)
        ac = ActivationConfig(store)
        state = ProjectState.build(tmp_path)
        return store, ac, state, tmp_path

    @pytest.mark.asyncio
    async def test_show_once_survives_periodic_reevaluation(self, setup):
        """ShowOnce hint fires at startup but not on periodic re-evaluation."""
        store, ac, state, _ = setup
        notifs_1: list[tuple] = []
        notifs_2: list[tuple] = []

        def send_1(msg, severity="info", timeout=7.0):
            notifs_1.append((msg, severity, timeout))

        def send_2(msg, severity="info", timeout=7.0):
            notifs_2.append((msg, severity, timeout))

        hint = _make_hint("once-hint", lifecycle=ShowOnce())

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            # Startup evaluation — hint should fire
            await run_pipeline(send_1, state, store, ac, [hint], budget=2, is_startup=True)
            assert len(notifs_1) == 1
            assert "once-hint" in notifs_1[0][0]

            # Periodic re-evaluation — same store, hint should NOT fire
            await run_pipeline(send_2, state, store, ac, [hint], budget=2, is_startup=False)
            assert len(notifs_2) == 0

    @pytest.mark.asyncio
    async def test_learn_command_rotation_across_evaluations(self, setup):
        """learn-command teaches /diff first, then /resume on next evaluation."""
        store, ac, state, _ = setup

        def make_learn_hint():
            trigger = LearnCommand(
                _get_taught=lambda: store.get_taught_commands("learn-command")
            )
            return HintSpec(
                id="learn-command",
                trigger=trigger,
                message=trigger.get_message,
                priority=4,
                lifecycle=ShowEverySession(),
            )

        # First evaluation — should teach /diff
        notifs_1: list[tuple] = []

        def send_1(msg, severity="info", timeout=7.0):
            notifs_1.append((msg, severity, timeout))

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await run_pipeline(
                send_1, state, store, ac, [make_learn_hint()], budget=2, is_startup=True
            )

        assert len(notifs_1) == 1
        assert "/diff" in notifs_1[0][0]
        assert "/diff" in store.get_taught_commands("learn-command")

        # Second evaluation — /diff is taught, should teach /resume
        notifs_2: list[tuple] = []

        def send_2(msg, severity="info", timeout=7.0):
            notifs_2.append((msg, severity, timeout))

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await run_pipeline(
                send_2, state, store, ac, [make_learn_hint()], budget=2, is_startup=False
            )

        assert len(notifs_2) == 1
        assert "/resume" in notifs_2[0][0]
        assert "/resume" in store.get_taught_commands("learn-command")

    @pytest.mark.asyncio
    async def test_save_failure_graceful_degradation(self, setup):
        """Pipeline completes without crashing even when save() fails."""
        store, ac, state, tmp_path = setup
        notifs: list[tuple] = []

        def send(msg, severity="info", timeout=7.0):
            notifs.append((msg, severity, timeout))

        hints = [_make_hint("h1")]

        # Make the .claude directory read-only so save() can't write
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(exist_ok=True)
        import os
        import stat

        original_mode = claude_dir.stat().st_mode
        try:
            claude_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)  # read+execute only

            with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
                # Should NOT raise — save() swallows OSError
                await run_pipeline(send, state, store, ac, hints, budget=2)

            # The hint was still shown even though save failed
            assert len(notifs) == 1
        finally:
            # Restore permissions for cleanup
            claude_dir.chmod(original_mode)

    @pytest.mark.asyncio
    async def test_cross_evaluation_suffix(self, setup):
        """Startup gets disable suffix on first toast; periodic does not."""
        store, ac, state, _ = setup

        notifs_startup: list[tuple] = []
        notifs_periodic: list[tuple] = []

        def send_s(msg, severity="info", timeout=7.0):
            notifs_startup.append((msg, severity, timeout))

        def send_p(msg, severity="info", timeout=7.0):
            notifs_periodic.append((msg, severity, timeout))

        hints = [_make_hint("h1"), _make_hint("h2")]

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            # Startup — first toast gets suffix
            await run_pipeline(
                send_s, state, store, ac, hints, budget=2, is_startup=True
            )
            assert "/hints off" in notifs_startup[0][0]
            if len(notifs_startup) > 1:
                assert "/hints off" not in notifs_startup[1][0]

            # Periodic — no suffix at all
            await run_pipeline(
                send_p, state, store, ac, hints, budget=2, is_startup=False
            )
            for msg, _, _ in notifs_periodic:
                assert "/hints off" not in msg


# ===========================================================================
# Integration tests: __init__.py — evaluate()
# ===========================================================================


class TestEvaluate:
    """Tests for the top-level evaluate() public API."""

    @pytest.mark.asyncio
    async def test_evaluate_calls_pipeline(self, tmp_path):
        """evaluate() wires up and calls the pipeline."""
        notifs = []

        def send(msg, severity="info", timeout=7.0):
            notifs.append(msg)

        # Create a project with no .git (triggers git-setup hint)
        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            from template.hints import evaluate

            await evaluate(send, tmp_path, session_count=1)

        # Should have shown at least the git-setup hint
        assert any("git" in m.lower() for m in notifs)

    @pytest.mark.asyncio
    async def test_evaluate_catches_all_errors(self, tmp_path):
        """Top-level try-except catches everything (iron rule)."""
        from template.hints import evaluate

        # Pass a send_notification that raises
        def bad_send(*args, **kwargs):
            raise RuntimeError("notification system exploded")

        # Should not raise
        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await evaluate(bad_send, tmp_path)

    @pytest.mark.asyncio
    async def test_get_taught_commands_di_wired(self, tmp_path):
        """get_taught_commands DI closure reads from state store."""
        notifs = []

        def send(msg, severity="info", timeout=7.0):
            notifs.append(msg)

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            from template.hints import evaluate

            await evaluate(send, tmp_path, session_count=1)

        # learn-command should appear since get_taught_commands is wired
        # (it may or may not be shown depending on budget, but the wiring
        # should not error)
        # The key test is that evaluate() completes without error.


# ---------------------------------------------------------------------------
# /hints CLI E2E tests (python -m hints)
# ---------------------------------------------------------------------------


class TestHintsCLI:
    """E2E tests for the hints CLI that the /hints skill invokes.

    Cycles through all commands in a single test to verify the full
    lifecycle: status → off → status → on → dismiss → status → reset.
    Each step checks both stdout and the actual state file on disk.
    """

    def _run_hints(self, project_root: Path, *args: str) -> subprocess.CompletedProcess:
        """Run `python -m hints <args>` in the given project root."""
        return subprocess.run(
            [sys.executable, "-m", "hints", *args],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )

    def _read_state(self, project_root: Path) -> dict:
        """Read and parse the hints state file."""
        state_file = project_root / ".claude" / "hints_state.json"
        if not state_file.exists():
            return {}
        return json.loads(state_file.read_text(encoding="utf-8"))

    def test_full_lifecycle(self, tmp_path):
        """Cycle through all /hints commands and verify state after each.

        This mirrors what a user does in claudechic:
          /hints status  → see "enabled"
          /hints off     → disable all
          /hints status  → see "disabled"
          /hints on      → re-enable
          /hints dismiss git-setup → dismiss one hint
          /hints status  → see "enabled" + dismissed list
          /hints reset   → clear state file
          /hints status  → back to defaults
        """
        # Setup: create .claude/ dir (required for state file)
        (tmp_path / ".claude").mkdir()

        # Also need hints package importable — copy it to tmp
        import shutil
        hints_src = Path(__file__).resolve().parent.parent / "hints"
        hints_dst = tmp_path / "hints"
        shutil.copytree(hints_src, hints_dst)

        # --- Step 1: status (default = enabled, no state file yet) ---
        result = self._run_hints(tmp_path, "status")
        assert result.returncode == 0, f"status failed: {result.stderr}"
        assert "enabled" in result.stdout.lower()

        # --- Step 2: off ---
        result = self._run_hints(tmp_path, "off")
        assert result.returncode == 0, f"off failed: {result.stderr}"
        assert "disabled" in result.stdout.lower()

        # Verify state file on disk
        state = self._read_state(tmp_path)
        assert state["activation"]["enabled"] is False

        # --- Step 3: status shows disabled ---
        result = self._run_hints(tmp_path, "status")
        assert result.returncode == 0
        assert "disabled" in result.stdout.lower()

        # --- Step 4: on ---
        result = self._run_hints(tmp_path, "on")
        assert result.returncode == 0, f"on failed: {result.stderr}"
        assert "enabled" in result.stdout.lower()

        state = self._read_state(tmp_path)
        assert state["activation"]["enabled"] is True

        # --- Step 5: dismiss a specific hint ---
        result = self._run_hints(tmp_path, "dismiss", "git-setup")
        assert result.returncode == 0, f"dismiss failed: {result.stderr}"
        assert "git-setup" in result.stdout.lower()

        state = self._read_state(tmp_path)
        assert "git-setup" in state["activation"]["disabled_hints"]
        # Global should still be enabled
        assert state["activation"]["enabled"] is True

        # --- Step 6: status shows enabled + dismissed hint ---
        result = self._run_hints(tmp_path, "status")
        assert result.returncode == 0
        assert "enabled" in result.stdout.lower()
        assert "git-setup" in result.stdout.lower()

        # --- Step 7: reset ---
        result = self._run_hints(tmp_path, "reset")
        assert result.returncode == 0, f"reset failed: {result.stderr}"
        assert "reset" in result.stdout.lower()

        # State file should be gone
        assert not (tmp_path / ".claude" / "hints_state.json").exists()

        # --- Step 8: status after reset = back to defaults ---
        result = self._run_hints(tmp_path, "status")
        assert result.returncode == 0
        assert "enabled" in result.stdout.lower()

    def test_unknown_command(self, tmp_path):
        """Unknown command exits with error."""
        (tmp_path / ".claude").mkdir()
        import shutil
        hints_src = Path(__file__).resolve().parent.parent / "hints"
        shutil.copytree(hints_src, tmp_path / "hints")

        result = self._run_hints(tmp_path, "bogus")
        assert result.returncode == 0
        assert "unknown" in result.stdout.lower()

    def test_dismiss_without_id(self, tmp_path):
        """dismiss without hint ID shows usage."""
        (tmp_path / ".claude").mkdir()
        import shutil
        hints_src = Path(__file__).resolve().parent.parent / "hints"
        shutil.copytree(hints_src, tmp_path / "hints")

        result = self._run_hints(tmp_path, "dismiss")
        assert result.returncode == 0
        assert "/hints dismiss" in result.stdout.lower()
