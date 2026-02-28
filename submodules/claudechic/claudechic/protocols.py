"""Callback protocols for Agent and AgentManager integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from claude_agent_sdk import ResultMessage, SystemMessage

    from claudechic.agent import Agent, ImageAttachment, ToolUse
    from claudechic.permissions import PermissionRequest, PermissionResponse


class AgentManagerObserver(Protocol):
    """Observer for AgentManager lifecycle events."""

    def on_agent_created(self, agent: Agent) -> None:
        """Called when a new agent is created."""
        ...

    def on_agent_switched(self, new_agent: Agent, old_agent: Agent | None) -> None:
        """Called when the active agent changes."""
        ...

    def on_agent_closed(self, agent_id: str, message_count: int) -> None:
        """Called when an agent is closed."""
        ...

    def on_global_permission_mode_changed(self, mode: str) -> None:
        """Called when global permission mode changes."""
        ...


class AgentObserver(Protocol):
    """Observer for per-agent events.

    All methods receive the agent as the first argument to identify the source.
    """

    def on_status_changed(self, agent: Agent) -> None:
        """Called when agent status changes (idle/busy/needs_input)."""
        ...

    def on_permission_mode_changed(self, agent: Agent) -> None:
        """Called when permission_mode changes (default/acceptEdits/plan)."""
        ...

    def on_message_updated(self, agent: Agent) -> None:
        """Called when agent message content changes."""
        ...

    def on_prompt_added(self, agent: Agent, request: PermissionRequest) -> None:
        """Called when a permission prompt is queued."""
        ...

    def on_error(self, agent: Agent, message: str, exception: Exception | None) -> None:
        """Called when an error occurs."""
        ...

    def on_connection_lost(self, agent: Agent) -> None:
        """Called when SDK connection is lost and needs reconnection."""
        ...

    def on_complete(self, agent: Agent, result: ResultMessage | None) -> None:
        """Called when a response completes."""
        ...

    def on_todos_updated(self, agent: Agent) -> None:
        """Called when TodoWrite updates the todo list."""
        ...

    def on_text_chunk(
        self, agent: Agent, text: str, new_message: bool, parent_tool_use_id: str | None
    ) -> None:
        """Called for each streaming text chunk."""
        ...

    def on_tool_use(self, agent: Agent, tool: ToolUse) -> None:
        """Called when a tool use starts."""
        ...

    def on_tool_result(self, agent: Agent, tool: ToolUse) -> None:
        """Called when a tool result arrives."""
        ...

    def on_system_message(self, agent: Agent, message: SystemMessage) -> None:
        """Called for SDK system messages."""
        ...

    def on_command_output(self, agent: Agent, content: str) -> None:
        """Called for local command output (e.g., /context)."""
        ...

    def on_skill_loaded(self, agent: Agent, skill_name: str) -> None:
        """Called when SDK loads a skill (user-defined slash command)."""
        ...

    def on_prompt_sent(
        self, agent: Agent, prompt: str, images: list[ImageAttachment]
    ) -> None:
        """Called when a user prompt is sent."""
        ...


class PermissionHandler(Protocol):
    """Handler for permission UI interactions.

    Returns a PermissionResponse with the user's choice and optional alternative message.
    """

    async def __call__(
        self, agent: Agent, request: PermissionRequest
    ) -> PermissionResponse: ...
