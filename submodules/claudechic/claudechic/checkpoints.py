"""Checkpoint tracking for /rewind command.

Each user message creates a checkpoint that can be used to restore
conversation and/or file state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claudechic.agent import Agent, AssistantContent, UserContent


@dataclass
class Checkpoint:
    """A checkpoint representing state at a user message.

    Attributes:
        index: 0-based checkpoint number (position in conversation)
        uuid: SDK user message UUID (needed for rewind_files call)
        preview: First ~50 chars of user message for display
        tool_count: Number of tool uses after this checkpoint (before next user msg)
    """

    index: int
    uuid: str | None
    preview: str
    tool_count: int


def get_checkpoints(agent: "Agent") -> list[Checkpoint]:
    """Extract checkpoints from agent's message history.

    Each user message corresponds to a checkpoint. The UUID comes from
    agent.checkpoint_uuids which is populated when SDK reports UserMessage
    with UUIDs (requires enable_file_checkpointing=True and
    extra_args={"replay-user-messages": None}).

    Args:
        agent: The agent to extract checkpoints from

    Returns:
        List of Checkpoint objects, one per user message
    """
    checkpoints: list[Checkpoint] = []
    user_msg_index = 0

    # Track tool uses between user messages
    tool_count = 0
    pending_checkpoint: Checkpoint | None = None

    for item in agent.messages:
        if item.role == "user":
            # Finalize previous checkpoint's tool count
            if pending_checkpoint is not None:
                pending_checkpoint.tool_count = tool_count
                tool_count = 0

            # Extract preview text from user message
            content: "UserContent" = item.content  # type: ignore
            preview = _get_preview(content.text)

            # Get UUID if available
            uuid = None
            if user_msg_index < len(agent.checkpoint_uuids):
                uuid = agent.checkpoint_uuids[user_msg_index]

            checkpoint = Checkpoint(
                index=user_msg_index,
                uuid=uuid,
                preview=preview,
                tool_count=0,  # Updated when next user message arrives
            )
            checkpoints.append(checkpoint)
            pending_checkpoint = checkpoint
            user_msg_index += 1

        elif item.role == "assistant":
            # Count tool uses in assistant response
            from claudechic.agent import ToolUse

            assistant_content: "AssistantContent" = item.content  # type: ignore
            for block in assistant_content.blocks:
                if isinstance(block, ToolUse):
                    tool_count += 1

    # Finalize last checkpoint's tool count
    if pending_checkpoint is not None:
        pending_checkpoint.tool_count = tool_count

    return checkpoints


def _get_preview(text: str, max_length: int = 50) -> str:
    """Get preview of text for display, truncating if needed."""
    # Remove leading/trailing whitespace and collapse internal whitespace
    preview = " ".join(text.split())
    if len(preview) > max_length:
        return preview[: max_length - 1] + "\u2026"  # Unicode ellipsis
    return preview
