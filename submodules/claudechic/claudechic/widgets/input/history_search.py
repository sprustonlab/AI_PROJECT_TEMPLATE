"""Reverse history search widget (Ctrl+R)."""

from __future__ import annotations

import re

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Static

from claudechic.history import load_global_history


class HistorySearch(Widget):
    """Reverse search through command history (like bash Ctrl+R).

    Shows single match inline. Ctrl+R cycles to older matches.
    """

    DEFAULT_CSS = """\
    HistorySearch {
        height: auto;
        width: 100%;
        display: none;
        background: $surface;
        border-left: tall $primary;
        padding: 0 1;

        & Horizontal {
            width: 100%;
            height: 1;
        }

        & #search-label {
            width: auto;
            color: $primary;
        }

        & #search-input {
            width: 1fr;
            height: 1;
            border: none;
            background: transparent;
            padding: 0;

            &:focus {
                border: none;
            }
        }

        & #match-display {
            width: 100%;
            height: auto;
            max-height: 3;
            color: $text-muted;
            padding: 0;
        }
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True, show=False),
        Binding("enter", "select", "Select", priority=True, show=False),
        Binding("ctrl+r", "next_match", "Next", priority=True, show=False),
        Binding("up", "prev_match", "Prev", priority=True, show=False),
        Binding("down", "next_match", "Next", priority=True, show=False),
    ]

    class Selected(Message):
        """Posted when user selects a history entry."""

        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    class Cancelled(Message):
        """Posted when user cancels search."""

        pass

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._history: list[str] = []
        self._filtered: list[str] = []
        self._match_index: int = 0
        self._query: str = ""

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static("(reverse-i-search)`", id="search-label")
            yield Input(placeholder="", id="search-input")
        yield Static("", id="match-display")

    def on_mount(self) -> None:
        self._history = load_global_history(limit=500)

    def show(self) -> None:
        """Show the search widget and focus input."""
        self.styles.display = "block"
        self._filtered = self._history
        self._match_index = 0
        self._query = ""
        self._update_display()
        inp = self.query_one("#search-input", Input)
        inp.value = ""
        inp.focus()

    def hide(self) -> None:
        """Hide the search widget."""
        self.styles.display = "none"

    def _current_match(self) -> str | None:
        """Get the currently selected match."""
        if self._filtered and 0 <= self._match_index < len(self._filtered):
            return self._filtered[self._match_index]
        return None

    def _update_display(self) -> None:
        """Update the match display with highlighted query."""
        display = self.query_one("#match-display", Static)
        match = self._current_match()
        if match:
            # Truncate and format for display
            text = match[:200] + "..." if len(match) > 200 else match
            text = text.replace("\n", " ⏎ ")
            text = escape(text)  # Escape Rich markup chars

            # Highlight the query match (case-insensitive)
            if self._query:
                escaped_query = escape(self._query)
                pattern = re.compile(re.escape(escaped_query), re.IGNORECASE)
                theme = self.app.current_theme
                primary = theme.primary if isinstance(theme.primary, str) else "#cc7700"
                text = pattern.sub(lambda m: f"[bold {primary}]{m.group()}[/]", text)

            # Show position if multiple matches
            if len(self._filtered) > 1:
                display.update(
                    f"\\[{self._match_index + 1}/{len(self._filtered)}] {text}"
                )
            else:
                display.update(text)
        else:
            display.update("[dim]no match[/dim]")

    def action_cancel(self) -> None:
        """Hide search and post Cancelled message."""
        self.hide()
        self.post_message(self.Cancelled())

    def action_select(self) -> None:
        """Accept current match and post Selected message."""
        match = self._current_match()
        if match:
            self.post_message(self.Selected(match))
        self.hide()

    def action_next_match(self) -> None:
        """Move to next (older) match."""
        if self._filtered and self._match_index < len(self._filtered) - 1:
            self._match_index += 1
            self._update_display()

    def action_prev_match(self) -> None:
        """Move to previous (newer) match."""
        if self._match_index > 0:
            self._match_index -= 1
            self._update_display()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter history as user types."""
        self._query = event.value
        query = self._query.lower()
        if not query:
            self._filtered = self._history
        else:
            self._filtered = [h for h in self._history if query in h.lower()]
        self._match_index = 0
        self._update_display()

    def on_input_blurred(self, _event: Input.Blurred) -> None:
        """Hide when input loses focus."""
        if self.styles.display != "none":
            self.hide()
            self.post_message(self.Cancelled())
