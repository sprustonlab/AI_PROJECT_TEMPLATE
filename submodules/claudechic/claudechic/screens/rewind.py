"""Rewind screen for checkpoint selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, Static

if TYPE_CHECKING:
    from claudechic.agent import Agent
    from claudechic.checkpoints import Checkpoint


class CheckpointItem(ListItem):
    """A checkpoint in the rewind picker."""

    DEFAULT_CSS = """
    CheckpointItem {
        pointer: pointer;
    }
    """

    def __init__(self, checkpoint: "Checkpoint") -> None:
        super().__init__()
        self.checkpoint = checkpoint

    def compose(self) -> ComposeResult:
        # Format: "#0: First message preview..."
        yield Label(f"#{self.checkpoint.index}: {self.checkpoint.preview}")
        # Show tool count if any
        tool_text = (
            f"{self.checkpoint.tool_count} tool use{'s' if self.checkpoint.tool_count != 1 else ''}"
            if self.checkpoint.tool_count > 0
            else "no tool uses"
        )
        yield Label(tool_text, classes="checkpoint-meta")


class RewindTypeItem(ListItem):
    """A rewind type option (conversation, code, or both)."""

    DEFAULT_CSS = """
    RewindTypeItem {
        pointer: pointer;
    }
    """

    def __init__(self, rewind_type: str, label: str, description: str) -> None:
        super().__init__()
        self.rewind_type = rewind_type
        self._label = label
        self._description = description

    def compose(self) -> ComposeResult:
        yield Label(self._label)
        yield Label(self._description, classes="rewind-type-desc")


class RewindScreen(Screen[tuple[int, str] | None]):
    """Full-screen rewind picker for selecting a checkpoint and rewind type.

    Returns (checkpoint_index, rewind_type) or None if cancelled.
    rewind_type is one of: "conversation", "code", "both"
    """

    def __init__(self, agent: "Agent") -> None:
        super().__init__()
        self._agent = agent
        self._selected_checkpoint: int | None = None
        self._phase: str = "checkpoint"  # "checkpoint" or "type"

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
    ]

    DEFAULT_CSS = """
    RewindScreen {
        background: $background;
        align: center top;
    }

    RewindScreen #rewind-container {
        width: 100%;
        max-width: 80;
        height: 100%;
        padding: 1 2;
    }

    RewindScreen #rewind-title {
        height: 1;
        margin-bottom: 1;
        text-style: bold;
    }

    RewindScreen #checkpoint-list,
    RewindScreen #checkpoint-list:focus,
    RewindScreen #type-list,
    RewindScreen #type-list:focus {
        height: 1fr;
        background: transparent;
    }

    RewindScreen #checkpoint-list > CheckpointItem,
    RewindScreen #type-list > RewindTypeItem {
        padding: 0 0 0 1;
        height: auto;
        margin: 0 0 1 0;
        border-left: tall $panel;
    }

    RewindScreen #checkpoint-list > CheckpointItem:hover,
    RewindScreen #checkpoint-list > CheckpointItem.-highlight,
    RewindScreen #type-list > RewindTypeItem:hover,
    RewindScreen #type-list > RewindTypeItem.-highlight {
        background: $surface-darken-1;
        border-left: tall $primary;
    }

    RewindScreen .checkpoint-meta,
    RewindScreen .rewind-type-desc {
        color: $text-muted;
    }

    RewindScreen #type-list {
        display: none;
    }

    RewindScreen.phase-type #checkpoint-list {
        display: none;
    }

    RewindScreen.phase-type #type-list {
        display: block;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="rewind-container"):
            yield Static("Rewind to Checkpoint", id="rewind-title")
            yield ListView(id="checkpoint-list")
            yield ListView(id="type-list")

    def on_mount(self) -> None:
        self._update_checkpoint_list()

    def _update_checkpoint_list(self) -> None:
        """Populate the checkpoint list."""
        from claudechic.checkpoints import get_checkpoints

        checkpoints = get_checkpoints(self._agent)
        list_view = self.query_one("#checkpoint-list", ListView)
        list_view.clear()

        if not checkpoints:
            # No checkpoints - show message and dismiss
            self.notify("No checkpoints available", severity="warning")
            self.dismiss(None)
            return

        # Show checkpoints in reverse order (most recent first)
        for checkpoint in reversed(checkpoints):
            list_view.append(CheckpointItem(checkpoint))

        list_view.index = 0
        list_view.focus()

    def _show_type_selection(self) -> None:
        """Switch to type selection phase."""
        self._phase = "type"
        self.add_class("phase-type")

        title = self.query_one("#rewind-title", Static)
        title.update(f"Rewind to #{self._selected_checkpoint} - Select what to restore")

        type_list = self.query_one("#type-list", ListView)
        type_list.clear()
        type_list.append(
            RewindTypeItem(
                "both",
                "Both (Recommended)",
                "Restore conversation and revert file changes",
            )
        )
        type_list.append(
            RewindTypeItem(
                "conversation",
                "Conversation only",
                "Truncate conversation, keep file changes",
            )
        )
        type_list.append(
            RewindTypeItem(
                "code",
                "Code only",
                "Revert file changes, keep conversation",
            )
        )
        type_list.index = 0
        type_list.focus()

    def action_go_back(self) -> None:
        """Handle escape - go back to checkpoint selection or dismiss."""
        if self._phase == "type":
            # Go back to checkpoint selection
            self._phase = "checkpoint"
            self.remove_class("phase-type")
            title = self.query_one("#rewind-title", Static)
            title.update("Rewind to Checkpoint")
            self.query_one("#checkpoint-list", ListView).focus()
        else:
            # Dismiss without selecting
            self.dismiss(None)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection in either list."""
        if isinstance(event.item, CheckpointItem):
            # Checkpoint selected - show type selection
            self._selected_checkpoint = event.item.checkpoint.index
            self._show_type_selection()
        elif isinstance(event.item, RewindTypeItem):
            # Type selected - return result
            if self._selected_checkpoint is not None:
                self.dismiss((self._selected_checkpoint, event.item.rewind_type))
