# User Alignment Check — Content Lock (Agent Knowledge = Phase)

**Trigger:** User insight — "Only give it the md file per phase to read. That would sync the agentic and guardrail checkpoint behavior."
**Date:** 2026-04-04

---

## The User's Insight

The agent should only see the markdown file for the current phase. It doesn't get the full tutorial — it gets one step at a time. This means:

- **What the agent knows** = the current phase's MD file
- **What guardrails enforce** = the current phase's rules
- **What must be proven to advance** = the current phase's checks

All three derive from the same phase identity. They **cannot desync** because there's only one source of truth: which phase is active.

---

## Is This a Third Unification?

The user has now unified three things under the phase concept:

| Unification | User's Words | What It Means |
|---|---|---|
| **1. Guardrails + Verification** | "Guardrails are not only preventing bad things, they are also used as checkpoints" | Phase has both `activate_rules` (prevention) and `advance_checks` (proof) |
| **2. mode_scope + state** | "What IS common between verification and guardrails? mode_scope and state are the same thing" | Phase is the single primitive that scopes everything |
| **3. Agent knowledge + Phase scope** | "Only give it the md file per phase to read" | The agent's context window IS phase-scoped — it literally can't act on future steps because it can't see them |

**Yes, this is a third unification.** And it's the most elegant one, because it turns an enforcement problem into an information problem:

- **Before:** The agent sees the whole tutorial. Guardrails must *prevent* it from jumping ahead, doing future steps, or spoiling upcoming content. Enforcement is complex — you need rules for every way the agent could misbehave.
- **After:** The agent only sees the current step's MD file. It *can't* jump ahead because it doesn't know what's ahead. It *can't* spoil content because it hasn't read it. The constraint is structural, not behavioral.

This is the same principle as the existing agent-assist design in axis_guidance.md §4 — the `AgentContext` is a read-only frozen snapshot, not a reference to the engine. The user's insight extends this: don't just limit the agent's *actions* — limit its *knowledge* to the current phase.

---

## Alignment with Previous Inputs

### Input 5: "Guardrails as checkpoints"

The content lock reinforces this. The agent can't claim a step is done by reading ahead to see what's expected. It must actually help the user do the work, then the check proves it happened. The agent's limited knowledge makes the checkpoint meaningful — it's not checking work the agent already knew the answer to.

### Input 7: "mode_scope and state are the same thing"

The content lock is the third facet of this. A phase now determines:
1. What's **allowed** (guardrail rules) — mode_scope
2. What's **required** (advance checks) — state
3. What's **known** (agent context) — NEW: knowledge scope

All three = same phase identity. The user is deepening their own insight, not changing direction.

### Input 6: "v1 is infrastructure, v2 is tutorial"

Content lock is cleanly a Phase primitive behavior, not a tutorial-specific feature. Any workflow could lock agent context to the current phase:
- Tutorial: agent sees only the current step's instructions
- Team project: Implementer sees only its assigned task file, not the full architecture
- Onboarding: agent sees only the current setup step

This is general infrastructure.

### Original request: "combines md files, agents, hints, and guardrails in a new mode"

The user listed **md files** and **agents** as separate components that get **combined**. The content lock IS the combination mechanism — the phase binds a specific MD file to a specific agent context. This is more faithful to the original request than treating content and agents as independent axes.

---

## What This Changes in the Architecture

### Phase Definition Gets a Content Field

```python
@dataclass(frozen=True)
class Phase:
    id: str
    description: str

    # Facet 1: Guards (what's allowed)
    activate_rules: tuple[str, ...] = ()
    deactivate_rules: tuple[str, ...] = ()

    # Facet 2: Gates (what advances)
    advance_checks: tuple[Check, ...] = ()

    # Facet 3: Context (what hints are active)
    hints: tuple[HintDeclaration, ...] = ()

    # Facet 4: Knowledge (what the agent sees)  ← NEW
    content_file: str | None = None  # Path to MD file for this phase
```

The workflow engine, when building agent context, reads `phase.content_file` and provides ONLY that content to the agent. The agent's system prompt is scoped to the current phase.

### Agent Over-Help Prevention Becomes Structural

The axis_guidance.md spec (§4) designed agent constraints as:
1. Read-only `AgentContext` (soft — agent can still reason about what it knows)
2. `agent_blocked_commands` guardrail rules (hard — block specific commands)

Content lock adds a third, more fundamental layer:
3. **The agent simply doesn't have the information** to act beyond the current phase

This is defense in depth:
- Layer 1: Agent role instructions say "don't do the work for the user"
- Layer 2: Guardrail rules block specific commands
- Layer 3: Agent can't see future steps, so it can't anticipate or shortcut

Layer 3 is the strongest because it requires no enforcement — it's a structural impossibility.

### The Skeptic's F5 (Agent Over-Help) Is More Fully Resolved

The Skeptic rated agent over-help as HIGH risk (#2 after checkpoint reliability). The content lock doesn't eliminate the risk within a single step (agent can still do the current step's work for the user), but it eliminates the risk across steps (agent can't pre-solve future steps or leak future content).

---

## Scope Check

### Is this scope creep?

No. The user is adding a facet to a primitive they already defined (Phase). The Phase already has guards, gates, and context. Adding knowledge-scope is the same pattern — another facet determined by phase identity. It doesn't add a new primitive or a new consumer.

### Does it add complexity?

Minimal. The workflow engine already builds agent context. Instead of passing "the whole tutorial" to the agent, it passes "the current phase's MD file." This is simpler, not more complex — less content to manage in the agent's context window.

### Does it conflict with anything?

No. The existing AgentContext design (axis_guidance.md §4) was already constrained and read-only. Content lock makes it *more* constrained in the right direction.

---

## The Four Facets of Phase (Updated)

```
Phase
 ├── Guards:    What's ALLOWED     (activate_rules, deactivate_rules)
 ├── Gates:     What's REQUIRED    (advance_checks)
 ├── Context:   What HELP is shown (hints)
 └── Knowledge: What's KNOWN       (content_file)  ← NEW

All four derive from: which phase is active.
All four change atomically on phase transition.
None can desync because there's one source of truth.
```

This is the complete phase model. Guards prevent bad actions. Gates require proof. Context provides guidance. Knowledge scopes what the agent can even think about. A single phase transition updates all four simultaneously.

---

## Verdict: ✅ ALIGNED — Strengthens the architecture

This is the user's most architecturally elegant insight. It:

1. **Follows directly from their earlier unifications** — guardrails + verification, then mode_scope + state, now agent knowledge + phase scope. Each narrows the gap between "what should happen" and "what can happen."
2. **Matches their original request** — "combines md files [and] agents" — the content lock IS the combination mechanism.
3. **Simplifies enforcement** — structural impossibility > behavioral constraint > rule enforcement.
4. **Adds no complexity** — less content to manage, not more. One field on Phase.
5. **Is general infrastructure** — any workflow can scope agent knowledge to the current phase.

### One recommendation:

The Phase model now has four facets. Document them as a set — "The Four Facets of Phase" — so the team understands that adding content_file isn't just "another field" but the completion of a unified model where phase identity governs everything the agent is, knows, can do, and must prove.
