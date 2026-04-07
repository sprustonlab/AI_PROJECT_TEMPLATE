# Check Protocol Specification

## Overview

The Check protocol is the compositional law for Axis 2 (Check Type). All checks implement one async method. The engine doesn't know implementation details — it calls `check()` and gets `CheckResult`. Checks don't know where they're used (advance gate, setup, standalone). All configuration is injected at construction.

The critical design challenge is `ManualConfirm` — the only check type that requires user interaction. The solution: dependency injection of an `AsyncConfirmCallback`. ManualConfirm never sees the TUI. The callback is the seam.

---

## 1. Check Protocol

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
    """Outcome of a check execution.

    Immutable value object. Crosses the Check↔Engine seam.
    The engine sees passed/evidence. It doesn't know how they were produced.
    """
    passed: bool
    evidence: str


# The type alias for ManualConfirm's injected callback.
# This is the seam between checks and TUI.
AsyncConfirmCallback = Callable[[str], Awaitable[bool]]


@runtime_checkable
class Check(Protocol):
    """Async protocol for all verification checks.

    Compositional law: every check type implements this protocol.
    The engine calls check() without knowing the implementation.
    If a new check type follows this protocol, it works everywhere
    checks are used — no engine changes needed.

    Checks are stateless — all configuration injected at construction.
    Checks know nothing about where they're used (advance gate, setup, standalone).
    """

    async def check(self) -> CheckResult: ...
```

**Design decisions:**

- `CheckResult` is a frozen dataclass, not a dict. Type safety at the seam.
- `Check` is a `Protocol`, not an ABC. Duck typing — any object with `async check() -> CheckResult` qualifies. No inheritance required.
- `@runtime_checkable` enables `isinstance(obj, Check)` for validation at manifest load time.
- `evidence` is always a string. The engine may log it, pass it to the hints adapter, or display it. The check doesn't decide how evidence is used.

---

## 2. Four Built-in Check Types

### 2.1 CommandOutputCheck

Runs a shell command and matches stdout against a regex pattern.

```python
class CommandOutputCheck:
    """Check that passes when a command's stdout matches a regex.

    Used for: setup checks (git auth, SSH connectivity, pixi health),
    advance checks (pytest passing), standalone verification.
    """

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
            stdout_bytes, _ = await asyncio.wait_for(
                proc.communicate(), timeout=30.0
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace")

            match = self.compiled_pattern.search(stdout)
            if match:
                # Evidence: the matching line (truncated for readability)
                matching_line = match.group(0)[:200]
                return CheckResult(
                    passed=True,
                    evidence=f"Pattern matched: {matching_line}",
                )
            else:
                # Evidence: first 3 lines of stdout for debugging
                excerpt = "\n".join(stdout.strip().splitlines()[:3])
                return CheckResult(
                    passed=False,
                    evidence=f"Pattern '{self.compiled_pattern.pattern}' not found in output: {excerpt}"[:300],
                )
        except asyncio.TimeoutError:
            return CheckResult(
                passed=False,
                evidence=f"Command timed out after 30s: {self.command}",
            )
        except OSError as e:
            return CheckResult(
                passed=False,
                evidence=f"Command failed: {e}",
            )
```

**Constructor parameters:**
- `command: str` — Shell command to run (via `asyncio.create_subprocess_shell`)
- `pattern: str` — Regex pattern to match against stdout

**Evidence format:**
- Pass: `"Pattern matched: <matching_text>"`
- Fail: `"Pattern '<pattern>' not found in output: <first_3_lines>"`
- Timeout: `"Command timed out after 30s: <command>"`
- Error: `"Command failed: <error>"`

---

### 2.2 FileExistsCheck

Checks whether a file exists at the given path.

```python
class FileExistsCheck:
    """Check that passes when a file exists.

    Used for: verifying generated files, config files, build artifacts.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def check(self) -> CheckResult:
        # File I/O is fast enough to not need asyncio.to_thread for exists()
        exists = self.path.exists()
        if exists:
            return CheckResult(
                passed=True,
                evidence=f"File found: {self.path}",
            )
        else:
            return CheckResult(
                passed=False,
                evidence=f"File not found: {self.path}",
            )
```

**Constructor parameters:**
- `path: str | Path` — File path to check (converted to `Path` internally)

**Evidence format:**
- Pass: `"File found: <path>"`
- Fail: `"File not found: <path>"`

---

### 2.3 FileContentCheck

Reads a file and matches its content against a regex pattern.

```python
class FileContentCheck:
    """Check that passes when a file's content matches a regex.

    Used for: verifying config values, checking generated code content,
    validating file structure.
    """

    def __init__(self, path: str | Path, pattern: str) -> None:
        self.path = Path(path)
        self.compiled_pattern = re.compile(pattern)

    async def check(self) -> CheckResult:
        if not self.path.exists():
            return CheckResult(
                passed=False,
                evidence=f"File not found: {self.path}",
            )

        try:
            content = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return CheckResult(
                passed=False,
                evidence=f"Cannot read file {self.path}: {e}",
            )

        # Search line by line for readable evidence
        for i, line in enumerate(content.splitlines(), 1):
            match = self.compiled_pattern.search(line)
            if match:
                return CheckResult(
                    passed=True,
                    evidence=f"Line {i}: {line.strip()}"[:200],
                )

        return CheckResult(
            passed=False,
            evidence=f"Pattern '{self.compiled_pattern.pattern}' not found in {self.path}",
        )
```

**Constructor parameters:**
- `path: str | Path` — File path to read
- `pattern: str` — Regex pattern to match against file content

**Evidence format:**
- Pass: `"Line <n>: <matching_line>"`
- Fail (no match): `"Pattern '<pattern>' not found in <path>"`
- Fail (no file): `"File not found: <path>"`
- Fail (read error): `"Cannot read file <path>: <error>"`

---

### 2.4 ManualConfirm

Asks the user a yes/no question via an injected callback. **This is the critical seam.**

```python
class ManualConfirm:
    """Check that passes when the user confirms.

    The ONLY check type that requires user interaction. All others are
    pure computation. ManualConfirm receives an AsyncConfirmCallback at
    construction — it never sees the TUI, the app, or any widget.

    The callback is the seam between Check and TUI.
    """

    def __init__(self, question: str, confirm_fn: AsyncConfirmCallback) -> None:
        self.question = question
        self.confirm_fn = confirm_fn

    async def check(self) -> CheckResult:
        try:
            confirmed = await self.confirm_fn(self.question)
            if confirmed:
                return CheckResult(passed=True, evidence="User confirmed")
            else:
                return CheckResult(passed=False, evidence="User declined")
        except Exception as e:
            return CheckResult(
                passed=False,
                evidence=f"Confirmation failed: {e}",
            )
```

**Constructor parameters:**
- `question: str` — The question to present to the user
- `confirm_fn: AsyncConfirmCallback` — `Callable[[str], Awaitable[bool]]`, injected by the engine

**Evidence format:**
- Pass: `"User confirmed"`
- Fail: `"User declined"`
- Error: `"Confirmation failed: <error>"`

---

## 3. ManualConfirm ↔ TUI Seam (Critical Design)

### The Problem

ManualConfirm needs to show a prompt to the user. The TUI has `SelectionPrompt` and `_show_prompt()`. How do we connect them without ManualConfirm knowing about the TUI?

### The Solution: Callback Injection

The **engine** creates a callback that closes over the app's TUI methods. ManualConfirm receives this callback at construction. The callback is the seam — it's the only code that knows both sides.

### Information Flow

```
ManifestYAML  →  Engine (creates callback)  →  ManualConfirm(question, callback)
                    ↓
               callback closes over app._show_prompt + SelectionPrompt
                    ↓
ManualConfirm.check()  →  await self.confirm_fn(question)  →  callback runs  →  TUI prompt
```

### Exact Callback Creation Code (in the engine)

```python
# claudechic/workflows/engine.py (relevant excerpt)

from claudechic.workflows.checks import (
    AsyncConfirmCallback,
    Check,
    CommandOutputCheck,
    FileContentCheck,
    FileExistsCheck,
    ManualConfirm,
)


class WorkflowEngine:
    """Manages phase transitions, check evaluation, and state persistence."""

    def __init__(self, app: "ChatApp") -> None:
        # The engine holds a reference to the app — this is expected.
        # The engine is infrastructure code, not a check.
        self._app = app

    def _make_confirm_callback(self) -> AsyncConfirmCallback:
        """Create an async confirm callback that uses the TUI.

        This is THE seam between the Check protocol and the TUI.
        The callback closes over the app's _show_prompt method.
        ManualConfirm receives this callback — it never sees the app.

        Returns:
            AsyncConfirmCallback: async (question: str) -> bool
        """
        app = self._app  # Capture in closure

        async def confirm(question: str) -> bool:
            """Show a yes/no confirmation prompt in the TUI.

            Uses the same SelectionPrompt + _show_prompt pattern as
            _show_guardrail_confirm in app.py. This is intentional —
            all user-facing confirmations use the same TUI primitive.
            """
            from claudechic.widgets.prompts import SelectionPrompt

            options = [
                ("yes", "Yes — confirm"),
                ("no", "No — decline"),
            ]
            title = f"✅ Check: {question}"
            prompt = SelectionPrompt(title, options)

            async with app._show_prompt(prompt):
                result = await prompt.wait()

            return result == "yes"

        return confirm

    def _build_check(self, check_spec: dict) -> Check:
        """Construct a Check object from manifest YAML data.

        The engine is the only place that knows how to map YAML check
        declarations to Check objects. It's also the only place that
        creates the confirm callback for ManualConfirm.
        """
        check_type = check_spec["type"]

        if check_type == "command-output-check":
            return CommandOutputCheck(
                command=check_spec["command"],
                pattern=check_spec["pattern"],
            )
        elif check_type == "file-exists-check":
            return FileExistsCheck(
                path=check_spec["path"],
            )
        elif check_type == "file-content-check":
            return FileContentCheck(
                path=check_spec["path"],
                pattern=check_spec["pattern"],
            )
        elif check_type == "manual-confirm":
            return ManualConfirm(
                question=check_spec["question"],
                confirm_fn=self._make_confirm_callback(),
            )
        else:
            raise ValueError(f"Unknown check type: {check_type}")
```

### How ManualConfirm Uses It

ManualConfirm is beautifully simple. It has no idea about TUI, widgets, or apps:

```python
# Inside ManualConfirm.check():
confirmed = await self.confirm_fn(self.question)
# That's it. The callback handles everything.
```

### Why This Design is Clean

| Concern | Who handles it? |
|---------|----------------|
| What question to ask | ManualConfirm (from manifest YAML) |
| How to display the question | The callback (closes over SelectionPrompt) |
| How to get user input | The callback (closes over `_show_prompt`) |
| What the answer means | ManualConfirm (maps to CheckResult) |

ManualConfirm doesn't import anything from `claudechic.widgets` or `claudechic.app`. The callback doesn't know what check called it or why. The engine is the only code that connects both sides.

### The Swap Test

Can we swap the TUI for a different UI without changing ManualConfirm?

- **CLI mode:** Engine creates `async def confirm(q): return input(q) == "y"` → ManualConfirm works unchanged.
- **Test mode:** Engine creates `async def confirm(q): return True` → ManualConfirm works unchanged.
- **Web UI:** Engine creates a callback that sends WebSocket messages → ManualConfirm works unchanged.

✅ Seam is clean. ManualConfirm is truly UI-agnostic.

---

## 4. CheckFailed → Hints Adapter

### Scope Resolution

**CheckFailed applies to ALL checks that have `on_failure` configuration**, not just setup checks.

- **Setup checks** (in `global.yaml` `checks:` section): Primary use case. `on_failure` produces hints that show until resolved (e.g., "GitHub auth failed — run `gh auth login`").
- **Advance checks** (in phase `advance_checks:`): Can also have `on_failure` config. When an advance check fails, the adapter fires hints for **informational value** — the gating mechanism is the AND-semantics short-circuit, not the hint. The hint tells the user/agent *why* the gate didn't open (e.g., "tests not passing yet — here's how to debug").

### The Adapter

```python
# claudechic/workflows/checks.py (continued)

from claudechic.hints._types import HintSpec, HintLifecycle, TriggerCondition


@dataclass(frozen=True)
class OnFailureConfig:
    """Parsed on_failure configuration from manifest YAML."""
    message: str
    severity: str = "warning"  # "info" | "warning" | "error"
    lifecycle: str = "show-until-resolved"  # maps to HintLifecycle


class AlwaysTrue:
    """Trigger condition that always fires.

    Used by the CheckFailed adapter because the check has already
    failed — no further condition evaluation needed. The adapter
    creates a HintSpec that fires immediately.
    """

    def evaluate(self, context: object) -> bool:
        return True


def check_failed_to_hint(
    check_result: CheckResult,
    on_failure: OnFailureConfig,
    check_id: str,
) -> HintSpec | None:
    """Adapter: convert a failed CheckResult to a HintSpec.

    This is the bridge between the Check protocol and the Hints pipeline.
    One-directional: checks produce results, this adapter converts failures
    to hints. The check doesn't know about hints. The hints pipeline
    doesn't know about checks. This function is the only code that knows both.

    Returns None if the check passed (no hint needed).
    """
    if check_result.passed:
        return None

    # Map lifecycle string from YAML to HintLifecycle enum/protocol
    lifecycle_map: dict[str, HintLifecycle] = {
        "show-once": ...,              # ShowOnce instance
        "show-until-resolved": ...,    # ShowUntilResolved instance
        "show-every-session": ...,     # ShowEverySession instance
    }
    # NOTE: The actual lifecycle instances depend on the hints system's
    # concrete types. The adapter imports them — it's allowed to know
    # both sides. That's its job.

    lifecycle = lifecycle_map.get(on_failure.lifecycle)
    # Fallback: if lifecycle string not recognized, default to show-until-resolved
    if lifecycle is None:
        lifecycle = lifecycle_map["show-until-resolved"]

    # Compose the hint message with the check's evidence
    message = on_failure.message
    if check_result.evidence:
        message = f"{on_failure.message}\n  Evidence: {check_result.evidence}"

    return HintSpec(
        id=f"check-failed:{check_id}",
        trigger=AlwaysTrue(),       # Already failed — fire immediately
        lifecycle=lifecycle,
        severity=on_failure.severity,
        message=message,
    )
```

### Integration with Existing Hints Pipeline

The adapter produces `HintSpec` objects. These feed directly into the existing `run_pipeline()`:

```python
# In the engine, after running checks:

async def _run_checks_with_hints(
    self,
    checks: list[tuple[str, Check, OnFailureConfig | None]],
) -> list[CheckResult]:
    """Run checks and feed failures into the hints pipeline.

    Args:
        checks: List of (check_id, check_instance, on_failure_config) tuples.
                 on_failure_config is None if no on_failure configured.

    Returns:
        List of CheckResults (one per check).
    """
    results: list[CheckResult] = []
    hint_specs: list[HintSpec] = []

    for check_id, check_instance, on_failure in checks:
        result = await check_instance.check()
        results.append(result)

        # If check failed AND has on_failure config, create a hint
        if not result.passed and on_failure is not None:
            hint = check_failed_to_hint(result, on_failure, check_id)
            if hint is not None:
                hint_specs.append(hint)

    # Feed any generated hints into the existing pipeline
    if hint_specs:
        # run_pipeline() evaluates triggers, checks lifecycle,
        # and delivers hints via the toast system.
        # Since our hints use AlwaysTrue trigger, they'll always
        # pass trigger evaluation and proceed to lifecycle check.
        from claudechic.hints._engine import run_pipeline
        await run_pipeline(hint_specs, self._hint_state)

    return results
```

**Key insight:** The adapter doesn't create a new delivery mechanism. It translates CheckResult into the existing HintSpec format, and the existing pipeline handles delivery, lifecycle, and deduplication. This is a textbook adapter pattern.

---

## 5. advance_checks AND Semantics

### Evaluation Rules

1. **AND semantics:** ALL checks must pass for phase transition to proceed.
2. **Short-circuit on first failure:** Stop evaluating after the first failed check.
3. **Sequential execution (not parallel):** Prevents ManualConfirm prompts from overlapping with other prompts or other ManualConfirm checks.
4. **On failure:** Phase transition blocked. If the failed check has `on_failure` config, the adapter fires a hint.
5. **On success:** Phase transitions. New phase state written atomically (temp file + rename).

### Why Sequential, Not Parallel

- ManualConfirm shows a TUI prompt. Two simultaneous prompts would confuse the user.
- CommandOutputCheck runs shell commands. Parallel commands could interfere with each other (e.g., both writing to the same file).
- Short-circuit semantics require knowing the result of check N before deciding to run check N+1.
- The performance cost is negligible — checks run only at phase transitions, not on every tool call.

### Engine Implementation

```python
# claudechic/workflows/engine.py (relevant excerpt)

import json
import tempfile
from pathlib import Path


class WorkflowEngine:
    # ... (constructor and _make_confirm_callback shown above)

    async def attempt_phase_advance(
        self,
        workflow_id: str,
        current_phase: str,
        next_phase: str,
        advance_checks: list[dict],  # Raw check specs from manifest YAML
        state_path: Path,
    ) -> bool:
        """Attempt to advance from current_phase to next_phase.

        Runs all advance_checks with AND semantics and short-circuit.
        Returns True if phase advanced, False if blocked.
        """
        # Build Check objects from manifest specs
        checks: list[tuple[str, Check, OnFailureConfig | None]] = []
        for i, spec in enumerate(advance_checks):
            check_id = f"{workflow_id}:{current_phase}:advance:{i}"
            check_instance = self._build_check(spec)

            # Parse on_failure config if present
            on_failure = None
            if "on_failure" in spec:
                on_failure = OnFailureConfig(
                    message=spec["on_failure"]["message"],
                    severity=spec["on_failure"].get("severity", "warning"),
                    lifecycle=spec["on_failure"].get("lifecycle", "show-once"),
                )

            checks.append((check_id, check_instance, on_failure))

        # Run checks sequentially with short-circuit
        for check_id, check_instance, on_failure in checks:
            result = await check_instance.check()

            if not result.passed:
                # Short-circuit: don't run remaining checks
                # Fire hint if on_failure configured
                if on_failure is not None:
                    hint = check_failed_to_hint(result, on_failure, check_id)
                    if hint is not None:
                        from claudechic.hints._engine import run_pipeline
                        await run_pipeline([hint], self._hint_state)

                return False  # Phase transition blocked

        # All checks passed — transition phase
        self._write_phase_state(state_path, workflow_id, next_phase)
        return True

    def _write_phase_state(
        self,
        state_path: Path,
        workflow_id: str,
        new_phase: str,
    ) -> None:
        """Write phase state atomically (temp file + rename).

        Atomic write prevents corruption on NFS (HPC clusters).
        No mtime caching — NFS is unreliable for mtime.
        """
        # Read existing state (may have other workflows' state)
        state: dict = {}
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text())
            except (json.JSONDecodeError, OSError):
                state = {}

        # Update phase for this workflow
        state["current_phase"] = f"{workflow_id}:{new_phase}"
        state["workflow_id"] = workflow_id
        state["phase"] = new_phase

        # Atomic write: temp file + rename
        state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=state_path.parent,
            suffix=".tmp",
        )
        try:
            with open(fd, "w") as f:
                json.dump(state, f, indent=2)
            Path(tmp_path).rename(state_path)
        except Exception:
            # Clean up temp file on failure
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass
            raise
```

### Setup Checks (global.yaml)

Setup checks in `global.yaml` use the same Check protocol but with different evaluation semantics:

```python
async def run_setup_checks(self, check_specs: list[dict]) -> list[CheckResult]:
    """Run setup checks from global.yaml at startup.

    Unlike advance_checks, setup checks do NOT short-circuit.
    All checks run, and all failures produce hints. The goal is
    to surface all environment issues at once, not block on the first.
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

    # Run ALL checks (no short-circuit) and collect hints
    return await self._run_checks_with_hints(checks)
```

**Key difference between setup and advance checks:**

| Aspect | Setup checks | Advance checks |
|--------|-------------|----------------|
| Location | `global.yaml` `checks:` section | Phase `advance_checks:` list |
| Short-circuit | No — run all, surface all issues | Yes — stop on first failure |
| Gating | Informational only (hints) | Blocks phase transition |
| Default lifecycle | `show-until-resolved` | `show-once` |
| When they run | Startup, phase transitions (re-eval) | Phase advance attempts only |

---

## 6. Concrete Code Sketches Summary

### Complete checks.py Module

```python
"""Check protocol and built-in check types.

Compositional law: all check types implement async check() -> CheckResult.
The engine doesn't know check implementation details. A new check type
that follows this protocol works everywhere — no engine changes needed.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Awaitable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


# ── Value Objects ──────────────────────────────────────────────

@dataclass(frozen=True)
class CheckResult:
    """Outcome of a check execution. Crosses the Check↔Engine seam."""
    passed: bool
    evidence: str


@dataclass(frozen=True)
class OnFailureConfig:
    """Parsed on_failure configuration from manifest YAML."""
    message: str
    severity: str = "warning"
    lifecycle: str = "show-until-resolved"


# ── Type Aliases ───────────────────────────────────────────────

AsyncConfirmCallback = Callable[[str], Awaitable[bool]]
"""The seam between ManualConfirm and the TUI.

ManualConfirm calls: await callback(question) -> bool
The engine creates the callback, closing over app._show_prompt.
ManualConfirm never imports anything from claudechic.widgets or app.
"""


# ── Protocol ───────────────────────────────────────────────────

@runtime_checkable
class Check(Protocol):
    """Async protocol for all verification checks."""
    async def check(self) -> CheckResult: ...


# ── Built-in Check Types ──────────────────────────────────────

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
            stdout_bytes, _ = await asyncio.wait_for(
                proc.communicate(), timeout=30.0
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace")

            match = self.compiled_pattern.search(stdout)
            if match:
                return CheckResult(
                    passed=True,
                    evidence=f"Pattern matched: {match.group(0)[:200]}",
                )
            excerpt = "\n".join(stdout.strip().splitlines()[:3])
            return CheckResult(
                passed=False,
                evidence=f"Pattern '{self.compiled_pattern.pattern}' not found in output: {excerpt}"[:300],
            )
        except asyncio.TimeoutError:
            return CheckResult(passed=False, evidence=f"Command timed out after 30s: {self.command}")
        except OSError as e:
            return CheckResult(passed=False, evidence=f"Command failed: {e}")


class FileExistsCheck:
    """Passes when file exists."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def check(self) -> CheckResult:
        if self.path.exists():
            return CheckResult(passed=True, evidence=f"File found: {self.path}")
        return CheckResult(passed=False, evidence=f"File not found: {self.path}")


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


class ManualConfirm:
    """Passes when user confirms via injected callback.

    The callback is the seam. ManualConfirm doesn't know about TUI.
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


# ── CheckFailed → Hints Adapter ───────────────────────────────

def check_failed_to_hint(
    check_result: CheckResult,
    on_failure: OnFailureConfig,
    check_id: str,
) -> dict | None:
    """Adapter: convert failed CheckResult to HintSpec-compatible dict.

    Returns None if check passed. The engine feeds the returned dict
    into the hints pipeline via run_pipeline().

    Returns a dict rather than HintSpec directly to avoid importing
    hints types at module level. The engine converts to HintSpec.
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

### Callback Creation in Engine

```python
# In WorkflowEngine.__init__:
#   self._app = app

def _make_confirm_callback(self) -> AsyncConfirmCallback:
    """THE seam between checks and TUI."""
    app = self._app

    async def confirm(question: str) -> bool:
        from claudechic.widgets.prompts import SelectionPrompt

        options = [("yes", "Yes — confirm"), ("no", "No — decline")]
        prompt = SelectionPrompt(f"✅ Check: {question}", options)
        async with app._show_prompt(prompt):
            result = await prompt.wait()
        return result == "yes"

    return confirm
```

### advance_checks Evaluation in Engine

```python
async def attempt_phase_advance(self, ..., advance_checks: list[dict]) -> bool:
    """AND semantics, sequential, short-circuit on first failure."""
    for i, spec in enumerate(advance_checks):
        check = self._build_check(spec)
        result = await check.check()

        if not result.passed:
            # Fire hint if on_failure configured
            if "on_failure" in spec:
                on_failure = OnFailureConfig(**spec["on_failure"])
                hint_data = check_failed_to_hint(result, on_failure, check_id)
                if hint_data:
                    # Feed into hints pipeline
                    ...
            return False  # Blocked

    # All passed — write new phase state atomically
    self._write_phase_state(state_path, workflow_id, next_phase)
    return True
```

---

## Design Decision Summary

| Decision | Rationale |
|----------|-----------|
| Protocol, not ABC | Duck typing. Any `async check() -> CheckResult` works. No inheritance needed. |
| `@runtime_checkable` | Enables validation at manifest load time without test execution. |
| Frozen dataclasses | CheckResult and OnFailureConfig are value objects. Immutability prevents mutation bugs across the seam. |
| AsyncConfirmCallback type alias | Makes the seam explicit and discoverable. `Callable[[str], Awaitable[bool]]` is the contract. |
| Engine creates callback | The engine is infrastructure — it's allowed to know both TUI and checks. Checks are not. |
| Sequential advance_checks | Prevents overlapping ManualConfirm prompts. Performance cost negligible (phase transitions are rare). |
| Setup checks don't short-circuit | Users need to see ALL environment issues, not just the first. |
| Adapter returns dict, not HintSpec | Avoids circular imports. Engine converts dict → HintSpec when feeding to pipeline. |
| `AlwaysTrue` trigger | The check already failed — no further trigger condition needed. The adapter's job is translation, not evaluation. |
| 30s command timeout | Prevents hanging on SSH or network checks. Long enough for real operations. |
| Evidence truncation (200-300 chars) | Prevents huge stdout from bloating hints. Evidence is for debugging, not comprehensive logging. |
