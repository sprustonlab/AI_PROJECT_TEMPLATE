#!/usr/bin/env python3
"""Framework integration tests for the guardrail hook generator + runtime.

Tests the FRAMEWORK mechanisms (generate_hooks.py + role_guard.py) using
synthetic rules from rules.yaml.example. No project rules are tested here.

Test protocol (same as test_role_guard.py — Pattern #5):
    1. Session-scoped fixture generates hooks from rules.yaml.example
    2. Per-test fixture creates temp GUARDRAILS_DIR with sessions/, acks/
    3. Real hook scripts run as subprocesses with real env vars
    4. Check exit code (0 = allow, 2 = block) and stderr output

Run with:
    conda run -n decode_prism pytest .claude/guardrails/test_framework.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
GUARDRAILS_DIR = Path(__file__).resolve().parent
GENERATE_HOOKS = GUARDRAILS_DIR / "generate_hooks.py"
ROLE_GUARD_PY = GUARDRAILS_DIR / "role_guard.py"
RULES_EXAMPLE = GUARDRAILS_DIR / "rules.yaml.example"


# ---------------------------------------------------------------------------
# Session-scoped fixture: generate hooks from rules.yaml.example ONCE
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def generated_hooks(tmp_path_factory):
    """Generate hook scripts from rules.yaml.example into a session temp dir.

    Copies generate_hooks.py + rules.yaml.example (as rules.yaml) + role_guard.py
    into a temp directory, runs the generator, and returns the hooks dir.
    This is expensive so it runs once per session.
    """
    gen_dir = tmp_path_factory.mktemp("fw_gen")

    # Copy generator and role_guard
    shutil.copy2(str(GENERATE_HOOKS), str(gen_dir / "generate_hooks.py"))
    shutil.copy2(str(ROLE_GUARD_PY), str(gen_dir / "role_guard.py"))
    # Copy example as rules.yaml (generator reads SCRIPT_DIR / "rules.yaml")
    shutil.copy2(str(RULES_EXAMPLE), str(gen_dir / "rules.yaml"))

    # Run generator
    result = subprocess.run(
        [sys.executable, str(gen_dir / "generate_hooks.py")],
        capture_output=True, text=True, timeout=30,
        cwd=str(gen_dir),
    )
    assert result.returncode == 0, f"Hook generation failed:\n{result.stderr}"

    hooks_dir = gen_dir / "hooks"
    assert hooks_dir.exists(), "hooks/ directory not created by generator"
    return gen_dir


# ---------------------------------------------------------------------------
# Per-test fixture: temp GUARDRAILS_DIR with hooks, sessions/, acks/
# ---------------------------------------------------------------------------

@pytest.fixture
def fw_env(generated_hooks, tmp_path):
    """Create a per-test temp GUARDRAILS_DIR with generated hooks.

    Copies generated hooks + role_guard.py into tmp_path so each test gets
    an isolated sessions/ and acks/ directory.

    Structure:
        tmp_path/
            hooks/          ← generated hook scripts
            role_guard.py   ← runtime module
            sessions/       ← session markers
            acks/           ← ack tokens
    """
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    acks_dir = tmp_path / "acks"
    acks_dir.mkdir()
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()

    # Copy role_guard.py
    shutil.copy2(str(generated_hooks / "role_guard.py"), str(tmp_path / "role_guard.py"))

    # Copy all generated hooks
    src_hooks = generated_hooks / "hooks"
    for hook_file in src_hooks.iterdir():
        shutil.copy2(str(hook_file), str(hooks_dir / hook_file.name))

    class Env:
        dir = str(tmp_path)
        path = tmp_path
        bash_guard = hooks_dir / "bash_guard.sh"
        write_guard = hooks_dir / "write_guard.sh"
        read_guard = hooks_dir / "read_guard.sh"
        glob_guard = hooks_dir / "glob_guard.sh"
        mcp_guard = hooks_dir / "mcp__fw__test_tool_guard.sh"

        @staticmethod
        def create_session_marker(coordinator_name: str, app_pid: str = "99999"):
            marker = sessions_dir / f"ao_{app_pid}"
            marker.write_text(json.dumps({"coordinator": coordinator_name}))
            return marker

    return Env()


# ---------------------------------------------------------------------------
# Helper: run a hook as subprocess
# ---------------------------------------------------------------------------

def run_hook(
    hook_script: Path,
    hook_input: dict,
    *,
    agent_name: str | None = None,
    agent_role: str | None = None,
    app_pid: str | None = None,
    timeout: int = 15,
) -> subprocess.CompletedProcess:
    """Pipe hook_input JSON to a hook script and return the result."""
    env = os.environ.copy()
    env.pop("CLAUDE_AGENT_NAME", None)
    env.pop("CLAUDE_AGENT_ROLE", None)
    env.pop("CLAUDECHIC_APP_PID", None)
    env.pop("GUARDRAILS_DIR", None)

    if agent_name is not None:
        env["CLAUDE_AGENT_NAME"] = agent_name
    if agent_role is not None:
        env["CLAUDE_AGENT_ROLE"] = agent_role
    if app_pid is not None:
        env["CLAUDECHIC_APP_PID"] = app_pid

    return subprocess.run(
        ["bash", str(hook_script)],
        input=json.dumps(hook_input),
        capture_output=True, text=True, env=env, timeout=timeout,
    )


# ===========================================================================
# §1: FW01 — regex_match (Bash, deny, universal)
# ===========================================================================

class TestFW01RegexMatch:
    """FW01: Basic regex_match + deny on Bash command field."""

    def test_matching_command_denied(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token dangerous_cmd"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW01" in result.stderr

    def test_non_matching_command_allowed(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token safe_command"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 0


# ===========================================================================
# §2: FW02 — regex_miss (Bash, warn, universal)
# ===========================================================================

class TestFW02RegexMiss:
    """FW02: regex_miss — fires when pattern does NOT match."""

    def test_missing_safe_prefix_warned(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "required_token do something without prefix"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW02" in result.stderr

    def test_has_safe_prefix_allowed(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token do something"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 0


# ===========================================================================
# §3: FW03 — MCP field extraction (regex_match)
# ===========================================================================

class TestFW03MCPFieldMatch:
    """FW03: MCP trigger + field: color + regex_match."""

    def test_red_color_denied(self, fw_env):
        result = run_hook(
            fw_env.mcp_guard,
            {"tool_input": {"color": "bright red", "shape": "circle"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW03" in result.stderr

    def test_blue_color_allowed(self, fw_env):
        result = run_hook(
            fw_env.mcp_guard,
            {"tool_input": {"color": "blue", "shape": "circle"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 0


# ===========================================================================
# §4: FW04 — MCP field extraction (regex_miss)
# ===========================================================================

class TestFW04MCPFieldMiss:
    """FW04: MCP trigger + field: shape + regex_miss."""

    def test_invalid_shape_warned(self, fw_env):
        result = run_hook(
            fw_env.mcp_guard,
            {"tool_input": {"color": "blue", "shape": "triangle"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW04" in result.stderr

    def test_valid_shape_allowed(self, fw_env):
        result = run_hook(
            fw_env.mcp_guard,
            {"tool_input": {"color": "blue", "shape": "circle"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 0


# ===========================================================================
# §5: FW05 — regex flags (IGNORECASE)
# ===========================================================================

class TestFW05Flags:
    """FW05: IGNORECASE flag on regex_match."""

    def test_lowercase_matches(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token flagtest"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW05" in result.stderr

    def test_uppercase_matches(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token FLAGTEST"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW05" in result.stderr

    def test_mixed_case_matches(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token FlagTest"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW05" in result.stderr


# ===========================================================================
# §6: FW06 — multi-pattern OR list
# ===========================================================================

class TestFW06MultiPattern:
    """FW06: Pattern list — any match fires the rule."""

    def test_alpha_bad_denied(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token alpha_bad"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW06" in result.stderr

    def test_beta_bad_denied(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token beta_bad"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW06" in result.stderr

    def test_gamma_good_allowed(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token gamma_good"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 0


# ===========================================================================
# §7: FW07 — exclude_if_matches
# ===========================================================================

class TestFW07ExcludeIf:
    """FW07: exclude_if_matches suppresses match when exclusion regex hits."""

    def test_guarded_action_denied(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token guarded_action"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW07" in result.stderr

    def test_guarded_action_with_bypass_allowed(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token guarded_action bypass_ok"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 0


# ===========================================================================
# §8: FW08 — exclude_contexts (python_dash_c, python_heredoc)
# ===========================================================================

class TestFW08ExcludeContexts:
    """FW08: Context stripping — code inside python -c or heredocs excluded."""

    def test_bare_context_word_denied(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token context_word"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW08" in result.stderr

    def test_context_word_in_python_c_allowed(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token python3 -c \"print('context_word')\""}},
            agent_name="TestAgent",
        )
        assert result.returncode == 0


# ===========================================================================
# §9: FW09 — block:[Coordinator] role gate
# ===========================================================================

class TestFW09BlockCoordinator:
    """FW09: block:[Coordinator] — only Coordinator is blocked."""

    def test_coordinator_blocked(self, fw_env):
        fw_env.create_session_marker("CoordAgent")
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token coord_restricted"}},
            agent_name="CoordAgent",
            app_pid="99999",
        )
        assert result.returncode == 2
        assert "FW09" in result.stderr

    def test_implementer_allowed(self, fw_env):
        fw_env.create_session_marker("CoordAgent")
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token coord_restricted"}},
            agent_name="Worker1",
            agent_role="Implementer",
            app_pid="99999",
        )
        assert result.returncode == 0

    def test_solo_mode_allowed(self, fw_env):
        """Solo mode (no session marker) → block:[Coordinator] skipped."""
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token coord_restricted"}},
            agent_name="SomeAgent",
            app_pid="99999",
        )
        assert result.returncode == 0


# ===========================================================================
# §10: FW10 — block:[Subagent] role gate
# ===========================================================================

class TestFW10BlockSubagent:
    """FW10: block:[Subagent] — only sub-agents are blocked; Coordinator exempt."""

    def test_subagent_warned(self, fw_env):
        fw_env.create_session_marker("CoordAgent")
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token subagent_restricted"}},
            agent_name="Worker1",
            agent_role="Implementer",
            app_pid="99999",
        )
        assert result.returncode == 2
        assert "FW10" in result.stderr

    def test_coordinator_exempt(self, fw_env):
        fw_env.create_session_marker("CoordAgent")
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token subagent_restricted"}},
            agent_name="CoordAgent",
            app_pid="99999",
        )
        assert result.returncode == 0


# ===========================================================================
# §11: FW11 — allow:[SpecialRole] allowlist gate
# ===========================================================================

class TestFW11AllowSpecial:
    """FW11: allow:[SpecialRole] — only SpecialRole is exempt."""

    def test_special_role_allowed(self, fw_env):
        fw_env.create_session_marker("CoordAgent")
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token privileged_cmd"}},
            agent_name="Specialist1",
            agent_role="SpecialRole",
            app_pid="99999",
        )
        assert result.returncode == 0

    def test_other_role_warned(self, fw_env):
        fw_env.create_session_marker("CoordAgent")
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token privileged_cmd"}},
            agent_name="Worker1",
            agent_role="Implementer",
            app_pid="99999",
        )
        assert result.returncode == 2
        assert "FW11" in result.stderr

    def test_coordinator_warned(self, fw_env):
        fw_env.create_session_marker("CoordAgent")
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token privileged_cmd"}},
            agent_name="CoordAgent",
            app_pid="99999",
        )
        assert result.returncode == 2
        assert "FW11" in result.stderr


# ===========================================================================
# §12: FW12 — Write/Edit deny (universal)
# ===========================================================================

class TestFW12WriteDeny:
    """FW12: Write/Edit regex_match on file_path → deny."""

    def test_secret_file_denied(self, fw_env):
        result = run_hook(
            fw_env.write_guard,
            {"tool_input": {"file_path": "config/keys.secret"}, "cwd": "/project"},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW12" in result.stderr

    def test_normal_file_allowed(self, fw_env):
        result = run_hook(
            fw_env.write_guard,
            {"tool_input": {"file_path": "config/settings.yaml"}, "cwd": "/project"},
            agent_name="TestAgent",
        )
        assert result.returncode == 0


# ===========================================================================
# §13: FW13 — Write/Edit warn with ack token flow
# ===========================================================================

class TestFW13WriteAck:
    """FW13: Write/Edit warn → ack token suppresses on retry."""

    def test_draft_file_warned_initially(self, fw_env):
        result = run_hook(
            fw_env.write_guard,
            {"tool_input": {"file_path": "notes/plan.draft"}, "cwd": "/project"},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW13" in result.stderr

    def test_draft_file_allowed_after_ack(self, fw_env):
        """Full ack cycle: write token → retry write → accepted."""
        temp_rg = fw_env.path / "role_guard.py"
        env = os.environ.copy()
        env.pop("CLAUDE_AGENT_NAME", None)
        env.pop("CLAUDE_AGENT_ROLE", None)
        env.pop("CLAUDECHIC_APP_PID", None)
        env["CLAUDE_AGENT_NAME"] = "TestAgent"
        env["GUARDRAILS_DIR"] = fw_env.dir

        # Step 1: Write ack token
        ack_result = subprocess.run(
            [sys.executable, str(temp_rg), "ack", "FW13", "notes/plan.draft"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert ack_result.returncode == 0

        # Step 2: Retry write → should pass
        result = run_hook(
            fw_env.write_guard,
            {"tool_input": {"file_path": "notes/plan.draft"}, "cwd": "/project"},
            agent_name="TestAgent",
        )
        assert result.returncode == 0, f"Expected allow after ack, got: {result.stderr}"


# ===========================================================================
# §14: FW14 — Write/Edit exclude_if_matches
# ===========================================================================

class TestFW14WriteExclude:
    """FW14: Write exclude_if_matches on file_path."""

    def test_generated_outside_safe_dir_denied(self, fw_env):
        result = run_hook(
            fw_env.write_guard,
            {"tool_input": {"file_path": "output/report_generated.py"}, "cwd": "/project"},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW14" in result.stderr

    def test_generated_inside_safe_dir_allowed(self, fw_env):
        result = run_hook(
            fw_env.write_guard,
            {"tool_input": {"file_path": "safe_dir/report_generated.py"}, "cwd": "/project"},
            agent_name="TestAgent",
        )
        assert result.returncode == 0


# ===========================================================================
# §15: FW15 — Read trigger (deny)
# ===========================================================================

class TestFW15ReadDeny:
    """FW15: Read trigger with target: file_path."""

    def test_classified_file_denied(self, fw_env):
        result = run_hook(
            fw_env.read_guard,
            {"tool_input": {"file_path": "docs/secrets.classified"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW15" in result.stderr

    def test_classified_case_insensitive(self, fw_env):
        result = run_hook(
            fw_env.read_guard,
            {"tool_input": {"file_path": "docs/secrets.CLASSIFIED"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW15" in result.stderr

    def test_normal_file_allowed(self, fw_env):
        result = run_hook(
            fw_env.read_guard,
            {"tool_input": {"file_path": "docs/readme.md"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 0


# ===========================================================================
# §16: FW16 — Glob trigger with path_is_root condition
# ===========================================================================

class TestFW16GlobRoot:
    """FW16: Glob ** from root warned, from subdirectory allowed."""

    def test_glob_star_star_from_root_warned(self, fw_env):
        result = run_hook(
            fw_env.glob_guard,
            {"tool_input": {"pattern": "**/*.py", "path": ""}, "cwd": "/project"},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW16" in result.stderr

    def test_glob_star_star_from_subdir_allowed(self, fw_env):
        result = run_hook(
            fw_env.glob_guard,
            {"tool_input": {"pattern": "**/*.py", "path": "src/"}, "cwd": "/project"},
            agent_name="TestAgent",
        )
        assert result.returncode == 0

    def test_glob_no_star_star_from_root_allowed(self, fw_env):
        result = run_hook(
            fw_env.glob_guard,
            {"tool_input": {"pattern": "*.py", "path": ""}, "cwd": "/project"},
            agent_name="TestAgent",
        )
        assert result.returncode == 0


# ===========================================================================
# §17: FW17 — Bash ack prefix suppression
# ===========================================================================

class TestFW17AckPrefix:
    """FW17: # ack:FW17 prefix suppresses warn-level match."""

    def test_warn_action_warned(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token warn_action"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW17" in result.stderr

    def test_ack_prefix_suppresses(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "# ack:FW17 safe_prefix required_token warn_action"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 0


# ===========================================================================
# §18: FW18 — deny > warn priority
# ===========================================================================

class TestFW18DenyPriority:
    """FW18: deny takes precedence over warn when both match."""

    def test_deny_overrides_warn(self, fw_env):
        """Command matches both FW17 (warn) and FW18 (deny) → deny wins."""
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token warn_action deny_also"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW18" in result.stderr

    def test_ack_cannot_suppress_deny(self, fw_env):
        """# ack:FW17 suppresses warn but deny from FW18 still fires."""
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "# ack:FW17 safe_prefix required_token warn_action deny_also"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW18" in result.stderr


# ===========================================================================
# §19: hits.jsonl logging
# ===========================================================================

class TestFW19HitsLogging:
    """Matched rules are logged to hits.jsonl."""

    def test_deny_logged_to_hits(self, fw_env):
        run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token dangerous_cmd"}},
            agent_name="LogTestAgent",
        )
        hits_file = fw_env.path / "hits.jsonl"
        assert hits_file.exists(), "hits.jsonl should be created"
        lines = hits_file.read_text().strip().split("\n")
        hits = [json.loads(line) for line in lines if line.strip()]
        fw01_hits = [h for h in hits if h.get("rule_id") == "FW01"]
        assert len(fw01_hits) >= 1
        assert fw01_hits[0]["enforcement"] == "deny"
        assert fw01_hits[0]["agent"] == "LogTestAgent"

    def test_no_match_no_hits(self, fw_env):
        run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token harmless_cmd"}},
            agent_name="TestAgent",
        )
        hits_file = fw_env.path / "hits.jsonl"
        if hits_file.exists():
            content = hits_file.read_text().strip()
            assert content == "", "No rules should match for harmless_cmd"


# ===========================================================================
# §20: FW20 — log enforcement (exit 0, record only)
# ===========================================================================

class TestFW20LogOnly:
    """FW20: log enforcement — exits 0 but records to hits.jsonl."""

    def test_log_event_exits_zero(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token log_this_event"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 0, f"Log enforcement should exit 0, got: {result.stderr}"

    def test_log_event_recorded_in_hits(self, fw_env):
        run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token log_this_event"}},
            agent_name="TestAgent",
        )
        hits_file = fw_env.path / "hits.jsonl"
        assert hits_file.exists()
        lines = hits_file.read_text().strip().split("\n")
        hits = [json.loads(line) for line in lines if line.strip()]
        fw20_hits = [h for h in hits if h.get("rule_id") == "FW20"]
        assert len(fw20_hits) >= 1, "FW20 should be logged even though it exits 0"


# ===========================================================================
# §21: FW21 — disabled rule (enabled: false)
# ===========================================================================

class TestFW21Disabled:
    """FW21: Disabled rule should never fire."""

    def test_disabled_pattern_not_blocked(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token disabled_pattern"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 0, f"Disabled rule should not fire, got: {result.stderr}"
        assert "FW21" not in result.stderr


# ===========================================================================
# §22: FW22 — regex_miss with deny + exclude_if_matches
# ===========================================================================

class TestFW22RegexMissDeny:
    """FW22: regex_miss + deny — fires when required_token is absent."""

    def test_missing_required_token_denied(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix some_cmd"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 2
        assert "FW22" in result.stderr

    def test_has_required_token_allowed(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token some_cmd"}},
            agent_name="TestAgent",
        )
        assert result.returncode == 0

    def test_exempt_cmd_skips_rule(self, fw_env):
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix exempt_cmd"}},
            agent_name="TestAgent",
        )
        # exclude_if_matches: \bexempt_cmd\b → FW22 skipped
        # But other rules may still fire (FW02 for missing safe_prefix...
        # actually safe_prefix is present so FW02 passes)
        # FW22 itself should not appear in stderr
        assert "FW22" not in result.stderr


# ===========================================================================
# §23: FW23 — block:[TeamAgent] group
# ===========================================================================

class TestFW23BlockTeamAgent:
    """FW23: block:[TeamAgent] — warns all agents in team mode."""

    def test_coordinator_warned_in_team_mode(self, fw_env):
        fw_env.create_session_marker("CoordAgent")
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token team_restricted"}},
            agent_name="CoordAgent",
            app_pid="99999",
        )
        assert result.returncode == 2
        assert "FW23" in result.stderr

    def test_subagent_warned_in_team_mode(self, fw_env):
        fw_env.create_session_marker("CoordAgent")
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token team_restricted"}},
            agent_name="Worker1",
            agent_role="Implementer",
            app_pid="99999",
        )
        assert result.returncode == 2
        assert "FW23" in result.stderr

    def test_solo_mode_skipped(self, fw_env):
        """Solo mode → block:[TeamAgent] skipped."""
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token team_restricted"}},
            agent_name="SomeAgent",
            app_pid="99999",
        )
        assert result.returncode == 0


# ===========================================================================
# §24: Solo mode and no-claudechic fallback
# ===========================================================================

class TestSoloModeAndNoClaudechic:
    """Role-gated rules pass silently in solo mode and without CLAUDE_AGENT_NAME."""

    def test_no_agent_name_universal_still_fires(self, fw_env):
        """No CLAUDE_AGENT_NAME → universal rules still fire."""
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token dangerous_cmd"}},
        )
        assert result.returncode == 2
        assert "FW01" in result.stderr

    def test_no_agent_name_role_gated_skipped(self, fw_env):
        """No CLAUDE_AGENT_NAME → role-gated rules return 0."""
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token coord_restricted"}},
        )
        assert result.returncode == 0


# ===========================================================================
# §25: Subagent with no CLAUDE_AGENT_ROLE in team mode
# ===========================================================================

class TestSubagentNoRole:
    """Subagent in team mode without CLAUDE_AGENT_ROLE → role checks inactive."""

    def test_no_role_passes_gated_rules(self, fw_env):
        fw_env.create_session_marker("CoordAgent")
        result = run_hook(
            fw_env.bash_guard,
            {"tool_input": {"command": "safe_prefix required_token coord_restricted"}},
            agent_name="Worker1",
            # No agent_role — CLAUDE_AGENT_ROLE unset
            app_pid="99999",
        )
        assert result.returncode == 0
        assert "CLAUDE_AGENT_ROLE" in result.stderr or result.returncode == 0


# ===========================================================================
# §26: Hook generation produces expected files
# ===========================================================================

class TestHookGeneration:
    """Verify the generator produces all expected hook files."""

    def test_all_hooks_generated(self, generated_hooks):
        hooks_dir = generated_hooks / "hooks"
        expected = {
            "bash_guard.sh",
            "write_guard.sh",
            "read_guard.sh",
            "glob_guard.sh",
            "mcp__fw__test_tool_guard.sh",
        }
        actual = {f.name for f in hooks_dir.iterdir()}
        assert expected == actual, f"Expected {expected}, got {actual}"

    def test_hooks_are_executable(self, generated_hooks):
        hooks_dir = generated_hooks / "hooks"
        for hook in hooks_dir.iterdir():
            assert os.access(str(hook), os.X_OK), f"{hook.name} is not executable"


# ---------------------------------------------------------------------------
# Legacy test runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
