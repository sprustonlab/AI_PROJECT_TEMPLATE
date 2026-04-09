---
paths:
  - submodules/claudechic/claudechic/checks/**
---

# Checks System

LEAF MODULE: `protocol.py` is stdlib only. `builtins.py` imports only from `checks/protocol`. `adapter.py` imports only `CheckResult` and `OnFailureConfig` from `checks/protocol`.

## Check Protocol

`Check` is an async protocol: `async def check(self) -> CheckResult`. Every check type implements this. The engine calls `check()` without knowing the implementation.

`CheckResult` is a frozen dataclass with `passed: bool` and `evidence: str`. This crosses the Check-Engine seam.

## Built-in Check Types

| Type | Passes when |
|------|-------------|
| `command-output-check` | Command stdout matches a regex pattern (30s timeout) |
| `file-exists-check` | File exists at the given path |
| `file-content-check` | File content matches a regex pattern (line-by-line scan) |
| `manual-confirm` | User confirms via injected `AsyncConfirmCallback` |

## Extension

Call `register_check_type(name, factory)` where factory is `(params: dict) -> Check`. Register in `builtins.py` at module level alongside existing registrations.

## Declaration vs Execution

`CheckDecl` is the YAML declaration (frozen dataclass with `id`, `namespace`, `type`, `params`, `on_failure`, `when`). `Check` is the executable. Conversion happens via `_build_check(decl)` which looks up the type in the registry.

For `manual-confirm` checks, the engine injects `confirm_fn` into params before building.

## Adapter Seam

`check_failed_to_hint()` in `adapter.py` bridges failed checks into the hints pipeline. Returns a hint data dict with `trigger: "always"` (fires immediately via `AlwaysTrue`) and the `on_failure` message + evidence.

## Advance Check Semantics

Advance checks use AND semantics — sequential execution, short-circuit on first failure. Failed check → hint via adapter if `on_failure` config is present.

**Freshness:** If you modify source files matched by this rule, verify this
document still accurately describes the system behavior. Update if needed.
