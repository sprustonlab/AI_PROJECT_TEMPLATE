# Fresh Terminology Review v2 — Final Architecture Audit

> **Reviewer:** TerminologyGuardian
> **Date:** 2026-04-04
> **Scope:** All 25 files in `specification/`
> **Canonical model:** 2 primitives (Check + Phase). Phase has 3 facets (guards, gates, context). "Phase" is canonical. "Step" = sub-phase. Session markers ≠ phase state.
> **Source of truth:** `unified_phase_model.md` + `terminology_phase_unification.md`

---

## Executive Summary

The converged model (Check + Phase) is cleanly defined in 2 files (`unified_phase_model.md`, `terminology_phase_unification.md`). But the other 23 files still use the OLD terminology. The codebase has **three geological layers of terminology** stacked on top of each other, all coexisting:

| Layer | Era | Key Terms | Files Using It |
|---|---|---|---|
| **Layer 1: Tutorial-specific** | Original spec (Apr 3) | Tutorial Step, Tutorial Mode, Tutorial Guardrail, Verification, VerificationResult, TutorialContext | 11 files (axis_*.md, composability.md, skeptic_*.md, terminology.md, user_alignment.md, fresh_*.md) |
| **Layer 2: Infrastructure split** | Infrastructure reframe (Apr 4 AM) | Step, Scoped Mode, Scoped Guardrail, ModeContext, ProgressStore, Check, CheckResult | 3 files (terminology_infrastructure_update.md, infrastructure_vs_tutorial.md, skeptic_infrastructure_review.md) |
| **Layer 3: Phase unification** | Phase model (Apr 4 PM) | Phase, Phase transition, Phase-scoped guardrail, ActivePhase, PhaseActive, Check, CheckResult, Workflow | 2 files (unified_phase_model.md, terminology_phase_unification.md) |

**The problem: no file has been updated to use Layer 3 terms. The canonical model exists only in 2 documents. Everything else is stale.**

---

## 1. Stale "Tutorial Step" — Should Be "Phase"

**44 occurrences across 13 files.** Every one should either be "phase" (infrastructure context) or "tutorial phase" (domain-specific context).

### Files with highest stale counts:

| File | Count | Impact |
|---|---|---|
| `terminology.md` | 6 | **CRITICAL** — the canonical terminology file still defines "Tutorial Step" as a primary term, with "phase" banned |
| `terminology_phase_unification.md` | 8 | Acceptable — this file documents the transition FROM "step" TO "phase" |
| `fresh_terminology_review.md` | 6 | Review doc — references old terms while auditing them |
| `composability.md` | 5 | **HIGH** — axis definitions reference "step" as the verification-gated unit |
| `fresh_composability_review.md` | 4 | Review doc |
| `axis_guidance.md` | 2 | **HIGH** — code examples use `TutorialStep` types |
| `terminology_infrastructure_update.md` | 3 | Transition doc — proposed "Step" as interim, now superseded by "Phase" |

### Specific corrections needed:

**`terminology.md`** — This is the most critical file. It must be rewritten to:
- Remove "Tutorial Step" as a core term
- Remove the ban on "phase" (line 92)
- Add "Phase" as the canonical infrastructure term
- Demote "step" to sub-phase granularity (instructions within a phase)

**`composability.md`** — The `TutorialStep` dataclass (line 58-65) should become `Phase` with the structure from `unified_phase_model.md`. The Step Protocol should become the Phase Protocol.

**`axis_guidance.md`** — `TutorialStepActive`, `TutorialStepStuck`, `TutorialVerificationFailed` triggers should be `PhaseActive`, `PhaseStuck`, `PhaseCheckFailed`.

---

## 2. Stale "Verification" — Should Be "Check"

**254 occurrences of "Verification/VerificationResult/VerificationContext" across 21 files.** The unified model renames these to Check/CheckResult/CheckContext.

**Only 84 occurrences of "Check/CheckResult/CheckContext" exist**, and most are in the newer files (`unified_phase_model.md`: 25, `infrastructure_vs_tutorial.md`: 31).

### The rename map:

| Old Term | New Term | Occurrences (old) | Occurrences (new) |
|---|---|---|---|
| `Verification` (protocol) | `Check` | ~100+ | ~50 |
| `VerificationResult` | `CheckResult` | ~60 | ~15 |
| `VerificationContext` | `CheckContext` | ~30 | ~5 |
| `verify_current_step()` | `run_gate_checks()` or similar | ~5 | 0 |
| `VerificationFailed` (trigger) | `PhaseCheckFailed` | ~5 | ~3 |

### Files most impacted:

| File | "Verification*" count | Needs rename? |
|---|---|---|
| `axis_verification.md` | 54 | **YES** — the entire file uses old naming. Should be renamed to `axis_checks.md` or updated inline. |
| `fresh_composability_review.md` | 26 | Review doc — references old terms |
| `axis_guidance.md` | 21 | **YES** — code examples use `VerificationResult`, `TutorialVerificationFailed` |
| `research_prior_art.md` | 20 | Historical research — old terms are acceptable in the context of citing prior art |
| `composability.md` | 18 | **YES** — defines `Verification` protocol |
| `fresh_terminology_review.md` | 14 | Review doc |

### Important nuance:

The unified model (`unified_phase_model.md`) already consistently uses "Check" everywhere:
- `Check` protocol
- `CheckResult`
- `CheckContext`
- `advance_checks` (on Phase)
- `PhaseCheckFailed` (trigger)

So the new naming IS defined. It's just not propagated.

---

## 3. Stale "Tutorial Mode" / "Mode-*" — Should Be "Phase"

**66 occurrences of "tutorial mode" across 17 files.** The phase unification subsumes "mode" — a mode is just a phase (or set of active phases).

**31 occurrences of "mode-scope/mode-aware/mode-based" across 10 files.** These should be "phase-scoped" / "phase-aware" / "phase-based."

### The key insight from the unified model:

> "Modes don't exist separately from phases." — `terminology_phase_unification.md`

A "tutorial mode" is simply "the ssh-cluster workflow is active and we're in its 'generate-key' phase." There's no separate "mode" concept needed.

### Files with highest "tutorial mode" counts:

| File | Count | Notes |
|---|---|---|
| `skeptic_review.md` | 10 | References pre-unification design |
| `fresh_user_alignment_review.md` | 8 | References user's "new mode" language (acceptable — user's words) |
| `terminology.md` | 7 | **CRITICAL** — still defines "Tutorial Mode" as a core term |
| `existing_infrastructure_audit.md` | 7 | Audit doc — found "mode" is missing infrastructure |
| `user_alignment.md` | 6 | References user's words |

### What to preserve vs change:

- **User-facing language:** The user said "a new mode." In user-facing docs and alignment checks, "tutorial mode" is fine as a casual description of "a tutorial workflow is active." It doesn't need to map 1:1 to an infrastructure type.
- **Infrastructure terminology:** In specs that define types and protocols, "mode" should not appear as a concept. Only "phase" and "workflow" exist.
- **The `mode_scope` field proposed on rules.yaml:** Should become `phase_scope` (already done in `unified_phase_model.md` and `research_phase_state_mapping.md`).

---

## 4. Stale "Scoped Mode" — Should Be Eliminated

**6 occurrences across 2 files** (`terminology_infrastructure_update.md`, `terminology_phase_unification.md`). This was the Layer 2 term, proposed as an intermediate generalization. The phase unification eliminated it.

**Fix:** Already addressed in `terminology_phase_unification.md`. The term should not appear in any new documents. The 2 files that use it are transition documents that explain the evolution.

---

## 5. New Terms in the Unified Model — Completeness Check

The unified model (`unified_phase_model.md`) introduces these types. Are they all defined clearly?

| Term | Defined in `unified_phase_model.md`? | Also in `terminology_phase_unification.md`? | Canonical? |
|---|---|---|---|
| **Phase** (dataclass) | ✅ Line 57-101. Full frozen dataclass. | ✅ Defined as infrastructure primitive | Yes |
| **Workflow** (dataclass) | ✅ Line 105-119. Ordered sequence of phases. | ❌ NOT in terminology doc | **GAP** |
| **ActivePhase** (runtime state) | ✅ Line 127-140. Runtime snapshot. | ❌ NOT in terminology doc | **GAP** |
| **Check** (protocol) | ✅ Referenced but not re-defined (defers to axis_verification.md's Verification → Check rename) | ✅ Mentioned as infrastructure primitive | Partially |
| **CheckResult** | ✅ Referenced as `CheckResult` | ✅ Mentioned | Partially |
| **CheckContext** | ❌ Not mentioned in unified model (it says "the same `Check` protocol and `CheckContext`") | ❌ | **GAP** |
| **PhaseActive** (trigger) | ✅ Line 445-459. Full implementation. | ✅ Listed in rename table | Yes |
| **PhaseStuck** (trigger) | ✅ Referenced in generalization table | ✅ Listed in rename table | Yes |
| **PhaseCheckFailed** (trigger) | ✅ Referenced in generalization table | ✅ Listed in rename table | Yes |
| **ShowUntilPhaseComplete** (lifecycle) | ✅ Line 481-493. Full implementation. | ❌ NOT in terminology doc | **GAP** |
| **WorkflowEngine** | ✅ Line 216-234. Class with `try_advance()`. | ❌ NOT in terminology doc | **GAP** |
| **AdvanceResult** | ✅ Referenced in `try_advance()` return type | ❌ NOT in terminology doc | **GAP** |
| **HintDeclaration** | ✅ Referenced in Phase.hints type | ❌ Not defined anywhere | **GAP** |
| **active_phase.json** | ✅ Line 162-168. File format. | ❌ NOT in terminology doc | **GAP** — also note `research_phase_state_mapping.md` proposes `phase_state.json` (different name!) |

### Critical gap: `active_phase.json` vs `phase_state.json`

Two different file names for the phase state persistence file:

| File | Proposed Name | Location |
|---|---|---|
| `unified_phase_model.md` | `active_phase.json` | `.claude/guardrails/active_phase.json` |
| `research_phase_state_mapping.md` | `phase_state.json` | `.ao_project_team/<project>/phase_state.json` |

These are different files in different locations with different schemas! The research doc proposes a persistent, project-scoped file (like STATUS.md). The unified model proposes a guardrails-directory file for hook reading. Both may be needed (one for persistence, one for hook runtime), but the terminology should be explicit:

- **Phase state file** (`phase_state.json`) — persistent project-scoped state, cross-session
- **Phase scope marker** (`active_phase.json`) — runtime file read by guardrail hooks, written on phase transition

---

## 6. Contradictions Between Specs

### Contradiction 1: Session marker vs Phase state (RESOLVED)

`research_phase_state_mapping.md` explicitly states (line 147):
> "The session marker and phase state are orthogonal... Session marker = WHO has permissions right now (runtime, ephemeral). Phase state = WHAT stage the project is in (persistent, cross-session). Both are needed. They should not be merged."

`skeptic_unification_review.md` initially proposed extending the session marker with a phase field (line 53-54):
> `Session Marker (unified): {"coordinator": "AI_PROJECT_TEMPLATE", "phase": 4, "project": "tutorial_system"}`

But later converges on the separate-files approach (line 229-230).

**Status:** The research doc's recommendation won. But the skeptic doc still has the merged proposal in its text. Minor inconsistency — both docs exist and a reader could get confused.

### Contradiction 2: `Check` protocol location

| File | Proposed Location |
|---|---|
| `infrastructure_vs_tutorial.md` | `checks/` directory at template root |
| `unified_phase_model.md` | `checks/` directory at template root |
| `existing_infrastructure_audit.md` | `tutorials/_verification.py` (tutorial-specific) |

**Status:** The newer docs agree on `checks/` as a top-level infrastructure directory. The older audit doc still says `tutorials/_verification.py`. Resolved by chronology — newer wins.

### Contradiction 3: Number of primitives

| File | Primitives Proposed |
|---|---|
| `infrastructure_vs_tutorial.md` | **4** primitives: Check System, Workflow State, Scoped Guardrails, Scoped Hints |
| `unified_phase_model.md` | **2** primitives: Check + Phase (Phase absorbs workflow state, scoped guardrails, scoped hints) |
| `skeptic_infrastructure_review.md` | **2 justified** (verification + mode-aware scoping), 2 questionable (progress tracking, TutorialContext) |

**Status:** The unified model explicitly addresses this collapse (line 265-278). The 4→2 reduction is the whole point of the phase unification. But the infrastructure_vs_tutorial.md file still presents the 4-primitive model and the reader must know to look at unified_phase_model.md for the updated count.

### Contradiction 4: `Workflow` vs `Phase` as the primary type

`unified_phase_model.md` defines BOTH `Phase` and `Workflow`:
```python
class Phase:  # The state with guards + gates + context
class Workflow:  # An ordered sequence of phases
```

`terminology_phase_unification.md` says "Phase" is the primitive and proposes `PhaseContext`, `PhaseProgressStore`. There's no mention of `Workflow` as a named type.

**Question:** Is the organizing type `Workflow` (which contains phases) or `Phase` (which is the primitive)? The unified model uses both. The terminology doc only names Phase.

**Recommendation:** Both are needed. `Phase` is the primitive (the state with 3 facets). `Workflow` is the container (ordered sequence of phases). Add `Workflow` to the terminology as an infrastructure term.

---

## 7. Terms Still Using Old Layer 1 or Layer 2 That Must Be Updated

### Layer 1 → Layer 3 renames (tutorial-specific → phase model):

| Old Term (Layer 1) | New Term (Layer 3) | Files Still Using Old |
|---|---|---|
| `TutorialStep` | `Phase` | composability.md, axis_guidance.md, axis_content.md |
| `Tutorial Mode` | (workflow is active) | terminology.md, skeptic_review.md, user_alignment.md |
| `TutorialContext` | `ActivePhase` (on ProjectState) | axis_guidance.md |
| `TutorialProgressStore` | (subsumed by `ActivePhase` persistence) | axis_guidance.md |
| `TutorialStepActive` | `PhaseActive` | axis_guidance.md |
| `TutorialStepStuck` | `PhaseStuck` | axis_guidance.md |
| `TutorialVerificationFailed` | `PhaseCheckFailed` | axis_guidance.md |
| `ShowUntilStepComplete` | `ShowUntilPhaseComplete` | axis_guidance.md |
| `Verification` (protocol) | `Check` | axis_verification.md, composability.md, axis_content.md, axis_guidance.md |
| `VerificationResult` | `CheckResult` | axis_verification.md, composability.md, axis_guidance.md |
| `VerificationContext` | `CheckContext` | axis_verification.md |
| `Tutorial Guardrail` | `Phase-scoped guardrail` | terminology.md |
| `Checkpoint Guardrail` | `Phase transition gate` (or keep "checkpoint guardrail") | terminology.md, axis_verification.md |
| `Tutorial Manifest` | `Manifest` (or `Workflow manifest`) | terminology.md, axis_content.md |
| `Tutorial Registry` | `Registry` (v2) | terminology.md |
| `Tutorial Selector` | `Selector` (v2) | terminology.md |

### Layer 2 → Layer 3 renames (infrastructure → phase model):

| Old Term (Layer 2) | New Term (Layer 3) | Files Still Using Old |
|---|---|---|
| `Scoped Mode` | `Phase` (subsumed) | terminology_infrastructure_update.md |
| `Scoped Guardrail` | `Phase-scoped guardrail` | terminology_infrastructure_update.md |
| `ModeContext` | `ActivePhase` | terminology_infrastructure_update.md, terminology_phase_unification.md |
| `ProgressStore` | (subsumed by ActivePhase + phase_state.json) | terminology_infrastructure_update.md |
| `Step` (as the gated unit) | `Phase` | terminology_infrastructure_update.md |

---

## 8. "Step" Usage — Demotion Check

The unified model demotes "step" to sub-phase granularity (individual instructions within a phase). Let me check if any file uses "step" to mean the verification-gated unit (which should now be "phase"):

### Files where "step" means the gated unit (WRONG under new model):

- **`axis_content.md`** — Extensively uses "step" as the primary unit: `steps:` in YAML, `step-01-generate-key.md`, `StepConfig` schema. This entire file treats "step" as the verification-gated unit.
- **`axis_verification.md`** — Uses "step" for the unit being verified: "step completion," "verify_current_step()."
- **`axis_guidance.md`** — Uses "step" throughout: "step content," "step-active," "step-stuck."
- **`composability.md`** — `TutorialStep` dataclass is the Step Protocol.

### Files where "step" correctly means instructions (OK under new model):

- **`unified_phase_model.md`** — Doesn't use "step" for the gated unit; uses "phase." Uses "step" only in the old 4-primitive discussion.

### The YAML schema problem:

`axis_content.md` defines the YAML manifest with:
```yaml
steps:
  - id: generate-key
    file: step-01-generate-key.md
```

Under the new model, this should be:
```yaml
phases:
  - id: generate-key
    file: phase-01-generate-key.md
```

Or keep the user-facing YAML key as `steps` for simplicity (since tutorial authors think in "steps") while the infrastructure type is `Phase`. This is a UX decision:

**Option A:** YAML uses `phases:` — consistent with infrastructure terminology.
**Option B:** YAML uses `steps:` — friendlier for tutorial authors, with the understanding that "step" in YAML = "phase" in code.

**Recommendation:** Option B with explicit documentation. Content authors write `steps:` (familiar language). The engine treats each "step" as a `Phase` internally. The mapping is: YAML `steps[n]` → `Phase` object. Document this once in the content authoring guide.

---

## 9. Banned Synonyms — Updated Status

### Bans from terminology.md that need updating:

| Ban | Status Under Phase Model |
|---|---|
| "phase (for tutorial units) → tutorial step" | **REVERSED** — Phase is now canonical |
| "walkthrough → tutorial" | **STILL VALID** |
| "lesson → tutorial" | **STILL VALID** |
| "task (for a tutorial unit) → tutorial step" | **UPDATE** → "task (for a phase) → phase" |
| "verification/validation (for step gates) → checkpoint" | **UPDATE** → "verification → check" (the protocol); "checkpoint" remains OK for the gating concept |
| "safety rail → guardrail" | **STILL VALID** |
| "guide/guided mode → tutorial mode" | **UPDATE** → tutorial mode is casual language for "a tutorial workflow is active" |
| "prompt/nudge → hint" | **STILL VALID** |
| "tutorial agent team → tutorial-runner agent" | **STILL VALID** |
| "runner/executor → tutorial-runner agent" | **STILL VALID** |
| "multi-agent tutorial → agent-team tutorial" | **STILL VALID** |

### New bans from terminology_phase_unification.md:

| DO NOT USE | USE INSTEAD |
|---|---|
| scoped mode | phase |
| stage | phase |
| state (for workflow position) | phase |
| tutorial engine | step-sequence engine (v1) or tutorial system (v2) |
| workflow (for step sequences) | step sequence |

**Problem:** That last ban ("workflow → step sequence") now contradicts `unified_phase_model.md`, which defines `Workflow` as an explicit type (ordered sequence of phases). The ban was written before the unified model.

**Fix:** Remove the ban on "workflow." `Workflow` is now a defined infrastructure type. Ban "pipeline" or "flow" as synonyms for workflow if needed.

---

## 10. Newcomer Readability

A newcomer reading the specification directory encounters 25 files with three layers of terminology. They would need to read them in the correct order to understand the evolution. This is a significant barrier.

### Recommended reading order (for a newcomer):

1. `unified_phase_model.md` — THE canonical architecture (2 primitives, Phase + Check)
2. `terminology_phase_unification.md` — How we got here, canonical term definitions
3. `axis_verification.md` — Check protocol details (read with s/Verification/Check/g)
4. `axis_content.md` — Content authoring format (read with s/step/phase/g mentally)
5. `axis_guidance.md` — Hints integration (read with s/TutorialStep*/Phase*/g)

Everything else is historical context, reviews, or transition documents.

### Recommendation:

After the architecture phase, consolidate into a single `architecture.md` that uses ONLY Layer 3 terminology. Keep the historical files for reference but mark them as superseded.

---

## Summary: Issues by Priority

### Must Fix (before implementation)

| # | Issue | Type | Scope |
|---|---|---|---|
| 1 | `terminology.md` uses Layer 1 terms throughout, bans "phase" | Stale canonical doc | Rewrite entire file |
| 2 | 254 "Verification*" occurrences should be "Check*" in axis specs | Bulk rename | axis_verification.md (54), composability.md (18), axis_guidance.md (21), axis_content.md (9) |
| 3 | 44 "tutorial step" occurrences should be "phase" | Bulk rename | Same files as #2 |
| 4 | `Workflow` type not in any terminology doc | Missing term | Add to terminology |
| 5 | `active_phase.json` vs `phase_state.json` naming conflict | Contradiction | Reconcile — likely need both (runtime marker + persistent state) |
| 6 | "workflow" banned in terminology_phase_unification.md but defined as a type in unified_phase_model.md | Self-contradiction | Remove the ban |

### Should Fix (during architecture)

| # | Issue | Type | Scope |
|---|---|---|---|
| 7 | `axis_content.md` YAML uses `steps:` — decide if YAML key changes to `phases:` or stays | Design decision | One decision, propagate |
| 8 | `ActivePhase`, `WorkflowEngine`, `AdvanceResult`, `HintDeclaration`, `ShowUntilPhaseComplete` not in any terminology doc | Missing terms | Add to canonical terminology |
| 9 | 66 "tutorial mode" occurrences — decide which are user-facing language (OK) vs infrastructure terms (rename) | Selective fix | Case-by-case |
| 10 | 31 "mode-scope/mode-aware/mode-based" occurrences should be "phase-scope/phase-aware/phase-based" | Bulk rename | 10 files |
| 11 | 4→2 primitive contradiction between infrastructure_vs_tutorial.md and unified_phase_model.md | Historical inconsistency | Mark infrastructure_vs_tutorial.md as superseded |

### Acceptable (historical documents)

| # | Issue | Notes |
|---|---|---|
| 12 | Transition docs (terminology_infrastructure_update.md, terminology_phase_unification.md) contain all three layers | Expected — they document the evolution |
| 13 | Review docs (fresh_*.md, skeptic_*.md) use terms from their era | Expected — they reviewed the spec at that point in time |
| 14 | research_prior_art.md uses "Verification" | Correct — it's citing prior art terminology |

---

## Canonical Term Reference (Layer 3 — Final Model)

For quick reference, the complete list of canonical terms under the unified model:

### Infrastructure (v1)

| Term | Type | Definition |
|---|---|---|
| **Check** | Protocol | `check(ctx: CheckContext) → CheckResult`. Pure function asserting a system state property. |
| **CheckContext** | Frozen dataclass | Sandboxed read-only system access for running checks. |
| **CheckResult** | Frozen dataclass | Structured result: `passed`, `message`, `evidence`, `check_description`, `sub_results`. |
| **Phase** | Frozen dataclass | Named workflow state with 3 facets: guards (activate/deactivate rules), gates (advance checks), context (hints). |
| **Workflow** | Frozen dataclass | Ordered sequence of phases with an ID. |
| **ActivePhase** | Frozen dataclass | Runtime snapshot: which phase is current, when entered, what's completed, last check result. |
| **Phase transition** | Event | Moving from one phase to the next. Atomic: runs gate checks, swaps guardrails, swaps hints, updates state. |
| **Phase-scoped guardrail** | Rule attribute | A guardrail rule with `phase_scope` field — active only in specified phases. |
| **Phase state file** | JSON file | Persistent, project-scoped: `phase_state.json` in `.ao_project_team/<project>/`. |
| **Phase scope marker** | JSON file | Runtime, guardrails-directory: `active_phase.json` in `.claude/guardrails/`. Read by hooks. |
| **WorkflowEngine** | Class | Orchestrates phase transitions: runs gate checks, manages scope markers, persists state. |
| **PhaseActive** | TriggerCondition | Hint trigger: fires when a specific phase is active. |
| **PhaseStuck** | TriggerCondition | Hint trigger: fires when user has been in a phase too long. |
| **PhaseCheckFailed** | TriggerCondition | Hint trigger: fires when last gate check failed. |
| **ShowUntilPhaseComplete** | HintLifecycle | Show hint until phase's gates pass and phase advances. |

### Built-in Check Implementations

| Term | Description |
|---|---|
| **CommandOutputCheck** | Run command, match output against regex. |
| **FileExistsCheck** | Check file/directory exists. |
| **ConfigValueCheck** | Check config value matches pattern. (Note: Skeptic recommends merging into CommandOutputCheck.) |
| **ManualConfirm** | Ask user yes/no question. |
| **CompoundCheck** | AND/OR composition of sub-checks. (Note: Skeptic recommends deferring to v2.) |

### Tutorial-specific (v2)

| Term | Definition |
|---|---|
| **Tutorial** | Interactive teaching experience built on a Workflow of Phases. |
| **Tutorial content** | Markdown instructional material for each phase. |
| **Tutorial-runner agent** | Agent role that drives tutorial execution. |
| **Tutorial registry** | Index of available tutorials. |
| **Tutorial selector** | UI for choosing a tutorial. |
| **Agent-team tutorial** | Special tutorial where multi-agent work is the learning content. |
| **Tutorial hints** | Hint definitions scoped to tutorial phases. |

### Preserved from original (unchanged)

| Term | Status |
|---|---|
| **Checkpoint** | Still valid as a casual name for a phase's gate checks. |
| **Hint** | Unchanged — existing system. |
| **Guardrail** | Unchanged — existing system. Phase adds scoping, not renaming. |
| **Manifest** | Still valid — the YAML file declaring a workflow's phases. |
