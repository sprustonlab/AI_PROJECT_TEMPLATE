# Research: Can Checks Be TriggerConditions? (Checks-as-Hints)

**Author:** Researcher
**Date:** 2026-04-04
**Requested by:** Coordinator
**Tier of best source found:** T1 (codebase itself)

---

## Question: Could a failed Check surface as a hint instead of needing a /check-setup command?

Short answer: **Yes, but only for filesystem checks. Not for command-output checks.** The result is a significant simplification: `FileExistsCheck` and most setup checks become hint triggers, the `/check-setup` command becomes optional, and we eliminate one surface area.

---

## 1. How Hints Are Discovered (Registration)

**Location:** `hints/hints.py` → `get_hints()` (line 316)

Registration is a plain Python function that returns a list:

```python
def get_hints(*, get_taught_commands=None) -> list[HintSpec]:
    hints = list(_STATIC_HINTS)  # 6 static hints
    if get_taught_commands is not None:
        hints.append(...)         # 1 dynamic hint
    return hints
```

`_STATIC_HINTS` is a module-level list of `HintSpec` objects. No plugin system, no YAML, no scanning — just a Python list. Users extend by editing this file or overriding `get_hints()`.

**Key insight:** Adding a new hint is adding one `HintSpec(...)` entry to `_STATIC_HINTS`. That's it.

## 2. How Hints Are Triggered (Pipeline)

**Location:** `hints/_engine.py` → `run_pipeline()` (line 46)

The pipeline is linear — 6 stages:

```
Activation (dict lookup) → Trigger (call check()) → Lifecycle (history check)
→ Sort (priority) → Budget (top N) → Present (toast notification)
```

For each `HintSpec`, the trigger is evaluated as:

```python
triggered = hint.trigger.check(project_state)  # bool
```

Wrapped in try-except (IRON RULE: never crash for a hint). If the trigger returns `True` AND the lifecycle says "show", the hint enters the candidate pool.

## 3. How Hints Surface to the User

**Location:** `hints/_engine.py` lines 134-156

Hints surface as **toast notifications** — non-blocking messages that appear and auto-dismiss:

```python
send_notification(display_message, severity=textual_severity, timeout=timeout)
```

- `info` severity → 7 second timeout
- `warning` severity → 10 second timeout
- First toast of session gets " — disable with /hints off" suffix
- Budget: max 2 toasts per evaluation cycle
- Startup timing: 2s initial delay, 6s gap between toasts

## 4. The Two Protocols Side-by-Side

```
TriggerCondition (existing)          Check (proposed in spec)
─────────────────────────            ─────────────────────────
check(ProjectState) → bool           check(CheckContext) → CheckResult

Constraints:                         Constraints:
  - Pure (same state → same result)    - (none stated)
  - Side-effect-free                   - May run commands
  - Fast (<50ms)                       - May ask user questions
  - Reads only disk/config             - Returns rich evidence

Context receives:                    Context receives:
  - root: Path                         - project_root: Path
  - copier: CopierAnswers              - run_command(cmd) → CommandResult
  - session_count: int | None          - read_file(path) → str
  - path_exists(rel) → bool            - file_exists(path) → bool
  - file_contains(rel, pat) → bool     - ask_user(question) → str
  - count_files_matching(dir,glob)→int
  - dir_is_empty(rel) → bool
```

**The overlap:** Both have `check()` methods. Both receive a context bag with `project_root` and filesystem primitives. `ProjectState.path_exists()` ≈ `CheckContext.file_exists()`. `ProjectState.file_contains()` ≈ `CheckContext.read_file()` + regex.

**The gap:** `CheckContext` can run shell commands and ask user questions. `ProjectState` cannot. This is the design boundary.

## 5. What Existing Triggers Actually Do

Every existing trigger uses only `ProjectState` filesystem primitives:

| Trigger | What it checks | Method used |
|---------|---------------|-------------|
| `GitNotInitialized` | `.git` directory exists | `state.path_exists(".git")` |
| `GuardrailsOnlyDefault` | Rules file content + rules.d/ count | `state.file_contains()` + `state.count_files_matching()` |
| `ProjectTeamNeverUsed` | `.ao_project_team` dir exists | `state.path_exists()` |
| `PatternMinerUnderutilized` | Session count + state file exists | `state.session_count` + `state.path_exists()` |
| `McpToolsEmpty` | Python files in mcp_tools/ | `state.count_files_matching()` |
| `ClusterConfiguredUnused` | Cluster dirs exist | `state.path_exists()` × 2 |

**None of them run commands. None of them ask the user.** They all use fast filesystem checks via `ProjectState` primitives.

## 6. Which Checks Can Be Triggers? Which Cannot?

The spec defines three check types. Let's classify them:

### Can be a TriggerCondition: `FileExistsCheck`

```python
# Spec's FileExistsCheck
class FileExistsCheck:
    def check(self, ctx: CheckContext) -> CheckResult:
        exists = ctx.file_exists(self.path)
        return CheckResult(passed=exists, message=f"File {'found' if exists else 'not found'}: {self.path}")
```

This is **identical** to what `GitNotInitialized` already does:

```python
class GitNotInitialized:
    def check(self, state: ProjectState) -> bool:
        return not state.path_exists(".git")
```

Same operation. Different return type (bool vs CheckResult). Same speed. A `FileExistsCheck` is a `TriggerCondition` that returns extra evidence.

**Verdict: YES — wrap trivially.**

### Can be a TriggerCondition with care: `CommandOutputCheck`

```python
# Spec's CommandOutputCheck
class CommandOutputCheck:
    def check(self, ctx: CheckContext) -> CheckResult:
        result = ctx.run_command(self.command)  # RUNS A SHELL COMMAND
        matched = re.search(self.pattern, result.stdout)
        return CheckResult(passed=bool(matched), ...)
```

This **violates two TriggerCondition contracts:**
- "Side-effect-free" — running a command is a side effect
- "Fast (<50ms)" — `pixi --version` takes 200-500ms; `git config user.email` takes 50-100ms

**But look at what the hints system actually enforces:** The IRON RULE is "never crash for a hint" — trigger failures are caught by try-except. The <50ms guidance is a design contract, not a runtime assertion. No timer kills slow triggers.

**Verdict: POSSIBLE but needs a budget decision.** If we allow CommandOutputCheck triggers, startup evaluation takes 500ms-2s longer. Acceptable? Probably yes for a 2-toast budget, but the contract violation should be acknowledged.

### Cannot be a TriggerCondition: `ManualConfirm`

```python
# Spec's ManualConfirm
class ManualConfirm:
    def check(self, ctx: CheckContext) -> CheckResult:
        answer = ctx.ask_user(self.question)  # BLOCKS ON USER INPUT
        return CheckResult(passed=answer.lower() in ("yes", "y"), ...)
```

This **completely breaks the pipeline.** `run_pipeline()` is async but evaluates triggers synchronously in a loop. A blocking user prompt would halt all hint evaluation. And `ProjectState` has no `ask_user()` capability.

**Verdict: NO — fundamentally incompatible.** ManualConfirm is a gate check, not a trigger. It belongs in phase transitions, not hint evaluation.

## 7. The Adapter: `CheckTrigger`

A thin wrapper that bridges the two protocols:

```python
@dataclass(frozen=True)
class CheckTrigger:
    """Adapts a Check into a TriggerCondition. Fires when check FAILS."""

    check_impl: Check  # Any Check that doesn't need ask_user()
    _description: str = ""

    def check(self, state: ProjectState) -> bool:
        # Build a CheckContext from ProjectState
        ctx = CheckContext(project_root=state.root)
        try:
            result = self.check_impl.check(ctx)
            return not result.passed  # Hint fires when check FAILS
        except Exception:
            return False  # Fail-closed: broken check → no hint

    @property
    def description(self) -> str:
        return self._description or f"Check failed: {type(self.check_impl).__name__}"
```

**Usage — SSH setup hint without /check-setup:**

```python
HintSpec(
    id="ssh-key-missing",
    trigger=CheckTrigger(
        check_impl=FileExistsCheck("~/.ssh/id_ed25519"),
        _description="SSH key not found",
    ),
    message="No SSH key found — run: ssh-keygen -t ed25519 -C 'your_email'",
    severity="warning",
    priority=1,
    lifecycle=ShowUntilResolved(),
)
```

This hint fires at session startup if `~/.ssh/id_ed25519` doesn't exist, shows a toast notification, and stops showing once the file appears (ShowUntilResolved checks the trigger again).

**No `/check-setup` command needed.** The hint IS the check.

## 8. The Deeper Insight: Checks and Triggers Are the Same Thing at Different Resolutions

| Aspect | TriggerCondition | Check |
|--------|-----------------|-------|
| Input | ProjectState (read-only context) | CheckContext (read-only context) |
| Output | bool | CheckResult (bool + message + evidence) |
| Contract | Fast, pure, side-effect-free | No stated constraints |
| Purpose | "Should this hint show?" | "Is this setup step complete?" |

A `Check` is a `TriggerCondition` that returns evidence. A `TriggerCondition` is a `Check` that discards evidence.

The relationship is: **Check ⊃ TriggerCondition** (Check is the richer type).

### Proposed Unification

Instead of two separate primitives, define Check as the base and TriggerCondition as a projection:

```python
# Check is the primitive (returns evidence)
class Check(Protocol):
    def check(self, ctx: CheckContext) -> CheckResult: ...

# TriggerCondition is ALSO a Check (same method name, different context)
# The adapter bridges them:
class CheckTrigger:
    """Adapts Check → TriggerCondition. Fires on failure."""
    def check(self, state: ProjectState) -> bool:
        result = self.check_impl.check(CheckContext(project_root=state.root))
        return not result.passed
```

But **don't merge the protocols**. They have different contracts (fast vs. unconstrained) and different context bags (ProjectState vs. CheckContext). The adapter is the right seam.

## 9. What This Means for the Spec

### Simplification: /check-setup becomes optional

If failed checks surface as hints automatically, then `/check-setup` is a convenience command for running all checks at once and displaying a report — not the primary discovery mechanism.

**Before (spec's design):**
```
User runs /check-setup → sees a list of pass/fail checks
```

**After (checks-as-hints):**
```
User starts session → toast appears: "No SSH key found — run ssh-keygen..."
User starts session → toast appears: "git user.email not configured — run git config..."
(User can also run /check-setup for a full report)
```

The hint path is better UX — it's proactive, not reactive. The user doesn't need to know `/check-setup` exists.

### What stays in /check-setup

`/check-setup` retains value as a **batch diagnostic** — run all checks at once, see a full report with evidence. Useful for debugging, CI, and when a user asks "is my environment correct?" It consumes Checks directly (not through the hint pipeline), displaying `CheckResult.message` and `CheckResult.evidence`.

### What changes in the spec

1. **CheckTrigger adapter** (~15 lines) — bridges Check → TriggerCondition
2. **`CheckContext` must be buildable from `ProjectState`** — needs a factory: `CheckContext.from_project_state(state)`
3. **Setup checks register as hints** in `hints/hints.py` alongside existing hints
4. **`/check-setup` still exists** but as a diagnostic, not the primary surface
5. **CommandOutputCheck triggers get a "slow trigger" annotation** — acknowledged contract relaxation

### Recommended hint registrations for setup checks

```python
# In hints/hints.py — setup checks as hints
HintSpec(
    id="ssh-key-missing",
    trigger=CheckTrigger(FileExistsCheck("~/.ssh/id_ed25519")),
    message="No SSH key found — run: ssh-keygen -t ed25519",
    severity="warning",
    priority=1,
    lifecycle=ShowUntilResolved(),
)

HintSpec(
    id="git-email-missing",
    trigger=CheckTrigger(CommandOutputCheck("git config user.email", r".+@.+")),
    message="git user.email not set — run: git config --global user.email 'you@example.com'",
    severity="warning",
    priority=1,
    lifecycle=ShowUntilResolved(),
)

HintSpec(
    id="pixi-not-installed",
    trigger=CheckTrigger(CommandOutputCheck("pixi --version", r"pixi \d+")),
    message="pixi not found — install from https://pixi.sh",
    severity="warning",
    priority=1,
    lifecycle=ShowUntilResolved(),
)
```

## 10. Constraint: Budget and Timing

The hint pipeline has a budget of 2 toasts per evaluation. If 3 setup checks fail, only the top 2 (by priority) show. The third waits for the next session.

**This is actually fine.** Priority 1 (blocking) checks surface first. Once the user fixes one, the next surfaces. Progressive disclosure — don't overwhelm with 5 error toasts at once.

The startup delay (2s initial + 6s gap) means checks need to complete in <2s total for the first toast to appear on time. `FileExistsCheck`: ~1ms. `CommandOutputCheck("pixi --version", ...)`: ~300ms. Three checks total: ~600ms. Well within budget.

## Summary

| Check Type | Can be TriggerCondition? | Speed | Constraint Violation? |
|-----------|------------------------|-------|----------------------|
| `FileExistsCheck` | **Yes — trivially** | <1ms | None |
| `CommandOutputCheck` | **Yes — with acknowledged relaxation** | 50-500ms | "Fast <50ms" soft contract |
| `ManualConfirm` | **No — fundamentally incompatible** | Blocks indefinitely | Breaks pipeline completely |

**Recommendation:** Build the `CheckTrigger` adapter (~15 lines). Register setup checks as hints. Keep `/check-setup` as a batch diagnostic for explicit use. This eliminates one command surface and gives users proactive discovery instead of reactive diagnosis.

The key architectural insight: **a Check is a TriggerCondition that returns evidence.** The adapter bridges them without merging the protocols, preserving both contracts.
