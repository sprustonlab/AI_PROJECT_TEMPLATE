"""Claude Chic - A stylish terminal UI for Claude Code."""

from importlib.metadata import version

from claudechic.app import ChatApp
from claudechic.theme import CHIC_THEME
from claudechic.protocols import AgentManagerObserver, AgentObserver, PermissionHandler

__all__ = [
    "ChatApp",
    "CHIC_THEME",
    "AgentManagerObserver",
    "AgentObserver",
    "PermissionHandler",
]
__version__ = version("claudechic")
