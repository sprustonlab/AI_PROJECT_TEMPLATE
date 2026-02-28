"""Process list modal."""

from datetime import datetime

from rich.table import Table

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Button

from claudechic.processes import BackgroundProcess


def _format_duration(start_time: datetime) -> str:
    """Format duration since start_time."""
    delta = datetime.now() - start_time
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    elif secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    else:
        hours = secs // 3600
        mins = (secs % 3600) // 60
        return f"{hours}h {mins}m"


def _get_process_table(processes: list[BackgroundProcess]) -> Table:
    """Build a table of running processes."""
    table = Table(
        box=None,
        padding=(0, 2),
        collapse_padding=True,
        show_header=True,
    )
    table.add_column("PID", justify="right", style="dim")
    table.add_column("Command")
    table.add_column("Duration", justify="right", style="dim")

    for proc in processes:
        cmd = proc.command
        if len(cmd) > 50:
            cmd = cmd[:47] + "..."
        table.add_row(str(proc.pid), cmd, _format_duration(proc.start_time))

    return table


class ProcessModal(ModalScreen):
    """Modal showing running background processes."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    ProcessModal {
        align: center middle;
    }

    ProcessModal #process-container {
        width: auto;
        min-width: 50;
        max-width: 80%;
        height: auto;
        max-height: 60%;
        background: $surface;
        border: solid $panel;
        padding: 1 2;
    }

    ProcessModal #process-header {
        height: 1;
        margin-bottom: 1;
    }

    ProcessModal #process-title {
        width: 1fr;
    }

    ProcessModal #process-content {
        height: auto;
    }

    ProcessModal #process-footer {
        height: 1;
        margin-top: 1;
        align: center middle;
    }

    ProcessModal #close-btn {
        min-width: 10;
    }
    """

    def __init__(self, processes: list[BackgroundProcess]) -> None:
        super().__init__()
        self._processes = processes

    def compose(self) -> ComposeResult:
        with Vertical(id="process-container"):
            with Horizontal(id="process-header"):
                yield Static(
                    "[bold]Background Processes[/]", id="process-title", markup=True
                )
            if self._processes:
                yield Static(_get_process_table(self._processes), id="process-content")
            else:
                yield Static(
                    "[dim]No background processes running.[/]",
                    id="process-content",
                    markup=True,
                )
            with Horizontal(id="process-footer"):
                yield Button("Close", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()
