"""Profile statistics modal."""

from rich.table import Table

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static, Button

from claudechic.profiling import get_stats_table, get_stats_text, reset_stats, _stats
from claudechic.sampling import get_sampler, flatten


def _get_sampling_table() -> Table | None:
    """Get sampling profiler results as a Rich Table."""
    sampler = get_sampler()
    if sampler is None:
        return None

    profile = sampler.get_merged_profile()
    flat = flatten(profile, min_count=1)
    if not flat:
        return None

    stats = sampler.get_stats()
    table = Table(
        box=None,
        padding=(0, 2),
        collapse_padding=True,
        show_header=True,
        title=f"[dim]CPU Samples (>{stats['threshold'] * 100:.0f}% threshold, {stats['sample_count']} samples)[/]",
        title_justify="left",
    )
    table.add_column("Function", style="dim")
    table.add_column("File", style="dim")
    table.add_column("Line", justify="right")
    table.add_column("Count", justify="right")
    table.add_column("%", justify="right")

    total = profile["count"] or 1
    for _ident, count, desc in flat[:20]:  # Top 20
        pct = count / total * 100
        # Shorten filename
        filename = desc["filename"]
        if len(filename) > 30:
            filename = "..." + filename[-27:]
        table.add_row(
            desc["name"],
            filename,
            str(desc["line_number"]),
            str(count),
            f"{pct:.1f}%",
        )
    return table


def _get_sampling_text() -> str:
    """Get sampling data as plain text with full filenames."""
    sampler = get_sampler()
    if sampler is None:
        return ""

    profile = sampler.get_merged_profile()
    flat = flatten(profile, min_count=1)
    if not flat:
        return ""

    stats = sampler.get_stats()
    total = profile["count"] or 1
    lines = [
        f"\nCPU Samples (>{stats['threshold'] * 100:.0f}% threshold, {stats['sample_count']} samples)",
        "",
    ]
    for _ident, count, desc in flat[:30]:  # More entries for clipboard
        pct = count / total * 100
        lines.append(
            f"{desc['name']:30} {count:5} ({pct:5.1f}%)  {desc['filename']}:{desc['line_number']}"
        )
    return "\n".join(lines)


class ProfileModal(ModalScreen):
    """Modal showing profiling statistics."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    ProfileModal {
        align: center middle;
    }

    ProfileModal #profile-container {
        width: auto;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: solid $panel;
        padding: 1 2;
    }

    ProfileModal #profile-header {
        height: 1;
        margin-bottom: 1;
    }

    ProfileModal #profile-title {
        width: 1fr;
    }

    ProfileModal #copy-btn {
        width: 3;
        min-width: 3;
        height: 1;
        padding: 0;
        background: transparent;
        border: none;
        color: $text-muted;
    }

    ProfileModal #copy-btn:hover {
        color: $primary;
        background: transparent;
    }

    ProfileModal #profile-scroll {
        height: auto;
        max-height: 50;
    }

    ProfileModal #profile-content {
        height: auto;
    }

    ProfileModal #sampling-content {
        height: auto;
        margin-top: 1;
    }

    ProfileModal #profile-footer {
        height: 1;
        margin-top: 1;
        align: center middle;
    }

    ProfileModal #close-btn {
        min-width: 10;
    }

    ProfileModal #reset-btn {
        min-width: 10;
        margin-right: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="profile-container"):
            with Horizontal(id="profile-header"):
                yield Static(
                    "[bold]Profiling Statistics[/]", id="profile-title", markup=True
                )
                yield Button("\u29c9", id="copy-btn")
            with VerticalScroll(id="profile-scroll"):
                if _stats:
                    yield Static(get_stats_table(), id="profile-content")
                else:
                    yield Static(
                        "[dim]No decorator profiling data.[/]",
                        id="profile-content",
                        markup=True,
                    )

                # Sampling profiler section
                sampling_table = _get_sampling_table()
                if sampling_table:
                    yield Static(sampling_table, id="sampling-content")
                else:
                    yield Static(
                        "[dim]No CPU samples collected (CPU stayed below threshold).[/]",
                        id="sampling-content",
                        markup=True,
                    )

            with Horizontal(id="profile-footer"):
                yield Button("Reset", id="reset-btn")
                yield Button("Close", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "copy-btn":
            try:
                import pyperclip

                text = get_stats_text() + "\n" + _get_sampling_text()
                pyperclip.copy(text)
                self.notify("Copied to clipboard")
            except Exception as e:
                self.notify(f"Copy failed: {e}", severity="error")
        elif event.button.id == "reset-btn":
            reset_stats()
            sampler = get_sampler()
            if sampler:
                sampler.reset()
            self.notify("Profiling stats reset")
            self.dismiss()
        elif event.button.id == "close-btn":
            self.dismiss()
