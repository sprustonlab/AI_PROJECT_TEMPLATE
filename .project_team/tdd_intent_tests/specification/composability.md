# Composability Analysis: TDD Intent-Based Integration Tests

## Domain Understanding

This project is about writing **intent-based integration tests** for a Copier template (AI_PROJECT_TEMPLATE) that scaffolds Claude Code projects with guardrails, multi-agent workflows, hints, and cluster support. The tests must prove that features actually work end-to-end — not just that components exist in isolation.

The system has a **full enforcement chain**: `rules.yaml` (declarations) -> `generate_hooks.py` (code generation) -> hook scripts (runtime enforcement) -> `role_guard.py` (role resolution via session markers + env vars) -> `settings.json` (Claude Code hook registration). Every link must be wired for guardrails to fire.

Critical discoveries:
1. Hook scripts are generated but **never wired into settings.json** for standard triggers
2. `rules.yaml` has only universal rules (R01-R03) — **no role-based rules exist yet**
3. `setup_ao_mode.sh` and `teardown_ao_mode.sh` are **referenced everywhere but don't exist**
4. The full chain from role assignment to enforcement has never been tested end-to-end

## Identified Axes

### Axis 1: Test Scope
- **Values:** `wiring` | `merge` | `enforcement-chain`
- **Why independent:** Wiring (does settings.json contain hook entries?) is orthogonal to merge (does updating preserve existing keys?) which is orthogonal to enforcement-chain (does a role-gated rule actually block the right agent?). Each can pass or fail independently.

### Axis 2: Template Feature
- **Values:** `guardrails` | `hints` | `project_team` | `cluster` | `pattern_miner`
- **Why independent:** Each feature is conditionally included via copier.yml booleans. Tests for one feature should not depend on another being enabled.

### Axis 3: Settings.json State (for merge tests)
- **Values:** `absent` | `empty` | `has_permissions` | `has_mcpServers` | `has_hooks` | `has_all`
- **Why independent:** The merge behavior must work regardless of what's already in settings.json. This axis captures the user's starting state.

### Axis 4: Trigger Type
- **Values:** `hardcoded` (Bash/Read/Glob/Write/Edit/SessionStart) | `mcp_custom` (mcp__*)
- **Why independent:** The current code treats these differently for settings.json wiring. Tests must cover both.

### Axis 5: Execution Context
- **Values:** `fresh_generation` | `copier_update` | `manual_regeneration`
- **Why independent:** The merge-vs-overwrite concern manifests differently in each context.

### Axis 6: Agent Role (NEW)
- **Values:** `Coordinator` | `Implementer` | `Skeptic` | `TestEngineer` | (any named role) | `unset`
- **Why independent:** Each role has different permissions. The enforcement outcome depends on the role but is independent of which trigger fires or what's in settings.json. A Coordinator blocked from Write is a different concern from an Implementer blocked from Write — the rule engine must evaluate them independently.
- **Seam:** claudechic sets `CLAUDE_AGENT_ROLE` via `spawn_agent(type=...)`. `role_guard.py` reads it for `allow:`/`block:` matching. The seam is the env var — clean in principle, but untested.

### Axis 7: Team Mode State (NEW)
- **Values:** `inactive` (no session marker) | `active` (marker present) | `torn_down` (marker deleted)
- **Why independent:** Team mode controls which rules fire. In solo mode, only `Agent`-group rules fire. In team mode, `TeamAgent`, `Subagent`, and named-role rules also fire. This is orthogonal to which role the agent has — an Implementer in solo mode behaves differently from an Implementer in team mode.
- **Seam:** `setup_ao_mode.sh` writes the session marker; `teardown_ao_mode.sh` deletes it. `role_guard.py` reads it via `get_my_role()`. The seam is the filesystem marker at `.claude/guardrails/sessions/ao_<PID>`.

### Axis 8: Rule Type (NEW)
- **Values:** `universal` (no allow/block — applies to all) | `role-gated` (has allow or block list)
- **Why independent:** A universal rule (R01: deny dangerous ops) fires regardless of role. A role-gated rule (e.g., "only Implementer may write to src/") fires based on role resolution. The detection logic (regex) is the same; the enforcement decision path diverges. These are independent dimensions of rule design.

## Compositional Laws

**Law 1 — Generate-then-wire:**
> Every hook script produced by `generate_hooks.py` MUST have a corresponding entry in `.claude/settings.json`. A hook script without a settings.json entry is dead code.

**Law 2 — Merge preservation:**
> `existing_keys(before) ⊆ existing_keys(after)`. No key present before the operation may be absent after.

**Law 3 — Idempotency:**
> Running generate_hooks.py N times produces identical settings.json.

**Law 4 — Role-enforcement correctness (NEW):**
> For a role-gated rule with `allow: [X]`: agents with role X pass, agents with role Y are blocked. For `block: [X]`: agents with role X are blocked, agents with role Y pass. This must hold for all enforcement levels (deny, warn, log).

**Law 5 — Team mode activation (NEW):**
> `get_my_role()` returns `None` when no session marker exists (solo mode). Returns `"Coordinator"` when session marker's `coordinator` field matches `CLAUDE_AGENT_NAME`. Returns the agent name for sub-agents. Team-mode rules fire only when `get_my_role() is not None`.

**Law 6 — Session lifecycle (NEW):**
> `setup_ao_mode.sh` creates a valid session marker. `teardown_ao_mode.sh` removes it. After teardown, `get_my_role()` returns `None` and team-mode rules stop firing. The lifecycle is: inactive -> setup -> active -> teardown -> inactive.

## Crystal Holes

### Hole 1: Hardcoded triggers not wired (CONFIRMED BUG)
- `update_settings_json()` only called for `mcp_triggers` (line 2048-2049)
- Standard hooks are dead code
- **Crystal:** Axis 4 = `hardcoded` x Axis 1 = `wiring` -> FAILS

### Hole 2: settings.json not created when absent
- `update_settings_json()` returns early if file doesn't exist (line 1885-1886)
- Fresh copier generations have no settings.json
- **Crystal:** Axis 3 = `absent` x Axis 1 = `wiring` -> FAILS

### Hole 3: No role-based rules in rules.yaml (CONFIRMED GAP)
- `rules.yaml.jinja` only has R01-R03 — all universal, no `allow:`/`block:` fields
- The entire role-gated code path in `generate_hooks.py` and `role_guard.py` is exercised by zero rules
- The code supports role gating (thoroughly implemented), but no rules use it
- **Crystal:** Axis 8 = `role-gated` x Axis 2 = `guardrails` -> NO COVERAGE
- **Impact:** The role permission system is dead — not because the code is broken, but because no rules activate it

### Hole 4: setup_ao_mode.sh / teardown_ao_mode.sh don't exist (CONFIRMED GAP)
- `role_guard.py` references them in docstrings (lines 79-80)
- `README.md` documents the "Team Skill Contract" requiring them (line 61-63)
- They are referenced as the mechanism to write/delete session markers
- But neither file exists anywhere in the template or project
- **Crystal:** Axis 7 = `active` x Axis 2 = `project_team` -> IMPOSSIBLE (no activation mechanism)
- **Impact:** Team mode cannot be activated through the documented contract. Session markers would have to be created manually or by some other undocumented mechanism.

### Hole 5: Full enforcement chain never tested end-to-end
- No test sends a simulated tool call through a generated hook with role env vars set and a session marker present
- The chain: `rules.yaml` -> `generate_hooks.py` -> hook script reads stdin -> imports `role_guard` -> checks env vars + session marker -> returns exit code
- Each link works in isolation (role_guard has unit-testable functions), but the chain has never been assembled
- **Crystal:** Axis 1 = `enforcement-chain` x Axis 6 = any role x Axis 7 = `active` -> NEVER TESTED

### Hole 6: Merge protection untested
- `update_settings_json()` preserves existing keys by accident (read-modify-write on full dict)
- No test verifies `permissions`, `mcpServers`, or custom user keys survive
- **Crystal:** Axis 3 = `has_permissions` x Axis 1 = `merge` -> NOT TESTED

### Hole 7: copier update may clobber settings.json
- If settings.json is added to template, copier update may overwrite it
- Need either `_skip_if_exists` in copier.yml or post-generation-only creation
- **Crystal:** Axis 5 = `copier_update` x Axis 3 = `has_all` -> RISK

## Seam Analysis

### Seam 1: Template Generation <-> Hook Generation
- **Current:** Copier generates files; user must run `generate_hooks.py` separately
- **Clean?** Mostly clean but leaves a gap — no one wires settings.json on fresh generation
- **Fix:** Either copier post-generation task runs generate_hooks.py, or template includes minimal settings.json

### Seam 2: Hook Scripts <-> Settings.json Registration (DIRTY)
- **Current:** Hardcoded triggers generate scripts only; MCP triggers do both
- **Fix:** All generated hooks registered uniformly. Trigger type must not affect wiring.

### Seam 3: Settings.json <-> Existing User Configuration
- **Current:** Read-modify-write preserves existing keys. Untested.
- **Clean?** Structurally clean but fragile without tests.

### Seam 4: claudechic <-> role_guard.py (NEW — CRITICAL)
- **Current:** claudechic sets `CLAUDE_AGENT_NAME` (always) and `CLAUDE_AGENT_ROLE` (via `spawn_agent(type=...)`). `role_guard.py` reads these for role resolution.
- **Clean?** The seam is the env var interface — clean in design. But the values must match exactly (case-sensitive). A mismatch between spawn `type=` and rules.yaml `allow:`/`block:` entry silently fails open (rule doesn't match, agent proceeds unblocked).
- **Test concern:** Must verify that spawning with `type="Implementer"` and a rule `allow: [Implementer]` produces the correct enforcement. Case mismatch (e.g., `type="implementer"`) must be caught.

### Seam 5: setup_ao_mode.sh <-> session marker <-> get_my_role() (NEW — BROKEN)
- **Current:** `get_my_role()` reads `.claude/guardrails/sessions/ao_<PID>` and expects JSON with a `coordinator` field. `setup_ao_mode.sh` is supposed to write this. But `setup_ao_mode.sh` doesn't exist.
- **Clean?** The seam design is clean (filesystem marker with JSON schema). But one side of the seam is missing entirely.
- **Fix:** Create `setup_ao_mode.sh` and `teardown_ao_mode.sh`. Test that the marker they write is correctly read by `get_my_role()`.

### Seam 6: rules.yaml <-> generate_hooks.py <-> hook scripts (NEW)
- **Current:** `generate_hooks.py` reads `rules.yaml`, generates Python hook scripts with inlined allow/block lists and baked role_guard calls. At runtime, hooks import `role_guard` and call `check_role()` with the baked lists.
- **Clean?** Clean — rules are the single source of truth, hooks are derived artifacts. But the generated code must correctly translate `allow:`/`block:` from YAML into Python literals. Currently untested for role-gated rules because no such rules exist (Hole 3).

## Recommended Test Structure (Algebraic)

Tests enforce laws, not combinations:

```
Law 1 (Wiring Completeness):
  For ALL hook scripts in .claude/guardrails/hooks/:
    ASSERT settings.json contains a matching entry

Law 2 (Merge Preservation):
  Given ANY pre-existing settings.json content:
    After generate_hooks.py runs:
      ASSERT all original keys still present
      ASSERT all original values unchanged (for non-hook keys)

Law 3 (Idempotency):
  Running generate_hooks.py N times produces identical settings.json

Law 4 (Role Enforcement):
  For EACH role-gated rule:
    For EACH agent role:
      Simulate hook stdin with role env vars set
      ASSERT exit code matches allow/block expectation

Law 5 (Team Mode Lifecycle):
  setup_ao_mode.sh -> get_my_role() returns role -> rules fire
  teardown_ao_mode.sh -> get_my_role() returns None -> team rules skip

Law 6 (Full Chain):
  copier generate -> generate_hooks.py -> hook script + settings.json entry
  + session marker + env vars -> hook fires -> correct enforcement
```

## File Structure Recommendation

```
tests/
  test_intent_wiring.py           # Law 1: hook scripts <-> settings.json entries
  test_intent_merge.py            # Law 2: settings.json preservation across states
  test_intent_guardrails.py       # Law 4: role-gated rule enforcement end-to-end
  test_intent_team_lifecycle.py   # Law 5: setup/teardown/get_my_role chain
  test_intent_full_chain.py       # Law 6: copier -> generate -> enforce
  test_intent_hints.py            # Feature: hints end-to-end
```

Each file tests one concern. No file depends on another.

## Recommended Deep-Dive Axes

1. **Agent Role (Axis 6)** — The role permission system exists in code but has zero rules exercising it. Tests must add role-gated rules to rules.yaml and verify the full allow/block/enforcement matrix.
2. **Team Mode State (Axis 7)** — The activation scripts don't exist. Tests must define and verify the session marker contract, then test that role resolution works across the lifecycle.
3. **Settings.json State (Axis 3)** — User's #1 stated concern. Merge must be exhaustively tested.
4. **Rule Type (Axis 8)** — Universal vs role-gated rules follow different code paths in generated hooks. Both must be tested through the chain.
