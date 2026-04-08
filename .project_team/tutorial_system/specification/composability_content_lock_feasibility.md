# Composability Response: Content Lock Feasibility

**Reviewer:** Composability (Lead Architect)
**Prompt:** Researcher found content lock is attention management (~80%), not security enforcement. Does the architecture need adjustment?

---

## The Asymmetry

The two-lock model has an asymmetry I should have caught:

| Lock | Enforcement | Mechanism |
|---|---|---|
| **Guardrail lock** | **Hard** — system-level, exit code 2, agent cannot bypass | Generated hooks, `phase_guard.py`, `phase_state.json` |
| **Content lock** | **Soft** — prompt-level, agent can read other files | Agent prompt only contains current phase file; warn guardrail on reading other phase files |

The guardrail lock is a wall. The content lock is a suggestion. They're not the same kind of thing.

---

## Does This Break the Compositional Law?

### Old law (from phase_content_lock.md):
> "Agent content boundary and guardrail scope derive from the same phase file selection — one source, two projections, can't desync."

### Reality:
They CAN desync. The agent can read `phase-05-testing.md` while guardrails scope to `phase-04-implementation`. The guardrails still enforce Phase 4 rules (the agent can't run unrestricted pytest), but the agent has Phase 5 knowledge.

### Does this matter?

**For guardrails: No.** The guardrail lock doesn't care what the agent knows. It cares what the agent does. If R01 blocks full pytest in Phase 4, reading Phase 5's instructions doesn't let the agent bypass R01. The enforcement is on the action, not on the knowledge.

**For checks (gates): No.** The advance_checks still run. Even if the agent knows Phase 5 exists, it can't advance without passing Phase 4's gate checks. The gate is in the engine, not in the agent's head.

**For hints: No.** Hints scope to `active_phase.phase_id`. The agent reading a different phase file doesn't change what hints fire.

**For workflow correctness: Marginal.** An agent that reads ahead might try to do Phase 5 work during Phase 4. But the guardrails catch the actions that matter (like running full pytest). The agent might write code that anticipates Phase 5, but that's not harmful — it's just premature.

---

## Revised Assessment

The content lock was never load-bearing. The architecture doesn't depend on it. Here's why:

### What actually enforces phase correctness:

```
phase_state.json
    │
    ├── Guardrail lock (HARD): rules scoped to current phase
    │   → Agent can't DO wrong-phase actions
    │
    ├── Gate lock (HARD): advance_checks must pass
    │   → Agent can't ADVANCE without proof
    │
    └── Hint lock (HARD): hints scoped to current phase
        → Agent gets right-phase guidance
```

### What the content lock adds:

```
Content lock (SOFT): agent only receives current phase instructions
    → Agent is less likely to ATTEMPT wrong-phase actions
    → Reduces guardrail friction (fewer denied actions)
    → Better agent focus and output quality
```

The content lock is a **performance optimization**, not a **safety mechanism**. It reduces wasted agent turns on actions that guardrails would deny anyway. That's valuable but not architectural.

---

## Architecture Adjustment

### The law needs revision

**Old (aspirational):**
> "Content and guardrail scope derive from the same phase file selection — can't desync."

**New (accurate):**
> "Phase correctness is enforced by guardrail scoping and gate checks. Content scoping is a best-effort optimization that reduces friction by limiting the agent's prompt to the current phase."

Or more concisely:

**Compositional law (revised):**
1. All checks produce `CheckResult` (unchanged)
2. All phase consumers read `phase_state.json` (unchanged) — this is the enforcement
3. Agent prompt is scoped to the current phase file — this is optimization, not enforcement

### The two-lock framing was wrong

It's not two locks. It's one lock (guardrails + gates, hard) and one lens (content scoping, soft). Calling them both "locks" implied equal enforcement. They're not equal.

**Better framing:**
- **Phase enforcement:** guardrail scoping + gate checks (hard, system-level)
- **Phase focus:** content scoping (soft, prompt-level, ~80% effective)

Both are useful. Only one is load-bearing.

---

## Does Anything Change in the Implementation?

### No structural changes needed.

The file-per-phase structure is still correct — not because it enforces a content lock, but because:

1. **It's cleaner.** Separate files per phase is better file organization regardless of enforcement.
2. **It simplifies agent prompts.** Loading one file instead of parsing a 275-line document for the relevant section.
3. **It co-locates guards with content.** Frontmatter + body in one file means the phase definition is atomic.
4. **It enables the soft content lock.** Even at ~80%, reducing unnecessary agent actions is worth doing.

### The warn guardrail on reading other phase files is still worth adding.

Not as a "lock" — as friction. The agent CAN read other phase files, but it'll get a warning that nudges it back. This is the same pattern as existing guardrails: R01 doesn't make `pytest` impossible, it makes it require the right invocation. A phase-read warning doesn't make reading impossible, it makes the agent reconsider.

### phase_state.json remains the single source of truth.

This was always the enforcement point. The content lock finding doesn't change this. Guardrail hooks read `phase_state.json`. Gate checks run from the engine. Both are hard enforcement. Both remain.

---

## Impact on Phase Primitive

None. The `PhaseMeta` type (parsed from frontmatter) is unchanged. The `ActivePhase` type is unchanged. `phase_state.json` is unchanged. The Check primitive is unchanged.

The only change is in how we describe the architecture:

| Before | After |
|---|---|
| "Two locks, inherently synced" | "One enforcement layer (guardrails + gates) + one optimization layer (content focus)" |
| "Can't desync" | "Enforcement can't be bypassed; focus is best-effort" |
| Content lock is load-bearing | Content lock is performance optimization |

---

## Summary

The Researcher's finding is correct and important, but it doesn't weaken the architecture — it sharpens the description of what's load-bearing and what isn't.

**Load-bearing (hard enforcement):**
- `phase_state.json` → guardrail scoping
- `advance_checks` → gate enforcement
- Both are system-level, agent-proof

**Optimization (soft focus):**
- Agent prompt scoped to current phase file
- Warn guardrail on reading other phase files
- ~80% effective, reduces friction

The architecture stands. The law is revised to be accurate about what's enforced vs. what's optimized. No structural changes needed.
