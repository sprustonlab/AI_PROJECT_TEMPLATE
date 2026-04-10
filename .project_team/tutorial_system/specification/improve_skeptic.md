# Skeptic Improvement Review

**Reviewer:** Skeptic
**Document:** SPECIFICATION.md (Tutorial System Architecture)
**Date:** 2026-04-04

---

## Executive Summary

The spec is well-structured and the two-primitive decomposition (Check + Phase) is sound. But it's overbuilt for v1, the line counts are optimistic, and the riskiest assumption — that `generate_hooks.py` integration will go smoothly — is buried at step 4 instead of proven first. Several components solve problems we don't have yet.

---

## 1. What a senior engineer would cut before implementing

### Cut: The entire tutorial engine from v1

The spec says "v1 is infrastructure. v2 is tutorial." Then it includes a tutorial engine, tutorial YAML format, tutorial content, tutorial hints, and a tutorial-runner role file in v1 scope. That's not infrastructure — that's the first consumer pretending to be infrastructure.

**Proposal:** v1 delivers Check primitive, Phase primitive, phase-scoped guardrails, COORDINATOR.md split, and `/check-setup`. The "First Pytest tutorial" becomes v1.1 — built after the infrastructure proves itself with the project-team workflow (the existing, real consumer). This removes ~275 lines from scope and eliminates tutorial-specific YAML parsing, `tutorial.yaml` format design, hint trigger types (`phase-stuck`, `phase-check-failed`), and the tutorial-runner role file.

### Cut: Tutorial-specific hint triggers from v1

`PhaseStuck` (threshold_seconds) and `PhaseCheckFailed` are tutorial-only triggers. The project-team workflow uses `PhaseIs`, which is simple. The tutorial triggers require timer infrastructure and check-result-to-hint plumbing that doesn't exist yet.

**Proposal:** Ship `PhaseIs` trigger only in v1. Tutorial-specific triggers are v1.1/v2.

### Cut: `workflow/` directory rename `AI_agents` → `teams`

A codebase-wide directory rename is high-risk busywork that touches every import, every path reference, every agent config. It has zero architectural value — it's cosmetic.

**Proposal:** Keep `AI_agents/` for v1. Rename in a dedicated cleanup PR when the dust settles.

---

## 2. What's going to be harder than the spec claims

### `generate_hooks.py` integration (~150 lines changed) is the real project

The spec treats this as one step among six. In reality, `generate_hooks.py` is load-bearing infrastructure that generates shell hooks consumed by Claude's guardrail system. Modifying it to:
- Parse YAML manifests
- Build a phase registry
- Validate `phase_block`/`phase_allow` references
- Emit `phase_guard.py` calls in generated hooks
- Do all this without breaking existing R01-R05 guardrails

...is not "~150 lines changed." It's a careful refactor of the generation pipeline with regression risk on every existing guardrail. The spec's own risk table marks this HIGH probability. Budget 3-4 days, not 2.

### `phase_state.json` concurrency

The spec mentions "temp-then-rename vs. file lock" as unresolved. But the real issue: what happens when a guardrail hook reads `phase_state.json` while the workflow engine is mid-write? On a shared filesystem (this is HPC — `/groups/spruston/home/`), atomic rename semantics are not guaranteed on NFS. This needs an explicit answer.

**Proposal:** Use temp-then-rename AND add a read-retry with validation (JSON parse succeeds, required fields present). Document that NFS may deliver stale reads and that fail-open (no phase = rule fires normally) is acceptable.

### COORDINATOR.md split is content surgery, not file reorganization

Splitting a 275-line document into 30 lines of cross-phase content + 7 phase files requires deep understanding of what content is truly cross-phase vs. phase-specific. The "splitting rule" is good in principle ("if removing a section makes any phase file unable to stand alone, it stays") but this will require multiple iterations to get right.

**Proposal:** Do a dry-run split first (no code changes) and have the Coordinator agent validate that each phase file is self-contained. Budget a full review cycle.

---

## 3. Where the first implementation surprise will come from

### Phase ID namespace collision

The spec puts project-team phase IDs (`testing`) and tutorial phase IDs (`run-test`) in the same `phase_block`/`phase_allow` lists in `rules.yaml`. There's no namespace prefix. When a second tutorial arrives with a `testing` phase, R01's `phase_block: [testing, run-test]` will silently match the wrong workflow's phase.

The `workflow_id` field exists in `phase_state.json` and `ActivePhase` but `phase_block`/`phase_allow` in `rules.yaml` don't reference it. The `should_skip_rule()` function checks `current_phase in phase_block` without checking `workflow_id`.

**Proposal:** Either:
- (a) Require qualified phase IDs in rules.yaml: `phase_block: ["project-team:testing", "first-pytest:run-test"]`, or
- (b) Accept this limitation for v1 and document it: "v1 assumes no phase ID collision across workflows. v2 adds workflow-qualified IDs." Option (b) is fine IF we're honest about it.

### Hint registration/unregistration during phase transitions

The spec says "Unregister Phase A's hints, Register Phase B's hints" atomically. But the existing hints system (`HintStateStore`, `run_pipeline()`) isn't built for dynamic registration. Hints are statically defined in `hints.py`. The spec adds `PhaseIs` triggers that check current phase — which is fine and doesn't need registration/unregistration at all. But tutorial hints declared in `tutorial.yaml` DO need runtime registration.

This is two different hint systems pretending to be one. The project-team hints work via existing trigger conditions. Tutorial hints need a YAML-to-HintSpec loader and dynamic hint set management.

**Proposal:** Clarify that for v1 (project-team only), no hint registration/unregistration is needed — `PhaseIs` triggers handle it naturally. Tutorial hint loading is v1.1 scope.

---

## 4. Are the line counts honest?

| Category | Spec estimate | My estimate | Why |
|---|---|---|---|
| `checks/` | ~175 | ~200 | `CheckContext.run_command()` needs subprocess handling, timeout, error capture |
| `workflow/` | ~125 | ~180 | `_engine.py` is doing a LOT: manifest parsing, transition logic, state persistence, hint coordination |
| `phase_guard.py` | ~40 | ~40 | Agree — this is straightforward |
| `generate_hooks.py` changes | ~150 changed | ~250+ changed | YAML loading, registry building, validation, emitting new hook code, backward compat |
| `/check-setup` | ~90 | ~90 | Agree if it's a slash command |
| Tests | ~360 | ~500+ | Missing: integration tests for generate_hooks.py, end-to-end phase transition tests, NFS edge cases |
| **Total** | **~1,260** | **~1,500-1,700** | |

The estimates are 20-35% low. Not catastrophically wrong, but enough to blow a timeline.

---

## 5. What to build FIRST to prove the riskiest assumption

The riskiest assumption: **`generate_hooks.py` can be extended with phase awareness without breaking existing guardrails.**

The spec puts this at step 4. It should be step 1.

**Proposal — Spike first:**
1. Add `phase_block: [testing]` to R01 in `rules.yaml`
2. Modify `generate_hooks.py` to parse it and emit a `phase_guard.py` call
3. Create `phase_guard.py` with `should_skip_rule()`
4. Create a minimal `phase_state.json` by hand
5. Run the full existing guardrail test suite

If this works, the rest is straightforward. If this breaks, we know before investing in Check/Phase/COORDINATOR split.

The Check primitive is low-risk (independent, no dependencies). COORDINATOR.md split is medium-risk (content surgery). `generate_hooks.py` is HIGH risk. Prove the hard thing first.

---

## 6. Are we solving the right problem?

### Yes, mostly

The core problem is real: the project-team workflow has implicit phases baked into a monolithic COORDINATOR.md, guardrails can't scope to workflow state, and there's no reusable assertion mechanism. Check + Phase primitives address this.

### But we're over-engineering the tutorial story

The spec repeatedly says "tutorials are the first consumer, not the architecture" — then spends 40% of its examples on tutorials. The `tutorial.yaml` format, tutorial-specific hints, tutorial-runner role, and First Pytest tutorial are v2 work dressed in v1 clothes.

The actual first consumer is the project-team workflow. Build for it. Prove the primitives work. THEN design the tutorial layer.

### The `WorkflowEngine` class is premature

The spec lists `_engine.py` with a `WorkflowEngine` class. For v1, phase transitions are: read manifest, check gates, update JSON file. That's 3 functions, not a class. A class implies state management, lifecycle, error recovery — complexity that hides bugs (per my own role file).

**Proposal:** v1 uses stateless functions: `load_manifest()`, `check_gates()`, `advance_phase()`. If v2 needs a class, refactor then.

---

## 7. Specific improvements

### 7.1 `CheckContext.ask_user()` shouldn't exist

`CheckContext` is described as "read-only context bag" with system access helpers. Then it has `ask_user()` — an interactive side effect. This breaks the pure-assertion model of Check. `ManualConfirm` is the only consumer.

**Proposal:** `ManualConfirm.check()` receives `ask_user` as a separate callback, not via `CheckContext`. Or: `CheckContext` has an optional `user_input: str | None` field pre-populated by the caller.

### 7.2 `CommandOutputCheck` regex on piped output is fragile

```yaml
command: "pixi run pytest --tb=short 2>&1 | tail -1"
pattern: "passed"
```

This pipes stderr to stdout, takes the last line, and regex-matches "passed". If pytest output format changes, if there's a warning after the summary, if `tail` isn't available — this silently breaks.

**Proposal:** Use pytest's exit code (0 = all passed) as the primary signal. Regex on output is the fallback, not the default. Add a `CommandExitCodeCheck` type:

```yaml
- type: command-exit-code-check
  command: "pixi run pytest --tb=short"
  expected_code: 0
```

### 7.3 Missing: how does the agent trigger phase advance?

Section 10.2 lists "Phase advance trigger: Agent calls engine vs. engine polls" as unresolved. This is a core interaction — the agent needs to know HOW to say "I'm done with this phase." For the project-team workflow, this is the Coordinator saying "advance to testing." Without this, the spec is incomplete.

**Proposal:** Resolve this now. Simplest: a slash command `/advance-phase` that runs gate checks and updates `phase_state.json`. Or: the workflow engine exposes `advance_phase()` and the Coordinator calls it.

### 7.4 Environment variable `PHASE_STATE_PATH` — who sets it?

The spec says the workflow engine sets it. But who starts the workflow engine? If it's a slash command, environment variables don't persist across Claude sessions. If it's a hook, it runs in a subprocess.

**Proposal:** Use a well-known path relative to project root (e.g., `.claude/phase_state.json`) instead of an environment variable. Discovery by convention, not configuration.

---

## 8. Summary of proposed changes

| # | Change | Impact | Risk reduction |
|---|---|---|---|
| 1 | Spike `generate_hooks.py` + `phase_guard.py` first | Reorder implementation | Proves riskiest assumption early |
| 2 | Cut tutorial engine/content from v1 | -275 lines, -1 YAML format | Reduces scope to actual first consumer |
| 3 | Cut `AI_agents` → `teams` rename from v1 | -N files touched | Eliminates cosmetic churn |
| 4 | Cut tutorial-specific hint triggers from v1 | -2 trigger types | Reduces hint system changes |
| 5 | Use functions not WorkflowEngine class | Simpler `_engine.py` | Verifiable by reading |
| 6 | Add `CommandExitCodeCheck` | +1 check type | More robust gate checks |
| 7 | Resolve phase advance mechanism now | Fills spec gap | Unblocks implementation |
| 8 | Use well-known path not env var for phase state | Simpler discovery | Works across sessions |
| 9 | Address phase ID namespace collision | Add docs or qualified IDs | Prevents silent bugs |
| 10 | Adjust line estimates +25% | Honest timeline | No blown deadlines |
