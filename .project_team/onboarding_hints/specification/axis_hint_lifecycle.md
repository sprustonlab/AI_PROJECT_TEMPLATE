# Axis Deep-Dive: HintLifecycle

## Step 1: Relevance Check — Is HintLifecycle a Real Axis?

**Yes. HintLifecycle is a genuine, non-collapsible axis.**

**Why it's not Activation:** Activation answers "is this hint *allowed* to run?" — a boolean gate (enabled/disabled/per-hint). It's a filter before the pipeline runs. HintLifecycle answers "given this hint *has* fired, should it be shown *right now* based on its history?" That's a stateful decision requiring persistence, timestamps, and counters. Collapsing them would mix a stateless toggle with a stateful policy — dirty seam.

**Why it's not TriggerCondition:** TriggerCondition answers "is the project in a state where this hint is relevant?" — a pure function of project state. HintLifecycle answers "has the user already seen this enough times?" — a function of *display history*, not project state. A trigger can fire every session, but the lifecycle policy may suppress it after the first showing. Different inputs, different concerns.

**Independence proof:** The same `PathNotExists(".git")` trigger + `enabled` activation can pair with `ShowOnce`, `ShowEverySession`, or `CooldownPeriod(3600)` — each producing different behavior without any change to trigger or activation code.

---

## Step 2: Deep Review

### 2.1 Protocol Definition

The `HintLifecycle` protocol answers exactly one question:

> Given a `hint_id` and the persisted display history, should this hint be shown right now?

```python
from typing import Protocol

class HintLifecycle(Protocol):
    """Policy that decides whether a hint should be shown based on its display history."""

    def should_show(self, hint_id: str, state: "HintStateStore") -> bool:
        """Return True if the hint should be shown right now.

        Args:
            hint_id: Unique identifier for the hint.
            state: Read-only access to this hint's display history
                   (times_shown, last_shown_timestamp, dismissed).

        Returns:
            True if the hint should be displayed, False to suppress it.
        """
        ...

    def record_shown(self, hint_id: str, state: "HintStateStore") -> None:
        """Record that the hint was shown. Called by the pipeline after presentation.

        Args:
            hint_id: Unique identifier for the hint.
            state: Writable access to update display history.
        """
        ...
```

**Key design decisions:**
- The protocol takes a `HintStateStore`, not raw dicts — clean seam for state access.
- `should_show` is a pure query; `record_shown` is the mutation. Separated for testability.
- No knowledge of what triggered the hint, how it's presented, or whether it's activated.

### 2.2 Lifecycle Policies (Python Dataclasses)

Per Skeptic's guidance: dataclasses, not YAML, for policy definitions. Each policy is a concrete implementation of the `HintLifecycle` protocol.

```python
from dataclasses import dataclass
import time


@dataclass(frozen=True)
class ShowOnce:
    """Show the first time the trigger fires, never again."""

    def should_show(self, hint_id: str, state: HintStateStore) -> bool:
        return state.get_times_shown(hint_id) == 0

    def record_shown(self, hint_id: str, state: HintStateStore) -> None:
        state.increment_shown(hint_id)


@dataclass(frozen=True)
class ShowUntilResolved:
    """Keep showing until the trigger condition becomes false.

    This is the only lifecycle policy that requires the trigger to be
    re-evaluated. The pipeline handles this: after lifecycle says
    "should_show=True", the pipeline re-runs the trigger. If the trigger
    now returns False, the hint is suppressed (the issue resolved itself).

    Important: The lifecycle module does NOT re-run triggers itself.
    It only checks whether the hint was previously dismissed by the user.
    The "resolved" check is the pipeline's responsibility — it simply
    re-evaluates the trigger. This keeps the seam clean.
    """

    def should_show(self, hint_id: str, state: HintStateStore) -> bool:
        return not state.is_dismissed(hint_id)

    def record_shown(self, hint_id: str, state: HintStateStore) -> None:
        state.increment_shown(hint_id)


@dataclass(frozen=True)
class ShowNTimes:
    """Show up to N times total, then stop."""
    n: int

    def __post_init__(self):
        if self.n < 1:
            raise ValueError(f"ShowNTimes requires n >= 1, got {self.n}")

    def should_show(self, hint_id: str, state: HintStateStore) -> bool:
        return state.get_times_shown(hint_id) < self.n

    def record_shown(self, hint_id: str, state: HintStateStore) -> None:
        state.increment_shown(hint_id)


@dataclass(frozen=True)
class ShowEverySession:
    """Always show when trigger fires. For critical/safety hints only.

    Usage should be rare — most hints should be ShowOnce or ShowNTimes.
    Reserve for things like "cluster quota nearly exhausted" or
    "guardrails disabled in production."
    """

    def should_show(self, hint_id: str, state: HintStateStore) -> bool:
        return True

    def record_shown(self, hint_id: str, state: HintStateStore) -> None:
        state.increment_shown(hint_id)  # Still track for analytics


@dataclass(frozen=True)
class CooldownPeriod:
    """Show at most once per cooldown window (in seconds).

    Uses monotonic-style comparison: compares current time against
    last_shown_timestamp. Gracefully handles clock skew by treating
    any negative elapsed time as "cooldown expired."
    """
    seconds: float

    def __post_init__(self):
        if self.seconds <= 0:
            raise ValueError(f"CooldownPeriod requires seconds > 0, got {self.seconds}")

    def should_show(self, hint_id: str, state: HintStateStore) -> bool:
        last_shown = state.get_last_shown_timestamp(hint_id)
        if last_shown is None:
            return True  # Never shown before
        elapsed = time.time() - last_shown
        if elapsed < 0:
            # Clock went backwards (skew, NTP adjustment, etc.)
            # Treat as cooldown expired — don't punish the user
            return True
        return elapsed >= self.seconds

    def record_shown(self, hint_id: str, state: HintStateStore) -> None:
        state.increment_shown(hint_id)
        state.set_last_shown_timestamp(hint_id, time.time())
```

### 2.3 State Persistence Design

#### Where does state live?

**Recommendation:** `.claude/hints_state.json` in the project root.

**Rationale:**
- `.claude/` is already the convention for Claude-related project state (e.g., guardrails live in `.claude/guardrails/`)
- JSON format matches existing patterns (`.patterns_mining_state.json` uses the same structure: keys → metadata dicts)
- Project-scoped, not user-global — different projects have independent hint journeys
- Easy to `.gitignore` (user-specific display history shouldn't be committed)

#### What's stored?

```json
{
  "version": 1,
  "activation": {
    "enabled": true,
    "disabled_hints": []
  },
  "lifecycle": {
    "git-setup": {
      "times_shown": 1,
      "last_shown_ts": 1774957452.69,
      "dismissed": false
    },
    "mcp-tools-empty": {
      "times_shown": 3,
      "last_shown_ts": 1774910951.63,
      "dismissed": false
    },
    "pattern-miner-discovery": {
      "times_shown": 0,
      "last_shown_ts": null,
      "dismissed": true
    },
    "learn-command": {
      "times_shown": 5,
      "last_shown_ts": 1774957452.69,
      "dismissed": false,
      "taught_commands": ["/diff", "/resume", "/worktree"]
    }
  }
}
```

> **Note (Rev 2a):** This file is shared with Activation state. The `activation` section
> is owned by `ActivationConfig`; the `lifecycle` section is owned by `HintStateStore`.
> Both are loaded by `hints/_state.py`. Independent sections, one file, one atomic write.

**Schema:**
- `version: int` — for future schema migrations
- `activation: dict` — owned by Activation axis (see `axis_activation.md`)
- `lifecycle: dict[str, HintState]` — keyed by hint_id, owned by Lifecycle axis
- Each `HintState`:
  - `times_shown: int` — total display count
  - `last_shown_ts: float | null` — Unix timestamp of last display (null = never shown)
  - `dismissed: bool` — user explicitly dismissed this hint (for `ShowUntilResolved`)
  - `taught_commands: list[str]` — (optional, `learn-command` only) list of command names already taught. Appended to each time the hint fires with a new command.

#### Who reads/writes it?

**Only the `HintStateStore` class** — the single module responsible for state I/O. This is the clean seam:

```python
from dataclasses import dataclass, field
from pathlib import Path
import json
import time


@dataclass
class HintStateRecord:
    """In-memory representation of a single hint's display history."""
    times_shown: int = 0
    last_shown_ts: float | None = None
    dismissed: bool = False


class HintStateStore:
    """Reads and writes hint display history.

    This is the ONLY module that touches the state file.
    Triggers, presenters, and activation logic never see this file.
    """

    DEFAULT_PATH = ".claude/hints_state.json"
    CURRENT_VERSION = 1

    def __init__(self, project_root: Path):
        self._path = project_root / self.DEFAULT_PATH
        self._state: dict[str, HintStateRecord] = {}
        self._load()

    def _load(self) -> None:
        """Load state from disk. Gracefully handles missing/corrupt files."""
        if not self._path.exists():
            # First run — no state yet. Start fresh.
            self._state = {}
            return

        try:
            raw = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable file — start fresh.
            # Don't crash the hints system because of bad state.
            self._state = {}
            return

        # Version check — future-proof for schema changes
        version = raw.get("version", 0)
        if version > self.CURRENT_VERSION:
            # Written by a newer version we don't understand.
            # Safe default: start fresh rather than misinterpret.
            self._state = {}
            return

        hints_raw = raw.get("hints", {})
        for hint_id, data in hints_raw.items():
            if not isinstance(data, dict):
                continue  # Skip malformed entries
            self._state[hint_id] = HintStateRecord(
                times_shown=data.get("times_shown", 0),
                last_shown_ts=data.get("last_shown_ts"),
                dismissed=data.get("dismissed", False),
            )

    def save(self) -> None:
        """Persist current state to disk. Creates parent dirs if needed."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.CURRENT_VERSION,
            "hints": {
                hint_id: {
                    "times_shown": rec.times_shown,
                    "last_shown_ts": rec.last_shown_ts,
                    "dismissed": rec.dismissed,
                }
                for hint_id, rec in self._state.items()
            },
        }
        # Atomic-ish write: write to temp then rename
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2))
        tmp_path.rename(self._path)

    def _get_or_create(self, hint_id: str) -> HintStateRecord:
        if hint_id not in self._state:
            self._state[hint_id] = HintStateRecord()
        return self._state[hint_id]

    # --- Query methods (used by lifecycle policies) ---

    def get_times_shown(self, hint_id: str) -> int:
        return self._get_or_create(hint_id).times_shown

    def get_last_shown_timestamp(self, hint_id: str) -> float | None:
        return self._get_or_create(hint_id).last_shown_ts

    def is_dismissed(self, hint_id: str) -> bool:
        return self._get_or_create(hint_id).dismissed

    # --- Mutation methods (called after presentation) ---

    def increment_shown(self, hint_id: str) -> None:
        rec = self._get_or_create(hint_id)
        rec.times_shown += 1
        rec.last_shown_ts = time.time()

    def set_last_shown_timestamp(self, hint_id: str, ts: float) -> None:
        self._get_or_create(hint_id).last_shown_ts = ts

    def set_dismissed(self, hint_id: str, dismissed: bool = True) -> None:
        self._get_or_create(hint_id).dismissed = dismissed
```

#### How does `ShowUntilResolved` work?

**Critical design point:** The lifecycle module does NOT re-run triggers. Here's why and how:

1. **Lifecycle checks:** "Has the user dismissed this hint?" → `state.is_dismissed(hint_id)`
2. **The pipeline checks:** "Does the trigger still fire?" → `trigger.evaluate(project_state)`
3. **Resolution happens naturally:** When the user fixes the issue (e.g., runs `git init`), the trigger `PathNotExists(".git")` returns `False` on the next evaluation. The hint simply doesn't enter the pipeline. No lifecycle involvement needed.

The pipeline flow for `ShowUntilResolved`:
```
Trigger fires (no .git) → True
  → Activation check → enabled
  → Lifecycle.should_show() → not dismissed? True
  → Present toast

User runs git init...

Next evaluation:
Trigger fires (no .git) → False  ← stops here, hint never reaches lifecycle
```

This keeps the seam clean: lifecycle never imports or calls trigger code.

### 2.4 Seam Verification

| Seam | What lifecycle knows | What lifecycle does NOT know | Clean? |
|------|---------------------|------------------------------|--------|
| Lifecycle ↔ Trigger | Nothing about triggers | What condition fired, how it's evaluated, what files are checked | ✅ |
| Lifecycle ↔ Presentation | Nothing about presentation | Whether it's a toast, log, or status bar | ✅ |
| Lifecycle ↔ Activation | Nothing about activation | Whether hints are enabled/disabled | ✅ |
| Lifecycle ↔ State | Full ownership | — (lifecycle owns the state file exclusively) | ✅ |

**Swap test results:**
- Replace `ShowOnce` with `CooldownPeriod(3600)` → no trigger, presentation, or activation code changes ✅
- Replace JSON state file with SQLite → only `HintStateStore` changes, lifecycle policies unchanged ✅
- Add a new lifecycle policy `ShowOnWeekdays` → no changes to any other axis ✅

**Inputs to lifecycle:** `hint_id: str` and `HintStateStore` — that's it. No `HintRecord`, no trigger result, no presentation details.

### 2.5 Edge Cases

#### First run (no state file)
- `HintStateStore._load()` detects `not self._path.exists()` → initializes empty state
- All hints start with `times_shown=0`, `last_shown_ts=None`, `dismissed=False`
- `ShowOnce.should_show()` → `0 == 0` → `True` (hint shown on first run) ✅
- State file created on first `save()` call, with parent dirs created via `mkdir(parents=True)`

#### State file deleted mid-use
- The `HintStateStore` loads state into memory at initialization
- If the file is deleted after loading, the in-memory state is still valid
- On next `save()`, the file is recreated
- If the file is deleted between sessions, it's equivalent to "first run" — hints may re-show. This is acceptable: slightly annoying but never dangerous. Graceful degradation.

#### Clock skew for cooldown
- `CooldownPeriod.should_show()` explicitly handles negative elapsed time:
  ```python
  if elapsed < 0:
      return True  # Clock went backwards — show the hint
  ```
- **Rationale:** If the clock jumped backwards, the user may have to wait an unreasonably long time for the cooldown to expire. Better to show an extra hint than to silently suppress it for hours/days.
- NTP corrections, VM suspend/resume, and timezone changes are all handled by this approach.

#### Multiple ClaudeChic sessions simultaneously
- **Risk:** Two sessions load state, both show a `ShowOnce` hint, both save — last writer wins but hint was shown twice.
- **Acceptable for MVP:** Hints are low-stakes. Showing a hint twice is mildly annoying, not dangerous.
- **Future mitigation (if needed):**
  - File locking via `fcntl.flock()` — simple but platform-dependent
  - Atomic compare-and-swap on the state file
  - Accept eventual consistency: each session maintains its own view, state converges on next load
- **Design note:** The `save()` method already uses write-to-temp-then-rename for crash safety. This also provides atomicity for the write itself (not for read-modify-write cycles).

#### Unknown hint_id in state file
- `_get_or_create()` handles missing hint_ids by creating a fresh `HintStateRecord`
- Old hint_ids left in the state file (from removed hints) are harmless — they're never queried and add minimal storage overhead
- No cleanup needed; the state file stays small (one entry per hint_id ever seen)

#### Malformed state entries
- `_load()` uses `.get()` with defaults for every field
- Non-dict entries are skipped (`if not isinstance(data, dict): continue`)
- A corrupt file triggers a full reset to empty state — no partial corruption propagation

---

## Summary

| Aspect | Decision |
|--------|----------|
| **Protocol** | `should_show(hint_id, state) -> bool` + `record_shown(hint_id, state)` |
| **Policies** | `ShowOnce`, `ShowUntilResolved`, `ShowNTimes(n)`, `ShowEverySession`, `CooldownPeriod(seconds)` — all frozen dataclasses |
| **State location** | `.claude/hints_state.json` (project-scoped) |
| **State schema** | `hint_id → {times_shown, last_shown_ts, dismissed}` with version field |
| **State ownership** | `HintStateStore` only — clean seam, no other module touches the file |
| **Graceful degradation** | Missing file = fresh start; corrupt file = fresh start; clock skew = show hint |
| **Concurrency** | Last-writer-wins for MVP; file locking available as future enhancement |
| **Seams** | All clean — lifecycle knows only hint_id and state, nothing about triggers/presentation/activation |
| **ShowUntilResolved** | Lifecycle checks `dismissed`; pipeline re-runs trigger to detect resolution. No cross-seam leakage. |
