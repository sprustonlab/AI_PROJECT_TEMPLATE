# Research Report: Phase-State Mapping — Existing Workflow vs Guardrails

**Requested by:** Coordinator
**Date:** 2026-04-04
**Tier of best source found:** T1 (Primary source code)

## Query

Map the concrete seams between the existing project team workflow phases (0-9) and the existing guardrail rules (R01-R05). Identify what should be phase-scoped, what drives phase transitions, how session markers relate to phase state, and what a phase-state file would look like.

---

## 1. Which Existing Guardrail Rules SHOULD Be Phase-Scoped?

### Current State: All Rules Are Always-On

Every rule in `rules.yaml` fires unconditionally (within its role scope). There is no phase awareness. Let me analyze each rule against the 9 workflow phases:

| Rule | Phase 0-1 (Vision/Setup) | Phase 2-3 (Spec) | Phase 4 (Impl) | Phase 5 (Testing) | Phase 6-9 (Ship) |
|------|--------------------------|-------------------|----------------|--------------------|--------------------|
| **R01: pytest-output-block** | Irrelevant (no code yet) | Irrelevant (no code yet) | **Correct** — test runs during impl should save output | **CONFLICT** — testing IS the phase; running pytest is the whole point | **Correct** — save output for audit |
| **R02: pip-install-block** | Irrelevant | Irrelevant | **Correct** — always use pixi | **Correct** — always use pixi | **Correct** — always use pixi |
| **R03: conda-install-block** | Irrelevant | Irrelevant | **Correct** — always use pixi | **Correct** — always use pixi | **Correct** — always use pixi |
| **R04: subagent-push-block** | N/A (no subagents) | **Correct** — only Coordinator pushes | **Correct** | **Correct** | **Correct** |
| **R05: subagent-guardrail-config** | N/A (no subagents) | **Correct** | **Correct** | **Correct** | **Correct** |

### Analysis

**R01 is the only rule with a clear phase-scoping need:**

- In **Phase 4 (Implementation)**, R01 is correct — Implementers running pytest should save output to `.test_runs/` so results are auditable.
- In **Phase 5 (Testing)**, R01 creates friction. TestEngineer's entire job is running pytest. The redirect-to-file requirement makes sense for full-suite runs but is hostile to the rapid red-green-refactor cycle where you run `pytest tests/test_foo.py` dozens of times. (Note: the current rule already exempts single-file runs via `exclude_if_matches`, which partially addresses this.)
- A phase-scoped variant could **relax** R01 during Phase 5 (e.g., downgrade from `deny` to `log`, or expand the exclusion pattern).

**R02 and R03 are phase-invariant** — you should never `pip install` or `conda install` regardless of phase. These are environment integrity rules, not workflow rules.

**R04 and R05 are role-scoped, not phase-scoped** — they fire based on who you are (Subagent vs Coordinator), not what phase you're in. This is correct. A Subagent should never push to remote regardless of phase.

### Verdict

| Rule | Phase-Scoping Needed? | Recommendation |
|------|----------------------|----------------|
| R01 | **Yes** (partial) | Phase 5: expand `exclude_if_matches` or downgrade to `warn`. Or: accept current behavior since single-file runs are already excluded. |
| R02 | No | Environment invariant — always deny |
| R03 | No | Environment invariant — always deny |
| R04 | No | Role invariant — always deny for Subagent |
| R05 | No | Role invariant — always deny for Subagent |

**Key insight:** The existing rules are mostly **environment invariants** and **role invariants**, not **phase-dependent**. Phase-scoping matters more for FUTURE rules — e.g., "during Phase 2-3, deny code changes to `src/`" or "during Phase 5, allow broader test execution." The current catalog is too small to demonstrate the pattern, but the infrastructure needs to support it for growth.

---

## 2. What Determines Phase Transitions Today?

### Current State: Pure Coordinator Judgment

Phase transitions are entirely driven by the Coordinator agent's interpretation of STATUS.md. There is **zero automated verification**. Here's the evidence:

| Transition | Trigger | Verification | Evidence |
|-----------|---------|--------------|----------|
| Phase 0 → 1 | User says "approved" | Coordinator interprets natural language | User Checkpoint 👤 |
| Phase 1 → 2 | STATUS.md + userprompt.md written | Coordinator checks files exist | Manual file check |
| Phase 2 → 3 | `list_agents` shows 4 Leadership agents | Coordinator runs `list_agents` | **Closest to automated** — but still Coordinator judgment |
| Phase 3 → 4 | "User Checkpoint 👤" — user approves spec | User says "approved" | Natural language |
| Phase 4 → 5 | "All Leadership approve" | Leadership agents `tell_agent` their approval | Coordinator interprets messages |
| Phase 5 → 6 | "All pass" (tests) | TestEngineer reports results | Agent-reported, unverified |
| Phase 6 → 7 | "All agents confirm READY" | Agents report readiness | Agent-reported, unverified |
| Phase 7 → 8 | Launch script works | Coordinator judgment | Manual |
| Phase 8 → 9 | User decision on E2E tests | User says yes/no | Natural language |

### Critical Gap: No Machine-Verifiable Phase Gates

The transition from Phase 4 → 5 is illustrative:

```
## Phase 4: Implementation
1. Spawn one Implementer agent per file, up to 6 implementer agents.
2. Inform Leadership about how many implementation agents have been started...
3. If Researcher is active → ask Researcher to find reference implementations...
4. Exit when all Leadership approve.
```

"Exit when all Leadership approve" is a **social protocol**, not a machine-checkable condition. The Coordinator reads `tell_agent` messages and decides. There's no: "run this command and check the exit code."

Similarly, Phase 5 → 6: "Run tests. Fix failures. Exit when all pass." But "all pass" is determined by the TestEngineer *claiming* tests pass, not by the system independently verifying `pytest` exit code = 0.

### What Phase Transitions COULD Look Like (with verification)

| Transition | Machine-Verifiable Check |
|-----------|--------------------------|
| Phase 2 → 3 | `list_agents` output contains all 4 Leadership names (parseable) |
| Phase 3 → 4 | All `specification/*.md` files exist AND user approval recorded |
| Phase 4 → 5 | All files listed in implementation plan exist AND Leadership approval messages logged |
| Phase 5 → 6 | `pytest` exit code = 0 AND test output saved to `.test_runs/` |
| Phase 6 → 7 | All agents reported READY (logged, parseable) |
| Phase 7 → 8 | Launch script exits 0 |

These are exactly the same patterns as tutorial step verification: **command-output-check**, **file-exists-check**, **compound checks**. The verification protocol designed for tutorials is directly applicable to phase gates.

---

## 3. How Does the Session Marker Pattern Relate to Phase State?

### Current Session Marker

**File:** `.claude/guardrails/sessions/ao_<PID>`
**Content:** `{"coordinator": "<CoordinatorName>"}`
**Created by:** `setup_ao_mode.sh`
**Deleted by:** `teardown_ao_mode.sh`
**Read by:** `role_guard.py::get_my_role()`

### What It Tracks

The session marker tracks exactly ONE thing: **"Is team mode active, and who is the Coordinator?"**

It does NOT track:
- Which project is active (could be any of 5 `.ao_project_team/` projects)
- Current phase
- Which agents are spawned
- Phase transition history

### Why It's Intentionally Minimal

The session marker is scoped to a **PID** (process lifetime). When ClaudeChic exits, the marker becomes stale. Next session gets a new PID, new marker. This is correct for its purpose: role-based permission checks only need to know "is this a team session right now?"

Phase state is a different concern — it persists across sessions. A project that's in Phase 4 stays in Phase 4 whether the Coordinator is running or not. This is why phase state belongs in STATUS.md (persistent, project-scoped), not in the session marker (ephemeral, PID-scoped).

### Relationship Diagram

```
Session Marker (ephemeral, PID-scoped)
  └── Answers: "Is team mode active? Who is Coordinator?"
  └── Read by: role_guard.py → check_role()
  └── Lifetime: single ClaudeChic process

STATUS.md (persistent, project-scoped)
  └── Answers: "What phase is this project in? What's been done?"
  └── Read by: Coordinator agent (manually, every turn)
  └── Lifetime: project duration (across many sessions)

Phase State File (PROPOSED — persistent, project-scoped, machine-readable)
  └── Answers: "What phase? What's verified? What's pending?"
  └── Read by: guardrails (phase-scoped rules), verification engine, hints (phase-aware)
  └── Lifetime: project duration (across many sessions)
```

**The session marker and phase state are orthogonal:**
- Session marker = WHO has permissions right now (runtime, ephemeral)
- Phase state = WHAT stage the project is in (persistent, cross-session)

Both are needed. They should not be merged.

---

## 4. What Would a Phase-State File Look Like?

### Design Constraints

1. **Machine-readable** — guardrails hooks must parse it in <10ms (they run on every tool invocation)
2. **Human-readable** — Coordinator and developers should be able to inspect it
3. **Persistent** — survives session restarts
4. **Project-scoped** — lives in `.ao_project_team/<project>/`
5. **Atomic writes** — follow the `HintStateStore` pattern (temp + rename)
6. **Forward-compatible** — version field for future schema changes

### Proposed Schema: `phase_state.json`

**Location:** `.ao_project_team/<project>/phase_state.json`

```json
{
  "version": 1,
  "project_id": "tutorial_system",
  "current_phase": 3,
  "phase_label": "specification",
  "updated_at": "2026-04-04T10:30:00Z",
  "updated_by": "Coordinator",

  "phases_completed": {
    "0": {
      "completed_at": "2026-04-03T14:00:00Z",
      "evidence": "user_approved_vision"
    },
    "1": {
      "completed_at": "2026-04-03T14:05:00Z",
      "evidence": "status_md_created"
    },
    "2": {
      "completed_at": "2026-04-03T14:10:00Z",
      "evidence": "leadership_spawned",
      "verification": {
        "type": "agent_list_check",
        "expected": ["Composability", "TerminologyGuardian", "Skeptic", "UserAlignment"],
        "actual": ["Composability", "TerminologyGuardian", "Skeptic", "UserAlignment"],
        "passed": true
      }
    }
  },

  "active_rule_overrides": {
    "R01": {
      "enforcement_override": null,
      "reason": null
    }
  }
}
```

### How Each System Reads It

**Guardrails (hook runtime, <10ms budget):**
```python
# In generated hook (baked in at generation time):
# OR: read at runtime from known path (fast — single JSON parse)
import json
phase_state_path = Path('.ao_project_team') / project_id / 'phase_state.json'
if phase_state_path.exists():
    phase = json.loads(phase_state_path.read_text()).get('current_phase')
    # Apply phase-scoped rules
```

**Verification engine (tutorial or phase-gate):**
```python
# Read phase_state.json to determine what to verify next
# Write verification results back as evidence
```

**Hints pipeline (via extended ProjectState):**
```python
# ProjectState gains:
#   active_project_id: str | None
#   current_phase: int | None
# Tutorial/hint triggers can check: "if phase == 5, suggest testing hints"
```

### Alternative: Lean Version (Minimum Viable)

If the full schema is over-engineered for v1, the minimum viable phase state is:

```json
{
  "version": 1,
  "project_id": "tutorial_system",
  "current_phase": 3,
  "updated_at": "2026-04-04T10:30:00Z"
}
```

Just 4 fields. Guardrails can read `current_phase` for scoping. Verification evidence and rule overrides can come in v2.

---

## 5. Concrete Seam Map: Workflow Phases × Guardrail Rules

### Current State (No Phase Awareness)

```
┌─────────────────────────────────┐
│         rules.yaml              │
│  R01-R05 (always active)        │
│  No phase field                 │
│  No mode field                  │
└───────────┬─────────────────────┘
            │
            ▼
┌─────────────────────────────────┐
│      generate_hooks.py          │
│  Bakes rules into hook scripts  │
│  No phase logic generated       │
└───────────┬─────────────────────┘
            │
            ▼
┌─────────────────────────────────┐
│    hooks/bash_guard.py          │
│    hooks/write_guard.py         │
│  Run on EVERY tool invocation   │
│  Check patterns + roles         │
│  No phase check                 │
└───────────┬─────────────────────┘
            │
            ▼
┌─────────────────────────────────┐
│      role_guard.py              │
│  Reads session marker           │
│  Resolves role + team mode      │
│  No phase awareness             │
└─────────────────────────────────┘
```

### Proposed State (Phase-Aware)

```
┌─────────────────────────────────┐
│         rules.yaml              │
│  R01-R05 + new rules            │
│  + phase_scope: [4, 5] field    │──────────┐
│  + mode_scope: [team, tutorial] │          │
└───────────┬─────────────────────┘          │
            │                                │
            ▼                                │
┌─────────────────────────────────┐          │
│      generate_hooks.py          │          │
│  Generates phase-check code     │          │
│  Reads phase_state.json path    │          │
└───────────┬─────────────────────┘          │
            │                                │
            ▼                                ▼
┌─────────────────────────────────┐  ┌──────────────────────┐
│    hooks/bash_guard.py          │  │  phase_state.json     │
│    hooks/write_guard.py         │  │  (persistent, per-    │
│  Pattern + role + PHASE check   │──│   project)            │
│  Reads phase_state.json at      │  │  current_phase: 3     │
│  runtime for phase-scoped rules │  │  project_id: "..."    │
└───────────┬─────────────────────┘  └──────────────────────┘
            │                                ▲
            ▼                                │
┌─────────────────────────────────┐          │
│      role_guard.py              │          │
│  + get_current_phase() helper   │──────────┘
│  Reads phase_state.json         │
│  Returns phase int or None      │
└─────────────────────────────────┘
```

### What Changes in Each Component

| Component | Change | Complexity |
|-----------|--------|------------|
| **rules.yaml schema** | Add optional `phase_scope: list[int]` and `mode_scope: list[str]` fields | Low |
| **generate_hooks.py** | Generate phase-check code for rules with `phase_scope`. Read `phase_state.json` at runtime (not baked in — phase is dynamic). | Medium |
| **role_guard.py** | Add `get_current_phase(project_id) -> int | None` helper. Reads `phase_state.json` from known path. | Low |
| **Generated hooks** | For phase-scoped rules: wrap pattern match in `if current_phase in [4, 5]:` check. | Low (generated code) |
| **Coordinator workflow** | Write/update `phase_state.json` at each phase transition. Trivial — Coordinator already updates STATUS.md. | Low |

### Performance Impact

Phase-scoped rules require reading `phase_state.json` at hook runtime. This adds one `Path.exists()` + one `json.loads()` call per hook invocation. Estimated cost: 0.5-2ms on local filesystem, 2-10ms on NFS. Within the <50ms hook budget.

**Optimization:** Cache the phase state in the hook process (hooks are short-lived Python scripts — no stale cache risk since each invocation is a fresh process). Or: only read `phase_state.json` if any rule in the hook has `phase_scope` set (skip I/O entirely for phase-invariant hooks).

---

## 6. The Shared Infrastructure: What Tutorials and Team Workflow Both Need

The analysis reveals that tutorials and the team workflow need the **same infrastructure primitive**: a machine-readable state file that enables phase/step-scoped behavior across systems.

| Need | Team Workflow | Tutorial System |
|------|--------------|-----------------|
| **State file** | `phase_state.json` (which phase?) | `tutorial_state.json` (which step?) |
| **Scoped rules** | `phase_scope: [4, 5]` | `mode_scope: ["tutorial"]` + step-level activation |
| **Verification** | Phase gate checks (pytest passes, files exist) | Step checkpoint checks (SSH works, git configured) |
| **Progression** | Phase 4 → 5 when all pass | Step 2 → 3 when verification passes |
| **State reader** | `get_current_phase()` in role_guard.py | `get_current_step()` in tutorial engine |
| **Hints scoping** | Phase-aware hints ("you're in testing, try pytest -v") | Step-aware hints (existing axis_guidance.md design) |

The infrastructure primitives are identical:
1. **A JSON state file** with `version`, `current_<thing>`, `updated_at`, `completed_<things>`
2. **A state reader** callable from hooks, hints, and the engine
3. **A scope field** on rules/hints that references the state
4. **A verification protocol** that checks real system state and reports pass/fail

Building these for tutorials automatically gives phase-scoping to the team workflow. This is the "v1 builds infrastructure, v2 builds features" insight.

---

## Summary

| Question | Answer |
|----------|--------|
| Which rules should be phase-scoped? | Only R01 has a marginal case (Phase 5 testing). Current rules are mostly environment/role invariants. Phase-scoping matters for FUTURE rules. |
| What drives phase transitions today? | Pure Coordinator judgment reading STATUS.md. Zero automated verification. |
| How do session markers relate to phase state? | Orthogonal. Session markers = ephemeral runtime permissions (WHO). Phase state = persistent project stage (WHAT). Don't merge them. |
| What would a phase-state file look like? | `phase_state.json` with `current_phase`, `project_id`, `phases_completed` (with optional verification evidence). Same pattern as `hints_state.json`. |
| What's the shared infrastructure? | Tutorials and team workflow need the same primitives: JSON state file, state reader, scope field on rules, verification protocol. Build once, use twice. |
