# Fresh User Alignment Review — Full Specification Package

**Reviewed:** All 9 specification files + userprompt.md
**Date:** 2026-04-03

---

## Original User Request (verbatim)

> Add a "tutorial" feature to the template that combines md files, a team of agents, hints, and guardrails in a new mode to help users complete a task. Tutorial ideas include: signing up for GitHub, SSH-ing into a cluster for the first time, learning a coding feature, setting up git config & SSH keys, creating a first project from the template, understanding pixi environments, writing and running a first test with pytest.

## User-Confirmed Decisions

1. Single tutorial-runner agent for v1 (not multi-agent per tutorial)
2. First multi-agent tutorial teaches agent-team workflow by doing it
3. SSH and GitHub signup are valid tutorials (no bootstrap problem)

---

## Alignment Verdict: ✅ ALIGNED

The specification faithfully implements what the user asked for. Every component the user named is present, well-specified, and integrated. The user would recognize this as "what I asked for."

---

## Component-by-Component Check

### 1. "md files" — ✅ FULLY ALIGNED

User said tutorials "combine md files." The spec delivers:
- `axis_content.md`: Tutorials are authored as YAML manifests + markdown step files
- Step content is pure markdown with YAML frontmatter
- Auto-discovery via `tutorials/content/*/tutorial.yaml`
- Zero-code tutorial authoring — add a directory with markdown + YAML, done

**This is exactly what the user asked for.** Tutorials are markdown-based, accessible to scientists, and the authoring format doesn't require programming knowledge.

### 2. "a team of agents" — ✅ ALIGNED (with user-approved scope adjustment)

User said "a team of agents." The spec implements:
- **V1:** Single tutorial-runner agent per tutorial (user-approved simplification)
- **Agent-team tutorial:** One special tutorial teaches multi-agent workflow by actually spawning agents
- `axis_guidance.md` §4: Agent role file, capabilities, constraints, and `AgentContext` design

The user explicitly approved the single-runner-for-v1 approach. The agent-team tutorial preserves the multi-agent concept as teaching content rather than delivery mechanism. **No scope shrink — the user confirmed this split.**

### 3. "hints" — ✅ FULLY ALIGNED

User listed hints as a distinct component. The spec delivers:
- `axis_guidance.md`: Full integration with existing hints pipeline
- Three tutorial-specific trigger types: `step-active`, `step-stuck`, `verification-failed`
- New lifecycle: `ShowUntilStepComplete`
- Hints declared per-step in YAML, translated to `HintSpec` objects
- Hints are a **distinct mechanism** from agent chat — triggered by time, failure, or manual request

**This directly addresses my original clarification.** Hints are NOT just the agent talking — they're a separate system with their own triggers and lifecycle, exactly as the user's listing implied.

### 4. "guardrails" — ✅ FULLY ALIGNED (enhanced beyond request)

User said "guardrails." The spec delivers guardrails in two roles:
- **Safety guardrails:** Prevent mistakes during tutorials (e.g., "don't delete SSH keys")
- **Checkpoint guardrails:** Verify step completion — the agent can't claim "done" without proof

The vision's expansion of guardrails to include verification is explicitly aligned with "help users complete a task." The user prompt doesn't say "guardrails only prevent mistakes" — the verification interpretation is a natural extension that makes the system more powerful. **Enhancement, not scope creep.**

`axis_verification.md` specifies:
- 5 verification types (command-output, file-exists, config-value, manual-confirm, compound)
- `VerificationContext` sandboxing (read-only, timeout-enforced)
- `VerificationResult` with evidence capture
- Three-level guardrail integration (prompt injection, progression gate, evidence persistence)

### 5. "in a new mode" — ⚠️ PARTIALLY SPECIFIED

User explicitly said **"in a new mode."** The spec acknowledges tutorial mode exists:
- `terminology.md`: "Tutorial Mode — a distinct operational mode... entering tutorial mode changes what agents are spawned, what guardrails are enforced, and what hints are surfaced"
- `TutorialContext` on `ProjectState` distinguishes tutorial-active from normal operation
- Per-step guardrail activation/deactivation

**However,** the Skeptic correctly identified that the mode lifecycle is under-specified:
- Entry mechanism (what command starts it?) — not defined
- Clean exit — not defined
- Abandon/resume — not defined
- Nesting prevention — not defined

❓ **USER ALIGNMENT FLAG:** The user said "a new mode," which implies clear entry/exit. The spec has the *concept* of mode but not the *experience* of mode. A user would expect to type something, enter tutorial mode, and know they're in it. The lifecycle spec needs to be completed before architecture.

### 6. "help users complete a task" — ✅ FULLY ALIGNED

This is the overarching goal. The checkpoint verification system directly ensures users actually complete tasks, not just read about them. The vision summary's key insight — "The agent can't just say 'done' — the guardrails prove it" — is fully implemented via:
- Verification protocol with evidence capture
- Checkpoint guardrail that blocks advancement without proof
- Agent over-help prevention (agent can guide but not execute verification-target commands)

---

## Scope Creep Check

### ℹ️ Progression axis: `branching` mode — MINOR SCOPE CREEP

The composability analysis introduces three progression modes: `linear`, `checkpoint-gated`, and `branching`. The user didn't ask for branching tutorials. `branching` is only mentioned as a commented-out example in tutorial.yaml.

**Verdict:** Not harmful — it's declared but unimplemented. Skeptic already flagged this should be explicitly deferred to v2. Agree.

### ℹ️ 6-axis decomposition — ENGINEERING SOPHISTICATION, NOT SCOPE CREEP

The composability analysis decomposes into 6 axes (Content × Progression × Verification × Guidance × Safety × Presentation). The user didn't ask for this level of architecture. However:
- It doesn't add user-facing features the user didn't request
- It ensures the system can support the range of tutorials the user listed
- It makes adding new tutorials trivial (zero-code, directory + files)

**Verdict:** This is engineering quality, not scope creep. The user benefits from the clean architecture even if they didn't ask for it explicitly.

### ℹ️ Prior art research — JUSTIFIED SUPPORT WORK

Research document validates design decisions against Rustlings, Exercism, GitHub Skills, Katacoda. Not scope creep — it's due diligence.

---

## Scope Shrink Check

### No shrink detected.

All five user-specified components are present. All seven tutorial examples the user listed are supportable by the content format:

| User's Example | Supportable? | Verification Type |
|---|---|---|
| Signing up for GitHub | ✅ | `manual-confirm` (external action) |
| SSH-ing into a cluster | ✅ | `command-output-check` (`ssh -T`) |
| Learning a coding feature | ✅ | `command-output-check` or `file-exists-check` |
| Setting up git config & SSH keys | ✅ | `compound` (config-value + file-exists) |
| Creating a first project from the template | ✅ | `file-exists-check` + `command-output-check` |
| Understanding pixi environments | ✅ | `config-value-check` / `command-output-check` |
| Writing and running a first test with pytest | ✅ | `command-output-check` (pytest exit code) |

**Every example the user provided can be implemented with the specified verification types.** No tutorial topic is unsupported.

---

## V1/V2 Split Alignment

| Feature | V1/V2 | Aligned with user priorities? |
|---|---|---|
| Tutorial content format (YAML + markdown) | V1 | ✅ Core ask |
| Single tutorial-runner agent | V1 | ✅ User-approved |
| Checkpoint verification (5 types) | V1 | ✅ Core ask |
| Hints integration | V1 | ✅ Core ask |
| Tutorial guardrails (safety + checkpoint) | V1 | ✅ Core ask |
| Tutorial mode (basic) | V1 | ✅ Core ask |
| Agent-team tutorial | V2 (or late V1) | ✅ User wants it but approved deferral |
| Branching progression | V2 | ✅ User didn't ask for it |
| Tutorial mode lifecycle (full state machine) | **NEEDS DECISION** | ⚠️ Entry/exit is v1; crash recovery could be v2 |
| Guardrail exemptions per-step | V2 | ✅ Edge case, not core |
| Watch mode (auto-recheck on file change) | V2 | ✅ Nice-to-have from prior art |

**The v1/v2 split is well-aligned.** Core user requirements are all v1. Deferred items are either user-approved (agent-team tutorial) or genuinely secondary (branching, watch mode).

---

## Wording Check

### ❓ "tutorial" vs "walkthrough" vs "lesson"

`terminology.md` correctly establishes "tutorial" as the canonical term and bans synonyms. **Aligned with user's own word choice.**

### ❓ "mode" — user's word preserved

User said "mode," spec says "tutorial mode." ✅ Wording preserved.

### ❓ "guardrails" — user's word preserved

User said "guardrails," spec uses "guardrails" (with subtypes: "tutorial guardrail," "checkpoint guardrail"). ✅ Wording preserved with clear sub-categorization.

### ❓ "hints" — user's word preserved

User said "hints," spec uses "hints." ✅ No synonym substitution.

---

## Domain Term Check

### "tutorial" — ✅ CORRECT MENTAL MODEL

The spec's implementation matches the user's mental model: interactive, step-by-step, guided, with verification. Not static docs. Not a video. Not a reference guide. The prior art comparison to Rustlings and GitHub Skills confirms the right gestalt.

### "mode" — ⚠️ NEEDS MORE DEFINITION

User said "new mode" — implies the system feels different when you're in it. The spec has the internal mechanics (TutorialContext, scoped guardrails) but hasn't defined the **user experience** of mode. What does the user see that tells them "I'm in tutorial mode"? A prompt change? A status bar? An explicit message? This is a UX gap, not a feature gap.

---

## Summary of Findings

### ✅ What's right (majority)
- All 5 user-specified components implemented
- All 7 tutorial examples supportable
- User's wording preserved throughout
- V1/v2 split aligned with user priorities
- Verification system exceeds user expectations (in a good way)
- No harmful scope creep
- No scope shrink

### ⚠️ What needs attention (2 items)
1. **Tutorial mode lifecycle** — User said "new mode." Spec needs entry/exit/resume state machine before architecture. This is the only genuinely under-specified user requirement.
2. **Agent-team tutorial scope** — Must be explicitly marked as v1 or v2. Currently ambiguous.

### ✅ What's fine as-is
- Branching progression deferred to v2 (user didn't ask for it)
- Skeptic's minor issues (retry semantics, env vars, naming conventions) are engineering refinements, not alignment concerns
- 6-axis architecture is engineering quality, not scope creep

---

## Recommendation

**Proceed to architecture.** The spec is well-aligned with user intent. The two ⚠️ items (mode lifecycle, agent-team scoping) should be resolved during architecture phase — they're specification gaps, not alignment failures. The user would look at this spec and say "yes, this is what I meant."
