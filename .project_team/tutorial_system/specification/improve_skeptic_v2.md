# Skeptic Improvement Review v2

**Reviewer:** Skeptic
**Date:** 2026-04-04
**Context:** Follow-up from Coordinator's decisions on v1 review

---

## 1. Implementation reorder: `generate_hooks.py` spike FIRST

The spec's Section 8.3 currently lists implementation order as:
1. Check primitive
2. COORDINATOR.md split
3. Phase state + phase_guard.py
4. generate_hooks.py changes (riskiest)
5. Tutorial engine
6. Tutorial content

**Proposed new order:**

1. **`generate_hooks.py` spike + `phase_guard.py`** — Prove phase-scoped guardrails work with R01 before building anything else. Deliverable: R01 gains `phase_block: [testing]`, a hand-crafted `phase_state.json` with `phase_id: "testing"` causes R01 to be skipped, existing guardrail tests still pass. This is ~3 days of focused work, not a half-day task.
2. **Check primitive** — Independent, low-risk. Enables `/check-setup` immediately.
3. **Phase state (`_state.py`)** — Replaces the hand-crafted `phase_state.json` from step 1 with proper read/write functions.
4. **COORDINATOR.md split + `phases.yaml`** — Now that phase_guard works and reads manifests, create the real manifest.
5. **Phase transitions (advance logic)** — Wire gate checks to phase state updates.
6. **Tutorial engine + content** — First consumer beyond project-team.

**Why this order matters:** Step 1 is a go/no-go gate. If `generate_hooks.py` can't be extended cleanly, the entire architecture needs rethinking. Every other component is low-risk by comparison. Don't build 400 lines of Check/Phase infrastructure only to discover the guardrail integration doesn't work.

**Spike acceptance criteria:**
- [ ] `rules.yaml` has `phase_block: [testing]` on R01
- [ ] `generate_hooks.py` parses `phase_block` field and emits `phase_guard.should_skip_rule()` call
- [ ] `phase_guard.py` reads `phase_state.json`, returns skip=True when phase matches
- [ ] ALL existing guardrail tests pass (zero regressions)
- [ ] Manual test: set `phase_id: "testing"` in phase_state.json, verify R01 doesn't fire

---

## 2. Phase ID namespace collision — pending Composability review

Awaiting Composability's proposed fix. Will review when it lands.

Key criteria I'll evaluate against:
- Does it prevent silent cross-workflow collisions?
- Does it avoid over-engineering (qualified IDs everywhere vs. documented limitation)?
- Is it backward-compatible with the `phase_block`/`phase_allow` syntax in `rules.yaml`?
- Does `should_skip_rule()` remain simple and readable?

---

## 3. Line count realism

The spec should add a note to Section 8.1 acknowledging estimate uncertainty:

**Proposed addition after the table in Section 8.1:**

> **Estimate confidence:** These are optimistic estimates assuming clean integration with existing systems. Realistic range is 20-35% higher (~1,500-1,700 lines) due to:
> - `generate_hooks.py` changes touching existing generation pipeline (higher integration cost)
> - Integration tests for phase-scoped guardrails (not separately budgeted)
> - Edge case handling in `phase_state.json` reads (NFS, corrupt file, missing fields)
> - Subprocess error handling in `CheckContext.run_command()`

This isn't a criticism — estimates are inherently uncertain. But the spec presents them as precise numbers (~450, ~275, etc.) which creates false confidence in timelines.

---

## 4. `ask_user()` on CheckContext — remove it

**The problem:** `CheckContext` is described as a "read-only context bag" (Section 2.1) providing dependency injection for testing. `ask_user()` is an interactive side effect — it blocks on user input, it's non-deterministic, and it makes `CheckContext` impossible to use in CI or automated contexts without mocking.

`ManualConfirm` is the only consumer. It's also the least "infrastructure" of the three check types — it's a human interaction, not a system assertion.

**Proposed fix — make `ManualConfirm` own its interaction:**

```python
@dataclass(frozen=True)
class CheckContext:
    """Read-only context for checks: project root and system access."""
    project_root: Path

    def run_command(self, cmd: str, timeout: float = 30.0) -> CommandResult: ...
    def read_file(self, path: str | Path) -> str: ...
    def file_exists(self, path: str | Path) -> bool: ...
    # No ask_user() — CheckContext is read-only system inspection
```

```python
@dataclass(frozen=True)
class ManualConfirm:
    """Check that requires user confirmation. Uses input() directly."""
    question: str

    def check(self, ctx: CheckContext) -> CheckResult:
        answer = input(f"{self.question} [y/N]: ").strip().lower()
        passed = answer in ("y", "yes")
        return CheckResult(
            passed=passed,
            message=self.question,
            evidence=f"User answered: {answer}",
            check_type="manual-confirm",
        )
```

**Why this is better:**
- `CheckContext` stays pure — read-only system inspection, no side effects
- `ManualConfirm` is self-contained — its interaction model is its own concern
- Testing `ManualConfirm` uses `monkeypatch` on `builtins.input` (standard pytest pattern) instead of mocking a context method
- Other checks (`CommandOutputCheck`, `FileExistsCheck`) never see `ask_user` — their context is exactly what they need, nothing more
- If a future check needs a different interaction (e.g., multi-choice), it handles it internally rather than bloating `CheckContext`

**For testing in CI:** `ManualConfirm` checks can be skipped or auto-answered via an environment variable (`TUTORIAL_AUTO_CONFIRM=y`), which is simpler than injecting a mock `ask_user` through `CheckContext`.

---

## 5. Standing by for Composability review

Ready to review Composability's spec updates when they land. Will focus on:
- Phase ID collision fix (item 2 above)
- Whether implementation reorder is reflected
- Whether line count caveat is added
- Whether `ask_user()` is removed from `CheckContext`
