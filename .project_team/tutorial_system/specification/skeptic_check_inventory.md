# Skeptic: Check Primitive vs TriggerCondition — Ruthless Inventory

**Reviewer:** Skeptic
**Date:** 2026-04-04

---

## The question

The Check primitive (`check(ctx) → CheckResult`) looks suspiciously like TriggerCondition (`check(state) → bool`) with extra fields. Does Check add real value, or is it unnecessary abstraction over what already exists?

---

## 1. Side-by-side comparison

| Feature | TriggerCondition (exists) | Check (proposed) |
|---|---|---|
| Protocol | `check(ProjectState) → bool` | `check(CheckContext) → CheckResult` |
| Context | `ProjectState` — project root, copier answers, filesystem helpers | `CheckContext` — project root, `run_command()`, `read_file()`, `file_exists()` |
| Output | `bool` (pass/fail) | `CheckResult(passed, message, evidence, check_type)` |
| Filesystem | `path_exists()`, `file_contains()`, `dir_is_empty()`, `count_files_matching()` | `file_exists()`, `read_file()` |
| Command execution | **None** | `run_command(cmd, timeout) → CommandResult` |
| Side effects | Must be pure, <50ms | Can run subprocesses, block on I/O |
| Error handling | try/except in engine, never crashes | Returns evidence on failure |
| Combinators | `AllOf`, `AnyOf`, `Not` | None (CompoundCheck deferred to v2) |

---

## 2. Proposed v1 check types — ruthless evaluation

### FileExistsCheck

**Spec example:** `FileExistsCheck("~/.ssh/id_ed25519")`

**Does this actually fail for real users?** Yes, but the example is wrong. SSH keys can be `id_rsa`, `id_ed25519`, `id_ecdsa`, or custom names. A hardcoded path catches ~40% of users at best.

**Could TriggerCondition handle this?**

```python
# Already works today:
@dataclass(frozen=True)
class SshKeyExists:
    def check(self, state: ProjectState) -> bool:
        ssh_dir = Path.home() / ".ssh"
        return any(
            f.name.startswith("id_") and not f.name.endswith(".pub")
            for f in ssh_dir.iterdir()
        ) if ssh_dir.is_dir() else False
```

This is BETTER than `FileExistsCheck("~/.ssh/id_ed25519")` because it handles all key types. The Check primitive's generic `path` parameter actively hurts here — it forces you into a single-path check when the real check is "any SSH key exists."

**Verdict:** TriggerCondition handles this better. FileExistsCheck is too generic to be useful for real checks.

---

### CommandOutputCheck

**Spec example:** `CommandOutputCheck("pixi run pytest tests/test_example.py", "passed")`

**Does this actually fail for real users?** Yes — pytest failing is the primary gate for phase transitions.

**Could TriggerCondition handle this?** No. TriggerConditions must be pure, <50ms, no side effects. Running `pixi run pytest` takes seconds, spawns subprocesses, and has side effects (test execution). This is fundamentally outside TriggerCondition's contract.

**Verdict: This is where Check adds real value.** Command execution with timeout, stdout capture, and regex matching is genuinely new capability that TriggerConditions cannot provide.

---

### ManualConfirm

**Spec example:** `ManualConfirm("Are all implementation tasks complete?")`

**Does this actually fail for real users?** N/A — it's a human interaction, not a system check.

**Could TriggerCondition handle this?** No — TriggerConditions are non-interactive. But ManualConfirm is also a weird fit for Check. It's not an assertion about system state; it's a UX flow. It belongs in the workflow engine's transition logic, not the check system.

**Verdict:** ManualConfirm is not a check. It's a confirmation prompt. It should be a first-class concept in phase transitions: `advance_requires: user-confirm` rather than pretending to be a system assertion.

---

## 3. The real inventory: what do phase gates actually need?

Phase gates need to answer: "Is the system in a state where we can advance?"

| Gate question | Mechanism needed | TriggerCondition? | Check? |
|---|---|---|---|
| Does file X exist? | Filesystem read | ✅ `path_exists()` already works | Adds nothing |
| Does file match pattern? | Filesystem read + regex | ✅ `file_contains()` already works | Adds nothing |
| Does command succeed? | Subprocess execution | ❌ Violates pure/fast contract | ✅ **New capability** |
| Does command output match? | Subprocess + regex | ❌ Violates pure/fast contract | ✅ **New capability** |
| Did user confirm? | Interactive prompt | ❌ Violates pure contract | ❌ Not a system check |

**The honest picture:** Of the three proposed check types, only CommandOutputCheck provides capability that doesn't already exist. FileExistsCheck is a worse version of `path_exists()`. ManualConfirm isn't a check at all.

---

## 4. Does the Check primitive add value over TriggerConditions?

### Where Check adds value (genuinely new)

1. **Subprocess execution with timeout.** TriggerConditions can't run commands. Phase gates need to run `pytest`, `pixi list`, etc. This is essential and cannot be worked around.

2. **Structured evidence.** `CheckResult.evidence` captures stdout/stderr, which is invaluable for debugging gate failures. TriggerConditions return bare `bool` — when a gate fails, you get "failed" with no diagnostic information. For a phase gate, you NEED to know WHY it failed.

3. **Different performance contract.** TriggerConditions must be <50ms (they run at startup). Phase gate checks can take 30 seconds (they run on explicit request). These are fundamentally different execution contexts.

### Where Check adds nothing

1. **File existence.** `ProjectState.path_exists()` already does this.
2. **File content matching.** `ProjectState.file_contains()` already does this.
3. **Boolean combination.** `AllOf`/`AnyOf`/`Not` already exist for TriggerConditions.

### The core insight

**Check and TriggerCondition serve different execution contexts.** TriggerConditions are evaluated passively (startup, background). Checks are evaluated actively (user requests phase advance). The difference isn't the assertion — it's when and how it runs.

A TriggerCondition that runs `pytest` would violate its contract and break the hints pipeline. A Check that runs `pytest` is doing exactly what it's designed for.

---

## 5. Recommendation: Keep Check, but slim it down

### Keep
- **Check protocol** — the `check(ctx) → CheckResult` contract
- **CheckResult** — structured verdict with evidence (genuine value over bool)
- **CheckContext** — project root + `run_command()` (the actual new capability)
- **CommandOutputCheck** — the only built-in that provides new capability

### Cut from v1
- **FileExistsCheck** — Use a TriggerCondition or inline `Path.exists()`. The generic single-path version is actively misleading (SSH key example proves this). If a gate needs file existence, write a 3-line lambda or a purpose-built trigger.
- **ManualConfirm** — Not a check. Move to workflow engine as `advance_requires: user-confirm` in the manifest.
- **Check registry (YAML type → class mapping)** — With only one built-in check type, a registry is overhead. Import CommandOutputCheck directly. Add registry when there are 3+ types.

### What this looks like

```python
# The entire Check system in v1:

@dataclass(frozen=True)
class CheckResult:
    passed: bool
    message: str
    evidence: str = ""

@dataclass(frozen=True)
class CheckContext:
    project_root: Path

    def run_command(self, cmd: str, timeout: float = 30.0) -> CommandResult: ...

class Check(Protocol):
    def check(self, ctx: CheckContext) -> CheckResult: ...

@dataclass(frozen=True)
class CommandOutputCheck:
    command: str
    pattern: str  # regex

    def check(self, ctx: CheckContext) -> CheckResult:
        result = ctx.run_command(self.command)
        passed = bool(re.search(self.pattern, result.stdout))
        return CheckResult(
            passed=passed,
            message=f"Command '{self.command}' output {'matches' if passed else 'does not match'} /{self.pattern}/",
            evidence=result.stdout[:500],
        )
```

That's ~50 lines. Not ~175. Because the actual new capability is subprocess execution with structured results. Everything else already exists.

### Gate declarations in manifest

```yaml
# Before (3 types, registry needed):
advance_checks:
  - type: file-exists-check
    path: "tests/test_example.py"
  - type: command-output-check
    command: "pixi run pytest"
    pattern: "passed"
  - type: manual-confirm
    question: "Are you done?"

# After (1 check type + inline expressions + confirm as separate field):
advance_checks:
  - type: command-output-check
    command: "pixi run pytest"
    pattern: "passed"
advance_requires_file: "tests/test_example.py"   # Simple, no Check needed
advance_confirm: "Are you done?"                   # Not a check, it's a UX prompt
```

Or even simpler — file existence is a precondition, not a gate check. The gate that matters is "does pytest pass?" The file must exist for pytest to pass. One check covers both.

---

## 6. Impact summary

| Change | Lines saved | Complexity removed |
|---|---|---|
| Cut FileExistsCheck | ~25 | One fewer check type, no misleading examples |
| Cut ManualConfirm | ~20 | Interaction logic out of check system |
| Cut Check registry | ~15 | No YAML type mapping for 1 type |
| Cut `/check-setup` (from v1 review) | ~60 | No standalone surface |
| **Total** | **~120** | Check system goes from ~175 to ~50 lines |

What remains is honest: **Check = run a command, match output, return structured evidence.** That's the one thing TriggerConditions can't do.

---

## 7. The deeper answer to the user's question

> "The hardcoded FileExistsCheck("~/.ssh/id_ed25519") example was wrong."

It was wrong because **generic file-exists checks are too simple to be useful.** Real file-existence checks need domain logic (any SSH key, not a specific one). That domain logic belongs in a purpose-built TriggerCondition, not a generic Check.

The Check primitive earns its existence through one capability: **running commands and capturing evidence.** Everything else is already handled by the existing hints infrastructure or is too simple to need a primitive.

If we can't point to a real command that needs to run as a gate check, the Check primitive is unnecessary. But we can: `pixi run pytest`. That's the gate. That's the reason Check exists.
