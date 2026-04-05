# Skeptic Review: CheckContext — Keep or Drop?

## The Claim

CheckContext is unnecessary indirection. The "sandbox" is fake. The built-in checks could work with `project_root: Path` and stdlib.

**The claim is correct.** Let me show why, then check if there's a reason to keep it anyway.

---

## What CheckContext Actually Does

From the spec:

```python
@dataclass(frozen=True)
class CheckContext:
    run_command: Callable[[str], CommandResult]  # wraps subprocess.run
    read_file: Callable[[str], str | None]       # wraps Path.read_text
    file_exists: Callable[[str], bool]           # wraps Path.exists
    ask_user: Callable[[str], bool]              # wraps input()
    working_dir: str
    timeout_seconds: float = 10.0
```

Each callable is a thin wrapper around a stdlib function. The "sandboxing" is:
- Timeout on subprocess (stdlib: `subprocess.run(timeout=...)`)
- Output truncation (one line: `output[:10240]`)
- Path expansion (`Path(path).expanduser()`)
- No stdin on subprocess (`stdin=subprocess.DEVNULL`)

None of this requires a dedicated abstraction. Every check can do this inline.

## What the Checks Look Like WITH CheckContext

```python
class CommandOutputCheck:
    def check(self, ctx: CheckContext) -> CheckResult:
        result = ctx.run_command(self.command)
        # match pattern against result.stdout
```

## What They Look Like WITHOUT CheckContext

```python
class CommandOutputCheck:
    def check(self, project_root: Path) -> CheckResult:
        result = subprocess.run(
            self.command, shell=True, capture_output=True, text=True,
            timeout=10, cwd=str(project_root), stdin=subprocess.DEVNULL,
        )
        # match pattern against result.stdout
```

The difference is one line: `ctx.run_command(self.command)` vs `subprocess.run(...)`. Three extra keyword arguments. That's it.

---

## Cost of Keeping CheckContext

- **55 lines** of code (CheckContext + CommandResult + build_check_context factory)
- One additional concept for implementers to understand
- Every new check type must accept `CheckContext` instead of the simpler `project_root: Path`
- "Sandbox" naming sets wrong expectations — someone reads "sandboxed" and thinks there's real isolation

## Cost of Dropping CheckContext

- Each check calls `subprocess.run` directly — 3 extra keyword args per check (~1 line longer per check)
- Timeout value is hardcoded per check (or passed as a field) instead of centralized
- Path expansion logic duplicated across FileExistsCheck and any future file-based check (~2 lines each)
- Tests must mock `subprocess.run` instead of injecting a fake `run_command` callable

## The Testing Argument

This is the only real argument for CheckContext. With it:

```python
def test_command_output_check():
    ctx = CheckContext(
        run_command=lambda cmd: CommandResult(0, "github.com", ""),
        file_exists=lambda p: True,
        ...
    )
    result = CommandOutputCheck("git remote -v", "github").check(ctx)
    assert result.passed
```

Without it:

```python
@patch("subprocess.run")
def test_command_output_check(mock_run):
    mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="github.com", stderr="")
    result = CommandOutputCheck("git remote -v", "github").check(Path("/tmp"))
    assert result.passed
```

The CheckContext version is slightly cleaner — no `@patch` decorator, no mock objects. But the `@patch` version is standard Python and every developer knows how to write it. The difference is cosmetic.

---

## The v2 Argument

Could CheckContext become useful later? Scenarios:

1. **Remote verification** — Run checks on a remote machine via SSH. `run_command` wraps `ssh host command` instead of `subprocess.run`. This is a real scenario (HPC cluster tutorials), but it's a v2/v3 concern. When you need it, you can introduce the abstraction then. YAGNI until then.

2. **Containerized verification** — Run checks inside a Docker container. Same argument: real but distant. Introduce when needed.

3. **Dry-run mode** — Return canned results without executing. Useful for tutorial content testing ("does this tutorial's verification flow make sense without a real SSH key?"). This is genuinely useful and CheckContext makes it trivial. But you can achieve the same with `@patch` or a test fixture.

None of these justify building the abstraction now. All of them can be introduced later without breaking existing checks — you just change the `check()` signature from `project_root: Path` to `ctx: CheckContext` when the need arises. Three checks to update. Ten minutes of work.

---

## Verdict

**Drop CheckContext for v1.** The checks take `project_root: Path` directly. Each check calls `subprocess.run` or `Path.exists` inline. Tests use `@patch` or `tmp_path` fixtures.

This saves 55 lines, removes one concept, and eliminates the misleading "sandbox" framing. If v2 needs injectable dependencies (remote execution, dry-run mode), introduce CheckContext then. The migration is trivial — three checks, one signature change each.

**Revised check signatures:**

```python
class CommandOutputCheck:
    command: str
    pattern: str
    check_stderr: bool = False
    timeout: float = 10.0

    def check(self, project_root: Path) -> CheckResult:
        try:
            result = subprocess.run(
                self.command, shell=True, capture_output=True, text=True,
                timeout=self.timeout, cwd=str(project_root), stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return CheckResult(passed=False, message=f"Command timed out after {self.timeout}s", ...)
        output = result.stderr if self.check_stderr else result.stdout
        matched = bool(re.search(self.pattern, output))
        ...

class FileExistsCheck:
    path: str

    def check(self, project_root: Path) -> CheckResult:
        resolved = Path(self.path).expanduser()
        if not resolved.is_absolute():
            resolved = project_root / resolved
        exists = resolved.exists()
        ...
```

Each check is self-contained. No shared context object. No indirection. Timeout is per-check (a field with a default), not centralized. Path expansion is two lines, duplicated in the two checks that need it (FileExistsCheck and a hypothetical FileContentCheck). That duplication is cheaper than an abstraction layer.

**Line count impact:** Check primitive drops from ~175 to ~120 lines. The 55-line CheckContext module is eliminated entirely.
