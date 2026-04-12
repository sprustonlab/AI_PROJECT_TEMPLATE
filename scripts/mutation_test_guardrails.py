#!/usr/bin/env python3
"""Manual mutation testing for the guardrails system.

Applies targeted mutations to guardrails source files, runs the test suite,
and checks if each mutation is caught (killed) or survives undetected.

Usage: pixi run python scripts/mutation_test_guardrails.py
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARDRAILS = ROOT / "submodules" / "claudechic" / "claudechic" / "guardrails"
TEST_CMD = [
    sys.executable,
    "-m",
    "pytest",
    "-x",
    "--no-header",
    "-q",
    "-p",
    "no:xdist",
    "--override-ini=addopts=",
    "--timeout=15",
    "submodules/claudechic/tests/test_workflow_guardrails.py",
    "submodules/claudechic/tests/test_workflow_hits_logging.py",
]


@dataclass
class Mutation:
    """A single mutation to apply and test."""

    id: str
    file: str  # relative to GUARDRAILS
    description: str
    old: str
    new: str
    severity: str = "high"  # high = security-critical, medium, low


# Define targeted mutations for the guardrails enforcement logic
MUTATIONS: list[Mutation] = [
    # === hooks.py mutations ===
    Mutation(
        id="hooks-01",
        file="hooks.py",
        description="Remove fail-closed check (fatal discovery error → allow all)",
        old="if result.errors and not result.rules:",
        new="if False:  # MUTANT: disable fail-closed",
        severity="high",
    ),
    Mutation(
        id="hooks-02",
        file="hooks.py",
        description="Change deny decision from 'block' to 'allow' (no blocking)",
        old="""            elif rule.enforcement == "deny":
                if consume_override and consume_override(rule.id, tool_name, tool_input, "deny"):
                    hit_logger.record(dataclasses.replace(hit, outcome="overridden"))
                    continue  # Token consumed — allow, check next rule
                else:
                    hit_logger.record(dataclasses.replace(hit, outcome="blocked"))
                    return {
                        "decision": "block",""",
        new="""            elif rule.enforcement == "deny":
                if consume_override and consume_override(rule.id, tool_name, tool_input, "deny"):
                    hit_logger.record(dataclasses.replace(hit, outcome="overridden"))
                    continue  # Token consumed — allow, check next rule
                else:
                    hit_logger.record(dataclasses.replace(hit, outcome="blocked"))
                    return {
                        "decision": "allow",""",
        severity="high",
    ),
    Mutation(
        id="hooks-03",
        file="hooks.py",
        description="Change warn decision from 'block' to 'allow'",
        old="""            elif rule.enforcement == "warn":
                if consume_override and consume_override(rule.id, tool_name, tool_input, "warn"):
                    hit_logger.record(dataclasses.replace(hit, outcome="ack"))
                    continue  # Token consumed — allow, check next rule
                else:
                    hit_logger.record(dataclasses.replace(hit, outcome="blocked"))
                    return {
                        "decision": "block",""",
        new="""            elif rule.enforcement == "warn":
                if consume_override and consume_override(rule.id, tool_name, tool_input, "warn"):
                    hit_logger.record(dataclasses.replace(hit, outcome="ack"))
                    continue  # Token consumed — allow, check next rule
                else:
                    hit_logger.record(dataclasses.replace(hit, outcome="blocked"))
                    return {
                        "decision": "allow",""",
        severity="high",
    ),
    Mutation(
        id="hooks-04",
        file="hooks.py",
        description="Skip all enforcement rules (empty for-loop body → continue)",
        old="            if not matches_trigger(rule, tool_name):\n                continue",
        new="            if True:  # MUTANT: skip all rules\n                continue",
        severity="high",
    ),
    Mutation(
        id="hooks-05",
        file="hooks.py",
        description="Skip namespace filtering (active workflow check disabled)",
        old='            if rule.namespace != "global" and rule.namespace != active_wf:\n                continue',
        new="            if False:  # MUTANT: skip namespace check\n                continue",
        severity="medium",
    ),
    Mutation(
        id="hooks-06",
        file="hooks.py",
        description="Invert detect pattern match (match → skip, skip → match)",
        old="            if rule.detect_pattern:\n                field_value = _get_field(tool_input, rule.detect_field)\n                if not rule.detect_pattern.search(field_value):\n                    continue",
        new="            if rule.detect_pattern:\n                field_value = _get_field(tool_input, rule.detect_field)\n                if rule.detect_pattern.search(field_value):\n                    continue",
        severity="high",
    ),
    Mutation(
        id="hooks-07",
        file="hooks.py",
        description="Disable role-based filtering (skip check entirely)",
        old="            if should_skip_for_role(rule, agent_role):\n                continue\n            if should_skip_for_phase(rule, current_phase):\n                continue",
        new="            pass  # MUTANT: skip role and phase checks",
        severity="medium",
    ),
    Mutation(
        id="hooks-08",
        file="hooks.py",
        description="Log enforcement continues instead of logging (skip hit recording for log)",
        old="""            if rule.enforcement == "log":
                hit_logger.record(dataclasses.replace(hit, outcome="allowed"))
                continue  # Log doesn't block — check next rule""",
        new="""            if rule.enforcement == "log":
                continue  # MUTANT: skip logging entirely""",
        severity="medium",
    ),
    Mutation(
        id="hooks-09",
        file="hooks.py",
        description="Injection not returning updatedInput (CLI won't see changes)",
        old="""        if injection_applied:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "updatedInput": tool_input,
                }
            }""",
        new="""        if injection_applied:
            return {}  # MUTANT: don't return updatedInput""",
        severity="high",
    ),
    # === rules.py mutations ===
    Mutation(
        id="rules-01",
        file="rules.py",
        description="matches_trigger always returns True (all tools match all rules)",
        old="    return False",
        new="    return True  # MUTANT: all tools match",
        severity="high",
    ),
    Mutation(
        id="rules-02",
        file="rules.py",
        description="should_skip_for_role never skips (role gating disabled)",
        old="""def should_skip_for_role(rule: Rule | Injection, agent_role: str | None) -> bool:
    \"\"\"Return True if the rule should be skipped for this agent role.

    - roles: rule only fires for these roles (skip if role not in list)
    - exclude_roles: rule never fires for these roles (skip if role in list)
    \"\"\"
    if rule.roles:
        # Rule only applies to specific roles
        if agent_role is None or agent_role not in rule.roles:
            return True
    if rule.exclude_roles:
        # Rule is skipped for excluded roles
        if agent_role and agent_role in rule.exclude_roles:
            return True
    return False""",
        new="""def should_skip_for_role(rule: Rule | Injection, agent_role: str | None) -> bool:
    \"\"\"Return True if the rule should be skipped for this agent role.\"\"\"
    return False  # MUTANT: never skip for role""",
        severity="high",
    ),
    Mutation(
        id="rules-03",
        file="rules.py",
        description="should_skip_for_phase never skips (phase gating disabled)",
        old="""def should_skip_for_phase(rule: Rule | Injection, current_phase: str | None) -> bool:
    \"\"\"Return True if rule should be skipped based on current phase.

    Takes the current qualified phase ID string directly (from engine).
    \"\"\"
    if not rule.phases and not rule.exclude_phases:
        return False  # No phase restrictions

    if current_phase is None:
        return bool(rule.phases)  # Skip if rule requires specific phases; don't skip if only exclude_phases

    if rule.phases and current_phase not in rule.phases:
        return True  # Skip: not in allowed phase

    if rule.exclude_phases and current_phase in rule.exclude_phases:
        return True  # Skip: excluded in this phase

    return False""",
        new="""def should_skip_for_phase(rule: Rule | Injection, current_phase: str | None) -> bool:
    \"\"\"Return True if rule should be skipped based on current phase.\"\"\"
    return False  # MUTANT: never skip for phase""",
        severity="high",
    ),
    Mutation(
        id="rules-04",
        file="rules.py",
        description="match_rule always returns True (no pattern matching)",
        old="""def match_rule(rule: Rule, tool_name: str, tool_input: dict[str, Any]) -> bool:
    \"\"\"Check exclude pattern first, then detect pattern.

    Returns True if the rule matches (i.e., should fire).
    \"\"\"
    if rule.detect_pattern is None:
        # No detect pattern = always matches (after trigger check)
        return True

    # Get the field to match against
    text = _get_field(tool_input, rule.detect_field)

    # Check exclude first — if exclude matches, rule does NOT fire
    if rule.exclude_pattern and rule.exclude_pattern.search(text):
        return False

    # Check detect pattern
    return bool(rule.detect_pattern.search(text))""",
        new="""def match_rule(rule: Rule, tool_name: str, tool_input: dict[str, Any]) -> bool:
    \"\"\"Check exclude pattern first, then detect pattern.\"\"\"
    return True  # MUTANT: always match""",
        severity="medium",
    ),
    Mutation(
        id="rules-05",
        file="rules.py",
        description="_get_field returns empty string always (pattern matching broken)",
        old='    return str(tool_input.get(field, ""))',
        new='    return ""  # MUTANT: always empty',
        severity="high",
    ),
    Mutation(
        id="rules-06",
        file="rules.py",
        description="apply_injection doesn't actually modify tool_input",
        old='        tool_input[field] = f"{current_value}{injection.inject_value}"',
        new="        pass  # MUTANT: skip injection application",
        severity="high",
    ),
    Mutation(
        id="rules-07",
        file="rules.py",
        description="Invert exclude_pattern logic in match_rule (exclude → include)",
        old="    if rule.exclude_pattern and rule.exclude_pattern.search(text):\n        return False",
        new="    if rule.exclude_pattern and not rule.exclude_pattern.search(text):\n        return False",
        severity="medium",
    ),
    # === tokens.py mutations ===
    Mutation(
        id="tokens-01",
        file="tokens.py",
        description="consume() always returns True (any token satisfies any rule)",
        old="""    def consume(
        self,
        rule_id: str,
        tool_name: str,
        tool_input: dict,
        enforcement: str = "",
    ) -> bool:
        \"\"\"Consume a one-time override token if one matches.

        Returns True if consumed. Token enforcement must match the
        requesting enforcement level — a warn token cannot satisfy
        a deny rule.
        \"\"\"
        cmd_hash = _hash_command(rule_id, tool_name, _extract_command(tool_input))
        for i, token in enumerate(self._tokens):
            if (
                token.rule_id == rule_id
                and token.tool_name == tool_name
                and token.command_hash == cmd_hash
                and token.enforcement == enforcement
            ):
                self._tokens.pop(i)
                return True
        return False""",
        new="""    def consume(
        self,
        rule_id: str,
        tool_name: str,
        tool_input: dict,
        enforcement: str = "",
    ) -> bool:
        \"\"\"MUTANT: always consume.\"\"\"
        return True  # MUTANT: bypass enforcement isolation""",
        severity="high",
    ),
    Mutation(
        id="tokens-02",
        file="tokens.py",
        description="Skip enforcement level check in consume (warn token satisfies deny)",
        old="""                and token.command_hash == cmd_hash
                and token.enforcement == enforcement""",
        new="""                and token.command_hash == cmd_hash
                # MUTANT: skip enforcement level check""",
        severity="high",
    ),
    Mutation(
        id="tokens-03",
        file="tokens.py",
        description="Don't pop token after consume (reusable tokens)",
        old="                self._tokens.pop(i)\n                return True",
        new="                return True  # MUTANT: token not consumed",
        severity="high",
    ),
    # === parsers.py mutations ===
    Mutation(
        id="parsers-01",
        file="parsers.py",
        description="RulesParser skips enforcement validation (invalid enforcement allowed)",
        old="""        enforcement = entry.get("enforcement", "deny")
        if enforcement not in ("deny", "warn", "log"):
            return f"unknown enforcement '{enforcement}'\"""",
        new="""        enforcement = entry.get("enforcement", "deny")
        # MUTANT: skip enforcement validation""",
        severity="medium",
    ),
    Mutation(
        id="parsers-02",
        file="parsers.py",
        description="_qualify_phases doesn't qualify (bare phase names not prefixed)",
        old="""            result.append(f"{namespace}:{phase}")""",
        new="""            result.append(phase)  # MUTANT: don't qualify""",
        severity="medium",
    ),
]


def apply_mutation(mutation: Mutation) -> tuple[Path, str]:
    """Apply a mutation and return (file_path, original_content)."""
    path = GUARDRAILS / mutation.file
    original = path.read_text(encoding="utf-8")
    if mutation.old not in original:
        raise ValueError(
            f"Mutation {mutation.id}: old text not found in {mutation.file}.\n"
            f"First 80 chars of old: {mutation.old[:80]!r}"
        )
    mutated = original.replace(mutation.old, mutation.new, 1)
    path.write_text(mutated, encoding="utf-8")
    return path, original


def revert(path: Path, original: str) -> None:
    """Restore the original file content."""
    path.write_text(original, encoding="utf-8")


def run_tests() -> bool:
    """Run the guardrails test suite. Returns True if tests pass."""
    result = subprocess.run(
        TEST_CMD,
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
    )
    return result.returncode == 0


def main() -> int:
    # First verify baseline passes
    print("=" * 70)
    print("MUTATION TESTING: Guardrails System")
    print("=" * 70)
    print("\nVerifying baseline tests pass...")
    if not run_tests():
        print("ERROR: Baseline tests fail! Fix tests before mutation testing.")
        return 1
    print("  ✓ Baseline tests pass\n")

    killed = []
    survived = []
    errors = []

    for mutation in MUTATIONS:
        label = f"[{mutation.id}] ({mutation.severity}) {mutation.description}"
        print(f"Testing: {label}")
        try:
            path, original = apply_mutation(mutation)
        except ValueError as e:
            print(f"  ⚠ SKIP: {e}\n")
            errors.append(mutation)
            continue

        try:
            tests_pass = run_tests()
            if tests_pass:
                survived.append(mutation)
                print("  🙁 SURVIVED — tests did NOT catch this mutation!")
            else:
                killed.append(mutation)
                print("  🎉 KILLED — tests caught the mutation")
        except subprocess.TimeoutExpired:
            killed.append(mutation)
            print("  ⏰ KILLED (timeout) — mutation caused test hang")
        finally:
            revert(path, original)

        print()

    # Summary
    total = len(killed) + len(survived)
    print("=" * 70)
    print("MUTATION TESTING RESULTS")
    print("=" * 70)
    print(f"\nTotal mutations tested: {total}")
    print(
        f"  Killed:   {len(killed)} ({100 * len(killed) / total:.0f}%)" if total else ""
    )
    print(
        f"  Survived: {len(survived)} ({100 * len(survived) / total:.0f}%)"
        if total
        else ""
    )
    if errors:
        print(f"  Errors:   {len(errors)} (could not apply)")

    if survived:
        print(f"\n{'─' * 70}")
        print("SURVIVING MUTANTS (tests should catch these but don't):")
        print(f"{'─' * 70}")
        for m in survived:
            sev = (
                "🔴"
                if m.severity == "high"
                else "🟡"
                if m.severity == "medium"
                else "⚪"
            )
            print(f"  {sev} [{m.id}] {m.description}")
            print(f"     File: {m.file} | Severity: {m.severity}")

    if killed:
        print(f"\n{'─' * 70}")
        print("KILLED MUTANTS (tests properly catch these):")
        print(f"{'─' * 70}")
        for m in killed:
            print(f"  ✓ [{m.id}] {m.description}")

    # Mutation score
    if total:
        score = 100 * len(killed) / total
        print(f"\nMutation Score: {score:.0f}%")
        if score >= 80:
            print("  → Good coverage of enforcement logic")
        elif score >= 60:
            print("  → Moderate coverage — some gaps in enforcement testing")
        else:
            print("  → LOW coverage — significant gaps in enforcement testing")

    return 0 if not survived else 2


if __name__ == "__main__":
    sys.exit(main())
