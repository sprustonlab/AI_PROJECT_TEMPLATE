# User Alignment Check — Phase Unification (Guardrails + Verification)

**Trigger:** User unified guardrails and verification under a shared "phase" concept.
**Date:** 2026-04-04

---

## The User's Insight

> "What IS common between verification and guardrails? mode_scope and state are the same thing."

User's mental model: A **phase** determines both:
- **What's allowed** (guardrails) — scoped rules active during this phase
- **What's complete** (verification) — conditions that prove this phase is done

Example from team workflows: phase 4 blocks full test suite (guardrail), phase 5 allows it (different guardrail scope). The phase transition from 4→5 requires verification that phase 4's work is done.

---

## Original Request Check

User said:
> "...that combines md files, a team of agents, **hints**, and **guardrails** in a new mode to help users complete a task."

The user listed guardrails as a component. The vision expanded guardrails to include verification ("the agent can't just say done — the guardrails prove it"). Now the user is **explicitly confirming** that guardrails and verification are two faces of the same concept: phase-scoped state.

**This is not a reinterpretation — the user is articulating what they meant all along.** The original request didn't separate "guardrails" and "verification" — the team did during specification. The user is now re-merging them, which is closer to the original intent.

---

## Does This Serve the Tutorial Use Case?

### Tutorial step as phase — mapping

| Phase concept | Tutorial equivalent | Example (SSH tutorial, step 2: "copy key to cluster") |
|---|---|---|
| Phase identity | Tutorial step ID | `copy-key` |
| What's allowed (guardrails) | Per-step guardrails | Block agent from running `ssh-copy-id` for the user |
| What's complete (verification) | Step checkpoint | `ssh -o BatchMode=yes host echo ok` returns "ok" |
| Phase transition | Step advancement | Move to step 3 only when checkpoint passes |
| Phase scope | Step-active guardrails activate/deactivate | `T-SSH-001` active during steps 1+3, inactive during step 2 |

### ✅ The mapping is clean

In the tutorial spec, every step already has:
- `guardrails: [T-SSH-001]` — what's blocked during this step
- `verification: { type: command-output-check, ... }` — what proves this step is done

The team treated these as separate axes (Safety and Verification in the composability analysis). The user is saying: **these are both expressions of the same phase.** A phase declares its guardrail scope AND its exit criteria.

This is correct. In the tutorial spec:
- Guardrails activate when you enter a step and deactivate when you leave
- Verification gates the exit from a step
- Both are scoped to the same unit: the step (= phase)

### ✅ Generalizes beyond tutorials

The user's team-workflow example proves this isn't tutorial-specific:
- Team phase 4 (specification): block implementation commands (guardrail), require spec files complete (verification)
- Team phase 5 (architecture): allow implementation planning (different guardrails), require architecture doc (different verification)
- Solo work mode: permissive guardrails, no phase-gated verification

Same primitives, different phase definitions. The tutorial is just one kind of phased workflow.

---

## Alignment Impact

### What changes?

**Before unification:**
- Verification axis: standalone protocol, 5 types, `VerificationResult`
- Safety axis: guardrail rules scoped per-step
- These were separate axes in the composability analysis

**After unification:**
- A **phase** declares both its guardrail scope and its exit verification
- The primitives (verification types, guardrail rules) stay the same
- What changes is the **organizing concept** — phase is the shared container

### Does anything get lost?

❓ **Can guardrails exist without verification?** Yes — some phases have guardrails but no formal exit gate. Solo work mode might restrict certain commands but have no "completion" concept. The unified model must allow phases with guardrails-only (no verification) and phases with verification-only (no special guardrails).

**Check against user's words:** The user said "mode_scope and state are the same thing." This means a phase HAS scope (guardrails) and state (progress/verification), but either can be empty. A phase with only guardrails is still a phase. A phase with only verification is still a phase.

✅ **Nothing is lost.** The unification is additive — it puts two existing concepts under one roof without requiring both to always be present.

### Does anything get gained?

Yes:
1. **Simpler mental model** — Authors (tutorial writers, team workflow designers) think in phases, not in separate "guardrail scope" and "verification gate" concepts
2. **Single configuration point** — A phase definition declares everything about that phase in one place
3. **Consistent lifecycle** — Enter phase → guardrails activate + verification becomes checkable. Exit phase → guardrails deactivate + verification evidence recorded. One lifecycle, not two.
4. **The tutorial mode lifecycle gap is resolved** — The Skeptic and I both flagged the missing tutorial mode state machine. If steps are phases, and phases have a defined lifecycle (enter/active/exit), the state machine comes for free.

---

## Specific Alignment Checks

### ❓ Does "phase" clash with existing terminology?

`terminology.md` banned the word "phase" for tutorial units:
> "phase (for tutorial units) → USE tutorial step — 'Phase' is used in the project-team workflow; avoid collision"

**But the user is now intentionally unifying these.** Tutorial steps and team phases are the same concept at different scales. The terminology guidance was protecting against accidental collision. The user is now making the collision deliberate and productive.

**Recommendation:** Update terminology. "Phase" becomes the general infrastructure term. "Tutorial step" remains the tutorial-specific name for a phase instance. A tutorial step IS a phase. A team workflow stage IS a phase. No collision — just a shared abstraction.

### ❓ Does the composability analysis survive?

The 6-axis decomposition had separate Verification and Safety axes. Under unification, these become two aspects of a single Phase concept. Does this break the crystal test?

**No.** The axes still exist as concerns — verification logic and guardrail rules are still independently authored and independently vary. What changes is that they're **co-scoped** by phase, not independently scoped. A phase activates specific guardrails AND specific verification. But you can still combine any verification type with any guardrail set — the phase just bundles them.

Think of it as: the axes are still orthogonal in implementation, but they share a lifecycle via the phase container.

### ⚠️ Does the user's original "guardrails" wording still hold?

User said "guardrails." The unification doesn't rename guardrails — it places them inside phases. Guardrails are still guardrails. They're just phase-scoped guardrails.

✅ **Wording preserved.** The user is adding structure (phases), not changing names.

---

## Risk Assessment

### ⚠️ RISK: Over-abstraction of "phase"

If "phase" becomes too general, it could mean everything and nothing. A tutorial step, a team workflow stage, a deployment gate, a CI pipeline step — all "phases"?

**Mitigation:** The user bounded it: "mode_scope and state are the same thing." Phase = scope (what's allowed) + state (what's done). If something has both of these, it's a phase. If it only has one, it still fits (with the other empty). If it has neither, it's not a phase.

**My recommendation:** Keep the phase concept grounded in the tutorial use case for V1. If it naturally extends to team workflows, great. Don't go looking for more phase-shaped things to unify.

### ✅ NOT A RISK: Losing the tutorial experience

The unification is an infrastructure-level insight. The tutorial user experience is unchanged:
- User still picks a tutorial
- Steps still have instructions, hints, verification
- Agent still guides, guardrails still protect, checkpoints still prove
- The user just doesn't know (or care) that steps are "phases" under the hood

---

## Verdict: ✅ ALIGNED — Strengthens both infrastructure and tutorial

The unification:
1. **Matches the user's original intent** — they listed guardrails as one concept, the team split it into two (safety + verification), and the user is re-merging them under "phase"
2. **Resolves a spec gap** — the missing tutorial mode lifecycle state machine is now just the phase lifecycle
3. **Generalizes correctly** — team workflows and tutorials share the same phase concept because they genuinely are the same pattern
4. **Preserves all existing specification work** — verification types, guardrail rules, hint integration all survive unchanged; only the organizing container changes

### Conditions:
1. Phase must allow guardrails-only or verification-only (not always require both)
2. "Tutorial step" remains the user-facing term for tutorials; "phase" is the infrastructure term
3. V1 infrastructure should demonstrate phases working for tutorials AND at least one non-tutorial use case (team workflow phases) to validate generality
4. Don't hunt for more things to unify under "phase" — let the concept prove itself on the two known use cases first

Standing by for architecture.
