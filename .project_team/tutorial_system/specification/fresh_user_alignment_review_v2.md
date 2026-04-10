# Fresh User Alignment Review — Final Architecture

**Date:** 2026-04-04
**Scope:** Full specification package (24 files), all user inputs throughout project
**What we're building:** 2 primitives (Check + Phase), ~200 lines core, 2 consumers (R01 phase-scoping + First Pytest tutorial), /check-setup diagnostic

---

## All User Inputs (Chronological)

I'm tracing every user input to verify nothing was lost:

### Input 1: Original Request
> "Add a 'tutorial' feature to the template that combines md files, a team of agents, hints, and guardrails in a new mode to help users complete a task."

### Input 2: Tutorial Examples
> "Tutorial ideas include: signing up for GitHub, SSH-ing into a cluster for the first time, learning a coding feature, setting up git config & SSH keys, creating a first project from the template, understanding pixi environments, writing and running a first test with pytest."

### Input 3: Agent Model Decision
> Single tutorial-runner agent for v1. First multi-agent tutorial teaches agent workflows by doing them.

### Input 4: Bootstrap Clarification
> SSH and GitHub signup are valid tutorials (users already have SSH on cluster, git pre-installed).

### Input 5: Guardrails as Verification
> "Guardrails are not only preventing bad things, they are also used as checkpoints"

### Input 6: Infrastructure-First Reframe
> "I think v1 is infrastructure, v2 is tutorial. We need to think about the seams between existing systems and define what reusable base functions we need to build a tutorial on top of."

### Input 7: Phase Unification
> "What IS common between verification and guardrails? mode_scope and state are the same thing."

### Input 8: Phase Example
> "Think of a workflow where in phase 4 we don't let agents run the full test suite"

### Input 9: Scope Change Acknowledgment
> "This changes the scope of the project based on the input from the team about what is needed"

---

## Input-by-Input Alignment Check

### Input 1: "tutorial feature" — ✅ HONORED

The architecture builds the infrastructure (v1) that tutorials (v2) will compose. The tutorial remains the motivating use case and the acceptance test for v1. The final architecture specifies:
- Check system → tutorial checkpoints
- Phase system → tutorial steps
- Phase-scoped guardrails → per-step safety
- Phase-scoped hints → per-step guidance

**Every component the user named (md files, agents, hints, guardrails, mode) has a clear path from infrastructure primitive to tutorial feature.**

### Input 2: Tutorial Examples — ✅ HONORED (deferred to v2, by design)

The examples are illustrative ("ideas include:"). V1 doesn't implement tutorials — it builds the primitives. But the architecture was designed by specifying actual tutorials first (SSH, pytest), then extracting primitives. The spec includes concrete examples showing how each tutorial type maps to Check + Phase.

The "First Pytest" tutorial is one of the two day-one consumers, directly from the user's list. This is the right choice — it validates the infrastructure with real content.

### Input 3: Single Runner + Agent-Team Tutorial — ✅ HONORED

The architecture doesn't mention agents directly because agent infrastructure already exists. The unified model correctly identifies: agent roles are existing infrastructure, not something to build. The tutorial-runner role is a v2 addition (one markdown file).

The Skeptic flagged the agent-team tutorial as needing isolation or explicit v2 deferral. The architecture implicitly defers it by not including it in the two day-one consumers. **Recommend making this explicit** — but it's a documentation gap, not an alignment failure.

### Input 4: Bootstrap Clarification — ✅ HONORED

No bootstrap paradox in the architecture. SSH and GitHub tutorials are valid because users already have the tools. This was resolved early and hasn't regressed.

### Input 5: "Guardrails as Checkpoints" — ✅ HONORED (this insight shaped the entire architecture)

This is the user's most architecturally significant input. It led directly to:
- The Check system (verification as a first-class primitive)
- Phase gates (advance_checks must pass before transition)
- Evidence capture (CheckResult.evidence proves completion)
- The three-level enforcement model (instruction injection, progression gate, evidence persistence)

The unified Phase model makes this concrete: a Phase has both `activate_rules` (what's prevented) and `advance_checks` (what must be proven). **Guardrails and checkpoints are two facets of the same phase.** This is exactly what the user said.

### Input 6: "v1 infrastructure, v2 tutorial" — ✅ HONORED (this IS the architecture)

The entire architecture is organized around this split:
- V1: Check + Phase (~200 lines core)
- V2: Tutorial content format, tutorial-runner agent, tutorial-specific triggers

The two day-one consumers (R01 phase-scoping, First Pytest tutorial) validate that v1 infrastructure works before v2 builds on it.

### Input 7: "mode_scope and state are the same thing" — ✅ HONORED (this IS the unification)

The Phase primitive directly implements this insight:
- `Phase.activate_rules` / `Phase.deactivate_rules` = mode_scope (what's allowed)
- `Phase.advance_checks` = state (what must be true)
- These are co-scoped by the same Phase identity

The composability analysis collapsed 4 proposed primitives into 2 (Check + Phase) because of this unification. The Skeptic validated the unification is real at the guardrail-scoping level.

### Input 8: "Phase 4, don't let agents run full test suite" — ✅ HONORED

This is one of the two day-one consumers. R01 (pytest-output-block) gets phase-scoping:
- Phase 4 (Implementation): R01 active (deny full pytest)
- Phase 5 (Testing): R01 relaxed

The unified_phase_model.md shows this as Example 1 with concrete YAML.

### Input 9: "This changes the scope" — ✅ HONORED

The user acknowledged the scope change. The architecture reflects it. The project name and goal still reference tutorials. The infrastructure is bounded by tutorial needs.

---

## Has Anything Been Lost?

### Checking each original component:

| Component | Status | Where in Architecture |
|---|---|---|
| **md files** | ✅ Preserved | V2: tutorial content format (YAML manifest + markdown steps). Architecture validated by full content spec (axis_content.md). |
| **team of agents** | ✅ Preserved | Existing infrastructure (agent roles). V2: add tutorial-runner role file. |
| **hints** | ✅ Preserved | V1: Phase-scoped hints (Phase.hints). V2: tutorial-specific triggers. Existing pipeline untouched. |
| **guardrails** | ✅ Preserved | V1: Phase-scoped guardrails (Phase.activate_rules/deactivate_rules). Day-one consumer: R01. |
| **new mode** | ✅ Preserved | V1: Phase system IS the mode system. ActivePhase on ProjectState. A tutorial is a workflow with phases. |
| **help users complete a task** | ✅ Preserved | V1: Check system proves completion (CheckResult.evidence). Phase gates block advancement without proof. |

**Nothing has been lost.**

### Checking the user's end-to-end vision:

> "A user types a command, picks 'SSH into my cluster,' and gets a guided, interactive walkthrough — with agents helping, hints nudging, and guardrails both preventing mistakes AND verifying that each step was actually completed."

This is a V2 experience. Can V1 infrastructure support it?

- "types a command" → V2: /tutorial skill (follows /hints pattern)
- "picks a tutorial" → V2: tutorial registry/selector
- "guided, interactive walkthrough" → V2: tutorial-runner agent + step content
- "agents helping" → V2: tutorial-runner role (existing spawn infrastructure)
- "hints nudging" → V1: Phase.hints registered into pipeline. V2: tutorial-specific triggers
- "guardrails preventing mistakes" → V1: Phase.activate_rules. Day-one consumer validates this works
- "verifying that each step was actually completed" → V1: Phase.advance_checks + CheckResult.evidence. Day-one consumer validates this works

**Every element of the vision has a clear implementation path through V1 → V2.**

---

## Has Anything Been Added?

### Checking for scope creep:

| Addition | User Asked? | Justified? |
|---|---|---|
| Phase system (general, not tutorial-specific) | User said "new mode" + "mode_scope and state are the same thing" | ✅ User explicitly requested generalization |
| R01 phase-scoping | User said "phase 4 don't let agents run full test suite" | ✅ User explicitly requested this |
| /check-setup diagnostic | User didn't ask for this | ⚠️ See below |
| WorkflowEngine with try_advance() | User implied this via "guardrails as checkpoints" | ✅ Natural consequence of user's checkpoint insight |
| phase_guard.py | User didn't name this | ✅ Infrastructure to implement user's phase-scoping request |

### ⚠️ /check-setup — Minor addition, acceptable

The /check-setup diagnostic is a day-one consumer that validates the Check system works outside of tutorials. The user didn't ask for it, but it's a small, useful byproduct of building the Check system. It demonstrates the "infrastructure serves more than just tutorials" principle the user endorsed.

**Verdict:** Not scope creep. It's a validation tool for infrastructure the user requested. If it grows beyond a diagnostic command, flag it.

### ✅ No other scope creep detected

The architecture is remarkably lean: 2 primitives, ~200 lines, 2 consumers. Previous specification work (6 axes, 5 verification types, 3 trigger types, content format, agent context) has been distilled down to what's needed for v1. The Skeptic's recommendation to "build the minimum viable unification" was followed.

---

## Would the User Say "Yes, That's What I Meant"?

### What the user would see:

**Day 1 deliverables:**
1. R01 is phase-scoped — in Phase 5 (Testing), agents can run pytest freely. In other phases, R01 still applies.
2. A "First Pytest" tutorial works: 2-3 steps, each gated by a Check (file exists, command output matches), with phase-scoped hints and guardrails.
3. `/check-setup` runs diagnostic checks on the project environment.

**Would the user recognize this as "what I asked for"?**

The user asked for a tutorial feature. Day 1 delivers one working tutorial + the infrastructure for more. The user also requested infrastructure-first ("v1 is infrastructure, v2 is tutorial") and phase unification ("mode_scope and state are the same thing"). Both are delivered.

**My assessment: Yes.** The user would say "yes, that's what I meant" because:
1. The infrastructure reflects their own reframing (inputs 6-9)
2. A real tutorial works on day 1 (from their example list)
3. R01 phase-scoping works on day 1 (from their explicit example)
4. The path to more tutorials is clear and requires only content, not more infrastructure
5. Nothing they asked for was dropped
6. Nothing they didn't ask for was added (beyond a diagnostic tool)

---

## Risks to Monitor Going Forward

### 1. V2 Must Ship
V1 infrastructure has limited standalone value. The user wants tutorials. Infrastructure is means, not end. V2 must have a concrete milestone.

### 2. "First Pytest" Tutorial Must Be Real
Not a synthetic test. A real, useful tutorial that teaches a scientist to write and run their first pytest. If this tutorial feels thin or forced, the infrastructure isn't serving its purpose.

### 3. Agent-Team Tutorial Needs Explicit Scoping
The architecture doesn't mention it. It was a significant user decision (Input 3). Should be explicitly marked as "v2 — after standard tutorials prove the pattern."

### 4. Don't Over-Generalize Phase
The Phase model serves tutorials and team workflows. Don't extend it to CI pipelines, deployment gates, or other contexts unless there's a concrete user need. The user bounded the infrastructure: "what reusable base functions we need to build a tutorial on top of."

---

## Final Verdict

### ✅ FULLY ALIGNED

Every user input is honored. Nothing lost. Nothing inappropriately added. The architecture is the distilled essence of 9 user inputs, 24 specification files, and team deliberation — collapsed into 2 primitives and 2 day-one consumers.

The user's journey from "add a tutorial feature" → "v1 is infrastructure" → "mode_scope and state are the same thing" is faithfully reflected in the architecture from tutorial spec → infrastructure extraction → Check + Phase unification.

**Proceed to implementation.**
