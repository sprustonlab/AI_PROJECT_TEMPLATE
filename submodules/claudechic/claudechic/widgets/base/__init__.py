"""Base classes for widgets.

Note: Mouse cursor styling is now handled via CSS (pointer: pointer, pointer: text).
See Textual 7.4.0+ for native support.
"""

from claudechic.widgets.base.clickable import ClickableLabel
from claudechic.widgets.base.tool_protocol import ToolWidget
from claudechic.widgets.base.tool_base import BaseToolWidget

__all__ = [
    "ClickableLabel",
    "ToolWidget",
    "BaseToolWidget",
]
