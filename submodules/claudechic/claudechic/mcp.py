"""In-process MCP server for claudechic agent control.

Exposes tools for Claude to manage agents within claudechic:
- spawn_agent: Create new agent, optionally with initial prompt
- spawn_worktree: Create git worktree + agent
- ask_agent: Send question to existing agent (expects reply)
- tell_agent: Send message to existing agent (no reply expected)
- list_agents: List current agents and their status
- close_agent: Close an agent by name
- finish_worktree: Finish current agent's worktree (commit, rebase, merge, cleanup)
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import tool, create_sdk_mcp_server

from claudechic.analytics import capture
from claudechic.config import CONFIG
from claudechic.features.worktree.git import (
    FinishPhase,
    FinishState,
    ResolutionAction,
    clean_gitignored_files,
    determine_resolution_action,
    diagnose_worktree,
    fast_forward_merge,
    finish_cleanup,
    get_cleanup_fix_prompt,
    get_finish_info,
    get_finish_prompt,
    start_worktree,
)
from claudechic.tasks import create_safe_task

if TYPE_CHECKING:
    from claudechic.app import ChatApp

log = logging.getLogger(__name__)

# Global app reference, set by ChatApp.on_mount()
_app: ChatApp | None = None


def set_app(app: ChatApp) -> None:
    """Register the app instance for MCP tools to use."""
    global _app
    _app = app


def _text_response(text: str, *, is_error: bool = False) -> dict[str, Any]:
    """Format a text response for MCP."""
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result


def _error_response(text: str) -> dict[str, Any]:
    """Format an error response for MCP."""
    return _text_response(text, is_error=True)


def _find_agent_by_name(name: str):
    """Find an agent by name. Returns (agent, error_message)."""
    if _app is None or _app.agent_mgr is None:
        return None, "App not initialized"
    agent = _app.agent_mgr.find_by_name(name)
    if agent:
        return agent, None
    return None, f"Agent '{name}' not found. Use list_agents to see available agents."


def _track_mcp_tool(tool_name: str) -> None:
    """Track MCP tool usage for analytics."""
    if _app and _app.agent_mgr:
        active = _app.agent_mgr.active
        _app.run_worker(
            capture(
                "mcp_tool_used",
                tool=tool_name,
                agent_id=active.analytics_id if active else "unknown",
            )
        )


def _clear_pending_reply_if_matched(
    sender_name: str | None, recipient_name: str
) -> None:
    """Clear _pending_reply_to if the sender is replying to their caller.

    Called from tell_agent. If the sending agent has
    _pending_reply_to == recipient_name, it means the agent is delivering
    its required answer — clear the obligation.
    """
    if not sender_name or not _app or not _app.agent_mgr:
        return
    sender = _app.agent_mgr.find_by_name(sender_name)
    if sender and sender._pending_reply_to == recipient_name:
        sender._pending_reply_to = None
        sender._reply_nudge_count = 0
        log.debug(
            "Agent '%s' fulfilled reply obligation to '%s'", sender_name, recipient_name
        )


def _send_prompt_fire_and_forget(
    agent,
    prompt: str,
    *,
    caller_name: str | None = None,
    expect_reply: bool = False,
    is_spawn: bool = False,
) -> None:
    """Fire-and-forget prompt send that doesn't block MCP handlers.

    MCP handlers have implicit timeouts - awaiting SDK operations like
    agent.send() can cause "stream closed" errors. This function schedules
    the send as a background task and returns immediately.

    Args:
        agent: The agent to send to
        prompt: The message to send
        caller_name: If set, wraps prompt with sender info
        expect_reply: If True (with caller_name), adds reply instructions
        is_spawn: If True (with caller_name), uses "Spawned by" prefix
    """
    # Wrap prompt with caller info if provided
    if caller_name:
        if expect_reply:
            prompt = f"[Question from agent '{caller_name}' - please respond back using tell_agent, or ask_agent if you need more context]\n\n{prompt}"
        elif is_spawn:
            prompt = f"[Spawned by agent '{caller_name}']\n\n{prompt}"
        else:
            prompt = f"[Message from agent '{caller_name}']\n\n{prompt}"

    async def do_send():
        if agent.client is None:
            log.warning(f"Agent '{agent.name}' not connected, skipping prompt")
            return
        await agent.send(prompt)

    # Use monotonic_ns for unique task names (helps debugging concurrent sends)
    task_id = time.monotonic_ns()
    create_safe_task(do_send(), name=f"send-prompt-{agent.name}-{task_id}")


def _make_spawn_agent(caller_name: str | None = None):
    """Create spawn_agent tool with optional caller name bound."""

    @tool(
        "spawn_agent",
        "Create a new Claude agent in claudechic. The agent gets its own chat view and can work independently.",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "path": {"type": "string"},
                "prompt": {"type": "string"},
                "model": {"type": "string", "description": "Model to use (inherits caller's model if not specified)"},
                "type": {"type": "string", "description": "Agent type for guardrail env vars"},
                "requires_answer": {
                    "type": "boolean",
                    "description": "If true, the spawned agent is expected to reply back to the caller using tell_agent. It will be nudged if idle without replying.",
                },
            },
            "required": ["name", "path", "prompt"],
        },
    )
    async def spawn_agent(args: dict[str, Any]) -> dict[str, Any]:
        """Spawn a new agent, optionally with an initial prompt."""
        if _app is None or _app.agent_mgr is None:
            return _error_response("App not initialized")
        _track_mcp_tool("spawn_agent")

        name = args["name"]
        # Default to active agent's cwd (so agents inherit creator's directory)
        default_cwd = _app.agent_mgr.active.cwd if _app.agent_mgr.active else Path.cwd()
        path = Path(args.get("path", str(default_cwd))).resolve()
        prompt = args.get("prompt")
        agent_type = args.get("type")
        requires_answer = args.get("requires_answer", False)

        # Inherit caller's model if not explicitly specified
        caller_model = None
        if caller_name:
            caller_agent = _app.agent_mgr.find_by_name(caller_name)
            if caller_agent:
                caller_model = caller_agent.model
        model = args.get("model") or caller_model

        if not path.exists():
            return _error_response(f"Path '{path}' does not exist")

        # Check if agent with this name already exists (active or closed)
        if _app.agent_mgr.find_by_name(name):
            return _error_response(f"Agent '{name}' already exists")
        if _app.agent_mgr.find_closed_by_name(name):
            return _error_response(
                f"A closed agent named '{name}' exists. "
                f"Ask the user to run /agent reopen {name}"
            )

        try:
            # Create agent via AgentManager (handles SDK connection)
            agent = await _app.agent_mgr.create(
                name=name, cwd=path, switch_to=False, model=model,
                agent_type=agent_type,
            )
        except Exception as e:
            return _error_response(f"Error creating agent: {e}")

        # Track that this agent owes a reply to the caller
        if requires_answer and caller_name:
            agent._pending_reply_to = caller_name

        result = f"Created agent '{name}' in {path}"

        if prompt:
            _send_prompt_fire_and_forget(
                agent, prompt, caller_name=caller_name, is_spawn=True
            )
            result += f"\nQueued initial prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}"

        return _text_response(result)

    return spawn_agent


def _make_spawn_worktree(caller_name: str | None = None):
    """Create spawn_worktree tool with optional caller name bound."""

    @tool(
        "spawn_worktree",
        "Create a git worktree (feature branch) with a new agent. Useful for isolated feature development.",
        {"name": str, "base_branch": str, "prompt": str},
    )
    async def spawn_worktree(args: dict[str, Any]) -> dict[str, Any]:
        """Create a git worktree and spawn an agent in it."""
        if _app is None or _app.agent_mgr is None:
            return _error_response("App not initialized")
        _track_mcp_tool("spawn_worktree")

        name = args["name"]
        prompt = args.get("prompt")

        # Create the worktree
        success, message, wt_path = start_worktree(name)
        if not success or wt_path is None:
            return _error_response(f"Error creating worktree: {message}")

        try:
            # Create agent in the worktree via AgentManager
            agent = await _app.agent_mgr.create(
                name=name, cwd=wt_path, worktree=name, switch_to=False
            )
        except Exception as e:
            return _error_response(
                f"Worktree created at {wt_path}, but agent failed: {e}"
            )

        result = f"Created worktree '{name}' at {wt_path} with new agent"

        if prompt:
            _send_prompt_fire_and_forget(
                agent, prompt, caller_name=caller_name, is_spawn=True
            )
            result += f"\nQueued initial prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}"

        return _text_response(result)

    return spawn_worktree


def _make_ask_agent(caller_name: str | None = None):
    """Create ask_agent tool with optional caller name bound."""

    @tool(
        "ask_agent",
        "Send a question to another agent. Returns immediately - the agent will respond back using tell_agent (or ask_agent if they need more context) when ready.",
        {"name": str, "prompt": str},
    )
    async def ask_agent(args: dict[str, Any]) -> dict[str, Any]:
        """Send question to an agent. Non-blocking."""
        if _app is None or _app.agent_mgr is None:
            return _error_response("App not initialized")
        _track_mcp_tool("ask_agent")

        name = args["name"]
        prompt = args["prompt"]

        agent, error = _find_agent_by_name(name)
        if agent is None:
            return _error_response(error or "Agent not found")

        _send_prompt_fire_and_forget(
            agent, prompt, caller_name=caller_name, expect_reply=True
        )

        # NOTE: Do NOT clear _pending_reply_to here. ask_agent is a
        # follow-up question, not a final answer. The obligation is only
        # fulfilled when the agent uses tell_agent to deliver a result.

        return _text_response(
            f"Question queued for '{name}'. Delivery is asynchronous - the message may not arrive if the agent is disconnected."
        )

    return ask_agent


def _make_tell_agent(caller_name: str | None = None):
    """Create tell_agent tool with optional caller name bound."""

    @tool(
        "tell_agent",
        "Send a message to another agent without expecting a reply. Use for status updates, results, or answering questions.",
        {"name": str, "message": str},
    )
    async def tell_agent(args: dict[str, Any]) -> dict[str, Any]:
        """Send message to an agent. Non-blocking, no reply expected."""
        if _app is None or _app.agent_mgr is None:
            return _error_response("App not initialized")
        _track_mcp_tool("tell_agent")

        name = args["name"]
        message = args["message"]

        agent, error = _find_agent_by_name(name)
        if agent is None:
            return _error_response(error or "Agent not found")

        _send_prompt_fire_and_forget(agent, message, caller_name=caller_name)

        # Clear pending reply if this agent is replying to its caller
        _clear_pending_reply_if_matched(caller_name, name)

        return _text_response(f"Message queued for '{name}'. Delivery is asynchronous.")

    return tell_agent


def _make_whoami(caller_name: str | None = None):
    """Create whoami tool that returns this agent's name."""

    @tool(
        "whoami",
        "Returns the name of the current agent.",
        {},
    )
    async def whoami(args: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
        return _text_response(caller_name or "unknown")

    return whoami


@tool(
    "list_agents",
    "List all agents currently running in claudechic with their status and working directory.",
    {},
)
async def list_agents(args: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """List all agents and their status."""
    try:
        if _app is None or _app.agent_mgr is None:
            return _error_response("App not initialized")

        if len(_app.agent_mgr) == 0:
            return _text_response("No agents running")

        lines = ["Agents:"]
        for i, agent in enumerate(_app.agent_mgr, 1):
            active = "*" if agent.id == _app.agent_mgr.active_id else " "
            wt = " (worktree)" if agent.worktree else ""
            lines.append(
                f"{active}{i}. {agent.name} [{agent.status}] - {agent.cwd}{wt}"
            )

        return _text_response("\n".join(lines))
    except Exception as e:
        log.exception("list_agents failed")
        return _error_response(f"Failed to list agents: {e}")


@tool(
    "finish_worktree",
    "When you're done working in a worktree, call this to clean it up. Handles committing, rebasing onto the base branch, merging, and removing the worktree. Prefer this over manual git worktree commands.",
    {},
)
async def finish_worktree(args: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Start the worktree finish flow for the current agent."""
    try:
        if _app is None or _app.agent_mgr is None:
            return _error_response("App not initialized")
        _track_mcp_tool("finish_worktree")

        agent = _app.agent_mgr.active
        if agent is None:
            return _error_response("No active agent")

        if agent.worktree is None:
            return _error_response(
                "Current agent is not in a worktree. "
                "Use this tool only from a worktree agent."
            )

        # Get finish info
        success, message, info = get_finish_info(agent.cwd)
        if not success or info is None:
            return _error_response(message or "Failed to get finish info")

        # Diagnose current state
        status = diagnose_worktree(info)

        # Store state on agent for continuation after Claude actions
        agent.finish_state = FinishState(
            info=info,
            phase=FinishPhase.RESOLUTION,
            status=status,
        )

        # Process resolution actions, returning instructions for Claude
        return await _process_finish_resolution(agent, info, status)

    except Exception as e:
        log.exception("finish_worktree failed")
        return _error_response(str(e))


async def _process_finish_resolution(
    agent: Any, info: Any, status: Any
) -> dict[str, Any]:
    """Process the finish resolution phase, handling automatic actions.

    Returns MCP response - either success or instructions for Claude.
    """
    # Guard against infinite loops (e.g., gitignored files keep reappearing)
    max_iterations = 10

    for _ in range(max_iterations):
        action = determine_resolution_action(status)

        if action == ResolutionAction.NONE:
            return await _do_cleanup(agent, info)

        if action == ResolutionAction.CLEAN_GITIGNORED:
            success, error = clean_gitignored_files(info.worktree_dir)
            if not success:
                agent.finish_state = None
                return _error_response(f"Error cleaning gitignored files: {error}")
            # Re-diagnose and loop
            status = diagnose_worktree(info)
            agent.finish_state.status = status
            continue

        if action == ResolutionAction.PROMPT_UNCOMMITTED:
            return _text_response(
                "There are uncommitted changes. Please commit all changes with a "
                "descriptive message, then call finish_worktree again to continue."
            )

        if action == ResolutionAction.FAST_FORWARD:
            success, error = fast_forward_merge(info)
            if success:
                return await _do_cleanup(agent, info)
            # Fast-forward failed, fall through to rebase
            return _text_response(
                f"Fast-forward merge failed: {error}\n\n"
                + get_finish_prompt(info)
                + "\n\nAfter completing, call finish_worktree again."
            )

        if action == ResolutionAction.REBASE:
            return _text_response(
                get_finish_prompt(info)
                + "\n\nAfter completing the rebase and merge, call finish_worktree again."
            )

        # Unknown action
        agent.finish_state = None
        return _error_response("Unknown resolution action")

    # Max iterations reached
    agent.finish_state = None
    return _error_response("Too many resolution iterations, aborting")


async def _do_cleanup(agent: Any, info: Any) -> dict[str, Any]:
    """Attempt cleanup and return appropriate response."""

    success, warning = await asyncio.to_thread(finish_cleanup, info)
    if success:
        branch = info.branch_name
        agent.finish_state = None
        await _close_worktree_agent(agent)
        msg = f"Successfully finished worktree '{branch}'"
        if warning:
            msg += f" ({warning})"
        return _text_response(msg)

    # Cleanup failed - ask Claude to fix
    agent.finish_state.phase = FinishPhase.CLEANUP
    return _text_response(
        f"Cleanup failed: {warning}\n\n"
        + get_cleanup_fix_prompt(warning, info.worktree_dir)
        + "\n\nAfter fixing, call finish_worktree again to retry."
    )


async def _close_worktree_agent(agent: Any) -> None:
    """Close a worktree agent after successful finish."""
    if _app is None or _app.agent_mgr is None:
        return

    # Don't close if it's the last agent
    if len(_app.agent_mgr) <= 1:
        return

    # Switch to main agent first if this is the active one
    if _app.agent_mgr.active_id == agent.id:
        main = next(
            (a for a in _app.agent_mgr if a.worktree is None),
            None,
        )
        if main:
            _app.agent_mgr.switch(main.id)

    # Await directly to ensure agent is fully closed before returning
    await _app._close_agent_core(agent.id)


def _make_close_agent(caller_name: str | None = None):
    """Create close_agent tool with caller name bound for safety checks."""

    @tool(
        "close_agent",
        "Close an agent by name. Cannot close the last remaining agent or the calling agent.",
        {"name": str},
    )
    async def close_agent(args: dict[str, Any]) -> dict[str, Any]:
        """Close an agent."""
        try:
            if _app is None or _app.agent_mgr is None:
                return _error_response("App not initialized")

            name = args["name"]

            # Can't close yourself
            if caller_name and name == caller_name:
                return _error_response("An agent cannot close itself")

            # Can't close the last agent
            if len(_app.agent_mgr) <= 1:
                return _error_response("Cannot close the last agent")

            agent, error = _find_agent_by_name(name)
            if agent is None:
                return _error_response(error or "Agent not found")

            agent_id = agent.id
            agent_name = agent.name

            # Await the close directly so the agent count is accurate
            # before this tool returns (prevents race conditions with
            # rapid successive close calls).
            await _app._close_agent_core(agent_id)

            return _text_response(f"Closed agent '{agent_name}'")
        except Exception as e:
            agent_name = args.get("name", "unknown") if args else "unknown"
            log.exception(f"close_agent failed for '{agent_name}'")
            return _error_response(f"Failed to close agent '{agent_name}': {e}")

    return close_agent


def discover_mcp_tools(mcp_tools_dir: Path, **kwargs) -> list:
    """Walk mcp_tools/, import each eligible .py, call get_tools()."""
    tools = []
    if not mcp_tools_dir.is_dir():
        return tools

    # Pre-load helper modules (underscore-prefixed) so tool files can import them
    for py_file in sorted(mcp_tools_dir.glob("_*.py")):
        if py_file.name == "__init__.py":
            continue
        module_name = f"mcp_tools.{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
        except Exception:
            log.warning("mcp_tools: failed to load helper %s", py_file.name, exc_info=True)

    for py_file in sorted(mcp_tools_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        module_name = f"mcp_tools.{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                log.warning("mcp_tools: could not load spec for %s", py_file.name)
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            get_tools_fn = getattr(module, "get_tools", None)
            if get_tools_fn is None:
                log.debug("mcp_tools: %s has no get_tools(), skipping", py_file.name)
                continue

            file_tools = get_tools_fn(**kwargs)
            tools.extend(file_tools)
            log.info("mcp_tools: loaded %d tool(s) from %s", len(file_tools), py_file.name)

        except Exception:
            log.warning("mcp_tools: failed to load %s, skipping", py_file.name, exc_info=True)
            continue

    return tools


def create_chic_server(caller_name: str | None = None):
    """Create the chic MCP server with all tools.

    Args:
        caller_name: Name of the agent that will use this server.
            Used to identify the sender in spawn/ask/tell agent calls.
    """
    tools = [
        _make_spawn_agent(caller_name),
        _make_spawn_worktree(caller_name),
        _make_ask_agent(caller_name),
        _make_tell_agent(caller_name),
        _make_whoami(caller_name),
        list_agents,
        _make_close_agent(caller_name),
    ]

    # finish_worktree is experimental - enable with experimental.finish_worktree: true
    if CONFIG.get("experimental", {}).get("finish_worktree", False):
        tools.append(finish_worktree)

    # LSF cluster tools (always registered; LSF availability checked at runtime)
    try:
        from claudechic.cluster import (
            cluster_jobs,
            cluster_kill,
            cluster_status,
            cluster_submit,
            _make_cluster_watch,
        )

        tools.extend([
            cluster_jobs,
            cluster_status,
            cluster_submit,
            cluster_kill,
            _make_cluster_watch(
                caller_name=caller_name,
                send_notification=_send_prompt_fire_and_forget,
                find_agent=_find_agent_by_name,
            ),
        ])
    except ImportError:
        log.debug("Cluster tools not available (missing dependencies)")

    # Discover mcp_tools/ plugins
    mcp_tools_dir = Path.cwd() / "mcp_tools"
    discovered_tools = discover_mcp_tools(
        mcp_tools_dir,
        caller_name=caller_name,
        send_notification=_send_prompt_fire_and_forget,
        find_agent=_find_agent_by_name,
    )
    tools.extend(discovered_tools)

    return create_sdk_mcp_server(
        name="chic",
        version="1.0.0",
        tools=tools,
    )
