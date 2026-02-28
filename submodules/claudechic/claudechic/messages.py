"""Custom Textual messages for SDK event communication."""

from textual.message import Message

from claude_agent_sdk import (
    ToolUseBlock,
    ToolResultBlock,
    ResultMessage,
    SystemMessage as SDKSystemMessage,
)


class ResponseComplete(Message):
    """Message sent when Claude's response is complete."""

    def __init__(
        self, result: ResultMessage | None = None, agent_id: str | None = None
    ) -> None:
        self.result = result
        self.agent_id = agent_id
        super().__init__()


class ToolUseMessage(Message):
    """Message sent when a tool use starts."""

    def __init__(
        self,
        block: ToolUseBlock,
        parent_tool_use_id: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        self.block = block
        self.parent_tool_use_id = parent_tool_use_id
        self.agent_id = agent_id
        super().__init__()


class ToolResultMessage(Message):
    """Message sent when a tool result arrives."""

    def __init__(
        self,
        block: ToolResultBlock,
        parent_tool_use_id: str | None = None,
        agent_id: str | None = None,
    ) -> None:
        self.block = block
        self.parent_tool_use_id = parent_tool_use_id
        self.agent_id = agent_id
        super().__init__()


class SystemNotification(Message):
    """Message sent when a system notification arrives from SDK."""

    def __init__(
        self, sdk_message: SDKSystemMessage, agent_id: str | None = None
    ) -> None:
        self.sdk_message = sdk_message
        self.subtype = sdk_message.subtype
        self.data = sdk_message.data
        self.agent_id = agent_id
        super().__init__()


class CommandOutputMessage(Message):
    """Message sent when a local command (e.g., /context) produces output."""

    def __init__(self, content: str, agent_id: str | None = None) -> None:
        self.content = content  # Markdown content
        self.agent_id = agent_id
        super().__init__()
