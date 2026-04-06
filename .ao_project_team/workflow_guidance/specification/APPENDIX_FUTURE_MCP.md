# Appendix: Future MCP Tools (Not in Scope)

> **Future scope — not part of the current specification.** These are potential MCP tools for later consideration. Ideas, not designs.

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
