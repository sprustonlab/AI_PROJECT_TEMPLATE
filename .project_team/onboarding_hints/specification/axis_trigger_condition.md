# Axis Deep-Dive: TriggerCondition

## Step 1: Relevance Check

**TriggerCondition is a real, non-collapsible axis.** Justification:

- **Not collapsible into HintLifecycle:** Lifecycle manages *how often* a hint is shown (once, N times, cooldown). TriggerCondition decides *whether the condition holds right now*. A `PathNotExists(".git")` trigger is reusable across show-once, show-until-resolved, or show-every-session lifecycles.
- **Not collapsible into EvaluationTiming:** Timing decides *when* to run a check (startup, on-command). The trigger is *what* to check. The same `DirEmpty("mcp_tools/")` trigger works whether evaluated at startup or periodically.
- **Not collapsible into Presentation:** Presentation consumes a `HintRecord`; it doesn't know or care what condition produced it.
- **Has multiple independent values:** file-existence, directory-empty, file-content-match, session-count-threshold, config-state, custom-callable — each is a distinct check type combinable with any lifecycle/timing/presentation.

**Verdict:** TriggerCondition is the most complex axis, with the most concrete implementations and the richest extension surface. It deserves its own deep design.

---

## Step 2: Protocol Definition

### 2.1 TriggerCondition Protocol

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TriggerCondition(Protocol):
    """Pure function of project state → bool.

    Design rule (from Skeptic): Triggers read ONLY from disk/config,
    never from live UI state. This keeps the TriggerCondition ↔
    EvaluationTiming seam clean.
    """

    def check(self, state: ProjectState) -> bool:
        """Return True if the condition is met (hint should fire).

        Must be:
        - Pure: same ProjectState → same result
        - Side-effect-free: no writes, no network calls
        - Fast: called at startup, should complete in <50ms
        """
        ...

    @property
    def description(self) -> str:
        """Human-readable description for debugging/logging."""
        ...
```

**Key constraints:**
1. **Pure function of `ProjectState`** — no imports of ClaudeChic, no Textual widgets, no runtime UI state.
2. **Side-effect-free** — triggers never write files or mutate state.
3. **Fast** — all triggers run at startup; total budget is ~200ms for all hints.

### 2.2 ProjectState Interface

> **Revision 2a** — Removed `PatternMinerState` and `SessionInfo` typed fields.
> These created cross-seam dependencies on other modules' internal state.
> `ProjectState` now exposes only generic filesystem primitives + `CopierAnswers`.

**Seam discipline:** `ProjectState` must NOT contain typed representations of other
modules' internal state (e.g., pattern miner's JSON schema). It provides generic
filesystem primitives that triggers compose to check whatever they need.

**Why `CopierAnswers` is allowed but `PatternMinerState` is not:**
- `.copier-answers.yml` is a **stable contract** defined by Copier itself. Its schema
  is determined at template generation time and doesn't change during project use.
- `.patterns_mining_state.json` is an **internal implementation detail** of `mine_patterns.py`.
  Its schema can change without notice. Parsing it creates a hidden dependency.

**Prerequisite:** The template must include `{{_copier_conf.answers_file}}.jinja` in
the `template/` subdirectory for Copier to generate `.copier-answers.yml` in destination
projects. Without this file, Copier silently skips answers file generation.
See Copier Integration section in SPECIFICATION.md.

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CopierAnswers:
    """Parsed Copier template answers from .copier-answers.yml.

    This is a stable contract — Copier generates this file in the destination
    project when the template includes {{_copier_conf.answers_file}}.jinja.

    GRACEFUL FALLBACK: If .copier-answers.yml is missing (template missing
    the jinja file, manually set up project, user deleted it), feature flags
    default to their copier.yml defaults. One source of truth rule:
    missing answers file = user accepted all Copier defaults.
    """
    raw: dict[str, Any]

    @classmethod
    def load(cls, project_root: Path) -> CopierAnswers:
        """Load from .copier-answers.yml, or return all-defaults if missing."""
        answers_file = project_root / ".copier-answers.yml"
        if not answers_file.is_file():
            return cls(raw={})  # All defaults
        try:
            import yaml
            data = yaml.safe_load(answers_file.read_text())
            return cls(raw=data if isinstance(data, dict) else {})
        except Exception:
            return cls(raw={})  # Corrupt file → same as missing

    @property
    def use_guardrails(self) -> bool:
        return bool(self.raw.get("use_guardrails", True))

    @property
    def use_project_team(self) -> bool:
        return bool(self.raw.get("use_project_team", True))

    @property
    def use_pattern_miner(self) -> bool:
        return bool(self.raw.get("use_pattern_miner", False))  # off by default in copier.yml

    @property
    def use_cluster(self) -> bool:
        return bool(self.raw.get("use_cluster", False))  # off by default in copier.yml

    @property
    def use_hints(self) -> bool:
        return bool(self.raw.get("use_hints", True))

    @property
    def cluster_scheduler(self) -> str | None:
        if not self.use_cluster:
            return None
        return self.raw.get("cluster_scheduler", "lsf")

    @property
    def project_name(self) -> str:
        return self.raw.get("project_name", "")

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)


@dataclass(frozen=True)
class ProjectState:
    """Read-only context passed to every TriggerCondition.check().

    SEAM DISCIPLINE: This class exposes ONLY:
    1. Project root path
    2. CopierAnswers (stable Copier contract)
    3. Context provided by ClaudeChic via evaluate() kwargs
    4. Generic filesystem primitives

    It does NOT expose typed representations of other modules' state.
    It does NOT read data that ClaudeChic already has — ClaudeChic
    passes that context via kwargs (e.g., session_count).

    KWARGS CONVENTION: All ClaudeChic-provided fields are Optional[T]
    with default None. None means "not provided" or "failed to compute."
    Triggers that depend on a field MUST check for None first.
    This scales to any future kwargs without new conventions.
    """
    root: Path                          # Project root (absolute)
    copier: CopierAnswers               # Parsed .copier-answers.yml

    # --- ClaudeChic-provided context (all Optional, default None) ---
    session_count: int | None = None    # None = unknown/not provided
                                        # 0    = genuinely zero sessions
                                        # ≥1   = real session count

    # --- Generic filesystem primitives ---

    def path_exists(self, relative: str) -> bool:
        """Check if a path exists relative to project root."""
        return (self.root / relative).exists()

    def dir_is_empty(self, relative: str) -> bool:
        """Check if a directory exists and contains no meaningful files.

        Ignores __pycache__, .gitkeep, README.md, and other boilerplate.
        Returns True if dir doesn't exist (vacuously empty).
        """
        d = self.root / relative
        if not d.is_dir():
            return True
        ignored = {"__pycache__", ".gitkeep", "README.md", ".DS_Store"}
        return not any(
            child.name not in ignored
            for child in d.iterdir()
            if not child.name.startswith(".")
            or child.name == ".gitkeep"
        )

    def file_contains(self, relative: str, pattern: str) -> bool:
        """Check if a file contains a regex pattern."""
        import re
        p = self.root / relative
        if not p.is_file():
            return False
        try:
            return bool(re.search(pattern, p.read_text()))
        except OSError:
            return False

    def count_files_matching(self, relative_dir: str, glob: str,
                              exclude_prefixes: tuple[str, ...] = ("_",)) -> int:
        """Count files matching a glob in a directory.

        Args:
            relative_dir: Directory path relative to project root
            glob: Glob pattern (e.g., "*.py")
            exclude_prefixes: Skip files starting with these prefixes (default: "_")
        """
        d = self.root / relative_dir
        if not d.is_dir():
            return 0
        return sum(
            1 for f in d.glob(glob)
            if not any(f.name.startswith(p) for p in exclude_prefixes)
        )

```

**Design decisions:**
- `frozen=True` on all dataclasses — triggers cannot mutate state.
- `CopierAnswers` wraps the raw dict with typed properties for feature toggles. This is safe because `.copier-answers.yml` is a stable Copier contract. **Prerequisite:** Template must include `template/{{_copier_conf.answers_file}}.jinja` for Copier to generate this file in destination projects.
- **Graceful fallback when `.copier-answers.yml` is missing:** Feature flags default to their `copier.yml` defaults (one source of truth). `use_guardrails=True`, `use_project_team=True`, but `use_pattern_miner=False`, `use_cluster=False`. This prevents broken hints — e.g., recommending "Run the Pattern Miner" when `scripts/mine_patterns.py` doesn't exist. Missing file = "user accepted all Copier defaults." Handles: manually set up projects, template missing the jinja file, user deleted the file.
- **No `PatternMinerState`** — removed. Triggers use `path_exists(".patterns_mining_state.json")` to check if the miner has run. No parsing of the miner's internal JSON.
- **ClaudeChic-provided fields are `Optional[T]`, default `None`** — General convention for all kwargs-sourced data. `None` means "not provided" or "failed to compute." Triggers MUST check for `None` before using the value. This is standard Python (`Optional`), works for all types (int, str, bool, etc.), and scales to future kwargs without new conventions.
- **`session_count` provided by ClaudeChic** — not read from filesystem. Claude stores sessions at `~/.claude/projects/<hashed-path>/` (user HOME). ClaudeChic passes the count via `evaluate()` kwargs. Defaults to `None` if not provided (old ClaudeChic compat), so triggers silently don't fire rather than firing on missing data.
- **No feature-specific helpers** like `count_rules_in_guardrails()` or `mcp_tool_files()`. Triggers compose the generic primitives: `count_files_matching(".claude/guardrails/rules.d", "*.yaml")`, `count_files_matching("mcp_tools", "*.py")`. This keeps `ProjectState` from accumulating feature-specific methods over time.
- Generic primitives are the ONLY interface. If a new trigger needs something not covered by the primitives, the right fix is a new generic primitive (e.g., `count_lines_matching()`), NOT a feature-specific typed field.

---

## Step 3: Built-in Trigger Implementations

All triggers are Python dataclasses (per Skeptic's feedback — no YAML for trigger definitions).

### 3.1 Git Setup Trigger

```python
@dataclass(frozen=True)
class GitNotInitialized:
    """Hint: No .git directory detected."""

    def check(self, state: ProjectState) -> bool:
        return not state.path_exists(".git")

    @property
    def description(self) -> str:
        return "Project is not a git repository"
```

- **What it checks:** `.git` directory existence
- **Copier-aware:** No — git is always relevant regardless of template features.
- **Uses:** `state.path_exists(".git")`

### 3.2 Guardrails Default-Only Trigger

```python
@dataclass(frozen=True)
class GuardrailsOnlyDefault:
    """Hint: Only the default R01 rule exists in guardrails."""
    rules_dir: str = ".claude/guardrails/rules.d"

    def check(self, state: ProjectState) -> bool:
        if not state.copier.use_guardrails:
            return False  # Feature disabled — skip hint
        # Template ships with just the default rule. If rules.d/ has no
        # user-added YAML files, user hasn't customized guardrails.
        return state.count_files_matching(self.rules_dir, "*.yaml") == 0

    @property
    def description(self) -> str:
        return "Guardrails have only the default rule"
```

- **What it checks:** Whether `rules.d/` contains user-added YAML rule files — the template ships with just R01 (deny-dangerous-ops) in the base `rules.yaml`.
- **Copier-aware:** Yes — skips if `use_guardrails=false`.
- **Uses:** `state.copier.use_guardrails`, `state.count_files_matching()` (generic primitive)

### 3.3 Project Team Never Used Trigger

```python
@dataclass(frozen=True)
class ProjectTeamNeverUsed:
    """Hint: /ao_project_team command has never been invoked."""
    ao_dir: str = ".ao_project_team"

    def check(self, state: ProjectState) -> bool:
        if not state.copier.use_project_team:
            return False  # Feature disabled — skip hint
        # If the .ao_project_team dir doesn't exist or has no session artifacts,
        # the user has never run the command.
        return not state.path_exists(self.ao_dir)

    @property
    def description(self) -> str:
        return "Project team workflow has never been used"
```

- **What it checks:** Whether `.ao_project_team/` directory exists (created on first `/ao_project_team` invocation).
- **Copier-aware:** Yes — skips if `use_project_team=false`.
- **Uses:** `state.copier.use_project_team`, `state.path_exists()`

### 3.4 Pattern Miner Underused Trigger

```python
@dataclass(frozen=True)
class PatternMinerUnderutilized:
    """Hint: Enough sessions exist but pattern miner has never run."""
    min_sessions: int = 10
    miner_state_file: str = ".patterns_mining_state.json"

    def check(self, state: ProjectState) -> bool:
        if not state.copier.use_pattern_miner:
            return False  # Feature disabled — skip hint
        if state.session_count is None:
            return False  # Session count unavailable — can't evaluate
        # Enough sessions to be useful, but miner never run.
        return (
            state.session_count >= self.min_sessions
            and not state.path_exists(self.miner_state_file)
        )

    @property
    def description(self) -> str:
        return f"Pattern miner never run despite {self.min_sessions}+ sessions"
```

- **What it checks:** Session count ≥ threshold AND `.patterns_mining_state.json` doesn't exist (miner never run).
- **Copier-aware:** Yes — skips if `use_pattern_miner=false`.
- **None-safe:** Checks `session_count is None` before comparison — if ClaudeChic didn't provide the count, hint silently doesn't fire.
- **Uses:** `state.copier.use_pattern_miner`, `state.session_count` (from ClaudeChic kwargs), `state.path_exists()`.
- **Seam clean:** Session count is provided by ClaudeChic (which already has session management). Does NOT parse `.patterns_mining_state.json` — only checks existence. No coupling to Claude's internal path-hashing or the miner's JSON schema.
- **Parameterized:** `min_sessions` is configurable (default 10 from user prompt).

### 3.5 MCP Tools Empty Trigger

```python
@dataclass(frozen=True)
class McpToolsEmpty:
    """Hint: No user-created MCP tools in mcp_tools/."""
    tools_dir: str = "mcp_tools"

    def check(self, state: ProjectState) -> bool:
        # Count .py files excluding _-prefixed helpers
        return state.count_files_matching(self.tools_dir, "*.py") == 0

    @property
    def description(self) -> str:
        return "No user-created MCP tools found in mcp_tools/"
```

- **What it checks:** Whether `mcp_tools/` contains any user-created `.py` files (excluding `_cluster.py`, `_*.py` prefixed internal helpers).
- **Copier-aware:** No explicit check needed — template always creates `mcp_tools/`, but only cluster tools are pre-populated. If there are zero non-underscore `.py` files, user hasn't added custom tools.
- **Uses:** `state.count_files_matching()` — generic primitive with default `exclude_prefixes=("_",)`

### 3.6 Cluster Configured But Unused Trigger

```python
@dataclass(frozen=True)
class ClusterConfiguredUnused:
    """Hint: Cluster is configured but no jobs have been submitted."""

    def check(self, state: ProjectState) -> bool:
        if not state.copier.use_cluster:
            return False  # Feature disabled — skip hint
        # Cluster is enabled but no evidence of use:
        # - No job output directories
        # - No cluster log files
        # We check for absence of typical cluster artifacts
        return not state.path_exists("cluster_jobs") and not state.path_exists("logs/cluster")

    @property
    def description(self) -> str:
        return "Cluster backend is configured but appears unused"
```

- **What it checks:** Cluster feature enabled but no cluster artifacts (job directories, logs) exist.
- **Copier-aware:** Yes — skips if `use_cluster=false`.
- **Uses:** `state.copier.use_cluster`, `state.path_exists()`

### 3.7 Learn Command Trigger (Dynamic)

```python
@dataclass(frozen=True)
class CommandLesson:
    """A single command lesson — name for tracking, message for display."""
    name: str
    message: str

COMMAND_LESSONS: list[CommandLesson] = [
    # Ordered by workflow value (canonical list, agreed with UIDesigner).
    # Commands covered by state hints (e.g., /ao_project_team) are excluded
    # to avoid redundancy — the state hint is the right vehicle for those.
    CommandLesson("/diff",       "Try /diff — see what changed since your last commit"),
    CommandLesson("/resume",     "Try /resume — pick up a previous conversation where you left off"),
    CommandLesson("/worktree",   "Try /worktree — work on a branch in isolation without stashing"),
    CommandLesson("/compact",    "Try /compact — summarize the conversation to free up context"),
    CommandLesson("/model",      "Try /model — switch between Claude models mid-conversation"),
    CommandLesson("/shell",      "Try /shell — open a shell without leaving the TUI"),
]


@dataclass(frozen=True)
class LearnCommand:
    """Pick an untaught command and generate a hint for it.

    This is a DYNAMIC trigger — it has a dynamic message that changes
    based on which command is selected. It also reads lifecycle state
    (taught_commands) to pick the next untaught command.

    This is a controlled seam crossing: the trigger reads lifecycle state
    to avoid repeating commands. The alternative (separate tracking) would
    duplicate state management. Since taught_commands is a simple list
    owned by this trigger's lifecycle entry, the coupling is minimal.
    """

    def check(self, state: ProjectState) -> bool:
        return self._pick_command(state) is not None

    def get_message(self, state: ProjectState) -> str:
        cmd = self._pick_command(state)
        return cmd.message if cmd else ""

    def _pick_command(self, state: ProjectState) -> CommandLesson | None:
        taught = state.hints_state.get_taught_commands("learn-command")
        for cmd in COMMAND_LESSONS:
            if cmd.name not in taught:
                return cmd
        return None  # All commands taught

    @property
    def description(self) -> str:
        return "Teach the user a new slash command"
```

- **What it checks:** Whether there's an untaught command remaining in `COMMAND_LESSONS`.
- **Dynamic message:** `get_message(state)` returns the message for the next untaught command. This is the first trigger with a dynamic message — see `HintSpec.message` extension below.
- **Tracking:** `taught_commands` list stored in lifecycle state, appended to each time the hint fires.
- **No usage tracking dependency:** We track what we've _taught_, not what the user has _used_. ClaudeChic has analytics (`_track_command()` → PostHog), but it's fire-and-forget to an external service with no local history. Tracking "taught" is simpler and sufficient.
- **Priority 4:** Lowest — only appears if budget has room after project-state hints.
- **Lifecycle:** show-every-session with rotation. Fires once per cycle, picks next untaught command, records it. When all are taught, trigger returns `False`.
- **Copier-aware hints in the list:** `/ao_project_team` lesson could check `state.copier.use_project_team`, but since it's just a command lesson (not recommending a complex action), showing it even if project team is disabled is harmless — the user can still try the command.

### Dynamic Message Extension to HintSpec

```python
@dataclass(frozen=True)
class HintSpec:
    id: str
    trigger: TriggerCondition
    message: str | Callable[[ProjectState], str]  # static string or dynamic callable
    severity: Literal["info", "warning"] = "info"
    priority: int = 3
    lifecycle: HintLifecycle = ShowUntilResolved()
```

The engine resolves the message:
```python
msg = hint.message(state) if callable(hint.message) else hint.message
```

Simple duck typing. No new axis, no pipeline change. Static hints (all 6 project-state hints) pass a string. `learn-command` passes `trigger.get_message`.

---

## Step 4: Composite and Utility Triggers

Beyond the 7 core hints, the protocol supports composition:

### 4.1 Logical Combinators

```python
@dataclass(frozen=True)
class AllOf:
    """AND combinator — all conditions must be true."""
    conditions: tuple[TriggerCondition, ...]

    def check(self, state: ProjectState) -> bool:
        return all(c.check(state) for c in self.conditions)

    @property
    def description(self) -> str:
        return " AND ".join(c.description for c in self.conditions)


@dataclass(frozen=True)
class AnyOf:
    """OR combinator — at least one condition must be true."""
    conditions: tuple[TriggerCondition, ...]

    def check(self, state: ProjectState) -> bool:
        return any(c.check(state) for c in self.conditions)

    @property
    def description(self) -> str:
        return " OR ".join(c.description for c in self.conditions)


@dataclass(frozen=True)
class Not:
    """Negation — inverts a condition."""
    condition: TriggerCondition

    def check(self, state: ProjectState) -> bool:
        return not self.condition.check(state)

    @property
    def description(self) -> str:
        return f"NOT ({self.condition.description})"
```

These allow declarative composition like:
```python
AllOf((
    PatternMinerUnderutilized(min_sessions=10),
    Not(GitNotInitialized()),  # Only hint about miner if git is set up
))
```

### 4.2 Generic Filesystem Triggers

```python
@dataclass(frozen=True)
class PathNotExists:
    """Generic: path does not exist."""
    path: str

    def check(self, state: ProjectState) -> bool:
        return not state.path_exists(self.path)

    @property
    def description(self) -> str:
        return f"Path does not exist: {self.path}"


@dataclass(frozen=True)
class DirEmpty:
    """Generic: directory is empty or doesn't exist."""
    path: str

    def check(self, state: ProjectState) -> bool:
        return state.dir_is_empty(self.path)

    @property
    def description(self) -> str:
        return f"Directory is empty: {self.path}"


@dataclass(frozen=True)
class FileContentMatches:
    """Generic: file contains a regex pattern."""
    path: str
    pattern: str

    def check(self, state: ProjectState) -> bool:
        return state.file_contains(self.path, self.pattern)

    @property
    def description(self) -> str:
        return f"File {self.path} matches /{self.pattern}/"


```

---

## Step 5: Custom Trigger Extension Point

Users extend by writing any class (or function) that satisfies the `TriggerCondition` protocol:

```python
# In project's onboarding_custom.py or similar:

from dataclasses import dataclass
from hints.triggers import ProjectState


@dataclass(frozen=True)
class MyLabSpecificCheck:
    """Check if the lab's data directory is mounted."""
    mount_point: str = "/nrs/spruston"

    def check(self, state: ProjectState) -> bool:
        from pathlib import Path
        return not Path(self.mount_point).is_dir()

    @property
    def description(self) -> str:
        return f"Data mount {self.mount_point} not available"
```

**Registration:** Custom triggers are registered in the hint registry (Python dataclass, not YAML — see the HintSpec below). The registry lives in the project, so users simply add entries:

```python
# In the project's hints/ folder
from hints.registry import HintSpec
from hints_custom import MyLabSpecificCheck

CUSTOM_HINTS = [
    HintSpec(
        id="lab-data-mount",
        trigger=MyLabSpecificCheck(mount_point="/nrs/spruston"),
        message="Lab data directory not mounted — check VPN connection",
        severity="warning",
    ),
]
```

**Protocol compliance is structural:** Any object with `.check(ProjectState) -> bool` and `.description: str` works. No base class inheritance required. This matches the MCP tools pattern in the template (`get_tools()` protocol).

---

## Step 6: HintSpec — The Registry Entry (Dataclass, not YAML)

Per Skeptic's feedback, the hint registry is Python code with dataclasses:

```python
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class HintSpec:
    """A single hint definition — a point in the composability crystal.

    This replaces the YAML registry from the initial composability analysis.
    Python dataclasses give us:
    - Type checking (triggers are real objects, not string references)
    - IDE support (autocomplete, go-to-definition)
    - No parsing layer (YAML→Python mapping is eliminated)
    - Trigger parameters are validated at import time
    """
    id: str
    trigger: TriggerCondition
    message: str
    severity: Literal["info", "warning"] = "info"
    lifecycle: Literal[
        "show-once", "show-until-resolved", "show-every-session"
    ] = "show-until-resolved"
```

### Built-in Registry

```python
# hints/hints.py — The default hint registry

BUILTIN_HINTS: list[HintSpec] = [
    HintSpec(
        id="git-setup",
        trigger=GitNotInitialized(),
        message="No git repo detected — spawn a Git agent to set one up",
        severity="warning",
        lifecycle="show-until-resolved",
    ),
    HintSpec(
        id="guardrails-default-only",
        trigger=GuardrailsOnlyDefault(),
        message="Your guardrails only have the default rule — add custom rules in .claude/guardrails/rules.yaml",
        severity="info",
        lifecycle="show-until-resolved",
    ),
    HintSpec(
        id="project-team-discovery",
        trigger=ProjectTeamNeverUsed(),
        message="Try /ao_project_team for multi-agent workflows",
        severity="info",
        lifecycle="show-once",
    ),
    HintSpec(
        id="pattern-miner-ready",
        trigger=PatternMinerUnderutilized(min_sessions=10),
        message="You have 10+ sessions — run the pattern miner to find recurring corrections",
        severity="info",
        lifecycle="show-once",
    ),
    HintSpec(
        id="mcp-tools-empty",
        trigger=McpToolsEmpty(),
        message="Drop Python files into mcp_tools/ for custom tools",
        severity="info",
        lifecycle="show-once",
    ),
    HintSpec(
        id="cluster-ready",
        trigger=ClusterConfiguredUnused(),
        message="Your cluster backend is ready — try submitting a job",
        severity="info",
        lifecycle="show-once",
    ),
    HintSpec(
        id="learn-command",
        trigger=LearnCommand(),
        message=lambda state: LearnCommand()._pick_command(state).message,  # dynamic
        severity="info",
        priority=4,
        lifecycle="show-every-session",  # rotates through commands
    ),
]
```

---

## Step 7: Copier-Awareness Strategy

The key insight: **Copier-awareness is inside triggers, not in the engine.**

Each trigger that relates to an optional feature checks `state.copier.use_<feature>` as its first operation and returns `False` if the feature is disabled. This means:

- The engine doesn't need conditional logic per feature
- The registry is the same for all projects — triggers self-skip
- No YAML templating needed for the hint list
- Adding a new Copier feature just means adding a trigger that checks the new flag

| Hint | Copier-Aware? | Guards on |
|------|--------------|-----------|
| git-setup | No | Always relevant |
| guardrails-default-only | Yes | `use_guardrails` |
| project-team-discovery | Yes | `use_project_team` |
| pattern-miner-ready | Yes | `use_pattern_miner` |
| mcp-tools-empty | No | Always relevant (mcp_tools/ always exists) |
| cluster-ready | Yes | `use_cluster` |
| learn-command | No | Always relevant (rotates through available commands) |

---

## Step 8: File Structure

```
hints/
  __init__.py              # Public API: evaluate(send_notification, **kwargs)
  _engine.py               # Pipeline: discover hint files, run pipeline
  _types.py                # HintSpec, HintRecord, TriggerCondition protocol
  _state.py                # ProjectState (generic primitives), CopierAnswers,
                           #   HintStateStore, ActivationConfig
  hints.py                 # BUILTIN_HINTS registry + built-in triggers (get_hints())
  # Users drop custom hint files here:
  my_lab_hints.py          # Custom hints, same get_hints() protocol
```

---

## Summary of Design Decisions

1. **Protocol, not ABC:** `TriggerCondition` is a `Protocol` — structural typing, no inheritance required.
2. **Frozen dataclasses everywhere:** Triggers, ProjectState, CopierAnswers — all immutable.
3. **ProjectState exposes generic primitives + ClaudeChic-provided context:** Filesystem: `path_exists()`, `dir_is_empty()`, `file_contains()`, `count_files_matching()`. ClaudeChic kwargs: `session_count` (and future fields). All kwargs-sourced fields are `Optional[T]` defaulting to `None` — triggers must None-check before use. No typed representations of other modules' internal state.
4. **Copier-awareness is per-trigger:** Each trigger self-skips if its feature is disabled. Engine doesn't branch on features.
5. **Python registry, not YAML:** `BUILTIN_HINTS` is a `list[HintSpec]` in Python code. Type-safe, IDE-friendly, no parsing layer.
6. **Combinators for composition:** `AllOf`, `AnyOf`, `Not` allow complex conditions without new trigger types.
7. **Extension via protocol compliance:** Users write any class with `.check()` and `.description` — duck typing via Protocol.
8. **No feature-specific helpers on ProjectState:** No `count_rules_in_guardrails()`, no `mcp_tool_files()`. Triggers compose generic primitives. This prevents `ProjectState` from accumulating feature-specific methods over time.
