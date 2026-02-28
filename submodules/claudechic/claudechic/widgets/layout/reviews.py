"""Review panel widget for displaying roborev reviews in the sidebar."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from claudechic.features.roborev.models import (
    RUNNING_STATUSES,
    ReviewJob,
    normalize_status,
)


def has_running_reviews(reviews: list[ReviewJob]) -> bool:
    """Return True if any reviews are still in progress (running/queued/pending).

    Tolerates None or non-string status values.
    """
    return any(normalize_status(r.status) in RUNNING_STATUSES for r in reviews)


# Braille spinner frames (same as widgets.primitives.Spinner)
_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class ReviewItem(Static):
    """Single review item: verdict icon, short SHA, truncated subject. Click shows detail."""

    DEFAULT_CSS = """
    ReviewItem {
        height: 1;
        pointer: pointer;
    }
    ReviewItem:hover {
        background: $panel;
    }
    """

    can_focus = True

    def __init__(self, review: ReviewJob) -> None:
        super().__init__()
        self.review = review
        self._spinner_frame = 0
        self._timer = None

    @property
    def _is_running(self) -> bool:
        return normalize_status(self.review.status) in RUNNING_STATUSES

    def on_mount(self) -> None:
        if self._is_running:
            self._timer = self.set_interval(1 / 10, self._tick)

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _tick(self) -> None:
        self._spinner_frame = (self._spinner_frame + 1) % len(_SPINNER_FRAMES)
        self.refresh(layout=False)

    def render(self) -> Text:
        # Verdict icon: P green, F red, spinner for running
        verdict = str(self.review.verdict or "").upper()
        if self._is_running:
            icon = (_SPINNER_FRAMES[self._spinner_frame] + " ", "yellow")
        elif verdict in ("P", "PASS"):
            icon = ("P ", "green")
        elif verdict in ("F", "FAIL"):
            icon = ("F ", "red")
        else:
            icon = ("? ", "dim")

        # Job ID (check for None and empty — 0 is a valid ID)
        job_id = (
            "?" if self.review.id is None or self.review.id == "" else self.review.id
        )

        # Short SHA (first 7 chars of git_ref)
        sha = self.review.git_ref[:7] if self.review.git_ref else "???????"

        # Truncated subject
        subject = self.review.commit_subject
        max_len = 18
        if len(subject) > max_len:
            subject = subject[: max_len - 1] + "…"

        return Text.assemble(
            icon, (f"#{job_id} ", "bold dim"), (f"{sha} ", "dim"), (subject, "")
        )

    def on_click(self, event) -> None:  # noqa: ARG002
        """Show review detail in chat via /reviews <id>."""
        from claudechic.commands import handle_command

        handle_command(self.app, f"/reviews {self.review.id}")  # type: ignore[arg-type]


class ReviewPanel(Widget):
    """Sidebar panel for roborev reviews."""

    DEFAULT_CSS = """
    ReviewPanel {
        width: 100%;
        height: auto;
        max-height: 30%;
        border-top: solid $panel;
        padding: 1;
    }
    ReviewPanel.hidden {
        display: none;
    }
    ReviewPanel .review-title {
        color: $text-muted;
        text-style: bold;
        padding: 0 0 1 0;
    }
    ReviewItem {
        height: 1;
    }
    """

    can_focus = False

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._reviews: list[ReviewJob] = []

    @property
    def review_count(self) -> int:
        """Number of reviews."""
        return len(self._reviews)

    def compose(self) -> ComposeResult:
        yield Static("Reviews", classes="review-title")

    def set_visible(self, visible: bool) -> None:
        """Control visibility (only shows if has reviews and visible=True)."""
        if visible and self._reviews:
            self.remove_class("hidden")
        else:
            self.add_class("hidden")

    def update_reviews(self, reviews: list[ReviewJob]) -> None:
        """Replace reviews with new list. Visibility controlled by set_visible().

        Note: This recreates all ReviewItem widgets, which resets spinner
        animation state for running reviews.  Acceptable since polls are
        infrequent (every 5s) and the spinner restarts instantly.
        """
        self._reviews = reviews
        # Remove old items
        for item in self.query(ReviewItem):
            item.remove()

        # Add new items
        for review in reviews:
            self.mount(ReviewItem(review))
