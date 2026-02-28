"""Process panel widget for displaying background processes."""

from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from claudechic.processes import BackgroundProcess


class ProcessItem(Static):
    """Single process item with PID and command. Click to view details."""

    DEFAULT_CSS = """
    ProcessItem {
        pointer: pointer;
    }
    ProcessItem:hover {
        background: $panel;
    }
    """

    can_focus = True

    def __init__(self, process: BackgroundProcess) -> None:
        super().__init__()
        self.process = process

    def render(self) -> Text:
        # Show running indicator and truncated command
        cmd = self.process.command
        if len(cmd) > 20:
            cmd = cmd[:19] + "…"
        return Text.assemble(("● ", "yellow"), (cmd, ""))

    def on_click(self, event) -> None:  # noqa: ARG002
        """Show process detail modal."""
        from claudechic.widgets.modals.process_detail import ProcessDetailModal

        self.app.push_screen(ProcessDetailModal(self.process))


class ProcessPanel(Widget):
    """Sidebar panel for background processes."""

    DEFAULT_CSS = """
    ProcessPanel {
        width: 100%;
        height: auto;
        max-height: 30%;
        border-top: solid $panel;
        padding: 1;
    }
    ProcessPanel.hidden {
        display: none;
    }
    ProcessPanel .process-title {
        color: $text-muted;
        text-style: bold;
        padding: 0 0 1 0;
    }
    ProcessItem {
        height: 1;
    }
    """

    can_focus = False

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._processes: list[BackgroundProcess] = []

    @property
    def process_count(self) -> int:
        """Number of processes."""
        return len(self._processes)

    def compose(self) -> ComposeResult:
        yield Static("Processes", classes="process-title")

    def set_visible(self, visible: bool) -> None:
        """Control visibility (only shows if has processes and visible=True)."""
        if visible and self._processes:
            self.remove_class("hidden")
        else:
            self.add_class("hidden")

    def update_processes(self, processes: list[BackgroundProcess]) -> None:
        """Replace processes with new list. Visibility controlled by set_visible()."""
        self._processes = processes
        # Remove old items
        for item in self.query(ProcessItem):
            item.remove()

        # Add new items
        for proc in processes:
            self.mount(ProcessItem(proc))
