# JSONL Analysis: What Skeptic Actually Received vs Phase Files

**Author:** Researcher agent
**Date:** 2026-04-15
**Issue:** #37
**Method:** Comparison of actual session data (corrections_report.json, test fixtures) against workflow phase files

---

## Executive Summary

ALL historical Skeptic sessions in the audit data predate the current `type=` spawn mechanism. The coordinator manually told the Skeptic to "read your role file" from a filepath. The Skeptic never received its identity.md or phase files through the system -- it received coordinator-written freeform prompts that partially paraphrase the phase instructions but omit significant content.

---

## Data Sources

| Source | Records | Skeptic Entries | Workflow Version |
|--------|---------|-----------------|------------------|
| `corrections_report.json` | 220 candidates, 27 sessions | 5 Skeptic sub-agent entries | `solo` or `ao_project_team` (both pre-current) |
| `v2.1.59_subagent_session.jsonl` (test fixture) | 5 lines | 1 Skeptic spawn | Synthetic test data |
| `.claude/hits.jsonl` | Guardrail hits | N/A | N/A |
| Live session (current) | In progress | N/A | `project-team` (current) |

**Critical context:** No sessions in corrections_report.json use `"workflow": "project-team"`. They use either `"solo"` or `"ao_project_team"` -- both predate the current agent_folders.py system with `type=` and `assemble_phase_prompt()`. This means ALL historical data shows the OLD behavior where the coordinator manually assembled prompts.

---

## Evidence Exhibit 1: Skeptic Spawn Prompt (2026-03-29, workflow "solo")

### What the coordinator actually sent:

```
[Spawned by agent 'AI_PROJECT_TEMPLATE']

You are Skeptic. Read your role file:
/groups/spruston/home/moharb/AI_PROJECT_TEMPLATE/AI_agents/project_team/SKEPTIC.md.
Project state:
/groups/spruston/home/moharb/AI_PROJECT_TEMPLATE/.ao_project_team/composable_plugins/.
Read /groups/spruston/home/moharb/AI_PROJECT_TEMPLATE/.ao_project_team/composable_plugins/userprompt.md
for context.

Phase task: Challenge assumptions in the vision. Key risks to evaluate:
1. Is a plugin system over-engineering for 5 features? What's the minimum viable abstraction?
2. "Lightweight" plugin system -- where's the line between too simple (just a convention)
   and too complex (full plugin framework)?
3. Onboarding UX -- web vs CLI vs Claude conversation: what are the real tradeoffs?
4. Existing codebase integration -- what can actually go wrong when wrapping someone's
   existing repo?
5. The pattern miner depends on Claude session JSONL files -- is that a stable interface
   to build on?

Write findings to ...specification/skeptic_review.md. Report to: Coordinator
```

**Source:** `corrections_report.json` line 1984, session `d9587d98`

### What the phase file says (specification.md):

```markdown
# Specification Phase

1. Challenge assumptions in the vision
2. Identify risks and failure modes
3. Distinguish essential complexity (inherent to the problem) from accidental (poor design)
4. Flag shortcuts disguised as simplicity
5. Flag designs that introduce layers, abstractions, or multi-phase engines when a simpler
   approach solves the same problem. If a proposal has more than 2 moving parts, ask: can
   this be done with 1?
6. Check for complexity carried over from previous spec revisions. When a spec is re-presented
   after user feedback, verify that old complexity was actually removed -- not just shuffled.
   Users simplify for a reason; do not let earlier over-engineering sneak back in
7. Write findings to specification/skeptic_review.md
8. Report to Coordinator
```

### Side-by-side comparison:

| Phase File Instruction | Coordinator Sent? | Notes |
|------------------------|-------------------|-------|
| 1. Challenge assumptions in the vision | YES | Coordinator paraphrased as "Challenge assumptions in the vision" |
| 2. Identify risks and failure modes | PARTIALLY | Coordinator listed specific risks instead of giving the general principle |
| 3. Distinguish essential vs accidental complexity | **NO** | Completely omitted. This is a core Skeptic principle. |
| 4. Flag shortcuts disguised as simplicity | **NO** | Completely omitted. |
| 5. Flag over-engineered designs (>2 moving parts = too many) | **NO** | Completely omitted. Ironic given the project was about plugin systems. |
| 6. Check for complexity from previous spec revisions | **NO** | Completely omitted. |
| 7. Write findings to skeptic_review.md | YES | Coordinator gave full path |
| 8. Report to Coordinator | YES | Coordinator said "Report to: Coordinator" |

**Result: 4 of 8 instructions were omitted.** The coordinator sent project-specific questions instead of the phase file's general principles. The Skeptic missed the "distinguish essential vs accidental complexity" lens entirely.

### What the Skeptic's identity.md says that was also missing:

The coordinator told the Skeptic to `Read your role file: .../SKEPTIC.md` -- but this was from an older path (`AI_agents/project_team/SKEPTIC.md`), not the current workflow path. The Skeptic had to read it as a file, not receive it as injected context. Whether it actually read it depends on the Claude model's tool-calling behavior.

---

## Evidence Exhibit 2: Skeptic Implementation Review (2026-03-30, workflow "solo")

### What the coordinator actually sent:

```
[Message from agent 'AI_PROJECT_TEMPLATE']

Phase 4 implementation is code-complete. Review ALL implemented files for risks, bugs,
and corner cases.

Two implementers worked:
[...detailed list of files and changes...]

Please review ALL files. Check:
1. Error handling -- does discovery never crash? Do tools return proper MCP error responses?
2. Fork sync conflicts -- were they resolved correctly?
3. Install scripts -- edge cases (pixi already installed, no git, no network)
4. Copier conditionals -- do all combinations work?
5. Security -- install scripts downloading from URLs, execution policy
6. kwargs graceful degradation -- cluster_watch without send_notification

Report your findings to Coordinator.
```

**Source:** `corrections_report.json` line 1969, session `d929dd27`

### What the phase file says (implementation.md):

```markdown
# Implementation Phase

Review Implementer code for:
- Shortcuts that break functionality (edge cases ignored, burden shifted)
- Unnecessary complexity (deep nesting, scattered responsibility, classes where functions suffice)
- Verifiability -- can you see correctness by reading the code?

Categorize issues as must-fix vs should-fix. Report to Coordinator.
```

### Side-by-side comparison:

| Phase File Instruction | Coordinator Sent? | Notes |
|------------------------|-------------------|-------|
| Shortcuts that break functionality | PARTIALLY | Coordinator listed specific things to check, not the general principle |
| Unnecessary complexity (deep nesting, scattered responsibility) | **NO** | Completely omitted |
| Verifiability -- can you see correctness by reading? | **NO** | Completely omitted |
| Categorize as must-fix vs should-fix | **NO** | Completely omitted |
| Classes where functions suffice | **NO** | Completely omitted |

**Result: The coordinator gave domain-specific review instructions but missed the Skeptic's core review lens.** The Skeptic was told WHAT to check but not HOW to evaluate it. The "verifiability" principle and the "must-fix vs should-fix" categorization framework were absent.

---

## Evidence Exhibit 3: Skeptic Debate Session (2026-03-30, workflow "solo")

### What the coordinator sent:

```
Skeptic2 -- Composability2 has a different recommendation. Read their analysis and respond.

[...Composability2's full position...]

But you said `_skip_if_exists` avoids that entirely (Copier skips claudechic on updates).
Does that invalidate their concern?

Do you agree or disagree? Where is Composability2 wrong? Where are you wrong?
Find the right answer together.

Reply to Composability2 via tell_agent, CC me (tell Coordinator too).
```

**Source:** `corrections_report.json` line 1789

### What any phase file says about this:

**Nothing.** There is no Skeptic phase file for "debate" or "cross-agent review." The coordinator is improvising the Skeptic's instructions entirely. The Skeptic's identity.md does say "You CAN push for simpler approaches" and "Essential vs Accidental complexity" -- principles that ARE relevant here -- but the coordinator didn't reference them.

---

## Evidence Exhibit 4: Test Fixture (Synthetic Data)

### The spawn in v2.1.59_subagent_session.jsonl:

```json
{
  "type": "user",
  "message": {
    "content": "[Spawned by agent 'AI_PROJECT_TEMPLATE']\n\nYou are the **Skeptic**.
    Review the implementation for correctness.\n\nPlease review scripts/data_loader.py
    for potential issues."
  }
}
```

**This is synthetic test data**, but it reveals the expected pattern: a minimal spawn prompt with no identity.md injection. The Skeptic gets a one-line role description ("You are the Skeptic") instead of the 117-line identity.md.

---

## Evidence Exhibit 5: Current Session (Live, 2026-04-15)

### What I (Researcher) actually received:

My prompt begins with the FULL content of `workflows/project_team/researcher/identity.md` (240 lines / 12,243 bytes), followed by `---`, followed by the coordinator's task prompt.

This confirms that in the CURRENT session (using the `project-team` workflow with the current claudechic version), `assemble_phase_prompt()` IS being called and IS prepending identity.md content.

**But:** The researcher role has no phase-specific files, so there was nothing to inject beyond identity.md. If I had been spawned during a phase that has a `researcher/specification.md`, it would have been included.

---

## Phase File Audit: Which Roles Have Phase Files?

| Role | identity.md | specification.md | implementation.md | testing.md | Other |
|------|:-----------:|:-----------------:|:------------------:|:----------:|:-----:|
| **coordinator** | YES | YES | YES | YES | vision, setup, leadership, signoff, documentation |
| **skeptic** | YES | YES | YES | YES | -- |
| **composability** | YES | YES | YES | -- | -- |
| **implementer** | YES | -- | YES | YES | -- |
| **researcher** | YES | -- | -- | -- | -- |
| **lab_notebook** | YES | -- | -- | -- | -- |
| **binary_portability** | YES | -- | -- | -- | -- |
| **memory_layout** | YES | -- | -- | -- | -- |
| **project_integrator** | YES | -- | -- | -- | -- |

**Key finding:** The Skeptic is one of only 3 non-coordinator roles that HAS phase files. If the `type=` system works correctly (and it does in the current session), the Skeptic SHOULD receive its phase files at spawn time. The question is whether this actually happens in practice, and what happens at phase transitions.

---

## The Timeline Problem

All historical Skeptic data is from `"workflow": "solo"` or `"workflow": "ao_project_team"` -- both predate the current system. The `type=` parameter and `assemble_phase_prompt()` were added later. This means:

1. **No historical data exists for the current system.** We can't prove from JSONL data whether today's coordinator passes `type=` when spawning Skeptic.
2. **The old behavior is well-documented:** coordinator manually told agents to read role files, paraphrased phase instructions, and frequently omitted key principles.
3. **The new system CAN work** (proven by my own spawn in this session), but there's no evidence it's being used consistently for all roles.

---

## Conclusions

### What the data proves:

1. **Historical sessions (pre-current workflow): Skeptic received coordinator-written prompts that omitted 50-75% of phase file instructions.** The coordinator paraphrased some items, added project-specific context, but consistently missed general principles like "distinguish essential vs accidental complexity" and "categorize as must-fix vs should-fix."

2. **The current system (assemble_phase_prompt + type=) would fix the spawn-time problem IF the coordinator passes type=.** My own session proves identity.md injection works.

3. **Phase transitions remain completely unaddressed.** Even with the current system, when the workflow advances from "specification" to "implementation", a running Skeptic agent that was spawned during specification will still have `specification.md` content, not `implementation.md`. There is no mechanism to update it.

4. **The Skeptic is one of the best-served roles** (has 3 phase files + identity.md). Most other sub-agent roles have only identity.md, making phase transitions irrelevant for them.

### What the data does NOT prove:

1. Whether the current coordinator actually passes `type=` when spawning Skeptic (no `project-team` workflow sessions exist in audit data yet).
2. Whether the Skeptic actually read the role file when told to via filepath (old sessions). The corrections_report.json shows the Skeptic doing good work, suggesting it did read the file -- but we can't confirm programmatically.
3. Whether the missing phase instructions (essential vs accidental complexity, etc.) actually caused measurable quality loss. The Skeptic debates in the data are sophisticated and well-reasoned despite the missing context.

---

## Recommendation

The fix should address both layers:

**Layer 1 (Guardrail):** Warn-level rule when `spawn_agent` is called without `type=` during an active workflow. This catches coordinator mistakes.

**Layer 2 (System):** For the 3 roles that have phase files (skeptic, composability, implementer), add phase-transition broadcast in `advance_phase`. This requires iterating over `_app.agent_mgr` agents that have a known `agent_type`, calling `assemble_phase_prompt()` for each, and sending the new phase content via `_send_prompt_fire_and_forget()`.

**Layer 3 (Content):** Audit whether more roles need phase files. Currently only coordinator, skeptic, composability, and implementer have them.
