"""Async task utilities for safe background task creation.

Provides wrappers for asyncio.create_task() that prevent unhandled exceptions
from crashing the application while maintaining proper logging.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Coroutine, Any

log = logging.getLogger(__name__)


def create_safe_task(
    coro: Coroutine[Any, Any, Any],
    name: str | None = None,
) -> asyncio.Task:
    """Create an asyncio task with exception handling to prevent crashes.

    Wraps the coroutine to catch and log exceptions rather than allowing
    them to propagate as unhandled task exceptions which can crash the app.

    Exceptions are logged via the standard logging system. If the logging
    NotifyHandler is configured (see errors.py), users will see a notification
    for errors at or above the configured level.

    Args:
        coro: The coroutine to run as a task.
        name: Optional name for the task (used in logging).

    Returns:
        The created asyncio.Task.

    Example:
        # Fire-and-forget task that logs errors but doesn't crash
        create_safe_task(some_async_operation(), name="my-operation")
    """
    task_name = name or "unnamed"

    async def wrapper():
        try:
            return await coro
        except asyncio.CancelledError:
            raise  # Let cancellation propagate normally
        except Exception:
            log.exception(f"Task '{task_name}' failed")
            return None

    return asyncio.create_task(wrapper(), name=name)
