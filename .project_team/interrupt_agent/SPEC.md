# Specification: `interrupt_agent` MCP Tool

**Issue:** GitHub #10
**Status:** Approved by Leadership team
**Target:** `submodules/claudechic/claudechic/mcp.py`

---

## 1. Tool Signature

```python
@tool(
    "interrupt_agent",
    "Interrupt another agent's current task and optionally redirect it with a new prompt. "
    "Awaits the interrupt to completion before sending any redirect.",
    {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the agent to interrupt",
            },
            "prompt": {
                "type": "string",
                "description": "New prompt to send after interrupting (optional)",
            },
        },
        "required": ["name"],
    },
)
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | `str` | yes | Target agent name (resolved via `_find_agent_by_name`) |
| `prompt` | `str` | no | New prompt to send after interrupt completes |

**Terminology (from TerminologyGuardian):**
- Parameter is `prompt` (not `message`, `instruction`, or `redirect`)
- Tool name is `interrupt_agent` (not `stop_agent`, `cancel_agent`, `kill_agent`)
- Matches `ask_agent` / `tell_agent` naming convention: `<verb>_agent`

---

## 2. Behavior Matrix (Crystal)

All four combinations of agent state x redirect are handled:

| Agent State | `prompt` provided? | Behavior | Return message |
|-------------|-------------------|----------|----------------|
| `busy` | no | Await `agent.interrupt()`, return | `"Interrupted '<name>'"` |
| `busy` | yes | Await `agent.interrupt()`, then `await agent.send(prompt)` | `"Interrupted '<name>' and sent new prompt"` |
| `idle` | no | No-op | `"Agent '<name>' is not currently busy"` |
| `idle` | yes | Skip interrupt, send prompt directly via `_send_prompt_fire_and_forget` | `"Agent '<name>' was idle; sent new prompt"` |

**Key design:** The idle+prompt case uses `_send_prompt_fire_and_forget` (non-blocking) because there is no interrupt to sequence against. The busy+prompt case uses `await agent.send()` directly to guarantee ordering: interrupt completes before redirect is dispatched.

---

## 3. Error Cases

| Condition | Return | isError |
|-----------|--------|---------|
| `_app` or `_app.agent_mgr` is None | `"App not initialized"` | yes |
| Agent name not found | `"Agent '<name>' not found"` (or similar from `_find_agent_by_name`) | yes |
| Agent name matches caller | `"An agent cannot interrupt itself"` | yes |
| `interrupt()` raises exception | `"Failed to interrupt '<name>': <error>"` | yes |
| `send()` raises after interrupt | `"Interrupted '<name>' but failed to send new prompt: <error>"` | yes |

The last two cases use a try/except around the await calls. If interrupt fails, the redirect is NOT attempted (fail-fast). If interrupt succeeds but redirect fails, the caller is told the interrupt worked but the redirect did not.

---

## 4. Implementation Approach

### 4.1 Factory Function

Follow the `_make_close_agent` pattern (mcp.py lines 600-642) since it also uses `await` (not fire-and-forget):

```python
def _make_interrupt_agent(caller_name: str | None = None):
    """Create interrupt_agent tool with caller name bound."""

    @tool(
        "interrupt_agent",
        "Interrupt another agent's current task and optionally redirect it "
        "with a new prompt. Awaits the interrupt to completion before sending "
        "any redirect.",
        {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the agent to interrupt",
                },
                "prompt": {
                    "type": "string",
                    "description": "New prompt to send after interrupting (optional)",
                },
            },
            "required": ["name"],
        },
    )
    async def interrupt_agent(args: dict[str, Any]) -> dict[str, Any]:
        """Interrupt an agent, optionally redirecting with a new prompt."""
        try:
            if _app is None or _app.agent_mgr is None:
                return _error_response("App not initialized")
            _track_mcp_tool("interrupt_agent")

            name = args["name"]
            prompt = args.get("prompt")

            # Self-interrupt prevention
            if caller_name and name == caller_name:
                return _error_response("An agent cannot interrupt itself")

            agent, error = _find_agent_by_name(name)
            if agent is None:
                return _error_response(error or "Agent not found")

            # Idle agent: skip interrupt, optionally send prompt
            if agent.status != "busy":
                if prompt:
                    _send_prompt_fire_and_forget(
                        agent, prompt, caller_name=caller_name
                    )
                    return _text_response(
                        f"Agent '{name}' was idle; sent new prompt"
                    )
                return _text_response(
                    f"Agent '{name}' is not currently busy"
                )

            # Busy agent: await interrupt to completion
            try:
                await agent.interrupt()
            except Exception as exc:
                log.exception(f"interrupt_agent: interrupt failed for '{name}'")
                return _error_response(
                    f"Failed to interrupt '{name}': {exc}"
                )

            # Redirect with new prompt if provided
            if prompt:
                try:
                    wrapped = prompt
                    if caller_name:
                        wrapped = (
                            f"[Redirected by agent '{caller_name}']\n\n"
                            f"{prompt}"
                        )
                    await agent.send(wrapped)
                except Exception as exc:
                    log.exception(
                        f"interrupt_agent: redirect failed for '{name}'"
                    )
                    return _error_response(
                        f"Interrupted '{name}' but failed to send "
                        f"new prompt: {exc}"
                    )
                return _text_response(
                    f"Interrupted '{name}' and sent new prompt"
                )

            return _text_response(f"Interrupted '{name}'")

        except Exception as exc:
            log.exception(f"interrupt_agent failed for '{args.get('name', 'unknown')}'")
            return _error_response(
                f"Failed to interrupt '{args.get('name', 'unknown')}': {exc}"
            )

    return interrupt_agent
```

### 4.2 Call Sequence (busy + redirect)

```
interrupt_agent(name="Researcher", prompt="Focus on section 3 instead")
  |
  +-- _find_agent_by_name("Researcher") -> agent
  +-- check agent.status == "busy"
  +-- await agent.interrupt()
  |     |-- SDK interrupt (up to 5s)
  |     |-- Wait for task completion (up to 3s)
  |     |-- State -> IDLE, observer.on_complete()
  |     +-- Drain any pre-existing pending messages
  +-- await agent.send("[Redirected by ...]\n\nFocus on section 3 instead")
  |     |-- agent is IDLE now, so send() calls _start_response() immediately
  |     +-- Agent begins processing new prompt
  +-- return "Interrupted 'Researcher' and sent new prompt"
```

### 4.3 Registration

In `create_chic_server()` (mcp.py line 934-947), add after `close_agent`:

```python
tools = [
    _make_spawn_agent(caller_name),
    _make_spawn_worktree(caller_name),
    _make_ask_agent(caller_name),
    _make_tell_agent(caller_name),
    _make_whoami(caller_name),
    list_agents,
    _make_close_agent(caller_name),
    _make_interrupt_agent(caller_name),  # <-- NEW
    # Workflow guidance tools
    advance_phase,
    get_phase,
    request_override,
    acknowledge_warning,
]
```

### 4.4 Module Docstring Update

Update the docstring at mcp.py line 1-11 to include `interrupt_agent`:

```python
"""In-process MCP server for claudechic agent control.

Exposes tools for Claude to manage agents within claudechic:
- spawn_agent: Create new agent, optionally with initial prompt
- spawn_worktree: Create git worktree + agent
- ask_agent: Send question to existing agent (expects reply)
- tell_agent: Send message to existing agent (no reply expected)
- interrupt_agent: Interrupt an agent, optionally redirect with new prompt
- list_agents: List current agents and their status
- close_agent: Close an agent by name
- finish_worktree: Finish current agent's worktree (commit, rebase, merge, cleanup)
"""
```

---

## 5. Risk Mitigations

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| 1 | No lock on `interrupt()` -- concurrent calls could race | Medium | Check `agent.status != "busy"` before calling. If status changes between check and await, `interrupt()` is idempotent (INTERRUPTED -> IDLE is valid; IDLE -> IDLE is a no-op in `_set_response_state`) |
| 2 | Interrupting idle agent | Low | Explicit status check with distinct return messages per the behavior matrix |
| 3 | Redirect lost on process death | High | `await agent.interrupt()` completes (or raises) before redirect is attempted. If interrupt fails, redirect is skipped and error is returned |
| 4 | Windows hard-kill vs Unix SIGINT | Medium | No new mitigation needed -- `_sigint_fallback()` already handles platform differences (agent.py lines 618-657). The sequencing fix (await before redirect) covers both platforms |
| 5 | Infinite interrupt loops | Medium | Self-interrupt banned via `caller_name` check. Rate limiting deferred to future work if needed (same pattern as other MCP tools) |
| 6 | Mid-tool-call interrupt | Low | Document-only: same behavior as Escape key. SDK handles mid-tool gracefully. No new code needed |
| 7 | MCP handler timeout from await | Medium | Worst case is ~8s (5s SDK timeout + 3s task wait). User explicitly chose robustness over responsiveness. `close_agent` already uses direct await as precedent |

---

## 6. TUI Notification

When an agent is interrupted via this tool, the TUI should show a notification toast. The existing `agent.interrupt()` flow triggers `observer.on_complete()` which updates the sidebar status indicator (busy -> idle).

**Additional notification:** The calling context in `app.py`'s `action_escape` shows `self.notify("Interrupted")`. For MCP-triggered interrupts, the notification happens naturally through the observer pattern -- `on_complete` posts `ResponseComplete` which the UI handles.

**Redirect prefix:** When a prompt includes a redirect, the message is prefixed with `[Redirected by agent '<caller_name>']` so the target agent understands the context change. This mirrors the existing patterns:
- `tell_agent`: `[Message from agent '<caller_name>']`
- `ask_agent`: `[Question from agent '<caller_name>' - please respond back...]`
- `spawn_agent`: `[Spawned by agent '<caller_name>']`

---

## 7. File Locations

| What | Where |
|------|-------|
| New factory function `_make_interrupt_agent` | `mcp.py`, after `_make_close_agent` (~line 643) |
| Registration in `create_chic_server` | `mcp.py` line 941, after `_make_close_agent(caller_name)` |
| Module docstring update | `mcp.py` lines 1-11 |
| No changes needed | `agent.py` (reuse existing `interrupt()` as-is) |
| No changes needed | `app.py` (observer pattern handles UI updates) |
| Tests | New file: `tests/test_mcp_interrupt_agent.py` |

---

## 8. Test Plan

### Unit Tests (in `tests/test_mcp_interrupt_agent.py`)

1. **Busy agent, no redirect:** Verify `interrupt()` is called, return message confirms interruption
2. **Busy agent, with redirect:** Verify `interrupt()` then `send()` called in order, return message confirms both
3. **Idle agent, no redirect:** Verify `interrupt()` NOT called, return message says "not busy"
4. **Idle agent, with redirect:** Verify `interrupt()` NOT called, `_send_prompt_fire_and_forget` called, return message says "idle; sent new prompt"
5. **Self-interrupt prevention:** Verify error when `caller_name == name`
6. **Agent not found:** Verify error for non-existent agent name
7. **Interrupt failure:** Mock `interrupt()` to raise, verify error returned and `send()` NOT called
8. **Redirect failure:** Mock `send()` to raise after successful interrupt, verify partial-success error
9. **Redirect prefix:** Verify `[Redirected by agent '...']` prefix is applied when `caller_name` is set

### Integration Tests (marked `@pytest.mark.integration`)

10. **Full flow with mock SDK:** Create two agents, have one interrupt the other mid-response, verify state transitions

---

## 9. Composability Verification

**Axes:** Target resolution x Interrupt mechanism x Redirect -- all orthogonal.

**Seam check (swap test):**
- Swap interrupt mechanism -> tool calls `agent.interrupt()`, no internal knowledge
- Swap messaging mechanism -> tool calls `agent.send()` / `_send_prompt_fire_and_forget`, no internal knowledge
- Interrupt does not know about redirect; redirect does not know about interrupt internals

**Crystal:** 4 points (busy/idle x redirect/no-redirect), all handled with distinct code paths and return messages. No holes.

**Algebraic composition:** Both interrupt and send follow their own protocols. The tool sequences them; it does not merge them. Adding new agent states or new post-interrupt actions would not require changing the interrupt mechanism.
