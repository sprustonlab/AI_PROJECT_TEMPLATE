# Research Report: Per-Phase Content Files — Splitting COORDINATOR.md

**Requested by:** Coordinator
**Date:** 2026-04-04
**Tier of best source found:** T1 (Primary source code)

## Query

The user suggests the agent only gets the MD file for its current phase, syncing agent behavior with guardrail checkpoints. Investigate: what would per-phase files look like, what does splitting lose, and is this the same pattern as tutorial per-step markdown?

---

## 1. COORDINATOR.md Phase Map — What Each Per-Phase File Would Look Like

### Current Structure (Single File, 276 Lines)

| Lines | Section | Phase | Persistent Context? |
|-------|---------|-------|-------------------|
| 1-7 | Header + Re-read instruction | ALL | Yes — identity |
| 8-19 | **Prime Directive** | ALL | Yes — behavioral constraint |
| 20-32 | "If user sends X" handler | ALL | Yes — error recovery |
| 34-51 | **Phase 0: Vision** | 0 | No — one-time |
| 53-70 | **Phase 1a: Working Directory** | 1 | No — one-time |
| 72-80 | **Phase 1b: Session Check** | 1 | No — one-time |
| 82-137 | **Phase 1c: Initialize** | 1 | No — one-time |
| 139-195 | **Phase 2: Spawn Leadership** | 2 | No — one-time |
| 199-228 | **Phase 3: Specification** | 3 | No — one-time |
| 230-236 | **Phase 4: Implementation** | 4 | No — one-time |
| 238-241 | **Phase 5: Testing** | 5 | No — one-time |
| 243-245 | **Phase 6: Sign-Off** | 6 | No — one-time |
| 247-249 | **Phase 7: Integration** | 7 | No — one-time |
| 251-253 | **Phase 8: E2E Checkpoint** | 8 | No — one-time |
| 255-257 | **Phase 9: Final Sign-Off** | 9 | No — one-time |
| 259-261 | Conflict Resolution | ALL | Yes — behavioral |
| 263-270 | Key Terms | ALL | Yes — vocabulary |

### Proposed Split

**Shared preamble file (always loaded):**

```
AI_agents/project_team/coordinator/
  _preamble.md          # Prime Directive, "x" handler, Conflict Resolution, Key Terms (~40 lines)
  phase-00-vision.md    # Phase 0 (~20 lines)
  phase-01-setup.md     # Phase 1a+1b+1c (~60 lines)
  phase-02-spawn.md     # Phase 2 (~60 lines)
  phase-03-spec.md      # Phase 3 (~30 lines)
  phase-04-impl.md      # Phase 4 (~8 lines)
  phase-05-testing.md   # Phase 5 (~5 lines)
  phase-06-signoff.md   # Phase 6 (~3 lines)
  phase-07-integration.md  # Phase 7 (~3 lines)
  phase-08-e2e.md       # Phase 8 (~3 lines)
  phase-09-final.md     # Phase 9 (~3 lines)
```

**What the agent sees at Phase 3:**
```
_preamble.md + phase-03-spec.md
```

**What it does NOT see:**
- Phase 0-2 instructions (already completed)
- Phase 4-9 instructions (not yet relevant)

### Per-Phase File Content Example

**`phase-03-spec.md`:**
```markdown
---
id: phase-03
title: "Specification"
phase: 3
verification:
  type: compound
  operator: and
  checks:
    - type: file-exists-check
      params:
        path: ".ao_project_team/{project}/specification/composability.md"
    - type: file-exists-check
      params:
        path: ".ao_project_team/{project}/specification/terminology.md"
    - type: file-exists-check
      params:
        path: ".ao_project_team/{project}/specification/skeptic_review.md"
    - type: file-exists-check
      params:
        path: ".ao_project_team/{project}/specification/user_alignment.md"
guardrails: []
---

# Phase 3: Specification

You are now the **Coordinator**. Leadership is active.

**EVERY TURN, BEFORE ANYTHING ELSE:**
1. **Read STATUS.md** — This is your memory.
2. **Re-read _preamble.md** — What should you be doing?

**Remember the Prime Directive: DELEGATE, not DO.**

Proceed automatically between phases. Stop only at User Checkpoints 👤.

## Actions

1. Wait for all Leadership agents to report their findings
2. If UI-heavy project → spawn UIDesigner
3. If Researcher is active → ask Researcher to investigate prior art
4. Composability spawns axis-agents based on project needs
5. Each axis-agent does relevance check:
   - Relevant → deep review → write to specification/
   - Not relevant → declare N/A → close
6. Synthesize all findings into specification document
7. Present to user

**User Checkpoint 👤:** Present specification. Handle response:
- **Approve** → proceed to Phase 4
- **Modify** → incorporate feedback, re-present
- **Redirect** → adjust approach, re-present
- **Fresh Review** → close Leadership, spawn fresh team, re-review
```

Note the YAML frontmatter — `verification` and `guardrails` fields following exactly the same schema as tutorial step files.

---

## 2. How Does the Existing System Handle Phase Transitions?

### Current Mechanism: Manual Re-Read + STATUS.md

The Coordinator's phase awareness works through two instructions:

**Instruction 1 — "Re-read this file after each compaction" (line 3):**
After context compaction, the agent re-reads the full 276-line file to recover its behavioral instructions. This is a **crash recovery** mechanism — compaction removes older context, so the file re-read restores it.

**Instruction 2 — "EVERY TURN, BEFORE ANYTHING ELSE" (Phase 3, lines 203-205):**
```
1. Read STATUS.md — This is your memory.
2. Re-read this file — What should you be doing?
```

The Coordinator reads STATUS.md to learn "what phase am I in" and then re-reads COORDINATOR.md to learn "what do I do in this phase." It then mentally skips to the relevant section.

**Transition trigger:** The Coordinator decides "this phase is complete" based on incoming agent messages and user responses, updates STATUS.md, and then reads the next phase's section from COORDINATOR.md.

### Problems With the Current Approach

| Problem | Evidence |
|---------|----------|
| **Context waste** | 276 lines loaded every turn, but only ~30 lines (current phase + preamble) are relevant. The other ~240 lines consume context window without value. |
| **No enforcement** | Nothing prevents the Coordinator from reading Phase 5 instructions during Phase 2 and acting on them prematurely. The "re-read" instruction is a social norm, not a technical constraint. |
| **No verification** | The Coordinator self-declares phase transitions. "Phase 4 → 5" happens when the Coordinator writes it to STATUS.md, not when anything verifiable occurs. |
| **Compaction fragility** | After aggressive compaction, the agent re-reads the full file but may not accurately reconstruct which phase it's in. STATUS.md mitigates this but it's still reconstructive, not authoritative. |

### How Per-Phase Files Fix These

| Problem | Fix |
|---------|-----|
| Context waste | Agent only loads `_preamble.md` + current phase file (~70 lines vs 276) |
| No enforcement | Agent literally cannot see future phases' instructions. The system controls which file it gets. |
| No verification | Phase file includes verification frontmatter. Transition requires verification to pass. |
| Compaction fragility | `phase_state.json` is the authoritative source. After compaction, system reads phase state → loads correct file. |

---

## 3. What Does the Coordinator Lose by Splitting?

### What It Loses

| Lost Content | Impact | Mitigation |
|-------------|--------|------------|
| **Visibility of future phases** | Cannot plan ahead ("in Phase 2, I should keep in mind that Phase 4 will need...") | Low impact. Phase design is the specification's job, not the Coordinator's. The Coordinator follows the script; it doesn't write it. |
| **Full workflow overview** | Cannot answer "what comes after Phase 5?" without loading the next file | Put a **phase summary table** in `_preamble.md`: one line per phase, no instructions. Coordinator sees the map but not the turn-by-turn directions. |
| **Cross-phase patterns** | "Phase 1 sets up paths that Phase 2 uses" — the connection between phases is implicit in the current file | Put **cross-phase contracts** in `_preamble.md`: "Phase 1 produces `working_dir` and `monorepo_root`. Phase 2+ receives them via STATUS.md." |
| **Retrospective context** | "In Phase 0, the user said..." is currently in the full file's Phase 0 section | Already solved: STATUS.md captures Vision from Phase 0. The Coordinator reads STATUS.md every turn. |

### What It Keeps

| Kept Content | How |
|-------------|-----|
| Prime Directive | In `_preamble.md` (always loaded) |
| "x" recovery handler | In `_preamble.md` (always loaded) |
| Conflict resolution | In `_preamble.md` (always loaded) |
| Key Terms | In `_preamble.md` (always loaded) |
| Current phase instructions | In the per-phase file |
| Phase history | In STATUS.md (already the canonical source) |

### Verdict: The Coordinator Loses Almost Nothing

The current COORDINATOR.md is already structured so that each phase section is **self-contained**. Phase 3's instructions don't reference Phase 7's. The only cross-phase dependencies are:
1. `working_dir` and `monorepo_root` (established in Phase 1, used in Phase 2+)
2. Vision Summary (established in Phase 0, copied to STATUS.md)
3. Leadership spawn evidence (established in Phase 2, tracked in STATUS.md)

All three are already persisted in STATUS.md. The per-phase file doesn't need them inline.

**The critical insight:** STATUS.md is already the Coordinator's working memory. COORDINATOR.md is the instruction manual. Splitting the instruction manual into chapters doesn't lose information — it focuses attention.

---

## 4. Is This the Same Pattern as Tutorial Per-Step Markdown?

### YES — It's Structurally Identical

| Dimension | Tutorial System | Team Workflow (Proposed) |
|-----------|----------------|--------------------------|
| **Manifest** | `tutorial.yaml` | `workflow.yaml` (new) or `_preamble.md` with phase table |
| **Per-unit content** | `step-01-generate-key.md` | `phase-03-spec.md` |
| **Frontmatter** | `id`, `title` | `id`, `title`, `phase` |
| **Verification** | In manifest: `verification: { type, params }` | In frontmatter or manifest: same schema |
| **Hints** | In manifest: per-step `hints:` list | Could add per-phase `hints:` list |
| **Guardrails** | In manifest: per-step `guardrails:` list | In frontmatter or manifest: per-phase `guardrails:` list |
| **Progression** | `checkpoint-gated` (verification must pass) | Phase-gated (same mechanism) |
| **Discovery** | Engine scans `tutorials/content/*/tutorial.yaml` | Engine scans `coordinator/phase-*.md` |
| **State persistence** | `tutorial_state.json` | `phase_state.json` |

### The Structural Parallel

**Tutorial step file:**
```markdown
---
id: generate-key
title: "Generate an SSH Key Pair"
---
# Generate an SSH Key Pair
[content for the user]
<!-- checkpoint: generate-key -->
```

**Coordinator phase file:**
```markdown
---
id: phase-03
title: "Specification"
phase: 3
---
# Phase 3: Specification
[instructions for the Coordinator agent]
<!-- checkpoint: phase-03 -->
```

The ONLY difference is the audience: tutorial steps are for users, phase files are for agents. The **structure** is identical:
- Frontmatter identifies the unit
- Content provides instructions
- Checkpoint marker triggers verification
- Verification must pass before progression

### What This Means Architecturally

The tutorial content engine and the team workflow engine can share:
1. **Content loading** — YAML frontmatter + markdown body parsing
2. **Verification protocol** — `Check.check(context) -> CheckResult`
3. **State persistence** — `PhaseStateStore` ≅ `TutorialStateStore`
4. **Phase/step-scoped guardrails** — same `scope` field in rules.yaml

The **reusable primitive** is: "a sequence of content files with verification checkpoints, gated progression, and scoped guardrails." Both tutorials and the team workflow are instances of this pattern.

### The Content Axis Spec Already Anticipated This

From `axis_content.md`:
> "Separation of concerns: The manifest is *structure* (what steps, what order, what verification). Markdown files are *content* (what the user reads)."

Replace "what the user reads" with "what the agent reads" and the principle is identical.

> "Configuration in manifest, not in step frontmatter — Single source of truth: An author can see the entire tutorial's structure in one file."

This maps to a `workflow.yaml` manifest that lists phases, their verification configs, and their guardrail scopes — analogous to `tutorial.yaml`.

---

## 5. Proposed `workflow.yaml` Manifest (for Team Workflow)

Following the tutorial `tutorial.yaml` schema:

```yaml
id: project-team-workflow
title: "Multi-Agent Project Team"
description: >
  Standard 10-phase workflow for multi-agent software development,
  from vision through implementation to deployment.

phases:
  - id: phase-00
    file: phase-00-vision.md
    verification:
      type: manual-confirm
      params:
        prompt: "Has the user approved the Vision Summary?"
    guardrails: []

  - id: phase-01
    file: phase-01-setup.md
    verification:
      type: compound
      operator: and
      checks:
        - type: file-exists-check
          params: { path: ".ao_project_team/{project}/STATUS.md" }
        - type: file-exists-check
          params: { path: ".ao_project_team/{project}/userprompt.md" }
    guardrails: []

  - id: phase-02
    file: phase-02-spawn.md
    verification:
      type: command-output-check
      params:
        command: "echo 'check list_agents for 4 Leadership agents'"
        expected_pattern: ".*"
      # Note: Real verification would use an MCP call or agent-list check
    guardrails: []

  - id: phase-03
    file: phase-03-spec.md
    verification:
      type: compound
      operator: and
      checks:
        - type: file-exists-check
          params: { path: ".ao_project_team/{project}/specification/composability.md" }
        - type: file-exists-check
          params: { path: ".ao_project_team/{project}/specification/terminology.md" }
        - type: file-exists-check
          params: { path: ".ao_project_team/{project}/specification/skeptic_review.md" }
        - type: file-exists-check
          params: { path: ".ao_project_team/{project}/specification/user_alignment.md" }
        - type: manual-confirm
          params: { prompt: "Has the user approved the specification?" }
    guardrails: []

  - id: phase-04
    file: phase-04-impl.md
    verification:
      type: manual-confirm
      params:
        prompt: "Have all Leadership agents approved the implementation?"
    guardrails: []

  - id: phase-05
    file: phase-05-testing.md
    verification:
      type: command-output-check
      params:
        command: "ls .test_runs/*.txt 2>/dev/null | tail -1 | xargs grep -c 'passed' || echo 0"
        expected_pattern: "[1-9]"
        failure_message: "No passing test runs found in .test_runs/"
    guardrails:
      - R01-relaxed  # Phase 5 variant: allow broader pytest usage

  - id: phase-06
    file: phase-06-signoff.md
    verification:
      type: manual-confirm
      params: { prompt: "Have all agents confirmed READY?" }
    guardrails: []

  - id: phase-07
    file: phase-07-integration.md
    verification:
      type: file-exists-check
      params: { path: "launch_script.sh" }  # or whatever the integration artifact is
    guardrails: []

  - id: phase-08
    file: phase-08-e2e.md
    verification:
      type: manual-confirm
      params: { prompt: "Does the user want E2E tests?" }
    guardrails: []

  - id: phase-09
    file: phase-09-final.md
    verification:
      type: manual-confirm
      params: { prompt: "Has the user given final approval?" }
    guardrails: []
```

This is the **exact same schema** as `tutorial.yaml`. The engine that processes one can process the other.

---

## 6. Context Size Impact

### Current (Single File)

| Phase | Context Loaded | Relevant | Waste |
|-------|---------------|----------|-------|
| Phase 0 | 276 lines | ~60 lines (preamble + Phase 0) | 216 lines (78%) |
| Phase 3 | 276 lines | ~70 lines (preamble + Phase 3) | 206 lines (75%) |
| Phase 5 | 276 lines | ~45 lines (preamble + Phase 5) | 231 lines (84%) |

### Proposed (Per-Phase Files)

| Phase | Context Loaded | Relevant | Waste |
|-------|---------------|----------|-------|
| Phase 0 | ~60 lines (preamble + phase-00) | ~60 lines | 0 lines (0%) |
| Phase 3 | ~70 lines (preamble + phase-03) | ~70 lines | 0 lines (0%) |
| Phase 5 | ~45 lines (preamble + phase-05) | ~45 lines | 0 lines (0%) |

**75-84% context window savings** per turn. For a Coordinator that re-reads every turn, this compounds significantly over a multi-phase project.

The savings matter more than they appear because the Coordinator's context window also contains: STATUS.md, agent messages, user messages, and specification files. Freeing ~200 lines of instruction overhead gives meaningful room.

---

## Summary

| Question | Answer |
|----------|--------|
| What would per-phase files look like? | `_preamble.md` (always loaded, ~40 lines) + `phase-NN-name.md` (per phase, 3-60 lines each). YAML frontmatter with verification + guardrails. |
| What does the Coordinator lose? | Almost nothing. Cross-phase dependencies already flow through STATUS.md. A phase summary table in `_preamble.md` preserves the workflow overview. |
| Is this the same pattern as tutorials? | **Structurally identical.** Same manifest schema, same per-unit markdown, same verification frontmatter, same checkpoint-gated progression. The only difference is audience (user vs agent). |
| What's the impact of splitting? | 75-84% context savings per turn. Agent can't see future phase instructions (feature, not bug). Phase transitions become machine-verifiable. |

**Key architectural insight:** Tutorials and team workflow are the same pattern — a sequence of content files with verification checkpoints, gated progression, and scoped guardrails. The difference is audience. Building a general "sequenced content with verification" engine serves both use cases.
