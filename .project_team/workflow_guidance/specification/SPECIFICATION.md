# Workflow Guidance System — Architecture Specification

> **Status:** Implementation-ready specification.
> **Scope:** Infrastructure in claudechic that lets workflows define phases, rules, checks, and hints via YAML manifests and markdown files. The project-team workflow is the first workflow built on this infrastructure.

---

## 1. Vision

Extend claudechic to offer a unified guidance system — advisory and enforced, positive and negative — where any workflow is just YAML manifest + markdown content. Users write manifests and agent folders. claudechic provides the engine, the loader, the checks, and the hooks. One combined system, one set of primitives, any workflow type.

**Why:**
- Guidance is currently scattered across multiple systems, formats, and locations. Rules, checks, and hints each have their own mechanism.
- Users shouldn't need to learn three separate systems. A single pattern — YAML manifests + markdown content in `global/` and `workflows/` — makes guidance easy to author, understand, and maintain.
- The 2×2 framing (advisory/enforced × positive/negative) gives users a clear mental model for where any piece of guidance fits and how it behaves.

**Foundational principle:** Decouple guidance authoring from guidance infrastructure. A workflow author writes YAML + markdown. claudechic provides the loader, engine, checks, hooks, and delivery. No code changes needed to create a new workflow. If claudechic ever needs `if workflow == "project-team":` branches, the system has failed.

### File-Based System Replacement

**The file-based hook system (`.claude/guardrails/generate_hooks.py` → shell hook scripts → Claude Code hooks protocol) is replaced by the closure-based SDK hook system described in this spec. The file-based system will be removed after the new system is validated.**

Specifically:

| File-Based Component | Replaced By | Notes |
|---|---|---|
| `generate_hooks.py` | Closure-based hooks in `guardrails/hooks.py` | Python closures replace generated shell scripts |
| `.claude/guardrails/hooks/` (generated shell scripts) | `create_guardrail_hooks()` return value | SDK hook protocol replaces Claude Code hooks protocol |
| `role_guard.py ack` mechanism (ack tokens, file-based TTL) | `acknowledge_warning` MCP tool + one-time token (see §8) | Agent calls MCP tool → token stored → retry consumes token |
| `.claude/guardrails/rules.yaml` | `global/rules.yaml` + workflow manifests | Rules now in manifests with namespace prefixing |
| `.claude/guardrails/hits.jsonl` | `.claude/hits.jsonl` via `guardrails/hits.py` | Richer data (outcome, agent role, enforcement level) |
| Session markers (`.claude/guardrails/sessions/`) | `Chicsession.workflow_state` + `CLAUDE_AGENT_ROLE` env var | Role set at spawn time, state in chicsession |

---

## 2. Terminology

> All terms are defined canonically here. Other sections reference but do not redefine them.

### Core Concepts

| Term | Definition |
|------|-----------|
| **Workflow** | A named configuration — YAML manifest + markdown content in a directory under `workflows/` — that defines phases, rules, checks, and hints. Each workflow has a `workflow_id` (kebab-case, e.g. `project-team`) used in namespacing. |
| **Manifest** | A YAML file declaring rules, phases, checks, and hints. Two kinds: **global manifests** (`global/*.yaml`, always active, no phases — each file is a bare list, section inferred from filename: `rules.yaml` → rules parser) and **workflow manifest** (`workflows/<name>/<name>.yaml`, scoped to one workflow, dict with section keys). All files in `global/` share the `global` namespace. Workflow manifest filename matches directory name (folder name = identity). |
| **Manifest Loader** | The unified system that reads all manifest files, discovers them by directory convention, and distributes each YAML section to a typed parser. Single code path — callers filter results. |
| **ManifestSection Protocol** | A typed parser interface (`ManifestSection[T]`) that each section kind implements. Three built-in parsers: rules, checks, hints. Adding a new section type means adding a parser — the loader itself does not change. |
| **Workflow Engine** | Manages workflow state, phase transitions, check execution, and hint delivery. Separate from the loader. |

### The 2×2 Guidance Framing

All guidance maps onto two axes: **valence** (positive/negative) × **bypassability** (advisory/enforced).

| | Advisory (agent authority) | Enforced (user authority) |
|---|---|---|
| **Positive** (do this) | **Quadrant A:** Do's in markdown — phase instructions, best practices | **Quadrant C:** Checkpoints — engine verifies work is done |
| **Negative** (don't do this) | **Quadrant B:** Don'ts in markdown + `warn` (agent ack) + `log` | **Quadrant D:** Guardrails — `deny` (user override via one-time token) |

The boundary is **authority**: `warn` and `log` are advisory (Quadrant B) — the agent has authority to proceed. `deny` is enforced (Quadrant D) — requires user authority via the `request_override` MCP tool. Both `warn` and `deny` are **per-command scoped** — each invocation must be individually acknowledged/approved. All four quadrants evolve across phases.

- **Advisory** — guidance the agent may choose to bypass. Includes markdown instructions (Quadrant A), markdown don'ts, and rules with `warn` or `log` enforcement (Quadrant B). `warn` blocks the tool call but the agent can self-acknowledge by calling `acknowledge_warning` MCP tool (stores token, no TUI) then retrying (2 actions — agent authority).
- **Enforced** — guidance the agent cannot bypass without user approval. Includes advance checks / checkpoints (Quadrant C) and rules with `deny` enforcement (Quadrant D). The agent calls `request_override` MCP tool → user approves the specific command → agent retries (2 actions — escalation required).
- **Guidance** — umbrella term for all four quadrants.
- **Guardrail** — specifically enforced negative guidance (Quadrant D: `deny` only).

### Rules

| Term | Definition |
|------|-----------|
| **Rule** | A YAML-declared directive that fires when a tool call matches its trigger and detect pattern. Each rule has an `id`, `trigger`, `enforcement` level, optional `detect` pattern, and optional role/phase scoping. Enforcement level determines quadrant placement — `deny` is enforced (Quadrant D), `warn`/`log` are advisory (Quadrant B). |
| **Trigger** | The SDK hook event that activates a rule. Format: `PreToolUse/<ToolName>` (e.g. `PreToolUse/Bash`). Bare `PreToolUse` matches all tools. |
| **Enforcement Level** | How the system responds when a rule fires. Three levels: `warn` (block, agent ack via `acknowledge_warning` MCP, per-command, 2 actions), `deny` (block, user override via `request_override` MCP, per-command, 2 actions), `log` (silent record). Both `warn` and `deny` use the same one-time token mechanism. See table in §8. |
| **Detect Pattern** | A regex in a rule's `detect` block, matched against a specified `field` of the tool input (default: `command`). If absent, the rule fires on every matching trigger. |
| **Exclude Pattern** | A regex (`exclude_if_matches`) that, when matched, prevents the rule from firing — checked before the detect pattern. |
| **Role Scoping** | `roles` — rule fires *only* for these roles (include filter). `exclude_roles` — rule *never* fires for these roles (exclude filter). |
| **Phase Scoping** | `phases` — rule fires only during these phases (include filter). `exclude_phases` — rule *never* fires during these phases (exclude filter). Within the same manifest, bare phase names are used; the loader qualifies them at parse time. Cross-workflow references (e.g. in `global/*.yaml`) use fully qualified IDs. |
| **HitRecord / Hit** | A single rule match event recorded in the audit trail. Contains `rule_id`, `agent_role`, `tool_name`, `enforcement`, `timestamp`, and `outcome`. Written as JSONL to `.claude/hits.jsonl`. |

### Phases

| Term | Definition |
|------|-----------|
| **Phase** | A named period in a workflow's lifecycle (e.g. `vision`, `setup`, `specification`). Ordered. Each has an `id`, a `file` reference, optional `advance_checks`, and optional `hints`. |
| **Phase Transition** | Moving from current phase to next. Gated by `advance_checks` — all must pass (AND semantics, short-circuit on first failure). |
| **Phase State** | Runtime tracking of current phase. Held in-memory by the engine, persisted via `Chicsession.workflow_state` on each phase transition. On session resume, the engine restores state from the chicsession. |
| **Qualified Phase ID** | `<workflow_id>:<phase_id>` (e.g. `project-team:testing`). The runtime form used in `phases` and `exclude_phases` fields. In YAML, bare names are used within the same manifest (loader qualifies them); fully qualified names are required for cross-workflow references in `global/*.yaml`. |

### Checks

| Term | Definition |
|------|-----------|
| **Check** | A verification that tests system state and returns pass/fail with evidence. The engine runs checks — not the agent. Protocol is async. |
| **Advance Checks** | Checks under a phase's `advance_checks` key. Gate phase transitions. AND semantics, short-circuit on first failure. |
| **Setup Checks** | Checks in `global/checks.yaml` that verify environment prerequisites. Include `on_failure` with message, severity, lifecycle. Bridged to hints pipeline via CheckFailed adapter. |
| **`when` Clause** | Condition on checks that gates whether the check runs, based on copier-answer values (e.g. `when: { copier: use_cluster }`). Evaluation semantics: truthy (value is present and not false/empty). |
| **`on_failure`** | Block on checks specifying what happens on failure: `message` (human-readable), `severity` (`warning`), `lifecycle` (e.g. `show-until-resolved`). |

### Hints

| Term | Definition |
|------|-----------|
| **Hint** | Advisory content delivered to the user via TUI toast. Not visible to the agent. Declared in manifests under phase entries or globally. Engine converts declarations to `HintSpec` objects via `run_pipeline()`. |
| **HintSpec** | Internal object representing a hint after manifest parsing. Consumed by the existing hints pipeline. |
| **Hint Lifecycle** | Controls display behavior: `show-once` (displayed once, suppressed), `show-until-resolved` (repeated until condition passes). |
| **CheckFailed Adapter** | Bridges failing checks into the hints pipeline. When a check fails and has `on_failure` config, produces a `HintSpec` surfaced through `run_pipeline()`. |
| **Toast** | A TUI notification displayed briefly to the user. Used by the hints pipeline (`run_pipeline()`) to surface advisory hints and check failure messages. |
| **`run_pipeline()`** | The 6-stage hints evaluation pipeline: activation → trigger → lifecycle → sort → budget → present. Converts `HintSpec` objects into displayed toasts. |
| **AlwaysTrue** | A `TriggerCondition` implementation that always returns `True`. Used by the `CheckFailed` adapter — when a check has already failed, the resulting hint fires immediately without further evaluation. |

### Agent Folders

| Term | Definition |
|------|-----------|
| **Agent Folder** | A directory inside a workflow directory (e.g. `workflows/project_team/coordinator/`). The folder name IS the role type. |
| **Role Type** | Identity of an agent, derived from folder name (e.g. `coordinator`, `implementer`, `skeptic`). Used in `roles`/`exclude_roles` and captured in SDK hook closures at spawn time. |
| **Identity File** | `identity.md` inside an agent folder. Cross-phase — always loaded. |
| **Phase File** | Markdown file named after a phase (e.g. `specification.md`). Loaded only during that phase. Pure advisory content. |
| **Agent Prompt** | The assembled prompt: `identity.md` + current phase file. Pull-based — the agent calls the `get_phase` MCP tool to discover the current phase, then reads its own markdown files. |

### SDK Hooks

| Term | Definition |
|------|-----------|
| **SDK Hook** | A callback registered with the Claude Agent SDK that intercepts tool calls. claudechic is the required runtime. |
| **Hook Closure** | A function created per-agent that captures the role type at creation time. Rules are loaded fresh on every tool call (no mtime caching). |
| **Hook Evaluation Pipeline** | Two-step: Step 1 applies `inject` rules (modify tool input). Step 2 evaluates enforcement rules: match trigger → check role skip → check phase skip → check exclude → match detect → log hit → apply enforcement (`log`/`warn`/`deny`). |
| **PostCompact Hook** | SDK hook that fires after `/compact`. Re-injects phase context (identity + current phase file). |
| **SelectionPrompt** | Existing TUI widget for user confirmations. Used by `deny` rule override approval (via `request_override` MCP tool — user sees the exact command) and `ManualConfirm` checks. Engine receives a confirmation callback — not a direct app reference. |

### Namespacing

| Term | Definition |
|------|-----------|
| **Namespace** | Prefix applied to bare IDs at load time: `global:<id>` for items in `global/*.yaml`, `<workflow_id>:<id>` for workflow items. All IDs are namespaced at runtime. IDs in YAML are written bare — the loader prefixes automatically. |
| **Qualified ID** | The runtime form: `namespace:name`. Examples: `global:pip_block`, `project-team:close_agent`. |

### Workflow

| Term | Definition |
|------|-----------|
| **WorkflowManifest** | Parsed representation of a workflow's YAML manifest. Contains the `workflow_id`, phases list, and metadata. Passed to `WorkflowEngine` at construction. |
| **Workflow Command** | A slash command auto-discovered from a workflow directory at startup. Name derived from `workflow_id` (kebab-case). Activates the workflow when invoked. Only registered if manifest parses without errors. |
| **Active Workflow** | The currently activated workflow (at most one). Set by invoking a workflow command or restored from chicsession on session resume. Queried via `/workflow list`. |

### Naming Convention: Bare Noun vs `Decl`

If `ManifestSection[T]` produces an object that IS the runtime object (parsed = evaluated), `T` gets the bare noun: `Rule`, `Injection`, `Phase`. If it produces a YAML declaration that's later converted to a different runtime type, `T` gets the `Decl` suffix: `CheckDecl` → `_build_check()` → `Check` (executable protocol), `HintDecl` → adapter → `HintSpec` (pipeline input). This convention signals where a conversion step exists.

### Content Delivery

**Pull-based:** The engine does NOT inject content mid-session. Agents call the `get_phase` MCP tool to discover the current phase, then read their own markdown files. The only exception is `/compact` recovery via the PostCompact hook. All phase queries go through the in-memory engine via MCP tools.

### Workflow Status in TUI

When a workflow is active, the existing `ChicsessionLabel` widget in the right sidebar displays workflow info as nested sub-elements:

```
Chicsession
  my-project
  Workflow: project-team
  Phase: specification
```

- **No chicsession, no workflow:** shows "none" (existing behavior)
- **Chicsession active, no workflow:** shows session name only (existing behavior)
- **Chicsession + active workflow:** shows session name + workflow name + current phase
- Phase line updates on each `advance_phase` transition

The `ChicsessionLabel` widget gains two optional reactive properties: `workflow_text` and `phase_text`. Set by the engine's `persist_fn` callback (same trigger as chicsession auto-save). Cleared on workflow deactivation. No new widget — extends the existing one.

### Failure Modes

| Mode | When | Behavior |
|------|------|----------|
| **Fail Closed** | `global/` or `workflows/` unreadable | Block everything. |
| **Fail Open** | Individual manifest malformed or bad regex | Skip that manifest/item, load the rest. |
| **Startup Validation** | Manifest load time | Duplicate ID detection, invalid regex detection, unknown phase reference validation. Raw IDs containing `:` rejected. |

### Terminology Hygiene

1. **Rule vs Check** — Rules are reactive (fire on tool calls). Checks are proactive (engine evaluates state). Distinct mechanisms.
2. **Phase** exclusively — never "stage" or "step."
3. **Manifest** for YAML files in `global/` and `workflows/`. "Config" refers to `~/.claude/.claudechic.yaml`.
4. **Agent folder** — not "role directory."
5. **Rule** = precise mechanism term covering all three enforcement levels (`deny`, `warn`, `log`). **Guardrail** = colloquial shorthand for Quadrant D only (enforced negative: `deny`). **Guidance** = umbrella for all four quadrants. In prose, use "rule" when referring to the mechanism generally; reserve "guardrail" for specifically enforced negative rules. **Injection** is a separate tool-input modification mechanism declared in the `injections:` manifest section, not an enforcement level and not in the `rules:` section.
6. **Advisory** is a classification. **Hint** is a specific mechanism (`HintSpec`/`run_pipeline()`). Advisory markdown (Quadrant A) is not delivered as hints.
7. **Engine** manages state and transitions. **Loader** reads and parses manifests. Separate components.
8. **Workflow** = full package (directory + manifest + agent folders + state). **Workflow manifest** = the YAML file specifically.
9. **Identity** = cross-phase `identity.md`. **Agent prompt** = identity + phase file.
10. **`roles`/`exclude_roles`** restrict by role. **`phases`/`exclude_phases`** restrict by phase. Bare noun (`roles`, `phases`) = scope-to (include filter). `exclude_` prefix (`exclude_roles`, `exclude_phases`) = exempt (exclude filter).

---

## 3. Architecture — Composability Axes

The system has six independent axes. Any combination of axis values produces a working system.

### Axis 1: Section Type (ManifestSection[T])

The kind of guidance declared in a manifest — `rules`, `checks`, `hints`, `phases`. Each has its own parser, runtime semantics, and delivery mechanism. The loader dispatches YAML sections to typed parsers without knowing what a "rule" or "check" means.

**Compositional law:** `ManifestSection[T].parse(raw_list) -> list[T]`. The loader doesn't branch on section type — it dispatches uniformly. For global files, the section key is inferred from the filename; for workflow manifests, it comes from the YAML dict key.

**Seam:** Raw YAML list (output of `yaml.safe_load`) crosses the boundary. The loader doesn't interpret section contents. The parser doesn't know about other sections or about the file it came from.

### Axis 2: Check Type

How verification is performed. Four built-in types, extensible via the Check protocol.

**Compositional law:** `async Check.check() -> CheckResult(passed: bool, evidence: str)`. The engine doesn't know which type it's running. A new check type works everywhere checks are used — no engine changes.

**Seam:** `CheckResult` crosses the boundary. The engine sees pass/fail + evidence. The check doesn't know whether it's gating a phase or reporting at startup.

### Axis 3: Scope (Where guidance applies)

Filtering dimensions that compose with AND semantics:

| Filter | Values | Applies to |
|--------|--------|------------|
| **Namespace** | `global` \| `{workflow_id}` | All guidance types |
| **Phase** | `phases` / `exclude_phases` lists | Rules, hints |
| **Role** | `roles` / `exclude_roles` lists | Rules |
| **Conditional** | `when: { copier: key }` | Checks |

Each filter is `(context) -> bool`. Evaluation: `all(f(ctx) for f in applicable_filters)`. No filter inspects another filter's state.

**Phase references cross workflow boundaries:** `phases: ["project-team:testing"]` in `global/rules.yaml` creates a coupling to a specific workflow. Cross-workflow references must use fully qualified IDs (bare names are only auto-qualified within the same manifest). The loader's startup validation makes this coupling explicit and fails fast.

**Note on axes 4–6:** These axes are not freely composable across all section types — they describe dimensions of variation within their applicable domains (e.g., lifecycle applies to hints, enforcement applies to rules).

### Axis 4: Enforcement / Delivery Mechanism

How guidance reaches the agent or user:

| Mechanism | Used by | Channel |
|-----------|---------|---------|
| SDK hook (deny) | Rules | PreToolUse → block; agent calls `request_override` MCP → user approves specific command → one-time token → retry consumes token |
| SDK hook (warn) | Rules | PreToolUse → block; agent calls `acknowledge_warning` MCP → token stored (no TUI) → retry → token consumed → allowed |
| SDK hook (log) | Rules | PreToolUse → silent record, no block |
| SDK hook (inject) | Injections (`injections:` section) | PreToolUse → modifies tool input. Separate section and parser, not an enforcement level. |
| Toast hint | Hints, check failures | TUI toast notification via `run_pipeline()` |
| Phase prompt assembly | Agent folders, phases | Agent reads identity.md + phase.md |
| PostCompact hook | Phase context | Re-inject after `/compact` |

A rule's enforcement level is a field on the rule, not a property of its content or scope. The same pattern-matching rule could be `deny` or `warn` — just change the YAML field. `inject` is orthogonal to enforcement — it modifies tool input rather than blocking.

### Axis 5: Lifecycle (Temporal behavior)

How guidance persists over time: `show-once`, `show-until-resolved`, `show-every-session`, `cooldown(seconds)` (existing in hints system, reusable).

**Compositional law:** `HintLifecycle` protocol — `should_show(hint_id, state) -> bool` and `record_shown(hint_id, state)`. Any lifecycle implementation works with any hint.

### Axis 6: Content vs. Infrastructure

The foundational axis. Content = `global/` + `workflows/` directories (YAML + markdown). Infrastructure = claudechic code (loader, engine, checks, hooks, delivery).

**Compositional law:** Manifests follow a schema. Markdown files follow a naming convention (folder name = role, file name = phase). Infrastructure processes any content that follows these conventions.

**Seam:** The `global/` and `workflows/` directory boundaries. claudechic reads from them but never writes workflow-specific logic.

### 10-Point Crystal Spot Check

| # | Section Type | Check Type | Scope | Enforcement | Lifecycle | Works? |
|---|-------------|-----------|-------|-------------|-----------|--------|
| 1 | rule | N/A | global + phases | deny | N/A | ✅ existing guardrails |
| 2 | check | CommandOutput | global | toast (via adapter) | show-until-resolved | ✅ setup checks |
| 3 | check | ManualConfirm | workflow phase | toast (via adapter) | show-once | ✅ advance_checks |
| 4 | hint | N/A | workflow phase | toast | show-once | ✅ phase hints |
| 5 | rule | N/A | global + role filter | deny | N/A | ✅ role-scoped rules |
| 6 | check | FileExists | global | toast (via adapter) | show-until-resolved | ✅ setup check |
| 7 | rule | N/A | workflow + exclude_phases | deny | N/A | ✅ phase-scoped rule |
| 8 | check | FileContent | workflow phase advance | N/A | N/A | ✅ advance gate |
| 9 | hint | N/A | global | toast | cooldown | ✅ global hint |
| 10 | check | ManualConfirm | global setup | toast (via adapter) | show-until-resolved | ⚠️ edge case — works mechanically but unusual |

No crystal holes found.

### Compositional Law Summary

1. **ManifestSection[T] law** — All section parsers consume raw YAML dicts and produce typed objects.
2. **Check protocol law** — All checks implement `async check() -> CheckResult`.
3. **Content convention law** — All guidance is YAML + markdown following naming conventions (`global/` for global, `workflows/` for workflows). claudechic doesn't know workflow domain semantics.

These three laws guarantee: a new workflow with new check types and new section types can be added without modifying claudechic infrastructure code.

---

## 4. Directory Structure

### Project-Side Content

```
global/                              # Global guidance (always active, no phases)
  rules.yaml                        # Global rules (pip_block, etc.)
  checks.yaml                       # Setup checks (github_auth, cluster_ssh, etc.)
  hints.yaml                        # Global hints

workflows/                           # Workflow definitions
  project_team/
    project_team.yaml                # Manifest: rules, phases, checks, hints
    coordinator/                     # Agent folder — folder name = role type
      identity.md                    # Cross-phase identity (always loaded)
      vision.md                      # Phase-specific (loaded during vision phase)
      setup.md
      specification.md
      implementation.md
      testing.md
      signoff.md
    composability/
      identity.md
      specification.md
    skeptic/
      identity.md
      specification.md
    implementer/
      identity.md
      implementation.md
      testing.md
```

Global guidance is NOT a workflow — it lives in `global/` alongside `workflows/`, not inside it. All YAML files in `global/` share the `global` namespace and are always active. Multiple files let authors organize (rules separate from checks separate from hints) but they merge into one namespace.

Folder name = identity everywhere: manifest filename, rule ID namespace, agent folder name.

### claudechic Infrastructure

```
claudechic/
  workflows/                    # Orchestration layer — imports from guardrails/, checks/, hints/
    __init__.py                 # Public API: ManifestLoader, WorkflowEngine, etc.
    loader.py                   # ManifestSection[T] dispatcher, manifest discovery
    engine.py                   # Phase transitions, state persistence, advance_checks
    phases.py                   # Phase dataclass (bridge type — imports CheckDecl + HintDecl)
    agent_folders.py            # Prompt assembly from identity + phase files

  checks/                       # NEW top-level package — check protocol + built-ins
    __init__.py                 # Public API: Check, CheckResult, CheckDecl, register_check_type
    protocol.py                 # Check protocol, CheckResult, CheckDecl (leaf — stdlib only)
    builtins.py                 # 4 built-in types + registry (imports protocol)
    adapter.py                  # CheckFailed → HintSpec bridge (imports protocol + hints/types)

  guardrails/                   # EXISTING, refactored
    __init__.py                 # MODIFIED — add exports from hooks.py
    rules.py                    # MODIFIED — Rule + Injection; namespace field; load_rules() replaced
    hooks.py                    # NEW — hook closure creation (extracted from app.py)
    hits.py                     # NEW — HitRecord, HitLogger (append-only JSONL audit trail)
    tokens.py                   # NEW — OverrideToken, OverrideTokenStore (leaf — stdlib only)

  hints/                        # NEW claudechic package (absorbed from template-side)
    __init__.py                 # Public API: evaluate hints
    types.py                    # HintSpec, HintLifecycle, TriggerCondition, HintDecl
    engine.py                   # run_pipeline() — 6-stage evaluation pipeline
    state.py                    # ProjectState, CopierAnswers, HintStateStore, ActivationConfig
```

The axis structure is visible in folders:
- `workflows/` = orchestration layer (axes 1, 2, 6) — imports from the three leaf packages
- `checks/` = check protocol, built-in types, and CheckFailed adapter (axis 2)
- `guardrails/` = rule evaluation and enforcement delivery (axis 4 for rules — all enforcement levels)
- `hints/` = advisory delivery + lifecycle (axes 4, 5 for hints)
- Three leaf packages (`guardrails/`, `checks/`, `hints/`) — none import from `workflows/`
- `workflows/` is the orchestration layer importing from all three. No cycles.
- Scope filtering (axis 3) lives in loader as composable predicates

---

## 5. Manifest Loader

### ManifestSection[T] Protocol

```python
from __future__ import annotations

from typing import Any, Protocol, TypeVar

T_co = TypeVar("T_co", covariant=True)


class ManifestSection(Protocol[T_co]):
    """Protocol for typed manifest section parsers.

    Each section type (rules, checks, hints, phases) implements this.
    The loader dispatches raw YAML sections to the appropriate parser
    without knowing section semantics. Adding a new section type =
    implementing this protocol + registering the key.
    """

    @property
    def section_key(self) -> str:
        """YAML key this parser handles (e.g. 'rules', 'checks')."""
        ...

    def parse(
        self,
        raw: list[dict[str, Any]],
        *,
        namespace: str,
        source_path: str,
    ) -> list[T_co]:
        """Parse raw YAML section into typed objects.

        Args:
            raw: List of dicts from yaml.safe_load for this section key.
            namespace: 'global' for global/*.yaml, workflow_id for workflow manifests.
            source_path: Path to manifest file (error messages only).

        Returns:
            List of parsed typed objects. Items that fail validation are
            skipped (logged, not raised) — fail open per-item.

        Raises:
            Nothing. Individual failures logged and skipped.
        """
        ...
```

### T for Each Section Type

| Section Key | T (parsed type) | Description |
|-------------|-----------------|-------------|
| `rules` | `Rule` | Rule (dataclass in `guardrails/rules.py`, extended with required `namespace` field) |
| `injections` | `Injection` | Tool-input modification declaration (dataclass in `guardrails/rules.py`) |
| `checks` | `CheckDecl` | Check declaration — type + params (dataclass in `checks/protocol.py`), not the executable check itself |
| `hints` | `HintDecl` | Hint declaration — message + lifecycle + scope metadata (dataclass in `hints/types.py`) |
| `phases` | `Phase` | Phase definition — id, file reference, advance_checks, nested hints (dataclass in `workflows/phases.py`) |

### Parse Method Contract

**Parser validates (section-specific):**
- Required fields present (rules need `id`, `trigger`, `enforcement`)
- Field value types (`enforcement` is one of `deny|warn|log`)
- Regex compilation (detect patterns, check patterns)
- Raw IDs don't contain `:` (reserved for namespace)
- Section-specific semantics

**Parser does NOT validate (loader's responsibility):**
- Duplicate IDs across manifests (needs cross-manifest view)
- Phase reference validity (`phases`/`exclude_phases` targets exist)
- Cross-section references

**Namespace prefixing happens IN the parser.** The parser receives `namespace` and prefixes every `id` field. The parser knows item structure; the loader is generic.

### Data Types

```python
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class WorkflowData:
    """Per-workflow parsed data."""
    workflow_id: str
    path: Path
    manifest: WorkflowManifest
    has_errors: bool = False        # True if any parse error in this workflow

@dataclass(frozen=True)
class LoadResult:
    """Complete result of loading all manifests."""
    rules: list[Rule] = field(default_factory=list)           # All rules (global + all workflows)
    injections: list[Injection] = field(default_factory=list)
    checks: list[CheckDecl] = field(default_factory=list)
    hints: list[HintDecl] = field(default_factory=list)
    phases: list[Phase] = field(default_factory=list)
    errors: list[LoadError] = field(default_factory=list)
    workflows: dict[str, WorkflowData] = field(default_factory=dict)  # Per-workflow data, keyed by workflow_id

    def get_workflow(self, wf_id: str) -> WorkflowData | None:
        """Look up per-workflow data by workflow_id."""
        return self.workflows.get(wf_id)


@dataclass(frozen=True)
class LoadError:
    """A non-fatal error encountered during loading."""
    source: str           # file path or "discovery" or "validation"
    message: str
    section: str | None = None
    item_id: str | None = None
```

### Manifest Discovery Algorithm

```python
def discover_manifests(global_dir: Path, workflows_dir: Path) -> list[Path]:
    """Discover all manifest files in global/ and workflows/.

    Returns paths in load order:
    1. global/*.yaml (all YAML files, sorted alphabetically)
    2. workflows/*/workflow_name.yaml (sorted alphabetically)

    Global: all .yaml files in global/ directory.
    Workflow: manifest filename must match parent directory name.
    Example: workflows/project_team/project_team.yaml ✓
             workflows/project_team/other.yaml ✗ (ignored)
    Hidden directories (.name) and hidden files skipped.
    No recursive scanning — exactly one level deep.
    """
    manifests: list[Path] = []

    # 1. Global manifests — all .yaml files in global/
    if global_dir.is_dir():
        for child in sorted(global_dir.iterdir()):
            if child.is_file() and child.suffix == ".yaml" and not child.name.startswith("."):
                manifests.append(child)

    # 2. Workflow manifests — workflows/*/name.yaml
    if workflows_dir.is_dir():
        for child in sorted(workflows_dir.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                manifest = child / f"{child.name}.yaml"
                if manifest.is_file():
                    manifests.append(manifest)

    return manifests
```

**Key decisions:**
- Alphabetical sort for deterministic load order across NFS nodes
- Global loads first so startup validation can report conflicts
- All `.yaml` files in `global/` are discovered (authors organize freely: `rules.yaml`, `checks.yaml`, `hints.yaml`, etc.)
- All global files share the `global` namespace

### Loader — Single Code Path

There is NO separate rules-only mode. The loader always loads all manifests and parses all sections. Callers filter:

```python
# Hot path (every tool call) — same loader, just use .rules
result = loader.load()
active_rules = result.rules

# Full load (startup, phase transitions) — use everything
result = loader.load()
all_checks = result.checks
all_phases = result.phases
```

**Why:** Two code paths means two places for bugs, two places to update, and a subtle coupling. One path, filter at the call site. Profile before optimizing.

### ManifestLoader Implementation

```python
class ManifestLoader:
    """Unified manifest loader — single code path, callers filter."""

    def __init__(self, global_dir: Path, workflows_dir: Path) -> None:
        self._global_dir = global_dir
        self._workflows_dir = workflows_dir
        self._parsers: dict[str, ManifestSection] = {}

    def register(self, parser: ManifestSection) -> None:
        self._parsers[parser.section_key] = parser

    def load(self) -> LoadResult:
        """Load all manifests and return unified result.

        Error handling:
        - global/ or workflows/ unreadable → fail closed (empty rules + fatal error;
          callers treat this as "block everything")
        - Individual manifest malformed → fail open (skip, log error)
        - Individual item malformed → fail open (skip, log error)
        """
        errors: list[LoadError] = []

        # Step 1: Discover
        try:
            paths = self._discover()
        except OSError as e:
            return LoadResult(errors=[
                LoadError(source="discovery", message=f"Cannot read global/ or workflows/: {e}")
            ])

        # Step 2: Parse each manifest through all registered parsers
        collected: dict[str, list] = {k: [] for k in self._parsers}
        for path in paths:
            namespace = self._namespace_for(path)
            try:
                with path.open() as f:
                    data = yaml.safe_load(f)
            except (OSError, yaml.YAMLError) as e:
                errors.append(LoadError(source=str(path), message=str(e)))
                continue

            # Determine namespace: global/ files get "global", workflow files get workflow_id
            if self._is_global_path(path):
                namespace = "global"
            else:
                if not isinstance(data, dict):
                    errors.append(LoadError(source=str(path), message="not a YAML mapping"))
                    continue
                wf_id = data.get("workflow_id")
                if wf_id:
                    namespace = str(wf_id)

            # Global files: bare list → infer section key from filename stem
            # e.g. global/rules.yaml (top-level list) → section_key "rules"
            if isinstance(data, list) and self._is_global_path(path):
                key = path.stem  # "rules", "checks", "hints", "injections"
                parser = self._parsers.get(key)
                if parser is None:
                    errors.append(LoadError(
                        source=str(path),
                        message=f"No parser registered for '{key}' (inferred from filename)",
                    ))
                else:
                    parsed = parser.parse(data, namespace=namespace, source_path=str(path))
                    collected[key].extend(parsed)
                continue

            if not isinstance(data, dict):
                errors.append(LoadError(source=str(path), message="not a YAML mapping"))
                continue

            # Dict-based files: dispatch by section keys (workflow manifests, or
            # global files that use section keys — both supported)
            for key, parser in self._parsers.items():
                section = data.get(key)
                if section is None:
                    continue
                if not isinstance(section, list):
                    errors.append(LoadError(
                        source=str(path), section=key,
                        message=f"'{key}' must be a list",
                    ))
                    continue
                parsed = parser.parse(section, namespace=namespace, source_path=str(path))
                collected[key].extend(parsed)

        # Step 2b: Extract phase-nested hints (after all manifests parsed)
        # Known loader↔PhasesParser coupling: phase-nested hints are post-processed here.
        for phase in collected.get("phases", []):
            if hasattr(phase, "hints") and phase.hints:
                collected.setdefault("hints", []).extend(phase.hints)

        # Step 3: Cross-manifest validation
        errors.extend(self._validate(collected))

        return LoadResult(
            rules=collected.get("rules", []),
            injections=collected.get("injections", []),
            checks=collected.get("checks", []),
            hints=collected.get("hints", []),
            phases=collected.get("phases", []),
            errors=errors,
        )
```

### Namespace Prefixing

```
YAML:           id: pip_block      (in global/rules.yaml)
After parse:    id: global:pip_block

YAML:           id: github_auth    (in global/checks.yaml)
After parse:    id: global:github_auth

YAML:           id: close_agent    (in project_team.yaml, workflow_id: project-team)
After parse:    id: project-team:close_agent

YAML:           id: testing        (phase in project_team.yaml)
After parse:    id: project-team:testing
```

**Phase reference qualification:** Phase references within the same manifest use bare names (e.g. `phases: [testing]`). The loader qualifies them with the workflow namespace at parse time, producing `project-team:testing`. Cross-workflow references in `global/rules.yaml` must use fully qualified names (e.g. `phases: ["project-team:testing"]`). The loader validates all qualified phase references against known phase IDs after all manifests are loaded.

### Cross-Manifest Validation

```python
def _validate(self, collected: dict[str, list]) -> list[LoadError]:
    errors: list[LoadError] = []

    # 1. Duplicate ID detection (after namespace prefixing)
    seen: dict[str, str] = {}
    for key, items in collected.items():
        for item in items:
            iid = getattr(item, "id", None)
            if iid is None:
                continue
            if iid in seen:
                errors.append(LoadError(
                    source="validation", section=key, item_id=iid,
                    message=f"duplicate ID (first in {seen[iid]})",
                ))
            else:
                seen[iid] = key

    # 2. Phase reference validation
    known_phases = {p.id for p in collected.get("phases", [])}
    for rule in collected.get("rules", []):
        for ref in getattr(rule, "phases", []):
            if ref not in known_phases:
                errors.append(LoadError(
                    source="validation", section="rules", item_id=rule.id,
                    message=f"unknown phase ref '{ref}' in phases",
                ))
        for ref in getattr(rule, "exclude_phases", []):
            if ref not in known_phases:
                errors.append(LoadError(
                    source="validation", section="rules", item_id=rule.id,
                    message=f"unknown phase ref '{ref}' in exclude_phases",
                ))

    return errors
```

### Manifest Reload Semantics

**When does the loader run?**

| Consumer | When it calls `loader.load()` | Mid-session edits? |
|----------|-------------------------------|---------------------|
| **Rules/Injections** (hook closure) | Every tool call — fresh load, no cache | ✅ Immediate — next tool call sees changes |
| **Advance checks** (engine) | Each `attempt_phase_advance()` call | ✅ Next advance attempt sees changes |
| **Global setup checks** (engine) | Once at startup | ❌ Requires restart or `/workflow reload` |
| **Workflow setup checks** (engine) | On workflow activation (`/{workflow-id}`) | ✅ Re-run on next activation |
| **All manifests** (startup + `/workflow reload`) | Startup and on `/workflow reload` | ✅ `/workflow reload` re-parses everything |
| **Phase definitions** (engine) | Once at engine init | ❌ Requires session restart — engine holds `self._manifest` |
| **Hints** (engine) | On phase transitions and startup | ⚠️ Phase-scoped hints refresh on transition; global hints at startup only |

**Design rationale:** Rules are the hot path (every tool call) and must be live-reloadable — a user fixing a bad regex or adding a new rule should see the effect immediately. Phase structure and setup checks are session-level concerns — changing them mid-session would invalidate engine state (e.g., current phase might no longer exist). Restart is the right answer.

### NFS Performance Strategy

Rules are loaded fresh on every tool call. No mtime caching. See [APPENDIX.md](APPENDIX.md) for NFS cost analysis and optimization strategies.

### Error Strategy Matrix

| Failure | Behavior | Rationale |
|---------|----------|-----------|
| `global/` or `workflows/` unreadable | **Fail closed** — empty rules + fatal error. Callers block everything. | Can't evaluate rules we can't read. |
| Individual manifest YAML parse error | **Fail open** — skip manifest, load rest. Log prominent warning. | One bad manifest shouldn't disable all rules. |
| Individual item bad regex | **Fail open** — skip item, parse rest. Log warning. | One bad rule shouldn't disable siblings. |
| Duplicate ID (after prefixing) | **Warn** — log, keep first occurrence. | First-wins is predictable. |
| Invalid phase reference | **Warn** — log. Rule loads but phase filter vacuously false. | Could be a typo or future phase. |
| Raw ID contains `:` | **Fail open** — skip item, log error. | Reserved for namespace qualification. |

### Fail-Closed Detection at Call Site

```python
# In the SDK hook closure (hot path):
result = loader.load()

if result.errors and not result.rules:
    fatal = any(e.source == "discovery" for e in result.errors)
    if fatal:
        return {"decision": "block", "message": "Rules unavailable — global/ or workflows/ unreadable"}
```

### Hint Scoping Model

```
Scope Level          Source Location                    Active When
─────────────        ───────────────                    ───────────
Global               global/hints.yaml → hints:          Always
Workflow-wide        workflow.yaml → hints:              Whenever workflow is active
Phase-scoped         workflow.yaml → phases[].hints:     Only during that phase
```

Phase-nested hints are extracted by the `PhasesParser` into `Phase.hints` field, then flattened by the loader into the main hints list with phase scope metadata attached.

---

## 6. Checks

### Check Protocol

```python
# claudechic/checks/protocol.py

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CheckResult:
    """Outcome of a check. Crosses the Check↔Engine seam."""
    passed: bool
    evidence: str


AsyncConfirmCallback = Callable[[str], Awaitable[bool]]
"""The seam between ManualConfirm and TUI.
ManualConfirm calls: await callback(question) -> bool
The engine creates the callback, closing over app._show_prompt.
ManualConfirm never imports anything from claudechic.widgets or app.
"""


@runtime_checkable
class Check(Protocol):
    """Async protocol for all verification checks.

    Compositional law: every check type implements this.
    The engine calls check() without knowing the implementation.
    """
    async def check(self) -> CheckResult: ...
```

**Design decisions:**
- `CheckResult` is frozen dataclass — type safety at the seam
- `Check` is Protocol (duck typing), not ABC — no inheritance required
- `@runtime_checkable` enables `isinstance(obj, Check)` for validation
- `evidence` is always string — engine decides how to use it

### Four Built-in Check Types

#### CommandOutputCheck

```python
class CommandOutputCheck:
    """Passes when command stdout matches regex."""

    def __init__(self, command: str, pattern: str) -> None:
        self.command = command
        self.compiled_pattern = re.compile(pattern)

    async def check(self) -> CheckResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                self.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            stdout = stdout_bytes.decode("utf-8", errors="replace")

            match = self.compiled_pattern.search(stdout)
            if match:
                return CheckResult(passed=True, evidence=f"Pattern matched: {match.group(0)[:200]}")
            excerpt = "\n".join(stdout.strip().splitlines()[:3])
            return CheckResult(
                passed=False,
                evidence=f"Pattern '{self.compiled_pattern.pattern}' not found in output: {excerpt}"[:300],
            )
        except asyncio.TimeoutError:
            return CheckResult(passed=False, evidence=f"Command timed out after 30s: {self.command}")
        except OSError as e:
            return CheckResult(passed=False, evidence=f"Command failed: {e}")
```

#### FileExistsCheck

```python
class FileExistsCheck:
    """Passes when file exists."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def check(self) -> CheckResult:
        if self.path.exists():
            return CheckResult(passed=True, evidence=f"File found: {self.path}")
        return CheckResult(passed=False, evidence=f"File not found: {self.path}")
```

#### FileContentCheck

```python
class FileContentCheck:
    """Passes when file content matches regex."""

    def __init__(self, path: str | Path, pattern: str) -> None:
        self.path = Path(path)
        self.compiled_pattern = re.compile(pattern)

    async def check(self) -> CheckResult:
        if not self.path.exists():
            return CheckResult(passed=False, evidence=f"File not found: {self.path}")
        try:
            content = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return CheckResult(passed=False, evidence=f"Cannot read {self.path}: {e}")

        for i, line in enumerate(content.splitlines(), 1):
            if self.compiled_pattern.search(line):
                return CheckResult(passed=True, evidence=f"Line {i}: {line.strip()}"[:200])

        return CheckResult(
            passed=False,
            evidence=f"Pattern '{self.compiled_pattern.pattern}' not found in {self.path}",
        )
```

#### ManualConfirm (Critical TUI Seam)

```python
class ManualConfirm:
    """Passes when user confirms via injected callback.

    The ONLY check type requiring user interaction. Receives an
    AsyncConfirmCallback at construction — never sees the TUI.
    """

    def __init__(self, question: str, confirm_fn: AsyncConfirmCallback) -> None:
        self.question = question
        self.confirm_fn = confirm_fn

    async def check(self) -> CheckResult:
        try:
            confirmed = await self.confirm_fn(self.question)
            if confirmed:
                return CheckResult(passed=True, evidence="User confirmed")
            return CheckResult(passed=False, evidence="User declined")
        except Exception as e:
            return CheckResult(passed=False, evidence=f"Confirmation failed: {e}")
```

### ManualConfirm ↔ TUI Seam

The engine creates a callback that closes over the app's TUI methods. ManualConfirm receives this callback at construction. The callback is the seam.

**Information flow:**
```
ManifestYAML → Engine (creates callback) → ManualConfirm(question, callback)
                  ↓
             callback closes over app._show_prompt + SelectionPrompt
                  ↓
ManualConfirm.check() → await self.confirm_fn(question) → callback → TUI prompt
```

**Callback creation in app.py** (the engine receives the callback — it never knows about the TUI):
```python
# In app.py — confirm callback factory (passed to WorkflowEngine at construction)

def _make_confirm_callback(self) -> AsyncConfirmCallback:
    """THE seam between checks and TUI. Created in app.py, injected into engine."""
    app = self

    async def confirm(question: str) -> bool:
        from claudechic.widgets.prompts import SelectionPrompt

        options = [("yes", "Yes — confirm"), ("no", "No — decline")]
        prompt = SelectionPrompt(f"✅ Check: {question}", options)
        async with app._show_prompt(prompt):
            result = await prompt.wait()
        return result == "yes"

    return confirm

# Passed to engine at construction (see §7):
# WorkflowEngine(manifest, persist_fn=..., confirm_callback=self._make_confirm_callback())
```

The engine stores the callback as `self._confirm_callback` and passes it to `ManualConfirm` checks. The engine's only constructor is the callback-based one defined in §7.

**Seam cleanliness — the swap test:**
- CLI mode: `async def confirm(q): return input(q) == "y"` → works
- Test mode: `async def confirm(q): return True` → works
- Web UI: WebSocket-based callback → works

ManualConfirm is truly UI-agnostic.

| Concern | Who handles it? |
|---------|----------------|
| What question to ask | ManualConfirm (from YAML) |
| How to display it | The callback (closes over SelectionPrompt) |
| How to get input | The callback (closes over `_show_prompt`) |
| What the answer means | ManualConfirm (maps to CheckResult) |

### Check Construction in Engine

```python
# Registry pattern — extensible without modifying _build_check()
_CHECK_REGISTRY: dict[str, Callable[[dict], Check]] = {}

def register_check_type(name: str, factory: Callable[[dict], Check]) -> None:
    _CHECK_REGISTRY[name] = factory

def _build_check(self, check_spec: CheckDecl) -> Check:
    """Map CheckDecl to Check objects via registry."""
    factory = _CHECK_REGISTRY.get(check_spec.type)
    if factory is None:
        raise ValueError(f"Unknown check type: {check_spec.type}")
    return factory(check_spec.params)

# Register 4 built-in types at module level:
register_check_type("command-output-check",
    lambda p: CommandOutputCheck(command=p["command"], pattern=p["pattern"]))
register_check_type("file-exists-check",
    lambda p: FileExistsCheck(path=p["path"]))
register_check_type("file-content-check",
    lambda p: FileContentCheck(path=p["path"], pattern=p["pattern"]))
register_check_type("manual-confirm",
    lambda p: ManualConfirm(question=p["question"], confirm_fn=p["confirm_fn"]))
```

**Note:** For `manual-confirm`, the engine injects `confirm_fn` into the params dict before calling `_build_check()`:
```python
if spec.type == "manual-confirm":
    spec = dataclasses.replace(spec, params={**spec.params, "confirm_fn": self._confirm_callback})
```

### CheckFailed → Hints Adapter

Bridges failing checks into the hints pipeline. One-directional: checks produce results, adapter converts failures to hints. The check doesn't know about hints. The hints pipeline doesn't know about checks.

```python
@dataclass(frozen=True)
class OnFailureConfig:
    """Parsed on_failure configuration from manifest YAML."""
    message: str
    severity: str = "warning"
    lifecycle: str = "show-until-resolved"


def check_failed_to_hint(
    check_result: CheckResult,
    on_failure: OnFailureConfig,
    check_id: str,
) -> dict | None:
    """Adapter: convert failed CheckResult to hint data.

    Returns None if check passed. Engine feeds result into
    hints pipeline via run_pipeline().
    """
    if check_result.passed:
        return None

    message = on_failure.message
    if check_result.evidence:
        message = f"{on_failure.message}\n  Evidence: {check_result.evidence}"

    return {
        "id": f"check-failed:{check_id}",
        "message": message,
        "severity": on_failure.severity,
        "lifecycle": on_failure.lifecycle,
        "trigger": "always",  # Already failed — fire immediately
    }
```

The adapter uses an `AlwaysTrue` trigger condition — the check already failed, no further evaluation needed.

### Setup Checks vs. Advance Checks

| Aspect | Setup Checks | Advance Checks |
|--------|-------------|----------------|
| Location | `global/checks.yaml` | Phase `advance_checks:` list |
| Short-circuit | No — run all, surface all issues | Yes — stop on first failure |
| Gating | Informational only (hints) | Blocks phase transition |
| Default lifecycle | `show-until-resolved` | `show-once` |
| When they run | Startup, phase transitions (re-eval) | Phase advance attempts only |

---

## 7. Workflow Engine

### Phase Transition Flow

```python
class WorkflowEngine:
    async def attempt_phase_advance(
        self,
        workflow_id: str,
        current_phase: str,
        next_phase: str,
        advance_checks: list[CheckDecl],
    ) -> bool:
        """AND semantics, sequential, short-circuit on first failure."""
        for i, spec in enumerate(advance_checks):
            check_id = f"{workflow_id}:{current_phase}:advance:{i}"
            check_instance = self._build_check(spec)
            result = await check_instance.check()

            if not result.passed:
                # Fire hint if on_failure configured
                if spec.on_failure:
                    on_failure = OnFailureConfig(
                        message=spec.on_failure["message"],
                        severity=spec.on_failure.get("severity", "warning"),
                        lifecycle=spec.on_failure.get("lifecycle", "show-once"),
                    )
                    hint_data = check_failed_to_hint(result, on_failure, check_id)
                    if hint_data:
                        from claudechic.hints.engine import run_pipeline
                        await run_pipeline([hint_data], self._hint_state)
                return False  # Phase transition blocked

        # All passed — update in-memory state + persist via chicsession
        self._current_phase = f"{workflow_id}:{next_phase}"
        if self._persist_fn:
            self._persist_fn()
        return True
```

**Why sequential, not parallel:**
- ManualConfirm shows TUI prompts — two simultaneous prompts confuse the user
- CommandOutputCheck shell commands could interfere with each other
- Short-circuit requires knowing result of check N before running N+1
- Performance cost negligible — phase transitions are rare

### In-Memory Phase State

**Key principle:** Phase state is held in-memory by the engine and persisted via `Chicsession.workflow_state`. All phase queries go through the in-memory engine. No separate state file.

```python
def get_current_phase(self) -> str | None:
    """In-memory lookup. No I/O."""
    return self._current_phase
```

### Chicsession Persistence

Phase state is persisted as an opaque `dict` on the `Chicsession` dataclass. The session system handles serialization and storage — the engine doesn't know how persistence works, only that it has a callback.

**Chicsession dataclass modification** (in `chicsessions.py`):
```python
@dataclass
class Chicsession:
    # ... existing fields ...
    workflow_state: dict | None = None  # Opaque to session system, owned by engine

    def to_dict(self) -> dict:
        d = {"name": self.name, "active_agent": self.active_agent, "agents": [...]}
        if self.workflow_state is not None:
            d["workflow_state"] = self.workflow_state
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Chicsession":
        return cls(..., workflow_state=data.get("workflow_state"))
```

**Engine interface:**
```python
class WorkflowEngine:
    def __init__(
        self,
        manifest: "WorkflowManifest",
        persist_fn: Callable[[], None] | None = None,
        confirm_callback: AsyncConfirmCallback | None = None,
    ) -> None:
        self._manifest = manifest
        self._workflow_id = manifest.workflow_id
        self._current_phase: str | None = None
        self._persist_fn = persist_fn
        self._confirm_callback = confirm_callback

    def get_current_phase(self) -> str | None:
        """In-memory lookup. No I/O."""
        return self._current_phase

    def to_session_state(self) -> dict:
        """Serialize engine state for chicsession persistence."""
        return {"workflow_id": self._workflow_id, "phase": self._current_phase}

    @classmethod
    def from_session_state(
        cls,
        state: dict | None,
        manifest: "WorkflowManifest",
        persist_fn: Callable[[], None] | None = None,
        confirm_callback: AsyncConfirmCallback | None = None,
    ) -> "WorkflowEngine":
        """Restore engine from chicsession state, or initialize to first phase."""
        engine = cls(manifest, persist_fn=persist_fn, confirm_callback=confirm_callback)
        if state:
            engine._current_phase = state.get("phase")
        else:
            engine._current_phase = manifest.phases[0].id if manifest.phases else None
        return engine
```

**App wiring** (in `app.py`):
```python
# persist_fn callback: update chicsession + save
def _make_persist_fn(self) -> Callable[[], None]:
    def persist():
        session = self._current_session
        if session and self._workflow_engine:
            session.workflow_state = self._workflow_engine.to_session_state()
            self._session_manager.save(session)
    return persist
```

**When a workflow is active, chicsession auto-save is implicitly enabled.** Workflows need agents, agents need session tracking. Phase state persistence is mandatory, not opt-in. The `persist_fn` fires on every phase transition (~6 writes per workflow run).

### Setup Check Execution

```python
async def run_setup_checks(self, check_specs: list[CheckDecl]) -> list[CheckResult]:
    """Run setup checks from global/checks.yaml at startup.

    Unlike advance_checks, setup checks do NOT short-circuit.
    All checks run, all failures produce hints. Goal: surface
    all environment issues at once.
    """
    checks: list[tuple[str, Check, OnFailureConfig | None]] = []
    for spec in check_specs:
        check_id = f"global:{spec['id']}"
        check_instance = self._build_check(spec)
        on_failure = None
        if "on_failure" in spec:
            on_failure = OnFailureConfig(
                message=spec["on_failure"]["message"],
                severity=spec["on_failure"].get("severity", "warning"),
                lifecycle=spec["on_failure"].get("lifecycle", "show-until-resolved"),
            )
        checks.append((check_id, check_instance, on_failure))

    return await self._run_checks_with_hints(checks)
```

### PostCompact Hook

The PostCompact hook is created **per-agent** alongside enforcement hooks, with the role captured in the closure at agent spawn time — same pattern as `create_guardrail_hooks()`. No runtime role lookup, no fallback.

```python
def create_post_compact_hook(
    engine: "WorkflowEngine",
    agent_role: str | None = None,
) -> dict[str, list[HookMatcher]]:
    """PostCompact hook: re-inject phase context after /compact.

    Created per-agent with role captured at spawn time.
    If no role, skip prompt assembly — don't guess.
    """

    async def reinject_phase_context(hook_input: dict, match: str | None, ctx: object) -> dict:
        current_phase = engine.get_current_phase()
        if not current_phase:
            return {}

        if not agent_role:
            return {}  # No role → no agent folder → nothing to inject

        prompt_content = assemble_phase_prompt(
            workflows_dir=engine.workflows_dir,
            workflow_id=engine.manifest.workflow_id,
            role_name=agent_role,
            current_phase=current_phase,
        )

        if prompt_content:
            return {"phase_context": prompt_content}
        return {}

    return {
        "PostCompact": [HookMatcher(matcher=None, hooks=[reinject_phase_context])],
    }
```

**Content re-injected:** identity.md + current phase file (the full agent prompt). This restores the agent's guidance context lost during compaction.

### Workflow Activation Model

Workflows are activated explicitly via auto-discovered slash commands — never auto-detected.

**Startup lifecycle:**
1. Parse ALL manifests (global + all workflows). Pay I/O cost once.
2. Surface parse errors as `show-until-resolved` hints via CheckFailed adapter — not app failures. Bad YAML, invalid regex, unknown phase references, duplicate IDs → user sees toast, app continues.
3. Register slash commands ONLY for workflows that parsed cleanly. Broken manifest = no command registered.
4. Run global setup checks (from `global/checks.yaml`).
5. If resuming a session with `chicsession.workflow_state`, auto-reactivate that workflow (honoring prior explicit intent).

**Slash commands:**

| Command | Action |
|---|---|
| `/{workflow-id}` | Activate this workflow. Created from parsed data (zero I/O). Creates engine, runs workflow setup checks, begins first phase. Only one workflow active at a time. |
| `/{workflow-id} stop` | Deactivate workflow. Destroys engine, clears `workflow_state` from chicsession. Returns to global-only mode. |
| `/workflow list` | Show all discovered workflows with status: valid/broken/active. |
| `/workflow reload` | Re-parse all manifests. Update command registrations (new valid → register, newly broken → deregister). Update error hints. Mid-session fix path — no restart needed. |

**Command naming:** derived from `workflow_id` field in manifest YAML (kebab-case). If `workflow_id` is absent, derive from folder name: `project_team` → `project-team`. Collision with built-in command names checked at registration — collision logs warning and skips registration.

**Discovery mechanism:**

```python
# At startup or /workflow reload:
def discover_and_register_workflows(
    global_dir: Path,
    workflows_dir: Path,
    loader: ManifestLoader,
) -> tuple[LoadResult, dict[str, Path]]:
    """Parse all manifests. Register valid workflow commands.

    Returns:
        - LoadResult with all parsed data (global + workflows)
        - Registry mapping workflow_id → directory path (valid only)
    """
    result = loader.load()  # Parse everything

    # Surface parse errors as hints (not failures)
    for error in result.errors:
        hint = parse_error_to_hint(error)  # → show-until-resolved toast
        # Queue hint for display

    # Build registry of valid workflows
    registry: dict[str, Path] = {}
    for wf_id, wf_data in result.workflows.items():
        if wf_data.has_errors:
            continue  # No command for broken workflows
        registry[wf_id] = wf_data.path
        register_slash_command(wf_id)  # /project-team

    return result, registry
```

**Activation (on `/{workflow-id}`):**

```python
def activate_workflow(wf_id: str, restored_state: dict | None = None):
    """Activate a workflow from already-parsed manifest data.

    Called by slash command or session resume. Zero I/O — data already parsed.
    """
    wf_data = self._load_result.get_workflow(wf_id)
    if wf_data is None:
        return "Unknown workflow. Run /workflow list."

    # Create engine from parsed data
    self._workflow_engine = WorkflowEngine.from_session_state(
        state=restored_state,
        manifest=wf_data.manifest,
        persist_fn=self._make_persist_fn(),
        confirm_callback=self._make_confirm_callback(),
    )

    # Run workflow-specific setup checks
    wf_checks = [c for c in self._load_result.checks if c.namespace == wf_id]
    if wf_checks:
        await self._workflow_engine.run_setup_checks(wf_checks)

    # Workflow rules now active — hook closure sees them on next tool call
```

**Session resume:**

```python
# On session resume:
session = load_chicsession(...)
if session.workflow_state:
    wf_id = session.workflow_state.get("workflow_id")
    if wf_id and wf_id in self._workflow_registry:
        activate_workflow(wf_id, restored_state=session.workflow_state)
```

**Before activation:** only global rules evaluate on tool calls. Workflow rules are parsed but dormant. The hook closure filters by active workflow:

```python
# In hook evaluation, before rule loop:
active_wf = engine.workflow_id if engine else None
for rule in result.rules:
    # Skip workflow-scoped rules if that workflow isn't active
    if rule.namespace != "global" and rule.namespace != active_wf:
        continue
    # ... rest of evaluation
```

**`/workflow reload`:**
Re-runs `discover_and_register_workflows()`. Updates `self._load_result` and `self._workflow_registry`. If the currently active workflow becomes broken, deactivates it and surfaces an error hint. New workflows get commands registered. Fixed workflows get commands re-registered.

### Engine Initialization

When the app starts, it creates the manifest loader, parses all manifests, registers workflow commands, and runs global setup checks:

```python
# In app.py on_mount() or _connect_initial_client():

# 1. Create shared loader, hit logger, and token store (created once at app init)
self._manifest_loader = ManifestLoader(self._global_dir, self._workflows_dir)
self._manifest_loader.register(RulesParser())
self._manifest_loader.register(InjectionsParser())
self._manifest_loader.register(ChecksParser())
self._manifest_loader.register(HintsParser())
self._manifest_loader.register(PhasesParser())

from claudechic.guardrails.hits import HitLogger
from claudechic.guardrails.tokens import OverrideTokenStore
self._hit_logger = HitLogger(self._claude_dir / "hits.jsonl")
self._token_store = OverrideTokenStore()  # Lives for app lifetime, independent of engine

# 2. Parse all manifests and register workflow commands
self._load_result, self._workflow_registry = discover_and_register_workflows(
    self._global_dir, self._workflows_dir, self._manifest_loader
)

# 3. Run global setup checks from global/checks.yaml
global_checks = [c for c in self._load_result.checks if c.namespace == "global"]
if global_checks:
    await run_global_setup_checks(global_checks)

# 4. Session resume — auto-reactivate workflow from prior session
session = self._current_session
if session and session.workflow_state:
    wf_id = session.workflow_state.get("workflow_id")
    if wf_id and wf_id in self._workflow_registry:
        activate_workflow(wf_id, restored_state=session.workflow_state)

# No workflow active yet — only global rules evaluate on tool calls.
# User activates via /{workflow-id} slash command.
```

**State initialization:** On activation or session resume, the engine restores from chicsession state or initializes to the first phase:

```python
# In app.py — engine initialization

# Fresh activation (via slash command):
engine = WorkflowEngine(
    manifest=manifest,
    persist_fn=self._make_persist_fn(),
    confirm_callback=self._make_confirm_callback(),
)
engine._current_phase = manifest.phases[0].id if manifest.phases else None

# Session resume (existing chicsession):
engine = WorkflowEngine.from_session_state(
    state=session.workflow_state,    # dict | None from chicsession
    manifest=manifest,
    persist_fn=self._make_persist_fn(),
    confirm_callback=self._make_confirm_callback(),
)
```

### `advance_phase` MCP Tool

Phase transitions are triggered by the coordinator agent via a dedicated MCP tool — a thin wrapper around the engine's `attempt_phase_advance()`:

```python
# In mcp.py — new MCP tool registration

async def advance_phase(args: dict[str, Any]) -> dict[str, Any]:
    """MCP tool: attempt to advance the active workflow to its next phase.

    The coordinator decides when to advance, then calls this tool.
    The engine runs advance_checks (AND semantics, short-circuit).
    Returns whether the transition succeeded and why.
    """
    engine = _app._workflow_engine
    if engine is None:
        return {"success": False, "reason": "No active workflow"}

    current = engine.get_current_phase()
    next_phase = engine.get_next_phase(current)
    if next_phase is None:
        return {"success": False, "reason": f"No phase after '{current}'"}

    # Engine runs advance_checks, updates in-memory state + persists via chicsession
    advanced = await engine.attempt_phase_advance(
        workflow_id=engine.workflow_id,
        current_phase=current,
        next_phase=next_phase,
        advance_checks=engine.get_advance_checks_for(current),
    )

    if advanced:
        return {"success": True, "phase": next_phase}
    else:
        return {"success": False, "reason": f"Advance checks failed for '{current}'"}
```

**Coordinator flow:**
1. Coordinator decides phase work is complete
2. Coordinator calls `advance_phase` MCP tool (no arguments needed — engine knows the current and next phase)
3. Engine runs `advance_checks` for the current phase (AND semantics, sequential, short-circuit)
4. If all pass → engine updates in-memory state + persists via chicsession → tool returns `{"success": true, "phase": "testing"}`
5. If any fail → CheckFailed adapter fires hints → tool returns `{"success": false, "reason": "..."}`
6. Coordinator communicates result to other agents via `tell_agent`

### `get_phase` MCP Tool

Agents query the current phase via MCP — in-memory engine lookup, no file I/O:

```python
# In mcp.py — new MCP tool registration

@server.tool()
async def get_phase(workflow_id: str | None = None) -> str:
    """Get current workflow phase.

    Agents call this at spawn time or when they need to know
    the current phase. Returns the qualified phase ID.
    In-memory lookup — no file I/O.
    """
    engine = _app._workflow_engine
    if engine is None:
        return "No active workflow."
    phase = engine.get_current_phase()
    return phase or "No phase set."
```

### `request_override` MCP Tool

Agents call this to request user approval for a specific `deny`-blocked action. The agent passes `rule_id`, `tool_name`, and `tool_input` (all from the block message). The user sees the exact command in a TUI SelectionPrompt. If approved, a **one-time override token** is stored — the agent must retry the exact same command to execute it. The token is consumed on use; the next invocation of the same command is blocked again.

**Per-command scoping:** Override tokens are keyed by `(rule_id, tool_name, hash(tool_input))`. This means the user approves a *specific action*, not a blanket rule suppression.

**Two-action flow:** The agent is blocked → calls `request_override(rule_id, tool_name, tool_input)` → user approves → agent retries the exact command → token consumed → allowed through. This is correct because `deny` requires user authority — the agent must escalate.

```python
# In mcp.py — new MCP tool registration

@server.tool()
async def request_override(rule_id: str, tool_name: str, tool_input: dict) -> str:
    """Request user approval to override a deny-level rule.
    User sees the exact command. If approved, stores a one-time token.

    Args:
        rule_id: The qualified ID of the blocking rule (from block message).
        tool_name: The tool that was blocked.
        tool_input: The exact tool input dict that was blocked.
    """
    approved = await app._show_override_prompt(
        rule_id,
        f"Agent wants to run blocked action:\n"
        f"  Tool: {tool_name}\n"
        f"  Input: {_format_tool_input(tool_input)}\n"
        f"  Blocked by: {rule_id}\n"
        f"Approve this specific action?"
    )

    if approved:
        app._token_store.store(rule_id, tool_name, tool_input)
        return f"Override approved for rule {rule_id}. Retry the exact same command."
    else:
        return f"Override denied."
```

### Override Token Store (`guardrails/tokens.py`)

Override tokens are an enforcement concern, not a workflow concern. The `OverrideTokenStore` is created at app init and lives for the app lifetime — independent of whether any workflow is active. This is critical because global `warn`/`deny` rules need the ack mechanism even before a workflow is activated.

Tokens are consumed on use — NOT persisted, NOT session-wide. Each token authorizes exactly one execution of one specific command.

```python
# claudechic/guardrails/tokens.py

import hashlib
import json
from dataclasses import dataclass

@dataclass(frozen=True)
class OverrideToken:
    """One-time authorization for a specific blocked action."""
    rule_id: str
    tool_name: str
    tool_input_hash: str


def _hash_tool_input(tool_input: dict) -> str:
    """Deterministic hash of tool input for token matching."""
    canonical = json.dumps(tool_input, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class OverrideTokenStore:
    """One-time override tokens for warn/deny enforcement.

    Lifecycle: created at app init, lives for app lifetime.
    Independent of workflow engine existence.
    """

    def __init__(self) -> None:
        self._tokens: list[OverrideToken] = []

    def store(self, rule_id: str, tool_name: str, tool_input: dict) -> None:
        """Store a one-time override token after acknowledgment or user approval."""
        self._tokens.append(OverrideToken(
            rule_id=rule_id,
            tool_name=tool_name,
            tool_input_hash=_hash_tool_input(tool_input),
        ))

    def consume(self, rule_id: str, tool_name: str, tool_input: dict) -> bool:
        """Consume a one-time override token if one matches. Returns True if consumed."""
        input_hash = _hash_tool_input(tool_input)
        for i, token in enumerate(self._tokens):
            if (token.rule_id == rule_id
                    and token.tool_name == tool_name
                    and token.tool_input_hash == input_hash):
                self._tokens.pop(i)
                return True
        return False
```

---

## 8. SDK Hooks and Enforcement

### Enforcement Levels

Three enforcement levels plus one separate mechanism:

| Level | Block? | Override | Who | Scoping | Actions | Mechanism |
|-------|--------|----------|-----|---------|---------|-----------|
| `warn` | Yes | One-time token | Agent (no TUI) | Per-command | 2 (acknowledge + retry) | `acknowledge_warning` MCP tool |
| `deny` | Yes | One-time token | User via TUI | Per-command | 2 (request + retry) | `request_override` MCP tool |
| `log` | No | — | — | — | — | Silent record |

**Separate mechanism (not an enforcement level):**

| Mechanism | Behavior |
|---|---|
| `inject` | Modifies tool input before execution. Declared in `injections:` manifest section (separate from `rules:`). Parsed by `InjectionsParser`. Processed BEFORE enforcement rules in the hook pipeline. Same trigger/detect/role/phase filtering. |

**Key design decisions:**
- **Per-command scoping** for both `warn` and `deny` — each invocation must be individually acknowledged/approved. No session-wide suppression.
- **Unified token mechanism** — both `warn` and `deny` use the same `OverrideToken(rule_id, tool_name, tool_input_hash)` and `OverrideTokenStore.consume()`. One in-memory `OverrideTokenStore` in `guardrails/tokens.py`, created at app init (independent of workflow engine).
- **`warn` = 2 actions** — agent calls `acknowledge_warning` MCP tool (stores token, no TUI prompt), then retries. Agent authority — no user involvement.
- **`deny` = 2 actions** — agent calls `request_override` MCP tool (TUI SelectionPrompt, user sees exact command), then retries. User authority — explicit escalation required.

### `warn` — Agent-Authority Acknowledgment (One-Time Token)

`warn` uses the same one-time token mechanism as `deny`, but without TUI prompts. The agent self-acknowledges by calling the `acknowledge_warning` MCP tool — no user interaction required.

```python
# In mcp.py — new MCP tool registration

@server.tool()
async def acknowledge_warning(rule_id: str, tool_name: str, tool_input: dict) -> str:
    """Acknowledge a warn-level rule to proceed past it.
    Stores a one-time token. Retry the exact same command to execute."""
    app._token_store.store(rule_id, tool_name, tool_input)
    return f"Warning acknowledged for rule {rule_id}. Retry the exact same command."
```

- **Agent flow**: blocked → message includes `acknowledge_warning` instructions → agent calls `acknowledge_warning(rule_id, tool_name, tool_input)` (token stored, NO TUI prompt) → agent retries exact same command → token consumed → allowed
- Works for ALL tool types (Bash, Write, etc.) — no tool-specific conventions needed
- **Per-command scoping**: each invocation must be individually acknowledged. Token is consumed on use.

### `deny` — User-Authority Override Token

See §7 for the `request_override` MCP tool and `guardrails/tokens.py` for the `OverrideTokenStore` implementation. Key properties:

- Token is keyed by `(rule_id, tool_name, hash(tool_input))` — approves a *specific action*, not a blanket rule suppression
- Token is **consumed on use** — next invocation of the same command is blocked again
- Tokens are **NOT persisted** — reset on session restart
- Uses the SAME `OverrideToken` and `OverrideTokenStore.consume()` as `warn` — unified mechanism
- **Agent flow**: blocked → calls `request_override(rule_id, tool_name, tool_input)` → user sees exact command in TUI → approves → agent retries exact same command → token consumed → allowed

### `inject` — Tool-Input Modification (Separate Section)

`inject` is NOT an enforcement level — it's a separate mechanism declared in the `injections:` manifest section. Processed BEFORE enforcement rules in the hook pipeline. Parsed by its own `InjectionsParser` (implements `ManifestSection[Injection]`).

**Injection dataclass:**
```python
@dataclass(frozen=True)
class Injection:
    id: str                    # Qualified: "project-team:force_tee"
    namespace: str
    trigger: list[str]         # Same trigger format as rules
    detect_pattern: re.Pattern[str] | None = None
    detect_field: str = "command"
    inject_value: str = ""     # What to inject (semantics depend on specific injection)
    roles: list[str] = field(default_factory=list)
    exclude_roles: list[str] = field(default_factory=list)
    phases: list[str] = field(default_factory=list)
    exclude_phases: list[str] = field(default_factory=list)
```

**Hook evaluation — Step 1:**
```python
# Step 1 of hook evaluation: apply injections (from `injections:` section)
for injection in result.injections:
    if not matches_trigger(injection, tool_name):
        continue
    if should_skip_for_role(injection, agent_role):
        continue
    if should_skip_for_phase(injection, current_phase):
        continue
    tool_input = apply_injection(injection, tool_input)

# Step 2: evaluate enforcement rules against the (possibly modified) input
```

**InjectionsParser** is registered alongside other parsers:
```python
self._manifest_loader.register(InjectionsParser())  # section_key = "injections"
```

### Hook Evaluation Pipeline

Two-step evaluation when a tool call arrives:

**Step 1 — Inject:** Process all `inject` rules (trigger → role → phase → detect filtering, then `apply_injection()`). Modifies tool input in place. No blocking.

**Step 2 — Enforcement:** For each non-inject rule:

0. **Filter namespace** — skip rules from inactive workflow namespaces. Only global rules and rules from the active workflow are evaluated. `rule.namespace != "global" and rule.namespace != active_wf` → skip.
1. **Match trigger** — `matches_trigger(rule, tool_name)`: splits `PreToolUse/Bash` on `/`, compares tool name. Bare `PreToolUse` matches all.
2. **Check role skip** — `should_skip_for_role(rule, agent_role)`: `roles` = only fires for listed roles; `exclude_roles` = never fires for listed roles.
3. **Check phase skip** — `should_skip_for_phase(rule, current_phase)`: evaluates `phases`/`exclude_phases` against current qualified phase ID.
4. **Check exclude pattern** — if `exclude_pattern` matches, skip this rule.
5. **Match detect pattern** — if `detect_pattern` is set and doesn't match, skip this rule.
6. **Log hit** — every rule match is recorded as a `HitRecord` regardless of enforcement level (see §8.1).
7. **Apply enforcement:**
   - `log` → allow (hit logged, no block, continue to next rule)
   - `warn` → check `consume_override(rule.id, tool_name, tool_input)`; if token consumed → allow (outcome: `ack`, continue); otherwise → block with `acknowledge_warning` instructions
   - `deny` → check `consume_override(rule.id, tool_name, tool_input)`; if token consumed → allow (outcome: `overridden`, continue); otherwise → block with `request_override` instructions

### Helper Functions

```python
def _get_field(tool_input: dict, field: str) -> str:
    """Extract a field from tool_input for pattern matching.
    Simple dict lookup, returns empty string for missing keys."""
    return str(tool_input.get(field, ""))


def apply_injection(injection: Injection, tool_input: dict) -> dict:
    """Apply an injection rule to tool_input, returning a modified copy.

    The injection's detect pattern identifies what to modify, and
    inject_value specifies what to inject. Exact injection semantics
    depend on the specific injection's configuration.

    Args:
        injection: An Injection with detect pattern and inject_value.
        tool_input: The current tool input dict.

    Returns:
        A modified copy of tool_input with the injection applied.
    """
    field = injection.detect_field
    current_value = _get_field(tool_input, field)
    if not current_value:
        return tool_input

    # Check detect pattern if present
    if injection.detect_pattern and not injection.detect_pattern.search(current_value):
        return tool_input

    # Apply injection — modify the target field
    modified = dict(tool_input)
    modified[field] = f"{current_value}\n{injection.inject_value}" if injection.inject_value else current_value
    return modified
```

### Rule-Evaluation Hook Closure

Extracted from `app.py` into `guardrails/hooks.py` (module name retained; the hooks evaluate all rules across all enforcement levels):

```python
# guardrails/hooks.py

from __future__ import annotations
import dataclasses
import time
from typing import Any, Callable
from claude_agent_sdk.types import HookMatcher
from claudechic.guardrails.hits import HitRecord, HitLogger

GetPhaseCallback = Callable[[], str | None]
GetActiveWfCallback = Callable[[], str | None]
OverrideTokenConsumer = Callable[[str, str, dict], bool]  # (rule_id, tool_name, tool_input) -> consumed


def create_guardrail_hooks(
    loader: "ManifestLoader",
    hit_logger: HitLogger,
    agent_role: str | None = None,
    get_phase: GetPhaseCallback | None = None,
    get_active_wf: GetActiveWfCallback | None = None,
    consume_override: OverrideTokenConsumer | None = None,
) -> dict[str, list[HookMatcher]]:
    """Create PreToolUse hooks that evaluate rules (all enforcement levels).

    Args:
        loader: Shared ManifestLoader instance (created once at app init,
                reused across all hook closures — parsers registered once).
        hit_logger: Shared HitLogger for audit trail.
        agent_role: Role type captured at agent creation time.
        get_phase: Callback returning current phase (in-memory engine lookup).
                   If None, phase filtering is skipped.
        get_active_wf: Callback returning the active workflow_id (in-memory).
                       If None, all workflow rules evaluate (no namespace filter).
        consume_override: Callback that checks and consumes a one-time override
                         token for a deny rule. Returns True if token was consumed.
                         If None, no overrides are possible.
    """

    async def evaluate(hook_input: dict, match: str | None, ctx: object) -> dict:
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input", {})

        # Load rules fresh every call (no mtime caching — NFS safe)
        result = loader.load()

        # Fail-closed check
        if result.errors and not result.rules:
            fatal = any(e.source == "discovery" for e in result.errors)
            if fatal:
                return {"decision": "block", "message": "Rules unavailable — global/ or workflows/ unreadable"}

        current_phase = get_phase() if get_phase else None
        active_wf = get_active_wf() if get_active_wf else None

        # Step 1: Apply injections (from `injections:` section)
        for injection in result.injections:
            if not matches_trigger(injection, tool_name):
                continue
            if should_skip_for_role(injection, agent_role):
                continue
            if should_skip_for_phase(injection, current_phase):
                continue
            tool_input = apply_injection(injection, tool_input)

        # Step 2: Evaluate enforcement rules
        for rule in result.rules:
            # Step 0: Skip rules from inactive workflows
            if rule.namespace != "global" and rule.namespace != active_wf:
                continue
            if not matches_trigger(rule, tool_name):
                continue
            if should_skip_for_role(rule, agent_role):
                continue
            if should_skip_for_phase(rule, current_phase):
                continue
            # Check exclude pattern
            if rule.exclude_pattern:
                field_value = _get_field(tool_input, rule.detect_field)
                if rule.exclude_pattern.search(field_value):
                    continue
            # Check detect pattern
            if rule.detect_pattern:
                field_value = _get_field(tool_input, rule.detect_field)
                if not rule.detect_pattern.search(field_value):
                    continue

            # Rule matches — log hit, then apply enforcement
            hit = HitRecord(
                rule_id=rule.id,
                agent_role=agent_role,
                tool_name=tool_name,
                enforcement=rule.enforcement,
                timestamp=time.time(),
            )

            if rule.enforcement == "log":
                hit_logger.record(dataclasses.replace(hit, outcome="allowed"))
                continue  # Log doesn't block — check next rule

            elif rule.enforcement == "warn":
                if consume_override and consume_override(rule.id, tool_name, tool_input):
                    hit_logger.record(dataclasses.replace(hit, outcome="ack"))
                    continue  # Token consumed — allow, check next rule
                else:
                    hit_logger.record(dataclasses.replace(hit, outcome="blocked"))
                    return {
                        "decision": "block",
                        "reason": (
                            f"{rule.message}\n"
                            f"To acknowledge: acknowledge_warning(rule_id=\"{rule.id}\", "
                            f"tool_name=\"{tool_name}\", tool_input={{...}})"
                        ),
                    }

            elif rule.enforcement == "deny":
                if consume_override and consume_override(rule.id, tool_name, tool_input):
                    hit_logger.record(dataclasses.replace(hit, outcome="overridden"))
                    continue  # Token consumed — allow, check next rule
                else:
                    hit_logger.record(dataclasses.replace(hit, outcome="blocked"))
                    return {
                        "decision": "block",
                        "reason": (
                            f"{rule.message}\n"
                            f"To request user override: request_override(rule_id=\"{rule.id}\", "
                            f"tool_name=\"{tool_name}\", tool_input={{...}})"
                        ),
                    }

        return {}  # No blocking rule matched — allow

    return {"PreToolUse": [HookMatcher(matcher=None, hooks=[evaluate])]}
```

### 8.1 Hit Logging

Every rule match — regardless of enforcement level — is logged as a `HitRecord`. This is the audit trail. Hit logging enables the hardening path: monitor hits at `warn` level, then promote to `deny` with confidence once the rule is validated.

**`HitRecord` dataclass:**

```python
# claudechic/guardrails/hits.py

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO


@dataclass(frozen=True)
class HitRecord:
    """A single rule hit — the audit unit."""
    rule_id: str           # Qualified: "project-team:pip_block"
    agent_role: str | None # Role of the agent that triggered the hit
    tool_name: str         # e.g. "Bash", "Write"
    enforcement: str       # "deny", "warn", "log"
    timestamp: float       # time.time()
    outcome: str = ""      # "blocked", "allowed", "ack", "overridden"

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "agent_role": self.agent_role,
            "tool_name": self.tool_name,
            "enforcement": self.enforcement,
            "timestamp": self.timestamp,
            "outcome": self.outcome,
        }
```

**`HitLogger` — append-only JSONL writer:**

```python
class HitLogger:
    """Append-only hit logger. Writes to JSONL file.

    Thread-safe for single-writer (the app process). Each line is
    a JSON object — one hit per line. File is opened in append mode
    and flushed after each write for crash safety.
    """

    def __init__(self, hits_path: Path) -> None:
        self._path = hits_path
        self._file: TextIO | None = None

    def record(self, hit: HitRecord) -> None:
        """Append a hit record to the log file."""
        if self._file is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self._path.open("a", encoding="utf-8")
        self._file.write(json.dumps(hit.to_dict()) + "\n")
        self._file.flush()

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
```

**Storage location:** `.claude/hits.jsonl` (in the project's `.claude/` metadata directory). The hit log is project-specific — different projects have different hit histories. Stored in `.claude/` so the audit trail persists even if `global/` or `workflows/` directories are reorganized.

**Hit logger lifecycle:**
- Created once at app init alongside the `ManifestLoader`
- Passed to `create_guardrail_hooks()` as a parameter
- Closed on app shutdown

**Hook closure signature (see §8 for full implementation):**

```python
def create_guardrail_hooks(
    loader: "ManifestLoader",
    hit_logger: HitLogger,
    agent_role: str | None = None,
    get_phase: GetPhaseCallback | None = None,
    consume_override: OverrideTokenConsumer | None = None,
) -> dict[str, list[HookMatcher]]:
```

**Hit outcomes by enforcement level:**

| Enforcement | Possible Outcomes | When |
|---|---|---|
| `log` | `allowed` | Always — log never blocks |
| `warn` | `blocked` | No acknowledgment token available |
| `warn` | `ack` | One-time acknowledgment token consumed (via `acknowledge_warning` MCP) |
| `deny` | `blocked` | No override token available |
| `deny` | `overridden` | One-time override token consumed (per-command, not session-wide) |

**Replaces:** The file-based system's `hits.jsonl` at `.claude/guardrails/hits.jsonl`. Same JSONL format, moved up to `.claude/hits.jsonl`, richer data (includes outcome, agent role, enforcement level).

### Integration in app.py

```python
def _merged_hooks(self, agent_type: str | None = None) -> dict[HookEvent, list[HookMatcher]]:
    hooks = self._plan_mode_hooks()

    # Rule-evaluation hooks (extracted to guardrails/hooks.py)
    from claudechic.guardrails.hooks import create_guardrail_hooks
    rule_hooks = create_guardrail_hooks(
        loader=self._manifest_loader,   # Shared instance, created at app init
        hit_logger=self._hit_logger,    # Shared instance, created at app init
        agent_role=agent_type,
        get_phase=(self._workflow_engine.get_current_phase
                   if self._workflow_engine else None),
        get_active_wf=(lambda: self._workflow_engine.workflow_id
                       if self._workflow_engine else None),
        consume_override=self._token_store.consume,  # App-level, always available
    )
    for event, matchers in rule_hooks.items():
        hooks.setdefault(event, []).extend(matchers)

    # PostCompact hook
    if self._workflow_engine:
        compact_hooks = self._workflow_engine.get_post_compact_hook()
        for event, matchers in compact_hooks.items():
            hooks.setdefault(event, []).extend(matchers)

    return hooks
```

### Failure Modes

- `global/` or `workflows/` unreadable → fail closed (block everything)
- Individual manifest malformed or bad regex → fail open (skip it, load the rest)
- Startup validation catches duplicate IDs, invalid regexes, unknown phase references

---

## 9. Agent Folders

### Prompt Assembly

```python
# claudechic/workflows/agent_folders.py

def assemble_agent_prompt(
    workflow_dir: Path,
    role_name: str,
    current_phase: str | None,
) -> str:
    """Read identity.md + phase.md, return concatenated content.

    Args:
        workflow_dir: e.g. workflows/project_team/
        role_name: folder name, e.g. "coordinator"
        current_phase: e.g. "specification" → reads specification.md
    """
    role_dir = workflow_dir / role_name

    identity_path = role_dir / "identity.md"
    identity = identity_path.read_text() if identity_path.is_file() else ""

    phase_content = ""
    if current_phase:
        phase_path = role_dir / f"{current_phase}.md"
        if phase_path.is_file():
            phase_content = phase_path.read_text()

    if phase_content:
        return f"{identity}\n\n---\n\n{phase_content}"
    return identity


def _find_workflow_dir(workflows_dir: Path, workflow_id: str) -> Path | None:
    """Find the workflow directory for a given workflow_id.

    Scans subdirectories of workflows_dir and matches on the
    workflow_id field in their YAML manifest. This handles the
    case where workflow_id is kebab-case but the directory is
    snake_case (e.g. workflow_id='project-team', dir='project_team').

    Returns the directory Path, or None if not found.
    """
    if not workflows_dir.is_dir():
        return None
    for child in sorted(workflows_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        manifest = child / f"{child.name}.yaml"
        if not manifest.is_file():
            continue
        try:
            import yaml
            with manifest.open() as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict) and data.get("workflow_id") == workflow_id:
                return child
        except (OSError, Exception):
            continue
    return None


def assemble_phase_prompt(
    workflows_dir: Path,
    workflow_id: str,
    role_name: str,
    current_phase: str | None,
) -> str | None:
    """Get full system prompt content for an agent.

    Called at agent spawn time and by PostCompact hook.
    Returns None if no agent folder exists.
    """
    # Map workflow_id to directory name
    # (workflow_id is kebab-case, directory may be snake_case)
    workflow_dir = _find_workflow_dir(workflows_dir, workflow_id)
    if workflow_dir is None:
        return None
    return assemble_agent_prompt(workflow_dir, role_name, current_phase) or None
```

### Spawn-Time Integration

```python
# In mcp.py spawn_agent, after agent creation:
from claudechic.workflows.agent_folders import assemble_phase_prompt

folder_prompt = assemble_phase_prompt(
    workflows_dir=workflows_dir,
    workflow_id=active_workflow_id,
    role_name=agent_type or name,
    current_phase=current_phase,
)

if folder_prompt:
    full_prompt = f"{folder_prompt}\n\n---\n\n{prompt}"
else:
    full_prompt = prompt

_send_prompt_fire_and_forget(agent, full_prompt, ...)
```

**Injection happens once at spawn time** (phase from `engine.get_current_phase()` — in-memory, no I/O). The agent's prompt persists in the conversation. Phase transitions don't mid-session inject — the agent calls the `get_phase` MCP tool if it needs current phase info. PostCompact hook restores context after `/compact`.

---

## 10. Hints Integration

### Migration: Template-Side → claudechic

The template-side `hints/` package (`AI_PROJECT_TEMPLATE/hints/`) has exactly the types and pipeline the new system needs. In ONE step, absorb the infrastructure into `claudechic/hints/`:

| Template-Side File | → claudechic Location | Contents |
|---|---|---|
| `hints/_types.py` | `claudechic/hints/types.py` | `TriggerCondition` (Protocol), `HintLifecycle` (Protocol), `HintSpec` (frozen dataclass), `HintDecl`, `HintRecord`, lifecycle impls: `ShowOnce`, `ShowUntilResolved`, `ShowEverySession`, `CooldownPeriod(seconds)` |
| `hints/_engine.py` | `claudechic/hints/engine.py` | `run_pipeline()` — 6-stage evaluation: activation → trigger → lifecycle → sort → budget → present |
| `hints/_state.py` | `claudechic/hints/state.py` | `ProjectState`, `CopierAnswers`, `HintStateStore` (`.claude/hints_state.json`), `ActivationConfig` |
| `hints/__init__.py` | `claudechic/hints/__init__.py` | Public API: `evaluate()` entry point |

**Key types reused:**
```python
# From hints/types.py (existing, moved to claudechic)

class TriggerCondition(Protocol):
    def check(self, state: ProjectState) -> bool: ...
    @property
    def description(self) -> str: ...

class HintLifecycle(Protocol):
    def should_show(self, hint_id: str, state: HintStateStore) -> bool: ...
    def record_shown(self, hint_id: str, state: HintStateStore) -> None: ...

@dataclass(frozen=True)
class HintSpec:
    id: str
    trigger: TriggerCondition
    message: str | Callable[[ProjectState], str]
    severity: Literal["info", "warning"] = "info"
    priority: int = 3
    lifecycle: HintLifecycle = ShowUntilResolved()
```

**New capability:** `AlwaysTrue` trigger condition for the CheckFailed adapter — hint always activates when created from a failed check.

**`app.py._run_hints()`** switches from `importlib` dynamic loading to direct import of `claudechic.hints`.

---

## 11. Refactoring Map

### Migration Table

#### guardrails/rules.py

| Existing Code | Action | New Location | Changes |
|---|---|---|---|
| `Rule` dataclass | **Modify in place** | guardrails/rules.py | Add required `namespace: str` field (no default). YAML uses `roles`/`exclude_roles` and `phases`/`exclude_phases`. |
| `load_rules(rules_path)` | **Replace** | workflows/loader.py | Old `load_rules()` deleted. All rule loading through ManifestLoader. RulesParser implements ManifestSection[Rule]. |
| `matches_trigger()` | **No change** | guardrails/rules.py | Unchanged. |
| `match_rule()` | **No change** | guardrails/rules.py | Unchanged. |
| `should_skip_for_role()` | **No change** | guardrails/rules.py | Unchanged. |
| `should_skip_for_phase()` | **Modify** | guardrails/rules.py | Signature: `(rule, phase_state: dict)` → `(rule, current_phase: str \| None)`. Engine provides the string. |
| `read_phase_state()` | **Delete** | N/A | Phase state restored from `Chicsession.workflow_state` via `WorkflowEngine.from_session_state()`. Normal operation uses `get_current_phase()` (in-memory). |

#### app.py Hook Code

| Existing Code | Action | New Location | Changes |
|---|---|---|---|
| `_guardrail_hooks()` | **Extract** | guardrails/hooks.py | Free function `create_guardrail_hooks(loader, hit_logger, agent_role, get_phase, consume_override)`. Two-step pipeline: injections first, then enforcement (log/warn/deny). Receives shared `ManifestLoader` + `HitLogger` + `GetPhaseCallback` + `OverrideTokenConsumer`. |
| `_show_guardrail_confirm()` | **Rename/repurpose** | app.py | Used by `request_override` MCP tool for user approval of specific `deny`-blocked commands. Shows exact tool name + input in SelectionPrompt. |
| `_plan_mode_hooks()` | **Stays** | app.py | App-level concern. No change. |
| `_merged_hooks()` | **Modify** | app.py | Add workflow hooks and PostCompact hook to merge. |
| `_make_options()` | **Modify** | app.py | No signature change; hooks now include workflow hooks. |
| `_run_hints()` | **Modify** | app.py | Switch from dynamic import to `claudechic.hints`. |

### Rule Dataclass — Redesigned

```python
@dataclass(frozen=True)
class Rule:
    id: str            # Qualified: "project-team:pip_block"
    namespace: str     # Required, no default: "global" or workflow_id
    trigger: list[str]
    enforcement: str
    detect_pattern: re.Pattern[str] | None = None
    detect_field: str = "command"
    exclude_pattern: re.Pattern[str] | None = None
    message: str = ""
    roles: list[str] = field(default_factory=list)
    exclude_roles: list[str] = field(default_factory=list)
    phases: list[str] = field(default_factory=list)
    exclude_phases: list[str] = field(default_factory=list)
```

### should_skip_for_phase() — Simplified

```python
# Old:
def should_skip_for_phase(rule: Rule, phase_state: dict[str, Any] | None) -> bool:

# New:
def should_skip_for_phase(rule: Rule, current_phase: str | None) -> bool:
```

### YAML Key Alignment

YAML keys map directly to code field names. No translation layer needed.

### YAML ↔ Code Field Mapping

| YAML Key | Code Field | Type | Notes |
|----------|-----------|------|-------|
| `id` | `id` | `str` | Bare in YAML, qualified at runtime (`namespace:id`) |
| `trigger` | `trigger` | `list[str]` | e.g. `PreToolUse/Bash` |
| `enforcement` | `enforcement` | `str` | `deny`, `warn`, `log` |
| `detect.pattern` | `detect_pattern` | `re.Pattern` | Compiled regex |
| `detect.field` | `detect_field` | `str` | Default: `"command"` |
| `exclude_if_matches` | `exclude_pattern` | `re.Pattern` | Compiled regex |
| `message` | `message` | `str` | Human-readable block message |
| `roles` | `roles` | `list[str]` | Rule fires only for these roles |
| `exclude_roles` | `exclude_roles` | `list[str]` | Rule never fires for these roles |
| `phases` | `phases` | `list[str]` | Rule fires only during these phases. Bare names in same manifest (auto-qualified); qualified IDs for cross-workflow refs. |
| `exclude_phases` | `exclude_phases` | `list[str]` | Rule never fires during these phases. Same qualification rules as `phases`. |
| `inject_value` | `inject_value` | `str` | Injection: what to inject (in `injections:` section) |
| `advance_checks[].type` | `CheckDecl.type` | `str` | Check type name |
| `advance_checks[].params` | `CheckDecl.params` | `dict` | Check-specific parameters |
| `hints[].lifecycle` | `HintDecl.lifecycle` | `str` | `show-once`, `show-until-resolved`, etc. |

### Manifest Types (Dissolved — No `manifest_types.py`)

Each type lives in the package that owns its domain:

```python
# claudechic/checks/protocol.py
@dataclass(frozen=True)
class CheckDecl:
    id: str
    type: str  # "command-output-check", "file-exists-check", etc.
    params: dict[str, Any]
    on_failure: dict | None = None
    when: dict | None = None
```

```python
# claudechic/hints/types.py
@dataclass(frozen=True)
class HintDecl:
    id: str
    message: str
    lifecycle: str = "show-once"
    cooldown_seconds: int | None = None
    phase: str | None = None       # qualified phase ID, or None for unscoped
    namespace: str = ""
```

```python
# claudechic/workflows/phases.py — bridge type (imports from two leaf packages)
from claudechic.checks.protocol import CheckDecl
from claudechic.hints.types import HintDecl

@dataclass(frozen=True)
class Phase:
    id: str                         # namespace-qualified
    file: str
    advance_checks: list[CheckDecl] = field(default_factory=list)
    hints: list[HintDecl] = field(default_factory=list)
```

**Phase-nested hint ID auto-generation:** Hints declared inside a phase's `hints:` list without an explicit `id` get auto-generated IDs: `{namespace}:{phase_id}:hint:{index}` where `index` is the 0-based position in the phase's hints list. For example, the first hint in `project_team.yaml`'s `implementation` phase gets ID `project-team:implementation:hint:0`. The `PhasesParser` generates these IDs during parsing, before the hints are flattened into the main hints list.

### RulesParser Implementation

```python
class RulesParser:
    """Parses the 'rules' section of manifests into Rule objects."""

    @property
    def section_key(self) -> str:
        return "rules"

    def parse(
        self,
        raw: list[dict[str, Any]],
        *,
        namespace: str,
        source_path: str,
    ) -> list[Rule]:
        rules: list[Rule] = []
        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                logger.warning("Skipping non-dict rule #%d in %s", i, source_path)
                continue
            result = self._parse_one(entry, namespace, source_path)
            if isinstance(result, Rule):
                rules.append(result)
            else:
                logger.warning("Skipping rule in %s: %s", source_path, result)
        return rules

    def _parse_one(self, entry: dict, namespace: str, source_path: str) -> Rule | str:
        raw_id = entry.get("id")
        if not raw_id or not isinstance(raw_id, str):
            return "missing 'id' field"
        if ":" in raw_id:
            return f"raw ID '{raw_id}' contains ':' — use bare IDs only"

        qualified_id = f"{namespace}:{raw_id}"

        raw_trigger = entry.get("trigger", "")
        triggers = [raw_trigger] if isinstance(raw_trigger, str) else [str(t) for t in raw_trigger]
        if not any(triggers):
            return f"rule '{raw_id}' has no trigger"

        enforcement = entry.get("enforcement", "deny")
        if enforcement not in ("deny", "warn", "log"):
            return f"unknown enforcement '{enforcement}'"

        detect = entry.get("detect", {})
        detect_pattern = None
        detect_field = "command"
        if isinstance(detect, dict) and detect.get("pattern"):
            try:
                detect_pattern = cached_compile(detect["pattern"])
            except re.error as e:
                return f"invalid detect regex: {e}"
            detect_field = detect.get("field", "command")

        exclude_pattern = None
        exclude_str = entry.get("exclude_if_matches", "")
        if exclude_str:
            try:
                exclude_pattern = cached_compile(exclude_str)
            except re.error as e:
                return f"invalid exclude regex: {e}"

        return Rule(
            id=qualified_id,
            namespace=namespace,
            trigger=triggers,
            enforcement=enforcement,
            detect_pattern=detect_pattern,
            detect_field=detect_field,
            exclude_pattern=exclude_pattern,
            message=entry.get("message", ""),
            roles=_as_list(entry.get("roles", [])),
            exclude_roles=_as_list(entry.get("exclude_roles", [])),
            phases=_as_list(entry.get("phases", [])),
            exclude_phases=_as_list(entry.get("exclude_phases", [])),
        )
```

### Files Summary

**CREATE:**
1. `claudechic/workflows/__init__.py`
2. `claudechic/workflows/loader.py`
3. `claudechic/workflows/engine.py`
4. `claudechic/workflows/phases.py` — `Phase` dataclass (bridge type, imports `CheckDecl` + `HintDecl`)
5. `claudechic/workflows/agent_folders.py`
6. `claudechic/checks/__init__.py` — Public API: `Check`, `CheckResult`, `CheckDecl`, `register_check_type`, `check_failed_to_hint`
7. `claudechic/checks/protocol.py` — `Check` protocol, `CheckResult`, `CheckDecl` (leaf — stdlib only)
8. `claudechic/checks/builtins.py` — 4 built-in types + `_CHECK_REGISTRY` + `register_check_type`
9. `claudechic/checks/adapter.py` — `CheckFailed` → `HintSpec` bridge
10. `claudechic/guardrails/hooks.py`
11. `claudechic/guardrails/hits.py` — `HitRecord` dataclass, `HitLogger` (append-only JSONL writer), hit outcome tracking
12. `claudechic/guardrails/tokens.py` — `OverrideToken`, `OverrideTokenStore` (leaf — stdlib only)
13. `claudechic/hints/__init__.py`
14. `claudechic/hints/types.py` — `HintSpec`, `HintLifecycle`, `TriggerCondition`, `HintDecl`
15. `claudechic/hints/engine.py` — `run_pipeline()` — 6-stage evaluation pipeline
16. `claudechic/hints/state.py` — `ProjectState`, `CopierAnswers`, `HintStateStore`, `ActivationConfig`

**MODIFY:**
1. `claudechic/guardrails/rules.py` — Add `namespace` field; simplify `should_skip_for_phase()` signature; delete `load_rules()` and `read_phase_state()`
2. `claudechic/guardrails/__init__.py` — Add hooks.py exports
3. `claudechic/app.py` — Extract `_guardrail_hooks` body to `guardrails/hooks.py`; update `_merged_hooks`; add engine init with `persist_fn` wiring; pass `token_store.consume` to hooks; init `HitLogger` + `OverrideTokenStore`; add `_show_override_prompt` for `request_override` MCP; add PostCompact
4. `claudechic/mcp.py` — Add agent folder prompt assembly to `spawn_agent`; add `advance_phase`, `get_phase`, `request_override`, and `acknowledge_warning` MCP tools
5. `claudechic/chicsessions.py` — Add `workflow_state: dict | None = None` field to `Chicsession` dataclass

**DELETE (file-based system removal — after new system validated):**
1. `.claude/guardrails/generate_hooks.py` — Shell hook generator, replaced by closure-based hooks
2. `.claude/guardrails/hooks/` — Generated shell hook scripts
3. `.claude/guardrails/role_guard.py` — Ack token mechanism, replaced by `acknowledge_warning` MCP tool + one-time tokens
4. `.claude/guardrails/rules.yaml` — Replaced by `global/rules.yaml` + workflow manifests
5. `.claude/guardrails/hits.jsonl` — Replaced by `.claude/hits.jsonl`
6. `.claude/guardrails/sessions/` — Session markers, replaced by chicsession + env var

**UNCHANGED:**
1. `claudechic/compact.py` — PostCompact hook is SDK-level, not compact.py
2. `claudechic/agent.py` — Agent is prompt-agnostic
3. `claudechic/agent_manager.py` — Already passes `agent_type` through

---

## 12. Import Dependency Graph

```
app.py
  ├── guardrails/hooks.py           (create_guardrail_hooks — rule-evaluation hooks)
  ├── guardrails/hits.py            (HitLogger — created at app init)
  ├── guardrails/tokens.py          (OverrideTokenStore — created at app init)
  ├── guardrails/rules.py           (Rule — type hints only)
  ├── workflows/engine.py           (WorkflowEngine — phase state, checks)
  ├── workflows/agent_folders.py    (assemble_phase_prompt)
  ├── chicsessions.py               (Chicsession — workflow_state field)
  └── hints/__init__.py             (run_pipeline — toast scheduling)

guardrails/hooks.py
  ├── guardrails/rules.py           (Rule, Injection, matches_trigger, should_skip_for_role, should_skip_for_phase)
  ├── guardrails/hits.py            (HitRecord, HitLogger)
  └── claude_agent_sdk.types        (HookMatcher)

guardrails/hits.py
  └── (json, pathlib, time only — no claudechic imports)

guardrails/tokens.py
  └── (hashlib, json, dataclasses only — no claudechic imports)

workflows/engine.py
  ├── workflows/phases.py           (Phase)
  ├── checks/protocol.py            (Check, CheckResult, CheckDecl)
  ├── checks/builtins.py            (register_check_type, _build_check)
  ├── checks/adapter.py             (check_failed_to_hint)
  ├── workflows/agent_folders.py    (assemble_agent_prompt)
  ├── guardrails/rules.py           (match_rule, matches_trigger, should_skip_*)
  └── claude_agent_sdk.types        (HookMatcher)

workflows/loader.py
  ├── guardrails/rules.py           (Rule, Injection — for rule/injection parsing)
  ├── checks/protocol.py            (CheckDecl)
  ├── hints/types.py                (HintDecl)
  ├── workflows/phases.py           (Phase)
  └── yaml

workflows/phases.py                 (bridge type — the one file importing from two leaf packages)
  ├── checks/protocol.py            (CheckDecl)
  └── hints/types.py                (HintDecl)

workflows/agent_folders.py
  └── (pathlib only — no claudechic imports)

checks/protocol.py
  └── (dataclasses only — no claudechic imports)

checks/builtins.py
  └── checks/protocol.py            (Check, CheckResult, CheckDecl)

checks/adapter.py
  ├── checks/protocol.py            (CheckResult)
  └── hints/types.py                (HintSpec)

hints/types.py
  └── (dataclasses only — no claudechic imports)

hints/engine.py
  ├── hints/types.py
  └── hints/state.py

hints/state.py
  └── (json, pathlib only)

hints/__init__.py
  ├── hints/types.py
  ├── hints/engine.py
  └── hints/state.py
```

### Circular Import Verification

**Three leaf packages — no cycles:**
- `guardrails/` → (stdlib only within package; `tokens.py` and `hits.py` are leaf nodes; no imports from workflows/, checks/, or hints/)
- `checks/protocol.py` → (stdlib only): leaf node
- `checks/builtins.py` → `checks/protocol.py`: one-way within package
- `checks/adapter.py` → `checks/protocol.py` + `hints/types.py`: one-way
- `hints/` → (stdlib only within package; no imports from workflows/, checks/, or guardrails/)
- `workflows/` → `guardrails/rules.py`, `checks/protocol.py`, `hints/types.py`: one-way (orchestration layer)
- `workflows/phases.py` → `checks/protocol.py` + `hints/types.py`: one-way (bridge type)
- `app.py` imports from all four packages but none import `app.py`

**Architecture invariant:** `guardrails/`, `checks/`, `hints/` are leaf packages — none import from `workflows/`. `workflows/` is the orchestration layer that imports from all three.

### Seam Cleanliness

| Boundary | Clean? | Notes |
|---|---|---|
| `workflows/` → `guardrails/rules.py` | ✅ | Only imports `Rule`, `Injection`, and matching functions |
| `workflows/` → `checks/protocol.py` | ✅ | Only imports `Check`, `CheckResult`, `CheckDecl` |
| `workflows/` → `hints/types.py` | ✅ | Only imports `HintDecl` |
| `checks/adapter.py` → `hints/types.py` | ✅ | Only imports `HintSpec` dataclass (CheckFailed bridge) |
| `app.py` → `guardrails/hooks.py` | ✅ | Factory function, passes loader + hit_logger + callbacks |
| `app.py` → `workflows/engine.py` | ✅ | Engine API, passes persist_fn + confirm callback for ManualConfirm |
| `hints/` standalone | ✅ | Zero imports from workflows/, checks/, or guardrails/ |
| `guardrails/` standalone | ✅ | Zero imports from workflows/, checks/, or hints/ |
| `checks/` semi-standalone | ✅ | Only `adapter.py` imports from `hints/types.py`; `protocol.py` and `builtins.py` are self-contained |

---

See [APPENDIX.md](APPENDIX.md) for risk register (R1–R12) and worked examples (7 examples covering manifests, phase transitions, rule evaluation, hook closures, discovery, and validation).

---

## Scope Boundaries

### In Scope (Build)
- Unified manifest loader with typed section parsers (ManifestSection[T])
- Workflow engine (phase transitions, advance_checks gates, state persistence)
- Explicit workflow activation via auto-discovered slash commands (`/{workflow-id}`, `/workflow list`, `/workflow reload`)
- Check protocol with 4 built-in types and CheckFailed → hints adapter
- Agent folder structure and prompt assembly
- `global/` directory with setup checks, global rules, and global hints
- COORDINATOR.md content split into agent folder
- `/compact` recovery hook (PostCompact)
- Phase-scoped rule evaluation
- Hints infrastructure absorbed from template-side into `claudechic/hints/`

### Explicitly Out of Scope
- **CompoundCheck** — OR semantics for checks
- **Content focus guards** — phase-aware read guards
- **Multi-workflow** — multiple workflows active simultaneously (enforced by the one-active-at-a-time slash command model)

- **`regex_miss` detect type** — negated pattern matching (rule fires when pattern does NOT match). Can be added later via a `negate: true` field on `detect`. Current spec supports `regex_match` (detect pattern present) and `always` (detect pattern absent).
- **`spawn_type_defined` detect type** — validates that the spawned agent type exists in agent folders. Can be added as a custom detect type once the detect system is extensible.

---

See [APPENDIX.md](APPENDIX.md) for future scope: MCP tools (`get_workflow_info`, `set_phase`, `list_phases`, `list_checks`, `run_check`), hint lifecycles (`show-until-phase-complete`), and NFS performance strategy.
