# User Alignment Check — Phase 3 Specification

## Original Request Summary

User said:
> Add a "tutorial" feature to the template that combines md files, a team of agents, hints, and guardrails in a new mode to help users complete a task.

Key elements extracted:
1. **"tutorial" feature** — a new feature added to the existing template
2. **Combines md files** — markdown content is a building block
3. **A team of agents** — multiple agents collaborating, not a single agent
4. **Hints** — nudging/guidance mechanism
5. **Guardrails** — safety/prevention mechanism
6. **A new mode** — distinct operational mode, not just a command
7. **Help users complete a task** — task completion is the goal

User also provided **example tutorial ideas**: GitHub signup, SSH into cluster, learning a coding feature, git config & SSH keys, creating first project from template, pixi environments, writing/running pytest.

## Current Vision

The vision in `userprompt.md` and `STATUS.md` captures:
- ✅ Tutorial system added to template
- ✅ Markdown content as building block
- ✅ Agent teams helping
- ✅ Hints nudging
- ✅ Guardrails preventing mistakes AND verifying completion
- ✅ Dedicated tutorial mode
- ✅ Interactive walkthrough (not static docs)
- ✅ Checkpoint guardrails that prove completion

## Alignment Status: ✅ ALIGNED (with minor clarifications needed)

The vision faithfully captures user intent. No features have been removed or reinterpreted. The vision correctly elevates the guardrail concept to include **verification** (not just prevention), which is a reasonable expansion consistent with the user's phrase "help users complete a task."

## Issues & Clarifications

### ❓ USER ALIGNMENT: "a team of agents" — scope unclear
User said "a team of agents." This could mean:
- (a) Each tutorial has its own dedicated agent team (like the project_team pattern)
- (b) A shared tutorial-agent team that runs all tutorials
- (c) The existing project_team agents operate in "tutorial mode"

**Recommend:** The vision says "agent teams" generically. Team should clarify the agent architecture early. Given the template context, option (a) per-tutorial agent teams seems most natural but is also the most complex.

### ❓ USER ALIGNMENT: "a new mode" — what constitutes a mode?
User explicitly said **"in a new mode."** This implies a distinct state the template enters — not just running a command. The vision says "dedicated tutorial mode" which matches, but the spec should define what "mode" means concretely (e.g., different prompt behavior, restricted commands, tutorial-specific UI).

**Recommend:** Ensure the specification defines what entering/exiting "tutorial mode" looks like to the user.

### ❓ USER ALIGNMENT: "hints" — distinct from agent responses?
User listed "hints" as a separate component alongside "agents." This suggests hints are a **distinct mechanism** — not just the agent talking. Perhaps: contextual hints that appear at specific points, or a hint system the user can invoke on demand.

**Recommend:** Spec should clarify how hints differ from general agent guidance. User may expect something like a "hint" button/command that reveals progressive clues.

### ℹ️ USER ALIGNMENT: Tutorial examples are illustrative, not required
The user said "Tutorial ideas **include**:" — these are suggestions, not requirements. The spec should NOT commit to implementing all listed tutorials. However, the system should be **designed to support** the range they represent (from account-setup tasks to coding/testing tasks).

### ❓ USER ALIGNMENT: User said "md files" — spec should preserve this
User explicitly said tutorials **"combine md files"** — this implies tutorials are at least partly authored as markdown files. The spec should ensure tutorials are markdown-authored (not purely code-defined), keeping the authoring experience accessible to non-developers (scientists).

**Recommend:** Ensure the tutorial authoring format is markdown-based as the user specified.

## No Scope Creep Detected

The vision does not add features the user didn't request. The "checkpoint guardrail" concept is a natural refinement of "guardrails" + "help users complete a task," not new scope.

## No Scope Shrink Detected

All five user-specified components (md files, agents, hints, guardrails, new mode) are represented in the vision.

## Domain Term Flags

### "tutorial"
User's mental model: guided, step-by-step, interactive learning experience. NOT a reference doc, NOT a README, NOT a video. Think: interactive tutorial like rustlings, exercism, or Learn Git Branching. The vision matches this.

### "mode"
User said "new mode" — implies the system behaves differently when in tutorial mode. This is stronger than "a tutorial command." The spec must honor this distinction.

### "guardrails"
User's likely mental model: safety nets that prevent the user from breaking things. The vision's expansion to include "verification guardrails" is additive and aligned, not contradictory.

## Recommendation

Vision is well-aligned. Proceed to specification with these clarifications flagged for the team:
1. Define "team of agents" architecture
2. Define what "tutorial mode" concretely means
3. Define "hints" as a distinct mechanism from agent chat
4. Ensure markdown-based authoring
5. Don't over-commit to specific tutorial topics — design the system, not the content
