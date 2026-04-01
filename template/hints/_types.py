"""Type definitions for the hints system.

Defines the core protocols (TriggerCondition, HintLifecycle), their concrete
implementations, and the data structures (HintSpec, HintRecord, CommandLesson)
that cross seams between axes.

All dataclasses are frozen — hints system types are immutable by design.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from hints._state import HintStateStore, ProjectState


# ---------------------------------------------------------------------------
# Axis: TriggerCondition — Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class TriggerCondition(Protocol):
    """Pure function of project state → bool.

    Triggers read ONLY from disk/config, never from live UI state.
    This keeps the TriggerCondition ↔ EvaluationTiming seam clean.
    """

    def check(self, state: ProjectState) -> bool:
        """Return True if the condition is met (hint should fire).

        Must be:
        - Pure: same ProjectState → same result
        - Side-effect-free: no writes, no network calls
        - Fast: called at startup, should complete in <50ms
        """
        ...

    @property
    def description(self) -> str:
        """Human-readable description for debugging/logging."""
        ...


# ---------------------------------------------------------------------------
# Axis: HintLifecycle — Protocol + Implementations
# ---------------------------------------------------------------------------


class HintLifecycle(Protocol):
    """Policy that decides whether a hint should be shown based on display history.

    Lifecycle is independent of triggers, activation, and presentation.
    It receives only a hint_id and the state store — nothing else.
    """

    def should_show(self, hint_id: str, state: HintStateStore) -> bool:
        """Return True if the hint should be shown right now.

        Args:
            hint_id: Unique identifier for the hint.
            state: Read-only access to this hint's display history.
        """
        ...

    def record_shown(self, hint_id: str, state: HintStateStore) -> None:
        """Record that the hint was shown. Called after presentation.

        Args:
            hint_id: Unique identifier for the hint.
            state: Writable access to update display history.
        """
        ...


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

    The lifecycle module does NOT re-run triggers. It only checks whether
    the user explicitly dismissed the hint. Resolution detection (trigger
    returning False) is the pipeline's responsibility.
    """

    def should_show(self, hint_id: str, state: HintStateStore) -> bool:
        return not state.is_dismissed(hint_id)

    def record_shown(self, hint_id: str, state: HintStateStore) -> None:
        state.increment_shown(hint_id)


@dataclass(frozen=True)
class ShowEverySession:
    """Always show when trigger fires. For rotating/critical hints.

    Usage should be intentional — most hints should be ShowOnce or
    ShowUntilResolved. Used by learn-command for command rotation.
    """

    def should_show(self, hint_id: str, state: HintStateStore) -> bool:
        return True

    def record_shown(self, hint_id: str, state: HintStateStore) -> None:
        state.increment_shown(hint_id)  # Still track for analytics/sorting


@dataclass(frozen=True)
class CooldownPeriod:
    """Show at most once per cooldown window (in seconds).

    Gracefully handles clock skew: negative elapsed time is treated as
    "cooldown expired" — better to show an extra hint than to silently
    suppress for hours due to clock adjustment.
    """

    seconds: float

    def __post_init__(self) -> None:
        if self.seconds <= 0:
            raise ValueError(
                f"CooldownPeriod requires seconds > 0, got {self.seconds}"
            )

    def should_show(self, hint_id: str, state: HintStateStore) -> bool:
        last_shown = state.get_last_shown_timestamp(hint_id)
        if last_shown is None:
            return True  # Never shown before
        elapsed = time.time() - last_shown
        if elapsed < 0:
            # Clock went backwards (NTP, VM suspend, etc.) — show the hint
            return True
        return elapsed >= self.seconds

    def record_shown(self, hint_id: str, state: HintStateStore) -> None:
        state.increment_shown(hint_id)
        state.set_last_shown_timestamp(hint_id, time.time())


# ---------------------------------------------------------------------------
# HintSpec — the registry entry (the composability crystal point)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HintSpec:
    """A single hint definition — a point in the composability crystal.

    Each HintSpec binds together one value from each axis:
    - trigger: TriggerCondition (when is the hint relevant?)
    - lifecycle: HintLifecycle (how often should it show?)
    - message: static string or dynamic callable
    - severity + priority: presentation parameters

    The engine resolves the message at evaluation time:
        msg = hint.message(state) if callable(hint.message) else hint.message
    """

    id: str
    trigger: TriggerCondition
    message: str | Callable[[ProjectState], str]
    severity: Literal["info", "warning"] = "info"
    priority: int = 3  # 1=blocking, 2=high-value, 3=enhancement, 4=command lesson
    lifecycle: HintLifecycle = ShowUntilResolved()  # object, not string


# ---------------------------------------------------------------------------
# HintRecord — the shared protocol object crossing all seams
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HintRecord:
    """A hint that passed all pipeline filters and is ready for presentation.

    This is the shared protocol object that crosses seams between axes.
    The pipeline produces HintRecords; presentation consumes them.

    Fields carry everything the presenter needs without importing
    trigger, lifecycle, or activation internals.
    """

    id: str
    message: str  # Already resolved (static or dynamic → concrete string)
    severity: Literal["info", "warning"]
    priority: int
