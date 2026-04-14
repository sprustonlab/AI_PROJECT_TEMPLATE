---
paths:
  - submodules/claudechic/claudechic/hints/**
  - hints/**
  - global/hints.yaml
---

# Hints System

LEAF MODULE: imports only stdlib. Never import from workflows/, checks/, or guardrails/.

## Two Patterns for Hints

claudechic has two distinct patterns for showing hints to users. Choose the right one based on what triggers the hint.

### Pattern 1: Pipeline Hints (YAML-defined)

For hints triggered by **project disk state** -- files existing, config values, workflow phase, etc.

- Defined in `global/hints.yaml` or workflow manifests
- Evaluated by the 6-stage pipeline at startup, workflow activation/deactivation
- Triggered by `TriggerCondition.check(ProjectState)` -- a frozen snapshot of disk/config state
- Lifecycle managed by pipeline (`ShowOnce`, `CooldownPeriod`, etc.)
- Respects `/hints off` activation gate
- All existing YAML hints use `AlwaysTrue` trigger + `show-once` lifecycle (rotating tip pool)

**When to use:** The hint's relevance can be determined from disk state (files, config, phase). The hint is not time-sensitive -- showing it a few seconds after startup is fine.

### Pattern 2: Event-Driven Hints (code-defined)

For hints triggered by **live UI events** -- agent count changes, first sidebar mount, widget interactions, etc.

- Defined inline in the relevant `app.py` handler (e.g., `on_agent_created`)
- Triggered by a specific code path, not the pipeline
- Uses direct `app.notify()` for display
- Uses `HintStateStore` for cross-session persistence (optional)
- Does NOT go through the pipeline, does NOT appear in hints.yaml
- NOT affected by `/hints off` (they're direct notifications)

**When to use:** The hint responds to a live UI event that `ProjectState` doesn't capture (agent spawned, widget clicked for the first time, etc.). The hint must appear at a precise moment.

**Implementation pattern:**

```python
# In the relevant app.py handler:
def on_agent_created(self, agent):
    # ... existing code ...

    # Event-driven hint: show once ever when agent count first reaches 2
    if len(self.agent_mgr.agents) == 2:
        from claudechic.hints.state import HintStateStore

        store = HintStateStore(self._cwd)
        hint_id = "event:agent-switcher-tip"
        if store.get_times_shown(hint_id) == 0:
            self.notify(
                "Tip: Use Ctrl+1-9 to switch agents, "
                "or click them in the sidebar.",
                severity="information",
                timeout=8,
            )
            store.increment_shown(hint_id)
            store.save()
```

**Key rules for event-driven hints:**
- Guard with `HintStateStore.get_times_shown() == 0` for show-once behavior
- Always call `store.save()` after mutation (atomic write to `.claude/hints_state.json`)
- Keep the hint logic in the handler where the event occurs -- don't scatter it
- Use `event:` prefix in hint IDs to distinguish from pipeline hints (see naming below)

**Naming convention for HintStateStore keys:**
- Pipeline hints: `namespace:bare-id` (e.g., `global:tip_worktree`) -- auto-qualified by parser
- Event-driven hints: `event:descriptive-name` (e.g., `event:agent-switcher-tip`) -- manually set in code
- The `event:` prefix prevents collisions with YAML-defined hint IDs and makes grep easy

**Grandfathered exception:** The existing key `"agent-switcher-tip"` in `app.py` predates this convention and does not carry the `event:` prefix. Do not rename it -- the key is persisted in `.claude/hints_state.json` on user machines and renaming would reset shown-state for existing users. All new event-driven hint IDs should follow the `event:` prefix convention.

**Where event-driven hints live in code:**
- In the app.py handler that detects the event (e.g., `on_agent_created`, `on_agent_switched`)
- NOT in `hints/` module (that's the pipeline system)
- NOT in `global/hints.yaml` (that's for pipeline hints)

## Pipeline Details

The hints engine runs a 6-stage pipeline: activation -> trigger -> lifecycle -> sort -> budget -> present.

1. **Activation** -- cheapest gate, dict lookup via `ActivationConfig.is_active(hint_id)`.
2. **Trigger** -- call `trigger.check(state)` wrapped in try-except (IRON RULE: never crash for a hint).
3. **Lifecycle** -- stateful history check via `HintLifecycle.should_show(hint_id, state_store)`.
4. **Sort** -- priority ASC, last_shown_ts ASC (None->0), definition_order ASC.
5. **Budget** -- take top N candidates (default 2 per evaluation cycle).
6. **Present** -- resolve dynamic messages, schedule toasts with delays, call `lifecycle.record_shown()`.

### Pipeline Evaluation Points

| Trigger Point | Budget | Timing |
|---|---|---|
| App startup (`on_mount`) | 2 toasts | 2s initial delay, 6s gap |
| Workflow activation | 2 toasts | 5s gap (non-startup) |
| Workflow deactivation | 1 toast | 5s gap (non-startup) |

## Extension Points

- Implement the `TriggerCondition` protocol: `check(state: ProjectState) -> bool` + `description` property. Keep checks pure, side-effect-free, and under 50ms.
- Implement the `HintLifecycle` protocol: `should_show(hint_id, state_store) -> bool` + `record_shown(hint_id, state_store)`. Built-in implementations: `ShowOnce`, `ShowUntilResolved`, `ShowEverySession`, `CooldownPeriod`.
- Messages can be static strings or `Callable[[ProjectState], str]` for dynamic content.

## Key Types

- `HintSpec` -- frozen dataclass binding trigger + lifecycle + message + severity + priority. This is the pipeline input.
- `HintDecl` -- YAML declaration parsed from manifests. Converted to `HintSpec` via adapter.
- `HintRecord` -- pipeline output, ready for presentation. Carries resolved message + severity + priority.
- `ProjectState` -- frozen snapshot passed to triggers. Contains: `root`, `copier` (CopierAnswers), `session_count`, `current_phase`. Also exposes filesystem primitives: `path_exists()`, `dir_is_empty()`, `file_contains()`, `count_files_matching()`.

## YAML ID Rules

Use bare names only in YAML (no colons). The parser qualifies IDs as `namespace:id` automatically. Phase-nested hints get auto-generated IDs: `{namespace}:{phase_id}:hint:{index}`.

## State Persistence

State persists to `.claude/hints_state.json`. Only `HintStateStore` reads/writes this file. Graceful degradation: missing or corrupt file = fresh start. Atomic writes via temp-then-rename.

Both pipeline hints and event-driven hints share the same state file. The `event:` prefix on event-driven hint IDs prevents collisions.

## Severity Levels

- `info` (default) -- 7s toast timeout, maps to Textual "information" severity.
- `warning` -- 10s toast timeout, maps to Textual "warning" severity.

**Freshness:** If you modify source files matched by this rule, verify this
document still accurately describes the system behavior. Update if needed.
