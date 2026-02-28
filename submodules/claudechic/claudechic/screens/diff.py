"""Diff review screen."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Static

from claudechic.features.diff import DiffSidebar, DiffView, get_changes
from claudechic.features.diff.git import HunkComment
from claudechic.features.diff.widgets import DiffFileItem

# Width threshold below which sidebar is hidden
SIDEBAR_MIN_WIDTH = 100


class DiffScreen(Screen[list[HunkComment]]):
    """Full-screen diff viewer for reviewing uncommitted changes."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = """
    DiffScreen {
        background: $background;
    }

    DiffScreen #diff-container {
        width: 100%;
        height: 100%;
    }

    DiffScreen #diff-empty {
        width: 100%;
        height: 100%;
        content-align: center middle;
        color: $text-muted;
    }

    DiffScreen #diff-sidebar.hidden {
        display: none;
    }
    """

    def __init__(
        self, cwd: Path, target: str = "HEAD", focus_file: str | None = None
    ) -> None:
        super().__init__()
        self._cwd = cwd
        self._target = target
        self._focus_file = focus_file
        self._sidebar: DiffSidebar | None = None
        self._view: DiffView | None = None

    def compose(self) -> ComposeResult:
        # Placeholder - will be replaced with actual content on mount
        yield Static("Loading...", id="diff-empty")

    async def on_mount(self) -> None:
        """Fetch changes and build the diff view."""
        changes = await get_changes(str(self._cwd), self._target)

        # Remove placeholder
        placeholder = self.query_one("#diff-empty")
        await placeholder.remove()

        if not changes:
            msg = (
                f"No changes vs {self._target}"
                if self._target != "HEAD"
                else "No uncommitted changes"
            )
            self.mount(Static(msg, id="diff-empty", markup=False))
            return

        # Build diff UI
        container = Horizontal(id="diff-container")
        self._sidebar = DiffSidebar(changes, id="diff-sidebar")
        self._view = DiffView(changes, id="diff-view")

        self.mount(container)
        container.mount(self._sidebar)
        container.mount(self._view)

        # Focus on specific file if requested (defer to allow widgets to mount)
        if self._focus_file and self._view:
            self.call_after_refresh(self._focus_on_file)
        else:
            self._view.focus()

    def _focus_on_file(self) -> None:
        """Focus on the specified file after widgets are ready."""
        if self._focus_file and self._view:
            self._view.scroll_to_file(self._focus_file)
            if self._sidebar:
                self._sidebar.set_active(self._focus_file)

    def action_go_back(self) -> None:
        """Return to chat with collected comments."""
        comments = self._view.get_comments() if self._view else []
        self.dismiss(comments)

    def on_key(self, event) -> None:
        """Handle j/k for hunk navigation and Enter for commenting."""
        # If editing a comment, let the input handle all keys
        if self._view and self._view.is_editing():
            return

        if event.key in ("j", "down"):
            if self._view:
                self._view.action_next_file()
            event.prevent_default()
            event.stop()
        elif event.key in ("k", "up"):
            if self._view:
                self._view.action_prev_file()
            event.prevent_default()
            event.stop()
        elif event.key in ("enter", "o"):
            if self._view:
                hunk = self._view.get_current_hunk_widget()
                if hunk:
                    hunk.start_editing()
            event.prevent_default()
            event.stop()
        elif event.key == "q":
            self.action_go_back()
            event.prevent_default()
            event.stop()

    def on_diff_file_item_selected(self, event: DiffFileItem.Selected) -> None:
        """Handle programmatic file selection - update sidebar highlight."""
        if self._sidebar:
            self._sidebar.set_active(event.path)

    def on_diff_file_item_clicked(self, event: DiffFileItem.Clicked) -> None:
        """Handle user click on sidebar item - scroll to file."""
        if self._sidebar:
            self._sidebar.set_active(event.path)
        if self._view:
            self._view.scroll_to_file(event.path)

    def on_resize(self) -> None:
        """Hide sidebar when screen is narrow."""
        if self._sidebar:
            if self.size.width < SIDEBAR_MIN_WIDTH:
                self._sidebar.add_class("hidden")
            else:
                self._sidebar.remove_class("hidden")
