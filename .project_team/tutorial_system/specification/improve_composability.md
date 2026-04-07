# Composability Improvement Review

**Reviewer:** Composability (Lead Architect)
**Date:** 2026-04-04
**Target:** SPECIFICATION.md

---

## Overall Assessment

The specification is well-structured and the two-primitive decomposition (Check + Phase) is sound. The compositional law is clean: checks produce `CheckResult`, phases consume them, and `phase_state.json` is the single source of truth. However, there is over-specification for v1, dead weight in types, and some areas that will block implementation.

---

## 1. SIMPLIFY: Over-specified for v1

### 1a. Drop `_registry.py` — it's 3 lines of value

The check registry is a dict mapping 3 strings to 3 classes. For v1 with a closed registry, this doesn't need its own file or abstraction. Put it as a module-level constant in `_builtins.py`:

```python
# Bottom of _builtins.py
CHECK_REGISTRY = {
    "command-output-check": CommandOutputCheck,
    "file-exists-check": FileExistsCheck,
    "manual-confirm": ManualConfirm,
}
```

**Why:** A 15-line file for a 5-line dict is premature structure. The v2 extensibility decision (Open Decision 10.2) explicitly defers plugin systems. Don't build the scaffolding now.

### 1b. `workflow/_triggers.py` and `workflow/_lifecycle.py` are v2 leaking into v1

The file structure lists `_triggers.py` (PhaseStuck, PhaseCheckFailed) and `_lifecycle.py` (ShowUntilPhaseComplete). But:

- `ShowUntilPhaseComplete` is explicitly listed as **v2 scope** (Section 9)
- `PhaseStuck` and `PhaseCheckFailed` are only used in tutorial hint triggers, which the tutorial engine interprets from YAML — they don't need to be separate workflow-level modules

**Recommendation:** For v1, put `PhaseIs` in the hints system where it naturally belongs (it's a `TriggerCondition`). Tutorial-specific triggers (`phase-stuck`, `phase-check-failed`) belong in the tutorial engine, not the workflow primitive. Delete both files from v1 scope.

### 1c. The `workflow/` package has 5 files for ~125 lines

That's 25 lines per file average. Flatten to:

```
workflow/
  __init__.py
  _types.py      # PhaseMeta, ActivePhase (merged with state read/write)
  _engine.py     # WorkflowEngine
```

State persistence (`_state.py` at ~40 lines) is a `json.loads` + `json.dumps` — it's implementation detail of the engine, not a separate concern.

---

## 2. SIMPLIFY: Dead weight in type definitions

### 2a. `CheckResult.check_type` field is redundant

```python
@dataclass(frozen=True)
class CheckResult:
    passed: bool
    message: str
    evidence: str = ""
    check_type: str = ""     # ← this
```

The caller already knows which check they ran. `check_type` on the result is metadata that no consumer uses in the spec. No code path inspects `result.check_type` to decide anything. If you need it for logging, the check object itself carries that info.

**Recommendation:** Remove `check_type` from `CheckResult`. If needed later, add it then.

### 2b. `ActivePhase.last_check_result` is premature

```python
@dataclass(frozen=True)
class ActivePhase:
    workflow_id: str
    phase_id: str
    phase_entered_at: float
    completed_phases: frozenset[str]
    last_check_result: CheckResult | None  # ← this
```

This field appears in the type but is never used in any consumer. `phase_state.json` (Section 3.1) doesn't include it. `phase_guard.py` doesn't read it. Hints don't check it. It's a speculative field.

**Recommendation:** Remove from v1. The engine can track this internally if needed; it doesn't need to be persisted state.

### 2c. `completed_phases` as `frozenset` in `ActivePhase` vs. list in JSON

The type says `frozenset[str]` but `phase_state.json` shows a JSON array. This creates a serialization seam that someone will get wrong. More importantly — for a linear phase sequence, `completed_phases` is redundant with the phase ordering in the manifest. You can derive it from `phase_id` + manifest order.

**Recommendation:** Either (a) drop `completed_phases` from v1 and derive it, or (b) keep it but document the serialization clearly. Option (a) is simpler.

---

## 3. UNDER-SPECIFIED: Will block implementation

### 3a. WorkflowEngine interface is completely unspecified

The spec describes `_engine.py` as "WorkflowEngine (transitions, gate evaluation)" but never defines its interface. Questions that will block implementers:

- How does the engine get instantiated? (manifest path? project root?)
- How does the agent trigger a phase advance? (method call? slash command?)
- Does the engine run as a persistent process, or is it invoked per-action?
- How does the engine deliver the phase markdown to the agent prompt?

**This is the most critical gap.** The spec precisely defines the data types but says nothing about the control flow. Add a `WorkflowEngine` protocol or at minimum a sequence diagram showing: agent action → engine check → transition → state write → prompt update.

### 3b. How does `/check-setup` actually work?

The spec says it's a standalone use of checks (~90 lines) and lists it as an open decision (slash command vs. CLI script). But the bigger question is: where do the check definitions for `/check-setup` live? Are they hardcoded? In a YAML file? Per-project?

**Recommendation:** Decide and specify. A simple answer: `check-setup.yaml` in project root listing checks to run.

### 3c. Tutorial engine vs. WorkflowEngine — same or different?

Section 6 shows `workflow/_engine.py` (WorkflowEngine) and Section 8.3 lists "Tutorial engine" as implementation step 5. Are these the same engine consuming different manifests (`phases.yaml` vs `tutorial.yaml`)? Or is the tutorial engine a separate thing?

The YAML schemas look identical. If they're the same engine, say so explicitly. If different, explain why.

**My read:** They should be the same engine. A workflow is a manifest + markdown files. The tutorial is just a workflow. This is the whole point of "v1 is infrastructure."

### 3d. `phase_entered_at` — who sets it and when is it read?

This timestamp appears in `ActivePhase` and is presumably used by `PhaseStuck` triggers (`threshold_seconds: 120`). But `PhaseStuck` is a tutorial-specific trigger, and the spec doesn't show how it's evaluated. Does the hints pipeline compare `time.time() - phase_entered_at`? Where?

---

## 4. UNNECESSARY ABSTRACTIONS

### 4a. `HintDeclaration` and `CheckDeclaration` — mentioned but never defined

`PhaseMeta` references `tuple[CheckDeclaration, ...]` and `tuple[HintDeclaration, ...]` but these types are never defined anywhere in the spec. Are they just dicts parsed from YAML? Typed dataclasses? This is an abstraction that's named but empty.

**Recommendation:** Either define them or just use `dict[str, Any]` for v1 and let the manifest parser handle validation.

### 4b. The `workflows` section in `rules.yaml` adds coupling

Currently `rules.yaml` is self-contained: it defines rules. Adding a `workflows` section that lists manifest paths creates a dependency from the guardrail system to the workflow system. Now `generate_hooks.py` must parse two different YAML schemas.

**Alternative:** Have `generate_hooks.py` discover manifests by convention (glob `**/phases.yaml` + `**/tutorial.yaml`) rather than requiring explicit listing. This removes the coupling and means adding a new tutorial doesn't require editing `rules.yaml`.

---

## 5. FLATTEN: File structure suggestions

### Current (15 new files across checks/ + workflow/)

```
checks/__init__.py, _types.py, _builtins.py, _registry.py
workflow/__init__.py, _types.py, _engine.py, _state.py, _triggers.py, _lifecycle.py
```

### Proposed (8 new files)

```
checks/__init__.py       # Re-exports
checks/_types.py         # CheckResult, CheckContext, Check protocol
checks/_builtins.py      # 3 built-in checks + CHECK_REGISTRY constant

workflow/__init__.py     # Re-exports
workflow/_types.py       # PhaseMeta, ActivePhase
workflow/_engine.py      # WorkflowEngine (includes state persistence)
```

That's 7 fewer files. Same functionality. Each file is meaningfully sized.

---

## 6. EXAMPLES: Too many, some redundant

Sections 7.1 through 7.5 provide 5 examples. Examples 7.2 (SSH), 7.3 (Pixi), and 7.5 (First Pytest) all demonstrate the same pattern: manifest YAML + rule scoping. The SSH and Pixi tutorials don't exist yet and won't in v1.

**Recommendation:** Keep 7.1 (project-team transition — shows the real workflow), 7.4 (standalone check — shows Check without Phase), and 7.5 (first-pytest — the actual v1 deliverable). Drop 7.2 and 7.3. Three examples, each demonstrating a distinct usage pattern.

---

## 7. MINOR ISSUES

### 7a. Directory rename scope is unclear

"`AI_agents` → `teams` throughout the codebase during implementation" — this is a massive refactor hiding in one sentence. How many files reference `AI_agents`? Is this really v1 scope or can it be deferred? If it stays, it should be a dedicated implementation step with its own risk assessment.

### 7b. `phase_state.json` location ambiguity

The spec says "project-scoped (one per project)" and discovery is via `PHASE_STATE_PATH` env var. But who sets this env var? The workflow engine? The project template? This needs a concrete answer or implementers will invent conflicting solutions.

### 7c. Appendix B reference implementations are good but should be labeled as illustrative

The `build_phase_registry` and `validate_phase_references` code in Appendix B reads as normative (implementers will copy-paste it). If that's intentional, say so. If it's illustrative, mark it clearly.

---

## Summary of Recommendations

| Priority | Action | Impact |
|---|---|---|
| **HIGH** | Specify WorkflowEngine interface and control flow | Unblocks implementation |
| **HIGH** | Clarify tutorial engine = workflow engine | Prevents duplicate code |
| **HIGH** | Define or drop `CheckDeclaration`/`HintDeclaration` types | Unblocks type implementation |
| **MEDIUM** | Remove `check_type` and `last_check_result` from types | Less dead weight |
| **MEDIUM** | Flatten workflow/ to 3 files, merge registry into builtins | Simpler structure |
| **MEDIUM** | Drop examples 7.2 and 7.3 | Shorter spec, less noise |
| **LOW** | Convention-based manifest discovery vs. `workflows` in rules.yaml | Less coupling |
| **LOW** | Assess `AI_agents` → `teams` rename scope | Risk clarity |
| **LOW** | Decide `completed_phases`: derive or persist | Cleaner state |
