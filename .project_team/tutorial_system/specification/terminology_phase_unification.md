# Terminology Analysis: Phase as the Unified Primitive

> **Reviewer:** TerminologyGuardian
> **Date:** 2026-04-04
> **Context:** User insight — mode_scope and state are the same thing. The primitive is "phase."

---

## The Conflict

The current `terminology.md` line 92 explicitly **bans** "phase" for tutorial units:

> | phase (for tutorial units) | **tutorial step** | "Phase" is used in the project-team workflow; avoid collision |

Now the user wants "phase" as the **unified infrastructure primitive**. This isn't a terminology drift — it's a deliberate reversal. The ban must be lifted, and the collision must be resolved by design, not avoidance.

---

## Existing "Phase" Usage: 6 Meanings Found

| # | Meaning | Where | How Entrenched |
|---|---------|-------|----------------|
| **1** | **Project-team workflow stages** (Phase 0–9: Vision → Final Sign-Off) | COORDINATOR.md, STATUS.md, agent roles, all project state files | **DEEPLY ENTRENCHED** — core project-team infrastructure. Every `.ao_project_team/<project>/STATUS.md` tracks current phase. Agents activate/deactivate by phase. |
| **2** | **TDD red/green phases** | Test files (`test_intent_*.py`) | LOW — used in comments to label test methodology. Clear from context. |
| **3** | **ClaudeChic worktree FinishPhase** | `submodules/claudechic/` (worktree lifecycle) | NONE — external submodule, internal enum. No collision risk. |
| **4** | **Package download+install phases** | Pixi/SLC comparison docs | NONE — domain-specific, isolated. |
| **5** | **Planning/refactoring phases** | Plan docs | NONE — generic English usage in prose. |
| **6** | **Proposed mode/phase scoping** | `infrastructure_vs_tutorial.md`, `skeptic_infrastructure_review.md` | MEDIUM — already discussing phase-based guardrail scoping as infrastructure. Validates the user's insight. |

**The only real collision is #1: project-team workflow phases.** Everything else is either isolated (submodules), domain-specific, or generic prose.

---

## The Critical Question: Does "Phase" Unify or Collide?

The user's insight is that project-team workflow phases and tutorial steps are **the same underlying primitive**: a named state in a workflow that determines what's allowed and what's complete.

Let me test this:

| Property | Project-Team Phase | Tutorial Step | Same Primitive? |
|---|---|---|---|
| Named state | Phase 3: "Specification" | Step 2: "Copy SSH Key" | ✅ Both are named states |
| Determines what's allowed | "During specification, don't allow code edits" | "During SSH key step, don't delete existing keys" | ✅ Both scope guardrails |
| Determines what's complete | "Specification complete when specs written + reviewed" | "Step complete when SSH key exists" | ✅ Both gate on verification |
| Transition is gated | Phase 3 → 4 requires leadership review | Step 2 → 3 requires checkpoint pass | ✅ Both have gated transitions |
| Has a defined order | Phase 0 → 1 → ... → 9 | Step 1 → 2 → 3 | ✅ Both are sequential |

**Verdict: Yes, these are the same primitive.** The user is correct. The collision isn't a naming problem — it's a recognition that two things we named differently are actually the same thing.

---

## Recommendation: "Phase" IS the Right Word

### Why "phase" and not alternatives

| Candidate | Verdict | Reason |
|---|---|---|
| **phase** | ✅ **RECOMMENDED** | Already the dominant term for this exact concept in the project (Phase 0–9). Using it as the infrastructure primitive UNIFIES rather than collides — project-team phases become instances of the general primitive, not a separate thing. |
| stage | ❌ | Weaker — implies less structure than "phase." No existing usage to anchor it. Introducing a new word when "phase" already means the right thing creates a synonym. |
| state | ❌ | Too generic — "state" means many things (application state, UI state, React state). "Phase" is more specific: a named state *in a workflow* with *scoped behavior*. |
| step | ❌ | Already used for a different granularity in the codebase. "Steps" within a tutorial phase are the atomic instructions. Overloading "step" to also mean the phase-level grouping would be worse than reusing "phase." |
| cycle | ❌ | Implies repetition. Phases are sequential, not cyclical. |
| milestone | ❌ | Implies achievement/completion, not an active state with scoped behavior. |

### The key argument

We don't need a NEW word. We need to RECOGNIZE that the project-team's "Phase 1–9" already implements the primitive the user described. The infrastructure work is generalizing that pattern so tutorials (and other workflows) can use it too.

Introducing "stage" or another synonym would mean: project-team uses "phase," tutorials use "stage," both mean the same thing — exactly the terminology drift we exist to prevent.

---

## How to Resolve the Collision

The collision resolves through **qualification**, not avoidance:

### Unqualified "phase" = the infrastructure primitive

> **Phase** — A named state in a workflow that determines what's allowed (guardrails) and what's complete (verification). A phase has: an identity (name/ID), scoped guardrails (active only in this phase), and a transition gate (verification that must pass before advancing to the next phase).

### Qualified "phase" = specific instances

| Qualified Term | Meaning |
|---|---|
| **Project-team phase** | A phase in the project-team workflow (Phase 0–9). Example: "Phase 3: Specification." |
| **Tutorial phase** | A phase in a tutorial workflow. Example: "Phase: Generate SSH Key." (What we've been calling "tutorial step.") |
| **Phase transition** | Moving from one phase to the next, gated by verification. General infrastructure. |
| **Phase-scoped guardrail** | A guardrail rule that activates/deactivates based on the current phase. General infrastructure. |

### The hierarchy

```
Phase (infrastructure primitive)
 ├── Project-Team Phase (instance: Phase 0–9 in COORDINATOR workflow)
 ├── Tutorial Phase (instance: steps in a tutorial sequence)
 └── [Future] Migration Phase, Onboarding Phase, etc.
```

---

## What Changes

### Ban reversed

| Old Ban | New Rule |
|---|---|
| "phase (for tutorial units) → tutorial step" | **LIFTED.** "Phase" is now the canonical infrastructure term. Tutorial phases ARE phases. |

### Term renames

| Old Term (from terminology_infrastructure_update.md) | New Term | Reason |
|---|---|---|
| Step | **Phase** | The user's insight: steps are phases. The granularity unifies. |
| Scoped Mode | **Phase** (subsumes it) | A "mode" was just "a named state with scoped behavior" — that's a phase. Modes don't exist separately from phases. |
| Scoped Guardrail | **Phase-scoped guardrail** | More precise — scoped to a specific phase. |
| ModeContext | **PhaseContext** | The runtime snapshot of which phase is active, injected into ProjectState. |
| ProgressStore | **PhaseProgressStore** | Tracks phase progression: current phase, completed phases, verification evidence. |
| Manifest | **Manifest** *(unchanged)* | Declares the phase sequence. Still general. |
| Checkpoint | **Phase transition gate** or **Checkpoint** *(either works)* | The verification that must pass before a phase transition. "Checkpoint" is already understood; "phase transition gate" is more precise but verbose. |

### "Step" demoted to sub-phase granularity

If "phase" replaces what we called "tutorial step," what happens to the atomic instructions within a phase?

**Proposal:** "Step" becomes the sub-phase granularity — the individual instructions within a phase's content. A tutorial phase has markdown content containing multiple steps (numbered instructions). The phase is the unit with verification; steps are the instructions within it.

```
Tutorial Phase: "Generate SSH Key"
  Step 1: Check if you already have a key (instruction)
  Step 2: Run ssh-keygen (instruction)
  Step 3: Verify the files exist (instruction)
  [Phase transition gate: file-exists-check on ~/.ssh/id_ed25519]
```

This matches natural language: "We're in the SSH key generation **phase**. Follow these **steps**."

---

## Impact on Project-Team Workflow

The project-team's Phase 0–9 are already phases under this definition. No rename needed. What changes:

1. **COORDINATOR.md** phases gain a formal definition they didn't have before — they're instances of the infrastructure Phase primitive.
2. **Phase-scoped guardrails** become possible for project-team phases too: "In Phase 3 (Specification), block code edits." This was already discussed in `infrastructure_vs_tutorial.md` line 96.
3. **Phase transitions** in the project-team can use the same verification infrastructure: "Phase 3 → 4 requires: all spec files written, skeptic review complete, user approval."

This is a UNIFICATION — the project-team workflow becomes a consumer of the same infrastructure that tutorials use.

---

## Updated Infrastructure Terminology (v1)

```
Phase (named workflow state with scoped behavior)
 ├── Phase transition (gated move to next phase)
 ├── Phase transition gate (verification check required to transition)
 ├── Phase-scoped guardrail (guardrail active only in this phase)
 ├── PhaseContext (runtime snapshot: current phase, timing, last verification)
 └── PhaseProgressStore (persistence: completed phases, evidence)

Verification Subsystem (unchanged from previous analysis)
 ├── Verification (protocol: check(ctx) → VerificationResult)
 ├── VerificationResult (seam object: passed, message, evidence)
 ├── VerificationContext (sandboxed read-only system access)
 └── Built-in Implementations (5 types)

Manifest (declares a phase sequence with verification config)
```

---

## Updated Synonym Control

### New bans

| DO NOT USE | USE INSTEAD | Reason |
|---|---|---|
| scoped mode | **phase** | Modes are phases — the user's unification insight |
| tutorial step (as the verification-gated unit) | **tutorial phase** or **phase** | Steps are instructions within a phase, not the gated unit |
| stage | **phase** | Synonym — one name only |
| state (for workflow position) | **phase** | Too generic; "phase" is specific to workflows with scoped behavior |

### Updated bans (from previous terminology.md)

| Old Ban | Status |
|---|---|
| "phase (for tutorial units) → tutorial step" | **REVERSED** — phase is now the correct term |
| "task (for a tutorial unit) → tutorial step" | **UPDATE** → "task (for a phase) → **phase**" |
| All other bans | **UNCHANGED** — walkthrough, lesson, nudge, guide, safety rail bans still apply |

---

## Open Questions for Composability Lead

1. **"Step" demotion** — Is everyone comfortable with "step" meaning the sub-phase instruction level (not the verification-gated level)? This reverses the current spec terminology. All existing axis specs say "step" where they'll now say "phase."

2. **Phase numbering convention** — Project-team uses "Phase 3." Tutorials currently use "step-01." Should tutorial phases be "Phase 1: Generate SSH Key" or keep the current naming? Recommend: phases are named (not numbered) in manifests; presentation can add numbers.

3. **COORDINATOR.md update scope** — The project-team Phase 0–9 definitions in COORDINATOR.md should be recognized as instances of the Phase primitive. Does this require a COORDINATOR.md update, or is it sufficient to note the relationship in infrastructure docs?

4. **PhaseContext vs TutorialContext** — Previous analysis proposed `ModeContext` (now `PhaseContext`). The project-team phases and tutorial phases may need different context fields. Should `PhaseContext` be a single general type, or a protocol with domain-specific implementations (`ProjectTeamPhaseContext`, `TutorialPhaseContext`)?
