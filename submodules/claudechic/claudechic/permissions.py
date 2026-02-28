"""Permission request handling for tool approvals."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from claudechic.enums import PermissionChoice
from claudechic.formatting import format_tool_header


@dataclass
class PermissionResponse:
    """Response to a permission request.

    Replaces string-based patterns like "deny:reason" with typed data.
    """

    choice: PermissionChoice
    alternative_message: str | None = None


@dataclass
class PermissionRequest:
    """Represents a pending permission request.

    Used for both UI display and programmatic testing.
    """

    tool_name: str
    tool_input: dict[str, Any]
    _event: asyncio.Event = field(default_factory=asyncio.Event)
    _result: PermissionResponse | None = field(default=None)

    @property
    def title(self) -> str:
        """Format permission prompt title."""
        return f"Allow {format_tool_header(self.tool_name, self.tool_input)}?"

    def respond(self, result: PermissionResponse) -> None:
        """Respond to this permission request."""
        self._result = result
        self._event.set()

    async def wait(self) -> PermissionResponse:
        """Wait for response (from UI or programmatic).

        Returns:
            The PermissionResponse with choice and optional alternative message.
        """
        await self._event.wait()
        return self._result or PermissionResponse(PermissionChoice.DENY)
