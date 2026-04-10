# Unified Phase Model

**Reviewer:** Composability (Lead Architect)
**Prompt:** "What IS common between verification and guardrails? Mode_scope and state are the same thing."

---

## The Insight

The user's observation is that we've been treating two things as separate when they're projections of the same primitive:

- **Guardrails** ask: "Given where we are, what's **allowed**?"
- **Checks** ask: "Given where we are, what's **required** to advance?"
- **Hints** ask: "Given where we are, what **help** should we surface?"

All three are functions of the same input: **where we are**. "Where we are" is the phase. The phase is the shared primitive.

---

## What a Phase Actually Is

A phase is a **named state that determines constraints and requirements**.

Looking at the existing project team workflow in COORDINATOR.md:

```
Phase 3: Specification
  - Agents allowed: Leadership only. Implementers blocked.
  - To advance: All Leadership reports received. User approves spec.
  - Context: "We're designing, not building."

Phase 4: Implementation
  - Agents allowed: Implementers + Leadership. Full pytest blocked.
  - To advance: All implementation tasks complete. Leadership approves.
  - Context: "We're building. Don't run full test suite yet."

Phase 5: Testing
  - Agents allowed: TestEngineer + Leadership. Full pytest allowed.
  - To advance: All tests pass.
  - Context: "We're testing. No new features."
```

The phase determines three things simultaneously:
1. **Guards** — what's blocked, what's allowed
2. **Gates** — what must be true to advance
3. **Context** — what guidance is relevant

These aren't three separate systems reading from one state. They're three **facets** of a single concept: the phase.

---

## The Minimal Model

### Phase Definition

```python
@dataclass(frozen=True)
class Phase:
    """A named state in a workflow that determines constraints and requirements.

    A phase is the primitive that guardrails, checks, and hints all read from.
    It answers three questions simultaneously:
      1. What's allowed right now? (guards)
      2. What must be true to advance? (gates)
      3. What guidance is relevant? (context)
    """

    id: str
    """Unique identifier within the workflow (e.g., 'implementation', 'testing')."""

    description: str
    """Human-readable description of what this phase is about."""

    # --- Facet 1: Guards (what's allowed) ---

    activate_rules: tuple[str, ...] = ()
    """Rule IDs from rules.yaml to ACTIVATE during this phase.
    These rules are only enforced while this phase is current.
    Example: ('T-SSH-001',) — block SSH key deletion during SSH tutorial.
    """

    deactivate_rules: tuple[str, ...] = ()
    """Rule IDs from rules.yaml to SUSPEND during this phase.
    These rules are normally active but are exempted for this phase.
    Example: ('R02',) — allow pip install during a tutorial about pixi.
    """

    # --- Facet 2: Gates (what advances) ---

    advance_checks: tuple[Check, ...] = ()
    """Checks that must ALL pass before advancing to the next phase.
    Example: (FileExistsCheck('~/.ssh/id_ed25519'),)
    """

    # --- Facet 3: Context (what guidance is relevant) ---

    hints: tuple[HintDeclaration, ...] = ()
    """Hints to register in the hints pipeline during this phase.
    Automatically registered on phase entry, removed on phase exit.
    """
```

### Workflow Definition

```python
@dataclass(frozen=True)
class Workflow:
    """An ordered sequence of phases with a current position.

    A workflow is the thing that moves through phases.
    Tutorials are workflows. Project team sessions are workflows.
    Migrations are workflows. Onboarding is a workflow.
    """

    id: str
    """Unique identifier (e.g., 'ssh-cluster', 'project-team', 'v2-migration')."""

    phases: tuple[Phase, ...]
    """Ordered sequence of phases. First phase is the starting point."""
```

### Active Phase (Runtime State)

```python
@dataclass(frozen=True)
class ActivePhase:
    """Runtime snapshot: which phase is current in which workflow.

    This is the single piece of state that guards, gates, and context
    all read from. Persisted to disk. Restored on reconnect.

    This is the "where we are" that everything else is a function of.
    """

    workflow_id: str
    phase_id: str
    phase_entered_at: float          # Unix timestamp
    completed_phases: frozenset[str]  # Phase IDs already completed
    last_check_result: CheckResult | None  # Most recent gate check
```

That's it. Three types. Everything else is a projection.

---

## How Each System Reads from ActivePhase

### Guardrails: "What's allowed?"

The guardrail system needs to know: given the active phase, which rules are active and which are suspended?

```
ActivePhase.phase_id
    → look up Phase definition
    → Phase.activate_rules: enforce these rules
    → Phase.deactivate_rules: suspend these rules
```

**Implementation:** A scope marker file (already proposed) that the generated hooks read at runtime:

```json
// .claude/guardrails/active_phase.json
{
  "workflow_id": "project-team",
  "phase_id": "implementation",
  "activate_rules": ["R-NO-FULL-PYTEST"],
  "deactivate_rules": []
}
```

The hook reads this file. If a rule ID appears in `activate_rules`, it's enforced. If a rule appears in `deactivate_rules`, it's skipped. Rules not mentioned in either list follow their default (always-on or always-off per their definition).

This is the same pattern as `role_guard.py` reading session markers. A `phase_guard.py` reads phase markers.

```python
# In generated hooks, alongside existing role_guard check:
def check_phase(rule_id: str) -> tuple[bool, bool]:
    """Check if a rule should be activated or deactivated by current phase.

    Returns (should_activate, should_deactivate).
    Both False means: rule follows its default behavior.
    """
    phase_file = Path(guardrails_dir) / "active_phase.json"
    if not phase_file.exists():
        return False, False  # No active phase → all defaults

    try:
        phase = json.loads(phase_file.read_text())
    except (json.JSONDecodeError, OSError):
        return False, False  # Corrupt → fail-open

    if rule_id in phase.get("activate_rules", []):
        return True, False
    if rule_id in phase.get("deactivate_rules", []):
        return False, True

    return False, False
```

### Checks: "Can we advance?"

The workflow engine needs to know: have all gate checks for the current phase passed?

```
ActivePhase.phase_id
    → look up Phase definition
    → Phase.advance_checks: list of Check objects
    → Run each check → CheckResult
    → All passed? → Can advance
```

**Implementation:** The workflow engine (not the guardrail system) runs checks. It uses the same `Check` protocol and `CheckContext` from the axis_verification spec. The engine calls `advance()`, which runs all `phase.advance_checks` and either advances or returns the failed check results.

```python
class WorkflowEngine:
    def try_advance(self) -> AdvanceResult:
        """Attempt to advance to the next phase."""
        current = self._get_current_phase()
        ctx = self._build_check_context()

        results = [check.check(ctx) for check in current.advance_checks]
        failed = [r for r in results if not r.passed]

        if failed:
            return AdvanceResult(
                advanced=False,
                blocked_by=tuple(failed),
                message=f"Phase '{current.id}' has {len(failed)} unmet gate(s)",
            )

        # All gates passed → advance
        next_phase = self._next_phase()
        self._transition_to(next_phase)
        return AdvanceResult(advanced=True, new_phase=next_phase)
```

### Hints: "What guidance is relevant?"

The hints system needs to know: what context-specific hints should be active?

```
ActivePhase.phase_id
    → look up Phase definition
    → Phase.hints: list of hint declarations
    → Register in hints pipeline on phase entry
    → Unregister on phase exit
```

**Implementation:** On phase transition, the workflow engine:
1. Unregisters hints from the old phase
2. Registers hints for the new phase
3. Updates `ProjectState` with the new `ActivePhase`

The hints pipeline itself doesn't change. It still evaluates `HintSpec` objects. It just gets a different set of them when the phase changes.

---

## What This Collapses

The previous `infrastructure_vs_tutorial.md` proposed 4 separate infrastructure primitives:
1. Check System
2. Workflow State
3. Scoped Guardrails
4. Scoped Hints

The unified phase model collapses primitives 2, 3, and 4 into one:

| Previous | Unified Model | Status |
|---|---|---|
| Check System | **Check System** (unchanged) | Independent primitive — checks are a building block, not a phase facet |
| Workflow State | **Phase** (absorbed) | Workflow state = which phase is current |
| Scoped Guardrails | **Phase.guards** (absorbed) | Rule scoping = a facet of the active phase |
| Scoped Hints | **Phase.context** (absorbed) | Hint scoping = a facet of the active phase |

**Result: 2 primitives, not 4.**

1. **Check** — a rich assertion about system state (produces `CheckResult`)
2. **Phase** — a named state that determines guards + gates + context

Checks are the building block. Phases are the organizer. Checks don't know about phases. Phases reference checks as gate conditions.

---

## Concrete Examples

### Example 1: Project Team Phase 4 → Phase 5

```yaml
# workflow: project-team
phases:
  - id: implementation
    description: "Building the code. No full test suite yet."
    activate_rules:
      - R-BLOCK-FULL-PYTEST    # Don't run full suite during implementation
    deactivate_rules: []
    advance_checks:
      - type: manual-confirm
        question: "Are all implementation tasks complete?"
    hints:
      - message: "Remember to write test stubs alongside code"
        trigger: { type: phase-active }
        lifecycle: show-once

  - id: testing
    description: "Running tests. No new features."
    activate_rules:
      - R-BLOCK-NEW-FEATURES   # No new feature code during testing
    deactivate_rules:
      - R-BLOCK-FULL-PYTEST    # NOW we can run full pytest
    advance_checks:
      - type: command-output-check
        command: "pixi run pytest --tb=short 2>&1 | tail -1"
        pattern: "passed"
    hints:
      - message: "Use pytest -v for verbose output"
        trigger: { type: phase-active }
        lifecycle: show-once
```

### Example 2: Tutorial SSH Setup (step = phase)

```yaml
# workflow: ssh-cluster
phases:
  - id: generate-key
    description: "Generate an SSH key pair"
    activate_rules:
      - T-SSH-001              # Block rm -rf ~/.ssh
    deactivate_rules: []
    advance_checks:
      - type: file-exists-check
        path: "~/.ssh/id_ed25519"
    hints:
      - message: "Try: ssh-keygen -t ed25519 -C 'your_email@example.com'"
        trigger: { type: phase-stuck, threshold_seconds: 120 }
        lifecycle: show-until-phase-complete

  - id: copy-key
    description: "Copy public key to the cluster"
    activate_rules:
      - T-SSH-001
    deactivate_rules: []
    advance_checks:
      - type: command-output-check
        command: "ssh -o BatchMode=yes ${CLUSTER_HOST} echo ok 2>&1"
        pattern: "ok"
    hints:
      - message: "Try: ssh-copy-id ${CLUSTER_USER}@${CLUSTER_HOST}"
        trigger: { type: phase-check-failed }
        lifecycle: show-until-phase-complete
```

### Example 3: Pixi Tutorial (exempting a rule)

```yaml
# workflow: pixi-environments
phases:
  - id: why-not-pip
    description: "Understand why pip install causes problems"
    activate_rules: []
    deactivate_rules:
      - R02                    # Allow pip install to demonstrate the problem
    advance_checks:
      - type: manual-confirm
        question: "Do you understand why direct pip install causes environment drift?"
    hints:
      - message: "Try running 'pip install numpy' and see what happens"
        trigger: { type: phase-active }
        lifecycle: show-once

  - id: use-pixi-add
    description: "Install packages the right way with pixi"
    activate_rules: []
    deactivate_rules: []       # R02 back to normal — pip blocked again
    advance_checks:
      - type: command-output-check
        command: "pixi list"
        pattern: "numpy"
    hints: []
```

Notice: `deactivate_rules: [R02]` in the first phase, empty in the second. When the workflow engine transitions from `why-not-pip` to `use-pixi-add`, R02 automatically re-activates. The phase controls the scope lifecycle.

---

## The Phase Transition is the Key Event

Everything happens at phase transition:

```
Phase A (current) → Phase B (next)

On transition:
  1. Run Phase A's advance_checks → all must pass
  2. Deactivate Phase A's activate_rules → remove from scope marker
  3. Reactivate Phase A's deactivate_rules → add back to scope marker
  4. Activate Phase B's activate_rules → add to scope marker
  5. Deactivate Phase B's deactivate_rules → remove from scope marker
  6. Unregister Phase A's hints
  7. Register Phase B's hints
  8. Update ActivePhase state (new phase_id, reset phase_entered_at)
  9. Persist to disk
```

This is ONE atomic operation. Not three separate systems coordinating. The workflow engine does it all because it owns the phase state.

---

## What About the Check System?

Checks remain independent. They're a building block that phases reference but don't own.

```
Phase ──references──► Check
                       │
                       ▼
                    CheckResult
```

A `Check` doesn't know it's being used as a gate. It just checks system state and returns a result. This is correct — checks are useful outside of phases too:

- A hint trigger could use a `Check` to evaluate a condition
- An agent could run a `Check` to verify its own work
- CI could run a `Check` as a validation step

The `Check` protocol is genuinely independent infrastructure. The `Phase` uses checks as gate conditions, but checks don't depend on phases.

---

## Generalized Trigger Conditions

With the phase model, the tutorial-specific triggers from axis_guidance.md become general:

| Tutorial-specific trigger | Generalized trigger | What it checks |
|---|---|---|
| `TutorialStepActive(tutorial_id, step_id)` | `PhaseActive(workflow_id, phase_id)` | "Are we in this phase?" |
| `TutorialStepStuck(tutorial_id, step_id, threshold)` | `PhaseStuck(workflow_id, phase_id, threshold)` | "Have we been in this phase too long?" |
| `TutorialVerificationFailed(tutorial_id, step_id)` | `PhaseCheckFailed(workflow_id, phase_id)` | "Did the last gate check fail?" |

These are `TriggerCondition` implementations that read from `ActivePhase` on `ProjectState`:

```python
@dataclass(frozen=True)
class PhaseActive:
    """Fires when a specific phase is active in a workflow."""
    workflow_id: str
    phase_id: str

    def check(self, state: ProjectState) -> bool:
        if state.active_phase is None:
            return False
        return (
            state.active_phase.workflow_id == self.workflow_id
            and state.active_phase.phase_id == self.phase_id
        )

    @property
    def description(self) -> str:
        return f"Workflow '{self.workflow_id}' is in phase '{self.phase_id}'"
```

`ProjectState` gets one new optional field:

```python
@dataclass(frozen=True)
class ProjectState:
    root: Path
    copier: CopierAnswers
    session_count: int | None = None
    active_phase: ActivePhase | None = None  # NEW — None when no workflow active
```

This is cleaner than the previous `tutorial: TutorialContext | None` because it's general — any workflow populates it, not just tutorials.

---

## Lifecycle: `ShowUntilPhaseComplete`

The tutorial-specific `ShowUntilStepComplete` generalizes to `ShowUntilPhaseComplete`:

```python
@dataclass(frozen=True)
class ShowUntilPhaseComplete:
    """Show until the current phase's gates pass and the phase advances."""
    workflow_id: str
    phase_id: str

    def should_show(self, hint_id: str, state: HintStateStore) -> bool:
        completion_key = f"phase:{self.workflow_id}:{self.phase_id}:complete"
        return not state.is_dismissed(completion_key)

    def record_shown(self, hint_id: str, state: HintStateStore) -> None:
        state.increment_shown(hint_id)
```

Same mechanism. Better name. Usable by any workflow.

---

## Impact on Infrastructure Design

### Before: 4 primitives

```
Check System ──── Workflow State ──── Scoped Guardrails ──── Scoped Hints
    │                   │                    │                     │
    └──── separate ─────┴──── separate ──────┴───── separate ─────┘
```

### After: 2 primitives

```
Check ◄────────── Phase
  │                 │
  │                 ├── guards (what's allowed)
  │                 ├── gates (what advances) ──► uses Check
  │                 └── context (what hints are active)
  │
  └── independent building block
```

The phase is the organizer. Checks are the building block. Everything else is a facet of the phase.

---

## What About Workflows Without Phases?

Not everything needs phases. A simple validation check ("does `.gitconfig` exist?") doesn't need a workflow. The `Check` system works standalone:

```python
# No workflow, no phase — just run a check
result = FileExistsCheck("~/.gitconfig").check(ctx)
if not result.passed:
    print(result.message)
```

Phases are for when you have a sequence of states with different constraints. Checks are for when you just need to assert something about the system.

---

## File Structure

```
template/
  checks/                    # Primitive 1: Check system
    __init__.py
    _types.py                # Check protocol, CheckContext, CheckResult
    _builtins.py             # CommandOutputCheck, FileExistsCheck, etc.
    _registry.py             # YAML type → Check class mapping

  workflow/                  # Primitive 2: Phase system
    __init__.py
    _types.py                # Phase, Workflow, ActivePhase
    _engine.py               # WorkflowEngine (transitions, gate evaluation)
    _state.py                # Persistence (active_phase.json)
    _triggers.py             # PhaseActive, PhaseStuck, PhaseCheckFailed
    _lifecycle.py            # ShowUntilPhaseComplete

  hints/                     # Existing (extended)
    ...                      # get_hints() accepts phase hints

  .claude/guardrails/        # Existing (extended)
    phase_guard.py            # Runtime phase scope evaluation
    active_phase.json         # Written by WorkflowEngine at transitions
```

---

## Summary

**The shared primitive is the Phase.** A phase is a named state that simultaneously determines:
- What's **allowed** (guardrail scoping)
- What's **required** to advance (gate checks)
- What **guidance** is relevant (hint scoping)

These aren't three systems coordinating — they're three facets of one concept.

This collapses 4 proposed infrastructure primitives into 2:
1. **Check** — a rich system state assertion (independent building block)
2. **Phase** — a named state that organizes guards, gates, and context (the organizer)

The phase model is already implicit in the project team workflow (COORDINATOR.md defines phases with constraints and transitions). Making it explicit and formal means the same primitive serves tutorials, project team phases, migrations, and onboarding — with guardrails, checks, and hints all reading from the same source of truth.
