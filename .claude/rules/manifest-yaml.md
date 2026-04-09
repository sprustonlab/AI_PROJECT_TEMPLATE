---
paths:
  - global/*.yaml
  - global/**/*.yaml
  - workflows/**/*.yaml
---

# Manifest YAML Files

Manifest files are the user-facing configuration surface for all claudechic systems. `ManifestLoader` parses them into typed objects.

## Valid Top-Level Sections

`rules`, `injections`, `checks`, `hints`, `phases`, `workflow_id`, `main_role`.

Each section (except `workflow_id` and `main_role`) must be a YAML list. The loader dispatches each list to the registered `ManifestSection[T]` parser for that key.

## Global Manifests

Located at `global/*.yaml`. Namespace is always `"global"`.

Global files support bare lists: if the YAML root is a list (not a mapping), the section key is inferred from the filename stem (e.g., `global/rules.yaml` → `rules` section, `global/hints.yaml` → `hints` section).

## Workflow Manifests

Located at `workflows/{name}/{name}.yaml` (filename must match directory name). Namespace is `workflow_id` from the YAML `workflow_id:` field, or the directory name as fallback.

Include `main_role:` to specify the role folder for the main agent.

## ID Rules

Use bare names only in YAML — never include colons. The parser qualifies IDs as `namespace:bare_id` automatically. Duplicate IDs (after qualification) are caught by cross-manifest validation.

## Phase-Nested Items

`advance_checks` and `hints` can be nested inside `phases:` entries. The loader extracts phase-nested hints into the top-level hints list after parsing. Advance check IDs: `{namespace}:{phase_id}:advance:{index}`. Hint IDs: `{namespace}:{phase_id}:hint:{index}` or `{namespace}:{explicit_id}`.

## Error Handling

- **Per-item: fail open** — bad entries are skipped with a warning, valid entries still load.
- **Discovery: fail closed** — if `global/` or `workflows/` directories are unreadable, the loader returns a fatal error and callers block everything.
- **Cross-manifest validation** — duplicate ID detection and phase reference validation produce warnings.

## Phase Reference Validation

Rules and injections referencing unknown phases in `phases:` or `exclude_phases:` produce validation warnings.

**Freshness:** If you modify source files matched by this rule, verify this
document still accurately describes the system behavior. Update if needed.
