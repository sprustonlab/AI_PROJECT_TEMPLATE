# Hints System — Full Specification (Rev 6)

## Overview

A contextual hints and feature discovery system for AI_PROJECT_TEMPLATE projects. Surfaces helpful hints via ClaudeChic toast notifications to help users discover template features (guardrails, project team, pattern miner, custom tools, cluster support).

**Key architectural decision:** The hints system lives in the **generated project** (not in ClaudeChic). ClaudeChic discovers it at startup via convention-based path, same pattern as `mcp_tools/`.

---

## Discovery Architecture

### How it works

1. **Copier question:** `use_hints: bool` (default `true`). If enabled, generates the `hints/` folder in the project.
2. **ClaudeChic discovery:** At startup, checks `Path.cwd() / "hints"`. If exists, imports and calls `evaluate(send_notification, **kwargs)`.
3. **Graceful absence:** If folder missing (old template, user deleted it, `use_hints=false`), nothing happens. No error, no warning.

### Discovery contract

```python
# ClaudeChic calls:
from hints import evaluate

from claudechic.sessions import count_sessions

await evaluate(
    send_notification=app.notify,   # callback: (message, severity, timeout) -> None
    project_root=Path.cwd(),
    session_count=count_sessions(), # ClaudeChic already has this; None if unavailable
    # **kwargs for forward-compatibility
)
```

ClaudeChic never imports hints internals. Hints module never imports Textual. The seam is: kwargs in, notification callback out.

### Version safety

- **Old ClaudeChic + new template:** Folder sits inert — no crash.
- **New ClaudeChic + old template:** No folder found — graceful skip.
- **Malformed folder:** Import fails → skip (same as MCP tools pattern).
- **Old ClaudeChic doesn't pass `session_count`** → defaults to `None` → triggers check `is None` and return `False`. Graceful.

---

## The Hint Pipeline

```
ProjectState (built at evaluation time)
    ↓
For each HintSpec in get_hints():
    1. Activation.is_active(hint_id) → skip if disabled     [cheapest filter]
    2. try: Trigger.check(project_state)                     [pure function, wrapped in try-except]
       except: log warning, skip hint                        [NEVER crash for a hint]
    3. Lifecycle.should_show(hint_id, state_store) → skip    [stateful history check]
    ↓
Collect passing hints → sort by (priority ASC, last_shown ASC, definition_order ASC)
    → take top 2 → schedule toasts with delays
    → record shown in HintStateStore
```

**Iron rule:** Every `trigger.check()` call is wrapped in try-except. Template-side trigger code can have bugs — discovery catches import errors, evaluation catches runtime errors.

### Evaluation Timing

The pipeline runs on two schedules:

| When | Trigger | Budget | ProjectState |
|------|---------|--------|--------------|
| **Startup** | 2s after app launch | 2 toasts | Built fresh |
| **Periodic** | Every 2 hours | 1 toast | Rebuilt fresh (filesystem may have changed) |

**How the periodic timer works in ClaudeChic:**
```python
# In app.py, after initial evaluate() call:
self._hints_timer = self.set_interval(7200, self._run_hints_evaluation)
```
Uses Textual's `set_interval()` — same pattern as the existing background process poller (2s interval) and review poller (5s interval). Timer is stored for lifecycle management and cancelled on app exit.

**Interaction with lifecycle:**
- The pipeline is **re-entrant** — calling it again at 2h is identical to calling it at startup
- `ShowOnce` hints shown at startup won't re-show at 2h — lifecycle checks `times_shown >= 1`
- `ShowUntilResolved` hints re-evaluate their trigger — if the user ran `git init` since startup, the trigger returns `False` and the hint disappears
- `CooldownPeriod` hints respect their cooldown across evaluation cycles
- The budget is **per evaluation cycle** (2 toasts at startup, 1 at each 2h cycle) — not per session total

**Why 2 hours?** Long enough that hints don't feel pushy. Short enough that if the user creates `mcp_tools/` files mid-session, they get acknowledged. The timer rebuilds `ProjectState` from disk each cycle, so filesystem changes are picked up.

### 5-Axis Composability Model

| Axis | v1 Scope | Expand Later |
|------|----------|-------------|
| **TriggerCondition** | Full — 7 built-in triggers + combinators + custom extension | ✓ |
| **EvaluationTiming** | Startup + periodic (2h) | on-focus, on-command |
| **Presentation** | Toast only | log, status-bar, `/hints` command |
| **HintLifecycle** | ShowOnce, ShowUntilResolved, CooldownPeriod | ShowNTimes, ShowEverySession |
| **Activation** | Global toggle + per-hint dismiss | — |

**Compositional law:** `HintRecord` is the shared protocol crossing all seams. Each axis is independent.

---

## Data Model

### HintSpec (the registry entry)

```python
@dataclass(frozen=True)
class HintSpec:
    id: str
    trigger: TriggerCondition
    message: str
    severity: Literal["info", "warning"] = "info"
    priority: int = 3                    # 1=blocking, 2=high-value, 3=enhancement
    lifecycle: HintLifecycle = ShowUntilResolved()  # object, not string — no version coupling
```

### ProjectState (read-only context for triggers)

```python
@dataclass(frozen=True)
class ProjectState:
    root: Path                          # Project root (absolute)
    copier: CopierAnswers               # Parsed .copier-answers.yml

    # ClaudeChic-provided context (all Optional, default None)
    session_count: int | None = None    # None = not provided / failed to compute

    # Generic filesystem primitives
    def path_exists(self, relative: str) -> bool: ...
    def dir_is_empty(self, relative: str) -> bool: ...
    def file_contains(self, relative: str, pattern: str) -> bool: ...
    def count_files_matching(self, relative_dir: str, glob: str,
                              exclude_prefixes: tuple[str, ...] = ("_",)) -> int: ...
```

**Data sources:**
- `root` — from ClaudeChic kwargs (passed into `evaluate()`)
- `session_count` — from ClaudeChic kwargs via `claudechic.sessions.count_sessions()`. `None` if not provided.
- `copier` — read from `.copier-answers.yml` by the hints module (graceful fallback: defaults match `copier.yml` defaults if file missing)
- Filesystem primitives — read project files relative to `root`

**Kwargs data-availability convention:** All ClaudeChic-provided fields are `T | None`, defaulting to `None`. `None` means "not provided" or "failed to compute." Triggers that depend on optional data MUST check `is None` before use — if `None`, return `False` (don't fire hints based on data we don't have). This convention scales to any future kwargs (model name, agent count, etc.) without new patterns.

**Seam discipline:** `ProjectState` exposes only generic filesystem primitives — no typed representations of other modules' internal state. Triggers compose these primitives to check whatever they need. `CopierAnswers` is allowed because `.copier-answers.yml` is a stable Copier contract (auto-generated by Copier in destination projects). If the file is missing (manually set up project, non-Copier project, user deleted it), feature flags default to their `copier.yml` defaults (one source of truth: `use_guardrails=True`, `use_project_team=True`, `use_pattern_miner=False`, `use_cluster=False`). This prevents broken hints — the Copier gate checks "is it installed?" while filesystem checks answer "has it been used?" Both are needed.

### State File (lifecycle + activation)

- **Location:** `.claude/hints_state.json` (project-scoped, gitignored)
- **Schema:**
  ```json
  {
    "version": 1,
    "activation": {
      "enabled": true,
      "disabled_hints": []
    },
    "lifecycle": {
      "git-setup": { "times_shown": 1, "last_shown_ts": 1774957452.69, "dismissed": false },
      "mcp-tools-empty": { "times_shown": 0, "last_shown_ts": null, "dismissed": false },
      "learn-command": { "times_shown": 3, "last_shown_ts": 1774957452.69, "dismissed": false, "taught_commands": ["/diff", "/resume", "/worktree"] }
    }
  }
  ```
- **Ownership:** Only `hints/_state.py` reads/writes this file. `ActivationConfig` owns the `activation` section; `HintStateStore` owns the `lifecycle` section. Independent sections, one file, one atomic write.
- **Graceful degradation:** Missing file = fresh start (all enabled), corrupt file = fresh start, clock skew = show hint
- **Note:** `disabled_hints` is personal preference. For multi-dev projects, suggest gitignoring `.claude/hints_state.json`.

---

## Built-in Hints (7)

| ID | Trigger | Message | Severity | Priority | Lifecycle |
|----|---------|---------|----------|----------|-----------|
| `git-setup` | No `.git` directory | "No git repo detected — launch a Git agent to set one up" | warning | 1 | show-until-resolved |
| `guardrails-default-only` | Only default R01 rule | "Your guardrails only have the default rule — add project-specific rules" | info | 2 | show-until-resolved |
| `project-team-discovery` | `.ao_project_team/` doesn't exist | "Try /ao_project_team to launch a multi-agent team for complex tasks" | info | 2 | show-once |
| `pattern-miner-ready` | `use_pattern_miner=true`, 10+ sessions, AND miner never run | "You have session history — run the Pattern Miner to find recurring corrections" | info | 3 | show-once |
| `mcp-tools-empty` | No user `.py` files in `mcp_tools/` | "Drop Python files into mcp_tools/ to add your own custom tools" | info | 3 | show-once |
| `cluster-ready` | Cluster enabled but no job artifacts | "Your cluster backend is configured and ready to use" | info | 3 | show-once |
| `learn-command` | Always (rotates through unlearned commands) | *Dynamic — see below* | info | 4 | show-every-session |

**Copier-awareness:** Each feature trigger self-skips if the feature was disabled during `copier copy`. Git and MCP tools hints always apply.

### The `learn-command` Hint (Dynamic)

This is a **rotating hint** — each evaluation cycle it picks ONE command the user hasn't been taught yet and shows a short description. It teaches the user one new command per session.

**How it works:**

```python
@dataclass(frozen=True)
class LearnCommand:
    """Pick an untaught command and generate a hint for it."""

    def check(self, state: ProjectState) -> bool:
        # Always True — there's always a command to teach
        # (until all commands have been taught, then returns False)
        return self._pick_command(state) is not None

    def get_message(self, state: ProjectState) -> str:
        """Dynamic message — changes based on which command is picked."""
        cmd = self._pick_command(state)
        return cmd.message  # e.g., "Try /diff — see what changed since your last commit"

    def _pick_command(self, state: ProjectState) -> CommandLesson | None:
        taught = state.hints_state.get_taught_commands()  # set of command names
        for cmd in COMMAND_LESSONS:
            if cmd.name not in taught:
                return cmd
        return None  # All commands taught
```

**Command lessons registry:**

```python
@dataclass(frozen=True)
class CommandLesson:
    name: str       # command name (for tracking)
    message: str    # one-line toast message

COMMAND_LESSONS: list[CommandLesson] = [
    # Ordered by workflow value (agreed with UIDesigner)
    CommandLesson("/diff",       "Try /diff — see what changed since your last commit"),
    CommandLesson("/resume",     "Try /resume — pick up a previous conversation where you left off"),
    CommandLesson("/worktree",   "Try /worktree — work on a branch in isolation without stashing"),
    CommandLesson("/compact",    "Try /compact — summarize the conversation to free up context"),
    CommandLesson("/model",      "Try /model — switch between Claude models mid-conversation"),
    CommandLesson("/shell",      "Try /shell — open a shell without leaving the TUI"),
]
```

**Why this is a single HintSpec, not 6 separate hints:**
- It occupies one slot in the priority system (priority 4 = lowest)
- It has one lifecycle policy (show-every-session, but rotate the message)
- It has one activation toggle (`/hints disable learn-command`)
- Adding a new command lesson is just appending to `COMMAND_LESSONS`, not adding a new HintSpec
- Commands already covered by state hints (e.g., `/ao_project_team` → `project-team-discovery`) are excluded to avoid redundancy

**Tracking which commands have been taught:**
- Stored in the lifecycle section of `.claude/hints_state.json`:
  ```json
  "learn-command": {
    "times_shown": 5,
    "last_shown_ts": 1774957452.69,
    "taught_commands": ["/diff", "/resume", "/worktree"]
  }
  ```
- `taught_commands` is a lifecycle-managed list — added to each time the hint fires
- When all commands are taught, the trigger returns `False` (nothing left to teach)

**No usage tracking dependency:** We don't need to know which commands the user has actually used — only which commands we've taught via hints. ClaudeChic does have analytics (`_track_command()` → PostHog), but that's fire-and-forget to an external service with no local history. Tracking "taught" is simpler and sufficient.

**Priority 4:** Lower than all project-state hints (1-3). Project-state hints are actionable and contextual. Command tips are nice-to-have. A `learn-command` hint only appears if there's room in the 2-toast budget after higher-priority hints are shown.

**Dynamic message pattern:**
This is the first hint with a dynamic message (all others are static strings). The `HintSpec` protocol needs a small extension:

```python
@dataclass(frozen=True)
class HintSpec:
    id: str
    trigger: TriggerCondition
    message: str | Callable[[ProjectState], str]  # static or dynamic
    severity: Literal["info", "warning"] = "info"
    priority: int = 3
    lifecycle: HintLifecycle = ShowUntilResolved()
```

The engine checks: if `message` is callable, call it with `project_state` to get the string. If it's a string, use it directly. Simple duck typing — no new axis, no pipeline change.

---

## UX Design

### Toast Delivery

- **2s delay** after app launch (lets UI settle)
- **6s gap** between the two toasts
- **Toasts persist** even if user starts typing — they're small, not in the way, expire naturally on timeout
- **First toast per session** includes suffix: "disable with `/hints off`"

### Toast Format

| Severity | Icon | Timeout |
|----------|------|---------|
| `information` | 💡 | 7 seconds |
| `warning` | ⚠️ | 10 seconds |

**Text style:** Advisory tone ("Try", "Consider"), no jargon ("custom tools" not "MCP"), actionable (includes command or path), max 2 lines.

### Priority & Throttling

- **Evaluation budget:** Max 2 toasts at startup, 1 toast per 2h cycle (user is deep in work; respect flow)
- **Sort key:** `(priority ASC, last_shown_ts ASC, definition_order ASC)`
  - `last_shown_ts = null` treated as `0` (never shown = highest priority within tier)
- **Natural rotation:** Least-recently-shown hints surface first within same priority tier
- **Cooldown:** Priority 3 hints have 1-cycle cooldown. Priority 1-2 have none. Priority 4 (`learn-command`) has no cooldown but only fires if budget has room.

### `/hints` Command (unified entry point)

`/hints` is the single command for everything — browse, toggle, manage:

| Command | Effect |
|---------|--------|
| `/hints` | Browse all currently-firing hints in chat view |
| `/hints off` | Disable all hints |
| `/hints on` | Re-enable hints (preserves per-hint dismissals) |
| `/hints status` | Show current state |
| `/hints reset` | Reset to defaults |

**Browse mode** (`/hints` with no args):
- Re-evaluates triggers at command time (resolved hints disappear)
- Groups: active first (with `[new]`/`[seen ×N]` badges), dismissed below separator
- `d` to dismiss individual hint, `a` to dismiss all
- Bypasses lifecycle suppression (shows badges, not hidden), respects activation gate

---

## Copier Integration

- **`use_hints: bool`** (default `true`) — Copier question during project generation
- If enabled: generates `hints/` folder with built-in hints and engine
- If disabled: folder excluded, ClaudeChic finds nothing at startup, no hints
- **Hints system is Copier-config aware internally:** triggers check `state.copier.use_<feature>` to skip hints for disabled features

### Prerequisite: answers file template

For `CopierAnswers` to work, the template must include:

```
template/{{_copier_conf.answers_file}}.jinja
```

This is a Copier convention — Copier processes this Jinja template during `copier copy` to generate `.copier-answers.yml` in the destination project. Without this file, Copier silently skips answers file generation and `CopierAnswers` falls back to `copier.yml` defaults.

**Why it's needed:** The hints system reads `.copier-answers.yml` to know which features the user enabled (guardrails, project team, pattern miner, cluster). Without it, triggers for optional features (pattern miner, cluster) won't fire because their defaults are `False`.

**Action item:** Add `template/{{_copier_conf.answers_file}}.jinja` to the AI_PROJECT_TEMPLATE repo. Standard content:

```jinja
# Changes here will be overwritten by Copier
{{ _copier_answers|to_nice_yaml }}
```

**Graceful fallback:** If `.copier-answers.yml` is missing (manually set up project, template missing the jinja file, user deleted it), `CopierAnswers.load()` returns defaults matching `copier.yml`: `use_guardrails=True`, `use_project_team=True`, `use_pattern_miner=False`, `use_cluster=False`. This prevents broken hints for features that aren't installed.

---

## File Structure (in generated project)

```
my-project/
├── hints/                       # Generated by Copier if use_hints=true
│   ├── __init__.py              # Public API: evaluate(send_notification, **kwargs)
│   ├── _engine.py               # Pipeline: activation → trigger → lifecycle → present
│   ├── _types.py                # HintSpec, HintRecord, TriggerCondition protocol, HintLifecycle protocol
│   ├── _state.py                # ProjectState, CopierAnswers, HintStateStore, ActivationConfig
│   └── hints.py                 # BUILTIN_HINTS: get_hints() -> list[HintSpec] (user-extensible)
├── mcp_tools/                   # (existing pattern — same discovery convention)
├── .claude/
│   └── hints_state.json         # Activation + lifecycle state (gitignored)
└── .copier-answers.yml          # Feature toggles read by CopierAnswers (may not exist)
```

Users extend by editing `hints.py` or adding new hint files.

---

## Key Invariants

1. **Triggers are pure functions** of `ProjectState` — no UI state, no side effects, <50ms each
2. **Every trigger.check() wrapped in try-except** — template-side code can have bugs, never crash for a hint
3. **Activation gate is checked first** (cheapest filter — dict lookup before disk I/O)
4. **Re-enabling a deactivated hint does NOT reset lifecycle state**
5. **Lifecycle and activation share one state file** (`.claude/hints_state.json`) with independent sections (`activation:` and `lifecycle:`)
6. **Never crash for a hint** — all state loading has graceful degradation
7. **Concurrency:** Last-writer-wins for MVP (showing a hint twice is annoying, not dangerous)
8. **ClaudeChic ↔ hints seam:** kwargs in, callback out. No cross-imports.

---

## Terminology (canonical)

| Term | Meaning |
|------|---------|
| **Hint** | An advisory message surfaced to the user (not tip/suggestion/nudge) |
| **Trigger** | A condition check that determines if a hint is relevant (not hook/check) |
| **Toast** | The Textual notification UI element |
| **Hint registry** | The declarative list of `HintSpec` entries |
| **Hints system** | The toggleable system as a whole |
| **Feature discovery** | Proactive surfacing of template features |

Feature canonical names: **Git agent**, **Guardrails**, **Project Team**, **Pattern Miner**, **custom tools** (user-facing) / MCP tools (internal), **Cluster backend**.
