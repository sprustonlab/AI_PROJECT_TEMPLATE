# How This Codebase Gives Checkers Access to System State

**Requested by:** Coordinator
**Date:** 2026-04-04
**Tier of best source found:** T1 (Primary source code)

## Query

What pattern does this codebase already use for "give a checker access to system state"? Specifically: How do TriggerCondition checks access state? How does ProjectState work? Do guardrail hooks use context objects or call things directly?

---

## 1. TriggerCondition Checks: Frozen Dataclasses with a Context Object

### The Protocol

```python
# hints/_types.py lines 26-41
@runtime_checkable
class TriggerCondition(Protocol):
    def check(self, state: ProjectState) -> bool:
        """Return True if the condition is met (hint should fire).
        Must be: Pure, Side-effect-free, Fast (<50ms)."""
        ...

    @property
    def description(self) -> str: ...
```

**Every trigger receives the same `ProjectState` context object.** No trigger ever calls `os.path.exists()` directly, reads environment variables, or touches the filesystem. All state access goes through the `ProjectState` API.

### How triggers use it

```python
# hints/hints.py — 6 concrete triggers, all identical pattern:

class GitNotInitialized:
    def check(self, state: ProjectState) -> bool:
        return not state.path_exists(".git")          # filesystem via context

class GuardrailsOnlyDefault:
    def check(self, state: ProjectState) -> bool:
        if not state.copier.use_guardrails:            # copier answers via context
            return False
        has_extra = state.file_contains(               # file content via context
            self.rules_file, r"- id:\s*R0[2-9]")
        has_rules_d = state.count_files_matching(      # glob via context
            self.rules_dir, "*.yaml")
        return not (has_extra or has_rules_d > 0)

class PatternMinerUnderutilized:
    def check(self, state: ProjectState) -> bool:
        if not state.copier.use_pattern_miner:         # feature flag via context
            return False
        if state.session_count is None:                # injected metadata via context
            return False
        return (state.session_count >= self.min_sessions
                and not state.path_exists(self.miner_state_file))
```

### Key properties of this pattern

| Property | How |
|----------|-----|
| **Checkers are frozen dataclasses** | `@dataclass(frozen=True)` — immutable, no mutation |
| **Config in fields, state in argument** | `self.rules_file` = static config, `state` = runtime context |
| **Context is the only state interface** | No `os`, `Path`, `json`, `subprocess` imports in triggers |
| **Composable** | `AllOf`, `AnyOf`, `Not` combinators wrap triggers, pass `state` through |
| **Testable** | Mock `ProjectState` with fake data, test triggers in isolation |

---

## 2. ProjectState: A Frozen Read-Only Context Object

### The class

```python
# hints/_state.py lines 97-187
@dataclass(frozen=True)
class ProjectState:
    """Read-only context passed to every TriggerCondition.check()."""

    root: Path
    copier: CopierAnswers
    session_count: int | None = None

    # --- Generic filesystem primitives ---
    def path_exists(self, relative: str) -> bool:
        return (self.root / relative).exists()

    def dir_is_empty(self, relative: str) -> bool: ...
    def file_contains(self, relative: str, pattern: str) -> bool: ...
    def count_files_matching(self, relative_dir: str, glob: str, ...) -> int: ...

    @classmethod
    def build(cls, project_root: Path, **kwargs) -> ProjectState:
        root = Path(project_root).resolve()
        copier = CopierAnswers.load(root)
        return cls(root=root, copier=copier, session_count=kwargs.get("session_count"))
```

### Architecture decisions baked into this design

1. **Frozen** — built once, never mutated. Triggers can't corrupt shared state.

2. **Generic filesystem primitives, not typed domain objects.** The docstring explicitly says:
   > *"Does NOT expose typed representations of other modules' state."*

   There's no `state.guardrails_config` or `state.project_team_phase`. Instead, triggers use `state.path_exists(".ao_project_team")` and `state.file_contains("rules.yaml", r"R0[2-9]")`. The state object provides **access mechanisms**, not domain models.

3. **kwargs convention for extensibility.** `session_count` is `int | None`, with None meaning "not provided." The docstring says:
   > *"All ClaudeChic-provided fields are T | None, defaulting to None. Triggers that depend on a field MUST check for None first."*

   This means adding new context fields (like `current_phase: int | None`) is a backward-compatible change — existing triggers ignore it.

4. **Factory method separates construction from use.** `ProjectState.build()` reads disk (CopierAnswers.load). Triggers never read disk directly — they receive a pre-built state.

### How it's wired together

```python
# hints/__init__.py lines 54-56 — the engine builds state once:
project_state = ProjectState.build(
    project_root, session_count=session_count, **kwargs
)

# Then passes it to the pipeline, which passes it to every trigger:
# _engine.py: for hint in hints: if hint.trigger.check(project_state): ...
```

**One build, many checks.** State is computed once per evaluation cycle, then shared read-only across all triggers.

---

## 3. Guardrail Hooks: Direct Access, No Context Object

### bash_guard.py pattern

```python
# .claude/guardrails/hooks/bash_guard.py lines 22-26
data = json.loads(sys.stdin.read())           # Read stdin directly
session_id = data.get('session_id', 'unknown')
command = data.get('tool_input', {}).get('command', '')
cwd = data.get('cwd', os.getcwd())            # os.getcwd() fallback
ts = datetime.now(timezone.utc).strftime(...)  # Direct datetime call

# Path resolution
_script_dir = Path(__file__).resolve().parent
_guardrails_dir = str(_script_dir.parent)
os.environ.setdefault('GUARDRAILS_DIR', _guardrails_dir)

# Rule evaluation — inline regex, direct variable access
if re.search(r'(?:^|&&|\|\||;)\s*pytest\b', command):
    _matched_rules.append((1, 'R01', 'deny', "...message..."))
```

### How role_guard is accessed

```python
# bash_guard.py lines 108-111
sys.path.insert(0, _guardrails_dir)        # Modify sys.path directly
import role_guard as _rg                    # Import at module level

# Per-rule: call role_guard functions directly
_pcode, _pmsg = _rg.check_role(
    allow=None, block=['Subagent'],
    enforce='deny', message='...')
```

### Key properties of this pattern

| Property | How |
|----------|-----|
| **No context object** | Variables extracted from stdin, used directly |
| **No abstraction layer** | `re.search()`, `os.getcwd()`, `Path(__file__)` called inline |
| **Auto-generated code** | Not meant to be human-maintained — generated by `generate_hooks.py` |
| **Module-level execution** | No functions, no classes — top-level script that runs and exits |
| **Imports are conditional** | `import role_guard` only emitted if any rule needs role-gating |

### Why hooks don't use context objects

The hooks are **generated code**, not human-written code. They're optimized for:
1. **Startup speed** — no object allocation, no factory methods
2. **Minimal imports** — only what's needed for the rules present
3. **Code generation simplicity** — emit flat if/elif blocks, not method calls

The generator (`generate_hooks.py`) is the "abstraction layer" — it reads structured rules and emits flat code. The generated hooks are the **compiled output**, not the source of truth.

---

## 4. The Two Patterns Compared

| Dimension | Hints System (Triggers) | Guardrail Hooks |
|-----------|------------------------|-----------------|
| **State access** | Context object (`ProjectState`) | Direct reads (`sys.stdin`, `os.getcwd()`) |
| **Abstraction** | Protocol + frozen dataclass | Flat generated script |
| **Extensibility** | User adds trigger classes | User adds rules to YAML |
| **Testability** | Mock ProjectState | Subprocess with piped stdin |
| **Who writes the code** | Humans (hints.py) | Machine (generate_hooks.py) |
| **Lifecycle** | Imported, called repeatedly | Exec'd once per tool invocation, exits |
| **State object** | Built once, shared read-only | Extracted from stdin, used inline |

---

## 5. Which Pattern Should the Check Protocol Follow?

### Answer: The hints pattern (context object), NOT the hooks pattern.

**Reasoning:**

1. **Checks are human-written**, like triggers. Users define verification logic for tutorial steps. They should get a clean API, not raw `os` calls.

2. **Checks need the same state primitives triggers need** — path_exists, file_contains, count_files_matching. Plus command execution (which triggers deliberately don't have).

3. **Checks should be testable in isolation.** A context object lets you mock filesystem state without temp directories.

4. **Hooks are generated code for a different concern.** Hooks run in a subprocess, receive stdin from Claude Code, and must exit with a code. Checks run in-process, receive a context, and return a result.

### What CheckContext should look like

Following ProjectState's design exactly:

```python
@dataclass(frozen=True)
class CheckContext:
    """Read-only context passed to every Check.verify().

    Same design as ProjectState:
    - Frozen (immutable)
    - Generic primitives (not domain-typed)
    - kwargs convention (T | None for optional fields)
    - Factory method for construction
    """

    root: Path
    phase: int | None = None
    env: dict[str, str] | None = None  # for command checks needing env vars

    # --- Filesystem primitives (same as ProjectState) ---

    def path_exists(self, relative: str) -> bool:
        return (self.root / relative).exists()

    def file_contains(self, relative: str, pattern: str) -> bool:
        p = self.root / relative
        if not p.is_file():
            return False
        try:
            return bool(re.search(pattern, p.read_text(encoding="utf-8")))
        except OSError:
            return False

    def count_files_matching(self, relative_dir: str, glob: str) -> int:
        d = self.root / relative_dir
        if not d.is_dir():
            return 0
        return sum(1 for _ in d.glob(glob))

    # --- Command execution (NEW — triggers don't have this) ---

    def run_command(self, cmd: list[str], timeout: float = 30.0) -> CommandResult:
        """Run a command and return its result. Checks may need this."""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, cwd=str(self.root),
                env=self.env or os.environ,
            )
            return CommandResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            return CommandResult(returncode=-1, stdout="", stderr=str(e))

    @classmethod
    def build(cls, project_root: Path, **kwargs) -> CheckContext:
        return cls(
            root=Path(project_root).resolve(),
            phase=kwargs.get("phase"),
            env=kwargs.get("env"),
        )
```

### Why not just reuse ProjectState directly?

**Concern separation.** ProjectState says:
> *"Does NOT expose typed representations of other modules' state."*

And:
> *"Triggers read ONLY from disk/config, never from live UI state."*

Checks need `run_command()` — a side-effecting operation that triggers explicitly exclude. Putting `run_command()` on ProjectState would violate its "pure, side-effect-free" contract.

But CheckContext should **share the filesystem primitives**. Two options:

**Option A: Duplicate the methods** (~15 lines)
```python
# CheckContext has its own path_exists(), file_contains(), etc.
# Identical implementation, separate class.
```

**Option B: Extract a shared mixin/base**
```python
class FilesystemContext:
    root: Path
    def path_exists(self, relative: str) -> bool: ...
    def file_contains(self, relative: str, pattern: str) -> bool: ...
    def count_files_matching(self, relative_dir: str, glob: str) -> int: ...

class ProjectState(FilesystemContext): ...  # hints
class CheckContext(FilesystemContext): ...   # checks, adds run_command()
```

**Recommendation: Option A for v1.** The methods are 5-10 lines each. Extracting a mixin adds an import dependency between the hints and checks systems, which are otherwise independent. Duplicate 15 lines now, refactor if a third system needs the same primitives.

---

## 6. The Check Protocol Itself

Following TriggerCondition's design:

```python
@runtime_checkable
class Check(Protocol):
    """Verification check for tutorial/workflow step completion.

    Same pattern as TriggerCondition:
    - Receives a frozen context object
    - Returns a result (not just bool — includes message and evidence)
    - Pure of side effects except run_command()
    - Composable via And/Or/Not combinators
    """

    def verify(self, ctx: CheckContext) -> CheckResult:
        """Return pass/fail with evidence."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description for debugging/logging."""
        ...


@dataclass(frozen=True)
class CheckResult:
    """Result of a verification check."""
    passed: bool
    message: str
    evidence: str = ""  # stdout, file contents, etc.
```

### Comparison with TriggerCondition

| Aspect | TriggerCondition | Check |
|--------|-----------------|-------|
| Method | `check(state) -> bool` | `verify(ctx) -> CheckResult` |
| Context | `ProjectState` (pure read) | `CheckContext` (read + commands) |
| Return | `bool` | `CheckResult` (bool + message + evidence) |
| Side effects | None (contract) | `run_command()` only |
| Composability | `AllOf`, `AnyOf`, `Not` | Same pattern |

The `Check` protocol is a **superset** of `TriggerCondition` — richer return type, richer context. But the structural pattern (frozen dataclass implementing a protocol, receiving a frozen context) is identical.

---

## Summary

| Question | Answer |
|----------|--------|
| How do TriggerConditions access state? | Via a **frozen `ProjectState` context object** passed to `check()`. Never directly. |
| How does ProjectState work? | **Frozen dataclass** with generic filesystem primitives. Built once by factory method, shared read-only. |
| Do hooks use context objects? | **No** — direct stdin/os/Path access. But hooks are generated code, not human-written. |
| Which pattern for Checks? | **The hints pattern** (context object). Checks are human-written like triggers, not generated like hooks. |
| What does CheckContext look like? | **Frozen dataclass** mirroring ProjectState's API, plus `run_command()` for verification. |
| Should we reuse ProjectState? | **No** — different contracts (pure vs side-effecting). Share by duplication for v1, extract mixin if needed later. |

**The codebase already has the answer: frozen context object + protocol + frozen dataclass checkers.** The Check system is TriggerCondition with a richer return type and a context that allows commands. Zero new patterns needed.
