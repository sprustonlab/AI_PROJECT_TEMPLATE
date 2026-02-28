"""Protocol for tool display widgets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from claude_agent_sdk import ToolResultBlock


@runtime_checkable
class ToolWidget(Protocol):
    """Protocol for widgets that display tool use/results.

    Implemented by:
    - ToolUseWidget: Standard tool display with collapsible details
    - TaskWidget: Nested subagent display
    - AgentToolWidget: MCP chic agent tools (spawn_agent, ask_agent, etc.)

    This protocol enables ChatView to treat all tool widgets uniformly
    for operations like collapse() and set_result().
    """

    def collapse(self) -> None:
        """Collapse this widget to save visual space."""
        ...

    def set_result(self, result: "ToolResultBlock") -> None:
        """Update the widget with the tool's result."""
        ...
