"""Built-in hint registry and trigger implementations.

This module defines:
- 6 project-state trigger classes (frozen dataclasses)
- 3 combinator triggers (AllOf, AnyOf, Not) for user extensibility
- COMMAND_LESSONS list for the learn-command rotating hint
- BUILTIN_HINTS registry (7 entries)
- get_hints() public API (extension point for users)

Users extend by editing this file or importing custom hints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ._state import ProjectState

from ._types import (  # noqa: TC001
    HintSpec,
    ShowEverySession,
    ShowOnce,
    ShowUntilResolved,
    TriggerCondition,
)


# ---------------------------------------------------------------------------
# Trigger implementations (frozen dataclasses satisfying TriggerCondition)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GitNotInitialized:
    """Hint: No .git directory detected."""

    def check(self, state: ProjectState) -> bool:
        return not state.path_exists(".git")

    @property
    def description(self) -> str:
        return "Project is not a git repository"


@dataclass(frozen=True)
class GuardrailsOnlyDefault:
    """Hint: Only the default R01 rule exists in guardrails."""

    rules_dir: str = ".claude/guardrails/rules.d"

    def check(self, state: ProjectState) -> bool:
        if not state.copier.use_guardrails:
            return False  # Feature disabled -- skip hint
        # Template ships with just the default rule (R01) in the base
        # rules.yaml. If rules.d/ has no user-added YAML files, user
        # hasn't customized guardrails.
        return state.count_files_matching(self.rules_dir, "*.yaml") == 0

    @property
    def description(self) -> str:
        return "Guardrails have only the default rule"


@dataclass(frozen=True)
class ProjectTeamNeverUsed:
    """Hint: /ao_project_team command has never been invoked."""

    ao_dir: str = ".ao_project_team"

    def check(self, state: ProjectState) -> bool:
        if not state.copier.use_project_team:
            return False  # Feature disabled -- skip hint
        return not state.path_exists(self.ao_dir)

    @property
    def description(self) -> str:
        return "Project team workflow has never been used"


@dataclass(frozen=True)
class PatternMinerUnderutilized:
    """Hint: Enough sessions exist but pattern miner has never run."""

    min_sessions: int = 10
    miner_state_file: str = ".patterns_mining_state.json"

    def check(self, state: ProjectState) -> bool:
        if not state.copier.use_pattern_miner:
            return False  # Feature disabled -- skip hint
        if state.session_count is None:
            return False  # Session count unavailable -- can't evaluate
        return (
            state.session_count >= self.min_sessions
            and not state.path_exists(self.miner_state_file)
        )

    @property
    def description(self) -> str:
        return f"Pattern miner never run despite {self.min_sessions}+ sessions"


@dataclass(frozen=True)
class McpToolsEmpty:
    """Hint: No user-created MCP tools in mcp_tools/."""

    tools_dir: str = "mcp_tools"

    def check(self, state: ProjectState) -> bool:
        # Count .py files excluding _-prefixed internal helpers
        return state.count_files_matching(self.tools_dir, "*.py") == 0

    @property
    def description(self) -> str:
        return "No user-created MCP tools found in mcp_tools/"


@dataclass(frozen=True)
class ClusterConfiguredUnused:
    """Hint: Cluster is configured but no jobs have been submitted."""

    def check(self, state: ProjectState) -> bool:
        if not state.copier.use_cluster:
            return False  # Feature disabled -- skip hint
        # Cluster enabled but no evidence of use (no job dirs or logs)
        return (
            not state.path_exists("cluster_jobs")
            and not state.path_exists("logs/cluster")
        )

    @property
    def description(self) -> str:
        return "Cluster backend is configured but appears unused"


# ---------------------------------------------------------------------------
# Learn-command trigger (dynamic, rotating)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandLesson:
    """A single command lesson -- name for tracking, message for display."""

    name: str
    message: str


COMMAND_LESSONS: list[CommandLesson] = [
    # Ordered by workflow value (canonical list, agreed with UIDesigner).
    # Commands covered by state hints (e.g., /ao_project_team) are excluded
    # to avoid redundancy -- the state hint is the right vehicle for those.
    CommandLesson("/diff", "Try /diff \u2014 see what changed since your last commit"),
    CommandLesson("/resume", "Try /resume \u2014 pick up a previous conversation where you left off"),
    CommandLesson("/worktree", "Try /worktree \u2014 work on a branch in isolation without stashing"),
    CommandLesson("/compact", "Try /compact \u2014 summarize the conversation to free up context"),
    CommandLesson("/model", "Try /model \u2014 switch between Claude models mid-conversation"),
    CommandLesson("/shell", "Try /shell \u2014 open a shell without leaving the TUI"),
]


@dataclass(frozen=True)
class LearnCommand:
    """Pick an untaught command and generate a hint for it.

    This is a DYNAMIC trigger -- it has a dynamic message that changes
    based on which command is selected. A ``_get_taught`` callable is
    injected at construction time (typically a closure over the
    ``HintStateStore``), keeping this trigger decoupled from state
    internals.
    """

    _get_taught: Callable[[], set[str]]

    def check(self, state: ProjectState) -> bool:
        return self._pick_command() is not None

    def get_message(self, state: ProjectState) -> str:
        """Dynamic message -- changes based on which command is picked."""
        cmd = self._pick_command()
        return cmd.message if cmd else ""

    def _pick_command(self) -> CommandLesson | None:
        """Pick the first untaught command from COMMAND_LESSONS."""
        taught = self._get_taught()
        for cmd in COMMAND_LESSONS:
            if cmd.name not in taught:
                return cmd
        return None  # All commands taught

    @property
    def description(self) -> str:
        return "Teach the user a new slash command"


# ---------------------------------------------------------------------------
# Combinator triggers (for user extensibility)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AllOf:
    """AND combinator -- all conditions must be true."""

    conditions: tuple[TriggerCondition, ...]

    def check(self, state: ProjectState) -> bool:
        return all(c.check(state) for c in self.conditions)

    @property
    def description(self) -> str:
        return " AND ".join(c.description for c in self.conditions)


@dataclass(frozen=True)
class AnyOf:
    """OR combinator -- at least one condition must be true."""

    conditions: tuple[TriggerCondition, ...]

    def check(self, state: ProjectState) -> bool:
        return any(c.check(state) for c in self.conditions)

    @property
    def description(self) -> str:
        return " OR ".join(c.description for c in self.conditions)


@dataclass(frozen=True)
class Not:
    """Negation -- inverts a condition."""

    condition: TriggerCondition

    def check(self, state: ProjectState) -> bool:
        return not self.condition.check(state)

    @property
    def description(self) -> str:
        return f"NOT ({self.condition.description})"


# ---------------------------------------------------------------------------
# Built-in hint registry
# ---------------------------------------------------------------------------

# Static hints -- these don't need any injected dependencies.
_STATIC_HINTS: list[HintSpec] = [
    HintSpec(
        id="git-setup",
        trigger=GitNotInitialized(),
        message="No git repo detected \u2014 spawn a Git agent to set one up",
        severity="warning",
        priority=1,
        lifecycle=ShowUntilResolved(),
    ),
    HintSpec(
        id="guardrails-default-only",
        trigger=GuardrailsOnlyDefault(),
        message=(
            "Your guardrails only have the default rule \u2014 "
            "add custom rules in .claude/guardrails/rules.yaml"
        ),
        severity="info",
        priority=2,
        lifecycle=ShowUntilResolved(),
    ),
    HintSpec(
        id="project-team-discovery",
        trigger=ProjectTeamNeverUsed(),
        message="Try /ao_project_team for multi-agent workflows",
        severity="info",
        priority=2,
        lifecycle=ShowOnce(),
    ),
    HintSpec(
        id="pattern-miner-ready",
        trigger=PatternMinerUnderutilized(min_sessions=10),
        message=(
            "You have 10+ sessions \u2014 "
            "run the Pattern Miner to find recurring corrections"
        ),
        severity="info",
        priority=3,
        lifecycle=ShowOnce(),
    ),
    HintSpec(
        id="mcp-tools-empty",
        trigger=McpToolsEmpty(),
        message="Drop Python files into mcp_tools/ for custom tools",
        severity="info",
        priority=3,
        lifecycle=ShowOnce(),
    ),
    HintSpec(
        id="cluster-ready",
        trigger=ClusterConfiguredUnused(),
        message="Your cluster backend is ready \u2014 try submitting a job",
        severity="info",
        priority=3,
        lifecycle=ShowOnce(),
    ),
]


def get_hints(
    *,
    get_taught_commands: Callable[[], set[str]] | None = None,
) -> list[HintSpec]:
    """Return the list of hint specs to evaluate.

    Args:
        get_taught_commands: Callable returning the set of command names
            already taught (injected by the engine from ``HintStateStore``).
            When ``None``, the learn-command hint is omitted.

    This is the extension point: users can append custom hints here
    or override this function entirely.  The engine calls ``get_hints()``
    to discover all registered hints.
    """
    hints = list(_STATIC_HINTS)

    if get_taught_commands is not None:
        trigger = LearnCommand(_get_taught=get_taught_commands)
        hints.append(
            HintSpec(
                id="learn-command",
                trigger=trigger,
                message=trigger.get_message,  # dynamic -- called with ProjectState
                severity="info",
                priority=4,
                lifecycle=ShowEverySession(),
            )
        )

    return hints
