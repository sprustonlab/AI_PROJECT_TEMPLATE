"""Usage display widget for /usage command."""

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from claudechic.usage import UsageInfo, format_reset_time


class UsageBar(Widget):
    """A single usage bar with label, progress, and percentage."""

    DEFAULT_CSS = """
    UsageBar {
        height: 2;
        margin-bottom: 1;
    }
    UsageBar .label-row {
        height: 1;
    }
    UsageBar .bar-row {
        height: 1;
    }
    """

    BAR_WIDTH = 40

    def __init__(
        self, label: str, utilization: float, reset_text: str, **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self.label = label
        self.utilization = utilization
        self.reset_text = reset_text

    def compose(self) -> ComposeResult:
        yield Static(f"[bold]{self.label}[/bold]", classes="label-row", markup=True)
        yield Static(self._render_bar_line(), classes="bar-row", markup=True)

    def _render_bar_line(self) -> str:
        """Render bar + percentage + reset time on one line."""
        filled = int((self.utilization / 100) * self.BAR_WIDTH)
        empty = self.BAR_WIDTH - filled

        # Color based on utilization
        if self.utilization < 50:
            fill_color = "$secondary"  # Blue - plenty of headroom
        elif self.utilization < 80:
            fill_color = "$warning"  # Yellow - moderate
        else:
            fill_color = "$error"  # Red - high

        bar = f"[{fill_color}]{'█' * filled}[/][$panel]{'░' * empty}[/]"
        pct = f"{self.utilization:.0f}% used"

        if self.reset_text:
            return f"{bar} {pct} [dim]· {self.reset_text}[/dim]"
        return f"{bar} {pct}"


class UsageReport(Widget):
    """Full usage report widget."""

    DEFAULT_CSS = """
    UsageReport {
        height: auto;
        margin: 1 0;
        padding: 1;
        border: round $panel;
    }
    UsageReport .title {
        height: 1;
        text-align: center;
        margin-bottom: 1;
    }
    UsageReport .error {
        color: $error;
        text-align: center;
    }
    """

    def __init__(self, usage: UsageInfo, **kwargs) -> None:
        super().__init__(**kwargs)
        self.usage = usage

    def compose(self) -> ComposeResult:
        yield Static("[bold]Usage[/bold]", classes="title", markup=True)

        if self.usage.error:
            yield Static(f"Error: {self.usage.error}", classes="error", markup=False)
            return

        if self.usage.five_hour:
            yield UsageBar(
                "Current session",
                self.usage.five_hour.utilization,
                format_reset_time(self.usage.five_hour.resets_at),
            )

        if self.usage.seven_day:
            yield UsageBar(
                "Current week (all models)",
                self.usage.seven_day.utilization,
                format_reset_time(self.usage.seven_day.resets_at),
            )

        if self.usage.seven_day_sonnet:
            yield UsageBar(
                "Current week (Sonnet only)",
                self.usage.seven_day_sonnet.utilization,
                format_reset_time(self.usage.seven_day_sonnet.resets_at),
            )
