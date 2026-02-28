"""Single process detail modal with kill and metrics."""

import os
import signal
from datetime import datetime
from pathlib import Path

import psutil
from rich.table import Table

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Button, TextArea

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


def _format_bytes(n: int) -> str:
    """Format bytes as human-readable."""
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}{unit}"
        value /= 1024
    return f"{value:.1f}TB"


def _get_process_metrics(pid: int) -> dict | None:
    """Get metrics for a process via psutil."""
    try:
        proc = psutil.Process(pid)
        mem = proc.memory_info()
        cpu = proc.cpu_percent(interval=0.1)
        return {
            "status": proc.status(),
            "cpu_percent": cpu,
            "memory_rss": mem.rss,
            "memory_vms": mem.vms,
            "num_threads": proc.num_threads(),
            "num_fds": proc.num_fds() if hasattr(proc, "num_fds") else None,
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def _read_output_tail(output_file: str, max_lines: int = 50) -> str | None:
    """Read last N lines from output file."""
    try:
        path = Path(output_file)
        if not path.exists():
            return None
        text = path.read_text()
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        return "\n".join(lines)
    except Exception:
        return None


class ProcessDetailModal(ModalScreen):
    """Modal showing details for a single process with kill option."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    ProcessDetailModal {
        align: center middle;
    }

    ProcessDetailModal #detail-container {
        width: auto;
        min-width: 60;
        max-width: 80%;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: solid $panel;
        padding: 1 2;
    }

    ProcessDetailModal #detail-command {
        width: 100%;
        text-align: center;
        text-style: bold;
        color: $primary;
    }

    ProcessDetailModal #detail-pid {
        width: 100%;
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    ProcessDetailModal #detail-metrics {
        width: 100%;
        content-align: center middle;
    }

    ProcessDetailModal #detail-output {
        width: 100%;
        height: auto;
        max-height: 20;
        margin-top: 1;
        border: solid $panel;
    }

    ProcessDetailModal #detail-footer {
        width: 100%;
        height: auto;
        margin-top: 1;
        align: center middle;
    }

    ProcessDetailModal Button {
        margin: 0 1;
    }
    """

    def __init__(self, process: BackgroundProcess) -> None:
        super().__init__()
        self.process = process

    def compose(self) -> ComposeResult:
        metrics = _get_process_metrics(self.process.pid)

        with Vertical(id="detail-container"):
            yield Static(self.process.command, id="detail-command")
            yield Static(f"PID {self.process.pid}", id="detail-pid")

            if metrics:
                table = Table(box=None, show_header=False, padding=(0, 1), expand=False)
                table.add_column("Key", style="dim", no_wrap=True)
                table.add_column("Value", no_wrap=True, justify="right")

                table.add_row("Status", metrics["status"])
                table.add_row("Duration", _format_duration(self.process.start_time))
                table.add_row("CPU", f"{metrics['cpu_percent']:.1f}%")
                table.add_row("Memory (RSS)", _format_bytes(metrics["memory_rss"]))
                table.add_row("Memory (VMS)", _format_bytes(metrics["memory_vms"]))
                table.add_row("Threads", str(metrics["num_threads"]))
                if metrics["num_fds"] is not None:
                    table.add_row("Open FDs", str(metrics["num_fds"]))

                yield Static(table, id="detail-metrics")
            else:
                yield Static(
                    "[dim]Process no longer exists[/]",
                    id="detail-metrics",
                    markup=True,
                )

            # Show output if available
            if self.process.output_file:
                output = _read_output_tail(self.process.output_file)
                if output:
                    yield TextArea(output, id="detail-output", read_only=True)

            with Horizontal(id="detail-footer"):
                yield Button("Kill", id="kill-btn", variant="error")
                yield Button("Close", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()
        elif event.button.id == "kill-btn":
            self._kill_process()
            self.dismiss()

    def _kill_process(self) -> None:
        """Kill the process and its children."""
        try:
            proc = psutil.Process(self.process.pid)
            # Kill children first
            for child in proc.children(recursive=True):
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            # Then kill the process itself
            proc.terminate()
        except psutil.NoSuchProcess:
            pass  # Already dead
        except psutil.AccessDenied:
            # Try SIGKILL as fallback
            try:
                os.kill(self.process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
