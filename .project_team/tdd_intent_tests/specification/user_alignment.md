# User Alignment Check — TDD Intent Tests (Revised)

## ⚠️ REVISION NOTE
Initial alignment check was **too narrow**. User rejected it. This revision captures the FULL scope of user intent, including team project activation and role-gated guardrails.

---

## Original Request Summary

The user has four explicit requirements:

1. **TDD (Red → Green):** "Write failing tests FIRST, then fix the code to make them pass."
2. **Intent-based tests using real copier + temp dirs:** "I want intent-based tests that use a TUI and the copier into a temp location and run through the features."
3. **Guardrail wiring into settings.json:** "The guardrail system is not firing as there is no wiring into the settings.json, this is with 'all tests passing'!"
4. **Settings merge, not overwrite:** "We also need to know how to change settings.json when it is already there and has values — must merge, not overwrite."

**Key frustration:** *"all tests pass" but features don't work* — "I found many promised things in the specs but not in the code." Tests validate components in isolation but never prove the system works end-to-end.

**What "features don't work" actually means (verified):** The entire guardrail-to-team-activation chain is broken at multiple points. It's not just settings.json — the whole pipeline from rules → hooks → team mode → role enforcement has missing links.

---

## Alignment Status: ⚠️ INITIAL VISION WAS TOO NARROW — NOW CORRECTED

The initial vision focused only on settings.json wiring and merge. But the user said **"I found many promised things in the specs but not in the code"** and **"run through the features"** — this means testing the FULL chain, not just one link.

---

## The Full Broken Chain (Verified in Codebase)

The guardrail system promises this pipeline:

```
rules.yaml → generate_hooks.py → hook scripts → settings.json wiring →
team mode activation (setup_ao_mode.sh) → CLAUDE_AGENT_ROLE set →
role_guard.py checks role → hook blocks/allows based on role
```

**What's broken (verified):**

| Link | Status | Evidence |
|------|--------|----------|
| rules.yaml → generate_hooks.py | ✅ Works | `generate_hooks.py` reads rules.yaml and generates hook scripts |
| Hook scripts generated | ✅ Works | bash_guard.py, read_guard.py, etc. exist in `.claude/guardrails/hooks/` |
| **settings.json wiring** | ❌ BROKEN | No `.claude/settings.json` exists. `update_settings_json()` only handles MCP triggers and returns early if file missing |
| **setup_ao_mode.sh** | ❌ MISSING | Referenced in README.md, role_guard.py, specs — file does NOT exist anywhere |
| **teardown_ao_mode.sh** | ❌ MISSING | Same — referenced but never created |
| **Role-gated rules in real rules.yaml** | ❌ MISSING | Real `rules.yaml` has only universal rules (R01-R03). Role-gated rules (block/allow) exist ONLY in `rules.yaml.example` (FW09-FW11, FW20, FW23) |
| **Role enforcement in real project** | ❌ NEVER TESTED | `test_framework.py` tests role gating synthetically with FW rules. No test spawns a real agent with `CLAUDE_AGENT_ROLE=Implementer` in a copier-generated project |
| **Session markers** | ❌ NEVER CREATED | `role_guard.py` checks for `.claude/guardrails/sessions/ao_<PID>` but nothing creates them (setup_ao_mode.sh doesn't exist) |

---

## Requirement-by-Requirement Verification

### Requirement 1: TDD (Red → Green)
**User said:** "TDD: Write failing tests FIRST, then fix the code to make them pass. Red → Green."
**Vision says:** "Red → Green. No fixing until the test proves the failure."
**Status:** ✅ Faithfully captured. Non-negotiable process constraint.

### Requirement 2: Intent-Based Tests with Real Copier + Temp Dirs
**User said:** "I want intent-based tests that use a TUI and the copier into a temp location and run through the features."
**Status:** ✅ Captured, but scope was too narrow.

**"Run through the features" means the FULL chain**, not just "does settings.json exist." The user wants tests that prove:
- Copier generates a project → guardrails are included → `generate_hooks.py` runs → settings.json is created with hook entries → team mode can be activated → role-gated rules fire for the right roles → guardrails actually block forbidden actions

**"TUI"** — most likely means the claudechic TUI that spawns agents (setting CLAUDE_AGENT_ROLE). The user wants to test that the TUI → agent spawn → role enforcement chain works.

### Requirement 3: Guardrail Wiring into settings.json
**User said:** "The guardrail system is not firing as there is no wiring into the settings.json"
**Status:** ✅ Captured, but this is SYMPTOM, not root cause.

**The root cause is deeper:** Even if settings.json were wired, the guardrails would still not enforce roles because:
1. `setup_ao_mode.sh` doesn't exist → no session marker → `role_guard.py` treats everything as solo mode → role-gated rules silently pass
2. Real `rules.yaml` has NO role-gated rules → even with team mode, no role enforcement happens
3. No test exercises the chain: spawn agent → agent tries forbidden action → guardrail blocks

### Requirement 4: Settings Merge, Not Overwrite
**User said:** "We also need to know how to change settings.json when it is already there and has values — must merge, not overwrite."
**Status:** ✅ Captured correctly. Verified gap is real — no merge logic exists.

---

## Gaps Found

### ⚠️ GAP 1 (CRITICAL): setup_ao_mode.sh and teardown_ao_mode.sh Don't Exist
**Promised in:** README.md (lines 61, 63), role_guard.py (lines 28, 79-80), SPECIFICATION.md, composability.md, terminology.md
**Reality:** These files do not exist anywhere in the repository.
**Impact:** Without setup_ao_mode.sh, NO session marker is ever written → `role_guard.py`'s `is_team_mode()` always returns False → ALL role-gated rules silently pass → role enforcement is dead.
**This is the user's core frustration:** "The guardrail system is not firing" — it's not JUST settings.json, it's the entire team mode activation.

### ⚠️ GAP 2 (CRITICAL): No Role-Gated Rules in Production
**Promised in:** rules.yaml.example (FW09: block Coordinator, FW10: block Subagent, FW11: allow SpecialRole, FW20: log for Agent, FW23: block TeamAgent)
**Reality:** Real `rules.yaml` has only R01-R03, all universal (no `block:` or `allow:` fields). Role enforcement is demonstrated but never deployed.
**Impact:** Even if team mode worked, no rules would use it. The role system is a framework with no users.

### ⚠️ GAP 3: test_framework.py Tests Are Synthetic, Not Intent-Based
**What exists:** `test_framework.py` has comprehensive synthetic tests — copies `rules.yaml.example` into temp dirs, generates hooks, runs them with env vars. Tests pass.
**What's missing:** No test ever:
1. Runs copier to generate a real project
2. Runs `generate_hooks.py` in that project
3. Checks that settings.json is created with hook entries
4. Activates team mode (writes session marker)
5. Spawns a process with `CLAUDE_AGENT_ROLE=Implementer`
6. Verifies that role-gated rules fire/don't fire appropriately

**This IS the user's complaint:** "all tests pass" because `test_framework.py` works in isolation, but the real system is unwired.

### ❓ GAP 4: "TUI" Ambiguity (Minor)
**User said:** "use a TUI and the copier"
**Likely meaning:** The claudechic TUI that activates team mode and spawns agents. Tests should exercise the entry point that sets env vars and activates team mode — even if calling it programmatically rather than through the actual TUI.

---

## What Tests Must Prove (Red Phase)

Based on the FULL user intent, failing tests must prove:

### Chain 1: Settings.json Wiring
1. **RED:** `generate_hooks.py` does NOT create settings.json for core hooks (Bash/Read/Glob/Write)
2. **RED:** `generate_hooks.py` does NOT create settings.json at all when it doesn't exist
3. **RED:** Running generate_hooks.py twice duplicates/corrupts entries (idempotency)

### Chain 2: Settings Merge
4. **RED:** Given a pre-existing settings.json with `permissions`, `mcpServers`, custom keys → running generate_hooks.py destroys them
5. **RED:** Given existing hook entries → running generate_hooks.py duplicates them

### Chain 3: Team Mode Activation
6. **RED:** `setup_ao_mode.sh` does not exist → cannot activate team mode
7. **RED:** `teardown_ao_mode.sh` does not exist → cannot deactivate team mode
8. **RED:** No session marker is ever created → `role_guard.py` always returns solo mode

### Chain 4: Role-Gated Enforcement (End-to-End)
9. **RED:** In a copier-generated project with `use_guardrails=True`, role-gated rules don't exist in real rules.yaml
10. **RED:** Spawning an agent with `CLAUDE_AGENT_ROLE=Coordinator` → role-gated guardrail does NOT fire (because no wiring)
11. **RED:** The full chain (copier → generate_hooks → settings.json → team mode → role check) has never been exercised

---

## Interaction with Skeptic

All requirements are explicit user requests. The Skeptic:
- **MAY** simplify implementation approach (e.g., "setup_ao_mode.sh could be a Python function instead of a shell script")
- **MUST NOT** defer any of the four chains above
- **MUST NOT** say "role-gated rules aren't needed yet" — the user explicitly flagged that example rules with roles are never tested

---

## Recommendation

**The specification must cover ALL FOUR chains, not just settings.json.** Implementation priorities:

1. **Write failing tests** for each chain (RED) — proving the system is broken at each link
2. **Fix in order of dependency:**
   - First: `generate_hooks.py` creates+merges settings.json (Chain 1+2)
   - Second: Create `setup_ao_mode.sh`/`teardown_ao_mode.sh` or equivalent (Chain 3)
   - Third: Add real role-gated rules to production rules.yaml (Chain 4)
   - Fourth: End-to-end test proving the full chain works (Chain 4, test 11)
3. **Verify** all tests pass (GREEN)

**The user's mental model is:** "I have a guardrail framework with roles documented everywhere, but when I actually use the project, nothing fires." The fix must make the ENTIRE documented chain operational, not just one link.
