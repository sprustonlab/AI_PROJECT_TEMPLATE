# Composability Response: CheckContext Necessity

**Reviewer:** Composability (Lead Architect)
**Prompt:** Do we need CheckContext as a class? Does removing it break seams or composability?

---

## Seam Analysis

CheckContext does NOT appear in any seam contract:

| Seam | Contract | CheckContext involved? |
|---|---|---|
| Check → Phase | `CheckResult` | No — gates consume results, not context |
| Check → Standalone | `CheckResult` | No — `/check-setup` consumes results |
| Phase → Guardrails | `phase_state.json` | No |
| Phase → Hints | `ActivePhase` | No |

CheckContext is an **input** to checks, not a **boundary** between components. Removing it changes how checks are called internally, but no seam consumer sees it.

---

## What Checks Actually Need

Looking at the three v1 built-ins:

| Check | Needs |
|---|---|
| `CommandOutputCheck` | Run a shell command, get stdout, match regex |
| `FileExistsCheck` | Resolve a path relative to project root, check existence |
| `ManualConfirm` | Ask the user a question, get yes/no |

The common denominator: `project_root: Path`. That's the one thing every check needs that it can't know on its own.

- `CommandOutputCheck` can call `subprocess.run()` directly — it already knows the command and timeout.
- `FileExistsCheck` can call `(project_root / path).exists()` — stdlib is fine.
- `ManualConfirm` can call `input()` — no abstraction needed.

---

## The Real Value of CheckContext

CheckContext does two things:

1. **Dependency injection for testing.** Mock `ctx.run_command()` instead of patching `subprocess.run`. This is real value — but only if checks are complex enough to warrant it.

2. **Shared timeout/truncation logic.** `run_command` wraps subprocess with timeout handling and output truncation. Without it, each check re-implements this.

Both are convenience, not architecture. The question is whether the convenience justifies the abstraction.

---

## Recommendation: Option 2 — Keep Thin, Rename

**Drop "sandboxed."** It's not sandboxed. Call it what it is.

**Rename to `CheckContext` (keep the name) but fix the description:**

```python
@dataclass(frozen=True)
class CheckContext:
    """Common inputs for checks: project root and system access helpers.

    Provides dependency injection for testing — mock this instead of
    patching subprocess and Path.
    """
    project_root: Path

    def run_command(self, cmd: str, timeout: float = 30.0) -> CommandResult:
        """Run a shell command with timeout. Returns stdout + return code."""
        ...

    def file_exists(self, path: str | Path) -> bool:
        """Check if path exists, resolved relative to project_root."""
        ...

    def read_file(self, path: str | Path) -> str:
        """Read file contents, resolved relative to project_root."""
        ...

    def ask_user(self, question: str) -> str:
        """Prompt the user and return their response."""
        ...
```

**Why not Option 1 (drop entirely):**

- Without CheckContext, the Check protocol becomes `check(project_root: Path) → CheckResult`. That works, but:
  - Every `CommandOutputCheck` re-implements `subprocess.run` + timeout + truncation (~10 lines each)
  - Testing requires patching `subprocess.run` at the module level instead of passing a mock context
  - Adding a new parameter later (e.g., `environment: dict` for cluster checks) requires changing every check's signature

- CheckContext is the [Parameter Object](https://refactoring.guru/introduce-parameter-object) pattern. It's 1 argument instead of N, and N can grow without breaking the protocol.

**Why not a bigger CheckContext:**

- No `cwd` — checks shouldn't change directory
- No `env` in v1 — add in v2 if cluster checks need it
- No `write_file` — checks observe, they don't mutate

---

## Impact on SPECIFICATION.md

One line changes. In section 2.1, the `CheckContext` docstring:

**Before:** `"""Sandboxed system access for checks."""`
**After:** `"""Common inputs for checks: project root and system access helpers."""`

Everything else — the protocol, the built-ins, the seams — stays the same. CheckContext is internal to the Check primitive. Nothing outside `checks/` depends on it.

---

## Summary

| Question | Answer |
|---|---|
| Does removing CheckContext break seams? | No — no seam references it |
| Does it make testing harder? | Yes — forces stdlib mocking instead of context injection |
| What's the minimal interface? | `project_root: Path` + `run_command()` helper |
| Keep or drop? | Keep thin. It's a parameter object + DI point. ~55 lines. Not worth removing. |
| What changes? | Drop "sandboxed" from docstring. That's it. |
