# User Alignment Report -- Issue #37: Sub-agent Phase Markdown Not Injected

## Original Request Summary

From userprompt.md:
1. **"Sub-agents spawned during workflow phases don't receive their role-specific phase instructions (identity.md + {phase}.md)"**
2. **"The coordinator sends something, but not the actual phase files"**
3. **"There is no automated way to inject updated context to sub-agents during phase transitions"**
4. **"Prevent coordinator from closing agents when it shouldn't"**
5. **"The team should investigate what's actually happening and propose fixes at whichever layer makes sense (guardrails, claudechic, workflow, or hybrid)"**

## Investigation Findings

### Finding 1: spawn_agent DOES inject phase markdown at spawn time

Contrary to the issue title, `spawn_agent` in mcp.py (lines 267-289) **already has code to inject role phase files**:

```python
if _app._workflow_engine:
    folder_prompt = assemble_phase_prompt(
        workflows_dir=Path.cwd() / "workflows",
        workflow_id=_app._workflow_engine.workflow_id,
        role_name=agent_type or name,
        current_phase=_app._workflow_engine.get_current_phase(),
    )
    if folder_prompt:
        full_prompt = f"{folder_prompt}\n\n---\n\n{prompt}"
```

**Critical detail:** This uses `agent_type or name` as the role lookup. If the coordinator spawns an agent with `type="user_alignment"`, the system reads `workflows/project_team/user_alignment/identity.md` + the current phase `.md`. If `type` is not provided, it falls back to the agent `name`, which may not match a role folder.

**So the real question is:** Does the coordinator actually pass `type=` when spawning? If it writes the spawn prompt itself (which it does -- the prompt is freeform text), the coordinator controls what `type` gets set to.

### Finding 2: Phase transitions DO NOT notify sub-agents

The `advance_phase` function (mcp.py lines 793-878) only injects phase context to the **main agent** (coordinator):
- Line 865: `_app._inject_phase_prompt_to_main_agent(...)` -- writes to `.claude/phase_context.md`
- This only updates the coordinator's context file
- **No mechanism exists to notify running sub-agents that the phase changed**
- Sub-agents spawned in phase N continue with phase N context even after advancing to phase N+1

This confirms the user's statement: **"there is no automated way to inject updated context to sub-agents during phase transitions."**

### Finding 3: close_agent has minimal guards

The `close_agent` function (mcp.py lines 602-643) has only two restrictions:
1. An agent cannot close itself (`name == caller_name`)
2. Cannot close the last agent (`len(agent_mgr) <= 1`)

**No other controls exist.** Any agent (including the coordinator) can close any other agent at any time. There are no:
- Phase-based restrictions (e.g., "don't close during active work")
- Role-based restrictions (e.g., "coordinator can't close leadership agents")
- Confirmation requirements
- Guardrail rules on close_agent

This confirms the user's concern about the coordinator closing agents when it shouldn't.

### Finding 4: Most roles lack phase-specific markdown

Phase coverage across roles (workflow has 8 phases: vision, setup, leadership, specification, implementation, testing, documentation, signoff):

| Role | Phase files | Coverage |
|------|------------|----------|
| coordinator | 8 of 8 | Full |
| skeptic | 3 (impl, spec, testing) | Partial |
| implementer | 2 (impl, testing) | Partial |
| user_alignment | 1 (specification) | Minimal |
| composability | 2 (impl, spec) | Partial |
| terminology | 1 (specification) | Minimal |
| researcher | 0 | identity.md only |
| test_engineer | 0 | identity.md only |
| ui_designer | 0 | identity.md only |
| lab_notebook | 0 | identity.md only |
| others | 0 | identity.md only |

Even if injection works, **most roles have no phase markdown to inject**. This is a content gap alongside the mechanism gap.

## Alignment Status

### [OK] ALIGNED: Discovery-first approach

The user said **"investigate what's actually happening"** -- team should NOT assume the system is broken. In fact, spawn-time injection code exists. The real issues are:
1. Whether the coordinator actually uses `type=` correctly when spawning
2. Phase transition notification is missing for sub-agents
3. close_agent is unrestricted
4. Phase file content is sparse for non-coordinator roles

### [OK] ALIGNED: Multi-layer fix options

The user said fixes can be **"at ANY layer -- guardrails, claudechic, workflow, or hybrid."** STATUS.md correctly lists 5 fix directions including hybrid approaches.

### [WARNING] Potential drift risk: Scope of "injection"

The user's framing distinguishes two separate problems:
1. **Spawn-time injection** -- "The coordinator sends something, but not the actual phase files"
2. **Phase-transition injection** -- "no automated way to inject updated context to sub-agents during phase transitions"

These require different fixes. The team must not conflate them into one solution. Spawn-time injection is partially working (code exists, depends on coordinator behavior). Phase-transition injection is completely missing.

### [WARNING] Potential drift risk: close_agent scope

The user said **"prevent coordinator from closing agents when it shouldn't."** This is a separate concern from phase injection but explicitly in the user's request. The team must not defer this as "out of scope" -- it was part of the original ask.

### ? NEEDS CLARIFICATION: What "shouldn't" means for close_agent

The user said the coordinator "shouldn't" close agents at certain times but didn't specify the rules. Options:
- Never close during active phases?
- Only close after agent reports completion?
- Require confirmation?
- Role-based (never close leadership agents)?

**Recommend:** Team should propose specific close_agent guard options rather than asking the user to define the policy.

## Recommendations for the Team

1. **Separate spawn-time vs. transition-time issues** -- they have different root causes and fixes
2. **Test the spawn-time path** -- Does the coordinator actually pass `type=` when spawning? If not, the existing injection code never triggers. This is testable right now.
3. **close_agent guards are a MUST** -- Don't let this get deprioritized. It's in the user's explicit request.
4. **Content gap matters** -- Even perfect injection is useless if roles have no phase files. Consider whether the fix includes adding phase markdown for key roles, or just the mechanism.
5. **Propose multiple options** -- User explicitly wants options, not one prescribed solution.
