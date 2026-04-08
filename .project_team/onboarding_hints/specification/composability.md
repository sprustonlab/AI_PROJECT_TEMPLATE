# Composability Analysis: Hints System

> **Revision 2** — Updated after user feedback: the hints system is NOT baked into ClaudeChic.
> It follows the MCP tools pattern: project-level folder discovered at startup.

## Domain Understanding

The system surfaces contextual hints to users of AI_PROJECT_TEMPLATE projects via ClaudeChic's toast notifications. It detects project state (e.g., no git repo, empty MCP tools directory, unused features) and shows relevant hints at the right moment.

**Architectural pivot:** The hints system lives in the **generated project**, not in ClaudeChic. ClaudeChic discovers it at startup, just like it discovers `mcp_tools/`. This matches the template's existing composition philosophy: ClaudeChic is a generic TUI; project-specific behavior lives in the project.

---

## Discovery Architecture (New)

### The MCP Tools Pattern

ClaudeChic already has a proven discovery pattern for `mcp_tools/`:

```
mcp_tools/           ← convention-based path (Path.cwd() / "mcp_tools")
  _cluster.py        ← underscore = helper, pre-loaded into sys.modules
  lsf.py             ← discovered: importlib loads it, calls get_tools(**kwargs)
  slurm.py           ← same protocol, different tool
```

**Discovery protocol:**
1. Path resolved by convention: `Path.cwd() / "mcp_tools"`
2. If directory missing → silently return empty list (no crash)
3. Pass 1: load `_*.py` helpers into `sys.modules["mcp_tools.<stem>"]`
4. Pass 2: load `*.py` (non-underscore), call `get_tools(**kwargs)` sentinel
5. Errors isolated per-file: log warning, continue

**Iron rule:** Discovery never crashes.

### Hints Replicates This Pattern

```
hints/               ← convention-based path (Path.cwd() / "hints")
  __init__.py        ← entry point: evaluate(send_notification, **kwargs) -> None
  _engine.py         ← pipeline engine (trigger → activation → lifecycle → present)
  _state.py          ← ProjectState builder + HintStateStore
  _types.py          ← HintSpec, HintRecord, protocol definitions
  hints.py           ← built-in hint definitions (the registry)
  my_custom_hints.py ← user-added hints (same protocol)
```

**ClaudeChic's only job:** At startup, check if `hints/` exists. If so, import `hints` and call:

```python
from claudechic.sessions import count_sessions

hints.evaluate(
    send_notification=self.notify,
    project_root=Path.cwd(),
    session_count=count_sessions(),  # ClaudeChic already has this
    **kwargs                          # forward-compatible for future context
)
```

**Kwargs data-availability convention:** All ClaudeChic-provided fields on `ProjectState`
are `T | None`, defaulting to `None`. `None` means "not provided" or "failed to compute."
Triggers that depend on optional data MUST check `is None` before use — if missing, the
trigger returns `False` (don't fire hints based on data we don't have).

```python
# In a trigger:
def check(self, state: ProjectState) -> bool:
    if state.session_count is None:
        return False  # Can't evaluate — data unavailable
    return state.session_count >= self.min_sessions
```

ClaudeChic passes context it already knows (session count, project root) as kwargs. The hints system consumes them without needing to query Claude's internals.

**The seam between ClaudeChic and hints is identical to the MCP tools seam:**
- ClaudeChic passes `send_notification` (the toast function) as a callback
- The hints module calls it with message strings
- ClaudeChic knows nothing about triggers, lifecycle, or activation
- The hints module knows nothing about Textual widgets or TUI internals

### Where Does `hints/` Live?

**Decision: Top-level, alongside `mcp_tools/`.**

| Option | Pros | Cons |
|--------|------|------|
| Top-level (`hints/`) | Matches `mcp_tools/` convention; visible; easy to find | Another top-level dir |
| Inside `.claude/` (`.claude/hints/`) | Groups with other Claude config | Hidden (dotfile); `.claude/` is for config, not runnable code |
| Inside `mcp_tools/` | No new directory | Wrong abstraction — hints aren't MCP tools |

Top-level wins because:
1. **Consistency:** Same pattern as `mcp_tools/` — convention-based, visible, discoverable
2. **Visibility:** Users see it, know it exists, can modify it
3. **Clean seam:** It's its own concern, not shoehorned into another directory's purpose

### How Does ClaudeChic Discover It?

**Convention-based path** (same as `mcp_tools/`):

```python
hints_dir = Path.cwd() / "hints"
if hints_dir.is_dir():
    # import and call entry point
```

Not config-driven. The convention IS the contract. If the folder exists, hints are available. If it doesn't, nothing happens.

### Discovery Protocol

**Single entry point** (differs from MCP tools' per-file discovery):

```python
# ClaudeChic calls:
import importlib.util
spec = importlib.util.spec_from_file_location("hints", hints_dir / "__init__.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.evaluate(send_notification=self.notify, **kwargs)
```

**Why single entry point, not per-file?** MCP tools are independent — each tool stands alone. Hints share infrastructure (engine, lifecycle state, activation config). A single `evaluate()` entry point lets the module manage its own internal composition. ClaudeChic doesn't need to understand the hint pipeline.

**But hint files ARE independently discoverable within the module.** The `_engine.py` walks `*.py` files (excluding `_`-prefixed) looking for `get_hints()` — same pattern as MCP tools, one level down:

```python
# hints/_engine.py discovers hint files:
# hints/hints.py        → get_hints() → [HintSpec, HintSpec, ...]
# hints/my_custom.py    → get_hints() → [HintSpec, ...]
```

**Two-level discovery:**
1. ClaudeChic discovers `hints/` (convention path, single entry point)
2. Hints engine discovers hint files within `hints/` (MCP-style per-file discovery)

This gives us the best of both worlds: ClaudeChic stays simple (one import, one call), and users can drop in new hint files without editing a registry.

### Copier Integration

**`use_hints` becomes a Copier question:**

```yaml
# copier.yml
use_hints:
  type: bool
  default: true
  help: "Enable contextual hints? (can be toggled at runtime)"
```

**If `use_hints: false`:** Copier excludes the entire `hints/` directory. ClaudeChic's convention-based check finds nothing → no hints. No dead code.

**If `use_hints: true`:** Copier generates `hints/` with built-in hints. The set of built-in hints is Copier-aware — feature-specific triggers check `state.copier.use_<feature>` and return `False` if that feature is disabled.

**Copier exclusions (same pattern as mcp_tools):**
```yaml
_exclude:
  - "{% if not use_hints %}hints/{% endif %}"
```

---

## ProjectState Seam Discipline

> **Revision 2a** — Fixes seam leak identified by user: `PatternMinerState` as a typed field
> on `ProjectState` couples hints to the pattern miner's internal JSON schema.

**Principle:** `ProjectState` must expose only **generic filesystem primitives**, not typed representations of other modules' internal state. If a trigger needs to know about the pattern miner, it uses `path_exists()` and `file_contains()` — never a parsed `PatternMinerState` dataclass.

**Why this matters:** The pattern miner owns `.patterns_mining_state.json`. Its schema can change without notice. If `ProjectState` parses that file into a typed object, the hints system breaks when the miner changes. That's a cross-module dependency disguised as a data structure.

**The fix:**
- **Remove** `PatternMinerState` and `SessionInfo` as typed fields on `ProjectState`
- **Keep** `CopierAnswers` — `.copier-answers.yml` is a stable Copier contract, not an internal implementation detail. **Prerequisite:** template must include `template/{{_copier_conf.answers_file}}.jinja` for Copier to generate this file. Graceful fallback if missing: defaults match `copier.yml` defaults (one source of truth)
- **Keep** generic filesystem helpers: `path_exists()`, `dir_is_empty()`, `file_contains()`, `count_files_matching()`
- **Add** `count_session_dirs()` — counts directories in `.claude/projects/` (filesystem primitive, no parsing)

**Pattern miner trigger becomes:**
```python
# BEFORE (leaky — parses miner's internal state):
state.miner.exists  # requires PatternMinerState with parsed JSON fields

# AFTER (clean — filesystem primitives only):
state.path_exists(".patterns_mining_state.json")  # file exists = miner has run
```

**Session count provided by ClaudeChic via kwargs:**
Claude stores sessions at `~/.claude/projects/<hashed-path>/` (user HOME, not project root). Rather than coupling hints to Claude's path-hashing logic, ClaudeChic passes `session_count` as a kwarg to `evaluate()`. ClaudeChic already has session management (session browser, `/resume`). The hints system receives it as data — no filesystem coupling, clean seam.

**What `ProjectState` exposes (complete list):**
```python
@dataclass(frozen=True)
class ProjectState:
    root: Path                   # Project root (absolute)
    copier: CopierAnswers        # .copier-answers.yml (stable Copier contract)
    session_count: int | None = None   # From ClaudeChic kwargs (None = not provided)

    # --- Generic filesystem primitives ---
    def path_exists(self, relative: str) -> bool: ...
    def dir_is_empty(self, relative: str) -> bool: ...
    def file_contains(self, relative: str, pattern: str) -> bool: ...
    def count_files_matching(self, relative_dir: str, glob: str) -> int: ...
```

**Data sources:**
- `root`, `session_count` — provided by ClaudeChic via `evaluate()` kwargs
- `copier` — read from `.copier-answers.yml` by the hints module (defaults to `copier.yml` defaults if file missing)
- Filesystem primitives — read project files at `root`

**Version safety:** If an older ClaudeChic doesn't pass `session_count`, it defaults to `None`. Triggers check `is None` and return `False` — no crashes, no false positives. Current ClaudeChic uses `claudechic.sessions.count_sessions()` which always returns a real int (0 if no sessions yet), so `None` only occurs with old/broken versions.

No typed fields for other modules' internal state. Triggers compose these primitives to check whatever they need.

---

## Identified Axes

The axes remain the same, but their **location** changes: all axis implementations live in the project's `hints/` folder, not in ClaudeChic.

### 1. **TriggerCondition** — What is checked
- **Values:** file-existence, directory-empty, file-content-match, session-count-threshold, config-state, command-never-used, custom-callable
- **Why independent:** Pure function: `(project_state) -> bool`. Independent of timing, presentation, lifecycle, activation.
- **Lives in:** `hints/hints.py` (built-in), `hints/*.py` (user-added)
- **Seam discipline:** Triggers use only `ProjectState` filesystem primitives. No typed representations of other modules' state.
- **Deep-dive:** See `specification/axis_trigger_condition.md`

### 2. **EvaluationTiming** — When triggers are checked
- **V1 values:** startup + periodic (every 2 hours)
- **Why independent:** When to check is orthogonal to what to check. The same pipeline runs at startup and at 2h — triggers, lifecycle, activation are all unaware of timing.
- **Lives in:** ClaudeChic calls `evaluate()` at startup and via `set_interval(7200, ...)`. The hints module doesn't know or care when it's called.
- **Budget:** 2 toasts per evaluation cycle. Lifecycle prevents re-showing (ShowOnce checks `times_shown`), so the 2h cycle only surfaces NEW or CHANGED hints.

### 3. **Presentation** — How hints reach the user
- **V1 value:** toast only (via `send_notification` callback)
- **Why independent:** The callback is injected by ClaudeChic. The hints module never imports Textual.
- **Lives in:** The seam itself — `send_notification` is the presentation protocol
- **Key insight:** By passing `send_notification` as a callback, presentation is fully decoupled. The hints module could run in a non-Textual context (e.g., CLI) by passing a different callback.

### 4. **HintLifecycle** — How a hint progresses through states
- **Values:** show-once, show-until-resolved, show-N-times, show-every-session, cooldown-period
- **Why independent:** Stateful display policy, independent of trigger logic or presentation
- **Lives in:** `hints/_engine.py` + `hints/_state.py`
- **State file:** `.claude/hints_state.json` (lifecycle's private state, no other module touches it)
- **Deep-dive:** See `specification/axis_hint_lifecycle.md`

### 5. **Activation** — Whether hints are on or off
- **Values:** enabled, disabled, per-hint-override
- **Why independent:** User preference gate, independent of everything else
- **Lives in:** `hints/_state.py` reads/writes `activation` section of `.claude/hints_state.json`
- **User controls:** `/hints on|off|disable <id>|enable <id>|status`
- **Deep-dive:** See `specification/axis_activation.md`

---

## Revised Compositional Law

**The law is now two-level:**

### Level 1: ClaudeChic ↔ Hints Module (Discovery Seam)

```
ClaudeChic                          hints/
    |                                    |
    |-- Path.cwd() / "hints" --------->|
    |   exists? import. call evaluate()  |
    |-- send_notification, project_root, |
    |   session_count ----------------->|  (kwargs: context ClaudeChic already has)
    |                                    |
    |<-- send_notification(msg, sev) ----|
    |   (callback, no Textual imports)   |
```

**Law:** ClaudeChic provides `send_notification`. The hints module provides `evaluate()`. They share only the callback signature. Neither imports the other's internals.

### Level 2: Within Hints Module (Hint Pipeline)

```
For each HintSpec from discovered hint files:
    1. Activation.is_active(hint_id)           → skip if False
    2. TriggerCondition.check(project_state)    → skip if False
    3. HintLifecycle.should_show(hint_id, store) → skip if False
    4. send_notification(hint.message, hint.severity)
    5. HintLifecycle.record_shown(hint_id, store)
```

**Law:** The `HintRecord` data object crosses all internal seams. Each stage is a pure filter/function. No stage knows about any other's internals.

---

## Revised Seam Analysis

### Seam 0 (NEW): ClaudeChic ↔ Hints Module
- **What crosses:** `send_notification` callback (ClaudeChic → hints), toast messages (hints → ClaudeChic)
- **What doesn't cross:** Textual widgets, app state, TUI internals
- **Swap test:** Replace ClaudeChic with a CLI that prints messages — hints code unchanged ✅
- **Swap test:** Replace hints/ with a different module exporting `evaluate()` — ClaudeChic code unchanged ✅
- **Pattern match:** Identical to `mcp_tools/` seam (kwargs in, tool results out)

### Seam 1: TriggerCondition ↔ HintRecord (clean, unchanged)
### Seam 2: HintRecord ↔ Presentation (clean, now via callback)
### Seam 3: HintRecord ↔ HintLifecycle (clean, unchanged)
### Seam 4: Activation ↔ Everything (clean, unchanged)

### Previous Potential Dirty Seam: TriggerCondition ↔ EvaluationTiming
- **Status:** Resolved by architecture. Triggers are pure functions of disk state. ClaudeChic controls when `evaluate()` is called. Triggers don't know or care about timing.

---

## Revised File Structure

```
project_root/
  hints/                         ← Copier generates if use_hints=true
    __init__.py                  ← Entry point: evaluate(send_notification, **kwargs)
    _engine.py                   ← Pipeline: discover hints, run pipeline, manage flow
    _types.py                    ← HintSpec, HintRecord, TriggerCondition protocol
    _state.py                    ← ProjectState builder, HintStateStore, ActivationConfig
    hints.py                     ← Built-in hints (6 from user prompt), get_hints() -> list
    # Users add files here:
    my_lab_hints.py              ← Custom hints, same get_hints() protocol

  .claude/
    hints_state.json             ← ALL hints-system state (activation + lifecycle)
```

**Self-containment principle:** Delete `hints/` + `.claude/hints_state.json` and the system is fully gone. No orphaned config anywhere.

**State file structure (`.claude/hints_state.json`):**
```json
{
  "version": 1,
  "activation": {"enabled": true, "disabled_hints": []},
  "lifecycle": {"git-setup": {"times_shown": 1, "last_shown": "..."}}
}
```
Both activation and lifecycle state in one file, with independent sections. Exclusively owned by `hints/_state.py`.

**Axis → File mapping:**
| Axis | File(s) | Notes |
|------|---------|-------|
| TriggerCondition | `hints.py`, user `*.py` files | Each file exports `get_hints()` |
| EvaluationTiming | `__init__.py` | ClaudeChic calls `evaluate()` at startup + every 2h |
| Presentation | Callback from ClaudeChic | Not a file — it's the seam itself |
| HintLifecycle | `_engine.py` + `_state.py` | `lifecycle` section in `.claude/hints_state.json` |
| Activation | `_state.py` | `activation` section in `.claude/hints_state.json` |

**Underscore convention (matches MCP tools):**
- `_engine.py`, `_types.py`, `_state.py` — infrastructure, not hint definitions
- `hints.py`, `my_custom.py` — hint definition files, discovered by engine

---

## Crystal Validation (Updated)

The crystal remains 2,100 configurations with no holes. The architectural pivot doesn't change the axes or their independence — it changes WHERE the code lives (project vs ClaudeChic) and HOW it's discovered (convention-based import).

The 10-point spot check from v1 still holds. The additional dimension (discovery) is not an axis — it's fixed infrastructure. There's exactly one way ClaudeChic discovers hints: convention path + `evaluate()` call.

---

## Impact on Axis Deep-Dives

### TriggerCondition (`axis_trigger_condition.md`)
- **Change:** Triggers now live in `hints/hints.py` in the project, not in ClaudeChic. The `ProjectState` interface and all built-in triggers are unchanged.
- **New consideration:** User-added hint files in `hints/*.py` use the same `get_hints()` → `list[HintSpec]` protocol. The engine discovers them like MCP tools discover tool files.

### HintLifecycle (`axis_hint_lifecycle.md`)
- **Change:** Lifecycle state file location is `.claude/hints_state.json`. The `HintStateStore` lives in `hints/_state.py` in the project.
- **No functional change.** Lifecycle is purely internal to the hints module.

### Activation (`axis_activation.md`)
- **Change (Rev 2a):** Activation config moved from `.claudechic.yaml` into `.claude/hints_state.json` alongside lifecycle state. Both are hints-system state, exclusively owned by `hints/_state.py`.
- **Self-containment:** The hints system touches only `hints/` (code) and `.claude/hints_state.json` (state). No dependency on `.claudechic.yaml` or any other external config file.
- **`/hints` command:** Can be implemented as an MCP tool in `mcp_tools/` that reads/writes `.claude/hints_state.json`. ClaudeChic doesn't need to know about hints activation.

---

## Summary of Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where does the hints system live? | Project-level `hints/` folder | Matches `mcp_tools/` pattern; visible; Copier-controlled |
| How does ClaudeChic find it? | Convention path: `Path.cwd() / "hints"` | Same as `mcp_tools/`; no config needed |
| What's the discovery protocol? | Single entry point: `hints.evaluate(send_notification, **kwargs)` | Hints is a system (not independent tools); needs shared infrastructure |
| How are hint files discovered? | Engine walks `*.py` (non-underscore) for `get_hints()` | MCP-style extensibility within the module |
| Is it a Copier question? | Yes: `use_hints` (default true) | Matches existing feature toggles; removes folder entirely if disabled |
| What does ClaudeChic know about hints? | Only: "if folder exists, import it, call evaluate()" | Minimal coupling; same knowledge level as mcp_tools |
