# Anyio CancelScope CPU Spin Bug

## The Problem

After disconnecting from the SDK (e.g., during `/resume`), the app would spin at 25% CPU even when idle. This persisted even after closing the agent.

## Root Cause

When the SDK disconnects, it cancels an anyio `CancelScope` containing a task group:

```python
# In claude_agent_sdk/_internal/query.py
async def close(self) -> None:
    self._closed = True
    if self._tg:
        self._tg.cancel_scope.cancel()
        with suppress(anyio.get_cancelled_exc_class()):
            await self._tg.__aexit__(None, None, None)
    await self.transport.close()
```

The issue: when `cancel_scope.cancel()` is called, anyio's `_deliver_cancellation()` method starts trying to cancel all tasks in the scope. If a task completes (`done=True`) but its `task_done` callback hasn't run yet to remove it from `_tasks`, the scope keeps retrying:

```python
# In anyio/_backends/_asyncio.py CancelScope._deliver_cancellation()
for task in self._tasks:
    should_retry = True  # <-- Always retries if tasks exist
    ...

if should_retry:
    self._cancel_handle = get_running_loop().call_soon(
        self._deliver_cancellation, origin  # <-- Reschedules itself
    )
```

This creates a spin loop of ~56,000 event loop iterations per second, burning 25% CPU.

## Diagnosis

We added `/debug profile` to run cProfile for 2 seconds. Fresh start showed ~350 `select` calls. After `/resume`, it showed ~112,000 `select` calls with `_deliver_cancellation` matching almost exactly.

Added `/debug scopes` to find cancelled CancelScopes with pending tasks:
```
Cancelled scope with 1 tasks:
  - Task-22: done=True, cancelled=False
```

A done task stuck in the scope's `_tasks` set.

## The Fix

We need both `sleep(0)` AND a gc-based cleanup after `client.disconnect()` in `agent.py`:

```python
await self.client.disconnect()
...
# Yield to event loop so task_done callbacks can clean up cancel scopes.
await asyncio.sleep(0)
self._cleanup_stale_cancel_scopes()

def _cleanup_stale_cancel_scopes(self) -> None:
    import gc
    from anyio._backends._asyncio import CancelScope
    for obj in gc.get_objects():
        if isinstance(obj, CancelScope) and obj._cancel_called:
            if hasattr(obj, '_tasks'):
                done = [t for t in obj._tasks if t.done()]
                for t in done:
                    obj._tasks.discard(t)
```

The `sleep(0)` gives the event loop one iteration to run `task_done` callbacks. However, this alone is not reliable - some tasks may still be stuck in the scope's `_tasks` set. The gc-based cleanup is required as a fallback to forcibly remove any done tasks that weren't cleaned up.

We initially thought `sleep(0)` alone would suffice, but testing showed the CPU spin returned without the gc cleanup. Both are needed.

## Affected Versions

- anyio 4.12.1
- claude-agent-sdk (bundled)
- Python 3.14

## Related

This may be a race condition in anyio's task cleanup during cancellation, or an issue with how the SDK uses `suppress()` around `__aexit__`. Consider filing an issue upstream if reproducible outside claudechic.
