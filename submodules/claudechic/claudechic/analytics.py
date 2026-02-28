"""PostHog analytics for claudechic - fire-and-forget event tracking."""

import os
import platform
import shutil
import sys
import uuid as uuid_mod
from datetime import datetime, timezone
from pathlib import Path

import httpx
from importlib.metadata import version

from claudechic.config import CONFIG

VERSION = version("claudechic")
SESSION_ID = str(uuid_mod.uuid4())  # Unique per process

POSTHOG_HOST = "https://us.i.posthog.com"
POSTHOG_API_KEY = "phc_M0LMkbSaDsaXi5LeYE5A95Kz8hTHgsJ4POlqucehsse"

# Module-level client for connection reuse (lazy initialized)
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=2.0)
    return _client


def get_terminal_program() -> str:
    """Detect terminal emulator across platforms."""
    # macOS
    if term := os.environ.get("TERM_PROGRAM"):
        return term
    # Specific terminals (Linux/cross-platform)
    if os.environ.get("KITTY_WINDOW_ID"):
        return "kitty"
    if os.environ.get("WEZTERM_PANE"):
        return "wezterm"
    if os.environ.get("ALACRITTY_SOCKET"):
        return "alacritty"
    if os.environ.get("KONSOLE_VERSION"):
        return "konsole"
    if os.environ.get("GNOME_TERMINAL_SCREEN"):
        return "gnome-terminal"
    if os.environ.get("WT_SESSION"):
        return "windows-terminal"
    if os.environ.get("ConEmuPID"):
        return "conemu"
    # Fallback to generic TERM
    return os.environ.get("TERM", "unknown")


async def capture(
    event: str, **properties: str | int | float | bool | list[str]
) -> None:
    """Capture an analytics event to PostHog.

    Fire-and-forget: failures are silently ignored.
    Respects analytics opt-out setting.
    """
    if not CONFIG["analytics"]["enabled"]:
        return

    # Build properties - session_id on all events, context only on app_started
    props: dict = {"$session_id": SESSION_ID, **properties}

    if event == "app_started":
        # Include version and environment context on session start
        props["claudechic_version"] = VERSION
        term_size = shutil.get_terminal_size()  # Falls back to (80, 24)
        props["term_width"] = term_size.columns
        props["term_height"] = term_size.lines
        props["term_program"] = get_terminal_program()
        props["os"] = platform.system()
        props["has_uv"] = shutil.which("uv") is not None
        props["has_conda"] = shutil.which("conda") is not None
        props["is_git_repo"] = Path(".git").exists() or Path(".git").is_file()
        props["cli_args"] = sys.argv[1:]

    if event == "app_installed":
        # Minimal context for install - just version and OS
        props["claudechic_version"] = VERSION
        props["os"] = platform.system()

    if event == "app_closed":
        # Capture terminal size at close (may have changed during session)
        term_size = shutil.get_terminal_size()
        props["term_width"] = term_size.columns
        props["term_height"] = term_size.lines

    payload = {
        "api_key": POSTHOG_API_KEY,
        "event": event,
        "distinct_id": CONFIG["analytics"]["id"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "properties": props,
    }

    try:
        client = _get_client()
        await client.post(f"{POSTHOG_HOST}/capture/", json=payload)
    except (httpx.HTTPError, httpx.TimeoutException):
        pass  # Silent failure - analytics should never impact user experience
