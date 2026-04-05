# User Alignment: Improvement Review

**Reviewer:** UserAlignment
**Document:** SPECIFICATION.md (Tutorial System)
**Date:** 2026-04-04

---

## Original Request Summary

The user asked to:
> Add a "tutorial" feature to the template that combines md files, a team of agents, hints, and guardrails in a new mode to help users complete a task.

They gave 7 tutorial ideas (GitHub signup, SSH, coding features, git config, first project, pixi environments, pytest). The vision doc emphasizes **interactive, verified walkthroughs** where guardrails prove completion — not just static markdown.

---

## Overall Alignment Status: :warning: PARTIALLY MISALIGNED

The spec is architecturally sound but has drifted from user intent in ways that matter. The core issue: **the user asked for a tutorial system; the spec delivers infrastructure that could eventually support tutorials.** The spec's own words: "v1 is infrastructure. v2 is tutorial." That's a red flag.

---

## Issue 1: The v1/v2 Split Is Inverted from User Perspective

:warning: **USER ALIGNMENT: The user asked for a tutorial feature. The spec defers most tutorial functionality to v2.**

Quote from userprompt.md: *"Add a 'tutorial' feature to the template that combines md files, a team of agents, hints, and guardrails in a new mode"*

The spec's v1 delivers:
- Check primitive (infrastructure)
- Phase primitive (infrastructure)
- Phase-scoped guardrails (infrastructure)
- COORDINATOR.md split (refactoring)
- Directory rename AI_agents -> teams (refactoring)
- `/check-setup` diagnostic (utility, not tutorial)
- ONE 2-phase proof-of-concept tutorial

The spec's v2 defers:
- Tutorial UI/presentation layer
- Tutorial catalog/discovery
- Phase-aware content locking
- Multi-workflow orchestration

**From the user's perspective:** v1 delivers plumbing and one toy tutorial. The things that make it *feel* like a tutorial system (catalog, presentation, multiple tutorials) are all v2. If I were the user, my first question would be: "So after all this work, I get... one two-step pytest tutorial?"

**Recommendation:** Reframe v1 to deliver at least 2-3 complete, useful tutorials even if the infrastructure is simpler. The user's success criteria is "a user picks 'SSH into my cluster' and gets a guided walkthrough" — not "check primitives have a protocol-based architecture."

---

## Issue 2: Scope Creep — Directory Rename and COORDINATOR.md Split

:information_source: **USER ALIGNMENT: The spec includes a directory rename (`AI_agents` -> `teams`) and COORDINATOR.md split that the user did not request.**

The user asked to *add* a tutorial feature. The spec proposes renaming existing directories and splitting existing files — both significant changes to the current codebase that serve the architecture, not the user's stated need.

**Recommendation:** These may be good ideas, but they should be explicitly flagged as optional/opportunistic, not required for v1. Or move them to v2. The user didn't ask for a refactor — they asked for a feature.

---

## Issue 3: Missing — How Does a User Actually START a Tutorial?

:question: **USER ALIGNMENT: The user experience of starting and navigating a tutorial is barely described.**

Quote from userprompt.md vision: *"A user types a command, picks 'SSH into my cluster,' and gets a guided, interactive walkthrough"*

The spec has 900+ lines of architecture but never clearly answers:
- What command does the user type to start a tutorial?
- How do they see available tutorials?
- What does the experience look like step-by-step from the user's chair?
- What happens when they get stuck? (Hints are described mechanically but not experientially.)
- Can they quit mid-tutorial and resume later?

The closest we get is YAML manifests and Python protocols. That's the engineer's view, not the user's view.

**Recommendation:** Add a "User Journey" section at the top (before architecture) that walks through the experience of completing one tutorial from start to finish, from the user's perspective. Something like:

```
1. User runs `/tutorial`
2. Agent shows available tutorials: "SSH setup", "First pytest", ...
3. User picks "First pytest"
4. Agent loads tutorial, shows Phase 1 instructions
5. User writes a test file
6. System verifies the file exists (checkpoint guardrail)
7. Agent congratulates, advances to Phase 2
8. ...
```

This grounds the architecture in reality and prevents the spec from becoming an exercise in abstraction.

---

## Issue 4: Missing — "Team of Agents" Aspect

:warning: **USER ALIGNMENT: The user explicitly asked for "a team of agents" as part of the tutorial system. The spec barely addresses agent collaboration during tutorials.**

Quote from userprompt.md: *"combines md files, a team of agents, hints, and guardrails"*

The spec mentions a "tutorial-runner role file (~50 lines)" in the line count table but never describes what agents are involved in a tutorial, what roles they play, or how they collaborate. The user's mental model includes agents as a core component, not an afterthought.

**Recommendation:** Define what agents participate in a tutorial. At minimum: a tutorial-runner agent. But the user said "team" (plural). Do tutorials use a guide agent + a checker agent? Does the existing project-team agent architecture apply? This needs to be specified.

---

## Issue 5: Over-Engineering — 900+ Lines for a Two-Phase Tutorial

The spec is ~900 lines including Python protocols, dataclasses, registry patterns, enforcement level analysis, and design rationale appendices. The v1 deliverable is a two-phase pytest tutorial.

**The ratio of architecture to actual tutorial content is extremely high.** The spec designs for extensibility (check registries, multiple workflow types, four enforcement levels) that v1 doesn't use.

This isn't a code quality concern (that's Skeptic's domain) — it's an alignment concern. The user asked for something they could use. The spec delivers something that's designed to be extended. These are different goals with different tradeoffs.

**Recommendation:** Ask whether the Check protocol/registry pattern is actually needed for v1's three check types, or whether simpler functions would suffice. The protocol can be introduced in v2 when extensibility is actually needed.

---

## Issue 6: Wording Change — "Tutorial Mode" Becomes "Phase"

:question: **USER ALIGNMENT: The user said "tutorial mode" and "tutorial guardrails." The spec introduces entirely new vocabulary: "Phase," "Check," "ActivePhase," "PhaseCoherence."**

The user's domain terms carry meaning. "Tutorial mode" implies a distinct mode the system enters — with a clear beginning, a clear end, and a different feel. "Phase" is more abstract and infrastructure-flavored.

This isn't wrong per se, but the spec should acknowledge the translation and make sure the user-facing experience still feels like a "mode." Internally the system can use whatever abstractions it wants, but the user should interact with "tutorial mode," not "workflow phases."

---

## Issue 7: Only 1 of 7 Tutorial Ideas Implemented

The user provided 7 tutorial ideas: GitHub signup, SSH, coding features, git config, first project, pixi environments, pytest. The spec implements only pytest.

**Recommendation:** v1 should deliver at least 2-3 tutorials to prove the system works for different types of tasks (e.g., one command-line task like pytest, one config task like SSH/git setup). A single proof-of-concept doesn't demonstrate the system's value.

---

## What the User's First Question Would Be

After reading this spec, the user would ask:

> "This is a lot of architecture. When do I actually get tutorials I can use? And what will the experience feel like for my users?"

The spec doesn't answer either question clearly.

---

## Suggested Improvements (Priority Order)

1. **Add a User Journey section** — Walk through the complete user experience before diving into architecture. Make the abstract concrete.

2. **Rebalance v1 toward tutorials, not just infrastructure** — Deliver 2-3 working tutorials, even if the underlying engine is simpler. Ship value first, refine architecture second.

3. **Separate the refactoring from the feature** — Directory rename and COORDINATOR.md split should be flagged as optional or moved to v2. Don't conflate "add tutorials" with "restructure the project."

4. **Define the agent team for tutorials** — The user explicitly asked for agent teams. Specify what agents participate.

5. **Keep user-facing terminology close to the user's words** — "Tutorial mode" should appear in the user-facing layer even if "Phase" is the internal abstraction.

6. **Trim the spec** — The appendices and enforcement level analysis are valuable design artifacts but they bloat the spec. Move rationale to a separate design-decisions.md. Keep the spec focused on what will be built and how.

---

## What's Well-Aligned

To be fair, the spec does several things right:

- **Checkpoint guardrails with evidence** — Directly addresses the user's concern about agents claiming "done" without verification. Quote from userprompt: *"The agent can't just say 'done' — the guardrails prove it."*
- **Hints integration** — User explicitly asked for hints; the spec has a clear hints mechanism.
- **Phase-scoped guardrails** — User asked for guardrails; the spec delivers them with sophistication.
- **The Check primitive** — The concept of verifiable assertions is exactly what the user wants. The implementation may be over-engineered, but the concept is right.

---

## Summary

The spec is a well-designed infrastructure document that has drifted from being a tutorial feature spec into being a general-purpose workflow engine spec. The architecture is sound, but it prioritizes extensibility over delivering what the user asked for. **Rebalance v1 toward user value: more tutorials, less plumbing, clearer user experience.**
