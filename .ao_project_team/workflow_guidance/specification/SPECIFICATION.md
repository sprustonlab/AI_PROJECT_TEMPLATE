# Workflow Guidance System — Architecture Specification

> **Status:** Implementation-ready specification.
> **Scope:** Infrastructure in claudechic that lets workflows define phases, rules, checks, and hints via YAML manifests and markdown files. The project-team workflow is the first workflow built on this infrastructure.

---

## 1. Vision

Extend claudechic to offer a unified guidance system — advisory and enforced, positive and negative — where any workflow is just YAML manifest + markdown content. Users write manifests and agent folders. claudechic provides the engine, the loader, the checks, and the hooks. One combined system, one set of primitives, any workflow type.

**Why:**
- Guidance is currently scattered across multiple systems, formats, and locations. Rules, checks, and hints each have their own mechanism.
- Users shouldn't need to learn three separate systems. A single pattern — YAML manifests + markdown content in `workflows/` — makes guidance easy to author, understand, and maintain.
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
| `.claude/guardrails/rules.yaml` | `workflows/global.yaml` + workflow manifests | Rules now in manifests with namespace prefixing |
| `.claude/guardrails/hits.jsonl` | `workflows/.hits.jsonl` via `guardrails/hits.py` | Richer data (outcome, agent role, enforcement level) |
| Session markers (`.claude/guardrails/sessions/`) | `Chicsession.workflow_state` + `CLAUDE_AGENT_ROLE` env var | Role set at spawn time, state in chicsession |

---

## 2. Terminology

> All terms are defined canonically here. Other sections reference but do not redefine them.

### Core Concepts

| Term | Definition |
|------|-----------|
| **Workflow** | A named configuration — YAML manifest + markdown content in a directory under `workflows/` — that defines phases, rules, checks, and hints. Each workflow has a `workflow_id` (kebab-case, e.g. `project-team`) used in namespacing. |
| **Manifest** | A YAML file declaring rules, phases, checks, and hints. Two kinds: **global manifest** (`workflows/global.yaml`, always active, no phases) and **workflow manifest** (`workflows/<name>/<name>.yaml`, scoped to one workflow). Filename matches directory name (folder name = identity). |
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
| **Role Scoping** | `roles_only` — rule fires *only* for these roles (scope-to). `roles_except` — rule *never* fires for these roles (exclude). |
| **Phase Scoping** | `phase_only` — rule fires only during these phases (scope-to, qualified IDs). `phase_except` — rule *never* fires during these phases (exclude, qualified IDs). |

### Phases

| Term | Definition |
|------|-----------|
| **Phase** | A named period in a workflow's lifecycle (e.g. `vision`, `setup`, `specification`). Ordered. Each has an `id`, a `file` reference, optional `advance_checks`, and optional `hints`. |
| **Phase Transition** | Moving from current phase to next. Gated by `advance_checks` — all must pass (AND semantics, short-circuit on first failure). |
| **Phase State** | Runtime tracking of current phase. Held in-memory by the engine, persisted via `Chicsession.workflow_state` on each phase transition. On session resume, the engine restores state from the chicsession. |
| **Qualified Phase ID** | `<workflow_id>:<phase_id>` (e.g. `project-team:testing`). Used in `phase_only` and `phase_except` fields. Bare phase IDs are never used in scoping fields. |

### Checks

| Term | Definition |
|------|-----------|
| **Check** | A verification that tests system state and returns pass/fail with evidence. The engine runs checks — not the agent. Protocol is async. |
| **Advance Checks** | Checks under a phase's `advance_checks` key. Gate phase transitions. AND semantics, short-circuit on first failure. |
| **Setup Checks** | Checks in `global.yaml` that verify environment prerequisites. Include `on_failure` with message, severity, lifecycle. Bridged to hints pipeline via CheckFailed adapter. |
| **`when` Clause** | Condition on checks that gates whether the check runs, based on copier-answer values (e.g. `when: { copier: use_cluster }`). Evaluation semantics: truthy (value is present and not false/empty). |
| **`on_failure`** | Block on checks specifying what happens on failure: `message` (human-readable), `severity` (`warning`), `lifecycle` (e.g. `show-until-resolved`). |

### Hints

| Term | Definition |
|------|-----------|
| **Hint** | Advisory content delivered to the agent or user. Declared in manifests under phase entries or globally. Engine converts declarations to `HintSpec` objects via `run_pipeline()`. |
| **HintSpec** | Internal object representing a hint after manifest parsing. Consumed by the existing hints pipeline. |
| **Hint Lifecycle** | Controls display behavior: `show-once` (displayed once, suppressed), `show-until-resolved` (repeated until condition passes). Out of scope: `ShowUntilPhaseComplete`. |
| **CheckFailed Adapter** | Bridges failing checks into the hints pipeline. When a check fails and has `on_failure` config, produces a `HintSpec` surfaced through `run_pipeline()`. |

### Agent Folders

| Term | Definition |
|------|-----------|
| **Agent Folder** | A directory inside a workflow directory (e.g. `workflows/project_team/coordinator/`). The folder name IS the role type. |
| **Role Type** | Identity of an agent, derived from folder name (e.g. `coordinator`, `implementer`, `skeptic`). Used in `roles_only`/`roles_except` and captured in SDK hook closures at spawn time. |
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
| **Namespace** | Prefix applied to bare IDs at load time: `_global:<id>` for global manifest items, `<workflow_id>:<id>` for workflow items. All IDs are namespaced at runtime. IDs in YAML are written bare — the loader prefixes automatically. |
| **Qualified ID** | The runtime form: `namespace:name`. Examples: `_global:pip_block`, `project-team:close_agent`. |

### Additional Terms

| Term | Definition |
|------|-----------|
| **WorkflowManifest** | Parsed representation of a workflow's YAML manifest. Contains the `workflow_id`, phases list, and metadata. Passed to `WorkflowEngine` at construction. |
| **HitRecord / Hit** | A single rule match event recorded in the audit trail. Contains `rule_id`, `agent_role`, `tool_name`, `enforcement`, `timestamp`, and `outcome`. Written as JSONL to `workflows/.hits.jsonl`. |
| **Toast** | A TUI notification displayed briefly to the user. Used by the hints pipeline (`run_pipeline()`) to surface advisory hints and check failure messages. |
| **`run_pipeline()`** | The 6-stage hints evaluation pipeline: activation → trigger → lifecycle → sort → budget → present. Converts `HintSpec` objects into displayed toasts. |
| **AlwaysTrue** | A `TriggerCondition` implementation that always returns `True`. Used by the `CheckFailed` adapter — when a check has already failed, the resulting hint fires immediately without further evaluation. |

### Content Delivery

**Pull-based:** The engine does NOT inject content mid-session. Agents call the `get_phase` MCP tool to discover the current phase, then read their own markdown files. The only exception is `/compact` recovery via the PostCompact hook. All phase queries go through the in-memory engine via MCP tools.

### Failure Modes

| Mode | When | Behavior |
|------|------|----------|
| **Fail Closed** | `workflows/` unreadable | Block everything. |
| **Fail Open** | Individual manifest malformed or bad regex | Skip that manifest/item, load the rest. |
| **Startup Validation** | Manifest load time | Duplicate ID detection, invalid regex detection, unknown phase reference validation. Raw IDs containing `:` rejected. |

### Terminology Hygiene

1. **Rule vs Check** — Rules are reactive (fire on tool calls). Checks are proactive (engine evaluates state). Distinct mechanisms.
2. **Phase** exclusively — never "stage" or "step."
3. **Manifest** for YAML files in `workflows/`. "Config" refers to `~/.claude/.claudechic.yaml`.
4. **Agent folder** — not "role directory."
5. **Rule** = precise mechanism term covering all three enforcement levels (`deny`, `warn`, `log`). **Guardrail** = colloquial shorthand for Quadrant D only (enforced negative: `deny`). **Guidance** = umbrella for all four quadrants. In prose, use "rule" when referring to the mechanism generally; reserve "guardrail" for specifically enforced negative rules. **Injection** is a separate tool-input modification mechanism declared in the `injections:` manifest section, not an enforcement level and not in the `rules:` section.
6. **Advisory** is a classification. **Hint** is a specific mechanism (`HintSpec`/`run_pipeline()`). Advisory markdown (Quadrant A) is not delivered as hints.
7. **Engine** manages state and transitions. **Loader** reads and parses manifests. Separate components.
8. **Workflow** = full package (directory + manifest + agent folders + state). **Workflow manifest** = the YAML file specifically.
9. **Identity** = cross-phase `identity.md`. **Agent prompt** = identity + phase file.
10. **`roles_only`/`roles_except`** restrict by role. **`phase_only`/`phase_except`** restrict by phase. `_only` = scope-to (fires only for listed values). `_except` = exclude (never fires for listed values).

---

## 3. Architecture — Composability Axes

The system has six independent axes. Any combination of axis values produces a working system.

### Axis 1: Section Type (ManifestSection[T])

The kind of guidance declared in a manifest — `rules`, `checks`, `hints`, `phases`. Each has its own parser, runtime semantics, and delivery mechanism. The loader dispatches YAML sections to typed parsers without knowing what a "rule" or "check" means.

**Compositional law:** `ManifestSection[T].parse(raw_yaml_section) -> list[T]`. The loader doesn't branch on section type — it dispatches uniformly.

**Seam:** Raw YAML dict (output of `yaml.safe_load`) crosses the boundary. The loader doesn't interpret section contents. The parser doesn't know about other sections or about the file it came from.

### Axis 2: Check Type

How verification is performed. Four built-in types, extensible via the Check protocol.

**Compositional law:** `async Check.check() -> CheckResult(passed: bool, evidence: str)`. The engine doesn't know which type it's running. A new check type works everywhere checks are used — no engine changes.

**Seam:** `CheckResult` crosses the boundary. The engine sees pass/fail + evidence. The check doesn't know whether it's gating a phase or reporting at startup.

### Axis 3: Scope (Where guidance applies)

Filtering dimensions that compose with AND semantics:

| Filter | Values | Applies to |
|--------|--------|------------|
| **Namespace** | `_global` \| `{workflow_id}` | All guidance types |
| **Phase** | `phase_only` / `phase_except` lists | Rules, hints |
| **Role** | `roles_only` / `roles_except` lists | Rules |
| **Conditional** | `when: { copier: key }` | Checks |

Each filter is `(context) -> bool`. Evaluation: `all(f(ctx) for f in applicable_filters)`. No filter inspects another filter's state.

**Phase references cross workflow boundaries:** `phase_only: ["project-team:testing"]` in `global.yaml` creates a coupling to a specific workflow. This is intentional (qualified IDs prevent ambiguity). The loader's startup validation makes this coupling explicit and fails fast.

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

The foundational axis. Content = `workflows/` directory (YAML + markdown). Infrastructure = claudechic code (loader, engine, checks, hooks, delivery).

**Compositional law:** Manifests follow a schema. Markdown files follow a naming convention (folder name = role, file name = phase). Infrastructure processes any content that follows these conventions.

**Seam:** The `workflows/` directory boundary. claudechic reads from it but never writes workflow-specific logic.

### 10-Point Crystal Spot Check

| # | Section Type | Check Type | Scope | Enforcement | Lifecycle | Works? |
|---|-------------|-----------|-------|-------------|-----------|--------|
| 1 | rule | N/A | global + phase_only | deny | N/A | ✅ existing guardrails |
| 2 | check | CommandOutput | global | toast (via adapter) | show-until-resolved | ✅ setup checks |
| 3 | check | ManualConfirm | workflow phase | toast (via adapter) | show-once | ✅ advance_checks |
| 4 | hint | N/A | workflow phase | toast | show-once | ✅ phase hints |
| 5 | rule | N/A | global + role filter | deny | N/A | ✅ role-scoped rules |
| 6 | check | FileExists | global | toast (via adapter) | show-until-resolved | ✅ setup check |
| 7 | rule | N/A | workflow + phase_except | deny | N/A | ✅ phase-scoped rule |
| 8 | check | FileContent | workflow phase advance | N/A | N/A | ✅ advance gate |
| 9 | hint | N/A | global | toast | cooldown | ✅ global hint |
| 10 | check | ManualConfirm | global setup | toast (via adapter) | show-until-resolved | ⚠️ edge case — works mechanically but unusual |

No crystal holes found.

### Compositional Law Summary

1. **ManifestSection[T] law** — All section parsers consume raw YAML dicts and produce typed objects.
2. **Check protocol law** — All checks implement `async check() -> CheckResult`.
3. **`workflows/` convention law** — All workflows are YAML + markdown following naming conventions. claudechic doesn't know workflow domain semantics.

These three laws guarantee: a new workflow with new check types and new section types can be added without modifying claudechic infrastructure code.

---

## 4. Directory Structure

### Project-Side Content (`workflows/`)

```
workflows/
  global.yaml                        # Global manifest: rules, checks, hints (always active, no phases)
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

Folder name = identity everywhere: manifest filename, rule ID namespace, agent folder name.

### claudechic Infrastructure

```
claudechic/
  workflows/                    # NEW package
    __init__.py                 # Public API: ManifestLoader, WorkflowEngine, etc.
    loader.py                   # ManifestSection[T] dispatcher, manifest discovery
    engine.py                   # Phase transitions, state persistence, advance_checks
    checks.py                   # Check protocol + 4 built-in types + CheckFailed adapter
    agent_folders.py            # Prompt assembly from identity + phase files
    manifest_types.py           # Parsed types: Phase, CheckSpec, HintDecl

  guardrails/                   # EXISTING, refactored
    __init__.py                 # MODIFIED — add exports from hooks.py
    rules.py                    # MODIFIED — Rule gains namespace field; load_rules() replaced
    hooks.py                    # NEW — hook closure creation (extracted from app.py)
    hits.py                     # NEW — HitRecord, HitLogger (append-only JSONL audit trail)

  hints/                        # NEW claudechic package (absorbed from template-side)
    __init__.py                 # Public API: evaluate hints
    _types.py                   # HintSpec, HintLifecycle, TriggerCondition (protocols + impls)
    _engine.py                  # run_pipeline() — 6-stage evaluation pipeline
    _state.py                   # ProjectState, CopierAnswers, HintStateStore, ActivationConfig
```

The axis structure is visible in folders:
- `workflows/` = engine/loader infrastructure (axes 1, 2, 6)
- `guardrails/` = rule evaluation and enforcement delivery (axis 4 for rules — all enforcement levels)
- `hints/` = advisory delivery + lifecycle (axes 4, 5 for hints)
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
            namespace: '_global' for global.yaml, workflow_id for workflow manifests.
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
| `injections` | `Injection` | Tool-input modification declaration — trigger, detect, inject_value, scope metadata |
| `checks` | `CheckSpec` | Check specification — type + params, not the executable check itself |
| `hints` | `HintDecl` | Hint declaration — message + lifecycle + scope metadata |
| `phases` | `Phase` | Phase definition — id, file reference, advance_checks, nested hints |

### Parse Method Contract

**Parser validates (section-specific):**
- Required fields present (rules need `id`, `trigger`, `enforcement`)
- Field value types (`enforcement` is one of `deny|warn|log`)
- Regex compilation (detect patterns, check patterns)
- Raw IDs don't contain `:` (reserved for namespace)
- Section-specific semantics

**Parser does NOT validate (loader's responsibility):**
- Duplicate IDs across manifests (needs cross-manifest view)
- Phase reference validity (`phase_only`/`phase_except` targets exist)
- Cross-section references

**Namespace prefixing happens IN the parser.** The parser receives `namespace` and prefixes every `id` field. The parser knows item structure; the loader is generic.

### Data Types

```python
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class LoadResult:
    """Complete result of loading all manifests."""
    rules: list[Rule] = field(default_factory=list)
    injections: list[Injection] = field(default_factory=list)
    checks: list[CheckSpec] = field(default_factory=list)
    hints: list[HintDecl] = field(default_factory=list)
    phases: list[Phase] = field(default_factory=list)
    errors: list[LoadError] = field(default_factory=list)


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
def discover_manifests(workflows_dir: Path) -> list[Path]:
    """Discover all manifest files under workflows/.

    Returns paths in load order:
    1. workflows/global.yaml (if exists)
    2. workflows/*/workflow_name.yaml (sorted alphabetically)

    Manifest filename must match parent directory name.
    Example: workflows/project_team/project_team.yaml ✓
             workflows/project_team/other.yaml ✗ (ignored)
    Hidden directories (.name) skipped.
    No recursive scanning — exactly one level deep.
    """
    manifests: list[Path] = []

    global_path = workflows_dir / "global.yaml"
    if global_path.is_file():
        manifests.append(global_path)

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

    def __init__(self, workflows_dir: Path) -> None:
        self._workflows_dir = workflows_dir
        self._parsers: dict[str, ManifestSection] = {}

    def register(self, parser: ManifestSection) -> None:
        self._parsers[parser.section_key] = parser

    def load(self) -> LoadResult:
        """Load all manifests and return unified result.

        Error handling:
        - workflows/ unreadable → fail closed (empty rules + fatal error;
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
                LoadError(source="discovery", message=f"Cannot read workflows/: {e}")
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

            if not isinstance(data, dict):
                errors.append(LoadError(source=str(path), message="not a YAML mapping"))
                continue

            # Override namespace from workflow_id if present
            if path.name != "global.yaml":
                wf_id = data.get("workflow_id")
                if wf_id:
                    namespace = str(wf_id)

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
YAML:           id: pip_block      (in global.yaml)
After parse:    id: _global:pip_block

YAML:           id: close_agent    (in project_team.yaml, workflow_id: project-team)
After parse:    id: project-team:close_agent

YAML:           id: testing        (phase in project_team.yaml)
After parse:    id: project-team:testing
```

Phase references are already qualified in YAML: `phase_only: ["project-team:testing"]`. The parser does NOT prefix these. The loader validates them against known phase IDs after all manifests are loaded.

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
        for ref in getattr(rule, "phase_only", []):
            if ref not in known_phases:
                errors.append(LoadError(
                    source="validation", section="rules", item_id=rule.id,
                    message=f"unknown phase ref '{ref}' in phase_only",
                ))
        for ref in getattr(rule, "phase_except", []):
            if ref not in known_phases:
                errors.append(LoadError(
                    source="validation", section="rules", item_id=rule.id,
                    message=f"unknown phase ref '{ref}' in phase_except",
                ))

    return errors
```

### NFS Performance Strategy

Rules are loaded fresh on every tool call. No mtime caching — NFS is unreliable on HPC clusters.

**Cost analysis:** ~2 small YAML files, ~0.5ms each for `yaml.safe_load`. Accept the I/O cost for simplicity.

**Day-one optimization — compiled regex cache:**
```python
_REGEX_CACHE: dict[str, re.Pattern[str]] = {}

def cached_compile(pattern: str) -> re.Pattern[str]:
    """Compile regex with caching. Safe for concurrent reads."""
    if pattern not in _REGEX_CACHE:
        _REGEX_CACHE[pattern] = re.compile(pattern)
    return _REGEX_CACHE[pattern]
```

**If optimization is needed later (priority order):**
1. Content hash cache (SHA256 before parsing — marginal gain)
2. Lazy section parsing (breaks single-path principle — last resort)

### Error Strategy Matrix

| Failure | Behavior | Rationale |
|---------|----------|-----------|
| `workflows/` unreadable | **Fail closed** — empty rules + fatal error. Callers block everything. | Can't evaluate rules we can't read. |
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
        return {"decision": "block", "message": "Rules unavailable — workflows/ unreadable"}
```

### Hint Scoping Model

```
Scope Level          Source Location                    Active When
─────────────        ───────────────                    ───────────
Global               global.yaml → hints:               Always
Workflow-wide        workflow.yaml → hints:              Whenever workflow is active
Phase-scoped         workflow.yaml → phases[].hints:     Only during that phase
```

Phase-nested hints are extracted by the `PhasesParser` into `Phase.hints` field, then flattened by the loader into the main hints list with phase scope metadata attached.

---

## 6. Checks

### Check Protocol

```python
# claudechic/workflows/checks.py

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

def _build_check(self, check_spec: CheckSpec) -> Check:
    """Map CheckSpec to Check objects via registry."""
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
| Location | `global.yaml` `checks:` section | Phase `advance_checks:` list |
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
        advance_checks: list[CheckSpec],
    ) -> bool:
        """AND semantics, sequential, short-circuit on first failure."""
        for i, spec in enumerate(advance_checks):
            check_id = f"{workflow_id}:{current_phase}:advance:{i}"
            check_instance = self._build_check(spec)
            result = await check_instance.check()

            if not result.passed:
                # Fire hint if on_failure configured
                if "on_failure" in spec:
                    on_failure = OnFailureConfig(
                        message=spec["on_failure"]["message"],
                        severity=spec["on_failure"].get("severity", "warning"),
                        lifecycle=spec["on_failure"].get("lifecycle", "show-once"),
                    )
                    hint_data = check_failed_to_hint(result, on_failure, check_id)
                    if hint_data:
                        from claudechic.hints._engine import run_pipeline
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
async def run_setup_checks(self, check_specs: list[CheckSpec]) -> list[CheckResult]:
    """Run setup checks from global.yaml at startup.

    Unlike advance_checks, setup checks do NOT short-circuit.
    All checks run, all failures produce hints. Goal: surface
    all environment issues at once.
    """
    checks: list[tuple[str, Check, OnFailureConfig | None]] = []
    for spec in check_specs:
        check_id = f"_global:{spec['id']}"
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

```python
def get_post_compact_hook(self) -> dict[str, list[HookMatcher]]:
    """PostCompact hook: re-inject phase context after /compact."""
    engine = self

    async def reinject_phase_context(hook_input: dict, match: str | None, ctx: object) -> dict:
        current_phase = engine.get_current_phase()
        if not current_phase:
            return {}

        role = hook_input.get("agent_role")
        prompt_content = assemble_phase_prompt(
            workflows_dir=engine.workflows_dir,
            workflow_id=engine.manifest.workflow_id,
            role_name=role or "coordinator",
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

### Active Workflow Determination

At most one workflow manifest is active besides `global.yaml`. The engine auto-detects from loader results:

```python
def _resolve_active_workflow(
    load_result: LoadResult,
) -> str | None:
    """Determine the active workflow from loaded manifests.

    Rules:
    - If no workflow manifests (only global.yaml) → no engine, return None
    - If exactly one workflow manifest → that's the active workflow
    - If multiple → use first alphabetical, log warning

    Returns the workflow_id of the active workflow, or None.
    """
    # Collect unique workflow namespaces (exclude _global)
    workflow_ids: list[str] = []
    seen: set[str] = set()
    for phase in load_result.phases:
        ns = phase.id.split(":")[0]
        if ns != "_global" and ns not in seen:
            workflow_ids.append(ns)
            seen.add(ns)

    if not workflow_ids:
        return None
    if len(workflow_ids) > 1:
        logger.warning(
            "Multiple workflows found: %s. Using '%s'. "
            "Multi-workflow is out of scope.",
            workflow_ids, workflow_ids[0],
        )
    return workflow_ids[0]
```

### Engine Initialization

When the app starts, it creates the manifest loader, loads manifests, resolves the active workflow, and initializes the engine:

```python
# In app.py on_mount() or _connect_initial_client():

# 1. Create shared loader and hit logger (created once at app init)
self._manifest_loader = ManifestLoader(self._workflows_dir)
self._manifest_loader.register(RulesParser())
self._manifest_loader.register(InjectionsParser())
self._manifest_loader.register(ChecksParser())
self._manifest_loader.register(HintsParser())
self._manifest_loader.register(PhasesParser())

from claudechic.guardrails.hits import HitLogger
self._hit_logger = HitLogger(self._workflows_dir / ".hits.jsonl")

# 2. Initial load
result = self._manifest_loader.load()

# 3. Resolve active workflow
active_wf = _resolve_active_workflow(result)
if active_wf is None:
    self._workflow_engine = None  # No workflow — rules still evaluate via global.yaml
else:
    manifest = self._build_manifest(active_wf, result)
    session = self._current_session

    # Restore from chicsession or initialize fresh
    self._workflow_engine = WorkflowEngine.from_session_state(
        state=session.workflow_state if session else None,
        manifest=manifest,
        persist_fn=self._make_persist_fn(),
        confirm_callback=self._make_confirm_callback(),
    )

# 4. Run setup checks from global.yaml
if result.checks and self._workflow_engine:
    await self._workflow_engine.run_setup_checks(result.checks)
```

**State initialization:** On startup or session resume, the engine restores from chicsession state or initializes to the first phase:

```python
# In app.py — engine initialization

# Fresh start (no existing session):
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
    engine = app.workflow_engine
    if engine is None:
        return "No active workflow."

    approved = await app._show_override_prompt(
        rule_id,
        f"Agent wants to run blocked action:\n"
        f"  Tool: {tool_name}\n"
        f"  Input: {_format_tool_input(tool_input)}\n"
        f"  Blocked by: {rule_id}\n"
        f"Approve this specific action?"
    )

    if approved:
        engine.store_override_token(rule_id, tool_name, tool_input)
        return f"Override approved for rule {rule_id}. Retry the exact same command."
    else:
        return f"Override denied."
```

### Override Token State on Engine

The engine tracks one-time override tokens in memory. Tokens are consumed on use — NOT persisted, NOT session-wide. Each token authorizes exactly one execution of one specific command.

```python
import hashlib
import json

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


class WorkflowEngine:
    def __init__(self, ...):
        # ... existing fields ...
        self._override_tokens: list[OverrideToken] = []  # One-time tokens, consumed on use

    def store_override_token(self, rule_id: str, tool_name: str, tool_input: dict) -> None:
        """Store a one-time override token after user approval."""
        token = OverrideToken(
            rule_id=rule_id,
            tool_name=tool_name,
            tool_input_hash=_hash_tool_input(tool_input),
        )
        self._override_tokens.append(token)
        logger.info("Override token stored for rule '%s'", rule_id)

    def consume_override_token(self, rule_id: str, tool_name: str, tool_input: dict) -> bool:
        """Consume a one-time override token if one matches. Returns True if consumed."""
        input_hash = _hash_tool_input(tool_input)
        for i, token in enumerate(self._override_tokens):
            if (token.rule_id == rule_id
                    and token.tool_name == tool_name
                    and token.tool_input_hash == input_hash):
                self._override_tokens.pop(i)
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
- **Unified token mechanism** — both `warn` and `deny` use the same `OverrideToken(rule_id, tool_name, tool_input_hash)` and `consume_override_token()`. One in-memory list `_override_tokens: list[OverrideToken]` on the engine.
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
    engine = app.workflow_engine
    if engine is None:
        return "No active workflow."
    engine.store_override_token(rule_id, tool_name, tool_input)
    return f"Warning acknowledged for rule {rule_id}. Retry the exact same command."
```

- **Agent flow**: blocked → message includes `acknowledge_warning` instructions → agent calls `acknowledge_warning(rule_id, tool_name, tool_input)` (token stored, NO TUI prompt) → agent retries exact same command → token consumed → allowed
- Works for ALL tool types (Bash, Write, etc.) — no tool-specific conventions needed
- **Per-command scoping**: each invocation must be individually acknowledged. Token is consumed on use.

### `deny` — User-Authority Override Token

See §7 for the `request_override` MCP tool and `OverrideToken` implementation. Key properties:

- Token is keyed by `(rule_id, tool_name, hash(tool_input))` — approves a *specific action*, not a blanket rule suppression
- Token is **consumed on use** — next invocation of the same command is blocked again
- Tokens are **NOT persisted** — reset on session restart
- Uses the SAME `OverrideToken` and `consume_override_token()` as `warn` — unified mechanism
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
    roles_only: list[str] = field(default_factory=list)
    roles_except: list[str] = field(default_factory=list)
    phase_only: list[str] = field(default_factory=list)
    phase_except: list[str] = field(default_factory=list)
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

1. **Match trigger** — `matches_trigger(rule, tool_name)`: splits `PreToolUse/Bash` on `/`, compares tool name. Bare `PreToolUse` matches all.
2. **Check role skip** — `should_skip_for_role(rule, agent_role)`: `roles_only` = only fires for listed roles; `roles_except` = never fires for listed roles.
3. **Check phase skip** — `should_skip_for_phase(rule, current_phase)`: evaluates `phase_only`/`phase_except` against current qualified phase ID.
4. **Check exclude pattern** — if `exclude_pattern` matches, skip this rule.
5. **Match detect pattern** — if `detect_pattern` is set and doesn't match, skip this rule.
6. **Log hit** — every rule match is recorded as a `HitRecord` regardless of enforcement level (see §8.1).
7. **Apply enforcement:**
   - `log` → allow (hit logged, no block, continue to next rule)
   - `warn` → check `consume_override_token(rule.id, tool_name, tool_input)`; if token consumed → allow (outcome: `ack`, continue); otherwise → block with `acknowledge_warning` instructions
   - `deny` → check `consume_override_token(rule.id, tool_name, tool_input)`; if token consumed → allow (outcome: `overridden`, continue); otherwise → block with `request_override` instructions

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
OverrideTokenConsumer = Callable[[str, str, dict], bool]  # (rule_id, tool_name, tool_input) -> consumed


def create_guardrail_hooks(
    loader: "ManifestLoader",
    hit_logger: HitLogger,
    agent_role: str | None = None,
    get_phase: GetPhaseCallback | None = None,
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
                return {"decision": "block", "message": "Rules unavailable — workflows/ unreadable"}

        current_phase = get_phase() if get_phase else None

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

**Storage location:** `workflows/.hits.jsonl` (in the project's `workflows/` directory, dotfile to avoid cluttering the manifest listing). The hit log is project-specific — different projects have different hit histories.

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

**Replaces:** The file-based system's `hits.jsonl` at `.claude/guardrails/hits.jsonl`. Same JSONL format, new location, richer data (includes outcome, agent role, enforcement level).

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
        consume_override=(self._workflow_engine.consume_override_token
                          if self._workflow_engine else None),
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

- `workflows/` unreadable → fail closed (block everything)
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
| `hints/_types.py` | `claudechic/hints/_types.py` | `TriggerCondition` (Protocol), `HintLifecycle` (Protocol), `HintSpec` (frozen dataclass), `HintRecord`, lifecycle impls: `ShowOnce`, `ShowUntilResolved`, `ShowEverySession`, `CooldownPeriod(seconds)` |
| `hints/_engine.py` | `claudechic/hints/_engine.py` | `run_pipeline()` — 6-stage evaluation: activation → trigger → lifecycle → sort → budget → present |
| `hints/_state.py` | `claudechic/hints/_state.py` | `ProjectState`, `CopierAnswers`, `HintStateStore` (`.claude/hints_state.json`), `ActivationConfig` |
| `hints/__init__.py` | `claudechic/hints/__init__.py` | Public API: `evaluate()` entry point |

**Key types reused:**
```python
# From hints/_types.py (existing, moved to claudechic)

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
| `Rule` dataclass | **Modify in place** | guardrails/rules.py | Add required `namespace: str` field (no default). YAML uses `roles_only`/`roles_except` only — no `block`/`allow` compat. |
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
    namespace: str     # Required, no default: "_global" or workflow_id
    trigger: list[str]
    enforcement: str
    detect_pattern: re.Pattern[str] | None = None
    detect_field: str = "command"
    exclude_pattern: re.Pattern[str] | None = None
    message: str = ""
    roles_only: list[str] = field(default_factory=list)
    roles_except: list[str] = field(default_factory=list)
    phase_only: list[str] = field(default_factory=list)
    phase_except: list[str] = field(default_factory=list)
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
| `roles_only` | `roles_only` | `list[str]` | Rule fires only for these roles |
| `roles_except` | `roles_except` | `list[str]` | Rule never fires for these roles |
| `phase_only` | `phase_only` | `list[str]` | Rule fires only during these phases (qualified IDs) |
| `phase_except` | `phase_except` | `list[str]` | Rule never fires during these phases (qualified IDs) |
| `inject_value` | `inject_value` | `str` | Injection: what to inject (in `injections:` section) |
| `advance_checks[].type` | `CheckSpec.type` | `str` | Check type name |
| `advance_checks[].params` | `CheckSpec.params` | `dict` | Check-specific parameters |
| `hints[].lifecycle` | `HintDecl.lifecycle` | `str` | `show-once`, `show-until-resolved`, etc. |

### Manifest Types

```python
# claudechic/workflows/manifest_types.py

@dataclass(frozen=True)
class CheckSpec:
    id: str
    type: str  # "command-output-check", "file-exists-check", etc.
    params: dict[str, Any]
    on_failure: dict | None = None
    when: dict | None = None

@dataclass(frozen=True)
class HintDecl:
    id: str
    message: str
    lifecycle: str = "show-once"
    cooldown_seconds: int | None = None
    phase: str | None = None       # qualified phase ID, or None for unscoped
    namespace: str = ""

@dataclass(frozen=True)
class Phase:
    id: str                         # namespace-qualified
    file: str
    advance_checks: list[CheckSpec] = field(default_factory=list)
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
            roles_only=_as_list(entry.get("roles_only", [])),
            roles_except=_as_list(entry.get("roles_except", [])),
            phase_only=_as_list(entry.get("phase_only", [])),
            phase_except=_as_list(entry.get("phase_except", [])),
        )
```

### Files Summary

**CREATE:**
1. `claudechic/workflows/__init__.py`
2. `claudechic/workflows/loader.py`
3. `claudechic/workflows/engine.py`
4. `claudechic/workflows/checks.py`
5. `claudechic/workflows/agent_folders.py`
6. `claudechic/workflows/manifest_types.py`
7. `claudechic/guardrails/hooks.py`
8. `claudechic/guardrails/hits.py` — `HitRecord` dataclass, `HitLogger` (append-only JSONL writer), hit outcome tracking
9. `claudechic/hints/__init__.py`
10. `claudechic/hints/_types.py`
11. `claudechic/hints/_engine.py`
12. `claudechic/hints/_state.py`

**MODIFY:**
1. `claudechic/guardrails/rules.py` — Add `namespace` field; simplify `should_skip_for_phase()` signature; delete `load_rules()` and `read_phase_state()`
2. `claudechic/guardrails/__init__.py` — Add hooks.py exports
3. `claudechic/app.py` — Extract `_guardrail_hooks` body to `guardrails/hooks.py`; update `_merged_hooks`; add engine init with `persist_fn` wiring; pass `consume_override_token` to hooks; init `HitLogger`; add `_show_override_prompt` for `request_override` MCP; add PostCompact
4. `claudechic/mcp.py` — Add agent folder prompt assembly to `spawn_agent`; add `advance_phase`, `get_phase`, `request_override`, and `acknowledge_warning` MCP tools
5. `claudechic/chicsessions.py` — Add `workflow_state: dict | None = None` field to `Chicsession` dataclass

**DELETE (file-based system removal — after new system validated):**
1. `.claude/guardrails/generate_hooks.py` — Shell hook generator, replaced by closure-based hooks
2. `.claude/guardrails/hooks/` — Generated shell hook scripts
3. `.claude/guardrails/role_guard.py` — Ack token mechanism, replaced by `acknowledge_warning` MCP tool + one-time tokens
4. `.claude/guardrails/rules.yaml` — Replaced by `workflows/global.yaml` + workflow manifests
5. `.claude/guardrails/hits.jsonl` — Replaced by `workflows/.hits.jsonl`
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
  ├── guardrails/rules.py           (Rule — type hints only)
  ├── workflows/engine.py           (WorkflowEngine — phase state, override tokens, checks)
  ├── workflows/agent_folders.py    (assemble_phase_prompt)
  ├── chicsessions.py               (Chicsession — workflow_state field)
  └── hints/__init__.py             (run_pipeline — toast scheduling)

guardrails/hooks.py
  ├── guardrails/rules.py           (matches_trigger, should_skip_for_role, should_skip_for_phase)
  ├── guardrails/hits.py            (HitRecord, HitLogger)
  └── claude_agent_sdk.types        (HookMatcher)

guardrails/hits.py
  └── (json, pathlib, time only — no claudechic imports)

workflows/engine.py
  ├── workflows/manifest_types.py   (Phase, CheckSpec)
  ├── workflows/checks.py           (Check, CheckResult, check_failed_to_hint)
  ├── workflows/agent_folders.py    (assemble_agent_prompt)
  ├── guardrails/rules.py           (match_rule, matches_trigger, should_skip_*)
  └── claude_agent_sdk.types        (HookMatcher)

workflows/loader.py
  ├── workflows/manifest_types.py   (all types)
  ├── guardrails/rules.py           (Rule — for rule parsing)
  └── yaml

workflows/checks.py
  ├── workflows/manifest_types.py   (CheckSpec)
  └── hints/_types.py               (HintSpec — for CheckFailed adapter only)

workflows/agent_folders.py
  └── (pathlib only — no claudechic imports)

workflows/manifest_types.py
  ├── guardrails/rules.py           (Rule)
  └── (dataclasses, pathlib)

hints/_types.py
  └── (dataclasses only — no claudechic imports)

hints/_engine.py
  ├── hints/_types.py
  └── hints/_state.py

hints/_state.py
  └── (json, pathlib only)

hints/__init__.py
  ├── hints/_types.py
  ├── hints/_engine.py
  └── hints/_state.py
```

### Circular Import Verification

**No cycles exist:**
- `workflows/` → `guardrails/rules.py`: one-way
- `guardrails/hooks.py` → `guardrails/rules.py`: one-way
- `guardrails/hooks.py` → `guardrails/hits.py`: one-way
- `guardrails/hits.py` → (stdlib only): leaf node
- `workflows/checks.py` → `hints/_types.py`: one-way
- `hints/` never imports `workflows/` or `guardrails/`
- `guardrails/` never imports `workflows/` or `hints/`
- `app.py` imports from all three packages but none import `app.py`

### Seam Cleanliness

| Boundary | Clean? | Notes |
|---|---|---|
| `workflows/` → `guardrails/rules.py` | ✅ | Only imports `Rule` type and matching functions |
| `workflows/checks.py` → `hints/_types.py` | ✅ | Only imports `HintSpec` dataclass |
| `app.py` → `guardrails/hooks.py` | ✅ | Factory function, passes loader + hit_logger + callbacks |
| `app.py` → `workflows/engine.py` | ✅ | Engine API, passes persist_fn + confirm callback for ManualConfirm |
| `hints/` standalone | ✅ | Zero imports from workflows/ or guardrails/ |

---

## 13. Risk Register

### R1: NFS Performance on Every Tool Call

**Risk:** Multi-manifest loading (2+ files, 4+ NFS ops) on every `PreToolUse` hook invocation. Existing code logs warnings >5ms.

**Severity:** Medium.

**Mitigation:** Accept I/O cost for small YAML files (~0.5ms each). Regex cache from day one. Profile before adding complexity. If optimization needed: content hash cache → lazy section parsing (last resort).

### R2: Folder-Name Coupling

**Risk:** Folder name = identity ties together manifest filename, namespace, agent folder names, and role type. Renaming requires coordinating multiple locations.

**Severity:** Medium.

**Mitigation:** `workflow_id` in YAML is source of truth for namespace. Folder name is convention. Loader validates that folder names match manifest `workflow_id` at startup where possible.

### R3: Pull-Based Content Delivery Staleness

**Risk:** Phase transitions triggered by coordinator won't be noticed by other agents until they next query via `get_phase` MCP tool. Agents may operate under stale phase guidance.

**Severity:** Medium.

**Mitigation:** Design accepts this — pull-based is intentional. Agents receive phase context at spawn time. The coordinator uses `tell_agent` to notify agents of transitions. Agents can call `get_phase` MCP tool to re-check. PostCompact hook restores context after `/compact`.

### R4: ManualConfirm TUI Coupling

**Risk:** ManualConfirm is the only check requiring user interaction — breaks "checks are pure" mental model.

**Severity:** Low (mitigated by design).

**Mitigation:** Callback injection. ManualConfirm receives `AsyncConfirmCallback` at construction. Never sees TUI, app, or widgets. Swap test passes (CLI, test, web UI all work with different callbacks).

### ~~R5: `warn` Enforcement Infinite Loop~~ — RESOLVED

Eliminated by the unified one-time token mechanism. `warn` rules block the tool call; the agent calls `acknowledge_warning` MCP tool (stores token), then retries. The hook's `consume_override_token()` detects and consumes the token. Per-command scoping means no session state, no loop risk — each invocation is independently evaluated.

### R6: Silent Rule Loss on Parse Error

**Risk:** YAML syntax error in `global.yaml` silently drops all global rules. No protection, no notification.

**Severity:** Medium.

**Mitigation:** Prominent warning/hint when a manifest fails to parse. `LoadResult.errors` is always checked. Fail-closed only for `workflows/` directory unreadable. Individual manifest failures logged loudly.

### ~~R7: NFS Atomic Write Visibility~~ — REMOVED

Eliminated by moving persistence to chicsession. The session system handles its own I/O; the engine has no direct file writes.

### R8: hints/ Package Name Collision

**Risk:** `claudechic/hints/` vs template-side `hints/` — different systems, similar names.

**Severity:** Low.

**Mitigation:** Different import paths: `claudechic.hints` vs dynamic load of `{project}/hints`. No collision at Python level. Migration absorbs template-side infrastructure in one step.

### R9: PostCompact Hook SDK Protocol

**Risk:** The PostCompact hook return value format (`phase_context` key) is speculative. SDK may not support context injection this way.

**Severity:** Medium.

**Mitigation:** Verify SDK docs/source for PostCompact hook protocol before implementing. Fallback: write to a file that the SDK's system prompt mechanism reads, or use SystemMessage injection.

### ~~R10: Corrupted state.json Recovery~~ — REMOVED

Eliminated by moving persistence to chicsession. Session system manages its own integrity.

### R11: Single Point of Failure (Engine Process)

**Risk:** In-memory phase state is lost if the engine process crashes.

**Severity:** Low — if the app crashes, all agents die anyway (they run as subprocesses). Chicsession auto-save on every phase transition (~6 writes per workflow run) ensures session resume loses at most the in-progress phase transition.

**Mitigation:** `persist_fn` fires on every successful phase transition, saving `engine.to_session_state()` to `Chicsession.workflow_state`. On session resume, `WorkflowEngine.from_session_state()` restores the last persisted phase.

### R12: Agent `get_phase` MCP Tool Call Cost

**Risk:** Agents must make an MCP tool call to query the current phase, adding latency compared to a direct file read.

**Severity:** Low — agents rarely poll mid-task. Phase is injected into the agent prompt at spawn time. The `get_phase` MCP tool is only needed if an agent wants to re-check the phase after a transition it wasn't notified about.

**Mitigation:** Engine's `get_current_phase()` is an in-memory attribute lookup — the MCP call overhead is the transport only, no I/O.

---

## 14. Examples

### Example 1: Full `project_team.yaml` Manifest

```yaml
# workflows/project_team/project_team.yaml
workflow_id: project-team

rules:
  - id: pytest_output
    trigger: PreToolUse/Bash
    enforcement: deny
    phase_only: ["project-team:testing"]
    detect: { pattern: '(?:^|&&|\|\||;|\brun\s+)\s*pytest\b', field: command }
    message: "Redirect pytest output to .test_runs/"

  - id: close_agent
    trigger: PreToolUse/mcp__chic__close_agent
    enforcement: deny
    phase_only: ["project-team:specification"]
    roles_only: [implementer]
    message: "Close agent during specification — user approval required."

  - id: force_push_warn
    trigger: PreToolUse/Bash
    enforcement: warn
    detect: { pattern: 'git\s+push\s+.*--force', field: command }
    message: "Force push detected — verify this is intentional."

  - id: tool_usage_tracking
    trigger: PreToolUse/Bash
    enforcement: log
    detect: { pattern: '\b(curl|wget)\b', field: command }
    message: "Network tool usage detected."

phases:
  - id: vision
    file: coordinator/vision.md
  - id: setup
    file: coordinator/setup.md
  - id: specification
    file: coordinator/specification.md
  - id: implementation
    file: coordinator/implementation.md
    advance_checks:
      - type: manual-confirm
        question: "Are all implementation tasks complete?"
    hints:
      - message: "Focus on writing code, not running the full test suite"
        lifecycle: show-once
  - id: testing
    file: coordinator/testing.md
    advance_checks:
      - type: command-output-check
        command: "pixi run pytest --tb=short 2>&1 | tail -1"
        pattern: "passed"
  - id: signoff
    file: coordinator/signoff.md
```

**After loading, rule IDs become:**
- `project-team:pytest_output` (deny)
- `project-team:close_agent` (deny)
- `project-team:force_push_warn` (warn)
- `project-team:tool_usage_tracking` (log)

**Note:** `pip_block` is in `global.yaml` only (as `_global:pip_block`), not duplicated here.

**Phase IDs become:**
- `project-team:vision`, `project-team:setup`, ..., `project-team:signoff`

### Example 2: `global.yaml` with Setup Checks

```yaml
# workflows/global.yaml
rules:
  - id: pip_block
    trigger: PreToolUse/Bash
    enforcement: deny
    detect: { pattern: '\bpip\s+install\b', field: command }
    message: "Use pixi, not pip."

checks:
  - id: github_auth
    type: command-output-check
    command: "git ls-remote https://github.com/sprustonlab/claudechic.git HEAD 2>&1 | head -1"
    pattern: "[0-9a-f]{40}"
    on_failure:
      message: "GitHub authentication failed. Run: gh auth login"
      severity: warning
      lifecycle: show-until-resolved

  - id: cluster_ssh
    type: command-output-check
    when: { copier: use_cluster }
    command: "ssh -o ConnectTimeout=5 -o BatchMode=yes ${cluster_ssh_target} hostname 2>&1"
    pattern: "^[a-zA-Z]"
    on_failure:
      message: "Cannot SSH to cluster. Run: ssh-copy-id ${cluster_ssh_target}"
      severity: warning
      lifecycle: show-until-resolved
```

**After loading, IDs become:** `_global:pip_block`, `_global:github_auth`, `_global:cluster_ssh`.

**At startup:** Engine runs all setup checks (no short-circuit). `github_auth` runs always. `cluster_ssh` runs only if `use_cluster` is truthy in copier answers. Failures produce hints via CheckFailed adapter with `show-until-resolved` lifecycle.

### Example 3: Phase Transition Walkthrough

Coordinator decides implementation is done, calls the `advance_phase` MCP tool:

1. **MCP tool `advance_phase` invoked** — engine determines current phase is `project-team:implementation`, next is `project-team:testing`.

2. **Engine reads advance_checks for `implementation` phase:**
   ```yaml
   advance_checks:
     - type: manual-confirm
       question: "Are all implementation tasks complete?"
   ```

3. **Engine builds check:** `ManualConfirm(question="Are all implementation tasks complete?", confirm_fn=<callback>)`

4. **Engine calls `check.check()`:**
   - Callback fires → SelectionPrompt appears in TUI
   - User sees: `✅ Check: Are all implementation tasks complete?` with Yes/No options

5. **User selects "Yes":**
   - `CheckResult(passed=True, evidence="User confirmed")`
   - All checks passed (only one in this case)

6. **Engine updates in-memory state + persists via chicsession:**
   ```python
   self._current_phase = "project-team:testing"  # In-memory — authoritative
   self._persist_fn()  # → session.workflow_state = engine.to_session_state(); manager.save(session)
   ```

7. **MCP tool returns `{"success": true, "phase": "testing"}`** — coordinator notifies other agents via `tell_agent`. Next hook evaluation calls `engine.get_current_phase()` (in-memory) and evaluates phase-scoped rules against `project-team:testing`.

8. **If user had selected "No":**
   - `CheckResult(passed=False, evidence="User declined")`
   - Short-circuit: phase transition blocked
   - If `on_failure` configured, hint fires via CheckFailed adapter
   - MCP tool returns `{"success": false, "reason": "Advance checks failed"}`
   - Coordinator remains in `implementation` phase

### Example 4: Phase-Scoped Rule Evaluation

Rule from manifest:
```yaml
- id: pytest_output
  trigger: PreToolUse/Bash
  enforcement: deny
  phase_only: ["project-team:testing"]
  detect: { pattern: '(?:^|&&|\|\||;|\brun\s+)\s*pytest\b', field: command }
  message: "Redirect pytest output to .test_runs/"
```

**Current phase: `project-team:implementation`** — agent runs `pytest`:

1. Trigger match: `PreToolUse/Bash` ✅
2. Role skip: no `roles_only`/`roles_except` → no skip
3. Phase skip: `phase_only: ["project-team:testing"]` — current phase is `project-team:implementation`, NOT in `phase_only` → **skip** ✅
4. Rule does NOT fire. `pytest` runs normally.

**Current phase: `project-team:testing`** — agent runs `pytest`:

1. Trigger match: `PreToolUse/Bash` ✅
2. Role skip: no restrictions → no skip
3. Phase skip: `phase_only: ["project-team:testing"]` — current phase IS in `phase_only` → **does not skip**
4. Detect match: `pytest` matches pattern ✅
5. Hit logged: `HitRecord(rule_id="project-team:pytest_output", outcome="blocked", ...)`
6. Enforcement: `deny` → `{"decision": "block", "reason": "Redirect pytest output to .test_runs/\nTo request user override: request_override(rule_id=\"project-team:pytest_output\", tool_name=\"Bash\", tool_input={...})"}`

Rule for `close_agent` with `phase_only` and `roles_only`:
```yaml
- id: close_agent
  trigger: PreToolUse/mcp__chic__close_agent
  enforcement: deny
  phase_only: ["project-team:specification"]
  roles_only: [implementer]
```

**Agent: implementer, phase: specification** — calls `close_agent`:
1. Trigger: `PreToolUse/mcp__chic__close_agent` ✅
2. Role: `roles_only: [implementer]` — agent IS implementer → does not skip
3. Phase: `phase_only: ["project-team:specification"]` — current phase IS in `phase_only` ��� does not skip
4. No detect pattern → fires
5. Enforcement: `deny` → block with message: "Close agent during specification — user approval required.\n\nTo request user override: request_override(rule_id=\"project-team:close_agent\", tool_name=\"mcp__chic__close_agent\", tool_input={...})"
6. Agent calls `request_override(rule_id="project-team:close_agent", tool_name="mcp__chic__close_agent", tool_input={...})` → user sees exact command in SelectionPrompt → if approved, one-time token stored → agent retries exact same command → token consumed → allowed through

**Agent: coordinator, phase: specification** — calls `close_agent`:
1. Trigger: ✅
2. Role: `roles_only: [implementer]` — agent is coordinator, NOT in roles_only → **skip** ✅
3. Rule does NOT fire.

### Example 5: Hook Closure Code

```python
# At agent spawn time (e.g., spawning an "implementer" agent):

# 1. app._make_options() calls _merged_hooks(agent_type="implementer")
# 2. _merged_hooks calls create_guardrail_hooks() (evaluates all rules, all enforcement levels):

hooks = create_guardrail_hooks(
    loader=app._manifest_loader,       # Shared instance (parsers registered once at app init)
    hit_logger=app._hit_logger,        # Shared instance (audit trail)
    agent_role="implementer",          # Captured in closure
    get_phase=app._workflow_engine.get_current_phase,  # In-memory lookup, no I/O
    consume_override=app._workflow_engine.consume_override_token,  # Per-command tokens
)

# 3. The returned hooks dict contains a PreToolUse hook.
# 4. On every tool call by this agent, the hook closure:
#    a. Calls loader.load() — reads manifests fresh (no mtime cache — NFS safe)
#    b. Evaluates each rule with agent_role="implementer"
#    c. Rules with roles_except=["implementer"] are skipped
#    d. Rules with roles_only=["implementer"] always fire for this agent
#    e. Phase from get_phase() — in-memory engine attribute, no file I/O

# The closure captures loader + hit_logger + agent_role + get_phase + consume_override.
# Different agents get different closures with different roles,
# but share the same loader, hit_logger, and engine callbacks.
```

### Example 6: Manifest Discovery

Given this file tree:
```
workflows/
  global.yaml
  project_team/
    project_team.yaml
    coordinator/
      identity.md
      ...
  another_workflow/
    another_workflow.yaml
  .hidden/
    hidden.yaml
  project_team/
    notes.txt                 # Not a manifest (wrong name)
```

`discover_manifests(Path("workflows/"))` returns:
```python
[
    Path("workflows/global.yaml"),              # 1. Global first
    Path("workflows/another_workflow/another_workflow.yaml"),  # 2. Alphabetical
    Path("workflows/project_team/project_team.yaml"),         # 3. Alphabetical
]
```

**Ignored:**
- `.hidden/` — starts with `.`
- `notes.txt` — not a manifest (filename doesn't match parent directory)

**Namespaces assigned:**
- `global.yaml` → `_global`
- `another_workflow.yaml` → value of `workflow_id` field, fallback to `another_workflow`
- `project_team.yaml` → value of `workflow_id` field (e.g. `project-team`), fallback to `project_team`

### Example 7: Phase Reference Validation

```yaml
# workflows/project_team/project_team.yaml
workflow_id: project-team

rules:
  - id: bad_ref
    trigger: PreToolUse/Bash
    enforcement: deny
    phase_only: ["project-team:nonexistent"]    # ← references unknown phase
    message: "This rule has a bad phase reference"

  - id: good_ref
    trigger: PreToolUse/Bash
    enforcement: deny
    phase_only: ["project-team:testing"]         # ← valid phase reference
    message: "This rule is correctly scoped"

phases:
  - id: implementation
    file: coordinator/implementation.md
  - id: testing
    file: coordinator/testing.md
```

**After loading:**
- Known phases: `project-team:implementation`, `project-team:testing`
- Rule `project-team:bad_ref` has `phase_only: ["project-team:nonexistent"]`
- Validation produces:
  ```
  LoadError(source="validation", section="rules", item_id="project-team:bad_ref",
            message="unknown phase ref 'project-team:nonexistent' in phase_only")
  ```
- The rule still loads (fail-open) but `phase_only` filter is vacuously false for `project-team:nonexistent` — the rule never activates on phase grounds
- Rule `project-team:good_ref` validates cleanly

---

## Scope Boundaries

### In Scope (Build)
- Unified manifest loader with typed section parsers (ManifestSection[T])
- Workflow engine (phase transitions, advance_checks gates, state persistence)
- Check protocol with 4 built-in types and CheckFailed → hints adapter
- Agent folder structure and prompt assembly
- `workflows/global.yaml` with setup checks
- COORDINATOR.md content split into agent folder
- `/compact` recovery hook (PostCompact)
- Phase-scoped rule evaluation
- Hints infrastructure absorbed from template-side into `claudechic/hints/`

### Explicitly Out of Scope
- **CompoundCheck** — OR semantics for checks
- **Content focus guards** — phase-aware read guards
- **Multi-workflow** — multiple workflows active simultaneously
- **`ShowUntilPhaseComplete`** — hint lifecycle type
- **`regex_miss` detect type** — negated pattern matching (rule fires when pattern does NOT match). Can be added later via a `negate: true` field on `detect`. Current spec supports `regex_match` (detect pattern present) and `always` (detect pattern absent).
- **`spawn_type_defined` detect type** — validates that the spawned agent type exists in agent folders. Can be added as a custom detect type once the detect system is extensible.

---

See [APPENDIX_FUTURE_MCP.md](APPENDIX_FUTURE_MCP.md) for potential future MCP tools (`get_workflow_info`, `set_phase`, `list_phases`, `list_checks`, `run_check`).
