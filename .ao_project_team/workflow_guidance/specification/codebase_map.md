# Codebase Map — Existing claudechic Code for Workflow Guidance System

**Author:** Researcher
**Date:** 2026-04-05
**Scope:** Files in `submodules/claudechic/claudechic/` that the Workflow Guidance System spec must modify or extend.

---

## 1. guardrails/rules.py — Rule Loading, Matching, Data Structures

### Data Structures

```python
@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    trigger: list[str]           # e.g. ["PreToolUse/Bash"]
    enforcement: str             # "deny" | "warn" | "log" | "user_confirm"
    detect_pattern: re.Pattern[str] | None = None
    detect_field: str = "command"
    exclude_pattern: re.Pattern[str] | None = None
    message: str = ""
    block_roles: list[str] = field(default_factory=list)
    allow_roles: list[str] = field(default_factory=list)
    phase_block: list[str] = field(default_factory=list)
    phase_allow: list[str] = field(default_factory=list)
```

**Key observation:** Rule already has `phase_block`, `phase_allow`, `block_roles`, `allow_roles` fields. The dataclass is frozen and immutable.

### Functions

| Function | Signature | Purpose |
|----------|-----------|---------|
| `load_rules(rules_path: Path) -> list[Rule]` | Reads a single YAML file, parses `data["rules"]` list | Returns `[]` if file missing. Parses trigger (str or list), detect pattern, exclude pattern, role restrictions, phase restrictions. |
| `matches_trigger(rule: Rule, tool_name: str) -> bool` | Checks trigger format `"PreToolUse/Bash"` | Splits on `/`, compares tool name. Bare `"PreToolUse"` matches all tools. |
| `match_rule(rule: Rule, tool_name: str, tool_input: dict) -> bool` | Pattern matching against tool input field | Checks exclude first, then detect. No pattern = always matches. |
| `should_skip_for_role(rule: Rule, agent_role: str \| None) -> bool` | Role-based filtering | `block_roles` = only fires for listed roles; `allow_roles` = never fires for listed roles. |
| `should_skip_for_phase(rule: Rule, phase_state: dict \| None) -> bool` | Phase-based filtering | Reads `current_phase` from dict. Checks `phase_block` and `phase_allow`. |
| `read_phase_state(phase_state_path: Path) -> dict \| None` | Reads JSON file | Returns None on missing/corrupt. |

### Discovery & Loading

- **Single file only:** `load_rules()` takes one `Path`, reads one YAML file.
- **No namespace prefixing:** Rule IDs are used as-is from YAML.
- **No validation:** No duplicate ID check, no regex validation, no phase reference validation.
- **YAML key mapping:** `block` → `block_roles`, `allow` → `allow_roles` (note: YAML keys are `block`/`allow`, not `block_roles`/`allow_roles`).

### What the New Spec Changes

1. **Multi-source loading:** Currently loads from one `rules_path`. Must load from `workflows/global.yaml` + all `workflows/*/workflow.yaml` manifest files and merge rules.
2. **Namespace prefixing:** Loader must auto-prefix IDs: `_global:pip_block`, `project_team:close_agent`.
3. **Startup validation:** Add duplicate ID detection, regex compilation validation, phase reference validation against known phases.
4. **Fail-open per-manifest:** Malformed manifest → skip it, load the rest. `workflows/` unreadable → fail closed.
5. **`load_rules()` becomes internal** to a new unified manifest loader, or is refactored to accept pre-parsed rule dicts.

---

## 2. guardrails/hits.py — Hit Logging

**File does not exist.** The guardrails directory contains only:
- `__init__.py` (re-exports from rules.py)
- `rules.py`
- `test_poc.py`

The `__init__.py` exports: `Rule`, `load_rules`, `matches_trigger`, `match_rule`, `should_skip_for_role`, `should_skip_for_phase`.

### What the New Spec Changes

- Hit logging is mentioned in the USER_PROMPT but there's no existing implementation to modify. This would be a new module if needed.

---

## 3. app.py — Hook Closures, SelectionPrompt, Confirmation Flow

### `_guardrail_hooks(self, agent_role: str | None = None)` (line 633)

Creates a `PreToolUse` hook closure that:
1. **Loads rules fresh every call** — `load_rules(rules_path)` with no caching
2. **Reads phase state** from `rules_path.parent / "phase_state.json"` (i.e., `.claude/guardrails/phase_state.json`)
3. **Evaluates in order:** trigger match → role skip → phase skip → pattern match → enforcement
4. **Enforcement actions:**
   - `deny` → returns `{"decision": "block", "reason": rule.message}`
   - `user_confirm` → calls `await app._show_guardrail_confirm(rule)` → blocks/allows
   - `warn` → returns `{"decision": "block", ...}` (same as deny currently)
   - `log` → falls through (allowed, but logged to stderr)
5. **Fail-open on exception** — catches all errors, returns `{}`
6. **Performance logging** — logs timing to stderr when >5ms

**Rules path discovery:** Hardcoded to `self._cwd / ".claude/guardrails/rules.yaml"`.

**Phase state path:** Hardcoded to `rules_path.parent / "phase_state.json"` = `.claude/guardrails/phase_state.json`.

**Hook signature:**
```python
async def evaluate(
    hook_input: dict,     # has tool_name, tool_input, permission_mode
    match: str | None,    # unused
    ctx: object,          # unused
) -> dict:                # {} = allow, {"decision": "block", "reason": ...} = block
```

### `_show_guardrail_confirm(self, rule: Any) -> bool` (line 720)

Shows a `SelectionPrompt` with "Allow" / "Deny" options. Uses `async with self._show_prompt(prompt)` context manager pattern. Returns `True` if user selects "allow", `False` on "deny" or error.

### `_show_prompt(self, prompt, agent: Agent | None = None)` (line 490)

Async context manager that:
1. Associates prompt with an agent via `self._active_prompts[agent.id]`
2. Mounts prompt widget as sibling of `#input-container`
3. Hides input container while prompt is visible
4. Restores input on exit (even if agent switched)
5. Handles multi-agent: prompt only visible when its agent is active

**This is the mechanism ManualConfirm checks would use.** The spec says ManualConfirm uses `SelectionPrompt` with a confirmation callback — this `_show_prompt` pattern is the existing infrastructure.

### `_merged_hooks(self, agent_type: str | None = None)` (line 746)

Merges plan-mode hooks with guardrail hooks into a single `dict[HookEvent, list[HookMatcher]]`. This is called from `_make_options()`.

### `_make_options(...)` (line 754)

Creates `ClaudeAgentOptions` for SDK connection. Key parameters:
- `agent_name`, `agent_type` → set as env vars `CLAUDE_AGENT_NAME`, `CLAUDE_AGENT_ROLE`
- `hooks=self._merged_hooks(agent_type=agent_type)` — hooks are created at option construction time
- `cwd`, `resume`, `model`, MCP servers, etc.

**Critical:** `agent_type` is passed through to `_guardrail_hooks()` where it's captured in the closure as `agent_role`. This is how role-based rule filtering works.

### `_run_hints(self, *, is_startup: bool, budget: int)` (line 1059)

Loads `hints/` package from `self._cwd / "hints"` via `importlib`. Calls `mod.evaluate(send_notification, project_root, session_count, is_startup, budget)`. Fire-and-forget, never crashes.

### `_periodic_hints(self)` (line 1095)

Runs `_run_hints(is_startup=False, budget=1)` every 2 hours (set up in `on_mount`).

### What the New Spec Changes

1. **`_guardrail_hooks()`:** Rules path changes from `.claude/guardrails/rules.yaml` to discovering and merging all manifests under `workflows/`. Phase state path changes to `workflows/<workflow>/state.json`.
2. **`_guardrail_hooks()` closure:** Must accept workflow engine context (active workflows, their phases) rather than reading a single `phase_state.json`. Evaluation adds: match trigger → check role → **check phase with qualified IDs** → match pattern → enforce.
3. **`_show_guardrail_confirm()`:** No major changes — works as-is for `user_confirm` enforcement. ManualConfirm checks would use the same `_show_prompt` + `SelectionPrompt` pattern.
4. **`_make_options()`:** `agent_type` is already wired. May need to also pass workflow context (which workflow the agent belongs to) for phase-scoped evaluation.
5. **`_run_hints()`:** The new system moves hints into YAML manifests. This method either becomes the bridge (loads hints from manifests and feeds them to the existing pipeline) or is replaced by a workflow engine startup routine.
6. **New: PostCompact hook** — Currently no PostCompact hook exists. Must add one that re-injects phase context after `/compact`.

---

## 4. hints/ — Trigger Conditions, Lifecycle, Pipeline, Project State, HintSpec

**Important:** The `hints/` directory does NOT live in claudechic. It lives at the **project root** (`AI_PROJECT_TEMPLATE/hints/`). It's a template-side package loaded dynamically by claudechic's `_run_hints()`.

### Files

| File | Purpose |
|------|---------|
| `__init__.py` | Public API: `evaluate()` entry point. Builds ProjectState, loads HintStateStore, runs pipeline. |
| `_types.py` | Core protocols and data structures: `TriggerCondition`, `HintLifecycle`, `HintSpec`, `HintRecord`, plus lifecycle implementations. |
| `_engine.py` | `run_pipeline()` — evaluation pipeline: activation → trigger → lifecycle → sort → budget → present. |
| `_state.py` | `ProjectState`, `CopierAnswers`, `HintStateStore`, `ActivationConfig`. State persistence at `.claude/hints_state.json`. |
| `hints.py` | Built-in hint registry: 6 trigger classes, 3 combinators, 7 hint specs, `get_hints()` API. |

### Key Types

**`TriggerCondition` (Protocol):**
```python
class TriggerCondition(Protocol):
    def check(self, state: ProjectState) -> bool: ...
    @property
    def description(self) -> str: ...
```

**`HintLifecycle` (Protocol):**
```python
class HintLifecycle(Protocol):
    def should_show(self, hint_id: str, state: HintStateStore) -> bool: ...
    def record_shown(self, hint_id: str, state: HintStateStore) -> None: ...
```

**Lifecycle implementations:** `ShowOnce`, `ShowUntilResolved`, `ShowEverySession`, `CooldownPeriod(seconds)`.

**`HintSpec`:**
```python
@dataclass(frozen=True)
class HintSpec:
    id: str
    trigger: TriggerCondition
    message: str | Callable[[ProjectState], str]
    severity: Literal["info", "warning"] = "info"
    priority: int = 3
    lifecycle: HintLifecycle = ShowUntilResolved()
```

**`ProjectState`:**
```python
@dataclass(frozen=True)
class ProjectState:
    root: Path
    copier: CopierAnswers
    session_count: int | None = None
    # Methods: path_exists(), dir_is_empty(), file_contains(), count_files_matching()
```

**`HintStateStore`:** Manages `.claude/hints_state.json`. Tracks per-hint: `times_shown`, `last_shown_ts`, `dismissed`, `taught_commands`. Atomic writes via temp-then-rename.

**`ActivationConfig`:** Global enable/disable + per-hint disable. Cheapest pipeline filter (dict lookup).

### `run_pipeline()` Signature

```python
async def run_pipeline(
    send_notification: Callable[..., Any],
    project_state: ProjectState,
    state_store: HintStateStore,
    activation: ActivationConfig,
    hints: Sequence[HintSpec],
    budget: int = 2,
    *,
    is_startup: bool = True,
) -> None:
```

Pipeline stages: activation gate → trigger check → lifecycle gate → sort by (priority, last_shown_ts, definition_order) → budget limit → resolve messages → schedule toasts with delays.

### `evaluate()` Entry Point

```python
async def evaluate(
    send_notification: Callable[..., Any],
    project_root: Path,
    session_count: int | None = None,
    **kwargs: Any,
) -> None:
```

Builds `ProjectState`, loads `HintStateStore`, creates `ActivationConfig`, gets hints from `hints.py`, runs pipeline.

### What the New Spec Changes

1. **Hints from YAML manifests:** The spec says hints are declared in manifest YAML (under phases and at top level). The existing Python `HintSpec`/`run_pipeline()` infrastructure is reused, but hint definitions come from manifest parsing rather than `hints.py`.
2. **`CheckFailed` adapter:** A new adapter bridges check failures to `HintSpec` objects, feeding them into the existing `run_pipeline()`.
3. **Phase-scoped hints:** Hints declared under `phases[].hints` in manifests are scoped to that phase. The manifest loader creates `HintSpec` objects with appropriate triggers.
4. **`on_failure` in checks:** Setup checks in `global.yaml` have `on_failure.lifecycle: show-until-resolved` — maps directly to existing `ShowUntilResolved`.
5. **`ProjectState` may need extension** to include current phase information for phase-aware triggers.
6. **The template-side `hints/` package continues to work** — the new system adds manifest-declared hints alongside it.

---

## 5. Agent Spawn Flow

### How Agents Are Spawned Today

**MCP `spawn_agent` tool** (mcp.py line 155):
```python
async def spawn_agent(args: dict[str, Any]) -> dict[str, Any]:
    # args: name, path, prompt, model, type, requires_answer
    agent_type = args.get("type")  # Optional role type
    agent = await _app.agent_mgr.create(
        name=name, cwd=path, switch_to=False, model=model,
        agent_type=agent_type,  # Passed through to _make_options
    )
```

**AgentManager.create()** (agent_manager.py line 120):
```python
async def create(self, name, cwd, *, worktree=None, resume=None,
                 switch_to=True, model=None, agent_type=None) -> Agent:
    options = self._options_factory(
        cwd=cwd, resume=resume, agent_name=agent.name, model=model,
        agent_type=agent_type,
    )
    await agent.connect(options, resume=resume)
```

**`_options_factory` = `ChatApp._make_options()`** — constructs `ClaudeAgentOptions` with hooks.

**Flow:** `spawn_agent` MCP tool → `AgentManager.create()` → `ChatApp._make_options(agent_type=...)` → `_merged_hooks(agent_type=...)` → `_guardrail_hooks(agent_role=agent_type)` captures role in closure.

**`agent_type` propagation:** MCP `type` arg → `AgentManager.create(agent_type=)` → `_make_options(agent_type=)` → env var `CLAUDE_AGENT_ROLE` + closure capture in guardrail hook.

### What the New Spec Changes

- Agent spawn must also pass **workflow context** (which workflow, current phase) so hooks can do phase-scoped evaluation.
- The `agent_type` maps to an **agent folder** in `workflows/<workflow>/<agent_type>/`. The workflow engine uses this to assemble the prompt (identity.md + phase file).

---

## 6. state.json and Phase State

### Current State Mechanism

- **Phase state path:** `.claude/guardrails/phase_state.json` (hardcoded in `_guardrail_hooks`)
- **Read by:** `read_phase_state(phase_state_path)` → returns `dict | None` with `current_phase` key
- **Written by:** Not written anywhere in claudechic — presumably written externally or by another tool.
- **Format:** `{"current_phase": "project-team:testing"}`

### What the New Spec Changes

- State moves to `workflows/<workflow>/state.json` (e.g., `workflows/project_team/state.json`).
- Written atomically by the workflow engine (temp file + rename).
- Read on every tool call (no mtime caching — NFS unreliable on HPC).
- Contains current phase, phase history, and potentially advance check results.

---

## 7. rules.yaml Discovery

### Current Discovery

Hardcoded single path:
```python
rules_path = Path(self._cwd) / ".claude/guardrails/rules.yaml"
```

### What the New Spec Changes

- Discovery scans `workflows/` at the project root (= `self._cwd / "workflows/"`)
- Loads `global.yaml` (always active, no phases)
- Loads each `workflows/<name>/<name>.yaml` manifest
- Each manifest can contain `rules:`, `phases:`, `checks:`, `hints:` sections
- A unified loader distributes sections to typed parsers (`ManifestSection[T]`)
- Two loading modes: **full load** (startup, phase transitions) and **rules-only load** (every tool call for guardrail evaluation)

---

## 8. Summary: Key Integration Points

| What | Current Location | New Location / Change |
|------|-----------------|----------------------|
| Rule loading | `guardrails/rules.py:load_rules()` from single YAML | Unified manifest loader from `workflows/*.yaml` |
| Rule path | `.claude/guardrails/rules.yaml` | `workflows/global.yaml` + `workflows/*/workflow.yaml` |
| Phase state | `.claude/guardrails/phase_state.json` | `workflows/<workflow>/state.json` |
| Hook creation | `app.py:_guardrail_hooks()` | Same method, but reads from manifest loader |
| Agent type flow | MCP spawn → AgentManager → _make_options → hook closure | Same, plus workflow engine maps type to agent folder |
| Confirmation UI | `_show_guardrail_confirm()` via `SelectionPrompt` | Reused for `user_confirm` and `ManualConfirm` checks |
| Hints | Template-side `hints/` package, loaded by `_run_hints()` | Manifest-declared hints fed to existing `run_pipeline()` |
| PostCompact hook | Does not exist | New hook to re-inject phase context |
| Startup validation | None | New: duplicate IDs, regex validation, phase reference validation |
| Namespace prefixing | None | New: `_global:` and `<workflow>:` auto-prefixing |
| Manifest loader | Does not exist | New module: typed section parsers (`ManifestSection[T]`) |
| Workflow engine | Does not exist | New module: phase transitions, advance checks, state persistence |
| Check protocol | Does not exist | New module: 4 check types + `CheckFailed` → hints adapter |

---

## 9. Files That Need New Modules

These don't exist yet and must be created:

1. **`claudechic/workflows/loader.py`** — Unified manifest discovery, loading, namespace prefixing, validation
2. **`claudechic/workflows/engine.py`** — Workflow engine: phase transitions, advance checks, state.json persistence
3. **`claudechic/workflows/checks.py`** — Check protocol: CommandOutputCheck, FileExistsCheck, FileContentCheck, ManualConfirm
4. **`claudechic/workflows/__init__.py`** — Public API

## 10. Files That Need Modification

1. **`guardrails/rules.py`** — `load_rules()` may be refactored to accept pre-parsed dicts from the manifest loader, or the manifest loader builds `Rule` objects directly. Add startup validation.
2. **`app.py`** — `_guardrail_hooks()` reads from manifest loader instead of single file. `_make_options()` may pass workflow context. Add PostCompact hook to `_merged_hooks()`. `_run_hints()` integrates manifest-declared hints.
3. **`mcp.py`** — `spawn_agent` passes workflow context alongside `agent_type`.
4. **`agent_manager.py`** — `create()` may need workflow context parameter.
