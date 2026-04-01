"""Hint evaluation pipeline.

Activation -> Trigger -> Lifecycle -> Present.

IRON RULE: Never crash for a hint. Every trigger.check() call is
wrapped in try-except. Template-side trigger code can have bugs —
evaluation catches runtime errors.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable

from ._state import ActivationConfig, HintStateStore, ProjectState
from ._types import HintSpec

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

# Toast scheduling constants
_STARTUP_INITIAL_DELAY_S = 2.0
_STARTUP_GAP_S = 6.0
_PERIODIC_DELAY_S = 5.0

# Timeout for toasts by severity (seconds)
_TOAST_TIMEOUT: dict[str, float] = {
    "info": 7.0,
    "warning": 10.0,
}

# Map HintSpec severity → Textual SeverityLevel
# HintSpec uses "info"/"warning"; Textual expects "information"/"warning"
_TEXTUAL_SEVERITY: dict[str, str] = {
    "info": "information",
    "warning": "warning",
}

# Suffix appended to the first toast of a session
_DISABLE_SUFFIX = "  \u2014 disable with /hints off"


async def run_pipeline(
    send_notification: Callable[..., Any],
    project_state: ProjectState,
    state_store: HintStateStore,
    activation: ActivationConfig,
    hints: Sequence[HintSpec],
    budget: int = 2,
    *,
    is_startup: bool = True,
) -> None:
    """Evaluate hints and schedule toast notifications.

    Parameters
    ----------
    send_notification:
        Callback ``(message, severity, timeout) -> None`` to show a toast.
    project_state:
        Read-only snapshot of the project for trigger evaluation.
    state_store:
        Mutable lifecycle state (times_shown, last_shown_ts, etc.).
    activation:
        Global + per-hint enable/disable config.
    hints:
        Ordered sequence of ``HintSpec`` entries (definition order matters
        as a tiebreaker).
    budget:
        Maximum number of toasts to show this evaluation cycle.
    is_startup:
        If ``True``, use startup delays (2 s initial, 6 s gap).
        If ``False``, use periodic delays (5 s gap).
    """
    # --- 1. Filter hints through the pipeline ---------------------------------
    candidates: list[tuple[int, HintSpec]] = []  # (definition_order, hint)

    for idx, hint in enumerate(hints):
        # Gate 1: Activation (cheapest — dict lookup)
        if not activation.is_active(hint.id):
            continue

        # Gate 2: Trigger (wrapped in try-except — IRON RULE)
        try:
            triggered = hint.trigger.check(project_state)
        except Exception:
            logger.warning(
                "Trigger check failed for hint %r — skipping", hint.id, exc_info=True
            )
            continue

        if not triggered:
            continue

        # Gate 3: Lifecycle (stateful history check)
        if not hint.lifecycle.should_show(hint.id, state_store):
            continue

        candidates.append((idx, hint))

    # --- 2. Sort: priority ASC, last_shown_ts ASC (None→0), definition_order ASC
    def _sort_key(entry: tuple[int, HintSpec]) -> tuple[int, float, int]:
        definition_order, h = entry
        last_ts = state_store.get_last_shown_timestamp(h.id)
        return (h.priority, last_ts if last_ts is not None else 0.0, definition_order)

    candidates.sort(key=_sort_key)

    # --- 3. Take top N (budget) -----------------------------------------------
    selected = candidates[:budget]
    if not selected:
        return

    # --- 4. Resolve dynamic messages ------------------------------------------
    resolved: list[tuple[HintSpec, str]] = []
    for _idx, hint in selected:
        try:
            if callable(hint.message):
                message = hint.message(project_state)
            else:
                message = hint.message
        except Exception:
            logger.warning(
                "Dynamic message failed for hint %r — skipping", hint.id, exc_info=True
            )
            continue
        resolved.append((hint, message))

    if not resolved:
        return

    # --- 5. Schedule toasts with delays ---------------------------------------
    toast_count = 0  # track toasts shown this pipeline run

    for i, (hint, message) in enumerate(resolved):
        # Calculate delay
        if is_startup:
            delay = _STARTUP_INITIAL_DELAY_S + i * _STARTUP_GAP_S
        else:
            delay = _PERIODIC_DELAY_S + i * _PERIODIC_DELAY_S

        # First toast of the session gets the disable suffix
        display_message = message
        if is_startup and toast_count == 0:
            display_message = message + _DISABLE_SUFFIX

        timeout = _TOAST_TIMEOUT.get(hint.severity, 7.0)

        # Schedule the toast
        await asyncio.sleep(delay)
        try:
            textual_severity = _TEXTUAL_SEVERITY.get(hint.severity, "information")
            send_notification(display_message, severity=textual_severity, timeout=timeout)
        except Exception:
            logger.warning(
                "send_notification failed for hint %r — continuing",
                hint.id,
                exc_info=True,
            )
            continue

        # --- 6. Record shown hint via lifecycle policy ------------------------
        hint.lifecycle.record_shown(hint.id, state_store)

        # Track taught command for learn-command rotation (duck typing)
        if hasattr(hint.trigger, '_pick_command'):
            cmd = hint.trigger._pick_command()
            if cmd:
                state_store.add_taught_command(cmd.name, hint.id)

        toast_count += 1

    # Persist state after all toasts are scheduled
    state_store.save()


