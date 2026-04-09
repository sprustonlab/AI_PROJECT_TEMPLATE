---
paths:
  - submodules/claudechic/**
---

# claudechic Overview

claudechic is the TUI wrapper + MCP server + workflow engine for Claude Code.

## Core Systems

1. **Hints** — advisory toasts shown via the 6-stage pipeline. Leaf module (stdlib only).
2. **Checks** — async verification protocol (`Check.check() -> CheckResult`). Leaf module.
3. **Guardrails/Rules** — enforcement via PreToolUse hooks. Three levels: `deny`, `warn`, `log`. Leaf module.
4. **Workflows** — orchestration layer with phases, advance checks, manifest loading, and chicsessions.

## Dependency Direction

Workflows → Phases/Rules/Hints → Checks. Never import upward. Each leaf module declares its import boundary in its module docstring.

## Seam Discipline

Systems communicate through frozen dataclasses and Protocol ABCs. Never pass mutable state across system boundaries.

Key seam objects:
- `CheckResult` / `CheckDecl` — checks protocol boundary
- `HintSpec` / `HintDecl` / `HintRecord` — hints pipeline types
- `Rule` / `Injection` — guardrails enforcement types
- `Phase` — bridge type importing from both checks/ and hints/
- `LoadResult` — unified loader output consumed by all systems

## Parser Registration

All manifest section parsers are registered via `register_default_parsers()` in `workflows/__init__.py`. Add new section types by implementing `ManifestSection[T]` and registering with the loader.

## Import Boundaries

Respect each module's declared import boundary (stated in module docstrings). When modifying any system, verify you do not introduce upward imports.

**Freshness:** If you modify source files matched by this rule, verify this
document still accurately describes the system behavior. Update if needed.
