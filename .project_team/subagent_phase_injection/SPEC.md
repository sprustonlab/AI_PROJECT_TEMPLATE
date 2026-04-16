# Architectural Specification: Sub-Agent Phase Injection (#37)

**Author:** Composability (Lead Architect)
**Phase:** Specification
**Date:** 2026-04-15

> **Terminology:** This spec uses the canonical terms from the Terminology
> Report. See `terminology_report.md` for definitions. Key terms: **agent
> prompt** (assembled identity file + phase file), **phase context**
> (`.claude/phase_context.md`, coordinator only), **spawn prompt** (task
> instructions from coordinator), **sub-agent** (hyphenated).

---

## Problem Statement

Sub-agents in the project-team workflow (and any multi-agent workflow) have two
gaps in how they receive phase-specific instructions:

1. **Phase transitions are coordinator-only.** When `advance_phase` succeeds,
   only the coordinator's phase context is updated. Running sub-agents are never
   notified and continue operating under stale phase file content.

2. **`spawn_agent` without `type=` skips agent prompt assembly.** When the
   coordinator omits the `type` parameter, `spawn_agent` falls back to using the
   agent `name` as the role lookup key (`role_name=agent_type or name` in
   `mcp.py:279`), which fails silently on case-sensitive filesystems (NFS,
   Linux) because agent names are capitalized (e.g., `"Skeptic"`) while role
   folders are lowercase (e.g., `skeptic/`). The sub-agent receives the spawn
   prompt but no agent prompt.

3. **Premature agent closure.** The coordinator can close sub-agents at any
   time, including during active phases where those agents are needed.

---

## Fix 1: Guardrail on `spawn_agent` Without `type=`

### Placement: Workflow-Specific

**File:** `workflows/project_team/project_team.yaml` (in the `rules:` section)

**Rationale:** This is a workflow-specific rule, not a global one. Not all
workflows use the agent folder/role system. A global rule would fire for simple
multi-agent use cases where `type` is irrelevant (e.g., spawning a quick
helper agent outside any workflow). The project-team workflow specifically
requires role-based agent prompts, so the rule belongs in its manifest.

### Rule Definition

```yaml
# In workflows/project_team/project_team.yaml, rules: section

- id: spawn_agent_requires_type
  trigger: PreToolUse/mcp__chic__spawn_agent
  enforcement: warn
  detect:
    pattern: "^(?!.*\"type\"\\s*:).*$"
    field: __raw__
  message: |
    spawn_agent called without type= parameter. Sub-agents need type= set
    to their role folder name (e.g. type="composability") to receive their
    agent prompt (identity file + phase file). Acknowledge if this agent
    intentionally has no role.
```

### Design Notes

- **`warn` not `deny`:** There are legitimate cases where a sub-agent has no
  role (e.g., a temporary utility agent). `warn` forces acknowledgment but
  allows override.
- **Detection challenge:** The `detect` field matching works on a single
  `tool_input` field. MCP tool inputs are JSON objects, not single strings.
  The `__raw__` pseudo-field would need to be the JSON-serialized input.

  **Alternative approach (simpler, preferred):** Instead of a guardrail rule
  (which operates on string pattern matching of tool input fields), handle
  this directly in `spawn_agent` in `mcp.py`. When a workflow is active and
  `type` is not provided, emit a warning in the tool response:

  ```python
  # In spawn_agent, after creating the agent but before sending prompt:
  if _app._workflow_engine and not agent_type:
      result += (
          "\n[WARNING] No type= specified. This agent will not receive "
          "role-specific phase instructions. Set type= to a role folder "
          "name to enable agent prompt injection."
      )
  ```

  This is simpler, more reliable, and doesn't require pattern matching on
  JSON. **Recommended over the guardrail approach.**

### Fix 1b: Remove `agent_type or name` Fallback in `spawn_agent`

The fallback `role_name=agent_type or name` in `mcp.py:279` is a **dirty
seam** -- it conflates agent display name (user-facing, capitalized, e.g.,
`"Skeptic"`) with role folder name (filesystem, lowercase, e.g., `skeptic/`).
On case-sensitive filesystems (NFS, Linux, macOS default), `"Skeptic"` does
not match `skeptic/`, so the lookup fails silently and no agent prompt is
injected.

**Fix:** Remove the `or name` fallback entirely. If `agent_type` is `None`,
skip agent prompt assembly (the warning from Fix 1 already tells the
coordinator what happened).

```python
# Current (mcp.py:276-279):
folder_prompt = assemble_phase_prompt(
    workflows_dir=Path.cwd() / "workflows",
    workflow_id=_app._workflow_engine.workflow_id,
    role_name=agent_type or name,  # BUG: name is capitalized, folder is lowercase
    current_phase=_app._workflow_engine.get_current_phase(),
)

# Fixed:
if agent_type:
    folder_prompt = assemble_phase_prompt(
        workflows_dir=Path.cwd() / "workflows",
        workflow_id=_app._workflow_engine.workflow_id,
        role_name=agent_type,
        current_phase=_app._workflow_engine.get_current_phase(),
    )
else:
    folder_prompt = None
```

**Why not `role_name.lower()` instead?** Because:
- It papers over the seam instead of cleaning it. Agent names are display
  strings; role folders are filesystem identifiers. They are different axes.
- It introduces a new assumption ("all role folders are lowercase") that isn't
  enforced anywhere.
- The `name` fallback is inherently fragile regardless of case -- agent names
  like `"Composability-2"` or `"review-skeptic"` won't match folder names.
- The `type` parameter exists precisely to be the explicit link to the role
  folder. Making the fallback "work sometimes" masks the real problem (missing
  `type=`).

**Why not case-insensitive folder lookup?** Because:
- Adds complexity (directory iteration) for a path that shouldn't be used.
- NFS + case-insensitive search is slow and fragile.
- Same fundamental problem: agent names aren't role identifiers.

### Composability Assessment

- **Workflow-specific rule:** Only fires for project-team. Other workflows
  that use roles get the benefit if they add a similar rule. Workflows without
  roles are unaffected.
- **Code-level warning (preferred approach):** Works for ALL workflows
  automatically since it checks `_app._workflow_engine` presence, not a
  specific workflow ID.

---

## Fix 2: Phase-Transition Broadcast in claudechic

### Overview

When `advance_phase` succeeds, iterate all running agents that have a stored
role, assemble each one's agent prompt for the new phase, and deliver it via
in-band delivery (`_send_prompt_fire_and_forget`).

### Prerequisite: Store `agent_type` on the Agent Object

**Current state:** `agent_type` is passed to `AgentManager.create()` and
forwarded to `_make_options()` for environment variables and hooks, but is
**never stored** on the `Agent` instance. The broadcast mechanism needs to
know each agent's role at phase-transition time.

**Change in `agent.py`:**

```python
class Agent:
    def __init__(
        self,
        name: str,
        cwd: Path,
        *,
        id: str | None = None,
        worktree: str | None = None,
        agent_type: str | None = None,  # NEW
    ):
        # ... existing fields ...
        self.agent_type = agent_type  # NEW: role name for phase broadcast
```

**Change in `agent_manager.py`:**

```python
async def create(self, ..., agent_type: str | None = None) -> Agent:
    agent = Agent(
        name=name,
        cwd=cwd,
        worktree=worktree,
        agent_type=agent_type,  # NEW: pass through
    )
    # ... rest unchanged ...
```

### Location: `mcp.py`, `_make_advance_phase()`, After Successful Advance

Insert after the existing `_inject_phase_prompt_to_main_agent` call (after
line ~867 in current code), inside the `if result.success:` block:

```python
# Broadcast phase update to all typed sub-agents
if _app.agent_mgr:
    from claudechic.workflows.agent_folders import assemble_phase_prompt

    for agent in _app.agent_mgr.agents.values():
        # Skip: coordinator (already handled above), agents without
        # roles, and the calling agent (gets phase in tool response)
        if not agent.agent_type:
            continue
        if agent.agent_type == main_role:
            continue
        if agent.name == caller_name:
            continue

        try:
            agent_prompt = assemble_phase_prompt(
                workflows_dir=Path.cwd() / "workflows",
                workflow_id=engine.workflow_id,
                role_name=agent.agent_type,
                current_phase=next_phase,
            )
            if agent_prompt:
                _send_prompt_fire_and_forget(
                    agent,
                    f"[Phase transition: {next_phase}]\n\n"
                    f"Your updated phase instructions:\n\n"
                    f"{agent_prompt}",
                )
        except Exception:
            log.debug(
                "Failed to broadcast phase to '%s'",
                agent.name,
                exc_info=True,
            )
```

### Edge Cases

| Edge Case | Handling |
|-----------|----------|
| Agent has no `agent_type` | Skipped (no role = no phase file to look up). No `name` fallback -- see Fix 1b. |
| Agent has `agent_type` but no phase file exists for the new phase | `assemble_phase_prompt` returns identity file only, or `None` if no role folder exists. If `None`, skip. If identity-only, still deliver (re-anchors identity after long conversations). |
| Dead/closed agents | Not in `agent_mgr.agents` iterator -- naturally excluded |
| Coordinator agent | Skipped via `agent.agent_type == main_role` check. Coordinator gets phase context via filesystem injection (existing mechanism). |
| Calling agent (the one that called `advance_phase`) | Skipped via `agent.name == caller_name`. Caller already receives phase instructions in the `advance_phase` tool response. |
| Agent is busy | `_send_prompt_fire_and_forget` queues the message. It will be delivered when the agent's current task completes. This is correct behavior -- don't interrupt work, queue the update. |
| Multiple agents with same role | Each gets the same agent prompt. This is correct -- same role = same instructions. |

### The `encoding='utf-8'` Fix in `agent_folders.py`

Per cross-platform rules (CLAUDE.md), all `read_text()` calls must pass
`encoding='utf-8'`. Two violations exist in `_assemble_agent_prompt`:

```python
# Current (broken on Windows):
identity = identity_path.read_text() if identity_path.is_file() else ""
phase_content = phase_path.read_text()

# Fixed:
identity = identity_path.read_text(encoding="utf-8") if identity_path.is_file() else ""
phase_content = phase_path.read_text(encoding="utf-8")
```

This is a mandatory fix regardless of the other changes.

### Composability Assessment

- **Fully generic.** The broadcast iterates `agent_mgr.agents` and uses
  `assemble_phase_prompt()` -- both are workflow-agnostic. Any workflow that
  defines role folders gets broadcast for free.
- **No-op safe.** If a workflow has no role folders, or agents have no
  `agent_type`, the broadcast does nothing. Zero cost for simple workflows.
- **Follows the algebraic law.** The law is: "every agent with a role gets
  its role's agent prompt at every phase lifecycle event." Spawn-time
  injection already follows this law. This fix extends it to phase transitions.
  PostCompact re-injection already follows it. All three mechanisms use the
  same `assemble_phase_prompt()` function -- the shared protocol.

---

## Fix 3: `close_agent` Guardrail

### Placement: Workflow-Specific

**File:** `workflows/project_team/project_team.yaml` (in the `rules:` section)

**Rationale:** Like Fix 1, this is specific to workflows where sub-agents have
persistent roles across phases. Not all multi-agent uses require agent
persistence -- utility agents should be closeable freely.

### Rule Definition

```yaml
# In workflows/project_team/project_team.yaml, rules: section

- id: no_close_leadership
  trigger: PreToolUse/mcp__chic__close_agent
  enforcement: warn
  roles: [coordinator]
  exclude_phases: [signoff]
  message: |
    Closing a Leadership agent before signoff phase. These agents provide
    continuity across phases. Acknowledge if this agent's work is truly
    complete for the remainder of the project.
```

### Design Decisions

- **`warn` not `deny`:** There are valid reasons to close an agent early
  (e.g., agent is stuck, role is genuinely complete). `warn` forces the
  coordinator to explicitly acknowledge, creating an audit trail via the
  hit logger, but doesn't hard-block.

- **`roles: [coordinator]`:** Only the coordinator can close other agents
  (sub-agents can't close each other -- `mcp.py` prevents self-close but
  doesn't restrict cross-agent closes). Scoping to coordinator means the
  rule only fires for the primary orchestrator.

- **`exclude_phases: [signoff]`:** In the signoff phase, closing agents is
  expected cleanup. No warning needed.

- **No per-role uncloseable list:** Instead of listing which roles can't be
  closed, the rule warns on ALL closes during active phases. This is simpler
  and catches unexpected closures of any role. The coordinator can acknowledge
  to proceed.

### Alternative Considered: Deny-Level with Role Allowlist

```yaml
# NOT recommended:
- id: no_close_leadership
  trigger: PreToolUse/mcp__chic__close_agent
  enforcement: deny
  detect:
    pattern: "(composability|skeptic|user_alignment|terminology_guardian)"
    field: name
  message: "Cannot close Leadership agent. Request override if necessary."
```

**Rejected because:**
- Hardcodes role names (breaks for other workflows)
- `deny` requires user override prompt (too disruptive for a common operation)
- Pattern matching on the `name` field is fragile (agent names may differ from role names)

### Composability Assessment

- **Workflow-specific:** Only project-team gets this rule. Other workflows can
  add similar rules if they have persistent agents.
- **Role-based scoping:** `roles: [coordinator]` means the rule only evaluates
  for the coordinator agent, which is the one that typically closes others.
- **Phase-based scoping:** `exclude_phases: [signoff]` correctly allows cleanup
  in the final phase.

---

## Implementation Order

1. **`encoding='utf-8'` fix** (agent_folders.py) -- standalone, no dependencies,
   cross-platform mandatory.

2. **Remove `or name` fallback + add type warning** (mcp.py) -- Fix 1 + Fix 1b.
   These go together: remove the broken fallback and add a clear warning when
   `type` is missing during an active workflow.

3. **Store `agent_type` on Agent** (agent.py + agent_manager.py) -- prerequisite
   for broadcast. Small change, no behavioral impact on its own.

4. **Phase-transition broadcast** (mcp.py) -- the core fix. Depends on step 3.

5. **Guardrail rules** (project_team.yaml) -- standalone, can be done in
   parallel. `close_agent` warning + optionally `spawn_agent` warn rule.

6. **Phase files for sub-agent roles** -- content work, depends on step 4
   (broadcast mechanism) to be useful. Out of scope for this spec but
   tracked as follow-up.

---

## Testing Strategy

### Unit Tests (in `submodules/claudechic/tests/`)

1. **`test_agent_type_stored`:** Verify `Agent(agent_type="foo").agent_type == "foo"`.

2. **`test_broadcast_on_advance`:** Mock `agent_mgr.agents` with typed agents,
   call `advance_phase`, verify `_send_prompt_fire_and_forget` called for each
   typed agent with correct role-specific agent prompt.

3. **`test_broadcast_skips_coordinator`:** Verify agent with `agent_type == main_role`
   is not broadcast to.

4. **`test_broadcast_skips_untyped`:** Verify agent with `agent_type=None` is skipped.

5. **`test_broadcast_no_phase_file`:** Verify agent whose role has no phase file
   for the new phase receives identity-only content (or is skipped if no role
   folder exists).

6. **`test_encoding_utf8`:** Verify `_assemble_agent_prompt` reads files with
   `encoding='utf-8'` (already covered by `test_utf8_encoding.py` pattern CI).

### Integration Tests (in `tests/`)

7. **`test_guardrail_close_leadership`:** Verify the `no_close_leadership` rule
   fires `warn` for coordinator closing an agent in specification phase, and
   does NOT fire in signoff phase.

8. **`test_guardrail_spawn_without_type`:** If using the guardrail approach,
   verify the rule fires when `spawn_agent` is called without `type`.

### Markers

All new tests should use the `fast` marker (default) since they are unit/mock
tests. No real SDK connections needed.

---

## Files Modified

| File | Layer | Change |
|------|-------|--------|
| `submodules/claudechic/claudechic/agent.py` | claudechic | Add `agent_type` parameter and attribute to `Agent.__init__` |
| `submodules/claudechic/claudechic/agent_manager.py` | claudechic | Pass `agent_type` to `Agent()` constructor |
| `submodules/claudechic/claudechic/mcp.py` | claudechic | Remove `or name` fallback (Fix 1b); add type warning (Fix 1); store `agent_type` on agent at spawn; broadcast on phase advance (Fix 2) |
| `submodules/claudechic/claudechic/workflows/agent_folders.py` | claudechic | Add `encoding='utf-8'` to `read_text()` calls |
| `workflows/project_team/project_team.yaml` | template source | Add `no_close_leadership` and optionally `spawn_agent_requires_type` rules |

---

## What This Spec Does NOT Cover

- **Writing phase files for sub-agent roles.** This is content work, not
  architecture. The broadcast mechanism must exist first (otherwise phase files
  are dead code). Tracked as follow-up work.

- **Interrupting busy agents on phase transition.** The current design queues
  phase updates (fire-and-forget). If an agent is in the middle of a long task,
  it won't see the update until that task completes. This is intentional --
  interrupting mid-task is disruptive and the agent will get the update soon.
  If immediate interruption is needed, the coordinator can use `interrupt_agent`.

- **Per-agent phase context files.** The spec uses in-band delivery (chat
  messages) for sub-agents, not per-agent `.claude/phase_context.md` files.
  This avoids filesystem complexity and works with the existing PostCompact
  re-injection mechanism for context persistence.
