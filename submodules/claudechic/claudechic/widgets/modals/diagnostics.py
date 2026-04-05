"""Diagnostics modal - shows session JSONL path and last compaction summary."""

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static, Button

from claudechic.sessions import get_project_sessions_dir


def _read_last_compact_summary(jsonl_path: str) -> str | None:
    """Read the last compaction summary from a session JSONL file.

    After autocompaction, the SDK writes a user message with isCompactSummary=true.
    The summary text is in message.content (a string).
    """
    path = Path(jsonl_path)
    if not path.is_file():
        return None
    try:
        last_summary = None
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Quick check before parsing JSON
                if "isCompactSummary" not in line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("isCompactSummary"):
                    content = msg.get("message", {}).get("content", "")
                    if isinstance(content, str) and content:
                        last_summary = content
        return last_summary
    except OSError:
        return None


class DiagnosticsModal(ModalScreen):
    """Modal showing session diagnostics info."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    DiagnosticsModal {
        align: center middle;
    }

    DiagnosticsModal #diagnostics-container {
        width: auto;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: solid $panel;
        padding: 1 2;
    }

    DiagnosticsModal #diagnostics-header {
        height: 1;
        margin-bottom: 1;
    }

    DiagnosticsModal #diagnostics-title {
        width: 1fr;
    }

    DiagnosticsModal .section-header {
        height: 1;
        margin-top: 1;
    }

    DiagnosticsModal .section-title {
        width: 1fr;
    }

    DiagnosticsModal .copy-btn {
        width: 3;
        min-width: 3;
        height: 1;
        padding: 0;
        background: transparent;
        border: none;
        color: $text-muted;
    }

    DiagnosticsModal .copy-btn:hover {
        color: $primary;
        background: transparent;
    }

    DiagnosticsModal #jsonl-path {
        height: auto;
        padding: 0 0 0 1;
        color: $text-muted;
    }

    DiagnosticsModal #compaction-scroll {
        max-height: 12;
        height: auto;
        padding: 0 0 0 1;
    }

    DiagnosticsModal #compaction-content {
        height: auto;
        color: $text-muted;
    }

    DiagnosticsModal #diagnostics-footer {
        height: 1;
        margin-top: 1;
        align: center middle;
    }

    DiagnosticsModal #close-btn {
        min-width: 10;
    }
    """

    def __init__(
        self, session_id: str | None, cwd: Path | None = None, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._session_id = session_id
        self._cwd = cwd
        self._jsonl_path = self._resolve_path()
        self._compact_summary = _read_last_compact_summary(self._jsonl_path)

    def _resolve_path(self) -> str:
        """Compute the JSONL file path for the current session."""
        if not self._session_id:
            return "(no active session)"
        sessions_dir = get_project_sessions_dir(self._cwd)
        if not sessions_dir:
            return "(sessions directory not found)"
        return str(sessions_dir / f"{self._session_id}.jsonl")

    def compose(self) -> ComposeResult:
        with Vertical(id="diagnostics-container"):
            with Horizontal(id="diagnostics-header"):
                yield Static(
                    "[bold]Diagnostics[/]", id="diagnostics-title", markup=True
                )
            # Session JSONL section
            with Horizontal(classes="section-header"):
                yield Static(
                    "[bold]Session JSONL[/]", classes="section-title", markup=True
                )
                yield Button("\u29c9", id="copy-jsonl-btn", classes="copy-btn")
            yield Static(self._jsonl_path, id="jsonl-path")
            # Last compaction summary section
            with Horizontal(classes="section-header"):
                yield Static(
                    "[bold]Last Compaction[/]", classes="section-title", markup=True
                )
                yield Button("\u29c9", id="copy-compaction-btn", classes="copy-btn")
            if self._compact_summary:
                with VerticalScroll(id="compaction-scroll"):
                    yield Static(self._compact_summary, id="compaction-content")
            else:
                yield Static("(no compaction this session)", id="compaction-content")
            with Horizontal(id="diagnostics-footer"):
                yield Button("Close", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "copy-jsonl-btn":
            self._copy_to_clipboard(self._jsonl_path)
        elif event.button.id == "copy-compaction-btn":
            if self._compact_summary:
                self._copy_to_clipboard(self._compact_summary)
            else:
                self.notify("No compaction summary to copy", severity="warning")
        elif event.button.id == "close-btn":
            self.dismiss()

    def _copy_to_clipboard(self, text: str) -> None:
        """Copy text to clipboard with notification."""
        try:
            import pyperclip

            pyperclip.copy(text)
            self.notify("Copied to clipboard")
        except Exception as e:
            self.notify(f"Copy failed: {e}", severity="error")
