---
paths:
  - submodules/claudechic/claudechic/guardrails/**
  - .claude/guardrails/**
---

# Guardrails System

LEAF MODULE: `rules.py` imports no other claudechic systems. `hooks.py` imports `ManifestLoader` under `TYPE_CHECKING` only. Never import from workflows/, checks/, or hints/.

## Terminology

- **Guardrail rule** — always-active safety rules in `.claude/guardrails/rules.yaml`.
- **Global rule** — rules in `global/rules.yaml`, always active when claudechic is running.
- **Workflow rule** — rules in workflow YAML, active only when that workflow is running.
- Both use the same `Rule` frozen dataclass and evaluation pipeline.

## Enforcement Levels

| Level | Behavior |
|-------|----------|
| `deny` | Hard block. Agent must call `request_override()` for user authorization. |
| `warn` | Acknowledgment required. Agent calls `acknowledge_warning()` to consume token. |
| `log` | Silent audit. Hit logged, execution continues. |

## Two-Step Hook Pipeline

`create_guardrail_hooks()` returns a `PreToolUse` hook closure. On every tool call:

1. **Injections first** — iterate `Injection` objects, call `apply_injection()` to mutate `tool_input` in-place. Return `updatedInput` via SDK hook protocol.
2. **Enforcement rules** — iterate `Rule` objects, check trigger → role → phase → exclude → detect pattern. First matching rule applies its enforcement level.

## Rule Scoping

- `roles` / `exclude_roles` — restrict which agent roles a rule applies to.
- `phases` / `exclude_phases` — restrict which workflow phases a rule applies to.
- Namespace filtering: rules from inactive workflows are skipped (namespace must be `"global"` or match `active_wf`).

## Rule Matching

Use `matches_trigger(rule, tool_name)` to check trigger events (format: `PreToolUse/Bash`). Use `match_rule(rule, tool_name, tool_input)` to check detect/exclude patterns against the `detect_field` (default: `"command"`).

## Override Tokens

One-time authorization via `consume_override` callback. Warn tokens consumed by `acknowledge_warning()`. Deny tokens consumed by `request_override()`. A warn token cannot satisfy a deny rule.

## Hit Logging

`HitLogger` records an append-only JSONL audit trail. Every rule match produces a `HitRecord` with outcome: `allowed`, `ack`, `blocked`, or `overridden`.

## Loader Integration

`hooks.py` receives a shared `ManifestLoader` instance. Rules are loaded fresh on every hook call (no mtime caching — NFS safe). Fail-closed: if discovery errors exist and no rules loaded, block everything.

## Template-Side Guardrails

Edit `.claude/guardrails/rules.yaml` for always-active guardrail rules. Run `generate_hooks.py` after editing to regenerate Claude Code hook files.

**Freshness:** If you modify source files matched by this rule, verify this
document still accurately describes the system behavior. Update if needed.
