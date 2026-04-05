# Infrastructure vs Tutorial: Decomposition Analysis

**Reviewer:** Composability (Lead Architect)
**Prompt:** User reframe — "v1 is infrastructure, v2 is tutorial." Which pieces from our 6-axis spec are general-purpose template infrastructure, and which are tutorial-specific?

---

## The Insight

The user is right. We designed tutorial-shaped primitives when we should have designed infrastructure that tutorials happen to consume. The 6 axes (Content, Progression, Verification, Guidance, Safety, Presentation) describe a *tutorial system* — but the **primitives underneath** those axes are general-purpose.

The analogy: we designed "a car" when we should have designed "an engine, wheels, and a chassis" — things that cars, trucks, and tractors all use.

---

## Re-Analysis: The 6 Axes Decomposed

### Axis 1: Verification → **INFRASTRUCTURE: System State Assertions**

What we designed:
- `Verification` protocol: `check(ctx) → VerificationResult`
- `VerificationContext`: sandboxed system access (run_command, read_file, file_exists, ask_user)
- `VerificationResult`: passed/failed + message + evidence
- 5 built-in checks: CommandOutputCheck, FileExistsCheck, ConfigValueCheck, ManualConfirm, CompoundCheck

**None of this is tutorial-specific.** These are general-purpose system state assertions. Other consumers:

| Consumer | How it uses assertions |
|---|---|
| **Project setup validation** | "Did the user run `pixi install`?" "Does `.copier-answers.yml` exist?" — the hints system already does this with `TriggerCondition`, but only returns bool. Assertions return evidence. |
| **Guardrail enforcement** | "Is the environment clean before running tests?" "Does the git remote exist before pushing?" |
| **CI/CD checks** | "Does the build artifact exist?" "Does the config parse correctly?" |
| **Agent task verification** | "Did the Implementer actually create the file it said it created?" |
| **Health checks** | "Is SSH agent running?" "Is pixi environment activated?" |

**What the hints system already has:** `TriggerCondition.check(state) → bool`. This is an assertion that returns only pass/fail — no evidence, no message, no structured result.

**The gap:** `TriggerCondition` is a degenerate assertion. It answers "is this true?" but not "what did you find?" or "why did it fail?" The `Verification` protocol we designed is a *richer assertion* — it returns evidence and a human-readable message.

**Infrastructure name:** `Assertion` (or `Check`). Not `Verification` — that implies something is being verified against expectations. `Assertion` or `Check` is general: "check this property of the system and report what you found."

**Proposed renaming:**

| Tutorial spec name | Infrastructure name | Reason |
|---|---|---|
| `Verification` | `Check` | General-purpose system state check |
| `VerificationContext` | `CheckContext` | Sandboxed system access for checks |
| `VerificationResult` | `CheckResult` | Structured result with evidence |
| `CommandOutputCheck` | (same) | Already well-named |
| `FileExistsCheck` | (same) | Already well-named |
| `ConfigValueCheck` | (same) | Already well-named |
| `ManualConfirm` | (same) | Already well-named |
| `CompoundCheck` | (same) | Already well-named |

### Axis 2: Progression → **INFRASTRUCTURE: Multi-Step Workflow State**

What we designed:
- Step ordering (linear, checkpoint-gated)
- Step state tracking (current step, completed steps, evidence per step)
- Persistence (JSON file with progress)
- Advancement gate (can't advance without passing check)

**This is general workflow/state infrastructure.** Other consumers:

| Consumer | How it uses workflow state |
|---|---|
| **Project initialization** | Template setup is multi-step: clone → answer prompts → install deps → configure git → run tests. Each step could have checks. |
| **Migration workflows** | "Upgrade from v1 to v2" has steps with checkpoints. |
| **Onboarding sequences** | Not tutorials — just "make sure new contributor has X, Y, Z configured." |
| **Agent task pipelines** | Multi-step agent tasks where each step must complete before the next. |

**What already exists:** Nothing. The template has no general-purpose multi-step workflow tracking. The hints system has lifecycle state (times_shown, dismissed) but no concept of "step N of M."

**The gap is real.** This is missing infrastructure.

**Infrastructure name:** `Workflow` or `StepSequence`. A sequence of named steps with optional checks and state persistence.

### Axis 3: Safety (Guardrails) → **INFRASTRUCTURE: Scoped Rule Activation**

What we designed:
- Tutorial-scoped guardrail rules (active only during tutorial)
- Per-step rule activation/deactivation
- Rule exemption per step
- Checkpoint enforcement (deny advancement without check passing)

**The primitive underneath is scoped rule activation.** The existing guardrails system has a primitive form of scoping: `block: [Subagent]` — rules that only fire for certain agent roles. But it doesn't have:

1. **Mode-based scoping** — "this rule is active only when in tutorial mode" or "this rule is active during project-team phase 3"
2. **Dynamic activation** — rules that can be activated/deactivated at runtime, not just at generation time
3. **Temporary exemption** — "exempt R02 for this step, then re-enable it"

Other consumers:

| Consumer | How it uses scoped rules |
|---|---|
| **Project team phases** | Phase-specific rules: "during specification, don't allow code edits." "During implementation, don't allow spec edits." |
| **Single-agent mode** | Different rule profile when user is working alone vs in a team |
| **CI mode** | Stricter rules when running in CI (no user interaction, no manual confirms) |
| **Protected branches** | Scoped rules for working on main vs feature branches |

**What already exists:**
- `rules.yaml` with static rules, statically generated into hook scripts
- `block: [Subagent]` — role-based scoping (via `role_guard.py` at runtime)
- `generate_hooks.py` — code generation that bakes rules into Python scripts

**The gap:** Role scoping exists. Mode/phase scoping does not. The guardrail engine evaluates rules at runtime via generated Python scripts, but the set of active rules is fixed at generation time. Dynamic scoping requires either:
- (a) A runtime rule filter (read an "active scope" file and skip rules not in scope), or
- (b) Regenerating hooks when scope changes (too slow, too fragile)

**Infrastructure name:** `ScopedRules` or extend existing system with a `scope` field on rules and a runtime scope context.

### Axis 4: Guidance (Hints Integration) → **PARTIALLY INFRASTRUCTURE: Context-Scoped Hint Registration**

What we designed:
- Tutorial-specific triggers (StepActive, StepStuck, VerificationFailed)
- YAML → HintSpec conversion
- ShowUntilStepComplete lifecycle
- Agent-assist with read-only context

**Split:**

| Piece | Infrastructure or Tutorial? |
|---|---|
| Pattern of registering context-specific hints dynamically | **Infrastructure** — any mode could register hints |
| `TutorialStepActive`, `TutorialStepStuck`, `TutorialVerificationFailed` triggers | **Tutorial-specific** — they read TutorialContext |
| `ShowUntilStepComplete` lifecycle | **Tutorial-specific** (but generalizable to "show until condition X") |
| `_build_hint_specs()` from YAML | **Infrastructure** — YAML → HintSpec conversion is useful for any declarative hint source |
| `AgentContext` for tutorial-runner | **Tutorial-specific** |
| `get_hints()` accepting additional hints | **Infrastructure** — existing extension point |

**The infrastructure piece:** The hints system already supports dynamic hint lists (the `get_hints()` function returns a list that the engine evaluates). The infrastructure gap is: there's no standard pattern for "an external system registers hints that are active only while that system is active." The tutorial spec's approach (append to the list, remove when done) works but should be generalized.

**Infrastructure name:** `ScopedHints` — hints that are registered/unregistered based on an active context.

### Axis 5: Content → **TUTORIAL-SPECIFIC**

What we designed:
- `tutorial.yaml` manifest format
- Step markdown format with `run` blocks and `<!-- checkpoint -->` markers
- Auto-discovery of tutorial directories
- YAML schema for step verification/hint declarations

**This is genuinely tutorial-specific.** The manifest format, step markdown conventions, and checkpoint markers are all about authoring tutorials. No other system needs a "tutorial.yaml" format.

However, there's a reusable sub-pattern: **declarative task manifest** — a YAML file that declares a sequence of steps, each with checks and context. This is the Workflow infrastructure from Axis 2, expressed as YAML. The tutorial manifest is just one consumer of this pattern.

### Axis 6: Presentation → **TUTORIAL-SPECIFIC**

How the tutorial renders to the user (CLI, conversational, TUI) is tutorial-specific. The underlying rendering infrastructure (toasts, agent conversations) already exists.

---

## Infrastructure Gap Map

### What Already Exists (and is reusable as-is)

```
┌─────────────────────────────────────────────────────────┐
│ EXISTING INFRASTRUCTURE                                  │
│                                                          │
│ Hints System                                             │
│ ├── TriggerCondition protocol (check → bool)            │
│ ├── HintLifecycle protocol (should_show, record_shown)  │
│ ├── HintSpec (registry entry)                           │
│ ├── HintRecord (seam object)                            │
│ ├── HintStateStore (lifecycle persistence)              │
│ ├── ActivationConfig (enable/disable)                   │
│ └── run_pipeline() (evaluation engine)                  │
│                                                          │
│ Guardrails System                                        │
│ ├── rules.yaml (rule catalog)                           │
│ ├── generate_hooks.py (code generation)                 │
│ ├── role_guard.py (role-based scoping at runtime)       │
│ ├── bash_guard.py / write_guard.py (generated hooks)    │
│ └── hits.jsonl (audit trail)                            │
│                                                          │
│ Agent System                                             │
│ ├── Agent role files (COORDINATOR.md, etc.)             │
│ ├── spawn_agent() with type= for role assignment        │
│ └── tell_agent/ask_agent for communication              │
│                                                          │
│ Project State                                            │
│ ├── ProjectState (frozen read-only context)             │
│ ├── CopierAnswers (template configuration)              │
│ └── path_exists, file_contains, etc. (primitives)       │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### What's Missing (infrastructure gaps tutorials exposed)

```
┌─────────────────────────────────────────────────────────┐
│ MISSING INFRASTRUCTURE (v1 scope)                        │
│                                                          │
│ 1. Check System (richer assertions)                      │
│    ├── Check protocol: check(ctx) → CheckResult         │
│    ├── CheckContext: sandboxed system access              │
│    ├── CheckResult: passed + message + evidence          │
│    ├── Built-in checks: CommandOutput, FileExists,       │
│    │   ConfigValue, ManualConfirm, Compound              │
│    └── YAML deserialization via registry                  │
│                                                          │
│ 2. Workflow State (multi-step tracking)                   │
│    ├── StepSequence: ordered steps with optional checks  │
│    ├── WorkflowState: current step, completed, evidence  │
│    ├── Advancement gate: check must pass to advance      │
│    └── JSON persistence with resume support              │
│                                                          │
│ 3. Scoped Guardrail Activation                           │
│    ├── scope field on rules.yaml rules                   │
│    ├── Runtime scope context (mode, phase, workflow)     │
│    ├── Dynamic activation/deactivation                   │
│    └── Temporary exemption mechanism                     │
│                                                          │
│ 4. Scoped Hint Registration                              │
│    ├── Register/unregister hint sets by context          │
│    ├── YAML → HintSpec conversion utility                │
│    └── Context-aware trigger conditions                  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## How Infrastructure ↔ Tutorial Connect

```
INFRASTRUCTURE (v1)                    TUTORIAL SYSTEM (v2)
───────────────────                    ────────────────────

Check System                    ◄───── Tutorials define checks per step
  Check protocol                       in tutorial.yaml as YAML declarations
  CheckResult
  Built-in checks

Workflow State                  ◄───── Tutorial is a workflow
  StepSequence                         tutorial.yaml steps = StepSequence
  WorkflowState                        Tutorial progress = WorkflowState
  Advancement gate                     Checkpoint = advancement gate

Scoped Guardrail Activation     ◄───── Tutorial mode = a scope
  scope field on rules                 Per-step rule activation
  Runtime scope context                exempt_guardrails per step
  Temporary exemption

Scoped Hint Registration        ◄───── Tutorial steps register hints
  Context-aware triggers               TutorialStepStuck etc. are context triggers
  YAML → HintSpec conversion           tutorial.yaml hints → HintSpec

                                       TUTORIAL-ONLY (v2):
                                       tutorial.yaml manifest format
                                       Step markdown format
                                       Tutorial-runner agent role
                                       Tutorial selector / registry UI
                                       Tutorial-specific triggers
                                       ShowUntilStepComplete lifecycle
```

---

## Seams Between Existing and New Infrastructure

### Check System ↔ Hints System

**Current:** `TriggerCondition.check(state) → bool`
**New:** `Check.check(ctx) → CheckResult`

These are related but NOT the same:
- `TriggerCondition` answers: "should this hint fire?" (project-level, startup-evaluated, cheap)
- `Check` answers: "did this thing actually happen?" (system-level, on-demand, may run commands)

**Seam:** `TriggerCondition` could delegate to `Check` internally, but they serve different purposes. A `TriggerCondition` could wrap a `Check` for richer trigger logic:

```python
@dataclass(frozen=True)
class CheckBasedTrigger:
    """TriggerCondition that delegates to a Check."""
    check: Check

    def check(self, state: ProjectState) -> bool:
        ctx = build_check_context(state)
        result = self.check.check(ctx)
        return result.passed

    @property
    def description(self) -> str:
        return self.check.description
```

But this is optional. The two systems can coexist without coupling. The seam is that `Check` is a richer primitive; `TriggerCondition` is a simpler one. Neither depends on the other.

### Check System ↔ Guardrails System

**Current:** Guardrails check regex patterns against tool input at hook time.
**New:** Check system checks system state (files, commands, configs).

**Different concerns:** Guardrails are pre-action gates ("should this tool call be allowed?"). Checks are post-action assertions ("did the expected thing happen?"). They're complementary, not competing.

**Seam:** The advancement gate (currently `CheckpointNotPassedError`) uses Check results to enforce progression. This sits in the Workflow State system, not in the guardrails system. The guardrail system doesn't need to know about Checks — the workflow engine is the enforcement point.

### Workflow State ↔ Hints System

**Current:** Hints have `HintStateStore` (lifecycle persistence). Hints have no concept of multi-step workflows.
**New:** Workflow State tracks step progression with persistence.

**Seam:** These are independent state stores:
- `HintStateStore` → `.claude/hints_state.json` (hint display history)
- `WorkflowState` → `.claude/workflow_state.json` (step progression)

Context-scoped hints (like "show when stuck on step 3") need to read workflow state. The seam: `ProjectState` gets an optional workflow context (similar to how we proposed `TutorialContext`, but generalized):

```python
@dataclass(frozen=True)
class WorkflowContext:
    """Read-only snapshot of active workflow state."""
    workflow_id: str | None
    current_step_id: str | None
    step_entered_at: float | None
    completed_steps: frozenset[str]
    last_check_result: CheckResult | None
```

This replaces the tutorial-specific `TutorialContext`. Any workflow (tutorial, migration, onboarding) populates this context. Hint triggers that care about workflow state read from it.

### Scoped Rules ↔ Existing Guardrails

**Current:** Rules are statically generated. Role scoping is runtime (`role_guard.py`).
**New:** Mode/workflow scoping at runtime.

**Implementation approach:** The existing `role_guard.py` already demonstrates runtime evaluation: it reads env vars and session markers to determine role. Scope evaluation follows the same pattern:

```python
# In generated hooks, alongside the existing role_guard check:
def check_scope(scope_config, guardrails_dir):
    """Check if a rule's scope matches the current runtime context."""
    if scope_config is None:
        return True  # No scope restriction — always active

    mode = scope_config.get("mode")
    if mode:
        # Read active mode from a scope marker file
        scope_file = Path(guardrails_dir) / "active_scope.json"
        if not scope_file.exists():
            return False
        active = json.loads(scope_file.read_text())
        if active.get("mode") != mode:
            return False

    return True
```

**The scope marker pattern** mirrors the session marker pattern (`sessions/ao_<PID>`). A scope marker file (`active_scope.json`) declares the current mode. Rules with `scope:` fields are filtered at runtime.

**Seam:** `generate_hooks.py` bakes scope configs into generated hooks (just like it bakes role configs). `check_scope()` evaluates at runtime (just like `check_role()`). The scope marker file is written/deleted by whatever system activates a mode (tutorial engine, project team, etc.).

---

## What's Actually Missing as Reusable Base Functions

Answering the user's direct question: "Agent roles — we already have these. What's missing as reusable infrastructure?"

### Missing Function 1: `check()` — Rich System State Assertions

**What:** A `Check` protocol + `CheckContext` + `CheckResult` + 5 built-in implementations.
**Where it lives:** New module, e.g., `checks/` at template root (parallel to `hints/`).
**Why it's missing:** The hints system has `TriggerCondition` (bool assertions) and `ProjectState` (file/path primitives), but no way to run commands, capture evidence, or compose checks. The guardrails have regex matching on tool input but no system state checks.

### Missing Function 2: `workflow_state()` — Multi-Step State Tracking

**What:** `StepSequence` definition + `WorkflowState` persistence + advancement gate.
**Where it lives:** New module, e.g., `workflow/` at template root.
**Why it's missing:** Nothing in the template tracks "step N of M" with persistence and gates. The hints system is stateless per-evaluation. The guardrails are per-action. Neither tracks progression through a sequence.

### Missing Function 3: `scope_rules()` — Runtime Guardrail Scoping

**What:** A `scope` field on rules.yaml rules + a `check_scope()` runtime function + an `active_scope.json` marker file.
**Where it lives:** Extension to existing guardrails system (`role_guard.py` → add `scope_guard.py`, update `generate_hooks.py`).
**Why it's missing:** The guardrails have role-based scoping (`block: [Subagent]`) but no mode/phase/workflow scoping. Adding a scope field and runtime check is a natural extension.

### Missing Function 4: `scoped_hints()` — Context-Aware Hint Registration

**What:** A utility to register/unregister sets of `HintSpec` objects tied to an active context + YAML → HintSpec conversion.
**Where it lives:** Extension to existing hints system (new function in `hints/` or utility module).
**Why it's missing:** `get_hints()` returns a static list. There's no pattern for "when context X is active, also include these hints."

---

## Revised Crystal: Infrastructure Axes

The infrastructure has its own compositional structure — its own crystal:

### Infrastructure Axes

1. **Check Type** — What system state is being asserted
   - Values: command-output | file-exists | config-value | manual-confirm | compound
   - Independent of who's consuming the check

2. **Scope Type** — What activates/deactivates a rule or hint set
   - Values: always | role-based | mode-based | workflow-step-based
   - Independent of what's being scoped (guardrails vs hints)

3. **State Domain** — What state is being tracked
   - Values: hint-lifecycle | workflow-progression | guardrail-scope
   - Independent storage, independent persistence

### Infrastructure Compositional Law

**The Check Protocol** — all checks produce `CheckResult`. All consumers read `CheckResult.passed` + `CheckResult.message` + `CheckResult.evidence`. No consumer knows which check type produced the result.

**The Scope Protocol** — all scope evaluators produce `bool` (is this scope active?). Rules and hint sets are filtered by scope. No rule knows why its scope is active or inactive.

---

## Impact on v1 vs v2 Planning

### v1: Infrastructure

Build four general-purpose primitives:

| Primitive | Module | Integrates with |
|---|---|---|
| Check system | `checks/` | Standalone; optionally wrappable by TriggerCondition |
| Workflow state | `workflow/` | Check system (advancement gates) |
| Scoped guardrails | `.claude/guardrails/` extension | Existing guardrail engine |
| Scoped hints | `hints/` extension | Existing hints engine |

### v2: Tutorial System

Build the tutorial-specific layer that consumes infrastructure:

| Tutorial piece | Consumes |
|---|---|
| tutorial.yaml manifest | Workflow (step sequence), Check (per-step checks), Scoped hints (per-step hints), Scoped guardrails (per-step rules) |
| Step markdown format | Nothing — pure content |
| Tutorial-runner agent | Workflow state (knows current step), Check results (shows evidence) |
| Tutorial selector | Workflow (discover available workflows) |
| Tutorial-specific triggers | Scoped hints (StepStuck wraps WorkflowContext) |
| ShowUntilStepComplete | Workflow state (step completion) |

### What v2 adds that v1 doesn't have:
- Tutorial-specific triggers (TutorialStepStuck, etc.) — these are HintSpec values, not infrastructure
- Tutorial content format (markdown + YAML) — authoring format, not infrastructure
- Tutorial-runner agent role — agent config, not infrastructure
- Tutorial selector UI — presentation, not infrastructure

---

## Summary

The user's insight is correct and sharpens the design significantly. The decomposition is:

| Our original axis | Infrastructure primitive | Tutorial-specific layer |
|---|---|---|
| Verification | **Check system** — rich assertions with evidence | Tutorial steps declare checks in YAML |
| Progression | **Workflow state** — multi-step tracking with gates | Tutorial manifest is a workflow definition |
| Safety | **Scoped guardrails** — runtime rule activation by mode/workflow | Tutorial mode is one scope |
| Guidance | **Scoped hints** — context-aware hint registration | Tutorial triggers are context-specific hints |
| Content | (none) | Tutorial manifest + step markdown |
| Presentation | (none) | Tutorial UI |

Four infrastructure primitives. Two tutorial-specific layers. Clean separation. The infrastructure is independently useful — projects that never use tutorials still benefit from rich checks, workflow tracking, scoped guardrails, and scoped hints.
