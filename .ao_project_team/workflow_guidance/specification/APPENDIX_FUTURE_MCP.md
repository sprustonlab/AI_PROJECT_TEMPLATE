# Appendix: Future Scope (v2)

> **Not part of the current specification.** These are ideas for later consideration — not designs.

---

### 1. `get_workflow_info`

```python
@server.tool()
async def get_workflow_info() -> dict:
    """Return full workflow state as a dict."""
```

**Returns:** `workflow_id`, `current_phase`, list of all phase IDs, active `advance_checks` for current phase, workflow manifest path.

**Why:** Agents that need situational awareness beyond just the phase name — e.g., understanding what gates the next transition or which phases remain.

---

### 2. `set_phase`

```python
@server.tool()
async def set_phase(phase_id: str) -> str:
    """Manually set the current phase, bypassing advance_checks."""
```

**Behavior:** Engine updates `self._current_phase` directly and persists via chicsession. Logs a warning that advance_checks were skipped.

**Why:** Debugging, recovery, or manual intervention — e.g., rolling back to a previous phase after discovering an issue, or skipping a gate during development.

---

### 3. `list_phases`

```python
@server.tool()
async def list_phases() -> list[dict]:
    """Return all phases in the active workflow."""
```

**Returns:** List of `{"id": str, "has_advance_checks": bool}` for each phase.

**Why:** Agents can understand the workflow structure without reading the manifest YAML — useful for coordinators planning work or reporting progress.

---

### 4. `list_checks`

```python
@server.tool()
async def list_checks(phase_id: str | None = None) -> list[dict]:
    """Return advance_checks for a phase (default: current phase)."""
```

**Returns:** List of `{"type": str, "params": dict, "last_result": "pass" | "fail" | "not_run"}` for each check.

**Why:** Debugging why a phase advance is blocked — see exactly which checks exist and their last known status.

---

### 5. `run_check`

```python
@server.tool()
async def run_check(check_index: int, phase_id: str | None = None) -> dict:
    """Run a single advance_check by index and return the CheckResult."""
```

**Returns:** `{"passed": bool, "evidence": str}`.

**Why:** Debug individual checks without triggering a full phase advance — useful when one check in an AND-chain is failing and you want to iterate on fixing it.

---

## Future Hint Lifecycles

### 6. `show-until-phase-complete`

**Problem it solves:** Some hints are relevant for the duration of a phase but should automatically disappear when the phase advances. Currently, `show-once` fires once and is gone (too brief), and `show-until-resolved` requires an explicit check to pass (requires authoring a check just to suppress a hint). There's no lifecycle that says "keep showing this hint while we're in phase X, stop when we leave."

**Desired behavior:**
- Hint is shown on every evaluation cycle while the current phase matches the phase it was declared in
- When the engine advances to the next phase, the hint is automatically suppressed — no check needed
- If the workflow rolls back to the phase, the hint reactivates

**Example use case:**
```yaml
phases:
  - id: implementation
    hints:
      - message: "Run tests after every code change"
        lifecycle: show-until-phase-complete
```

This hint reminds the user throughout the implementation phase but stops once the team advances to testing (where running tests is already the primary activity).

**Why deferred:** Requires the hints pipeline to be phase-aware — `should_show()` would need access to the engine's current phase. In v1, the hints pipeline is phase-agnostic (it receives pre-filtered `HintSpec` objects). Adding phase awareness means either passing phase state into the lifecycle evaluator or having the engine pre-filter before calling `run_pipeline()`. Both are tractable but add coupling that v1 avoids.

**Implementation sketch (v2):**
- Add `source_phase: str | None` field to `HintSpec` (set by `PhasesParser` for phase-nested hints)
- New lifecycle class: `ShowUntilPhaseComplete.should_show(hint_id, state)` returns `True` when `engine.get_current_phase() == hint.source_phase`
- The engine passes current phase into `run_pipeline()` as context, or the lifecycle queries it via a callback
