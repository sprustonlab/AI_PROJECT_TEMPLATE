---
paths:
  - submodules/claudechic/claudechic/workflows/**
  - workflows/**/*.yaml
  - workflows/**/identity.md
  - workflows/**/*.md
---

# Workflows System

ORCHESTRATION LAYER: imports from checks/, hints/, and guardrails/. This is the integration point — all other systems are leaf modules.

## ManifestLoader

`ManifestLoader` is the universal parser. It discovers `global/*.yaml` + `workflows/*/*.yaml`, dispatches each YAML section to registered `ManifestSection[T]` parsers, and returns a unified `LoadResult`.

- Register a parser: implement `ManifestSection[T]` protocol (`section_key` property + `parse()` method), then call `loader.register(parser)`.
- Discovery: global files = all `.yaml` in `global/`. Workflow files = `workflows/{name}/{name}.yaml` (filename must match directory name).
- Load order: global manifests first (alphabetical), then workflow manifests (alphabetical).

## WorkflowEngine

`WorkflowEngine` manages in-memory phase state, executes advance checks, and persists state via a `PersistFn` callback. Never does direct file I/O for state.

- Phase transitions use AND semantics on advance checks: sequential execution, short-circuit on first failure.
- Failed check → hint via `check_failed_to_hint()` adapter when `on_failure` config is present.
- Serialization: `to_session_state()` produces an opaque dict; `from_session_state()` restores. Validates saved phase against current manifest.
- Setup checks run without short-circuit — all checks execute and all failures are reported.

## Phase Type

`Phase` is a frozen dataclass (bridge type) with `id`, `namespace`, `file`, `advance_checks: list[CheckDecl]`, and `hints: list[HintDecl]`. Phase-nested hints are extracted into the top-level hints list by the loader after all manifests are parsed.

## PhasesParser

Parses `phases:` YAML sections into `Phase` objects. Advance check IDs are auto-generated as `{namespace}:{phase_id}:advance:{index}`. Phase-nested hint IDs: `{namespace}:{phase_id}:hint:{index}` (or `{namespace}:{raw_id}` if explicit).

## Namespace Qualification

All IDs use `namespace:bare_id` format. Use bare names in YAML (no colons). The parser qualifies them at runtime. Global manifests use namespace `"global"`. Workflow manifests use `workflow_id` from YAML or directory name.

## Chicsessions

Named multi-agent snapshots at `.chicsessions/{name}.json`. `ChicsessionManager` handles atomic save/load. The `Chicsession` dataclass stores `name`, `active_agent`, `agents: list[ChicsessionEntry]`, and `workflow_state: dict | None` (opaque, owned by engine).

## Agent Prompt Assembly

Read `identity.md` + `{phase}.md` from `workflows/{workflow}/{role}/` for agent prompt context. PostCompact hook re-injects phase context after `/compact`.

**Freshness:** If you modify source files matched by this rule, verify this
document still accurately describes the system behavior. Update if needed.
