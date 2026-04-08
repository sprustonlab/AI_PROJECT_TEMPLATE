# UserAlignment — Phase 4 Test Review

## Tests Reviewed

1. `tests/test_intent_guardrail_wiring.py` — Chains 1+2 (settings wiring + merge)
2. `tests/test_intent_team_activation.py` — Chain 3 (team mode activation)
3. Chain 4 (role enforcement end-to-end) — **NOT YET WRITTEN**

---

## test_intent_guardrail_wiring.py — ✅ ALIGNED

### Coverage Map

| Required RED Test | Test Method | Status |
|-------------------|------------|--------|
| Chain 1.1: settings.json not created when absent | `test_generate_hooks_creates_settings_json_when_absent` | ✅ Covers it |
| Chain 1.2: core hooks excluded from registration | `test_all_generated_hooks_have_settings_entries` | ✅ Covers it |
| Chain 1.3: idempotency | `test_settings_merge_is_idempotent` | ✅ Covers it |
| Chain 2.1: merge preserves existing content | `test_settings_merge_preserves_existing_content` | ✅ Covers it |
| Chain 2.2: merge preserves existing hooks | `test_settings_merge_preserves_existing_content` (checks custom_tool entry) | ✅ Covers it |

### Quality Assessment

- ✅ **Uses real copier** — `copier_output` fixture generates a real project in a temp dir
- ✅ **Runs real generate_hooks.py** — subprocess execution, not mocking
- ✅ **Tests user-visible outcomes** — "does settings.json exist and have the right entries?"
- ✅ **Failure messages explain WHY** — each assertion message describes the broken chain link
- ✅ **Expected to fail today** — comments explain exactly why each test should be RED
- ✅ **No mocking** — tests exercise the real system

### No Issues Found

This file faithfully captures Chains 1+2 from my alignment spec.

---

## test_intent_team_activation.py — ✅ ALIGNED with minor notes

### Coverage Map

| Required RED Test | Test Method | Status |
|-------------------|------------|--------|
| Chain 3.1: setup_ao_mode.sh doesn't exist | `test_setup_ao_mode_creates_session_marker` (first assert) | ✅ Covers it |
| Chain 3.2: teardown_ao_mode.sh doesn't exist | `test_teardown_ao_mode_removes_marker` (first assert) | ✅ Covers it |
| Chain 3.3: double-activation rejected | `test_setup_ao_mode_rejects_double_activation` | ✅ Covers it |

### Quality Assessment

- ✅ **Uses real copier** — `copier_output` fixture
- ✅ **Tests existence of scripts first** — fails fast on the real problem (scripts don't exist)
- ✅ **Tests behavior after existence** — if scripts exist, verifies session marker creation/deletion
- ✅ **Tests safety** — double-activation must be rejected (matches README.md spec)
- ✅ **Uses env vars correctly** — sets CLAUDE_AGENT_NAME, CLAUDECHIC_APP_PID

### Minor Notes (not blockers)

1. **Session marker content**: Test asserts `{"coordinator": "Coordinator"}` — this is a reasonable expectation based on role_guard.py docs. ✅ Aligned.

2. **Missing: stale marker cleanup test** — README says "setup_ao_mode.sh stale-marker cleanup also removes markers for non-running PIDs." No test for this, but it's an implementation detail, not user intent. Not flagging as a gap.

3. **Missing: test that role_guard.py detects team mode via session marker** — this would bridge Chain 3 → Chain 4. Could be in this file or in the Chain 4 file. Not a problem if Chain 4 covers it.

---

## Chain 4 (role enforcement end-to-end) — ⚠️ NOT YET WRITTEN

This is the most critical chain for user intent. The user specifically said "there are example rules with roles that are also never tested, this needs the activation of the team project."

### What Chain 4 tests MUST cover:

1. **RED:** In a copier-generated project, real `rules.yaml` has no role-gated rules (only R01-R03)
2. **RED:** Given role-gated rules + team mode active + agent with CLAUDE_AGENT_ROLE → hook actually blocks the action
3. **RED:** Given role-gated rules + NO team mode → role-gated rules silently pass (proving team mode is required)
4. **RED:** Full chain: copier → generate_hooks → settings.json → team mode → role check → block/allow

### What "intent-based" means for Chain 4:

The tests should NOT just check "does the file contain the word 'block'" — they should:
- Run a hook script as a subprocess with CLAUDE_AGENT_ROLE set
- Feed it a JSON tool-use payload that should trigger a rule
- Verify the exit code is non-zero (blocked) or zero (allowed) based on the role
- This is what the user means by "run through the features" — exercise the actual enforcement, not just check file contents

---

## Overall Alignment Verdict

| File | Alignment | Notes |
|------|-----------|-------|
| test_intent_guardrail_wiring.py | ✅ ALIGNED | All Chain 1+2 RED tests covered |
| test_intent_team_activation.py | ✅ ALIGNED | All Chain 3 RED tests covered |
| Chain 4 test file | ⚠️ MISSING | Most critical for user intent — must test role enforcement end-to-end |

**Recommendation:** Chain 4 test file is the most important one. Without it, we've proven the plumbing is broken but haven't proven that role enforcement itself doesn't work in a real project. The user's specific complaint was "example rules with roles are also never tested" — Chain 4 tests are the direct answer to that complaint.
