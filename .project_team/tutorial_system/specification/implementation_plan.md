# SDK Hooks Migration — Implementation Plan

## Overview

**Goal:** Replace the file-based guardrail system (~2860 lines of generated hooks, shell scripts, and env var plumbing) with the PoC SDK in-process hooks in claudechic (~210 lines), then extend with phase system support.

**Current state:** PoC validated in `claudechic/guardrails/rules.py` + `app.py._guardrail_hooks()`. Works for deny + user_confirm. Has debug logging, no hit logging, no ack flow, fail-open on errors.

---

## Phase A: PoC → Production Quality

### A1: Remove debug logging from hook

**Files to modify:**
- `submodules/claudechic/claudechic/app.py` (lines 657-658, 680-684, 690-692, 702-707, 712-713)

**Lines changed:** ~15 deleted/modified

**Dependencies:** None

**Work:**
- Remove all `print(f"[guardrail-hook] ...")` statements from `evaluate()` and `_show_guardrail_confirm()`
- Replace stderr debug prints with structured logging (or just remove — hits.jsonl covers the audit trail in A3)
- Keep the `except Exception` handler but change from fail-open print to proper error handling (see A5)

**Test plan:**
- Run `pixi run pytest` with output redirect — confirm no `[guardrail-hook]` lines in stderr
- Trigger R02 (pip install) — confirm it still blocks
- Trigger user_confirm — confirm prompt appears and works

---

### A2: Startup validation for rules.yaml

**Files to modify:**
- `submodules/claudechic/claudechic/guardrails/rules.py` — add `validate_rules_file()` function (~30 lines)
- `submodules/claudechic/claudechic/app.py` — call validator at startup, show error in TUI (~10 lines)

**Lines changed:** ~40 added

**Dependencies:** None

**Work:**
- New function `validate_rules_file(path: Path) -> list[str]` that checks:
  - File exists and is valid YAML
  - Has `rules:` key
  - Each rule has required fields (`id`, `trigger`, `enforcement`)
  - Regex patterns compile without error
  - Enforcement values are in `{"deny", "warn", "log", "user_confirm"}`
- Call during `on_mount()` or agent creation in `app.py`
- Display validation errors via `self.notify()` (Textual notification)

**Test plan:**
- Create a malformed rules.yaml (bad regex, missing field) — confirm error notification appears
- Restore valid rules.yaml — confirm clean startup
- Unit test `validate_rules_file()` with known-bad inputs

---

### A3: Add hits.jsonl logging

**Files to modify:**
- `submodules/claudechic/claudechic/guardrails/hits.py` — NEW file (~30 lines)
- `submodules/claudechic/claudechic/guardrails/__init__.py` — NEW file if missing (empty or re-export)
- `submodules/claudechic/claudechic/app.py` — call `log_hit()` when a rule matches (~5 lines)

**Lines changed:** ~35 added

**Dependencies:** A1 (debug logging removed, so we know what to replace)

**Work:**
- `hits.py` contains `log_hit(rule_id, enforcement, tool_name, tool_input_summary, agent_role, decision, path)`
- Appends one JSON line per hit to `.claude/guardrails/hits.jsonl`
- Format: `{"ts": ISO8601, "rule": "R02", "enforcement": "deny", "tool": "Bash", "command_prefix": "pip install ...", "agent_role": null, "decision": "block"}`
- Call from `evaluate()` whenever a rule matches (before returning decision)

**Test plan:**
- Trigger R02 — confirm line appended to hits.jsonl
- Trigger user_confirm rule — confirm hit logged with `decision: "allow"` or `"deny"` based on user choice
- Confirm hits.jsonl is valid JSONL (each line parses as JSON)

---

### A4: Handle ack flow for warn enforcement

**Files to modify:**
- `submodules/claudechic/claudechic/app.py` — change `warn` handling in `evaluate()` (~20 lines)
- `submodules/claudechic/claudechic/guardrails/rules.py` — add ack checking function (~15 lines)

**Lines changed:** ~35 added/modified

**Dependencies:** A1

**Work:**
- Currently `warn` just blocks (same as deny). Change to:
  1. Check for `# ack:R01` in the command text (Bash tool_input["command"])
  2. If ack present → allow (log the ack in hits.jsonl)
  3. If no ack → block with message that includes "Add `# ack:R01` to acknowledge"
- New function in rules.py: `has_ack(rule_id: str, tool_input: dict) -> bool`
- Respect `ack_ttl_seconds` from rules.yaml catalog metadata

**Test plan:**
- Create a test rule with `enforcement: warn`
- Trigger without ack → confirm blocked with ack instructions
- Trigger with `# ack:RXX` in command → confirm allowed
- Verify hits.jsonl records both cases

---

### A5: Fail-closed behavior on bad rules.yaml

**Files to modify:**
- `submodules/claudechic/claudechic/app.py` — change `except` handler in `evaluate()` (~5 lines)

**Lines changed:** ~5 modified

**Dependencies:** A1, A2

**Work:**
- Change the catch-all `except` in `evaluate()` from `return {}` (fail-open) to `return {"decision": "block", "reason": "Guardrail system error — blocking for safety. Fix rules.yaml and restart."}`
- This ensures a corrupt rules.yaml doesn't silently disable all guardrails
- The A2 startup validation gives early warning; this is the runtime safety net

**Test plan:**
- Corrupt rules.yaml mid-session (e.g., invalid YAML syntax)
- Attempt a Bash command → confirm it's blocked with error message
- Fix rules.yaml → confirm next command works (rules reloaded fresh each call)

---

## Phase B: Wire Up for All Agents

### B1: Per-agent closures with static role for subagents

**Files to modify:**
- `submodules/claudechic/claudechic/app.py` — modify `_make_options()` call sites (~15 lines)
- `submodules/claudechic/claudechic/agent_manager.py` — ensure `agent_type` propagates through `create_agent()` (~5 lines)

**Lines changed:** ~20 modified

**Dependencies:** A1-A5 complete

**Work:**
- `_merged_hooks(agent_type)` already creates a closure capturing `agent_role` — correct for per-agent closures
- Fix all `_make_options()` call sites to pass `agent_type`:
  - Line 944: main agent creation — passes `agent_name` but NOT `agent_type` → fix
  - Lines 2095, 2295, 2310: reconnect/reload paths → add `agent_type`
- Subagents get `agent_type="Subagent"` (static) — baked into the closure
- Verify `AgentManager.create_agent()` passes `agent_type` through

**Test plan:**
- Create a subagent via `/agent` → confirm it has `agent_type="Subagent"`
- Trigger R04 (git push) from subagent → confirm blocked
- Trigger R04 from main agent → confirm allowed
- Verify role appears in hits.jsonl

---

### B2: Main agent role assignment

**Files to modify:**
- `submodules/claudechic/claudechic/app.py` — set `agent_type="Coordinator"` for main agent (~3 lines)

**Lines changed:** ~3 modified

**Dependencies:** B1

**Work:**
- In main agent creation, pass `agent_type="Coordinator"`
- R04's `block: [Subagent]` correctly skips for the Coordinator

**Test plan:**
- Start app → main agent should have Coordinator role
- Trigger role-gated rules → confirm correct behavior per role

---

### B3: Test with team mode (Coordinator + subagents)

**Files to modify:** None (integration test task)

**Dependencies:** B1, B2

**Work:** Manual integration test:
- Launch claudechic, create Coordinator + 2 subagents
- R04 (git push) from subagent → blocked; from coordinator → allowed
- R05 (edit guardrails) from subagent → blocked; from coordinator → allowed
- R01, R02 (non-role-gated) → blocked for all agents

**Test plan:** Manual test scenarios above, verify hits.jsonl entries

---

## Phase C: Delete Old System

### C1: Delete generators and generated hooks

**Files to delete:**
- `.claude/guardrails/generate_hooks.py` (2155 lines)
- `.claude/guardrails/hooks/bash_guard.py` (173 lines)
- `.claude/guardrails/hooks/write_guard.py` (185 lines)
- `template/.claude/guardrails/generate_hooks.py`

**Lines deleted:** ~2513

**Dependencies:** B3

**Test plan:** SDK hooks still work after deletion, no import errors

---

### C2: Delete role_guard.py

**Files to delete:**
- `.claude/guardrails/role_guard.py` (~350 lines)
- `template/.claude/guardrails/role_guard.py`

**Lines deleted:** ~700

**Dependencies:** C1

**Test plan:** No imports reference `role_guard`, role-based enforcement works via SDK hooks

---

### C3: Remove session marker system and env vars

**Files to delete:**
- `.claude/guardrails/setup_ao_mode.sh`
- `.claude/guardrails/teardown_ao_mode.sh`
- `.claude/guardrails/sessions/` directory

**Files to modify:**
- `submodules/claudechic/claudechic/app.py` — remove env var lines for `CLAUDE_AGENT_NAME`, `CLAUDECHIC_APP_PID`, `CLAUDE_AGENT_ROLE` (lines 775-782, ~8 lines)

**Lines deleted/modified:** ~78

**Dependencies:** C1, C2

**Work:** SDK hooks get `agent_role` via closure capture — no env vars needed. Remove the 3 env var assignments from `_make_options()`.

**Test plan:** Guardrails still work without env vars, team mode still works

---

### C4: Clean up references

**Files to modify:**
- `.claude/guardrails/test_framework.py` — DELETE
- `.claude/guardrails/README.md` — UPDATE for new architecture
- `.claude/guardrails/rules.yaml` line 5 — remove `generate_hooks.py` comment
- `.claude/guardrails/rules.yaml.example` — same
- `.claude/commands/init_project.md` — remove references to deleted files

**Lines changed:** ~50

**Dependencies:** C1-C3

**Test plan:** `grep -r "generate_hooks\|bash_guard\|write_guard\|role_guard\|setup_ao_mode\|teardown_ao_mode" .claude/` returns nothing

---

## Phase D: Phase System (Check + Phase Primitives)

### D1: Harden phase_state.json reader

**Files to modify:**
- `submodules/claudechic/claudechic/guardrails/rules.py` — harden `read_phase_state()`, add `write_phase_state()` (~25 lines)

**Lines changed:** ~25 modified/added

**Dependencies:** Phase C complete

**Test plan:** Unit tests for read/write, corrupt file returns None

---

### D2: Phase evaluation verification

**Files to modify:**
- `submodules/claudechic/claudechic/guardrails/rules.py` — minor hardening of `should_skip_for_phase()` (~5 lines)

**Lines changed:** ~5 modified

**Dependencies:** D1

**Test plan:** Add test rules with `phase_block`/`phase_allow`, verify with different phase_state.json values

---

### D3: WorkflowEngine

**Files to create:**
- `submodules/claudechic/claudechic/guardrails/workflow.py` — NEW (~80 lines)

**Lines changed:** ~80 added

**Dependencies:** D1, D2

**Work:** `WorkflowEngine` class with `load_manifest()`, `current_phase()`, `advance_phase()`, `run_checks()`. Integrates with Check protocol from specification.

**Test plan:** Unit tests for manifest loading, phase advancement, gate check blocking

---

### D4: COORDINATOR.md split into phase files + manifest

**Files to create:**
- `.ao_project_team/phases.yaml` — manifest (~30 lines)
- `.ao_project_team/phases/` — per-phase markdown files

**Lines changed:** ~150 added (mostly markdown)

**Dependencies:** D3

**Test plan:** WorkflowEngine successfully loads manifest, phase files referenced correctly

---

## Dependency Graph

```
A1 ──┬── A3
     ├── A4
     └── A5 (also needs A2)
A2 ──┘

A1-A5 ── B1 ── B2 ── B3

B3 ── C1 ──┬── C3 ── C4
            └── C2 ──┘

C4 ── D1 ── D2 ── D3 ── D4
```

**Parallelizable:** A1+A2 in parallel. A3+A4 in parallel. C1+C2 in parallel.

## Summary Table

| Task | Est. Lines | Files | Dependencies |
|------|-----------|-------|-------------|
| A1: Remove debug logging | -15 | app.py | — |
| A2: Startup validation | +40 | rules.py, app.py | — |
| A3: hits.jsonl logging | +35 | hits.py (new), app.py | A1 |
| A4: Ack flow for warn | +35 | app.py, rules.py | A1 |
| A5: Fail-closed | +5 | app.py | A1, A2 |
| B1: Per-agent closures | ~20 | app.py, agent_manager.py | A* |
| B2: Main agent role | ~3 | app.py | B1 |
| B3: Team mode test | 0 | (manual test) | B1, B2 |
| C1: Delete generators | -2513 | 4 files deleted | B3 |
| C2: Delete role_guard | -700 | 2 files deleted | C1 |
| C3: Remove session/env | -78 | scripts + app.py | C1, C2 |
| C4: Clean references | -50 | various | C1-C3 |
| D1: Phase state reader | +25 | rules.py | C* |
| D2: Phase evaluation | +5 | rules.py | D1 |
| D3: WorkflowEngine | +80 | workflow.py (new) | D1, D2 |
| D4: Phase files | +150 | phases.yaml + markdown | D3 |

**Net change:** ~-2968 lines deleted, ~+388 lines added = **~-2580 net lines**
