# Skeptic Review: TDD Intent Tests (Updated — Expanded Scope)

## Verdict: Expanded scope is the right call. Four new risks need resolution.

The original review focused narrowly on settings.json wiring. The user's rejection is correct: settings.json wiring is necessary but not sufficient. The full chain is: **team activation → session marker → role in env → hook fires → role checked → action blocked/allowed.** Every link must be tested. Below is the updated assessment.

---

## PRIOR FINDINGS (Still Valid)

The five risks from the initial review remain. Summary:

| # | Risk | Status | One-line |
|---|------|--------|----------|
| 1 | TUI test infra | Solved | Textual Pilot API works headless in CI on 3 OSes |
| 2 | Copier in temp dirs | Low | `copier_output` fixture works cross-platform |
| 3 | settings.json wiring | **Critical** | `update_settings_json()` silently no-ops when file absent; hardcoded triggers never registered |
| 4 | Testing the right layer | Medium | Focus on settings.json lifecycle, not hook behavior (already tested) |
| 5 | generate_hooks.py bootstrap | **Critical** | Can't create file, only manages MCP triggers |

---

## NEW RISK 6: setup_ao_mode.sh Doesn't Exist

**Status: CONFIRMED. The script is referenced 14 times but never created.**

`role_guard.py` line 79: "written by `setup_ao_mode.sh` when a team skill activates." `README.md` describes the contract in detail. But `find` across the entire repo returns zero files named `setup_ao_mode*` or `teardown_ao_mode*`.

**What it must do** (derived from README.md + role_guard.py):

1. **Write session marker:** `.claude/guardrails/sessions/ao_<AGENT_SESSION_PID>` containing `{"coordinator": "<CLAUDE_AGENT_NAME>"}`
2. **Fail if marker exists:** Prevent double-activation (one team session per PID)
3. **Clean stale markers:** Remove markers for non-running PIDs at startup
4. **Set env vars (or verify they're set):** `AGENT_SESSION_PID` (or fallback `CLAUDECHIC_APP_PID`)
5. **Create sessions/ dir** if absent

Corresponding `teardown_ao_mode.sh` must delete the marker.

**The risk here is scope creep, not difficulty.** The script itself is ~30 lines of bash. The risk is: **who calls it?** The README says "any skill that activates team mode must call `setup_ao_mode.sh`." Currently, the `/ao_project_team` command just reads `COORDINATOR.md`. There's no activation hook. The skill → script → marker → role_guard chain has a gap at the skill layer.

**For testing:** We DON'T need the skill to call the script. We need:
- A test that creates a session marker directly (like `test_framework.py` already does via `fw_env.create_session_marker`)
- A test that the script creates a valid marker when invoked
- A test that role_guard.py reads it correctly (already tested in test_framework.py §9-§11, §23-§25)

**Recommendation:** Create `setup_ao_mode.sh` and `teardown_ao_mode.sh` with tests. The script is simple. The test is: run it, verify marker exists with correct JSON. Don't try to test the full skill→script→marker chain in this PR — that requires claudechic integration.

---

## NEW RISK 7: rules.yaml Has No Role-Gated Rules for Real Project Roles

**Status: CONFIRMED. rules.yaml has 3 rules (R01-R03), all universal. Zero role-gated.**

The current `rules.yaml`:
- R01: pytest output redirect (universal, deny)
- R02: pip install block (universal, deny)
- R03: conda install block (universal, deny)

None of these have `allow:` or `block:` fields. No real project roles (Implementer, Skeptic, Coordinator, etc.) appear anywhere in rules.yaml.

Meanwhile, `rules.yaml.example` has extensive role-gated synthetic rules (FW09-FW11, FW23) using `block: [Coordinator]`, `block: [Subagent]`, `allow: [SpecialRole]`, `block: [TeamAgent]`. These exercise the framework perfectly — but with synthetic roles, not real ones.

**What roles exist:** 17 role files in `AI_agents/project_team/`: COORDINATOR, IMPLEMENTER, SKEPTIC, TEST_ENGINEER, RESEARCHER, UI_DESIGNER, USER_ALIGNMENT, COMPOSABILITY, GIT_SETUP, LAB_NOTEBOOK, MEMORY_LAYOUT, PROJECT_INTEGRATOR, PROJECT_TYPES, SYNC_COORDINATOR, TERMINOLOGY_GUARDIAN, BINARY_PORTABILITY.

**What restrictions make sense?** This requires domain knowledge. Examples:
- `block: [Skeptic]` on Write/Edit of production code (Skeptic reviews, doesn't write)
- `block: [Subagent]` on modifying `rules.yaml` itself (only Coordinator)
- `allow: [Implementer, TestEngineer]` on creating new files (restrict other roles)
- `block: [Subagent]` on `git push` (only Coordinator pushes)

**The risk:** Inventing role restrictions without user input creates rules nobody asked for that may actively hinder workflows.

**Recommendation:** The spec should define 2-3 concrete role-gated rules as **exemplars**, not a complete policy. Enough to prove the chain works end-to-end with real role names. The user can then add more rules following the pattern. Suggested exemplars:
1. `block: [Subagent]` on editing `rules.yaml` or `settings.json` (protect the guardrail config)
2. `block: [Subagent]` on `git push` (Coordinator-only operation)
3. `allow: [Implementer, TestEngineer]` on some write operation (prove allowlist with real roles)

---

## NEW RISK 8: How to Test Multi-Agent Role Enforcement Without Claude Code

**Status: SOLVED. test_framework.py already shows the pattern.**

The `test_framework.py` file has 35 tests that prove role enforcement works using **subprocess + env vars**. The pattern is:

1. Generate hooks from rules.yaml into temp dir
2. Create session marker (JSON file) to activate team mode
3. Set env vars: `CLAUDE_AGENT_NAME`, `CLAUDE_AGENT_ROLE`, `AGENT_SESSION_PID`
4. Pipe tool input JSON to hook script via subprocess
5. Assert exit code (0 = allow, 2 = block) and stderr output

This is the **correct** testing pattern. It tests the real hook scripts as real subprocesses with real env vars. It does NOT require Claude Code, the TUI, or the SDK.

**What's missing for the expanded scope:**
- test_framework.py uses **synthetic** rules from `rules.yaml.example`. New tests need to use **real** rules from `rules.yaml`.
- test_framework.py lives in `.claude/guardrails/` (framework tests). New tests should live in `tests/` (project tests).
- The `fw_env` fixture creates hooks from `rules.yaml.example`. We need a similar fixture that creates hooks from the real `rules.yaml` and runs them against real project role names.

**The test structure should be:**

```python
# tests/test_role_enforcement.py

class TestImplementerCanWrite:
    """Implementer role is allowed to write production code."""
    def test_implementer_allowed(self, project_env):
        result = run_hook(
            project_env.write_guard,
            {"tool_input": {"file_path": "src/app.py"}, "cwd": "/project"},
            agent_name="Impl1",
            agent_role="Implementer",
            app_pid="99999",
        )
        assert result.returncode == 0

class TestSubagentCannotPush:
    """Subagents cannot git push."""
    def test_subagent_blocked(self, project_env):
        project_env.create_session_marker("CoordAgent")
        result = run_hook(
            project_env.bash_guard,
            {"tool_input": {"command": "git push origin main"}},
            agent_name="Worker1",
            agent_role="Skeptic",
            app_pid="99999",
        )
        assert result.returncode == 2
```

**Recommendation:** Mirror the `fw_env` pattern from test_framework.py but use real rules.yaml. This is straightforward — the infrastructure exists.

---

## NEW RISK 9: Should Intent Tests Duplicate test_framework.py's 35 Tests?

**Status: NO. Clear separation exists.**

| Layer | File | Tests | Purpose |
|-------|------|-------|---------|
| Framework | `.claude/guardrails/test_framework.py` | 35 | Proves generate_hooks.py + role_guard.py mechanisms work. Uses synthetic rules (FW01-FW23). Tests every pattern type, every enforcement level, every role group. |
| Project | `tests/test_copier_generation.py` | ~15 | Proves copier generates correct files and guardrail scripts work. |
| **NEW: Intent** | `tests/test_role_enforcement.py` | ~10-15 | Proves the full chain with REAL rules and REAL roles. |

**The intent tests should NOT duplicate framework mechanism testing.** Framework tests already prove that `block: [Coordinator]` works with any role name. Intent tests should prove that the SPECIFIC rules in `rules.yaml` enforce the SPECIFIC restrictions the user wants.

**What intent tests add that framework tests don't:**
1. Tests that real rules.yaml rules fire correctly (not synthetic FW rules)
2. Tests that real project role names (Implementer, Skeptic, etc.) match correctly
3. Tests that the full chain works: copier → generate_hooks → settings.json → hook scripts → role enforcement
4. Tests that setup_ao_mode.sh creates valid session markers

**What to NOT test again:**
- regex_match/regex_miss mechanisms (FW01-FW08 cover this)
- Role groups (Agent, TeamAgent, Subagent) (FW09-FW11, FW23 cover this)
- Ack token flow (FW13, FW17 cover this)
- hits.jsonl logging (FW19-FW20 cover this)
- Disabled rules (FW21 covers this)
- Deny > warn priority (FW18 covers this)

---

## UPDATED SUMMARY

| # | Risk | Severity | Action |
|---|------|----------|--------|
| 1 | TUI test infra | Solved | No action |
| 2 | Copier cross-platform | Low | No action |
| 3 | settings.json wiring | **Critical** | Create file + register ALL triggers |
| 4 | Testing wrong layer | Medium | Focus on settings.json lifecycle |
| 5 | generate_hooks.py bootstrap | **Critical** | Same fix as #3 |
| 6 | setup_ao_mode.sh missing | **High** | Create script + test. ~30 lines bash. |
| 7 | No real role-gated rules | **High** | Add 2-3 exemplar rules with real roles. Don't invent policy. |
| 8 | Testing multi-agent without Claude Code | Solved | Use test_framework.py's subprocess+env pattern |
| 9 | Duplicating framework tests | Solved | Don't. Test real rules with real roles only. |

## WHAT THE SPEC MUST DELIVER

### Tests (Red phase — all should FAIL today)

1. **`test_settings_json_created`** — `generate_hooks.py` on fresh project → settings.json exists with ALL hook entries (hardcoded + MCP)
2. **`test_settings_json_merge`** — Pre-populate settings.json with user content → run generate_hooks → user content preserved, hooks added
3. **`test_setup_ao_mode_creates_marker`** — Run setup_ao_mode.sh → session marker exists with correct JSON
4. **`test_setup_ao_mode_rejects_double_activation`** — Run setup_ao_mode.sh twice → second call fails
5. **`test_teardown_ao_mode_removes_marker`** — Run teardown_ao_mode.sh → marker deleted
6. **`test_real_role_blocked`** — Real rules.yaml rule with `block: [Subagent]` → Subagent blocked, Coordinator allowed
7. **`test_real_role_allowed`** — Real rules.yaml rule with `allow: [Implementer]` → Implementer allowed, others blocked
8. **`test_full_chain`** — copier generates project → generate_hooks creates hooks + settings.json → session marker created → hook fires with real role → correct enforcement

### Code (Green phase — make tests pass)

1. **`generate_hooks.py`:** Create settings.json if absent; register ALL triggers (hardcoded + MCP)
2. **`setup_ao_mode.sh`:** Write session marker, reject double activation, clean stale markers
3. **`teardown_ao_mode.sh`:** Delete session marker
4. **`rules.yaml`:** Add 2-3 role-gated exemplar rules with real project role names

### What NOT to Build

- A complete role policy for all 17 roles (that's the user's job)
- TUI tests for guardrail rendering (wrong layer)
- Duplicates of test_framework.py's mechanism tests
- A settings.json template file in copier (generate_hooks.py should handle creation — single source of truth)
