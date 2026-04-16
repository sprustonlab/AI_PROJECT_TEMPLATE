# Chicsession Analysis: What Skeptic Actually Received

**Author:** Researcher agent
**Date:** 2026-04-15
**Issue:** #37
**Method:** Direct comparison of raw JSONL session data from `.chicsessions/` pointers to Claude session files

---

## Executive Summary

**SMOKING GUN FOUND.** The Cluster2 chicsession (2026-04-10) uses the `project-team` workflow but the coordinator spawned the Skeptic **without the `type=` parameter**. The Skeptic received ONLY the coordinator's freeform prompt -- zero identity.md, zero phase files. The current session (Inject_Bug37, 2026-04-15) DOES pass `type="skeptic"` -- confirming the fix works but proving the problem was real in prior sessions.

---

## Data Sources

### Chicsession Files (`.chicsessions/`)

These are JSON metadata files containing agent names, session UUIDs, and workflow state. The actual conversation data lives in `~/.claude/projects/-groups-spruston-home-moharb-AI-PROJECT-TEMPLATE/{session_id}.jsonl`.

| Chicsession | Date | Workflow | Phase | Agents |
|-------------|------|----------|-------|--------|
| **Inject_Bug37** | 2026-04-15 | project-team | leadership | 6 (Coord, Comp, Term, Skeptic, UA, Researcher) |
| **Cluster2** | 2026-04-11 | project-team | signoff | 11 (Coord + 4 leadership + 4 implementers + TestEngineer + Researcher) |
| **Backend** | 2026-04-11 | project-team | specification | 5 (Coord + 4 SpecReviewers) |
| **project-team** | 2026-04-10 | project-team | signoff | 1 (Coord only - agents already closed) |

### Session JSONL Files Used

| Agent | Session UUID | Source Chicsession |
|-------|-------------|-------------------|
| Coordinator (Cluster2) | `95eb7cca-b5df-4f28-996b-a9ae71c3309f` | Cluster2 |
| Skeptic (Cluster2) | `0a8174c2-03a6-4e5d-b44e-40cb9f066728` | Cluster2 |
| Coordinator (current) | `0b8e7bba-aa88-4d22-984d-a2628c356eba` | Inject_Bug37 |

---

## Evidence Exhibit A: Cluster2 Session -- Skeptic Spawn (NO `type=` parameter)

### Raw JSONL from coordinator session (line 76)

The coordinator's `spawn_agent` call:

```json
{
  "name": "mcp__chic__spawn_agent",
  "input": {
    "name": "Skeptic",
    "path": "/groups/spruston/home/moharb/AI_PROJECT_TEMPLATE",
    "requires_answer": true,
    "prompt": "You are the **Skeptic** leadership agent for the \"bootstrapping_bridge\" project.\n\n## Your Role\nChallenge assumptions, identify risks, failure modes, and over-engineering. Push back on unnecessary complexity.\n\n## Context\n..."
  }
}
```

**CRITICAL: No `"type"` field.** The coordinator passed `name`, `path`, `requires_answer`, and `prompt` -- but NOT `type`.

### What the Skeptic actually received (from Skeptic's JSONL, line 1)

```
[Spawned by agent 'AI_PROJECT_TEMPLATE']

You are the **Skeptic** leadership agent for the "bootstrapping_bridge" project.

## Your Role
Challenge assumptions, identify risks, failure modes, and over-engineering.
Push back on unnecessary complexity.

## Context
We're designing the **bootstrapping bridge** for AI_PROJECT_TEMPLATE --
connecting Copier questionnaire (generation time) with runtime claudechic workflows.

**The Problem:** Two-phase onboarding with no state handoff. Copier asks questions
and generates stubs, runtime workflows ignore what was collected.

**6 Seams identified:** cluster setup, git setup, codebase integration, claudechic mode,
quick start presets, MCP tools.

**Reference:** PR #18 converts cluster_setup from a markdown doc to a 7-phase
executable workflow.

## Your Task
1. Read these files:
   - /groups/spruston/home/moharb/AI_PROJECT_TEMPLATE/template/copier.yml
   - /groups/spruston/home/moharb/AI_PROJECT_TEMPLATE/.project_team/bootstrapping_bridge/STATUS.md

2. Challenge the following assumptions:
   - Do we actually need a generic "bridge"? Or is this 2-3 specific fixes?
   - Is the "two-phase onboarding" actually a problem users experience, or theoretical?
   - How many of the 6 seams are real pain points vs nice-to-haves?
   - Is re-verification actually BAD? Maybe it's a feature (validation)?
   - Could we solve this by just making Copier ask LESS and letting workflows do MORE?
   - What's the cost of building a generic bridge vs just fixing each seam individually?

3. Identify risks:
   - Over-engineering: are we building an abstraction nobody asked for?
   - State synchronization: what happens when Copier and workflows disagree?
   - Maintenance burden: does a bridge become another thing to keep in sync?
   - User confusion: does adding a bridge layer make onboarding MORE complex?

4. Propose the **simplest thing that could work** as a counterpoint to any elaborate design.

Reply back with your critique using `tell_agent` to Coordinator.
```

### What the Skeptic identity.md contains (but was NOT sent)

The full 117-line identity.md includes these critical sections that the Skeptic never received:

**Missing: "Essential vs Accidental Complexity" framework:**
```markdown
## Essential vs Accidental Complexity

- **Accidental complexity:** Complexity from poor design choices. Eliminate it.
- **Essential complexity:** Complexity inherent to the problem. Solve it, don't avoid it.

If the user explicitly asks for X and X is complex, the complexity is **essential**.
Don't propose Y because Y is simpler -- propose how to make X as simple as possible
while still being X.
```

**Missing: "Four Questions" evaluation framework:**
```markdown
## Four Questions

1. "Does this fully solve what the user asked for?" -- Not an easier version. The actual requirement.
2. "Is this complete?" -- No shortcuts. All inputs, all states, all paths handled.
3. "Is complexity obscuring correctness?" -- Can we simplify while still solving the full problem?
4. "Is simplicity masking incompleteness?" -- Are we proposing something simpler because it's
   better, or because we're not solving the hard part?
```

**Missing: "Red Flags" checklist:**
```markdown
## Red Flags

- "Works for the common case" -> shortcut, not solution
- "Just do X first" -> burden shifted, not handled
- "We can add that later" -> incomplete now, technical debt forever
- Can't explain the flow in one sentence -> too complex to verify
- "X is too hard, let's do Y instead" -> avoiding essential complexity
- "This is simpler" (but solves a different problem) -> not simpler, just incomplete
```

**Missing: "On Verifiability" evaluation lens:**
```markdown
## On Verifiability

Code is **verifiable** when you can *see* it's correct by reading it -- not hope,
not "the tests pass."
```

**Missing: "Authority" bounds:**
```markdown
## Authority

- You CAN demand complete solutions over shortcuts
- You CAN push for simpler approaches that are easier to verify
- You CANNOT accept shortcuts disguised as simplicity
- You CANNOT cut features from userprompt.md
```

### What the phase file (leadership phase) would have added

The Skeptic was spawned during the `leadership` phase. The Skeptic has NO `leadership.md` file -- so `assemble_phase_prompt()` would have returned just identity.md. But since `type=` was missing, even identity.md was not injected.

---

## Evidence Exhibit B: Current Session (Inject_Bug37) -- Skeptic Spawn (WITH `type=`)

### Raw JSONL from coordinator session (line 95)

```json
{
  "name": "mcp__chic__spawn_agent",
  "input": {
    "name": "Skeptic",
    "path": "/groups/spruston/home/moharb/AI_PROJECT_TEMPLATE",
    "type": "skeptic",
    "requires_answer": true,
    "prompt": "You are the Skeptic agent for issue #37: Sub-agent phase markdown not injected.\n\nRead /groups/spruston/home/moharb/AI_PROJECT_TEMPLATE/.project_team/subagent_phase_injection/STATUS.md for the full vision.\n\nYour job: Challenge assumptions and find risks. Investigate:\n\n1. Read submodules/claudechic/claudechic/mcp.py -- the spawn_agent function..."
  }
}
```

**`"type": "skeptic"` IS PRESENT.** This means `assemble_phase_prompt()` was called with `role_name="skeptic"`, found `workflows/project_team/skeptic/identity.md`, and prepended it to the coordinator's prompt.

### What the Skeptic in the current session received

```
{identity.md content - all 117 lines}

---

{coordinator's freeform prompt about issue #37}
```

The Skeptic in THIS session got its full identity, including the Four Questions, the Red Flags, the Essential vs Accidental framework, and the Authority bounds.

---

## Evidence Exhibit C: Also Missing `type=` -- All Other Agents in Cluster2

The same coordinator session (Cluster2, line 72) shows the Composability spawn:

```json
{
  "name": "mcp__chic__spawn_agent",
  "input": {
    "name": "Composability",
    "path": "/groups/spruston/home/moharb/AI_PROJECT_TEMPLATE",
    "requires_answer": true,
    "prompt": "You are the **Composability** leadership agent for the \"bootstrapping_bridge\" project..."
  }
}
```

**No `type` field.** Same pattern for Terminology (line 74), UserAlignment (line 78), and Researcher.

In contrast, the current session (Inject_Bug37) passes `type=` for ALL agents:
- Line 91: `"type": "composability"`
- Line 93: `"type": "terminology"`
- Line 95: `"type": "skeptic"`
- Line 97 (likely): `"type": "user_alignment"` or similar

---

## Evidence Exhibit D: Backend Session -- Non-Standard Agent Names

The Backend chicsession used agent names that DON'T match role folders:
- `SpecReviewer-Arch`, `SpecReviewer-Risk`, `SpecReviewer-UX`, `SpecReviewer-Code`

These names have no corresponding `workflows/project_team/specreviewer-arch/` directory. Even WITH `type=`, these agents would receive nothing unless they use a `type` that maps to an existing role folder. Without `type=`, the fallback logic uses `agent_type or name` (mcp.py line 279), which would try `SpecReviewer-Arch` as the role name -- which doesn't exist.

---

## Side-by-Side: What Was Lost

### Cluster2 Skeptic (NO identity injection)

| Skeptic Identity Component | Present? | Impact |
|---------------------------|----------|--------|
| "Complete, Correct, Simple -- in that order" principle | NO | Agent lacks the priority framework |
| Essential vs Accidental Complexity framework | NO | Agent can't distinguish problem complexity from design complexity |
| Four Questions evaluation method | NO | Agent reviews without structured methodology |
| "Simplicity in Code vs Tests" distinction | NO | Agent might over-simplify tests |
| Verifiability evaluation lens | NO | Agent doesn't know to check if code is verifiable by reading |
| Red Flags checklist | NO | Agent misses common anti-patterns |
| Authority bounds | NO | Agent doesn't know what it can/can't demand |
| Communication protocol | NO | Agent may use wrong inter-agent tools |

### Current Session Skeptic (WITH identity injection)

| Skeptic Identity Component | Present? | Impact |
|---------------------------|----------|--------|
| All of the above | YES | Full identity context available |
| Phase-specific instructions | NO* | No `leadership.md` for Skeptic role |

*The Skeptic's `specification.md`, `implementation.md`, and `testing.md` files exist but were NOT injected because the current phase is `leadership`, and there is no `skeptic/leadership.md`.

---

## The Evolution: What Changed Between Sessions

| Aspect | Cluster2 (2026-04-10) | Inject_Bug37 (2026-04-15) |
|--------|----------------------|--------------------------|
| Workflow | `project-team` | `project-team` |
| claudechic version | 2.1.87 | 2.1.87 |
| Coordinator passes `type=` | **NO** | **YES** |
| Sub-agents get identity.md | **NO** | **YES** |
| Phase files injected | **NO** (no type + no matching phase file) | **PARTIALLY** (type passed, but no leadership.md for skeptic) |

**The system code hasn't changed.** The `type=` parameter and `assemble_phase_prompt()` existed in BOTH sessions (same claudechic version 2.1.87). The difference is purely **whether the coordinator chose to pass `type=`**. This confirms the problem is behavioral, not a missing feature -- the feature exists but the coordinator doesn't reliably use it.

---

## Conclusions

### 1. The `type=` parameter is the single point of failure

The system works correctly when `type=` is passed. Identity.md is prepended. But coordinators don't reliably pass it. In Cluster2 (a full project-team workflow run with 11 agents), NONE of the spawns included `type=`.

### 2. This is a guardrail problem, not a system bug

The claudechic code at mcp.py lines 267-289 correctly handles identity injection. The `assemble_phase_prompt()` function works. The issue is that coordinators write freeform prompts and forget (or don't know) to include `type=`. A warn-level guardrail that fires when `spawn_agent` is called without `type=` during an active workflow would catch this.

### 3. Phase file gap remains even with `type=` fixed

The Skeptic has `specification.md`, `implementation.md`, and `testing.md` but NOT `leadership.md`. Since Leadership is the spawn phase, even with `type="skeptic"`, the Skeptic gets identity.md but NOT phase-specific instructions at spawn time. And when the workflow advances to specification/implementation/testing, there is NO broadcast to update the Skeptic with its new phase instructions.

### 4. Non-standard agent names bypass the system entirely

The Backend session used names like `SpecReviewer-Arch` that don't match any role folder. The `type=` parameter is the ONLY way to map arbitrary agent names to role folders. Without it, the fallback `agent_type or name` (mcp.py line 279) uses the agent name, which fails silently.

### 5. Phase transition remains the critical unfixed gap

Even in the current session (which correctly passes `type=`), advancing from leadership to specification would NOT update the Skeptic with `skeptic/specification.md`. The `advance_phase` code only updates the coordinator's `.claude/phase_context.md`.
