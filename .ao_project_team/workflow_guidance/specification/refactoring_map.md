# Refactoring Map: Workflow Guidance System

## Status Quo Summary

**Existing code in claudechic:**
- `guardrails/rules.py` — `Rule` dataclass, `load_rules()`, matching/filtering functions (197 lines)
- `guardrails/__init__.py` — Public re-exports of rules.py (20 lines)
- `guardrails/test_poc.py` — Test file (the only other file in guardrails/)
- `guardrails/hits.py` — **Does NOT exist** (referenced in task but missing from codebase)
- `hints/` — **Does NOT exist as a claudechic package.** The hints system in `app.py` (lines 1059-1098) dynamically loads a `hints/` package from the *project root* (`AI_PROJECT_TEMPLATE/hints/`), not from claudechic. This is a pure template-side module.
- `app.py` — 3341 lines. Contains hook closures (`_guardrail_hooks`, `_plan_mode_hooks`, `_merged_hooks`), TUI confirmation (`_show_guardrail_confirm`), hint evaluation (`_run_hints`), and agent creation (`_make_options`).
- `compact.py` — Session compaction (378 lines). Pure file manipulation, no hooks. No `PostCompact` hook exists yet.
- `agent.py` — Agent class. Receives `ClaudeAgentOptions` (including hooks) via `connect()` at line 284. Agent has no knowledge of guardrails or workflows.
- `agent_manager.py` — Creates agents via `create()` (line 120). Passes `agent_type` to `_options_factory` which flows to `_make_options` in app.py. No workflow awareness.
- `mcp.py` — `spawn_agent` (line 177) accepts `type` param, passes as `agent_type` to `agent_manager.create()`.

**Existing template-side hints/ package** (at project root, NOT in claudechic):
- `hints/__init__.py` — Public API: `evaluate()` entry point
- `hints/_types.py` — `TriggerCondition` (Protocol), `HintLifecycle` (Protocol), `HintSpec` (dataclass), `HintRecord`, lifecycle impls: `ShowOnce`, `ShowUntilResolved`, `ShowEverySession`, `CooldownPeriod(seconds)`
- `hints/_engine.py` — `run_pipeline()`: activation → trigger → lifecycle → sort → budget → present
- `hints/_state.py` — `ProjectState`, `CopierAnswers`, `HintStateStore`, `ActivationConfig`. State at `.claude/hints_state.json`
- `hints/hints.py` — Built-in hint registry: 6 trigger classes, 3 combinators, 7 hint specs

**Key YAML mapping quirk in rules.py:** The YAML keys `block`/`allow` map to dataclass fields `block_roles`/`allow_roles` (rules.py lines 73-79). The new manifest format uses `block_roles`/`allow_roles` directly in YAML to avoid this confusion.

**Phase state currently at:** `.claude/guardrails/phase_state.json` (hardcoded in `_guardrail_hooks` at app.py:648). Not written anywhere in claudechic — written externally. Must move to `workflows/<workflow>/state.json`.

---

## 1. Target File Structure

```
claudechic/
  workflows/                    # NEW package
    __init__.py                 # Public API: load_manifests, WorkflowEngine, etc.
    loader.py                   # ManifestSection[T] dispatcher, manifest discovery
    engine.py                   # Phase transitions, state persistence, advance_checks
    checks.py                   # Check protocol + 4 built-in types
    agent_folders.py            # Prompt assembly from identity + phase files
    manifest_types.py           # Parsed types: WorkflowManifest, Phase, CheckSpec, HintDecl

  guardrails/                   # EXISTING, refactored
    __init__.py                 # MODIFIED — new exports for hooks.py
    rules.py                    # MODIFIED — Rule dataclass gains namespace field; load_rules() replaced
    hooks.py                    # NEW — hook closure creation (EXTRACTED from app.py)

  hints/                        # NEW claudechic package (NOT the project-side hints/)
    __init__.py                 # Public API: evaluate hints
    _types.py                   # HintSpec, HintLifecycle, TriggerCondition
    _engine.py                  # Pipeline runner (run_pipeline)
    _state.py                   # State persistence (shown hints, cooldowns)
    hints.py                    # Discovery and evaluation coordinator
```

**Critical distinction:** The project-side `hints/` directory (loaded dynamically at app.py:1059-1093) is a *different system* from the new `claudechic/hints/` package. The new package provides infrastructure for manifest-declared hints. The old project-side hints system can coexist or be migrated later.

---

## 2. Migration Table

### guardrails/rules.py

| Existing Code | Current Location | Line(s) | Action | New Location | Interface Changes |
|---|---|---|---|---|---|
| `Rule` dataclass | guardrails/rules.py | 19-33 | **Modify in place** | guardrails/rules.py | Add required `namespace: str` field (no default). YAML uses `block_roles`/`allow_roles` only. |
| `load_rules(rules_path)` | guardrails/rules.py | 36-105 | **Replace** | workflows/loader.py | Old `load_rules()` deleted. All rule loading goes through ManifestLoader. RulesParser implements ManifestSection[Rule]. |
| `matches_trigger()` | guardrails/rules.py | 108-123 | **No change** | guardrails/rules.py | Unchanged. |
| `match_rule()` | guardrails/rules.py | 126-145 | **No change** | guardrails/rules.py | Unchanged. |
| `should_skip_for_role()` | guardrails/rules.py | 148-162 | **No change** | guardrails/rules.py | Unchanged. |
| `should_skip_for_phase()` | guardrails/rules.py | 165-185 | **Modify** | guardrails/rules.py | Currently reads `phase_state: dict`. Change to accept `current_phase: str` directly (engine provides the string, not raw dict). |
| `read_phase_state()` | guardrails/rules.py | 188-197 | **Move** | workflows/engine.py | This is workflow state reading, not rule logic. Engine owns state.json. |

### guardrails/__init__.py

| Existing Code | Current Location | Action | New Location | Interface Changes |
|---|---|---|---|---|
| Re-exports of rules.py | guardrails/__init__.py | **Modify** | guardrails/__init__.py | Add exports from new hooks.py: `create_guardrail_hooks` |

### app.py Hook Code

| Existing Code | Current Location | Line(s) | Action | New Location | Interface Changes |
|---|---|---|---|---|---|
| `_guardrail_hooks()` | app.py | 633-718 | **Extract** | guardrails/hooks.py | See §3 for details |
| `_show_guardrail_confirm()` | app.py | 720-744 | **Stays** | app.py | No change — this is TUI code |
| `_plan_mode_hooks()` | app.py | 598-631 | **Stays** | app.py | No change — plan mode is app-level concern |
| `_merged_hooks()` | app.py | 746-752 | **Modify** | app.py | Add workflow hooks to the merge |
| `_make_options()` | app.py | 754-803 | **Modify** | app.py | No signature change, but hooks= now includes workflow hooks |
| `_run_hints()` | app.py | 1059-1098 | **Stays** | app.py | This loads project-side hints. The new claudechic hints system is separate. Eventually _run_hints may delegate to the new system, but that's a later migration. |

---

## 3. What Moves Out of app.py

### Extracted: `_guardrail_hooks()` → `guardrails/hooks.py`

**Current code** (app.py:633-718): A method on `ChatApp` that creates a closure capturing `self` (the app) and `agent_role`. The closure imports from `guardrails.rules`, loads rules from a fixed path, evaluates them, and for `user_confirm` calls `app._show_guardrail_confirm(rule)`.

**Problem:** The closure captures `self` (the full ChatApp instance) just to call `_show_guardrail_confirm`. This couples the guardrail engine to the TUI.

**New design in `guardrails/hooks.py`:**

```python
# guardrails/hooks.py

from __future__ import annotations
from pathlib import Path
from typing import Any, Awaitable, Callable

from claude_agent_sdk.types import HookMatcher


# Type alias for the confirm callback
ConfirmCallback = Callable[[str, str], Awaitable[bool]]  # (rule_id, message) -> approved


def create_guardrail_hooks(
    rules_path: Path,
    phase_state_path: Path,
    agent_role: str | None = None,
    confirm_callback: ConfirmCallback | None = None,
) -> dict[str, list[HookMatcher]]:
    """Create PreToolUse hooks that evaluate guardrail rules.

    Args:
        rules_path: Path to rules.yaml (or workflow manifest)
        phase_state_path: Path to state.json for phase filtering
        agent_role: Role type captured at agent creation time
        confirm_callback: async (rule_id, message) -> bool for user_confirm enforcement.
                         If None, user_confirm rules are denied.
    """
    # ... closure with evaluate() function, same logic as current _guardrail_hooks
```

**What app.py provides:** A thin adapter that wraps `_show_guardrail_confirm` as a `ConfirmCallback`:

```python
# In app.py
async def _guardrail_confirm_callback(self, rule_id: str, message: str) -> bool:
    """Adapter: wraps _show_guardrail_confirm for the hooks module."""
    # Create a lightweight object with .id and .message for the prompt
    class _RuleProxy:
        def __init__(self, id, message):
            self.id = id
            self.message = message
    return await self._show_guardrail_confirm(_RuleProxy(rule_id, message))
```

**Updated `_merged_hooks()`:**

```python
def _merged_hooks(self, agent_type: str | None = None) -> dict[HookEvent, list[HookMatcher]]:
    hooks = self._plan_mode_hooks()

    # Guardrail hooks (extracted to guardrails/hooks.py)
    from claudechic.guardrails.hooks import create_guardrail_hooks
    guardrail_hooks = create_guardrail_hooks(
        rules_path=self._rules_path,
        phase_state_path=self._phase_state_path,
        agent_role=agent_type,
        confirm_callback=lambda rid, msg: self._guardrail_confirm_callback(rid, msg),
    )
    for event, matchers in guardrail_hooks.items():
        hooks.setdefault(event, []).extend(matchers)

    # Workflow hooks (NEW — phase-aware rules from manifest)
    # The workflow engine provides additional hooks if active
    if self._workflow_engine:
        wf_hooks = self._workflow_engine.create_hooks(
            agent_role=agent_type,
            confirm_callback=lambda rid, msg: self._guardrail_confirm_callback(rid, msg),
        )
        for event, matchers in wf_hooks.items():
            hooks.setdefault(event, []).extend(matchers)

    return hooks
```

### Stays in app.py

- `_show_guardrail_confirm()` (lines 720-744) — Pure TUI: creates `SelectionPrompt`, uses `_show_prompt()` context manager. This MUST stay in app.py.
- `_plan_mode_hooks()` (lines 598-631) — App-level concern, not workflow-related.
- `_show_prompt()` (lines 490-520) — Core TUI infrastructure.
- `_run_hints()` (lines 1059-1098) — Project-side hints loader. Separate system.

### New Code app.py Needs

1. **Workflow engine initialization** — In `on_mount()` or `_connect_initial_client()`, discover manifests and create the engine.
2. **Confirm callback adapter** — A method wrapping `_show_guardrail_confirm` with the `ConfirmCallback` signature.
3. **PostCompact hook registration** — Add a `PostCompact` hook to `_merged_hooks()` that re-injects phase context.
4. **Workflow engine reference** — `self._workflow_engine: WorkflowEngine | None` attribute.

---

## 4. Interface Changes

### 4.1 `should_skip_for_phase()` — Signature Simplification

**Old signature:**
```python
def should_skip_for_phase(rule: Rule, phase_state: dict[str, Any] | None) -> bool:
```

**New signature:**
```python
def should_skip_for_phase(rule: Rule, current_phase: str | None) -> bool:
```

**Why:** The engine reads state.json and provides the current phase string. The rule evaluator shouldn't know about state.json structure.

**Callers to update:**
- `guardrails/hooks.py` `evaluate()` closure (extracted from app.py:670-675)
- Direct callers via `guardrails/__init__.py` (if any external callers exist)

**Backward compat:** Breaking change but all callers are internal to claudechic. The change point is:
```python
# Old (app.py:666):
phase_state = read_phase_state(phase_state_path)
# ... later:
if should_skip_for_phase(rule, phase_state):

# New:
current_phase = engine.get_current_phase()  # or read from state.json directly
# ... later:
if should_skip_for_phase(rule, current_phase):
```

### 4.2 `load_rules()` — Replaced

**Old (REMOVED):**
```python
def load_rules(rules_path: Path) -> list[Rule]:
```

**Replaced by manifest loader:**
```python
# In workflows/loader.py — the ManifestLoader handles all rule loading
result = loader.load()
rules = result.rules  # list[Rule], namespace-qualified
```

**Why:** No backward compat needed (unreleased system). One rule loading path: the manifest loader. Old `load_rules()` is deleted, not supplemented.

### 4.3 `Rule` Dataclass — Redesigned

**New:**
```python
@dataclass(frozen=True)
class Rule:
    id: str  # Qualified: "project_team:pip_block"
    namespace: str  # "_global" or workflow_id (required, no default)
    trigger: list[str]
    enforcement: str
    # ... rest as defined in manifest_loader.md RulesParser
```

**Why:** Namespace is required — every rule comes from a manifest with a known namespace. No defaults needed since old `load_rules()` is gone. YAML uses `block_roles`/`allow_roles` only (no `block`/`allow` compat).

### 4.4 Rule YAML Keys — Alignment Fix

**Old (rules.py lines 73-79):** YAML keys `block`/`allow` map to fields `block_roles`/`allow_roles`:
```yaml
# Old rules.yaml
- id: close_agent
  block: [implementer]    # YAML key
  allow: [coordinator]    # YAML key
```

**New (manifest YAML):** Keys match field names directly:
```yaml
# New manifest YAML
- id: close_agent
  block_roles: [implementer]   # Matches dataclass field
  allow_roles: [coordinator]   # Matches dataclass field
```

**Why:** Eliminates the confusing mapping. The old `load_rules()` keeps its `block`/`allow` key mapping for backward compat. The new manifest loader uses `block_roles`/`allow_roles` directly.

**Impact:** Manifest authors use the clearer field names. Existing standalone `rules.yaml` files continue to work with old keys.

### 4.5 Hook Creation — New Public API

**Old:** `ChatApp._guardrail_hooks(agent_role)` — private method on app.

**New:** `guardrails.hooks.create_guardrail_hooks(rules_path, phase_state_path, agent_role, confirm_callback)` — free function.

**Why:** Decouples hook creation from TUI. Testable in isolation.

**Callers:** Only `app.py._merged_hooks()`. The change is internal refactoring.

---

## 5. New Modules

### 5.1 `workflows/__init__.py`

**Purpose:** Public API for the workflow guidance system.

**Exports:**
```python
from workflows.loader import load_manifests, ManifestSection
from workflows.engine import WorkflowEngine
from workflows.checks import Check, CheckResult, CommandOutputCheck, FileExistsCheck, FileContentCheck, ManualConfirm
from workflows.manifest_types import WorkflowManifest, Phase, CheckSpec, HintDecl
```

**Imports:** Only from its own submodules.

**Dependents:** `app.py` (engine init, hook creation), `guardrails/hooks.py` (manifest-based rule loading).

### 5.2 `workflows/loader.py`

**Purpose:** Discover manifests in `workflows/` directory, parse YAML, dispatch sections to typed parsers.

**Key exports:**
```python
T = TypeVar("T")

class ManifestSection(Protocol[T]):
    """Protocol for section parsers."""
    section_key: str  # e.g. "rules", "checks", "hints", "phases"
    def parse(self, raw: list[dict], namespace: str) -> list[T]: ...

def discover_manifests(workflows_dir: Path) -> list[Path]:
    """Find global.yaml and all workflow manifests."""

class ManifestLoader:
    """Single code path. load() returns LoadResult, callers filter."""
    def __init__(self, workflows_dir: Path) -> None: ...
    def load(self) -> LoadResult: ...
    # No load_rules_only() — callers do loader.load().rules
```

**Imports:** `yaml`, `pathlib`, `guardrails.rules.Rule` (for rule parsing), `workflows.manifest_types`

**Dependents:** `workflows/__init__.py`, `workflows/engine.py`, `guardrails/hooks.py`

### 5.3 `workflows/engine.py`

**Purpose:** Phase transitions, state persistence (state.json), advance check orchestration.

**Key exports:**
```python
class WorkflowEngine:
    def __init__(
        self,
        manifest: WorkflowManifest,
        state_path: Path,
        confirm_callback: ConfirmCallback | None = None,
    ): ...

    def get_current_phase(self) -> str | None:
        """Read current phase from state.json (no caching — NFS safe)."""

    async def try_advance(self) -> bool:
        """Run advance_checks for current phase. Advance if all pass."""

    async def set_phase(self, phase_id: str) -> None:
        """Set phase directly (for manual transitions)."""

    def create_hooks(
        self,
        agent_role: str | None,
        confirm_callback: ConfirmCallback | None,
    ) -> dict[str, list[HookMatcher]]:
        """Create SDK hooks for this workflow's rules (phase-aware)."""

    def get_post_compact_hook(self) -> dict[str, list[HookMatcher]]:
        """Create PostCompact hook for phase context re-injection."""
```

**Imports:** `json`, `pathlib`, `workflows.manifest_types`, `workflows.checks`, `guardrails.rules` (for evaluation functions)

**Dependents:** `app.py`, `workflows/__init__.py`

### 5.4 `workflows/checks.py`

**Purpose:** Check protocol and 4 built-in implementations.

**Key exports:**
```python
@dataclass
class CheckResult:
    passed: bool
    evidence: str

class Check(Protocol):
    async def check(self) -> CheckResult: ...

@dataclass
class CommandOutputCheck:
    command: str
    pattern: str  # regex
    async def check(self) -> CheckResult: ...

@dataclass
class FileExistsCheck:
    path: Path
    async def check(self) -> CheckResult: ...

@dataclass
class FileContentCheck:
    path: Path
    pattern: str  # regex
    async def check(self) -> CheckResult: ...

@dataclass
class ManualConfirm:
    question: str
    confirm_callback: Callable[[str], Awaitable[bool]]
    async def check(self) -> CheckResult: ...

def check_failed_to_hint(result: CheckResult, on_failure: dict) -> HintSpec:
    """CheckFailed adapter: convert failed check to HintSpec for the hints pipeline."""
```

**Imports:** `asyncio`, `re`, `pathlib`, `subprocess` (for command execution). The `check_failed_to_hint` adapter imports from `hints._types.HintSpec`.

**Dependents:** `workflows/engine.py`, `workflows/loader.py`

### 5.5 `workflows/agent_folders.py`

**Purpose:** Assemble agent prompts from identity.md + current phase.md.

**Key exports:**
```python
def assemble_agent_prompt(
    workflow_dir: Path,
    role_name: str,
    current_phase: str | None,
) -> str:
    """Read identity.md + phase.md for the given role, return concatenated content.

    Args:
        workflow_dir: e.g. workflows/project_team/
        role_name: folder name, e.g. "coordinator"
        current_phase: e.g. "specification" -> reads specification.md

    Returns:
        Concatenated markdown: identity.md + \\n\\n---\\n\\n + {phase}.md
        If phase file doesn't exist, returns identity.md only.
    """

def get_system_prompt_injection(
    workflows_dir: Path,
    workflow_id: str,
    role_name: str,
    current_phase: str | None,
) -> str | None:
    """Get the full system prompt content for an agent.

    Called at agent spawn time and by PostCompact hook.
    Returns None if no agent folder exists for this role.
    """
```

**Imports:** `pathlib` only.

**Dependents:** `workflows/engine.py` (for PostCompact), `mcp.py` or `app.py` (at agent spawn time)

### 5.6 `workflows/manifest_types.py`

**Purpose:** Dataclasses for parsed manifest content.

**Key exports:**
```python
@dataclass
class CheckSpec:
    """A check declaration from a manifest."""
    id: str
    type: str  # "command-output-check", "file-exists", etc.
    params: dict[str, Any]  # type-specific parameters
    on_failure: dict | None = None  # {message, severity, lifecycle}
    when: dict | None = None  # conditional (e.g., {copier: key})

@dataclass
class HintDecl:
    """A hint declaration from a manifest."""
    message: str
    lifecycle: str = "show-once"

@dataclass
class Phase:
    """A phase in a workflow."""
    id: str
    file: str  # relative path to phase markdown
    advance_checks: list[CheckSpec] = field(default_factory=list)
    hints: list[HintDecl] = field(default_factory=list)

@dataclass
class WorkflowManifest:
    """Parsed workflow manifest."""
    workflow_id: str
    path: Path  # path to the manifest file
    rules: list[Rule] = field(default_factory=list)
    phases: list[Phase] = field(default_factory=list)
    checks: list[CheckSpec] = field(default_factory=list)
    hints: list[HintDecl] = field(default_factory=list)
```

**Imports:** `dataclasses`, `pathlib`, `guardrails.rules.Rule`

**Dependents:** `workflows/loader.py`, `workflows/engine.py`, `workflows/checks.py`

### 5.7 `guardrails/hooks.py`

**Purpose:** Hook closure factory, extracted from app.py.

**Key exports:**
```python
ConfirmCallback = Callable[[str, str], Awaitable[bool]]

def create_guardrail_hooks(
    rules_path: Path,
    phase_state_path: Path,
    agent_role: str | None = None,
    confirm_callback: ConfirmCallback | None = None,
) -> dict[str, list[HookMatcher]]:
    """Create PreToolUse hooks that evaluate guardrail rules."""
```

**Imports:** `guardrails.rules` (all matching functions), `claude_agent_sdk.types.HookMatcher`

**Dependents:** `app.py._merged_hooks()`, `workflows/engine.py.create_hooks()`

### 5.8 `claudechic/hints/` — Moved from Template-Side to claudechic

**Design decision:** The template-side `hints/` package (`AI_PROJECT_TEMPLATE/hints/`) already has the exact types and pipeline the new system needs: `TriggerCondition`, `HintLifecycle`, `HintSpec`, `run_pipeline()`, `ProjectState`, `HintStateStore`. Rather than duplicating these types, the new `claudechic/hints/` package **absorbs the infrastructure** from the template-side package:

- `hints/_types.py` — `TriggerCondition` (Protocol), `HintLifecycle` (Protocol), `HintSpec` (frozen dataclass with `id`, `trigger`, `message`, `severity`, `priority`, `lifecycle`), `HintRecord`. Lifecycle implementations: `ShowOnce`, `ShowUntilResolved`, `ShowEverySession`, `CooldownPeriod(seconds)`.
- `hints/_engine.py` — `run_pipeline(send_notification, project_state, state_store, activation, hints, budget, is_startup)` — the 6-stage pipeline
- `hints/_state.py` — `ProjectState`, `CopierAnswers`, `HintStateStore` (manages `.claude/hints_state.json`), `ActivationConfig`
- `hints/hints.py` — Built-in hint specs (the 7 existing hints) — OR this stays template-side if we want project-specific hints separate
- `hints/__init__.py` — Public API: `evaluate()` entry point

**Migration (single step):** Move infrastructure from template-side `hints/` into `claudechic/hints/`. Switch `app.py._run_hints()` from `importlib` dynamic loading to direct import of `claudechic.hints`. Template-side hint definitions (the 7 built-in hints) move to YAML manifests or stay as Python-based hint source — decided during implementation.

**Key reuse:** The existing `HintSpec` type is exactly what `check_failed_to_hint()` needs. The existing `run_pipeline()` is exactly what manifest-declared hints feed into. No new hint infrastructure needed — just move and extend.

**New capability:** `AlwaysTrue` trigger condition for CheckFailed adapter (hint always activates when created from a failed check).

**Imports:** `pathlib`, `json`, `dataclasses`

**Dependents:** `workflows/checks.py` (CheckFailed adapter uses `HintSpec`), `app.py` (pipeline evaluation)

---

## 6. Import Dependency Graph

```
app.py
  ├── guardrails/hooks.py           (create_guardrail_hooks)
  ├── guardrails/rules.py           (Rule — for type hints only)
  ├── workflows/engine.py           (WorkflowEngine)
  ├── workflows/agent_folders.py    (get_system_prompt_injection)
  └── hints/__init__.py             (run_pipeline — for toast scheduling)

guardrails/hooks.py
  ├── guardrails/rules.py           (load_rules, match_rule, matches_trigger, should_skip_*)
  └── claude_agent_sdk.types        (HookMatcher)

workflows/engine.py
  ├── workflows/manifest_types.py   (WorkflowManifest, Phase, CheckSpec)
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
- `workflows/` → `guardrails/rules.py`: one-way (workflows uses rule matching)
- `guardrails/hooks.py` → `guardrails/rules.py`: one-way (hooks uses rule loading)
- `workflows/checks.py` → `hints/_types.py`: one-way (CheckFailed adapter)
- `hints/` never imports `workflows/` or `guardrails/`
- `guardrails/` never imports `workflows/` or `hints/`
- `app.py` imports from all three packages but none import app.py

### Seam Cleanliness

| Boundary | Clean? | Notes |
|---|---|---|
| `workflows/` → `guardrails/rules.py` | Yes | Only imports `Rule` type and matching functions. No internal state access. |
| `workflows/checks.py` → `hints/_types.py` | Yes | Only imports `HintSpec` dataclass. One-way adapter. |
| `app.py` → `guardrails/hooks.py` | Yes | Uses factory function, passes callback. No app reference leaks. |
| `app.py` → `workflows/engine.py` | Yes | Uses engine API, passes confirm callback. |
| `hints/` standalone | Yes | Zero imports from workflows/ or guardrails/. |

---

## 7. PostCompact Hook

### How Compaction Works Today

`compact.py` (`compact_session()`, line 54) operates on JSONL session files directly. It:
1. Loads all messages from `{session_id}.jsonl`
2. Identifies old, large tool_use inputs and tool_result outputs
3. Replaces them with placeholder strings (`"[compacted]"`)
4. Writes the modified file back

Compaction is triggered by the `/compactish` command (in `commands.py`). The SDK reads the JSONL on resume, so compacted content affects what Claude sees.

**There is NO PostCompact hook today.** The SDK supports `PostCompact` as a `HookEvent` (confirmed by the type import at app.py:16), but no hook is registered for it.

### Where the PostCompact Hook Lives

**Location:** `workflows/engine.py` → `WorkflowEngine.get_post_compact_hook()`

**Design:**
```python
def get_post_compact_hook(self) -> dict[str, list[HookMatcher]]:
    """Create PostCompact hook that re-injects phase context after /compact."""
    engine = self  # capture for closure

    async def reinject_phase_context(
        hook_input: dict,
        match: str | None,
        ctx: object,
    ) -> dict:
        """PostCompact: inject current phase info into the conversation."""
        current_phase = engine.get_current_phase()
        if not current_phase:
            return {}

        # Assemble the agent's phase context
        # The hook_input should contain enough to identify the agent role
        role = hook_input.get("agent_role")  # or from env var
        prompt_content = get_system_prompt_injection(
            workflows_dir=engine.workflows_dir,
            workflow_id=engine.manifest.workflow_id,
            role_name=role or "coordinator",
            current_phase=current_phase,
        )

        if prompt_content:
            return {"inject_context": prompt_content}
        return {}

    return {
        "PostCompact": [HookMatcher(matcher=None, hooks=[reinject_phase_context])],
    }
```

### How It Gets Current Phase Info

The engine reads `state.json` on every call to `get_current_phase()` (no caching — NFS safe, per spec constraint). The state file is at `workflows/{workflow_id}/state.json`.

### Integration in app.py

```python
def _merged_hooks(self, agent_type: str | None = None) -> dict[HookEvent, list[HookMatcher]]:
    hooks = self._plan_mode_hooks()
    # ... guardrail hooks ...
    # ... workflow hooks ...

    # PostCompact hook for phase context recovery
    if self._workflow_engine:
        compact_hooks = self._workflow_engine.get_post_compact_hook()
        for event, matchers in compact_hooks.items():
            hooks.setdefault(event, []).extend(matchers)

    return hooks
```

**Open question:** What does the SDK do with the `PostCompact` hook return value? The `inject_context` key is speculative. Need to verify SDK's PostCompact hook protocol — does it support injecting a system message? If not, the hook may need to write to a file that the SDK's system prompt mechanism reads, or use `SystemMessage` injection via the client.

---

## 8. Agent Folder Prompt Assembly

### How `agent_folders.py` Assembles Prompts

```python
def assemble_agent_prompt(
    workflow_dir: Path,     # e.g., workflows/project_team/
    role_name: str,         # e.g., "coordinator" (folder name)
    current_phase: str | None,  # e.g., "specification"
) -> str:
    """
    1. Read {workflow_dir}/{role_name}/identity.md
    2. If current_phase: read {workflow_dir}/{role_name}/{current_phase}.md
    3. Return concatenation: identity + separator + phase content
    """
    role_dir = workflow_dir / role_name

    # Always load identity
    identity_path = role_dir / "identity.md"
    identity = identity_path.read_text() if identity_path.is_file() else ""

    # Load phase-specific content
    phase_content = ""
    if current_phase:
        phase_path = role_dir / f"{current_phase}.md"
        if phase_path.is_file():
            phase_content = phase_path.read_text()

    if phase_content:
        return f"{identity}\n\n---\n\n{phase_content}"
    return identity
```

### Where It's Called

**At agent spawn time:** When `mcp.py:spawn_agent()` creates an agent with a `type` parameter, the prompt assembly should happen. The assembled content is prepended to the agent's initial prompt.

**Call chain:**
1. `mcp.py:spawn_agent(args)` — receives `type` (role) and `prompt`
2. Currently: prompt is sent directly via `_send_prompt_fire_and_forget(agent, prompt)`
3. **New:** Before sending the prompt, assemble agent folder content:

```python
# In mcp.py spawn_agent, after agent creation:
from claudechic.workflows.agent_folders import get_system_prompt_injection

folder_prompt = get_system_prompt_injection(
    workflows_dir=workflows_dir,
    workflow_id=active_workflow_id,
    role_name=agent_type or name,  # role folder name
    current_phase=current_phase,
)

if folder_prompt:
    full_prompt = f"{folder_prompt}\n\n---\n\n{prompt}"
else:
    full_prompt = prompt

_send_prompt_fire_and_forget(agent, full_prompt, ...)
```

**By PostCompact hook:** After `/compact`, the PostCompact hook re-injects the phase context (see §7).

**NOT on every message.** The prompt is injected once at spawn time. The agent's system prompt persists in the conversation. Phase transitions don't mid-session inject — the agent reads `state.json` if it needs current phase info.

### Interaction with agent.py and agent_manager.py

**agent.py:** No changes needed. The agent receives its prompt via `query()` — the prompt content is opaque to the Agent class. The hooks (including PostCompact) are part of `ClaudeAgentOptions.hooks` set at connect time.

**agent_manager.py:**
- `create()` (line 120) already accepts `agent_type` and passes it to `_options_factory`
- The `_options_factory` is `app._make_options()` which passes `agent_type` to `_merged_hooks()`
- **New responsibility:** `_options_factory` should also return prompt content for the agent folder, OR the spawn code in mcp.py prepends it (preferred — keeps agent_manager clean)

**mcp.py:**
- `spawn_agent` (line 177) needs to call `get_system_prompt_injection()` before sending the prompt
- This requires knowing the `workflows_dir` and current workflow/phase — these come from the `WorkflowEngine` instance on the app

---

## 9. Summary of Changes by File

### Files to CREATE:
1. `claudechic/workflows/__init__.py`
2. `claudechic/workflows/loader.py`
3. `claudechic/workflows/engine.py`
4. `claudechic/workflows/checks.py`
5. `claudechic/workflows/agent_folders.py`
6. `claudechic/workflows/manifest_types.py`
7. `claudechic/guardrails/hooks.py`
8. `claudechic/hints/__init__.py`
9. `claudechic/hints/_types.py`
10. `claudechic/hints/_engine.py`
11. `claudechic/hints/_state.py`
12. `claudechic/hints/hints.py`

### Files to MODIFY:
1. `claudechic/guardrails/rules.py` — Add `namespace` field to Rule; simplify `should_skip_for_phase()` signature; move `read_phase_state()` out
2. `claudechic/guardrails/__init__.py` — Add hooks.py exports
3. `claudechic/app.py` — Extract `_guardrail_hooks` body to hooks.py; update `_merged_hooks` to include workflow hooks and PostCompact; add workflow engine init; add confirm callback adapter
4. `claudechic/mcp.py` — Add agent folder prompt assembly to `spawn_agent`

### Files UNCHANGED:
1. `claudechic/compact.py` — No changes. PostCompact hook is SDK-level, not compact.py.
2. `claudechic/agent.py` — No changes. Agent is prompt-agnostic.
3. `claudechic/agent_manager.py` — No changes. Already passes `agent_type` through.

---

## 10. Startup Validation (New in loader.py)

The existing `load_rules()` has **no validation** — no duplicate ID check, no regex compilation validation, no phase reference validation. The new manifest loader adds:

1. **Duplicate ID detection:** After namespace prefixing, all rule/check/hint IDs across all manifests must be unique. Collision → warning + skip the duplicate.
2. **Regex compilation validation:** All `detect.pattern` and check `pattern` fields compiled at load time. Invalid regex → warning + skip that rule/check (fail-open per-item).
3. **Phase reference validation:** `phase_block`/`phase_allow` values validated against known phases from all loaded manifests. Unknown phase → warning (not error, since global rules may reference workflow phases loaded in a different manifest).
4. **Raw ID validation:** Rule IDs in YAML must not contain `:` (prevents double-prefixing like `project_team:project_team:pip_block`).
5. **Fail modes:** `workflows/` directory unreadable → fail closed (block everything). Individual manifest malformed → fail open (skip that manifest, log warning, load the rest).

---

## 11. Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| PostCompact hook SDK protocol unknown | Medium | Verify SDK docs/source for PostCompact hook return value format before implementing |
| NFS latency on every tool call (rules reload) | Low | Spec explicitly says no mtime caching. Accept latency. Profile later. |
| Circular import between workflows/ and guardrails/ | Low | Dependency graph verified clean (§6). workflows/ imports guardrails/ one-way. |
| hints/ package name collision with project-side hints/ | Medium | Different import paths: `claudechic.hints` vs dynamic load of `{project}/hints`. No collision. |
| app.py _merged_hooks growing complex | Low | Each hook source is a clean factory function. Merging is just dict extension. |
| ManualConfirm callback injection threading | Medium | Confirm callback is async and runs on the main event loop (Textual). Same pattern as existing `_show_guardrail_confirm`. No threading issues. |
