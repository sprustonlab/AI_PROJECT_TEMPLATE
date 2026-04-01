"""Intent-based tests: settings.json wiring for guardrail hooks.

Red-phase TDD — these tests prove that generate_hooks.py fails to
create/populate .claude/settings.json with hook entries.

Each test targets a specific broken chain:
  1. settings.json not created when absent
  2. hardcoded triggers (Bash, Read, Glob, Write, Edit) excluded from registration
  3. merge with pre-existing settings.json content
  4. idempotency of repeated generate_hooks.py runs
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest


class TestSettingsJsonWiring:
    """Verify generate_hooks.py creates and populates .claude/settings.json."""

    def test_generate_hooks_creates_settings_json_when_absent(self, copier_output):
        """generate_hooks.py must CREATE settings.json if it does not exist.

        Without settings.json, Claude Code has no hook registrations and the
        entire guardrail system is silently non-operational.

        Expected to FAIL because update_settings_json() returns early when
        the file is absent instead of creating it.
        """
        dest = copier_output({
            "project_name": "wiring_absent",
            "claudechic_mode": "standard",
            "use_guardrails": True,
            "use_cluster": False,
        })

        settings_path = dest / ".claude" / "settings.json"
        # Ensure settings.json does not exist before running
        if settings_path.exists():
            settings_path.unlink()

        # Run generate_hooks.py
        result = subprocess.run(
            [sys.executable, str(dest / ".claude" / "guardrails" / "generate_hooks.py")],
            cwd=dest,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"generate_hooks.py failed:\nSTDOUT: {result.stdout[:500]}\n"
            f"STDERR: {result.stderr[:500]}"
        )

        # settings.json MUST exist after generation
        assert settings_path.exists(), (
            ".claude/settings.json was not created by generate_hooks.py — "
            "update_settings_json() returns early when the file is absent, "
            "leaving all hook scripts unregistered"
        )

        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        pre_tool_use = settings.get("hooks", {}).get("PreToolUse", [])
        assert len(pre_tool_use) > 0, (
            "settings.json exists but has no PreToolUse entries — "
            "guardrails will never fire"
        )

    def test_all_generated_hooks_have_settings_entries(self, copier_output):
        """Every generated hook script must have a matching settings.json entry.

        This includes BOTH MCP-trigger hook scripts AND hardcoded-trigger hook scripts
        (bash_guard, read_guard, glob_guard, write_guard, edit_guard).

        Expected to FAIL because hardcoded triggers (Bash, Read, Glob, Write,
        Edit) are explicitly excluded from settings.json registration.
        """
        dest = copier_output({
            "project_name": "wiring_all_hooks",
            "claudechic_mode": "standard",
            "use_guardrails": True,
            "use_cluster": False,
        })

        # Run generate_hooks.py
        result = subprocess.run(
            [sys.executable, str(dest / ".claude" / "guardrails" / "generate_hooks.py")],
            cwd=dest,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"generate_hooks.py failed:\nSTDOUT: {result.stdout[:500]}\n"
            f"STDERR: {result.stderr[:500]}"
        )

        settings_path = dest / ".claude" / "settings.json"
        assert settings_path.exists(), (
            "settings.json must exist for this test — "
            "if this fails, test_generate_hooks_creates_settings_json_when_absent "
            "must be fixed first"
        )

        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        pre_tool_use = settings.get("hooks", {}).get("PreToolUse", [])

        # Collect all generated hook scripts
        hooks_dir = dest / ".claude" / "guardrails" / "hooks"
        hook_scripts = [
            h for h in hooks_dir.glob("*.py")
            if h.name != ".gitkeep" and h.name != "__pycache__"
        ]
        assert len(hook_scripts) > 0, (
            "No hook scripts found in .claude/guardrails/hooks/ — "
            "generate_hooks.py did not produce any hooks"
        )

        # Every hook script must have at least one matching PreToolUse entry
        missing = []
        for hook in hook_scripts:
            matched = any(
                hook.name in (entry.get("hooks", [{}])[0].get("command", ""))
                for entry in pre_tool_use
            )
            if not matched:
                missing.append(hook.name)

        assert not missing, (
            f"Hook scripts without settings.json entries: {missing} — "
            f"these hook scripts exist on disk but will NEVER be invoked by Claude Code "
            f"because hardcoded triggers (Bash, Read, Glob, Write, Edit) are "
            f"excluded from registration in update_settings_json()"
        )

    def test_settings_merge_preserves_existing_content(self, copier_output):
        """Running generate_hooks.py must merge INTO existing settings.json.

        Pre-existing keys (permissions, mcpServers, etc.) must survive.
        Only hooks.PreToolUse should be added/updated.

        Expected to FAIL because update_settings_json() returns early if
        the file is absent, and even if the file exists, hardcoded triggers
        are excluded from registration.
        """
        dest = copier_output({
            "project_name": "wiring_merge",
            "claudechic_mode": "standard",
            "use_guardrails": True,
            "use_cluster": False,
        })

        settings_path = dest / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)

        # Pre-populate with existing user content (including a custom hook)
        custom_hook_entry = {
            "matcher": "custom_tool",
            "hooks": [{"type": "command", "command": "echo custom"}],
        }
        existing_content = {
            "permissions": {
                "allow": ["Read"],
            },
            "mcpServers": {
                "my_server": {
                    "command": "node",
                },
            },
            "hooks": {
                "PreToolUse": [custom_hook_entry],
            },
        }
        settings_path.write_text(
            json.dumps(existing_content, indent=2), encoding="utf-8"
        )

        # Run generate_hooks.py
        result = subprocess.run(
            [sys.executable, str(dest / ".claude" / "guardrails" / "generate_hooks.py")],
            cwd=dest,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"generate_hooks.py failed:\nSTDOUT: {result.stdout[:500]}\n"
            f"STDERR: {result.stderr[:500]}"
        )

        settings = json.loads(settings_path.read_text(encoding="utf-8"))

        # Pre-existing keys must survive
        assert settings.get("permissions") == existing_content["permissions"], (
            "generate_hooks.py destroyed pre-existing 'permissions' key — "
            "settings merge is not preserving existing content"
        )
        assert settings.get("mcpServers") == existing_content["mcpServers"], (
            "generate_hooks.py destroyed pre-existing 'mcpServers' key — "
            "settings merge is not preserving existing content"
        )

        # hooks.PreToolUse must contain BOTH the pre-existing custom entry
        # AND the newly generated guardrail entries
        pre_tool_use = settings.get("hooks", {}).get("PreToolUse", [])
        assert len(pre_tool_use) > 1, (
            "settings.json should have both custom and generated PreToolUse entries — "
            f"found {len(pre_tool_use)} entries"
        )

        # The original custom hook entry must still be present
        custom_matchers = [
            e for e in pre_tool_use
            if e.get("matcher") == "custom_tool"
        ]
        assert len(custom_matchers) == 1, (
            "Pre-existing custom PreToolUse entry was lost during merge — "
            "generate_hooks.py must append to, not replace, existing hook entries"
        )

    def test_settings_merge_is_idempotent(self, copier_output):
        """Running generate_hooks.py twice must produce identical settings.json.

        No duplicate entries, no lost entries, no changed ordering.

        Expected to FAIL because the first run won't create settings.json
        (update_settings_json returns early if absent), so the second run
        also fails, and comparison is impossible.
        """
        dest = copier_output({
            "project_name": "wiring_idempotent",
            "claudechic_mode": "standard",
            "use_guardrails": True,
            "use_cluster": False,
        })

        settings_path = dest / ".claude" / "settings.json"
        # Ensure settings.json does not exist
        if settings_path.exists():
            settings_path.unlink()

        gen_script = str(dest / ".claude" / "guardrails" / "generate_hooks.py")

        # First run
        result1 = subprocess.run(
            [sys.executable, gen_script],
            cwd=dest,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result1.returncode == 0, (
            f"generate_hooks.py first run failed:\n"
            f"STDOUT: {result1.stdout[:500]}\nSTDERR: {result1.stderr[:500]}"
        )

        assert settings_path.exists(), (
            "settings.json not created after first run — "
            "cannot test idempotency if the file is never created"
        )
        content_after_first = settings_path.read_text(encoding="utf-8")

        # Second run
        result2 = subprocess.run(
            [sys.executable, gen_script],
            cwd=dest,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result2.returncode == 0, (
            f"generate_hooks.py second run failed:\n"
            f"STDOUT: {result2.stdout[:500]}\nSTDERR: {result2.stderr[:500]}"
        )

        content_after_second = settings_path.read_text(encoding="utf-8")

        # Parse both to compare structurally (order-independent)
        settings_first = json.loads(content_after_first)
        settings_second = json.loads(content_after_second)

        assert settings_first == settings_second, (
            "settings.json differs after second run of generate_hooks.py — "
            "hooks registration is not idempotent.\n"
            f"After first run: {json.dumps(settings_first, indent=2)[:500]}\n"
            f"After second run: {json.dumps(settings_second, indent=2)[:500]}"
        )
