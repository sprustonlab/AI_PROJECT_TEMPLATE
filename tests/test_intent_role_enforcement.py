"""Intent-based tests for role-based enforcement in real rules.yaml.

Red-phase TDD: these tests MUST FAIL on the current codebase because:
  - rules.yaml contains only universal rules R01-R03 (no role gates)
  - No role-gated rules exist to block subagents from dangerous operations
  - The full copier-to-enforcement chain has multiple broken links
  - The TUI wiring from spawn_agent(type=X) to CLAUDE_AGENT_ROLE is untested
    against real role-gated rules

These tests prove that real project role names (Coordinator, Implementer,
Skeptic, TestEngineer) are NOT enforced by the current rule catalog.
Once role-gated exemplar rules are added to rules.yaml (Phase B),
these tests will pass.

Three test classes:
  1. TestRealRoleRuleBlocksSubagent — subprocess + env var (hook-level)
  2. TestFullChainCopierToEnforcement — copier → hooks → settings.json → enforcement
  3. TestTUIRoleWiringToEnforcement — TUI Pilot API → spawn_agent → CLAUDE_AGENT_ROLE
     → session marker → hook enforcement (true E2E through the TUI)
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

TEMPLATE_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helper: run a hook as subprocess (same pattern as test_framework.py)
# ---------------------------------------------------------------------------

def run_hook(
    hook_script: Path,
    hook_input: dict,
    *,
    guardrails_dir: str | None = None,
    agent_name: str | None = None,
    agent_role: str | None = None,
    app_pid: str | None = None,
    timeout: int = 15,
) -> subprocess.CompletedProcess:
    """Pipe hook_input JSON to a hook script and return the result."""
    env = os.environ.copy()
    # Clear agent-related env vars for isolation
    for var in (
        "CLAUDE_AGENT_NAME", "CLAUDE_AGENT_ROLE",
        "AGENT_SESSION_PID", "CLAUDECHIC_APP_PID", "GUARDRAILS_DIR",
    ):
        env.pop(var, None)

    if agent_name is not None:
        env["CLAUDE_AGENT_NAME"] = agent_name
    if agent_role is not None:
        env["CLAUDE_AGENT_ROLE"] = agent_role
    if app_pid is not None:
        env["AGENT_SESSION_PID"] = app_pid
    if guardrails_dir is not None:
        env["GUARDRAILS_DIR"] = guardrails_dir

    return subprocess.run(
        [sys.executable, str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True, text=True, env=env, timeout=timeout,
    )


def create_session_marker(
    guardrails_dir: Path,
    coordinator_name: str,
    app_pid: str = "99999",
) -> Path:
    """Create a session marker file (team mode activation).

    Mirrors the fw_env.create_session_marker pattern from test_framework.py.
    """
    sessions_dir = guardrails_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    marker = sessions_dir / f"ao_{app_pid}"
    marker.write_text(
        json.dumps({"coordinator": coordinator_name}),
        encoding="utf-8",
    )
    return marker


# ===========================================================================
# Test 8: Real role-gated rule blocks subagent
# ===========================================================================

class TestRealRoleRuleBlocksSubagent:
    """Test that real rules.yaml has role-gated rules blocking subagents.

    WHY THIS FAILS (Red phase):
        rules.yaml contains only R01-R03, all universal (no block:/allow: fields).
        There is NO rule that blocks subagents from running 'git push origin main'.
        A role-gated rule like:
            block: [Subagent]
            pattern: 'git\\s+push'
        does not exist in the real rules.yaml.

    When fixed (Green phase):
        A new rule (e.g. R04) will be added to rules.yaml with block: [Subagent]
        that denies 'git push' for non-Coordinator agents in team mode.
    """

    def test_real_role_rule_blocks_subagent(self, copier_output, tmp_path):
        """Subagent (Skeptic) should be blocked from 'git push'; Coordinator allowed.

        Full chain:
        1. copier copy with use_guardrails=True
        2. run generate_hooks.py to generate hook scripts
        3. create session marker (team mode active)
        4. set CLAUDE_AGENT_ROLE=Skeptic, pipe 'git push origin main' through bash_guard
        5. assert exit code 2 (blocked) — FAILS because no role-gated rule exists
        6. repeat with Coordinator (no role) — assert exit code 0 (allowed)
        """
        # Step 1: copier copy
        dest = copier_output({
            "project_name": "role_test",
            "quick_start": "everything",
            "use_cluster": False,
        })
        guardrails_dir = dest / ".claude" / "guardrails"
        assert guardrails_dir.exists(), (
            "Guardrails dir should exist after copier copy with use_guardrails=True"
        )

        # Step 2: run generate_hooks.py
        gen_result = subprocess.run(
            [sys.executable, str(guardrails_dir / "generate_hooks.py")],
            capture_output=True, text=True, timeout=30,
            cwd=str(guardrails_dir),
        )
        assert gen_result.returncode == 0, (
            f"generate_hooks.py should succeed, got:\n{gen_result.stderr}"
        )

        hooks_dir = guardrails_dir / "hooks"
        bash_guard = hooks_dir / "bash_guard.py"
        assert bash_guard.exists(), (
            "bash_guard.py should exist after running generate_hooks.py"
        )

        # Step 3: create session marker (team mode active)
        app_pid = "88888"
        create_session_marker(guardrails_dir, "CoordAgent", app_pid)

        # Step 4: Skeptic agent tries 'git push origin main' — should be BLOCKED
        result_skeptic = run_hook(
            bash_guard,
            {"tool_input": {"command": "git push origin main"}},
            guardrails_dir=str(guardrails_dir),
            agent_name="SkepticAgent",
            agent_role="Skeptic",
            app_pid=app_pid,
        )
        assert result_skeptic.returncode == 2, (
            "Subagent (Skeptic) should be BLOCKED from 'git push origin main' "
            "by a role-gated rule in rules.yaml, but no such rule exists. "
            f"Got exit code {result_skeptic.returncode}. "
            "rules.yaml has only universal rules R01-R03 with no block:/allow: fields. "
            "Add a role-gated rule like: block: [Subagent], pattern: 'git\\s+push'"
        )

        # Step 5: Coordinator tries same command — should be ALLOWED
        result_coordinator = run_hook(
            bash_guard,
            {"tool_input": {"command": "git push origin main"}},
            guardrails_dir=str(guardrails_dir),
            agent_name="CoordAgent",
            app_pid=app_pid,
        )
        assert result_coordinator.returncode == 0, (
            "Coordinator should be ALLOWED to 'git push origin main' "
            "(not blocked by a Subagent-only rule). "
            f"Got exit code {result_coordinator.returncode}: {result_coordinator.stderr}"
        )


# ===========================================================================
# Test 9: Full chain — copier to enforcement
# ===========================================================================

class TestFullChainCopierToEnforcement:
    """End-to-end test: copier copy -> generate hooks -> settings.json -> team mode -> enforcement.

    WHY THIS FAILS (Red phase):
        Multiple chain links are broken simultaneously:
        a) settings.json may not be created (update_settings_json returns early if absent)
        b) No role-gated rules exist in rules.yaml (only universal R01-R03)
        c) setup_ao_mode.sh does not exist (session markers must be created manually)

    When fixed (Green phase):
        - generate_hooks.py creates settings.json if absent and registers ALL triggers
        - rules.yaml includes role-gated exemplar rules (e.g., R04 block:[Subagent])
        - setup_ao_mode.sh creates session markers
    """

    def test_full_chain_copier_to_enforcement(self, copier_output, tmp_path):
        """Full end-to-end chain from copier to role enforcement.

        Steps:
        1. copier copy into temp dir with use_guardrails=True
        2. run generate_hooks.py
        3. assert settings.json exists with hook entries
        4. create session marker (team mode)
        5. set CLAUDE_AGENT_ROLE=Implementer
        6. pipe a role-restricted action through the generated bash_guard hook
        7. assert correct enforcement (blocked for Implementer, allowed for Coordinator)
        """
        # Step 1: copier copy
        dest = copier_output({
            "project_name": "e2e_chain_test",
            "quick_start": "everything",
            "use_cluster": False,
        })
        guardrails_dir = dest / ".claude" / "guardrails"

        # Step 2: run generate_hooks.py (cwd must be project root for settings.json path)
        gen_result = subprocess.run(
            [sys.executable, str(guardrails_dir / "generate_hooks.py")],
            capture_output=True, text=True, timeout=30,
            cwd=str(dest),
        )
        assert gen_result.returncode == 0, (
            f"generate_hooks.py should succeed:\n{gen_result.stderr}"
        )

        # Step 3: assert settings.json exists with hook entries
        settings_path = dest / ".claude" / "settings.json"
        assert settings_path.exists(), (
            "settings.json should be created by generate_hooks.py, but "
            "update_settings_json() returns early when the file is absent "
            "(line ~1885: 'if not settings_path.exists(): return'). "
            "Fix: create the file if absent instead of returning."
        )

        # If settings.json exists, verify it has PreToolUse hook entries
        if settings_path.exists():
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            pre_tool_use = settings.get("hooks", {}).get("PreToolUse", [])
            assert len(pre_tool_use) > 0, (
                "settings.json should contain PreToolUse hook entries for "
                "Bash, Read, Write, Edit, Glob triggers. "
                "Currently update_settings_json() only registers MCP triggers, "
                "excluding hardcoded ones (line ~2034: "
                "'mcp_triggers = sorted(t for t in groups if t not in _hardcoded)')."
            )

            # Verify that Bash trigger is registered (hardcoded trigger)
            bash_entries = [
                e for e in pre_tool_use
                if e.get("matcher") == "Bash"
            ]
            assert len(bash_entries) > 0, (
                "settings.json should have a PreToolUse entry for 'Bash' trigger, "
                "but hardcoded triggers are explicitly excluded from registration. "
                "All generated hooks need matching settings.json entries."
            )

        # Step 4: create session marker (team mode active)
        app_pid = "77777"
        create_session_marker(guardrails_dir, "CoordAgent", app_pid)

        # Step 5 + 6: Implementer tries a role-restricted action
        hooks_dir = guardrails_dir / "hooks"
        bash_guard = hooks_dir / "bash_guard.py"
        assert bash_guard.exists(), "bash_guard.py should exist after generation"

        result_impl = run_hook(
            bash_guard,
            {"tool_input": {"command": "git push origin main"}},
            guardrails_dir=str(guardrails_dir),
            agent_name="ImplAgent",
            agent_role="Implementer",
            app_pid=app_pid,
        )

        # Step 7: assert enforcement
        assert result_impl.returncode == 2, (
            "Implementer should be BLOCKED from 'git push origin main' by a "
            "role-gated rule in rules.yaml (e.g., R04 with block: [Subagent]). "
            f"Got exit code {result_impl.returncode}. "
            "The full chain is broken: rules.yaml has no role-gated rules, "
            "settings.json may not have been created, and the enforcement "
            "never fires because there is nothing to enforce for roles. "
            "This test validates the ENTIRE chain: "
            "copier -> generate_hooks -> settings.json -> team mode -> role enforcement."
        )

        # Coordinator should be allowed for the same action
        result_coord = run_hook(
            bash_guard,
            {"tool_input": {"command": "git push origin main"}},
            guardrails_dir=str(guardrails_dir),
            agent_name="CoordAgent",
            app_pid=app_pid,
        )
        assert result_coord.returncode == 0, (
            "Coordinator should be ALLOWED to 'git push origin main'. "
            f"Got exit code {result_coord.returncode}: {result_coord.stderr}"
        )


# ===========================================================================
# TUI mock fixtures (mirrors tests/test_tui_chatapp.py)
# ===========================================================================

async def _empty_async_gen():
    """Empty async generator for mocking receive_response."""
    return
    yield  # noqa: unreachable


async def _wait_for_workers(app):
    """Wait for all background workers to complete."""
    await app.workers.wait_for_complete()


@pytest.fixture
def mock_sdk():
    """Patch SDK to not actually connect (mirrors test_tui_chatapp.py)."""
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


# ===========================================================================
# Test 10: TUI Role Wiring to Enforcement (true E2E through the TUI)
# ===========================================================================

class TestTUIRoleWiringToEnforcement:
    """TUI E2E: spawn_agent(type=X) → CLAUDE_AGENT_ROLE → session marker → enforcement.

    Tests the entry point that subprocess tests skip: the TUI's _make_options()
    method, which is the ONLY place CLAUDE_AGENT_ROLE gets injected into the
    agent's environment. If this wiring is broken, no role-gated rule can ever
    fire, regardless of what rules.yaml contains.

    WHY THIS FAILS (Red phase):
        1. _make_options() correctly sets CLAUDE_AGENT_ROLE in the env dict
           when agent_type is provided (line 650-651 of app.py) — this part WORKS.
        2. BUT rules.yaml has NO role-gated rules (only universal R01-R03).
        3. So even though the TUI correctly wires CLAUDE_AGENT_ROLE=Implementer,
           the generated bash_guard.py has no role-gated code path to enforce.
        4. The test proves: TUI wiring is necessary but NOT SUFFICIENT —
           real role-gated rules must also exist in rules.yaml.

    When fixed (Green phase):
        - Add role-gated exemplar rules to rules.yaml (e.g., R04 block:[Subagent])
        - The TUI wiring (already working) + real rules = enforcement fires
    """

    @pytest.mark.asyncio
    @pytest.mark.tui
    @pytest.mark.timeout(60)
    async def test_tui_spawn_agent_wires_role_to_enforcement(
        self, mock_sdk, copier_output, tmp_path,
    ):
        """Full TUI E2E: ChatApp._make_options(agent_type=X) → env → hook enforcement.

        Chain tested:
        1. ChatApp._make_options(agent_type="Implementer") produces env with
           CLAUDE_AGENT_ROLE=Implementer
        2. copier copy + generate_hooks.py produces bash_guard.py from real rules.yaml
        3. Session marker created (team mode active)
        4. bash_guard.py invoked with the TUI-produced env vars
        5. Assert: role-gated enforcement fires (exit 2 for subagent)

        This test bridges the gap between:
        - test_tui_chatapp.py (tests TUI mechanics but not guardrail enforcement)
        - test_real_role_rule_blocks_subagent (tests hooks but skips TUI entry point)
        """
        from claudechic.app import ChatApp

        # --- Step 1: Verify TUI wires CLAUDE_AGENT_ROLE via _make_options ---
        app = ChatApp()
        async with app.run_test() as pilot:
            # Verify the initial agent exists
            assert len(app.agents) == 1
            assert app._agent is not None

            # Call _make_options with agent_type="Implementer" — the same path
            # that spawn_agent → AgentManager.create → _options_factory follows
            options_impl = app._make_options(
                cwd=tmp_path,
                agent_name="ImplAgent",
                agent_type="Implementer",
            )

            # Verify CLAUDE_AGENT_ROLE is in the env dict
            assert options_impl.env.get("CLAUDE_AGENT_ROLE") == "Implementer", (
                "ChatApp._make_options(agent_type='Implementer') must set "
                "CLAUDE_AGENT_ROLE='Implementer' in the env dict. "
                "This is the ONLY place role wiring happens (app.py line 650-651)."
            )

            # Verify CLAUDECHIC_APP_PID is set (needed for session marker lookup)
            assert "CLAUDECHIC_APP_PID" in options_impl.env, (
                "CLAUDECHIC_APP_PID must be in env for session marker lookup."
            )
            app_pid = options_impl.env["CLAUDECHIC_APP_PID"]

            # Verify Coordinator (no agent_type) does NOT get CLAUDE_AGENT_ROLE
            options_coord = app._make_options(
                cwd=tmp_path,
                agent_name="CoordAgent",
                agent_type=None,
            )
            assert "CLAUDE_AGENT_ROLE" not in options_coord.env, (
                "Coordinator (agent_type=None) must NOT have CLAUDE_AGENT_ROLE set. "
                "Coordinator identity comes from the session marker, not env var."
            )

        # --- Step 2: copier copy + generate hooks from REAL rules.yaml ---
        dest = copier_output({
            "project_name": "tui_e2e_test",
            "quick_start": "everything",
            "use_cluster": False,
        })
        guardrails_dir = dest / ".claude" / "guardrails"

        gen_result = subprocess.run(
            [sys.executable, str(guardrails_dir / "generate_hooks.py")],
            capture_output=True, text=True, timeout=30,
            cwd=str(guardrails_dir),
        )
        assert gen_result.returncode == 0, (
            f"generate_hooks.py should succeed:\n{gen_result.stderr}"
        )

        hooks_dir = guardrails_dir / "hooks"
        bash_guard = hooks_dir / "bash_guard.py"
        assert bash_guard.exists(), "bash_guard.py should exist after generation"

        # --- Step 3: Create session marker (team mode) ---
        # Use the CLAUDECHIC_APP_PID from the TUI's env dict
        create_session_marker(guardrails_dir, "CoordAgent", app_pid)

        # --- Step 4: Pipe command through hook with TUI-produced env vars ---
        # Reconstruct the env exactly as the TUI would set it for a spawned agent
        tui_env = os.environ.copy()
        for var in (
            "CLAUDE_AGENT_NAME", "CLAUDE_AGENT_ROLE",
            "AGENT_SESSION_PID", "CLAUDECHIC_APP_PID", "GUARDRAILS_DIR",
        ):
            tui_env.pop(var, None)

        # Apply the env vars from _make_options (the TUI's wiring)
        tui_env["CLAUDE_AGENT_NAME"] = "ImplAgent"
        tui_env["CLAUDE_AGENT_ROLE"] = options_impl.env["CLAUDE_AGENT_ROLE"]
        tui_env["CLAUDECHIC_APP_PID"] = app_pid
        tui_env["GUARDRAILS_DIR"] = str(guardrails_dir)

        result_impl = subprocess.run(
            [sys.executable, str(bash_guard)],
            input=json.dumps({"tool_input": {"command": "git push origin main"}}),
            capture_output=True, text=True, env=tui_env, timeout=15,
        )

        # --- Step 5: Assert role-gated enforcement ---
        assert result_impl.returncode == 2, (
            "TUI E2E: Implementer agent (spawned via ChatApp with "
            "agent_type='Implementer') should be BLOCKED from 'git push origin main' "
            "by a role-gated rule in rules.yaml. "
            f"Got exit code {result_impl.returncode}. "
            "The TUI correctly wires CLAUDE_AGENT_ROLE='Implementer' via "
            "_make_options(), but rules.yaml has NO role-gated rules (only R01-R03). "
            "The generated bash_guard.py therefore has no role-gated code path. "
            "Fix: add role-gated exemplar rules to rules.yaml "
            "(e.g., R04 with block: [Subagent] for git push)."
        )

        # Coordinator should be allowed (same command, no CLAUDE_AGENT_ROLE)
        coord_env = tui_env.copy()
        coord_env["CLAUDE_AGENT_NAME"] = "CoordAgent"
        coord_env.pop("CLAUDE_AGENT_ROLE", None)

        result_coord = subprocess.run(
            [sys.executable, str(bash_guard)],
            input=json.dumps({"tool_input": {"command": "git push origin main"}}),
            capture_output=True, text=True, env=coord_env, timeout=15,
        )
        assert result_coord.returncode == 0, (
            "TUI E2E: Coordinator should be ALLOWED to 'git push origin main'. "
            f"Got exit code {result_coord.returncode}: {result_coord.stderr}"
        )
