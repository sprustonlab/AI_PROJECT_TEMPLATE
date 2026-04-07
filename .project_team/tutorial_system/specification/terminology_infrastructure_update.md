# Terminology Infrastructure Update — v1/v2 Split Analysis

> **Reviewer:** TerminologyGuardian
> **Date:** 2026-04-04
> **Context:** Project reframed — v1 builds general-purpose infrastructure primitives, v2 builds tutorials on top. This document analyzes which terms generalize, which stay tutorial-specific, and proposes updated terminology.

---

## The Core Insight

Looking at the specs through the infrastructure lens, a pattern emerges: most of the "tutorial" machinery is actually **a general step-sequence engine with pluggable verification**. Tutorials are one consumer of this engine, but the same primitives could power setup wizards, onboarding flows, migration scripts, or CI preflight checks.

The question for each term: **does the concept exist because of tutorials, or does it exist because step-sequenced-work-with-verification is a general need?**

---

## Classification: Every Term in terminology.md

### Tier 1 — Generalize to Infrastructure (v1)

These concepts have nothing inherently tutorial-specific. They describe a **step-sequence execution engine with verification gates**.

| Current Term | Proposed v1 Name | Rationale |
|---|---|---|
| **Tutorial Step** | **Step** | A discrete unit of work with instructions, hints, and a verification gate. Nothing about this is tutorial-specific. Steps exist in onboarding flows, migration scripts, setup wizards. |
| **Checkpoint** | **Checkpoint** *(unchanged)* | A verification gate that proves a step was completed. Already general — keep as-is. Disambiguate from ClaudeChic's "session checkpoint" stays relevant. |
| **Checkpoint Guardrail** | **Checkpoint Guardrail** *(unchanged)* | A guardrail that blocks progression until a checkpoint passes. The enforcement mechanism is general — it works for any step sequence, not just tutorials. |
| **Tutorial Manifest** | **Manifest** | The configuration file declaring steps, checkpoints, guardrails, hints. The schema is general — it describes a step sequence with verification, not specifically a "lesson." |
| **Tutorial Mode** | **Scoped Mode** | A distinct operational state where specific guardrails, hints, and agent behavior are active. "Tutorial mode" is one instance of a scoped mode. Other instances: "migration mode," "setup mode," "onboarding mode." |
| **Tutorial Guardrail** | **Scoped Guardrail** | A guardrail active only during a specific scoped mode. Tutorial guardrails are one case; migration guardrails, setup guardrails would use the same mechanism. |

**New infrastructure terms** (not in current terminology.md but implied by the specs):

| Proposed v1 Term | Source in Specs | Definition |
|---|---|---|
| **Verification** (protocol) | `axis_verification.md` | A protocol (`check(ctx) → VerificationResult`) for confirming that an observable system property holds. Pure function of system state — read-only, deterministic, bounded-time. |
| **VerificationResult** | `axis_verification.md` | Frozen data object returned by all verifications: `passed` (bool), `message` (human-readable), `evidence` (raw proof). The sole seam-crossing object from the verification subsystem. |
| **VerificationContext** | `axis_verification.md` | Sandboxed environment providing read-only system access (run commands, read files, check existence) to verification implementations. |
| **Verification implementations** | `axis_verification.md` | Built-in verification strategies: `CommandOutputCheck`, `FileExistsCheck`, `ConfigValueCheck`, `ManualConfirm`, `CompoundCheck`. Each is a frozen dataclass satisfying the Verification protocol. |
| **ProgressStore** | `axis_guidance.md` (as TutorialProgressStore) | Persistence for step-sequence state: current step, completed steps, verification evidence. JSON-file-based, session-resumable. General — not tutorial-specific. |
| **ModeContext** | `axis_guidance.md` (as TutorialContext) | Read-only snapshot of a scoped mode's progress, injected into `ProjectState`. Contains: active mode ID, current step, step timing, last verification result, completed steps. General container — `TutorialContext` would be one type. |

---

### Tier 2 — Tutorial-Specific (v2)

These terms describe the **tutorial experience built on top of v1 infrastructure**. They make sense only in the context of "teaching a user something."

| Term | Status | Why Tutorial-Specific |
|---|---|---|
| **Tutorial** | Keep as-is (v2) | The specific experience type: an interactive, guided teaching session. The infrastructure doesn't know about "teaching" — it knows about step sequences with verification. "Tutorial" is the domain layer on top. |
| **Tutorial Content** | Keep as-is (v2) | Markdown instructional material. The infrastructure has "step instructions" (a string); tutorials add the pedagogical layer — explanations, examples, "why" sections. |
| **Tutorial-Runner Agent** | Keep as-is (v2) | The specific agent role that manages tutorial execution. The infrastructure provides the engine; the tutorial-runner is a domain-specific agent that drives it for teaching purposes. |
| **Agent-Team Tutorial** | Keep as-is (v2) | A special tutorial category. Entirely domain-specific — the infrastructure doesn't distinguish tutorial types. |
| **Tutorial Registry** | → **Registry** (partially generalizable) | The index of available step sequences. The concept generalizes (you could have a "migration registry" or "setup registry"), but the specific implementation is tutorial-focused. v1 could provide a generic `Registry` protocol; v2 implements `TutorialRegistry`. |
| **Tutorial Selector** | → **Selector** (partially generalizable) | The UI for choosing a step sequence to run. Same generalization pattern as Registry. |
| **Hint (in tutorial context)** | Keep as-is (v2) | Tutorial-scoped hints are a specialization of the existing hint system. The hints engine itself is already v1 infrastructure. Tutorial hints are v2 content registered into it. |

---

### Tier 3 — Borderline Cases (Needs Decision)

| Term | Generalize? | Arguments For | Arguments Against |
|---|---|---|---|
| **`run` fence tag** (in markdown) | Lean v1 | Marking "executable commands" in markdown content is useful beyond tutorials — setup docs, READMEs, onboarding guides could all use it. | It's a content-format convention, not infrastructure. v1 shouldn't specify markdown conventions. |
| **auto-discovery** (scanning for manifests) | v1 | Scanning `content/*/manifest.yaml` is a generic engine capability. | Trivially general — barely needs a name. |
| **agent_blocked_commands** | Lean v1 | Preventing an agent from executing specific commands is a general guardrail concept (scoped command restrictions), not tutorial-specific. | The per-step scoping is tightly coupled to the step-sequence engine. |
| **evidence** (in VerificationResult) | v1 | Already general — raw output captured as proof of any verification, not just tutorial checkpoints. | Already covered by VerificationResult definition. |

**Recommendation:** Generalize `agent_blocked_commands` → **scoped command restrictions** (a guardrail mechanism). Keep `run` fence tag and auto-discovery as v2 content-format details.

---

## Proposed Terminology Structure: v1 vs v2

### v1: Infrastructure Layer (terminology_infrastructure.md)

```
Step-Sequence Engine
 ├── Step (unit of work with instructions + verification gate)
 ├── Manifest (declares steps, checkpoints, guardrails, hints)
 ├── Checkpoint (verification gate blocking progression)
 ├── ProgressStore (persistence: current step, completed steps, evidence)
 └── Scoped Mode (distinct operational state with scoped behavior)
      ├── Scoped Guardrail (guardrail active only in this mode)
      ├── Checkpoint Guardrail (blocks advancement until checkpoint passes)
      ├── ModeContext (read-only progress snapshot on ProjectState)
      └── Scoped Command Restriction (per-step agent command blocking)

Verification Subsystem
 ├── Verification (protocol: check(ctx) → VerificationResult)
 ├── VerificationResult (seam object: passed, message, evidence)
 ├── VerificationContext (sandboxed read-only system access)
 └── Built-in Implementations
      ├── CommandOutputCheck
      ├── FileExistsCheck
      ├── ConfigValueCheck
      ├── ManualConfirm
      └── CompoundCheck
```

### v2: Tutorial Layer (terminology_tutorial.md)

```
Tutorial System (built on Step-Sequence Engine + Verification)
 ├── Tutorial (interactive teaching experience using Steps)
 ├── Tutorial Content (markdown pedagogical material for each Step)
 ├── Tutorial-Runner Agent (agent role driving the tutorial)
 ├── Tutorial Registry (index of available tutorials)
 ├── Tutorial Selector (UI for picking a tutorial)
 ├── Agent-Team Tutorial (special category with multi-agent content)
 └── Tutorial Hints (hint definitions scoped to tutorial steps)
```

---

## Impact on Existing Specs

### Terms that change across ALL specification files

| Old Term | New Term | Files Affected |
|---|---|---|
| Tutorial step | **Step** (within engine context) | composability.md, axis_content.md, axis_guidance.md, axis_verification.md |
| Tutorial manifest | **Manifest** (within engine context) | composability.md, axis_content.md |
| Tutorial mode | **Scoped mode** (the general concept); "tutorial mode" remains as the specific instance | composability.md, axis_guidance.md, skeptic_review.md |
| Tutorial guardrail | **Scoped guardrail** (general); "tutorial guardrail" for specific instance | composability.md, axis_verification.md, terminology.md |
| TutorialContext | **ModeContext** (general type); `TutorialContext` becomes a concrete implementation | axis_guidance.md |
| TutorialProgressStore | **ProgressStore** (general); tutorial progress is one use | axis_guidance.md |

### Specs that need structural changes

| Spec | Change Needed |
|---|---|
| `composability.md` | Reframe axes as engine-level, not tutorial-level. Content axis stays v2. Other 5 axes (Progression, Verification, Guidance, Safety, Presentation) are v1 infrastructure. |
| `axis_verification.md` | Already general — minimal changes. Just rename `TutorialStep` references to `Step`. |
| `axis_guidance.md` | Split: `TutorialContext` → `ModeContext` (general) + `TutorialContext extends ModeContext` (specific). `TutorialProgressStore` → `ProgressStore` (general). |
| `axis_content.md` | Stays v2-scoped (tutorial content authoring format). |
| `terminology.md` | Major rewrite — split into two sections or two files. |

---

## Naming Principles for the Split

### 1. Infrastructure terms are SHORT and UNPREFIXED

v1 terms drop "tutorial": Step, Manifest, Checkpoint, Verification, ProgressStore. These are the primitives. They shouldn't carry domain baggage.

### 2. Tutorial terms are PREFIXED to show they're domain-specific

v2 terms keep "tutorial": Tutorial Content, Tutorial-Runner Agent, Tutorial Registry. The prefix signals "this builds on infrastructure for a specific domain."

### 3. "Scoped" replaces "tutorial" for mode-related infrastructure

"Scoped mode," "scoped guardrail," "scoped command restriction." The word "scoped" communicates the key property — these activate/deactivate based on what mode is active — without assuming the mode is a tutorial.

### 4. The Verification subsystem was ALREADY general

Looking at `axis_verification.md`, the Verification protocol, VerificationResult, VerificationContext, and all five implementations mention nothing tutorial-specific. They check system state. They don't know about teaching. They were designed as infrastructure from the start — they just lived in a "tutorial spec" document. The reframe formalizes what the design already implied.

---

## Synonym Control Updates

### New bans needed

| DO NOT USE | USE INSTEAD | Reason |
|---|---|---|
| tutorial step (in v1 context) | **step** | Infrastructure doesn't know about tutorials |
| tutorial checkpoint (in v1 context) | **checkpoint** | Already general |
| tutorial verification | **verification** | The protocol is domain-agnostic |
| mode context (when meaning the specific class) | **ModeContext** | Capital M, compound noun — it's a type name |
| progress store (when meaning the specific class) | **ProgressStore** | Same |

### Bans that still apply in v2

All existing bans from terminology.md carry over. Additionally:

| DO NOT USE | USE INSTEAD | Reason |
|---|---|---|
| tutorial engine | **step-sequence engine** (v1) or **tutorial system** (v2) | "Engine" is an implementation detail; the infrastructure is a "step-sequence engine," the domain layer is the "tutorial system" |
| workflow (for step sequences) | **step sequence** | "Workflow" is overloaded (GitHub workflows, CI workflows); "step sequence" is precise |

---

## Open Questions for Composability Lead

1. **Should terminology.md split into two files?** Propose: `terminology_infrastructure.md` (v1) + `terminology_tutorial.md` (v2). Or: keep one file with clearly separated sections. One file is simpler for cross-referencing; two files enforce the layering.

2. **Does the step-sequence engine get its own directory?** If v1 infrastructure is general, it shouldn't live under `tutorials/`. Propose: `stepengine/` or `workflow_engine/` at the template root, with `tutorials/` as a consumer. This is an architecture decision, not terminology, but the naming reflects the layering.

3. **ModeContext on ProjectState — is one general type enough?** The current spec has `TutorialContext` with tutorial-specific fields (active_tutorial_id, active_step_id, etc.). A general `ModeContext` would have `active_mode_id`, `active_step_id`, `step_entered_at`, `last_verification`, `completed_steps`. Tutorial-specific extensions would subclass or add fields. Is subclassing worth the complexity, or is one general type sufficient for v1?

4. **Registry and Selector — v1 or v2?** The concepts generalize (any step-sequence collection needs discovery and selection), but v1 might not need them if only tutorials use step sequences initially. Propose: defer to v2, build them as tutorial-specific, generalize later if a second consumer appears (YAGNI).
