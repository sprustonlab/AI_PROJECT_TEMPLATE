"""Enums for magic strings used throughout the codebase."""

from enum import Enum


class StrEnum(str, Enum):
    """String enum base class (compatible with Python < 3.11)."""

    def __str__(self) -> str:
        return self.value


class ToolName(StrEnum):
    """Tool names from Claude Code SDK."""

    # File operations
    EDIT = "Edit"
    WRITE = "Write"
    READ = "Read"
    NOTEBOOK_EDIT = "NotebookEdit"

    # Command execution
    BASH = "Bash"

    # Search tools
    GLOB = "Glob"
    GREP = "Grep"

    # Task management
    TASK = "Task"
    TODO_WRITE = "TodoWrite"

    # Web tools
    WEB_SEARCH = "WebSearch"
    WEB_FETCH = "WebFetch"

    # User interaction
    ASK_USER_QUESTION = "AskUserQuestion"

    # Plan mode
    ENTER_PLAN_MODE = "EnterPlanMode"
    EXIT_PLAN_MODE = "ExitPlanMode"

    # Skills
    SKILL = "Skill"


class AgentStatus(StrEnum):
    """Agent status values (for sidebar UI display)."""

    IDLE = "idle"
    BUSY = "busy"
    NEEDS_INPUT = "needs_input"


class ResponseState(StrEnum):
    """Internal state of the agent's response processing pipeline.

    This is separate from AgentStatus (which is for UI display). ResponseState
    tracks the lifecycle of a single SDK response stream.

    Valid transitions::

        IDLE -> STREAMING      (_start_response)
        STREAMING -> IDLE      (_process_response finally block, normal completion)
        STREAMING -> INTERRUPTED (interrupt() called)
        INTERRUPTED -> IDLE    (interrupt cleanup completes)
        IDLE -> IDLE           (no-op: disconnect/interrupt when already idle)
    """

    IDLE = "idle"
    STREAMING = "streaming"
    INTERRUPTED = "interrupted"


class PermissionChoice(StrEnum):
    """Permission choice values returned from permission prompts."""

    ALLOW = "allow"
    ALLOW_ALL = "allow_all"
    ALLOW_SESSION = "allow_session"
    DENY = "deny"


class TodoStatus(StrEnum):
    """Todo item status values (from TodoWrite tool)."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
