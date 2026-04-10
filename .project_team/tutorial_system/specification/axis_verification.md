# Axis Deep-Dive: Verification

## Purpose

Verification is the axis that answers: **"Did the user actually complete this step, and can we prove it?"** It is what prevents the failure mode called out in the project vision — "the agent claims success without verification."

Every verification is a **pure function of system state → result**. It does not know what content is being taught, how the user navigates between steps, or how guidance is delivered. It only knows how to check one thing and report what it found.

---

## 1. The `Verification` Protocol

```python
@runtime_checkable
class Verification(Protocol):
    """Pure function: context → result.

    A Verification checks a single observable property of the system
    (file exists, command produces expected output, config value matches).

    Contract:
    - Must be deterministic given the same system state.
    - Must not mutate system state (read-only).
    - Must complete in bounded time (timeout enforced by VerificationContext).
    - Must capture evidence (the actual output/value that was checked).

    Analogous to TriggerCondition in hints/_types.py, but returns a
    rich result instead of a bare bool.
    """

    def check(self, ctx: VerificationContext) -> VerificationResult:
        """Run the verification and return a structured result."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description for logging/debugging.

        Example: "Check that git remote -v contains a GitHub URL"
        """
        ...
```

**Design rationale:** Following the `TriggerCondition` pattern from `hints/_types.py`:
- `@runtime_checkable` enables duck typing — any object with `.check()` and `.description` works.
- Pure function contract matches `TriggerCondition.check(state) -> bool`, but with a richer return type.
- `description` property mirrors `TriggerCondition.description` — used for logging, not for presentation (presentation reads `VerificationResult.message`).

---

## 2. `VerificationContext` — What Verifiers Receive

```python
@dataclass(frozen=True)
class VerificationContext:
    """Sandboxed environment for running verifications.

    Provides controlled access to system inspection capabilities.
    All operations are read-only — verifiers cannot modify the system.

    The engine constructs this once per verification run and passes it in.
    Verifiers never construct their own context.
    """

    run_command: Callable[[str], CommandResult]
    """Execute a shell command and capture output.

    The engine wraps this with:
    - A timeout (default 10s, configurable per-step)
    - Read-only enforcement where possible (no sudo, no rm, no write redirects)
    - Output capture (stdout + stderr + exit code)

    Example: ctx.run_command("git remote -v")
    """

    read_file: Callable[[str], str | None]
    """Read a file's contents. Returns None if file doesn't exist.

    Path is resolved relative to the tutorial's working directory.
    Symlinks are followed. Binary files return None.

    Example: ctx.read_file("~/.ssh/id_ed25519.pub")
    """

    file_exists: Callable[[str], bool]
    """Check if a file or directory exists.

    Example: ctx.file_exists("~/.ssh/id_ed25519")
    """

    ask_user: Callable[[str], bool]
    """Prompt the user with a yes/no question. For ManualConfirm only.

    Example: ctx.ask_user("Did you click the verification link in the GitHub email?")
    """

    working_dir: str
    """The tutorial's working directory (for resolving relative paths)."""

    timeout_seconds: float = 10.0
    """Maximum time for any single operation (command, file read)."""


@dataclass(frozen=True)
class CommandResult:
    """Output of a command executed through VerificationContext.run_command."""

    exit_code: int
    stdout: str
    stderr: str
```

**Sandboxing strategy:**

The `VerificationContext` is the **only** way verifiers interact with the system. The engine constructs it with sandboxed implementations:

1. **`run_command`** — The engine wraps subprocess execution with:
   - Timeout enforcement (kills process after `timeout_seconds`)
   - Command allowlisting (optional, per-tutorial): only commands matching a pattern are permitted
   - No interactive commands (stdin is closed)
   - Output truncation (cap at 10KB to prevent memory issues)

2. **`read_file`** — Resolves `~` and relative paths, checks against path traversal, returns `None` for missing/binary files.

3. **`file_exists`** — Thin wrapper around `pathlib.Path.exists()` with home directory expansion.

4. **`ask_user`** — Delegates to the Presentation axis (which decides _how_ to ask). The Verification axis only sees the bool result.

**Why callables, not methods on a class?** Frozen dataclass with callables makes the sandboxing explicit and testable — in tests, you inject mock callables. This matches the functional style of the hints system.

---

## 3. `VerificationResult` — What Verifiers Return

```python
@dataclass(frozen=True)
class VerificationResult:
    """Outcome of a verification check.

    This is the seam object — the ONLY thing other axes see from Verification.
    Progression reads `passed`. Presentation reads `message` and `evidence`.
    Neither knows what verification was performed or how.

    Analogous to HintRecord in hints/_types.py — a fully-resolved,
    seam-crossing data object with no behavior.
    """

    passed: bool
    """Whether the verification succeeded."""

    message: str
    """Human-readable explanation of what was checked and what happened.

    On success: "✓ git remote -v shows GitHub URL: git@github.com:user/repo.git"
    On failure: "✗ git remote -v did not contain a GitHub URL. Got: (empty output)"
    """

    evidence: str | None = None
    """Raw output/value that proves the result.

    For command checks: the actual stdout/stderr.
    For file checks: the file path that was checked (and first N bytes if relevant).
    For config checks: the actual config value found.
    For manual confirms: None (user attestation, no system evidence).
    For compound checks: concatenated evidence from all sub-checks.

    Evidence is stored in tutorial state for audit trail / session resumption.
    """

    check_description: str = ""
    """What was checked (from Verification.description). For logging only."""

    sub_results: tuple[VerificationResult, ...] = ()
    """For CompoundCheck: individual results of each sub-check.
    Empty for non-compound verifications.
    """
```

**Key design decisions:**
- **Frozen dataclass** — immutable, like all seam-crossing objects in this codebase.
- **`evidence` is optional** — `ManualConfirm` has no system evidence; the user's word is the proof.
- **`sub_results` for compound checks** — enables presentation to show _which_ sub-check failed, not just "compound check failed." Uses `tuple` (not `list`) to maintain frozen semantics.
- **`check_description`** — copied from `Verification.description` at check time. Decouples the result from the verifier instance.

---

## 4. Built-in Verification Implementations

### 4.1 `CommandOutputCheck`

```python
@dataclass(frozen=True)
class CommandOutputCheck:
    """Runs a command and checks output against an expected pattern.

    Examples:
    - CommandOutputCheck(command="git remote -v", pattern=r"github\.com")
    - CommandOutputCheck(command="ssh -T git@github.com", pattern=r"successfully authenticated", check_stderr=True)
    - CommandOutputCheck(command="python --version", pattern=r"Python 3\.\d+")
    """

    command: str
    """Shell command to execute."""

    pattern: str
    """Regex pattern that stdout (or stderr) must match."""

    check_stderr: bool = False
    """If True, check stderr instead of stdout (some tools output to stderr)."""

    expected_exit_code: int | None = None
    """If set, also verify the exit code matches. None = don't check exit code."""

    @property
    def description(self) -> str:
        target = "stderr" if self.check_stderr else "stdout"
        return f"Run `{self.command}`, check {target} matches /{self.pattern}/"

    def check(self, ctx: VerificationContext) -> VerificationResult:
        result = ctx.run_command(self.command)
        output = result.stderr if self.check_stderr else result.stdout

        pattern_match = bool(re.search(self.pattern, output))
        exit_code_ok = (
            self.expected_exit_code is None
            or result.exit_code == self.expected_exit_code
        )

        passed = pattern_match and exit_code_ok

        if passed:
            message = f"✓ `{self.command}` output matches expected pattern"
        elif not pattern_match:
            message = (
                f"✗ `{self.command}` output did not match /{self.pattern}/. "
                f"Got: {_truncate(output, 200)}"
            )
        else:
            message = (
                f"✗ `{self.command}` exited with code {result.exit_code}, "
                f"expected {self.expected_exit_code}"
            )

        return VerificationResult(
            passed=passed,
            message=message,
            evidence=f"stdout: {result.stdout}\nstderr: {result.stderr}\nexit_code: {result.exit_code}",
            check_description=self.description,
        )
```

### 4.2 `FileExistsCheck`

```python
@dataclass(frozen=True)
class FileExistsCheck:
    """Checks that a file or directory exists.

    Examples:
    - FileExistsCheck(path="~/.ssh/id_ed25519")
    - FileExistsCheck(path="~/.ssh/id_ed25519.pub")
    - FileExistsCheck(path=".git/config")
    """

    path: str
    """Path to check (supports ~ expansion and relative paths)."""

    @property
    def description(self) -> str:
        return f"Check file exists: {self.path}"

    def check(self, ctx: VerificationContext) -> VerificationResult:
        exists = ctx.file_exists(self.path)
        if exists:
            message = f"✓ {self.path} exists"
        else:
            message = f"✗ {self.path} not found"

        return VerificationResult(
            passed=exists,
            message=message,
            evidence=f"file_exists({self.path}) = {exists}",
            check_description=self.description,
        )
```

### 4.3 `ConfigValueCheck`

```python
@dataclass(frozen=True)
class ConfigValueCheck:
    """Checks a config value matches an expected pattern.

    Runs a command that outputs a config value, then checks it.

    Examples:
    - ConfigValueCheck(command="git config user.email", pattern=r".+@.+\..+")
    - ConfigValueCheck(command="git config user.name", pattern=r".+")  # non-empty
    - ConfigValueCheck(command="pixi info --json | jq -r '.platform'", pattern=r"linux-64")
    """

    command: str
    """Command that outputs the config value (stdout, trimmed)."""

    pattern: str
    """Regex pattern the value must match."""

    value_name: str = ""
    """Human-readable name for the config value (for messages)."""

    @property
    def description(self) -> str:
        name = self.value_name or self.command
        return f"Check config `{name}` matches /{self.pattern}/"

    def check(self, ctx: VerificationContext) -> VerificationResult:
        result = ctx.run_command(self.command)
        value = result.stdout.strip()
        name = self.value_name or self.command
        matched = bool(re.search(self.pattern, value))

        if matched:
            message = f"✓ {name} = {_truncate(value, 100)}"
        elif not value:
            message = f"✗ {name} is not set (empty output from `{self.command}`)"
        else:
            message = f"✗ {name} = {_truncate(value, 100)}, expected to match /{self.pattern}/"

        return VerificationResult(
            passed=matched,
            message=message,
            evidence=f"command: {self.command}\nvalue: {value}",
            check_description=self.description,
        )
```

### 4.4 `ManualConfirm`

```python
@dataclass(frozen=True)
class ManualConfirm:
    """Asks the user to confirm something that can't be automated.

    This is the fallback for external actions (clicking email links,
    checking a website, confirming a physical action).

    Examples:
    - ManualConfirm(question="Did you click the verification link in the GitHub email?")
    - ManualConfirm(question="Can you see the repository at https://github.com/yourname/repo?")
    """

    question: str
    """Yes/no question to present to the user."""

    @property
    def description(self) -> str:
        return f"Manual confirm: {self.question}"

    def check(self, ctx: VerificationContext) -> VerificationResult:
        confirmed = ctx.ask_user(self.question)
        if confirmed:
            message = f"✓ User confirmed: {self.question}"
        else:
            message = f"✗ User did not confirm: {self.question}"

        return VerificationResult(
            passed=confirmed,
            message=message,
            evidence=None,  # No system evidence — user attestation only
            check_description=self.description,
        )
```

### 4.5 `CompoundCheck`

```python
@dataclass(frozen=True)
class CompoundCheck:
    """AND/OR composition of sub-checks.

    Enables multi-condition verification without creating custom verifiers.

    Examples:
    - CompoundCheck(checks=[FileExistsCheck("~/.ssh/id_ed25519"),
                            CommandOutputCheck("ssh-add -l", r"ED25519")],
                    mode="all")  # AND: both must pass
    - CompoundCheck(checks=[FileExistsCheck("~/.ssh/id_ed25519"),
                            FileExistsCheck("~/.ssh/id_rsa")],
                    mode="any")  # OR: either key type works
    """

    checks: tuple[Verification, ...]
    """Sub-checks to evaluate. Tuple for frozen semantics."""

    mode: Literal["all", "any"] = "all"
    """'all' = AND (every check must pass), 'any' = OR (at least one must pass)."""

    label: str = ""
    """Optional label for the compound check (used in messages)."""

    @property
    def description(self) -> str:
        op = " AND " if self.mode == "all" else " OR "
        parts = op.join(c.description for c in self.checks)
        if self.label:
            return f"{self.label}: ({parts})"
        return f"({parts})"

    def check(self, ctx: VerificationContext) -> VerificationResult:
        sub_results = tuple(c.check(ctx) for c in self.checks)

        if self.mode == "all":
            passed = all(r.passed for r in sub_results)
        else:
            passed = any(r.passed for r in sub_results)

        # Build summary message
        passed_count = sum(1 for r in sub_results if r.passed)
        total = len(sub_results)
        label = self.label or f"Compound ({self.mode})"

        if passed:
            message = f"✓ {label}: {passed_count}/{total} checks passed"
        else:
            failed = [r for r in sub_results if not r.passed]
            fail_msgs = "; ".join(r.message for r in failed)
            message = f"✗ {label}: {passed_count}/{total} passed. Failed: {fail_msgs}"

        # Concatenate evidence
        evidence_parts = [
            f"[{i+1}] {r.check_description}: {'PASS' if r.passed else 'FAIL'}\n{r.evidence or '(no evidence)'}"
            for i, r in enumerate(sub_results)
        ]
        evidence = "\n---\n".join(evidence_parts)

        return VerificationResult(
            passed=passed,
            message=message,
            evidence=evidence,
            check_description=self.description,
            sub_results=sub_results,
        )
```

### Utility

```python
def _truncate(s: str, max_len: int = 200) -> str:
    """Truncate a string for display in messages."""
    if len(s) <= max_len:
        return s
    return s[:max_len] + f"... ({len(s)} chars total)"
```

---

## 5. Integration with the Guardrails System

### The Problem

Without guardrail integration, the agent can bypass verification entirely:

```
Agent: "I've completed the SSH key setup for you. Moving to the next step."
# No verification was run. The user might not have a key at all.
```

### The Solution: Checkpoint Guardrail Rule

A new guardrail rule type — `checkpoint` — integrates verification into the existing guardrail enforcement pipeline. This rule activates when a tutorial is in progress and denies step progression unless verification passes.

#### Rule in `rules.yaml`

```yaml
  # ── T01 ─────────────────────────────────────────────────────────────────────
  - id: T01
    name: tutorial-checkpoint-enforcement
    trigger: PreToolUse/Bash
    enforcement: deny
    scope:
      mode: tutorial_active
    detect:
      type: tutorial_checkpoint
      # No regex — this rule type is handled by the tutorial engine
    message: "[GUARDRAIL DENY T01] Tutorial step '{step_id}' requires verification before proceeding. Run the step's verification check first."
    source: "Tutorial system — checkpoint verification enforcement"
```

#### How It Works

The integration operates at two levels:

**Level 1: Agent instruction guardrail (soft)**
When a tutorial is active, the tutorial engine injects a system prompt addendum:

```
TUTORIAL MODE ACTIVE — Step: "Generate SSH key"
You MUST run the verification check before telling the user this step is complete.
Verification: Run `ls -la ~/.ssh/id_ed25519` and confirm the file exists.
Do NOT claim this step is done without showing the verification output.
```

This is the same pattern as existing guardrail `inject` enforcement — adding context to the agent's system prompt.

**Level 2: Progression gate guardrail (hard)**
The tutorial engine exposes a `verify_current_step()` function that the agent must call. The engine tracks whether verification has passed for the current step. If the agent attempts to advance (by calling a step-transition function) without a passing `VerificationResult` recorded, the guardrail denies it:

```python
class TutorialEngine:
    """Orchestrates tutorial execution (simplified)."""

    def advance_to_next_step(self) -> TutorialStep | None:
        """Move to the next step. Denied if current step unverified."""
        current = self._current_step
        if current.verification is not None:
            result = self._state.get_verification_result(current.id)
            if result is None or not result.passed:
                raise CheckpointNotPassedError(
                    step_id=current.id,
                    message=f"Step '{current.id}' requires verification before advancing. "
                            f"Run verify_current_step() first.",
                )
        # Verification passed (or step has no verification) — advance
        return self._advance()

    def verify_current_step(self) -> VerificationResult:
        """Run verification for the current step and record the result."""
        current = self._current_step
        ctx = self._build_verification_context()
        result = current.verification.check(ctx)
        self._state.record_verification(current.id, result)
        return result
```

**Level 3: Evidence persistence**
Every `VerificationResult` is persisted in the tutorial state store (JSON file), including the `evidence` field. This creates an audit trail:

```json
{
  "tutorial_id": "ssh-cluster",
  "steps": {
    "generate-key": {
      "verified_at": "2026-04-03T14:22:31Z",
      "passed": true,
      "evidence": "stdout: -rw------- 1 user user 399 Apr  3 14:22 /home/user/.ssh/id_ed25519\n"
    }
  }
}
```

### Integration Summary

| Guardrail mechanism | Existing pattern | Tutorial verification usage |
|---|---|---|
| `deny` enforcement | R01–R05 in rules.yaml | Deny step advancement without passing verification |
| `inject` enforcement | Post-compact injector | Inject verification instructions into agent context |
| Evidence capture | (new) | Store command output / file contents as proof |
| Scoped rules | `block: [Subagent]` on R04–R05 | `scope: { mode: tutorial_active }` on checkpoint rules |

---

## 6. Seam Analysis

### The Verification Seam

The **only** object that crosses from Verification into other axes is `VerificationResult`. This is the seam boundary.

```
                    ┌─────────────────────┐
                    │   Verification      │
                    │   Axis              │
                    │                     │
                    │  CommandOutputCheck  │
                    │  FileExistsCheck     │
                    │  ConfigValueCheck    │     VerificationResult
                    │  ManualConfirm      │ ───────────────────────►  Other axes
                    │  CompoundCheck      │     (passed, message,
                    │                     │      evidence)
                    │  VerificationContext│
                    │  CommandResult      │
                    └─────────────────────┘
```

### What Each Axis Sees

| Axis | What it reads from VerificationResult | What it does NOT see |
|---|---|---|
| **Progression** | `passed` (bool) | Which command was run, what pattern was checked |
| **Presentation** | `message`, `evidence`, `sub_results` | The `VerificationContext`, how sandboxing works |
| **Content** | Nothing at runtime — content _declares_ which `Verification` to use at authoring time | Verification internals at runtime |
| **Guidance** | `message` (to help user fix failures) | The `Verification` implementation details |
| **Safety** | `passed` (to enforce checkpoint gate) | How the check was performed |

### Seam Integrity Checks

1. **Verification → Content: No leak.** Content authors reference verifications by type + config (e.g., `type: command_output_check, command: "git remote -v", pattern: "github.com"`). Content YAML doesn't import verification code — the engine deserializes.

2. **Verification → Progression: No leak.** Progression calls `engine.advance_to_next_step()`, which internally checks `result.passed`. Progression never calls `.check()` directly or inspects evidence.

3. **Verification → Guidance: No leak.** When guidance helps a user fix a failed step, it reads `result.message` ("git remote -v did not contain a GitHub URL"). It does NOT re-run the verification or inspect the regex pattern. The message is self-contained.

4. **Verification → Presentation: No leak.** Presentation renders `message` and optionally `evidence`. It doesn't know whether the check was a command, file, or manual confirm — it just shows text.

5. **VerificationContext is internal.** Only `Verification` implementations receive a `VerificationContext`. The engine constructs it. No other axis touches it.

---

## YAML Serialization Format

For content authors, verifications are declared in `tutorial.yaml` as data:

```yaml
steps:
  - id: generate-ssh-key
    content: step-01.md
    verification:
      type: file_exists_check
      path: "~/.ssh/id_ed25519"

  - id: add-key-to-agent
    content: step-02.md
    verification:
      type: command_output_check
      command: "ssh-add -l"
      pattern: "ED25519"
      check_stderr: false

  - id: verify-github-email
    content: step-03.md
    verification:
      type: manual_confirm
      question: "Did you click the verification link in the GitHub email?"

  - id: full-ssh-setup
    content: step-04.md
    verification:
      type: compound_check
      mode: all
      label: "SSH setup complete"
      checks:
        - type: file_exists_check
          path: "~/.ssh/id_ed25519"
        - type: command_output_check
          command: "ssh -T git@github.com"
          pattern: "successfully authenticated"
          check_stderr: true
        - type: config_value_check
          command: "git config user.email"
          pattern: ".+@.+"
          value_name: "git email"
```

The engine deserializes `type` → implementation class using a simple registry:

```python
VERIFICATION_REGISTRY: dict[str, type[Verification]] = {
    "command_output_check": CommandOutputCheck,
    "file_exists_check": FileExistsCheck,
    "config_value_check": ConfigValueCheck,
    "manual_confirm": ManualConfirm,
    "compound_check": CompoundCheck,
}
```

This keeps content YAML decoupled from Python imports — content authors write data, not code.

---

## Summary

| Component | Role | Pattern followed |
|---|---|---|
| `Verification` protocol | Interface all verifiers implement | `TriggerCondition` from hints/_types.py |
| `VerificationContext` | Sandboxed system access for verifiers | Frozen dataclass with callable fields |
| `VerificationResult` | Seam-crossing result object | `HintRecord` from hints/_types.py |
| `CommandOutputCheck` | Run command, match output regex | Frozen dataclass implementing protocol |
| `FileExistsCheck` | Check file/dir existence | Frozen dataclass implementing protocol |
| `ConfigValueCheck` | Check config value matches pattern | Frozen dataclass implementing protocol |
| `ManualConfirm` | Ask user yes/no (fallback) | Frozen dataclass implementing protocol |
| `CompoundCheck` | AND/OR composition of sub-checks | Frozen dataclass with recursive structure |
| Checkpoint guardrail | Deny step advancement without proof | Extends existing rules.yaml enforcement |
| YAML deserialization | Content authors declare checks as data | Registry pattern, no code in YAML |
