# Terminology Analysis: Content Lock

> **Reviewer:** TerminologyGuardian
> **Date:** 2026-04-04
> **Context:** User insight — the agent only receives the MD for its current phase, creating a knowledge boundary that syncs with guardrail enforcement.

---

## The Concept

The user's insight is that the agent's knowledge boundary should align with the phase boundary. The agent doesn't get the full tutorial — it gets ONE phase file. When the phase transitions, it gets the NEXT file. The agent literally cannot help with step 3 while on step 2, because it doesn't have step 3's content.

This creates a powerful alignment: what the agent **knows** (content), what the agent **can do** (guardrails), and what must be **proven** (checks) all scope to the same unit — the phase.

---

## Does "Content Lock" Conflict with Existing Terms?

### "lock" usage in the codebase (161 occurrences)

| Context | Meaning | Files | Collision Risk |
|---|---|---|---|
| **pixi lock / pixi.lock / lockfile** | Dependency lockfile — frozen set of resolved package versions | `scripts/import_env.py`, `pixi.lock`, corrections_report.json, composable_plugins specs | **MEDIUM** — "lock" in this codebase primarily means "lockfile" (dependency pinning). "Content lock" would be a different meaning. |
| **Lock inheritance / seqlock** | Concurrency primitives (from SYNC_COORDINATOR.md) | `AI_agents/project_team/SYNC_COORDINATOR.md` | **LOW** — concurrency domain, clearly different context. |
| **"the lock"** (TERMINOLOGY_GUARDIAN.md) | Example of an ambiguous implicit reference | `AI_agents/project_team/TERMINOLOGY_GUARDIAN.md` | **NONE** — it's an example of bad terminology, not a defined term. |
| **ecosystem lock-in** | Vendor lock-in (from COMPOSABILITY.md) | `AI_agents/project_team/COMPOSABILITY.md` | **NONE** — different domain entirely. |
| **filelock** | Python filelock dependency in pixi.lock | `pixi.lock` | **LOW** — internal dependency, not user-facing. |

### Verdict on "lock"

**"Lock" is overloaded in this codebase, but the primary meaning is "lockfile" (dependency pinning).** "Content lock" would introduce a FOURTH meaning of "lock" alongside: (1) dependency lockfile, (2) concurrency lock, (3) vendor lock-in. This is a terminology smell — same word, different meanings.

However, "content lock" is a compound noun, and it's distinct enough in context that confusion is unlikely. Nobody reading "content lock" would think "pixi.lock." The bigger question is whether "lock" is the **right metaphor** for what's happening.

---

## Is "Lock" the Right Word?

### What "lock" implies

"Lock" carries these connotations:
1. **Something was open and is now closed** — implies restricting something that was previously accessible
2. **Exclusion / prevention** — you lock a door to keep others out
3. **Intentional constraint** — locking is a deliberate security/safety action
4. **Static / frozen** — locked things don't change

### What the concept actually IS

The agent receives ONLY the current phase's markdown. It doesn't have future phases. It doesn't have past phases (or at least, they're not in its active context). The content boundary = phase boundary.

This is less about "locking something that was open" and more about **scoping what the agent can see**. The agent was never given all phases and then restricted — it was only ever given one phase at a time.

### Candidate terms

| Candidate | Connotation | Fits? |
|---|---|---|
| **content lock** | Something locked down; restricted | ⚠️ Implies content was accessible and is now restricted. In reality, future content was never given. |
| **content scope** | What's visible/in-scope | ✅ Accurate — the agent's content is scoped to the current phase. But "scope" is already overused in this project (guardrail scope, phase scope, etc.). |
| **content boundary** | Edge of what's known | ✅ Accurate — the boundary between what the agent knows and doesn't know. But passive — doesn't capture the enforcement aspect. |
| **phase file** | The specific file for this phase | ✅ Concrete — names the artifact. But describes the FILE, not the PATTERN of restricting knowledge. |
| **content gate** | Content is gated per phase | ⚠️ "Gate" already means "check that must pass to advance" in the phase model. Adding "content gate" overloads "gate." |
| **knowledge boundary** | Limit of what the agent knows | ✅ Accurate but academic-sounding. |
| **phase-scoped content** | Content scoped to the active phase | ✅ Follows existing pattern (phase-scoped guardrail). Consistent. Slightly verbose. |
| **content lock** (revisited) | Agent's content is locked to current phase | ✅ Actually, on reflection: "locked TO" a phase is different from "locked" in the lockfile sense. The metaphor is "locked in position" — content is pinned/locked to the phase, not locked as in encrypted/frozen. |

### Recommendation: **"Content lock" is acceptable, with a precise definition**

The term works IF defined precisely. The metaphor is "content locked to the current phase" — not "content that's been locked down." It's analogous to "phase lock" in signal processing (output locked to input frequency) rather than "file lock" in concurrency.

**But** if the team wants maximum clarity with zero ambiguity, **"phase-scoped content"** follows the existing naming pattern (phase-scoped guardrail, phase-scoped hint) and requires no metaphor interpretation.

**My recommendation: Accept "content lock" as the concept name, but define it with zero ambiguity. Use "phase file" for the artifact.**

---

## Term Definitions

### Content Lock

The enforcement pattern where the tutorial-runner agent receives ONLY the markdown content for the current phase — never future phases, and no longer past phases (unless explicitly retained for context). The agent's knowledge boundary aligns with the phase boundary, creating a three-way sync:

- **What the agent knows** (content lock) = current phase file
- **What the agent can do** (phase-scoped guardrails) = current phase's allowed actions
- **What must be proven** (gate checks) = current phase's advance conditions

This alignment is the core design insight: by controlling what the agent sees, the system ensures the agent's guidance is naturally scoped to the current phase without needing explicit per-phase instructions to "ignore future steps."

> **Disambiguation:** "Lock" here means "locked to" (pinned to the current phase), NOT "lockfile" (dependency pinning) or "concurrency lock" (mutual exclusion). If ambiguity arises, use the full phrase "content lock" — never bare "lock."

### Phase File

The single markdown file that contains the instructional content for one phase. When a phase is active, the tutorial-runner agent receives this file (and only this file) as its operational context.

Phase files are the artifacts that `axis_content.md` calls "step markdown files" (e.g., `step-01-generate-key.md`). Under the phase model, the naming convention becomes `phase-01-generate-key.md` (or the existing `step-NN-*.md` if the YAML key stays `steps:` for author friendliness).

> **Relationship to Tutorial Content:** "Tutorial content" (from terminology.md) is the full set of phase files for a tutorial. A "phase file" is one file from that set — the one active during the current phase.

### Phase Transition (updated definition)

A phase transition now involves three synchronized changes:

1. **Content lock update** — the agent receives the next phase's file (replacing the current one)
2. **Phase state update** — `phase_state.json` updated with new current phase
3. **Guardrail swap** — previous phase's rules deactivated, new phase's rules activated

These are atomic — they happen together as a single operation by the WorkflowEngine. The content lock ensures the agent's knowledge transitions at exactly the same moment as the guardrails and state.

---

## How This Relates to Existing Concepts

### AgentContext (from axis_guidance.md)

The `AgentContext` dataclass already implements a proto-content-lock:

```python
class AgentContext:
    step_content: str  # The step's markdown — what to teach
```

The `step_content` field is exactly the content lock — it's the phase file's content injected into the agent's prompt. The user's insight formalizes this as a named pattern with intentional enforcement, not just a convenience.

**What changes:** The `AgentContext` is no longer just "helpful context for the agent." It's the **enforcement mechanism** for the content lock. The agent's system prompt contains ONLY the current phase file, which means the agent literally cannot reference future phase content because it doesn't exist in its context window.

### The Three-Way Sync (new concept)

This is the real insight. The content lock completes a three-facet alignment that was implicit but never named:

```
Phase
 ├── Content lock:     agent sees ONLY this phase's file
 ├── Phase-scoped guardrails: agent CAN DO only this phase's allowed actions
 └── Gate checks:      agent must PROVE this phase's conditions before advancing
```

All three scope to the same unit. This is what makes the phase primitive powerful — it's not just three independent facets, it's three facets that are intentionally aligned to the same boundary.

> **Proposal:** The "three-way sync" should be named or at least documented as a design invariant. Possible name: **phase coherence** — the property that content, guardrails, and checks are all scoped to the same phase boundary. If any of the three gets out of sync (e.g., agent sees phase 3 content but phase 2 guardrails are active), the system is in an incoherent state.

---

## Synonym Control

| DO NOT USE | USE INSTEAD | Reason |
|---|---|---|
| content scope (as a noun) | **content lock** | "Scope" is overloaded (guardrail scope, phase scope, variable scope) |
| knowledge boundary | **content lock** | Too academic; "content lock" is concrete |
| content gate | **content lock** | "Gate" already means "check-that-must-pass" in the phase model |
| context restriction | **content lock** | Implies something negative; content lock is a design feature |
| phase content | **phase file** | "Phase content" is ambiguous (the concept? the file? the text?); "phase file" names the artifact |
| step file (in new docs) | **phase file** | Layer 3 terminology: phases, not steps |

---

## Impact on Existing Specs

### `axis_guidance.md` — AgentContext

The `AgentContext.step_content` field should be recognized as the content lock mechanism. When this spec is updated to Layer 3 terms:
- `step_content: str` → `phase_content: str` (or `phase_file_content: str`)
- `step_number: int` / `total_steps: int` → `phase_number: int` / `total_phases: int`
- The docstring should reference the content lock pattern

### `axis_content.md` — Step markdown files

The per-phase markdown files are phase files. The naming convention may change from `step-NN-*.md` to `phase-NN-*.md`, or stay as-is if the YAML key remains `steps:` (pending design decision from v2 review).

### `unified_phase_model.md` — Phase dataclass

The Phase dataclass currently has:
```python
class Phase:
    id: str
    description: str
    activate_rules: tuple[str, ...]
    deactivate_rules: tuple[str, ...]
    advance_checks: tuple[Check, ...]
    hints: tuple[HintDeclaration, ...]
```

It does NOT reference content. This is deliberate — the Phase is an infrastructure primitive that doesn't know about markdown. But the tutorial system's USE of Phase should add:
```python
class TutorialPhase(Phase):  # or: tutorial-layer extension
    content_file: str  # Path to the phase file (the content lock artifact)
```

Or, the manifest's `phases[n].file` field in YAML serves this purpose. The content lock is enforced by the WorkflowEngine: on phase transition, load the new phase's `file` and inject it into the agent's context, replacing the old content.

---

## Open Questions for Composability Lead

1. **Past phase content retention** — Should the agent retain any knowledge of completed phases? Options:
   - **(a) Strict lock:** Agent sees ONLY current phase file. No memory of past phases.
   - **(b) Cumulative:** Agent sees current phase + summary of completed phases.
   - **(c) Sliding window:** Agent sees current phase + previous phase (for context continuity).

   Strict lock is simplest and cleanest. Cumulative risks context window bloat. Sliding window is a pragmatic middle ground. Recommend (a) for v1.

2. **"Phase coherence" as a named invariant** — Should the three-way sync (content lock + guardrails + checks all scoped to same phase) be formalized as an invariant called "phase coherence"? It's a strong design property worth naming.

3. **Phase file naming convention** — `step-NN-*.md` or `phase-NN-*.md`? This connects to the v2 review's YAML key decision (`steps:` vs `phases:`).
