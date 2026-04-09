---
paths:
  - submodules/claudechic/claudechic/hints/**
  - hints/**
  - global/hints.yaml
---

# Hints System

LEAF MODULE: imports only stdlib. Never import from workflows/, checks/, or guardrails/.

## Pipeline

The hints engine runs a 6-stage pipeline: activation → trigger → lifecycle → sort → budget → present.

1. **Activation** — cheapest gate, dict lookup via `ActivationConfig.is_active(hint_id)`.
2. **Trigger** — call `trigger.check(state)` wrapped in try-except (IRON RULE: never crash for a hint).
3. **Lifecycle** — stateful history check via `HintLifecycle.should_show(hint_id, state_store)`.
4. **Sort** — priority ASC, last_shown_ts ASC (None→0), definition_order ASC.
5. **Budget** — take top N candidates (default 2 per evaluation cycle).
6. **Present** — resolve dynamic messages, schedule toasts with delays, call `lifecycle.record_shown()`.

## Extension Points

- Implement the `TriggerCondition` protocol: `check(state: ProjectState) -> bool` + `description` property. Keep checks pure, side-effect-free, and under 50ms.
- Implement the `HintLifecycle` protocol: `should_show(hint_id, state_store) -> bool` + `record_shown(hint_id, state_store)`. Built-in implementations: `ShowOnce`, `ShowUntilResolved`, `ShowEverySession`, `CooldownPeriod`.
- Messages can be static strings or `Callable[[ProjectState], str]` for dynamic content.

## Key Types

- `HintSpec` — frozen dataclass binding trigger + lifecycle + message + severity + priority. This is the pipeline input.
- `HintDecl` — YAML declaration parsed from manifests. Converted to `HintSpec` via adapter.
- `HintRecord` — pipeline output, ready for presentation. Carries resolved message + severity + priority.

## YAML ID Rules

Use bare names only in YAML (no colons). The parser qualifies IDs as `namespace:id` automatically. Phase-nested hints get auto-generated IDs: `{namespace}:{phase_id}:hint:{index}`.

## State Persistence

State persists to `.claude/hints_state.json`. Only `HintStateStore` reads/writes this file. Graceful degradation: missing or corrupt file = fresh start. Atomic writes via temp-then-rename.

## Severity Levels

- `info` (default) — 7s toast timeout, maps to Textual "information" severity.
- `warning` — 10s toast timeout, maps to Textual "warning" severity.

**Freshness:** If you modify source files matched by this rule, verify this
document still accurately describes the system behavior. Update if needed.
