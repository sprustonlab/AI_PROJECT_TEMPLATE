"""CollapsedTurn: lightweight widget representing an entire user+assistant turn."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from textual.widget import Widget

from claudechic.widgets.primitives.collapsible import QuietCollapsible

if TYPE_CHECKING:
    from claudechic.agent import AssistantContent, UserContent


class CollapsedTurn(QuietCollapsible):
    """A collapsed representation of a user+assistant turn pair.

    Shows a summary like "fix the bug → 5 tools" when collapsed.
    Expands to full widgets (ChatMessage, ToolUseWidget, etc.) on click.
    Uses lazy loading - widgets are only created when first expanded.
    """

    DEFAULT_CSS = """
    CollapsedTurn {
        margin: 0;
        padding: 0;
        border-left: wide $panel;
        background: transparent;
    }
    CollapsedTurn:hover {
        border-left: wide $panel-lighten-2;
    }
    CollapsedTurn:focus-within {
        background: transparent;
    }
    CollapsedTurn > CollapsibleTitle {
        padding: 0;
        color: $text-muted;
        background: transparent;
    }
    CollapsedTurn > CollapsibleTitle:hover {
        background: $surface;
        color: $text-muted;
    }
    CollapsedTurn > CollapsibleTitle:focus {
        background: $surface;
        color: $text-muted;
        text-style: none;
    }
    CollapsedTurn > Contents {
        padding: 0;
    }
    """

    def __init__(
        self,
        user_content: UserContent,
        assistant_content: AssistantContent,
        widget_factory: Callable[[], list[Widget]],
        **kwargs,
    ) -> None:
        title = self._make_summary(user_content, assistant_content)
        super().__init__(
            title=title,
            collapsed=True,
            content_factory=widget_factory,
            collapsed_symbol="◇",
            expanded_symbol="◆",
            **kwargs,
        )

    @staticmethod
    def _make_summary(user: UserContent, assistant: AssistantContent) -> str:
        """Create a short summary of the turn."""
        from claudechic.agent import TextBlock, ToolUse

        # Truncate user prompt
        user_text = user.text.strip().replace("\n", " ")
        if len(user_text) > 40:
            user_text = user_text[:37] + "..."

        # Count assistant blocks
        tool_count = sum(1 for b in assistant.blocks if isinstance(b, ToolUse))
        text_count = sum(1 for b in assistant.blocks if isinstance(b, TextBlock))

        # Build response summary
        parts = []
        if tool_count:
            parts.append(f"{tool_count} tool{'s' if tool_count > 1 else ''}")
        if text_count:
            parts.append(f"{text_count} msg{'s' if text_count > 1 else ''}")

        response_summary = ", ".join(parts) if parts else "empty"
        return f"{user_text} → {response_summary}"
