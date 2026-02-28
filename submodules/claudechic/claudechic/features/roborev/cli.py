"""Pure functions for interacting with the roborev CLI.

All functions are synchronous and intended to be called via asyncio.to_thread().
They return empty/None on error - never crash the TUI.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

from claudechic.features.roborev.models import (
    VISIBLE_STATUSES,
    ReviewDetail,
    ReviewJob,
    normalize_status,
)

log = logging.getLogger(__name__)


_roborev_available: bool | None = None
_roborev_checked_at: float = 0.0
_ROBOREV_CACHE_TTL = 60.0  # seconds


def is_roborev_available() -> bool:
    """Check if roborev CLI is on PATH. Cached with a 60-second TTL."""
    global _roborev_available, _roborev_checked_at
    now = time.monotonic()
    if _roborev_available is None or (now - _roborev_checked_at) > _ROBOREV_CACHE_TTL:
        _roborev_available = shutil.which("roborev") is not None
        _roborev_checked_at = now
    return _roborev_available


def get_current_branch(cwd: Path) -> str:
    """Get the current git branch name. Returns empty string on error."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        log.debug("Failed to get current branch", exc_info=True)
    return ""


def list_reviews(
    cwd: Path, branch: str | None = None, limit: int = 20
) -> list[ReviewJob]:
    """List reviews via `roborev list --json`. Returns empty list on error."""
    if not is_roborev_available():
        return []

    cmd = ["roborev", "list", "--json"]
    if branch:
        cmd.extend(["--branch", branch])

    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            log.debug("roborev list failed: %s", result.stderr)
            return []

        data = json.loads(result.stdout)
        if isinstance(data, list):
            jobs = [ReviewJob.from_dict(item) for item in data]
            # Only show actionable reviews: unaddressed + valid status
            visible = [
                j
                for j in jobs
                if not j.addressed and normalize_status(j.status) in VISIBLE_STATUSES
            ]
            return visible[:limit]
    except Exception:
        log.debug("Failed to list reviews", exc_info=True)
    return []


def show_review(job_id: str, cwd: Path) -> ReviewDetail | None:
    """Show review detail via `roborev show --json --job <id>`. Returns None on error."""
    if not is_roborev_available():
        return None

    try:
        result = subprocess.run(
            ["roborev", "show", "--json", "--job", job_id],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            log.debug("roborev show failed: %s", result.stderr)
            return None

        data = json.loads(result.stdout)
        if isinstance(data, dict):
            return ReviewDetail.from_dict(data)
    except Exception:
        log.debug("Failed to show review", exc_info=True)
    return None
