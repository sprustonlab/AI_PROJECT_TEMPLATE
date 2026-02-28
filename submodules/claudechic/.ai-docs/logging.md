# Logging & Error Handling

Errors in Textual apps are invisible by default (stderr is captured). This doc explains how to make errors visible.

## Log File

All logs go to `~/claudechic.log`. View with:
```bash
tail -f ~/claudechic.log
```

## How to Log

```python
import logging
log = logging.getLogger(__name__)

# These all write to ~/claudechic.log
log.info("Something happened")
log.warning("Something concerning")
log.error("Something failed")
log.exception("Something failed with traceback")  # includes stack trace
```

Child loggers (e.g., `claudechic.app`, `claudechic.widgets.tools`) automatically inherit the file handler configured in `errors.py`.

## Showing Errors to Users

For errors users need to see, use `app.show_error()`:

```python
try:
    await risky_operation()
except Exception as e:
    self.show_error("Operation failed", e)  # Shows in chat + logs to file
```

This:
1. Displays an `ErrorMessage` widget in the chat view (red border, visible)
2. Shows a toast notification
3. Logs full traceback to `~/claudechic.log`

## When to Use What

| Situation | Method |
|-----------|--------|
| Debug info, flow tracing | `log.info()` / `log.debug()` |
| Warning but not user-facing | `log.warning()` |
| Error user should see | `app.show_error(msg, exception)` |
| Swallowed exception (widget not mounted, etc.) | `pass` with comment |

## Bare Except Blocks

Many `except Exception: pass` blocks exist for Textual lifecycle timing (widget not mounted yet). These are intentional. If you add a new one, include a comment explaining why.
