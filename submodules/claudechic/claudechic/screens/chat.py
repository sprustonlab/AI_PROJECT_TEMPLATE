"""Main chat screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.message import Message
from textual.screen import Screen

from claudechic.widgets import (
    ChatView,
    ChatInput,
    ImageAttachments,
    TextAreaAutoComplete,
    HistorySearch,
    AgentSection,
    TodoPanel,
    ProcessPanel,
    PlanSection,
    FilesSection,
    HamburgerButton,
    ReviewPanel,
)
from claudechic.widgets.layout.footer import StatusFooter


class InputContainer(Vertical):
    """Input container with text cursor on hover (via CSS pointer: text)."""

    pass


if TYPE_CHECKING:
    from claudechic.app import ChatApp


class ChatScreen(Screen):
    """Main chat screen with all chat widgets."""

    BINDINGS = [
        Binding("escape", "escape", "Cancel", show=False),
        Binding("ctrl+l", "clear", "Clear", show=False),
        Binding("ctrl+r", "history_search", "History", priority=True, show=False),
        Binding(
            "shift+tab", "cycle_permission_mode", "Auto-edit", priority=True, show=False
        ),
    ]

    def __init__(self, slash_commands: list[str] | None = None) -> None:
        super().__init__()
        self._slash_commands = slash_commands or []

    def compose(self) -> ComposeResult:
        yield HamburgerButton(id="hamburger-btn")
        with Horizontal(id="main"):
            with Vertical(id="chat-column"):
                yield ChatView(id="chat-view")
                with InputContainer(id="input-container"):
                    yield ImageAttachments(id="image-attachments", classes="hidden")
                    yield HistorySearch(id="history-search")
                    yield ChatInput(id="input")
                    yield TextAreaAutoComplete(
                        "#input",
                        slash_commands=self._slash_commands,
                    )
            with Vertical(id="right-sidebar", classes="hidden"):
                yield AgentSection(id="agent-section")
                yield PlanSection(id="plan-section", classes="hidden")
                yield FilesSection(id="files-section", classes="hidden")
                yield TodoPanel(id="todo-panel")
                yield ReviewPanel(id="review-panel", classes="hidden")
                yield ProcessPanel(id="process-panel", classes="hidden")
        yield StatusFooter()

    def on_mount(self) -> None:
        """Signal to app that screen widgets are ready."""
        # Post a message to let the app know widgets are available
        self.post_message(ChatScreen.Ready())

    # Actions delegate to app since app owns agent state
    @property
    def chat_app(self) -> ChatApp:
        return cast("ChatApp", self.app)

    def action_escape(self) -> None:
        self.chat_app.action_escape()

    def action_clear(self) -> None:
        self.chat_app.action_clear()

    def action_history_search(self) -> None:
        self.chat_app.action_history_search()

    def action_cycle_permission_mode(self) -> None:
        self.chat_app.action_cycle_permission_mode()

    class Ready(Message):
        """Posted when chat screen widgets are mounted and ready."""
