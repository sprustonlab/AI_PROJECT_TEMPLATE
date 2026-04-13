# SPEC: Fix interrupt_agent MCP Tool (Issue #32)

## Problem Statement

The `interrupt_agent` MCP tool passes all 724 tests but fails in the real TUI. Root cause: tests mock every component below the MCP handler, hiding two code bugs and missing all integration-level failure modes.

## 1. Bug Fixes

### Fix A: Busy-agent redirect uses blocking `await agent.send()` (Critical)

**File:** `claudechic/mcp.py`, lines 709-718

**Current code (broken):**
```python
# Line 709-718: Redirect with new prompt if provided
if prompt:
    try:
        wrapped = prompt
        if caller_name:
            wrapped = (
                f"[Redirected by agent '{caller_name}']\n\n"
                f"{prompt}"
            )
        await agent.send(wrapped)  # BUG: blocks MCP handler
    except Exception as exc:
        ...
```

**Problem:** Two failures cascade:

1. **MCP timeout:** `_send_prompt_fire_and_forget` exists precisely because MCP handlers have implicit timeouts -- awaiting `agent.send()` directly can cause "stream closed" errors. Every other MCP tool (ask_agent, tell_agent, spawn_agent) uses `_send_prompt_fire_and_forget`. interrupt_agent is the sole exception on the redirect path.

2. **Silent queue swallowing:** Even if the await doesn't timeout, `Agent.send()` checks `if self._response_state != ResponseState.IDLE:` and silently queues the message. After `await agent.interrupt()` returns, the agent's response state IS IDLE (interrupt sets it at line 586). BUT there is a race: `interrupt()` at line 612 creates a `_yield_then_drain` task that calls `_drain_next_message()` after a `sleep(0)`. If the MCP handler's `send()` call arrives in the same event loop tick, it could interleave with the drain task.

**Fix:**
```python
            # Redirect with new prompt if provided
            if prompt:
                wrapped = prompt
                if caller_name:
                    wrapped = (
                        f"[Redirected by agent '{caller_name}']\n\n"
                        f"{prompt}"
                    )
                # Fire-and-forget: don't block MCP handler.
                # caller_name=None because we already wrapped the prefix.
                _send_prompt_fire_and_forget(agent, wrapped)
                return _text_response(
                    f"Interrupted '{name}' and sent new prompt"
                )
```

**Dead code removal:** Delete the `except Exception as exc:` block for redirect failure (old lines 719-726). Fire-and-forget handles errors internally via `create_safe_task`.

### Fix B: `needs_input` status not handled (Minor)

**File:** `claudechic/mcp.py`, line 688

**Current code:**
```python
if agent.status != "busy":
    # Treat as idle...
```

**Fix:** Invert to allowlist -- only skip interrupt for truly IDLE agents:
```python
from claudechic.enums import AgentStatus

if agent.status == AgentStatus.IDLE:
    # Truly idle: skip interrupt, optionally send prompt
    ...
else:
    # Busy or needs_input -- interrupt first
    ...
```

This is a denylist-to-allowlist inversion. Both `"busy"` and `"needs_input"` (and any future status values) will take the interrupt path.

### Fix B Addendum: pending_prompts leak on CancelledError

**File:** `claudechic/agent.py`, inside `interrupt()` method

**Problem:** When an agent is in `needs_input` (awaiting permission prompt inside `can_use_tool`), calling `interrupt()` cancels the response task. CancelledError propagates up through `prompt.wait()` before the cleanup code in `_handle_permission` (lines 1282-1284) runs. The `PermissionRequest` stays in `agent.pending_prompts` deque.

The UI widget itself IS cleaned up correctly (`_show_prompt` has a `finally` block). Only the agent-level `pending_prompts` leaks.

**Fix:** Add cleanup to `interrupt()` after task cancellation, before setting IDLE:
```python
        # Clear stale permission prompts left by CancelledError
        self.pending_prompts.clear()
```

This is safe because:
- Any pending permission prompt was part of the interrupted response
- The UI already cleaned up its widget via `_show_prompt`'s `finally`
- No other code path is waiting on these stale prompts

## 2. Test Improvements

### Category 1: State Machine Tests (Real ResponseState transitions)

#### Test 2.1: `test_interrupt_transitions_response_state`
**What:** Verify `interrupt()` moves `_response_state` through `STREAMING -> INTERRUPTED -> IDLE`.
**Setup:** Real Agent, mock ClaudeSDKClient (interrupt returns immediately), mock `_response.task` (completes when cancelled).
**Assertions:**
- Before: `agent._response_state == ResponseState.STREAMING`
- After: `agent._response_state == ResponseState.IDLE`
- After: `agent.status == AgentStatus.IDLE`
**Components:** Real Agent + real enums. Mock SDK client.

#### Test 2.2: `test_interrupt_sets_idle_before_send`
**What:** After `interrupt()` completes, confirm `_response_state == IDLE` so that a subsequent `send()` call dispatches immediately (doesn't queue).
**Setup:** Real Agent, mock SDK client. Call `interrupt()`, then call `send("redirect")`. Instrument `_start_response` to confirm it was called (not the queue path).
**Assertions:**
- `len(agent._pending_messages) == 0`
- `_start_response` was called (via mock/spy)
**Components:** Real Agent. Mock SDK client.

### Category 2: TOCTOU Race Test

#### Test 2.3: `test_status_changes_between_check_and_interrupt`
**What:** Agent status is `busy` when MCP handler checks, but transitions to `idle` before `interrupt()` is called.
**Setup:** Mock Agent with side effect: `interrupt()` is a no-op because agent is already idle.
**Assertions:**
- `interrupt()` on idle agent doesn't crash
- MCP handler returns success (not error)
**Components:** Mock Agent (simulating race). Real MCP handler.

### Category 3: Redirect Delivery Tests

#### Test 2.4: `test_redirect_after_interrupt_delivers_not_queues`
**What:** After interrupt completes, redirect prompt is delivered (triggers `_start_response`), not silently queued.
**Setup:** Real Agent with mock SDK client. Put agent in STREAMING state. Call MCP `interrupt_agent` handler with `prompt="redirect"`. After Fix A: fire-and-forget schedules `agent.send()` as background task.
**Assertions:**
- `len(agent._pending_messages) == 0` (NOT queued)
- New response task exists (redirect dispatched)
**Components:** Real Agent, real asyncio event loop. Mock SDK client.

#### Test 2.5: `test_redirect_does_not_block_mcp_handler`
**What:** Verify MCP handler returns immediately after scheduling redirect.
**Setup:** Mock Agent with a `send()` that sleeps 10 seconds.
**Assertions:**
- Handler returns in < 1 second
- No `isError` in result
**Components:** MCP handler (real). Mock agent with slow send.

### Category 4: Timeout and Fallback Tests

#### Test 2.6: `test_interrupt_sdk_timeout_triggers_sigint`
**What:** When `client.interrupt()` takes longer than 5s, the SIGINT fallback fires.
**Setup:** Real Agent, mock SDK client whose `interrupt()` never returns.
**Assertions:**
- `await agent.interrupt()` completes (not hang forever)
- SIGINT fallback was called (via spy)
- `agent.status == AgentStatus.IDLE` (recovered)
**Components:** Real Agent. Mock SDK client (hanging). Real asyncio timers.
**Marker:** `@pytest.mark.slow` (involves real 5s timeout)

#### Test 2.7: `test_interrupt_task_timeout_triggers_cancel`
**What:** When `_response.task` doesn't finish within 3s after SDK interrupt, it gets cancelled + SIGINT.
**Setup:** Real Agent, mock SDK client (interrupt returns immediately), mock `_response.task` that never completes.
**Assertions:**
- `response_task.cancelled()`
- SIGINT fallback was called
- `agent.status == AgentStatus.IDLE`
**Components:** Real Agent, real asyncio. Mock task + SDK.
**Marker:** `@pytest.mark.slow`

### Category 5: Needs-Input Interrupt Tests

#### Test 2.8: `test_interrupt_needs_input_agent`
**What:** Agent in `needs_input` (awaiting permission) gets interrupted and redirected.
**Setup:** Real Agent with mock SDK client. Put agent in `needs_input` state with `_response_state == STREAMING`.
**Assertions:**
- Interrupt path was taken (not idle path)
- `agent.pending_prompts` is empty (no leaked requests)
- `agent.status == AgentStatus.IDLE`
- `agent._response_state == ResponseState.IDLE`
- Redirect prompt (if any) delivered via fire-and-forget
**Marker:** `@pytest.mark.integration`

#### Test 2.11: `test_permission_request_cleaned_up_after_interrupt`
**What:** CancelledError during permission wait doesn't leak PermissionRequest.
**Setup:** Real Agent, mock SDK client. Start response, trigger permission prompt. Verify `agent.pending_prompts` has 1 request.
**Assertions:**
- After `await agent.interrupt()`: `agent.pending_prompts` is empty
- `agent.status == AgentStatus.IDLE`
**Components:** Real Agent, mock SDK.

### Category 6: Rewrite "Integration" Test

#### Test 2.9: `test_full_interrupt_redirect_flow_real_agent` (replaces Test 10)
**What:** End-to-end flow with real Agent.
**Setup:** Real Agent with mock SDK client. Start response (STREAMING/BUSY). Call MCP `interrupt_agent` handler with redirect. Run event loop.
**Assertions:**
- Agent state: `AgentStatus.IDLE`, `ResponseState.IDLE`
- Redirect delivered (not queued): `len(agent._pending_messages) == 0`
- MCP handler returned success
**Components:** Real Agent, real MCP handler, real asyncio. Mock SDK client only.
**Marker:** `@pytest.mark.integration`

### Category 7: Drain-After-Interrupt Race Test

#### Test 2.10: `test_drain_after_interrupt_does_not_eat_redirect`
**What:** The `_yield_then_drain` task from `interrupt()` must not interfere with redirect prompt.
**Setup:** Real Agent with pending inter-agent messages AND a redirect. Call interrupt, then schedule redirect via fire-and-forget. Run event loop.
**Assertions:** Both the queued message AND the redirect are eventually delivered.
**Components:** Real Agent, real asyncio. Mock SDK client.

## 3. Files to Change

| File | Change Type | Description |
|------|------------|-------------|
| `claudechic/mcp.py` | Bug fix | Fix A: Replace `await agent.send()` with pre-wrapped `_send_prompt_fire_and_forget(agent, wrapped)` (caller_name=None). Remove dead error-handling code. |
| `claudechic/mcp.py` | Bug fix | Fix B: Import `AgentStatus`, change `!= "busy"` to `== AgentStatus.IDLE`. |
| `claudechic/agent.py` | Bug fix | Fix B addendum: Add `self.pending_prompts.clear()` to `interrupt()` before setting IDLE. |
| `tests/test_mcp_interrupt_agent.py` | Update | Reflect fire-and-forget behavior, remove partial-success test. |
| `tests/test_interrupt_agent_integration.py` | New file | Tests 2.1-2.4, 2.6-2.11 requiring real Agent with mock SDK client. |
| `tests/conftest.py` | Add fixture | Shared fixture: real Agent with mock ClaudeSDKClient (supports connect, interrupt, query, receive_response). |

## 4. Test Markers

- Tests 2.1-2.5, 2.11: No special marker (fast, < 1s each)
- Tests 2.6-2.7: `@pytest.mark.slow` (involve real timeouts, 5-8s each)
- Tests 2.8-2.10: `@pytest.mark.integration`

## 5. Verification Criteria

The fix is correct when:
1. `interrupt_agent` with redirect on a busy agent returns immediately (< 1s) from the MCP handler
2. The redirect prompt is actually delivered to the agent (starts a new response), not silently queued
3. `interrupt_agent` on a `needs_input` agent interrupts it (doesn't treat it as idle)
4. Permission prompts are cleaned up after interrupt (no leaked pending_prompts)
5. All existing unit tests still pass (with updates for the new fire-and-forget behavior)
6. The "partial success" error path is removed (fire-and-forget can't raise)
