"""Error handling and logging infrastructure.

Provides centralized exception handling to make errors visible instead of
silently swallowed. Logs to file (configurable) and can notify user via UI.
"""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path
from typing import Callable, Literal

from claudechic.config import CONFIG

# Configure module logger
log = logging.getLogger("claudechic")

# Severity levels matching Textual's SeverityLevel
SeverityLevel = Literal["information", "warning", "error"]

# Callback for UI notifications, set by ChatApp on startup
_notify_callback: Callable[[str, SeverityLevel], None] | None = None


class NotifyHandler(logging.Handler):
    """Logging handler that sends notifications to the UI."""

    def emit(self, record: logging.LogRecord) -> None:
        # Capture callback to avoid TOCTOU race (callback could be set to None
        # between check and call)
        callback = _notify_callback
        if callback is None:
            return
        try:
            # Map log level to notification severity
            severity: SeverityLevel
            if record.levelno >= logging.ERROR:
                severity = "error"
            elif record.levelno >= logging.WARNING:
                severity = "warning"
            else:
                severity = "information"

            msg = self.format(record)
            # Truncate long messages for notifications
            if len(msg) > 200:
                msg = msg[:197] + "..."
            callback(msg, severity)
        except Exception as e:
            # Don't let notification failures cause more problems, but make them visible
            print(f"NotifyHandler.emit() failed: {e}", file=sys.stderr)


def set_notify_callback(
    callback: Callable[[str, SeverityLevel], None] | None,
) -> None:
    """Set the callback for UI notifications.

    Args:
        callback: Function(message, severity) where severity is
                  "information", "warning", or "error".
                  Typically lambda msg, sev: app.notify(msg, severity=sev).
    """
    global _notify_callback
    _notify_callback = callback


def setup_logging(level: int = logging.DEBUG) -> None:
    """Initialize logging. Call once at app startup.

    Configures the root 'claudechic' logger so all child loggers
    (claudechic.app, claudechic.widgets.*, etc.) inherit the handlers.

    Reads configuration from ~/.claude/.claudechic.yaml:
    - logging.file: Path to log file, or null to disable (default: ~/claudechic.log)
    - logging.notify-level: Min level for UI notifications (default: warning)
    """
    # Guard against being called multiple times
    if log.handlers:
        return

    log.setLevel(level)
    log.propagate = False  # Avoid duplicates if root logger is configured

    # File handler (if configured)
    log_file = CONFIG.get("logging", {}).get(
        "file", str(Path.home() / "claudechic.log")
    )
    if log_file:
        # Expand ~ in path (config may use ~/claudechic.log)
        log_file = str(Path(log_file).expanduser())
        try:
            file_handler = logging.FileHandler(log_file, mode="a")
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            )
            file_handler.setLevel(level)
            log.addHandler(file_handler)
        except OSError:
            # Can't write to log file - continue without file logging
            log_file = None

    # Notification handler (if configured)
    notify_level_str = CONFIG.get("logging", {}).get("notify-level", "warning")
    if notify_level_str:
        notify_level = getattr(logging, notify_level_str.upper(), logging.WARNING)
        notify_handler = NotifyHandler()
        notify_handler.setFormatter(logging.Formatter("%(message)s"))
        notify_handler.setLevel(notify_level)
        log.addHandler(notify_handler)

    if log_file:
        log.info("Logging initialized")


def log_exception(e: Exception, context: str = "") -> str:
    """Log an exception with context. Returns formatted message for display."""
    tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    if context:
        log.error(f"{context}: {e}\n{tb}")
        return f"{context}: {e}"
    else:
        log.error(f"{e}\n{tb}")
        return str(e)
