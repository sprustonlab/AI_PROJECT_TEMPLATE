# Composability Analysis: Sub-Agent Phase Injection (#37)

**Author:** Composability (Lead Architect)
**Date:** 2026-04-15

---

## Domain Understanding

The system has a multi-agent workflow engine where a **coordinator agent** spawns **sub-agents** with specific roles (e.g., Composability, Skeptic, UserAlignment). Each role has per-phase markdown instructions (`identity.md` + `{phase}.md`) stored in `workflows/{workflow}/{role}/`. The problem: sub-agents don't reliably receive their role-specific phase instructions, and running sub-agents aren't updated when the phase transitions.

---

## Architectural Analysis: Three Layers

### Layer 1: claudechic (Core Engine)

#### What spawn_agent currently does (mcp.py lines 267-294)

**Good news: spawn-time injection already exists.** When `_app._workflow_engine` is active and a prompt is provided, `spawn_agent` calls `assemble_phase_prompt()` with the agent's `type` (role) and prepends the role-specific phase markdown to the coordinator's prompt. This means:

- `assemble_phase_prompt(workflow_id, role_name=agent_type, current_phase)` is called
- The result (identity.md + phase.md for that role) is prepended to the coordinator's spawn prompt
- The full prompt is: `{role_phase_markdown}\n\n---\n\n{coordinator_prompt}`

**The real gap is NOT at spawn time -- it's at phase transition time.**

#### What advance_phase does (mcp.py lines 793-878)

When `advance_phase` succeeds:

1. It assembles phase prompt for `main_role` only (the coordinator's role)
2. It calls `_inject_phase_prompt_to_main_agent()` which writes to `.claude/phase_context.md`
3. `.claude/phase_context.md` is a single file that becomes part of the system prompt

**Critical gap:** `advance_phase` never notifies running sub-agents. The `_inject_phase_prompt_to_main_agent` method name says it all -- it only targets the main agent. There is NO iteration over `agent_mgr.agents` to send phase updates to sub-agents.

#### What _write_phase_context does (app.py lines 1702-1747)

Writes to `.claude/phase_context.md` for ONE role only (always `main_role`). This is a single shared file -- it cannot contain instructions for multiple roles simultaneously. Sub-agents read the same `.claude/phase_context.md` and get the coordinator's phase instructions, not their own.

#### PostCompact hook (agent_folders.py lines 105-146)

The PostCompact hook re-injects phase context after `/compact`. It captures `agent_role` at creation time and correctly uses the agent's own role. **This is the one place where per-role context is handled correctly for sub-agents** -- but only after compaction, not on phase transitions.

### Layer 2: Guardrails System

The guardrail hook pipeline (`hooks.py`) operates on `PreToolUse` events. It:

- Receives `agent_role` at hook creation time (captured in closure)
- Can match on tool name, detect patterns, and phases
- Can block, warn, or log

**Key observation:** Guardrails fire on MCP tool calls (`PreToolUse/spawn_agent`, `PreToolUse/advance_phase`). They CAN detect when spawn_agent or advance_phase is called, but they operate in the **blocking** paradigm (block/warn/allow). They are not designed for **injection** of additional context into tool responses. The `Injection` mechanism modifies `tool_input` fields, which is for command rewriting, not for adding system context.

### Layer 3: Workflow Definitions / Template

The workflow YAML and role folder structure (`workflows/project_team/{role}/{phase}.md`) contain the actual content. This layer is correct -- the content exists and is properly organized per-role and per-phase.

---

## Composability Axes

### Axis 1: WHO (Agent Role)
- Values: coordinator, composability, skeptic, user_alignment, terminology_guardian, ...
- Each role has its own identity.md and per-phase markdown
- This axis is well-separated at the content layer

### Axis 2: WHEN (Phase Lifecycle Event)
- Values: spawn-time, phase-transition, post-compact, mid-task
- Each event type has a different injection mechanism (or lacks one)
- **This axis has holes** -- phase-transition doesn't serve sub-agents

### Axis 3: WHAT (Content Type)
- Values: identity, phase instructions, coordinator prompt
- These compose cleanly (identity + phase = full context)
- The `assemble_phase_prompt()` function handles this correctly

### Axis 4: HOW (Delivery Mechanism)
- Values: file-based (.claude/phase_context.md), inline (prepended to prompt), message (send to agent)
- **This axis has dirty seams** -- file-based assumes one role per project, inline works for any role

---

## Crystal Analysis: Holes Identified

### Hole 1: Phase transition x Sub-agents (CRITICAL)

| Event | Coordinator | Sub-agents |
|-------|-------------|------------|
| Spawn | identity + phase (via file) | identity + phase (inline) -- WORKS |
| Phase advance | Updated via file + tool response | **NOTHING** -- NOT NOTIFIED |
| Post-compact | Re-injected via hook | Re-injected via hook -- WORKS |

The crystal has a gaping hole at (phase-transition, sub-agent). This is the core bug.

### Hole 2: File-based delivery is single-role

`.claude/phase_context.md` can only contain ONE role's instructions. When a sub-agent reads it (which all agents in the same directory do), they get the coordinator's instructions. This is a fundamental design flaw in using a shared file for per-role content.

### Hole 3: No sub-agent registry for broadcast

When `advance_phase` fires, the engine has no notion of "all agents with roles that need phase updates." The `agent_mgr` has all agents, and each agent has an `agent_type` attribute, but `advance_phase` never iterates over them.

---

## Proposed Fix Directions

### Direction A: claudechic System Fix (Auto-Injection at Phase Transition)

**Where:** `mcp.py` `_make_advance_phase()`, after successful advance

**What:** After advancing, iterate over all running agents that have an `agent_type`, assemble their role-specific phase prompt, and send it via `_send_prompt_fire_and_forget()`.

```python
# After the existing _inject_phase_prompt_to_main_agent call:
if _app.agent_mgr:
    for agent in _app.agent_mgr.agents.values():
        if agent.agent_type and agent.name != caller_name:
            try:
                phase_prompt = assemble_phase_prompt(
                    workflows_dir=Path.cwd() / "workflows",
                    workflow_id=engine.workflow_id,
                    role_name=agent.agent_type,
                    current_phase=next_phase,
                )
                if phase_prompt:
                    _send_prompt_fire_and_forget(
                        agent,
                        f"--- Phase Transition: {next_phase} ---\n\n{phase_prompt}",
                    )
            except Exception:
                log.debug("Failed to inject phase to %s", agent.name, exc_info=True)
```

**Composability assessment:** This is the ALGEBRAIC fix. It follows the law: "every agent with a role gets its role's phase content at every lifecycle event." It works for ANY workflow, not just project-team. New workflows automatically benefit.

**Tradeoffs:**
- Sub-agents receive phase updates as chat messages (not system prompt), which means they may be compacted away. But the PostCompact hook already handles that.
- If a sub-agent is busy, the message queues (which is correct behavior).
- The coordinator can still send task-specific context in addition.

### Direction B: Guardrail Rule (Warn/Deny on spawn_agent without phase context)

**Where:** `global/rules.yaml` or workflow YAML `rules:` section

**What:** A guardrail rule that detects `spawn_agent` calls and warns if the `prompt` field doesn't contain phase-relevant keywords.

**Composability assessment:** This is a BAND-AID, not a fix. It works for the spawn-time case but:
- Cannot detect missing phase context in the prompt content reliably (pattern matching on natural language)
- Does nothing for phase transitions
- Adds friction without solving the root cause
- Workflow-specific rules would need per-workflow configuration

**Verdict:** Low value. The spawn-time injection already works in claudechic. The real problem is phase transitions, and guardrails can't inject messages into agents.

### Direction C: Workflow Definition Fix

**Where:** `workflows/project_team/coordinator/` phase files

**What:** Add explicit instructions to the coordinator's phase markdown telling it to relay phase context to sub-agents using `tell_agent`.

**Composability assessment:** This WORKS but is NOT ALGEBRAIC. It relies on:
- The coordinator following instructions correctly (unreliable)
- The coordinator summarizing/relaying content (lossy)
- Every workflow author remembering to add these instructions
- The coordinator not being busy or ignoring the instruction

**Verdict:** Useful as a safety net (defense in depth) but should not be the primary mechanism. The coordinator may still choose to summarize or omit content.

### Direction D: Hybrid (RECOMMENDED)

Combine Direction A (claudechic auto-injection) + Direction C (workflow instructions as fallback):

1. **Primary:** claudechic auto-injects phase content to all typed agents on phase transition (Direction A). This is the algebraic, works-for-all-workflows fix.

2. **Secondary:** Workflow phase instructions include a note like "Ensure sub-agents have acknowledged their phase transition" -- this gives the coordinator awareness without making it the sole mechanism.

3. **Optional enhancement:** Add a `get_phase` enhancement that shows each agent's role and whether they've received the current phase content. This gives visibility.

---

## Seam Analysis

### Seam: spawn_agent <-> assemble_phase_prompt

**Status: CLEAN.** The `assemble_phase_prompt()` function takes `(workflows_dir, workflow_id, role_name, current_phase)` and returns `str | None`. It doesn't know about agents, MCP, or the TUI. The caller (spawn_agent) handles delivery.

### Seam: advance_phase <-> phase delivery

**Status: DIRTY.** `advance_phase` hardcodes delivery to `main_role` only. The concept of "who needs phase content" is not abstracted -- it's baked into the single call to `_inject_phase_prompt_to_main_agent`. The method name encodes the assumption.

**Fix:** The delivery logic should iterate over all agents with roles, using the same `assemble_phase_prompt()` function with each agent's role. The seam between "what phase are we in" and "who needs to know" should be explicit.

### Seam: .claude/phase_context.md <-> Claude Code system prompt

**Status: INHERENTLY SINGLE-ROLE.** This file-based mechanism can only serve one role. For multi-role support, either:
- Each agent needs its own context file (complex, requires per-agent `.claude/` directories)
- Sub-agents get phase content via chat messages instead of system prompt (simpler, and compaction is already handled)

The inline approach (chat messages) is the pragmatic choice since the PostCompact hook already handles re-injection.

---

## Summary

| Fix Direction | Fixes Spawn | Fixes Phase Transition | Works for All Workflows | Complexity |
|---------------|-------------|----------------------|------------------------|------------|
| A: claudechic auto-inject | Already works | YES | YES (algebraic) | Low-medium |
| B: Guardrail rules | Partial | NO | NO | Low |
| C: Workflow instructions | Depends on coordinator | Unreliable | NO (per-workflow) | Low |
| D: Hybrid (A+C) | YES | YES | YES | Medium |

**Recommendation:** Direction D (Hybrid), with Direction A as the primary fix in claudechic. The fix is ~20 lines of code in `mcp.py`'s `advance_phase`, follows the existing `assemble_phase_prompt` law, and benefits all workflows automatically.

The close_agent issue mentioned in the STATUS.md is a separate concern -- it's about the coordinator prematurely closing agents, which is a workflow instruction / guardrail problem, not a phase injection problem.
