# Evidence Report: Sub-Agent Phase Injection

**Author:** Researcher agent
**Date:** 2026-04-15
**Issue:** #37
**Method:** Source code tracing + runtime observation + session data analysis

---

## Executive Summary

Sub-agents receive their `identity.md` content at spawn time (when `type=` is passed), but **receive ZERO automated phase updates during phase transitions**. The `advance_phase` code path only updates the coordinator's `.claude/phase_context.md` file. There is no iteration over sub-agents, no broadcast mechanism, and no system-level code that touches sub-agents during phase transitions.

---

## Task 1: spawn_agent Code Path

**File:** `submodules/claudechic/claudechic/mcp.py`
**Function:** `_make_spawn_agent()` (lines 159-298)

### Parameters Accepted (lines 162-186)

| Parameter | Type | Required | Purpose |
|-----------|------|----------|---------|
| `name` | string | Yes | Agent display name |
| `path` | string | Yes | Working directory |
| `prompt` | string | Yes | Initial prompt text |
| `model` | string | No | Model override |
| `type` | string | No | **Role name for guardrail env vars AND prompt assembly** |
| `requires_answer` | boolean | No | Whether agent owes a reply |

### What happens with `type` parameter (lines 198-227)

When `type` is provided AND a workflow is active:
1. **Validation** (lines 206-227): Checks that a folder `workflows/{workflow_id}/{type}/` exists. If not, returns an error listing available roles.
2. **Model inheritance** (lines 229-235): If no explicit model, inherits caller's model.

### How assemble_phase_prompt() is called (lines 267-289)

```python
# Line 268-269
full_prompt = prompt
if _app._workflow_engine:
    # Lines 272-279
    folder_prompt = assemble_phase_prompt(
        workflows_dir=Path.cwd() / "workflows",
        workflow_id=_app._workflow_engine.workflow_id,
        role_name=agent_type or name,    # <-- CRITICAL: uses type param, falls back to name
        current_phase=_app._workflow_engine.get_current_phase(),
    )
    if folder_prompt:
        full_prompt = f"{folder_prompt}\n\n---\n\n{prompt}"
```

### What assemble_phase_prompt() does

**File:** `submodules/claudechic/claudechic/workflows/agent_folders.py` (lines 80-102)

Calls `_assemble_agent_prompt()` (lines 48-77) which:
1. Looks for `workflows/{workflow_id}/{role_name}/identity.md` -- reads it if exists
2. Looks for `workflows/{workflow_id}/{role_name}/{bare_phase}.md` -- reads it if exists
3. Returns `"{identity}\n\n---\n\n{phase_content}"` if both exist, or just identity

### The full_prompt sent to the sub-agent (line 283)

```
{identity.md content}

---

{phase.md content if it exists}

---

{coordinator's freeform prompt text}
```

Then wrapped by `_send_prompt_fire_and_forget()` (lines 138-156) with:
```
[Spawned by agent '{caller_name}']

{full_prompt above}
```

### Key Finding: Spawn IS wired correctly (when type is passed)

If the coordinator passes `type="researcher"` when spawning me, the system WILL prepend my `identity.md` + current phase `.md` (if it exists) to the coordinator's prompt. **This is the intended path and it works.**

---

## Task 2: advance_phase Code Path

**File:** `submodules/claudechic/claudechic/mcp.py`
**Function:** `_make_advance_phase()` (lines 793-878)

### After successful phase transition (lines 835-872)

```python
if result.success:
    # Lines 841-861: Build phase prompt for MAIN ROLE ONLY
    phase_content = ""
    main_role = getattr(engine.manifest, "main_role", None)
    if main_role:
        phase_content = assemble_phase_prompt(
            workflows_dir=Path.cwd() / "workflows",
            workflow_id=engine.workflow_id,
            role_name=main_role,       # <-- ONLY the coordinator role
            current_phase=next_phase,
        )

        # Line 865-867: Write to file for main agent
        _app._inject_phase_prompt_to_main_agent(
            engine.workflow_id, main_role, next_phase
        )

    # Lines 869-871: Return phase content inline to caller
    response = f"Advanced to phase: {next_phase}"
    if phase_content:
        response += f"\n\n--- Phase Instructions ---\n\n{phase_content}"
    return _text_response(response)
```

### What _inject_phase_prompt_to_main_agent does

**File:** `submodules/claudechic/claudechic/app.py` (lines 1688-1700)

```python
def _inject_phase_prompt_to_main_agent(self, workflow_id, main_role, current_phase):
    self._write_phase_context(workflow_id, main_role, current_phase)  # Writes .claude/phase_context.md
    self._update_sidebar_workflow_info()                               # Updates UI sidebar
```

`_write_phase_context()` (lines 1702-1747) writes to `.claude/phase_context.md` which is read as a system prompt file by Claude Code on the next turn. **This only affects the main agent (coordinator).**

### Is there ANY code that touches sub-agents during advance_phase?

**NO.** I searched the entire `advance_phase` function, `_inject_phase_prompt_to_main_agent`, and `_write_phase_context`. There is:
- No loop over `_app.agent_mgr` agents
- No call to `_send_prompt_fire_and_forget` for sub-agents
- No call to `assemble_phase_prompt` for any role other than `main_role`
- No broadcast mechanism of any kind

The comment on line 866 even says: "Still broadcast to OTHER agents asynchronously" -- but this is misleading. The function name `_inject_phase_prompt_to_main_agent` is accurate: it ONLY touches the main agent's context file.

---

## Task 3: Real Session Data

### Available Data Sources

| Source | Path | Content |
|--------|------|---------|
| Messages JSONL | `.project_team/audit_workflow/poc/gliclass/messages_310.jsonl` | 315 raw user messages from sessions |
| Classification | `.project_team/audit_workflow/poc/gliclass/gliclass_results.jsonl` | ML classification of corrections |
| Corrections Report | `corrections_report.json` | 27 sessions analyzed, 220 candidates |
| Audit DBs | `scripts/audit/audit.db`, `scripts/audit/corrections.db` | Empty (0 bytes, initialized 2026-04-14) |

### Evidence from corrections_report.json

The corrections report documents sub-agent sessions where agents diverged from intent. Notably:
- Session type "sub-agent" entries exist for agents like "Composability"
- Corrections were detected when agents misunderstood architectural concepts
- This confirms that sub-agents operate on whatever context the coordinator gave them, not on system-injected phase content

### What the coordinator actually sends to sub-agents

Based on the code path and the current session observation, the coordinator crafts a freeform prompt. If `type=` is passed, the system prepends `identity.md + phase.md`. If `type=` is NOT passed, the sub-agent gets ONLY the coordinator's freeform text.

---

## Task 4: Current Session Observation

### What I (Researcher) actually received

My initial prompt begins with:

```
[Spawned by agent 'AI_PROJECT_TEMPLATE']

# Research Agent

**Role: Research & Intelligence**
...
```

This IS the content of `workflows/project_team/researcher/identity.md` (all 240 lines). This confirms that:
1. The coordinator passed `type="researcher"` when spawning me
2. `assemble_phase_prompt()` found my `identity.md` and prepended it
3. The system IS working correctly for spawn-time injection

### What phase file exists for researcher?

```
workflows/project_team/researcher/
    identity.md   <-- EXISTS (12,243 bytes)
    (no phase files)
```

The researcher role has NO phase-specific `.md` files (no `setup.md`, `leadership.md`, etc.). So even if the system DID broadcast phase updates to sub-agents, there would be nothing to inject for the researcher role. The same may be true for other non-coordinator roles.

### What phase files exist for coordinator?

```
workflows/project_team/coordinator/
    identity.md
    vision.md
    setup.md
    leadership.md
    specification.md
    implementation.md
    testing.md
    signoff.md
    documentation.md
```

The coordinator has a `.md` file for EVERY phase. This is the only role with per-phase content.

### Current .claude/phase_context.md

Contains the coordinator's identity.md + leadership.md content. Confirms the system updates this file for the coordinator only.

---

## Summary of Findings

### What WORKS

| Mechanism | Status | Evidence |
|-----------|--------|----------|
| `type=` parameter on spawn_agent | WORKS | Code lines 198-227, validated at runtime |
| identity.md injection at spawn | WORKS | My own prompt contains full identity.md |
| phase.md injection at spawn | WORKS (if file exists) | Code lines 272-283 |
| Coordinator phase updates | WORKS | `.claude/phase_context.md` is written on advance |
| PostCompact hook for re-injection | WORKS | `agent_folders.py` lines 105-147 |

### What DOES NOT EXIST

| Mechanism | Status | Evidence |
|-----------|--------|----------|
| Phase broadcast to sub-agents on advance | DOES NOT EXIST | No sub-agent iteration in advance_phase (lines 835-872) |
| Phase-specific files for non-coordinator roles | MOSTLY ABSENT | researcher/ has only identity.md; need to check other roles |
| Automatic re-injection of phase context to sub-agents | DOES NOT EXIST | PostCompact hook is per-agent but only fires on /compact |

### The Two-Bug Problem

**Bug A (spawn-time):** If coordinator forgets to pass `type=` parameter, the sub-agent gets NO role identity at all -- only the coordinator's freeform prompt. The system works correctly when `type=` is used, but there's no enforcement that it must be used.

**Bug B (phase-transition):** Even if Bug A is fixed, there is NO mechanism to update running sub-agents when the workflow advances to a new phase. The system explicitly only updates `.claude/phase_context.md` for the main role. Sub-agents continue operating with whatever phase context they had at spawn time -- which for most non-coordinator roles is nothing, because phase-specific `.md` files don't exist for those roles.

### Architectural Observation

The current design seems intentional for a coordinator-centric model: the coordinator is the only agent that needs phase-by-phase instructions because it orchestrates the others. Sub-agents (Researcher, Skeptic, Composability, etc.) have role identities that are phase-invariant -- they do the same kind of work regardless of phase; only the coordinator's behavior changes per phase.

The question for issue #37 is whether this is the RIGHT design, or whether sub-agents would benefit from phase-aware context (e.g., "in specification phase, focus on X; in implementation phase, focus on Y").

---

## Recommendations for the Team

1. **Bug A is solvable with guardrails**: A `warn`-level rule on `spawn_agent` when `type` is missing and a workflow is active would catch coordinator mistakes.

2. **Bug B requires a design decision**: Adding phase broadcast to sub-agents is a claudechic system change. But it only matters if sub-agent roles have phase-specific `.md` files. Currently they don't, so the broadcast would be a no-op.

3. **The real fix may be workflow-level**: Create phase-specific `.md` files for key sub-agent roles (Skeptic, Composability, etc.) AND add broadcast on advance. Without both, neither alone is useful.

4. **Phase file audit needed**: Check which sub-agent roles have phase-specific files vs. only identity.md to understand the scope of the gap.
