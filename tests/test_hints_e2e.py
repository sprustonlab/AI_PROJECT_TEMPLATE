"""E2E tests: hints system → Textual toast notification on screen.

Proves that evaluate() → app.notify() → Toast widgets appear in the DOM.
Uses a MinimalApp (bare Textual app) to isolate from ClaudeChic internals.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static


# ---------------------------------------------------------------------------
# Minimal Textual app — just enough to receive toasts
# ---------------------------------------------------------------------------


class MinimalApp(App):
    """Bare-minimum Textual app to receive hint toasts."""

    def compose(self) -> ComposeResult:
        yield Static("Minimal app for hint testing")


# ---------------------------------------------------------------------------
# E2E tests
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(30)]


async def test_hint_produces_visible_toast(tmp_path):
    """Full E2E: evaluate() → app.notify() → Toast visible in DOM.

    A fresh tmp_path has no .git directory, so the git-setup hint
    (priority 1, warning) fires. We verify:
    1. app._notifications contains the hint
    2. Toast widgets are rendered in the DOM tree
    """
    app = MinimalApp()

    async with app.run_test(size=(120, 40), notifications=True) as pilot:
        from template.hints import evaluate

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await evaluate(
                send_notification=app.notify,
                project_root=tmp_path,
                session_count=1,
            )

        await pilot.pause()

        # Notifications were created
        assert len(app._notifications) > 0, "No notifications created"

        # The git-setup hint appeared (priority 1, always fires on fresh dir)
        messages = [n.message for n in app._notifications]
        assert any("git" in m.lower() for m in messages), (
            f"Expected git-setup hint in notifications, got: {messages}"
        )

        # Toast widgets are rendered in the DOM
        from textual.widgets._toast import Toast

        toasts = list(app.screen.query(Toast))
        assert len(toasts) > 0, "No Toast widgets found in DOM"


async def test_hint_toast_has_correct_severity(tmp_path):
    """git-setup hint should produce a warning-severity toast.

    The hints engine passes severity='warning' for git-setup.
    Verify it reaches the Notification object correctly.
    """
    app = MinimalApp()

    async with app.run_test(size=(120, 40), notifications=True) as pilot:
        from template.hints import evaluate

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await evaluate(
                send_notification=app.notify,
                project_root=tmp_path,
                session_count=1,
            )

        await pilot.pause()

        # Find the git-setup notification
        notifs = list(app._notifications)
        git_notifs = [n for n in notifs if "git" in n.message.lower()]
        assert len(git_notifs) > 0, (
            f"Expected git-setup notification, got: {[n.message for n in notifs]}"
        )
        assert git_notifs[0].severity == "warning", (
            f"Expected severity='warning', got '{git_notifs[0].severity}'"
        )


async def test_no_hints_when_disabled(tmp_path):
    """When hints are globally disabled, no toasts appear."""
    # Pre-create state file with hints disabled
    state_dir = tmp_path / ".claude"
    state_dir.mkdir()
    (state_dir / "hints_state.json").write_text(
        json.dumps(
            {
                "version": 1,
                "activation": {"enabled": False, "disabled_hints": []},
                "lifecycle": {},
            }
        ),
        encoding="utf-8",
    )

    app = MinimalApp()

    async with app.run_test(size=(120, 40), notifications=True) as pilot:
        from template.hints import evaluate

        with patch("template.hints._engine.asyncio.sleep", new_callable=AsyncMock):
            await evaluate(
                send_notification=app.notify,
                project_root=tmp_path,
                session_count=1,
            )

        await pilot.pause()

        assert len(app._notifications) == 0, (
            f"Expected no notifications when disabled, got: "
            f"{[n.message for n in app._notifications]}"
        )
