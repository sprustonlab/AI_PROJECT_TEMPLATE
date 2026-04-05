"""Chicsession picker screen for /chicsession restore."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Input, Static

from claudechic.chicsessions import ChicsessionManager


class ChicsessionItem(ListItem):
    """A chicsession entry in the picker list."""

    DEFAULT_CSS = """
    ChicsessionItem {
        pointer: pointer;
    }
    """

    def __init__(self, name: str, agent_count: int, agent_names: list[str]) -> None:
        super().__init__()
        self.chicsession_name = name
        self.agent_count = agent_count
        self.agent_names = agent_names

    def compose(self) -> ComposeResult:
        yield Label(self.chicsession_name, classes="chicsession-title")
        agents_str = ", ".join(self.agent_names) if self.agent_names else "—"
        yield Label(
            f"{self.agent_count} agent{'s' if self.agent_count != 1 else ''} · {agents_str}",
            classes="chicsession-meta",
        )


class ChicsessionScreen(Screen[str | None]):
    """Full-screen picker for restoring a chicsession.

    Args:
        root_dir: Root directory for .chicsessions/ storage.
    """

    def __init__(self, root_dir: Path) -> None:
        super().__init__()
        self._root_dir = root_dir

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = """
    ChicsessionScreen {
        background: $background;
        align: center top;
    }

    ChicsessionScreen #chicsession-container {
        width: 100%;
        max-width: 80;
        height: 100%;
        padding: 1 2;
    }

    ChicsessionScreen #chicsession-title {
        height: 1;
        margin-bottom: 1;
        text-style: bold;
    }

    ChicsessionScreen #chicsession-search {
        height: 3;
        margin-bottom: 1;
    }

    ChicsessionScreen #chicsession-list,
    ChicsessionScreen #chicsession-list:focus {
        height: 1fr;
        background: transparent;
    }

    ChicsessionScreen #chicsession-list > ChicsessionItem {
        padding: 0 0 0 1;
        height: auto;
        margin: 0 0 1 0;
        border-left: tall $panel;
    }

    ChicsessionScreen #chicsession-list > ChicsessionItem:hover,
    ChicsessionScreen #chicsession-list > ChicsessionItem.-highlight {
        background: $surface-darken-1;
        border-left: tall $primary;
    }

    ChicsessionScreen .chicsession-meta {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="chicsession-container"):
            yield Static("Restore Chicsession", id="chicsession-title")
            yield Input(placeholder="Search chicsessions...", id="chicsession-search")
            yield ListView(id="chicsession-list")

    def on_mount(self) -> None:
        self._update_list("")
        self.query_one("#chicsession-search", Input).focus()

    def on_key(self, event) -> None:
        """Forward navigation keys to list."""
        list_view = self.query_one("#chicsession-list", ListView)
        if event.key == "down":
            list_view.action_cursor_down()
            event.prevent_default()
        elif event.key == "up":
            list_view.action_cursor_up()
            event.prevent_default()

    def action_go_back(self) -> None:
        self.dismiss(None)

    def _update_list(self, search: str) -> None:
        mgr = ChicsessionManager(self._root_dir)
        names = mgr.list_chicsessions()

        search_lower = search.lower()
        if search_lower:
            names = [n for n in names if search_lower in n.lower()]

        list_view = self.query_one("#chicsession-list", ListView)
        list_view.clear()

        title = self.query_one("#chicsession-title", Static)

        if not names:
            title.update("No chicsessions found")
            return

        title.update(f"Restore Chicsession ({len(names)})")

        for cs_name in names:
            try:
                cs = mgr.load(cs_name)
                agent_names = [a.name for a in cs.agents]
                list_view.append(
                    ChicsessionItem(cs_name, len(cs.agents), agent_names)
                )
            except (ValueError, FileNotFoundError):
                list_view.append(ChicsessionItem(cs_name, 0, []))

        if names:
            list_view.index = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "chicsession-search":
            self._update_list(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "chicsession-search":
            list_view = self.query_one("#chicsession-list", ListView)
            if list_view.index is not None and list_view.highlighted_child:
                item = list_view.highlighted_child
                list_view.post_message(
                    ListView.Selected(list_view, item, list_view.index)
                )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ChicsessionItem):
            self.dismiss(event.item.chicsession_name)
