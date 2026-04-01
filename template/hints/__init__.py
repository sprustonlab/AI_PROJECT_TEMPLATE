"""Hints system — contextual feature discovery for AI_PROJECT_TEMPLATE projects.

Public API: ``evaluate()`` is the single entry point called by ClaudeChic.
All internals are private (prefixed with ``_``).

Discovery contract::

    from hints import evaluate

    await evaluate(
        send_notification=app.notify,
        project_root=Path.cwd(),
        session_count=count_sessions(),
    )
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


async def evaluate(
    send_notification: Callable[..., Any],
    project_root: Path,
    session_count: int | None = None,
    **kwargs: Any,
) -> None:
    """Evaluate hints and show toast notifications.

    This is the public entry point — the only function ClaudeChic calls.
    Everything is wrapped in a top-level try-except: if ANYTHING fails,
    we silently return. A hint system must never crash its host.

    Parameters
    ----------
    send_notification:
        Callback ``(message, severity, timeout) -> None`` to show a toast.
    project_root:
        Project root directory (absolute ``Path``).
    session_count:
        Number of ClaudeChic sessions. ``None`` if unavailable.
    **kwargs:
        Forward-compatible — passed through to the engine.
    """
    try:
        from ._engine import run_pipeline
        from ._state import ActivationConfig, HintStateStore, ProjectState

        # Build read-only project context
        project_state = ProjectState.build(
            project_root, session_count=session_count, **kwargs
        )

        # Load persistent state (lifecycle + activation) from .claude/hints_state.json
        state_store = HintStateStore(project_root)
        activation = ActivationConfig(state_store)

        # Global kill switch — cheapest possible exit
        if not activation.is_globally_enabled:
            return

        # Get hint definitions (lazy import — hints.py may not exist yet)
        from .hints import get_hints

        hints = get_hints(
            get_taught_commands=lambda: state_store.get_taught_commands(),
        )

        # Run the pipeline: activation -> trigger -> lifecycle -> present
        await run_pipeline(
            send_notification=send_notification,
            project_state=project_state,
            state_store=state_store,
            activation=activation,
            hints=hints,
            budget=kwargs.get("budget", 2),
            is_startup=kwargs.get("is_startup", True),
        )

    except Exception:
        # IRON RULE: Never crash for a hint.
        # Import errors, missing files, bad state — all caught here.
        logger.warning("Hint evaluation failed — silently skipping", exc_info=True)
