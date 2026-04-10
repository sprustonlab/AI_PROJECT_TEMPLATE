# Specification: TDD Intent-Based Tests — Full Guardrail + Team Mode Chain

## Summary

Four broken chains in the guardrail system. All documented, none operational. Write failing tests for each chain, then fix.

| Chain | What's Broken | Root Cause |
|-------|---------------|------------|
| 1. Settings.json wiring | Hooks generated but never registered | `update_settings_json()` returns early if file absent; hardcoded triggers excluded |
| 2. Settings merge | No merge-safe update | Same function — but merge logic itself is sound once reachable |
| 3. Team mode activation | `setup_ao_mode.sh` / `teardown_ao_mode.sh` don't exist | Referenced 14+ times in docs, never created |
| 4. Role enforcement | Real `rules.yaml` has zero role-gated rules | Only universal R01-R03; roles exist only in `rules.yaml.example` |

## Approach: Red → Green TDD

**Phase A (Red):** 8 failing tests proving each chain is broken.
**Phase B (Green):** 4 code changes to make them pass.

---

## Phase A: Failing Tests

### File 1: `tests/test_intent_guardrail_wiring.py`

Tests that settings.json gets created, populated with ALL hooks, and merges safely.

#### Test 1: `test_generate_hooks_creates_settings_json_when_absent`
- **Setup:** Copier copy with `use_guardrails=True`. Ensure no settings.json exists.
- **Act:** Run `generate_hooks.py`
- **Assert:** `.claude/settings.json` exists AND contains `hooks.PreToolUse` entries
- **Why RED:** `update_settings_json()` returns early at line ~1886 if file absent

#### Test 2: `test_all_generated_hooks_have_settings_entries`
- **Setup:** Copier copy + run `generate_hooks.py`
- **Act:** List all `.py` hook scripts in `.claude/guardrails/hooks/`, parse `settings.json`
- **Assert:** Every hook script has a matching `PreToolUse` entry — both hardcoded (Bash, Read, Glob, Write, Edit) AND MCP triggers
- **Why RED:** Hardcoded triggers explicitly excluded at line ~2034

#### Test 3: `test_settings_merge_preserves_existing_content`
- **Setup:** Copier copy, pre-populate settings.json with:
  ```json
  {"permissions": {"allow": ["Read"]}, "mcpServers": {"my_server": {"command": "node"}}}
  ```
- **Act:** Run `generate_hooks.py`
- **Assert:** `permissions` and `mcpServers` keys unchanged, `hooks.PreToolUse` added alongside
- **Why RED:** Function returns early / no merge path for hardcoded triggers

#### Test 4: `test_settings_merge_is_idempotent`
- **Setup:** Copier copy + run `generate_hooks.py` twice
- **Assert:** settings.json content identical after both runs (no duplicate entries)
- **Why RED:** First run fails to create file; if fixed, idempotency needs verification

### File 2: `tests/test_intent_team_activation.py`

Tests that team mode can be activated and deactivated via the documented scripts.

#### Test 5: `test_setup_ao_mode_creates_session_marker`
- **Setup:** Copier copy with `use_guardrails=True` and `use_project_team=True`
- **Act:** Run `setup_ao_mode.sh` with `CLAUDE_AGENT_NAME=Coordinator` and `CLAUDECHIC_APP_PID=12345`
- **Assert:** `.claude/guardrails/sessions/ao_12345` exists with valid JSON `{"coordinator": "Coordinator"}`
- **Why RED:** `setup_ao_mode.sh` does not exist

#### Test 6: `test_teardown_ao_mode_removes_marker`
- **Setup:** Same as Test 5, run `setup_ao_mode.sh` first
- **Act:** Run `teardown_ao_mode.sh`
- **Assert:** Session marker file is deleted, `sessions/` dir is clean
- **Why RED:** `teardown_ao_mode.sh` does not exist

#### Test 7: `test_setup_ao_mode_rejects_double_activation`
- **Setup:** Run `setup_ao_mode.sh` once
- **Act:** Run `setup_ao_mode.sh` again with same PID
- **Assert:** Second call fails (non-zero exit) with error message
- **Why RED:** Script doesn't exist

### File 3: `tests/test_intent_role_enforcement.py`

Tests that real role-gated rules in `rules.yaml` enforce correctly with real project role names. Uses the subprocess + env var pattern from `test_framework.py` — NOT duplicating mechanism tests, only testing real rules with real roles.

#### Test 8: `test_real_role_rule_blocks_subagent`
- **Setup:** Copier copy + generate hooks. Add session marker (team mode active). Set env: `CLAUDE_AGENT_ROLE=Skeptic`, `CLAUDE_AGENT_NAME=SkepticAgent`
- **Act:** Pipe a forbidden action (e.g., `git push`) through the bash guard hook
- **Assert:** Exit code 2 (blocked) for Subagent; exit code 0 (allowed) for Coordinator
- **Why RED:** Real `rules.yaml` has no role-gated rules — only universal R01-R03

#### Test 9: `test_full_chain_copier_to_enforcement`
- **Setup:** Full end-to-end:
  1. Copier copy into temp dir
  2. Run `generate_hooks.py`
  3. Verify settings.json has hook entries
  4. Run `setup_ao_mode.sh` to activate team mode
  5. Set `CLAUDE_AGENT_ROLE=Implementer`
- **Act:** Pipe a role-restricted action through the generated hook
- **Assert:** Correct enforcement (blocked or allowed per the rule)
- **Why RED:** Multiple chain links broken simultaneously

---

## Phase B: Code Fixes (after ALL red tests written and confirmed failing)

### Fix 1: `generate_hooks.py` — Create settings.json if absent + register ALL triggers

**File:** `template/.claude/guardrails/generate_hooks.py` (and root copy `.claude/guardrails/generate_hooks.py`)

**Change A — create file if absent:**
```python
# Current (line ~1885):
if not settings_path.exists():
    return

# Fix:
if not settings_path.exists():
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("{}")
```

**Change B — register hardcoded triggers too:**
```python
# Current (line ~2034):
mcp_triggers = sorted(t for t in groups if t not in _hardcoded)

# Fix: register ALL triggers, not just MCP
all_triggers = sorted(groups.keys())
```

Then call `update_settings_json()` for all triggers, not just MCP ones.

### Fix 2: Create `setup_ao_mode.sh`

**Files to create:**
- `template/.claude/guardrails/setup_ao_mode.sh`
- `.claude/guardrails/setup_ao_mode.sh` (root copy)

**Behavior (derived from README + role_guard.py docs):**
1. Read `CLAUDECHIC_APP_PID` (or `AGENT_SESSION_PID`) from env
2. Read `CLAUDE_AGENT_NAME` from env
3. Create `sessions/` dir if absent
4. Check for existing marker — fail if already active for this PID
5. Write marker: `{"coordinator": "$CLAUDE_AGENT_NAME"}`
6. Exit 0

### Fix 3: Create `teardown_ao_mode.sh`

**Files to create:**
- `template/.claude/guardrails/teardown_ao_mode.sh`
- `.claude/guardrails/teardown_ao_mode.sh` (root copy)

**Behavior:**
1. Read PID from env
2. Delete session marker
3. Exit 0

### Fix 4: Add exemplar role-gated rules to `rules.yaml`

**File:** `template/.claude/guardrails/rules.yaml.jinja` (and root `rules.yaml`)

Add 2-3 role-gated exemplar rules using real project role names. Suggested:

```yaml
- id: R04
  description: "Only Coordinator can push to remote"
  trigger: Bash
  pattern: "git\\s+push"
  enforce: deny
  block: [Subagent]
  message: "Only Coordinator can push. Ask Coordinator to push for you."

- id: R05
  description: "Subagents cannot modify guardrail config"
  trigger: Write
  file_pattern: "\\.claude/guardrails/"
  enforce: deny
  block: [Subagent]
  message: "Guardrail config is managed by Coordinator only."
```

**Note:** These are exemplars, not a full policy. The user adds more following this pattern.

---

## Files to Create/Modify

| File | Action | Phase |
|------|--------|-------|
| `tests/test_intent_guardrail_wiring.py` | CREATE — 4 failing tests | A (Red) |
| `tests/test_intent_team_activation.py` | CREATE — 3 failing tests | A (Red) |
| `tests/test_intent_role_enforcement.py` | CREATE — 2 failing tests | A (Red) |
| `template/.claude/guardrails/generate_hooks.py` | MODIFY — create settings.json + register all triggers | B (Green) |
| `.claude/guardrails/generate_hooks.py` | MODIFY — same fix (root copy) | B (Green) |
| `template/.claude/guardrails/setup_ao_mode.sh` | CREATE | B (Green) |
| `template/.claude/guardrails/teardown_ao_mode.sh` | CREATE | B (Green) |
| `.claude/guardrails/setup_ao_mode.sh` | CREATE (root copy) | B (Green) |
| `.claude/guardrails/teardown_ao_mode.sh` | CREATE (root copy) | B (Green) |
| `template/.claude/guardrails/rules.yaml.jinja` | MODIFY — add 2-3 role-gated exemplars | B (Green) |
| `.claude/guardrails/rules.yaml` | MODIFY — add matching rules | B (Green) |

---

## What NOT to Build

- A complete role policy for all 17 agent types (user's job — we provide exemplars)
- TUI rendering tests (wrong layer — test wiring, not UI)
- Duplicates of test_framework.py's 35 mechanism tests (those already prove the framework works)
- A settings.json template file in copier (generate_hooks.py should be single source of truth for hooks registration)

---

## Compositional Laws Enforced by Tests

| Law | Property | Test(s) |
|-----|----------|---------|
| 1. Wiring Completeness | Every hook script → matching settings.json entry | 1, 2 |
| 2. Merge Preservation | Pre-existing settings.json keys survive | 3 |
| 3. Idempotency | N runs of generate_hooks.py → identical output | 4 |
| 4. Role-Enforcement Correctness | allow:[X] passes X, blocks Y | 8 |
| 5. Team Mode Activation | Session marker → role_guard detects team mode | 5, 6, 7 |
| 6. Full Chain | copier → hooks → settings → team mode → enforcement | 9 |

---

## Success Criteria

1. All 9 new tests fail on current code (Red confirmed)
2. After fixes, all 9 tests pass (Green confirmed)
3. All existing tests still pass (no regressions)
4. A generated project has settings.json with ALL hook entries
5. `setup_ao_mode.sh` creates valid session markers
6. Real role-gated rules fire for real project role names
7. The full chain works end-to-end in a copier-generated temp project
