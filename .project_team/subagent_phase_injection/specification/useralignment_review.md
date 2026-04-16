# User Alignment Review -- Specification Phase

## User Requirements Checklist

Extracted from userprompt.md + user's in-session clarifications:

| # | User Requirement | Source |
|---|-----------------|--------|
| R1 | Investigate what's actually happening -- don't assume | userprompt.md: "The team should investigate what's actually happening" |
| R2 | Sub-agents should receive role-specific phase instructions (identity.md + {phase}.md) | userprompt.md: "Sub-agents spawned during workflow phases don't receive their role-specific phase instructions" |
| R3 | Phase transitions need automated context injection to sub-agents | userprompt.md: "no automated way to inject updated context to sub-agents during phase transitions" |
| R4 | Prevent coordinator from closing agents when it shouldn't | userprompt.md: "prevent coordinator from closing agents when it shouldn't" |
| R5 | Propose fixes at ANY layer (guardrails, claudechic, workflow, or hybrid) | userprompt.md: "propose fixes at whichever layer makes sense" |
| R6 | Multiple fix options, not one prescribed solution | STATUS.md lists 5 directions; user wants team to suggest |
| R7 | Sparse phase files are a SYMPTOM -- sub-agents SHOULD have phase-specific instructions | User in-session: "this is from the fact that skeptic is missing things" |

---

## Coverage Assessment: What the Spec MUST Include

### [OK] R1 -- Investigation complete, findings are evidence-based

The Researcher and Skeptic both traced actual code paths and produced evidence. Nobody assumed. The team discovered:
- Spawn-time injection EXISTS but is fragile (depends on `type=` being passed)
- Phase-transition broadcast DOES NOT EXIST
- close_agent has minimal guards

This is exactly the discovery-first approach the user wanted.

### [WARNING] R2 -- Spec must not downplay spawn-time injection

The Skeptic correctly notes spawn-time injection "exists but is fragile." However, the user's original framing was: "The coordinator sends something, but not the actual phase files." The spec must address making spawn-time injection **reliable**, not just acknowledge it exists. Specifically:

- The `type=` parameter must be prominently documented or enforced (guardrail warn if missing)
- The silent `except Exception` swallowing must be fixed
- The `encoding='utf-8'` cross-platform bug must be fixed

The Skeptic's recommendation #5 says "Do NOT add a spawn_agent guardrail for phase injection -- the system should handle this automatically." This is a reasonable position IF the system fix is reliable. But the user originally asked for "a guardrail warn on spawn without the right MD file context." **The user explicitly requested a guardrail here.** The spec should include it, even if the system fix makes it a belt-and-suspenders approach.

```
? USER ALIGNMENT: User said "guardrail warn on spawn without the right MD file context."
Skeptic says "Do NOT add a spawn_agent guardrail."
These directly conflict. User's explicit request takes priority.
Recommend: Include the guardrail (warn level) as the user asked, even alongside system fixes.
```

### [OK] R3 -- Phase-transition broadcast is a clear gap, all agents agree

Everyone confirms: `advance_phase` only updates the coordinator. The spec MUST include a mechanism for sub-agent notification. The Skeptic's suggestion of `tell_agent` (queued, non-interrupting) is a reasonable approach.

### [WARNING] R4 -- close_agent guards must be specified concretely

The user said "prevent coordinator from closing agents when it shouldn't." The Skeptic calls this "theoretical" and recommends a warn-level guardrail. This is fine as a starting point, but the spec needs to define **what "shouldn't" means**. Options the spec should evaluate:

1. Warn when closing an agent that is currently busy (status != idle)
2. Warn when closing an agent that hasn't reported back (has pending work)
3. Warn when closing an agent during a phase where that role is active
4. Deny closing agents that have `requires_answer` pending

The spec should pick at least one concrete policy, not just "add a guardrail."

### [OK] R5 -- Multi-layer approach is well-covered

The Skeptic's hybrid recommendation (Direction 4: claudechic for mechanism + guardrails for behavior) correctly spans layers. The Researcher confirmed the architectural context. The spec should present this as the recommended approach while noting alternatives.

### [WARNING] R6 -- Spec should present options, not just one recommendation

The user wanted the team to "suggest how to handle it" with multiple options. The Skeptic's report DOES analyze 4 directions with pros/cons. The spec should preserve this multi-option presentation, not collapse to a single "this is what we'll do." Let the user choose.

### [WARNING] R7 -- Phase file content is IN SCOPE, not deferred

The user confirmed sparse phase files are a symptom. The spec must address this. Two options:

**Option A: Include phase file creation in the spec scope.** Write phase files for key roles (at minimum: skeptic, user_alignment, implementer, test_engineer) for the most common phases (specification, implementation, testing).

**Option B: Mechanism-only, with a "missing phase file" warning.** Fix the injection mechanism, and add a hint/warning when a sub-agent role has no phase file for the current phase. This makes the gap visible so it gets addressed organically.

The user's reaction suggests Option A is closer to their intent -- they see missing files as the bug's consequence, implying they should be filled in. But Option B is defensible if the spec explains why. **The spec should present both and let the user decide.**

---

## Items NOT in User's Request (Scope Creep Watch)

| Item | Risk | Assessment |
|------|------|------------|
| PostCompact hook improvements | Low | Mentioned by Researcher but not in user's request. Fine to note but shouldn't be a primary deliverable. |
| Documenting `type` param for workflow authors | Low | Supportive of the fix, not scope creep. |
| Encoding bug fix in agent_folders.py | Low | Trivial, cross-platform mandatory per CLAUDE.md. Include it. |
| Phase broadcast to stale agents (spawned 2+ phases ago) | Medium | Edge case worth noting in spec but shouldn't drive design. |
| Race condition (TOCTOU) between spawn and advance | Low | Skeptic correctly flagged. Note but don't over-engineer. |

None of these are scope creep -- they're reasonable supporting work. No red flags here.

---

## Summary: Spec Readiness Checklist

| Requirement | Covered? | Action Needed |
|------------|----------|---------------|
| R1: Investigation | YES | Findings are solid |
| R2: Spawn-time injection fix | PARTIAL | Must include user's requested guardrail warn, not just system fix |
| R3: Phase-transition broadcast | YES | Clear gap, clear fix direction |
| R4: close_agent guards | PARTIAL | Must define concrete "when" policy, not just "add a guardrail" |
| R5: Multi-layer approach | YES | Hybrid is well-justified |
| R6: Multiple options | AT RISK | Spec must present options, not collapse to one |
| R7: Phase file content | AT RISK | Must address content creation or visibility, not ignore |

---

## Recommendation

The spec is on solid ground for the mechanism fixes (R2, R3, R5). The three areas needing attention before spec approval:

1. **Include the spawn_agent guardrail the user asked for** -- even if the Skeptic disagrees, the user explicitly requested it
2. **Define concrete close_agent policy** -- "warn level guardrail" is too vague; specify the trigger conditions
3. **Address phase file content** -- present Option A (write them) and Option B (warn when missing) and let user choose
