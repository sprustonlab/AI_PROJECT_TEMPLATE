# User Alignment Check — Infrastructure Reframe

**Trigger:** User reframed project scope. V1 = infrastructure primitives, V2 = tutorial layer.
**Date:** 2026-04-04

---

## The Reframe

User said:
> "I think v1 is infrastructure, v2 is tutorial. We need to think about the seams between existing systems and define what reusable base functions we need to build a tutorial on top of."

User's key observations:
- Verification types are general primitives, not tutorial-specific
- Progress tracking shouldn't be tutorial-specific
- Mode-aware guardrail scoping is a general thing (team phases, single-mode work, tutorials)
- Agent roles already exist
- "This changes the scope of the project based on the input from the team about what is needed"

---

## Original Request (verbatim, for reference)

> Add a "tutorial" feature to the template that combines md files, a team of agents, hints, and guardrails in a new mode to help users complete a task.

---

## Alignment Analysis

### Is the reframe aligned with the original goal?

**Yes — and it's a mature decision.** Here's why:

The user's original request names five components: md files, agents, hints, guardrails, and a new mode. The team's specification work revealed that **four of these five already exist in the template** in some form:

| User's Component | Already Exists | What's Missing |
|---|---|---|
| md files | Markdown is everywhere in the template | Tutorial-specific content format |
| agents | Agent team infrastructure exists | Tutorial-runner role |
| hints | Full hints pipeline (`HintSpec`, triggers, lifecycle) | Tutorial-specific triggers |
| guardrails | Guardrail engine, `rules.yaml`, enforcement levels | Mode-scoped activation, verification-as-guardrail |
| **new mode** | **No** | **Mode system entirely missing** |

The user is recognizing a pattern the team surfaced: **the tutorial system is largely a composition of existing systems with missing infrastructure seams.** Building those seams as general infrastructure (not tutorial-specific) means:

1. The same verification primitives serve tutorials, CI checks, project setup validation, etc.
2. The same mode-scoping system serves tutorials, team phases, solo work, etc.
3. The same progress tracking serves tutorials, onboarding, project milestones, etc.

**This is not losing sight of the goal — it's finding the right level of abstraction to achieve it.**

### Does the original user goal survive?

✅ **Yes.** The user's vision of "scientist picks a tutorial and gets an interactive walkthrough" is preserved as the V2 deliverable. V1 builds the foundation that makes V2 possible — and also makes the template more capable in general.

The user explicitly acknowledged this is a scope change driven by team input:
> "This changes the scope of the project based on the input from the team about what is needed"

This is a user making an informed decision, not drift.

---

## Risk Assessment: Is the User at Risk?

### ⚠️ RISK 1: Infrastructure without a customer

**The danger:** Building "general purpose" infrastructure that technically works but doesn't actually serve the tutorial use case well. Classic premature abstraction.

**Mitigation already present:** The team has already specified the tutorial system in detail (verification types, content format, guidance integration). The infrastructure isn't being designed in a vacuum — it's being extracted from a concrete spec. This is the **right order**: concrete use case → specification → extract reusable primitives → build primitives → build use case on top.

**My recommendation:** The infrastructure work should be constantly validated against the tutorial spec. Every primitive should have a clear "this is how tutorials will use this" test. If an infrastructure decision can't point to a specific tutorial need, flag it as potential over-engineering.

### ⚠️ RISK 2: V2 never ships

**The danger:** V1 infrastructure is complete, useful for other things, and V2 (the actual tutorial experience) gets deprioritized because the urgent need feels met.

**Mitigation:** The user's original request is clear — they want tutorials. The infrastructure has no user-facing value without V2. The user should set a concrete V2 milestone to prevent this.

**My recommendation:** V1 success criteria should include: "a trivial tutorial (2-3 steps) can be built using only V1 primitives + a thin tutorial layer." This proves V1 is sufficient and creates momentum for V2.

### ✅ NOT A RISK: "Building infra first" losing the end-user experience

Some teams build infrastructure and forget the user. **That's not happening here** because:
1. The user explicitly described the end-user experience in the original request AND the vision
2. The full tutorial specification already exists — it's not being thrown away, it's being layered
3. The infrastructure is being *extracted from* a user-facing spec, not designed abstractly

---

## What the User's Original Words Demand of Infrastructure

Checking each user component against the infra reframe:

### "md files"
**Infra need:** A content format system that can load structured markdown with metadata. Not tutorial-specific — any feature that uses "markdown files with YAML frontmatter as configuration" benefits.
**Alignment:** ✅ Building a general content loader serves tutorials and other template features.

### "a team of agents"
**Infra need:** Agent role system already exists. Tutorial needs one new role (runner). No new infrastructure needed here — this is V2 work (defining the tutorial-runner role).
**Alignment:** ✅ Correctly identified as already existing.

### "hints"
**Infra need:** The hints pipeline exists. Tutorial needs new `TriggerCondition` implementations. These are **new values on an existing axis** — the infrastructure (trigger protocol) is already there.
**Alignment:** ✅ Infrastructure is already built. Tutorial-specific triggers are V2.

### "guardrails"
**Infra need:** Mode-aware guardrail scoping. This IS new infrastructure. Currently guardrails are global (rules.yaml). Tutorials need per-mode activation/deactivation. But so do team phases, solo work, etc.
**Alignment:** ✅ This is the strongest argument for the infra-first approach. General mode-scoping benefits the whole template.

### "in a new mode"
**Infra need:** A mode system. This is the biggest missing piece. The template has no concept of "modes" today. Tutorials need it, but so does any workflow that changes system behavior contextually.
**Alignment:** ✅ This is the core infrastructure gap. Building it generally is the right call.

---

## V1/V2 Split Alignment

### V1 (Infrastructure) — should deliver:
1. **Verification primitives** — General `check(context) → result` protocol, built-in implementations
2. **Mode system** — Enter/exit modes, mode-scoped guardrail activation
3. **Progress tracking** — General step-completion tracking with evidence
4. **Content loading** — YAML manifest + markdown file discovery pattern

### V2 (Tutorial) — should deliver:
1. **Tutorial content format** — tutorial.yaml schema, step markdown conventions
2. **Tutorial-runner agent role** — role file, AgentContext, over-help prevention
3. **Tutorial-specific triggers** — `TutorialStepStuck`, `TutorialVerificationFailed`
4. **Tutorial mode definition** — what "tutorial mode" means as a mode system value
5. **Actual tutorial content** — at least 2-3 real tutorials

### Does the split preserve user intent?
✅ **Yes.** Every user-requested feature lands in V2 at the latest. V1 just builds the pieces that V2 composes. The user will get their tutorials — they'll just also get a more capable template.

---

## Scope Creep Check

### ❓ Is "general infrastructure" scope creep?

The user asked for a tutorial feature. Now V1 is "general infrastructure." Is this scope creep?

**My assessment: No, IF the infrastructure is bounded by tutorial needs.**

The user said: "We need to think about the seams between existing systems and define what reusable base functions we need to build a tutorial on top of." The key phrase is **"to build a tutorial on top of."** The user is bounding the infrastructure to what tutorials need. They're not saying "build a general-purpose mode system for all possible future uses" — they're saying "build the general pieces that tutorials require, and make them general so they serve other uses too."

**This is scope refinement, not scope creep.**

### ⚠️ Watch for: infrastructure that tutorials don't need

If V1 introduces infrastructure that has no tutorial justification, flag it. Examples that would be scope creep:
- A plugin system for verification types (tutorials only need the 5 built-in types)
- A visual mode editor (tutorials just need enter/exit)
- Distributed progress sync (tutorials are local)

---

## Wording Check

### ❓ USER ALIGNMENT: User said "tutorial feature," spec now says "infrastructure primitives"

User's original words: "Add a tutorial feature." The reframe changes the deliverable from "a tutorial feature" to "infrastructure primitives that enable a tutorial feature."

**Is this a problem?** No — because:
1. The user themselves initiated this reframe
2. The user explicitly said "this changes the scope"
3. The end goal (tutorials) is preserved as V2
4. The user's reasoning is sound (primitives should be general)

**But:** The project name should still reference tutorials. Calling it "infrastructure project" would lose the thread. The user should see "Tutorial System — Phase 1: Infrastructure" not "General Template Infrastructure."

---

## Final Verdict

### ✅ ALIGNED — This is a mature scope refinement, not drift.

The user is doing what good architects do: looking at a feature request, recognizing that the right implementation is to build reusable foundations first, and explicitly choosing to layer the feature on proven infrastructure.

**The original goal is preserved.** Scientists will still get interactive tutorials with markdown content, agent guidance, hints, guardrails, and a dedicated mode. They'll just get it built on top of solid, reusable infrastructure — which is better than a tutorial-specific silo.

### Conditions for continued alignment:
1. **V1 must be bounded by tutorial needs** — don't build infrastructure tutorials won't use
2. **V1 must prove itself with a trivial tutorial** — "can we build a 3-step tutorial with just V1 primitives?" is the acceptance test
3. **V2 must have a concrete milestone** — date or trigger, not "someday"
4. **The project should keep "tutorial" in its name** — to maintain the connection to the user's original intent

### My role going forward:
I'll continue checking that infrastructure decisions serve the tutorial use case. If V1 work drifts toward generality that tutorials don't need, I'll flag it. The user's original words remain the source of truth — the reframe is an implementation strategy, not a goal change.
