# Skeptic Specification Review

## Overall Assessment

The specification package is strong. The Verification axis is thorough and well-designed. The Content axis provides a clean authoring format. The Guidance axis achieves genuine composability with the existing hints pipeline. Prior art validates the core design decisions. The composability analysis passes the crystal test.

Three of my five original concerns are fully resolved. Two remain partially addressed. I also found a few new issues in the specifications themselves.

---

## Original Concerns — Status

### 1. Checkpoint Verification (was HIGH) → RESOLVED ✅

`axis_verification.md` addresses this comprehensively:
- The `Verification` protocol is a clean `check(ctx) → VerificationResult` contract
- `VerificationContext` provides sandboxed, read-only access (timeout-enforced, output-truncated)
- Five built-in implementations cover the real verification needs (command output, file exists, config value, manual confirm, compound)
- Three-level guardrail integration (agent instruction injection, progression gate, evidence persistence) prevents bypass
- YAML serialization keeps content authors writing data, not code
- `VerificationResult.evidence` captures proof for audit trail and agent guidance

**One residual gap:** The spec doesn't address **retry semantics**. When a network-dependent verification (e.g., `ssh -T git@github.com`) times out or fails due to transient issues, what happens? The user gets a failure message, but there's no distinction between "you didn't do the step" and "the verification itself was flaky." Recommendation: add an optional `retries: int` field to verification config (default 1), with a brief delay between attempts. This is a small addition to the YAML schema, not a design change.

### 2. Agent Over-Help (was HIGH) → RESOLVED ✅

`axis_guidance.md` section 4 handles this well:
- `AgentContext` is a read-only frozen dataclass — the agent gets content and results, not engine references
- Agent role file explicitly constrains: "MUST NOT run commands on behalf of the user that are part of the verification"
- `agent_blocked_commands` per-step in `tutorial.yaml` generates scoped guardrail rules that prevent the agent from executing verification-target commands
- Structural separation: the agent literally cannot call `advance_step()` or `verify_current_step()` — those live on the engine, which the agent doesn't have a reference to

This is the right design. The constraint is enforced both by prompt instruction (soft) and by guardrail rules (hard).

### 3. Tutorial Mode Lifecycle (was MEDIUM) → PARTIALLY ADDRESSED ⚠️

Pieces are present but scattered across specs without a cohesive lifecycle definition:

| Lifecycle Event | Specified? | Where |
|---|---|---|
| **Entry** (starting a tutorial) | Implied | `TutorialContext` on `ProjectState` goes from `None` to populated |
| **Step advancement** | Yes | `axis_verification.md` — `advance_to_next_step()` with checkpoint gate |
| **Clean exit** (tutorial completed) | Not specified | What cleanup runs? How is completion recorded globally? |
| **Abandon** (user quits mid-tutorial) | Not specified | Is progress saved? Can they resume? What command resumes? |
| **Crash/disconnect** | Partially | `tutorial_progress.json` persists state, but reconnect behavior is undefined |
| **Guardrail profile switching** | Partially | Tutorial guardrails are additive per-step, but activation/deactivation on entry/exit isn't specified |
| **Nesting prevention** | Not specified | What happens if user starts tutorial B while tutorial A is active? |

**What's missing is the state machine.** The individual mechanisms exist (TutorialProgressStore, TutorialContext, scoped guardrails), but the transitions between states aren't defined. This matters because:
- If cleanup on exit is undefined, tutorial guardrails could persist after the tutorial ends
- If nesting isn't prevented, two tutorials could conflict (both setting TutorialContext, both adding guardrails)
- If resume isn't defined, users who disconnect lose their progress conceptually even if the JSON file persists

**Recommendation:** Add a `tutorial_lifecycle.md` spec defining the state machine:
```
INACTIVE → ACTIVE (start command, load content, activate guardrails, set TutorialContext)
ACTIVE → STEP_N (advance, swap per-step guardrails, update TutorialContext)
ACTIVE → COMPLETED (all steps verified, persist completion, deactivate guardrails, clear TutorialContext)
ACTIVE → ABANDONED (user quits, persist progress, deactivate guardrails, clear TutorialContext)
ABANDONED → ACTIVE (resume command, reload from progress store, reactivate guardrails)
```

### 4. Agent Teams Tutorial Isolation (was MEDIUM) → NOT ADDRESSED ❌

None of the five specs address the "Working with Agent Teams" special tutorial. The composability doc mentions it as a user decision:

> "One special tutorial ("Working with Agent Teams") spawns actual agents as its content — teaching the multi-agent workflow by doing it."

But no specification defines:
- How the tutorial-runner gets agent-spawning permissions (standard runners are constrained)
- What happens when user exits mid-tutorial with spawned agents still running
- How verification checks agent state (no built-in verification type for "agent X exists and completed task Y")
- Whether this tutorial uses the same `tutorial.yaml` format or needs extensions

**Recommendation:** This can be deferred to v2, but that decision should be **explicit**. If the Agent Teams tutorial is v1 scope, it needs its own spec addendum. If it's v2, say so and remove it from the composability crystal test assumptions.

### 5. Guardrail Conflicts (was MEDIUM) → PARTIALLY ADDRESSED ⚠️

The specs define **additive** tutorial guardrails — tutorials can add rules that are active during steps. But they don't define **exemptive** tutorial guardrails — tutorials that need to temporarily disable existing rules.

**Concrete example:** A tutorial teaching "why pixi manages dependencies" might include a step where the user intentionally runs `pip install foo` to see it fail or to demonstrate the problem. R02 (`pip-install-block`) would deny this.

Options:
1. **Tutorial guardrail profile with exemptions** — tutorial.yaml can declare `exempt_rules: [R02]` for specific steps
2. **Reframe the tutorial** — never actually run the blocked command; just explain why it's blocked (weaker pedagogically)
3. **Guardrail passthrough mode** — tutorial mode downgrades `deny` to `warn` for exempt rules

The specs don't address this. The Safety axis in composability says "Tutorial-specific rules are additive — they extend the catalog, not replace it." This is correct for most cases but doesn't cover the exemption scenario.

**Recommendation:** Add an `exempt_guardrails` field per step in `tutorial.yaml`, with the engine temporarily deactivating those rules for the step's duration. This is a small addition to the content schema and the guardrail scoping mechanism.

---

## New Issues Found in Specifications

### N1: CompoundCheck eager evaluation (LOW)

In `axis_verification.md`, `CompoundCheck.check()` evaluates ALL sub-checks regardless of mode:

```python
sub_results = tuple(c.check(ctx) for c in self.checks)
```

For `mode="all"`, if the first check fails, the remaining checks still run. This wastes time on expensive checks (network commands) and could produce confusing evidence (user sees 3 failures when only the first matters).

**Recommendation:** Short-circuit for `mode="all"` — stop on first failure. Keep eager evaluation for `mode="any"` (need to find at least one pass). This is a one-line implementation change, but it should be in the spec to set expectations.

### N2: Environment variable resolution undefined (MEDIUM)

`axis_content.md` allows `${CLUSTER_HOST}` in verification params. But:
- Where are these variables defined? User environment? Tutorial-specific config? A `.env` file?
- What happens if `${CLUSTER_HOST}` is not set? Does verification fail with a confusing error? Does the engine refuse to start the tutorial?
- Can variables reference other variables?

**Recommendation:** Define a `variables` section in `tutorial.yaml` where authors declare required variables with descriptions. The engine prompts the user for undefined variables at tutorial start, not mid-step.

```yaml
variables:
  CLUSTER_HOST:
    description: "Your cluster's hostname (e.g., login.hpc.example.edu)"
    required: true
  CLUSTER_USER:
    description: "Your username on the cluster"
    required: true
    default: "${USER}"  # Fall back to current username
```

### N3: Verification type naming inconsistency (LOW)

`axis_verification.md` uses Python class names (`CommandOutputCheck`, `FileExistsCheck`) and a registry with underscored keys (`command_output_check`). `axis_content.md` uses hyphenated YAML keys (`command-output-check`, `file-exists-check`). These must be reconciled — the YAML format is what content authors write, and the registry is what the engine uses. The spec should pick one convention and define the mapping explicitly.

The YAML uses hyphens (`command-output-check`), the registry uses underscores (`command_output_check`). Both are fine conventions, but the mapping needs to be explicit in one place (either the registry normalizes hyphens to underscores, or the YAML schema uses underscores).

### N4: `ProjectState.tutorial` coupling (LOW)

`axis_guidance.md` extends `ProjectState` with a `tutorial: TutorialContext | None` field. This means the hints system's core data model now knows about tutorials. It's a minor coupling — one optional field — but it means the hints `_types.py` or `_state.py` must import or define `TutorialContext`.

The spec says this follows the "existing kwargs convention," but `session_count` (the existing optional field) is a primitive (`int | None`), not a domain-specific dataclass from another subsystem. `TutorialContext` is richer.

**Recommendation:** This is acceptable if `TutorialContext` is defined in a shared types module (not in the tutorial engine). Or: pass tutorial state through the existing `**kwargs` and have tutorial triggers extract it themselves, keeping `ProjectState` clean.

---

## Prior Art Review — Validated

`research_prior_art.md` is solid. The five sources are relevant, properly tiered, and the synthesis patterns (verification as exit code, evidence capture, manifest-driven content, watch/react mode, automate the unimportant) directly validate the specification's design.

One observation: **Katacoda's "general-to-specific" verification ordering** (check file exists before checking file content) is good advice that should be explicitly stated as a content authoring guideline. Currently it's buried in the research doc but not surfaced in `axis_content.md`.

---

## Composability Review — Validated with Notes

The 6-axis decomposition (Content × Progression × Verification × Guidance × Safety × Presentation) is clean. The crystal test passes. The Step Protocol is the right shared law.

The Progression axis is the least specified — it's named in the composability doc but has no deep-dive. The spec defines `linear`, `branching`, and `checkpoint-gated` as values but doesn't specify the state machine for each. For v1 with only `checkpoint-gated`, this is fine. But `branching` is listed as a value with only a commented-out example in `tutorial.yaml`:

```yaml
# branching_rules:
#   - from: step-id
#     condition: "verification.result == 'already-configured'"
#     goto: skip-to-step-id
```

**Recommendation:** Either spec `branching` fully or explicitly defer it to v2. A half-specified progression mode is worse than no progression mode.

---

## Summary Table

| Concern | Status | Action Required |
|---|---|---|
| Checkpoint verification | ✅ RESOLVED | Add optional `retries` field for flaky checks |
| Agent over-help | ✅ RESOLVED | None |
| Tutorial mode lifecycle | ⚠️ PARTIAL | Add `tutorial_lifecycle.md` state machine spec |
| Agent Teams tutorial | ❌ NOT ADDRESSED | Explicitly scope to v2 or add spec addendum |
| Guardrail conflicts | ⚠️ PARTIAL | Add `exempt_guardrails` per-step field |
| CompoundCheck eager eval | NEW (LOW) | Short-circuit on `mode="all"` |
| Environment variables | NEW (MEDIUM) | Add `variables` section to `tutorial.yaml` schema |
| Verification type naming | NEW (LOW) | Reconcile hyphen vs. underscore convention |
| ProjectState coupling | NEW (LOW) | Minor — acceptable if TutorialContext in shared types |
| Branching progression | NEW (LOW) | Fully spec or defer to v2 |

## Verdict

**The specification is ready to proceed to architecture, contingent on resolving the two PARTIAL items** (tutorial mode lifecycle state machine, guardrail exemption mechanism). The NOT ADDRESSED item (Agent Teams tutorial) should be explicitly deferred to v2. The NEW issues are improvements, not blockers — they can be resolved during architecture phase.

The design is complete, correct, and as simple as the problem allows. The essential complexity (checkpoint verification, agent constraint enforcement, hints integration) is solved, not avoided. The accidental complexity concerns from v1 review (multi-agent overhead, deep hints coupling) were either resolved by user corrections or eliminated by good design decisions.
