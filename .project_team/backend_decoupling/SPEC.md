# Backend Decoupling Specification

**Project:** backend_decoupling
**Status:** Phase 1 Specification (Approved Approach A: pydantic-ai as engine)
**Date:** 2026-04-11
**Authors:** Composability, Skeptic, Terminology, Researcher, UserAlignment agents
**Amended:** 2026-04-11 — Fresh review findings incorporated (see Amendment Log)

---

## 1. Overview

### Goal

Decouple the claudechic workflow engine from the Claude Code API so it can run
on alternative AI backends. This extends claudechic's audience beyond Claude Code
users, making the workflow/phase/guardrails system available to anyone using
OpenAI, Gemini, Mistral, Ollama, or other LLM providers.

### Scope (Phase 1)

- Define an `AgentBackend` protocol that abstracts the LLM connection
- Extract the existing Claude Code SDK usage into a `ClaudeCodeBackend` adapter
- Implement a `PydanticAIBackend` adapter using pydantic-ai's `Agent.iter()` API
- Implement 7 core file/system tools for non-Claude-Code backends
- Bridge claudechic's orchestration tools (spawn_agent, tell_agent, etc.) to
  pydantic-ai's function-calling interface
- Integrate claudechic's guardrails with pydantic-ai's hook system
- Integrate interactive tool permissions with pydantic-ai's hook system

### Non-Goals (Phase 1)

- Session resume for pydantic-ai backend
- Context compaction (`/compact`) for pydantic-ai backend
- File checkpointing / `/rewind`
- Permission mode cycling (default/auto-edit/plan)
- Implementing all Claude Code tools (WebSearch, WebFetch, NotebookEdit, etc.)
- MCP server mode for Cursor/Cline integration
- Agent-to-Agent (A2A) protocol support

### Decision

**pydantic-ai (core, maintained by the Pydantic team) is the backend engine.**

- pydantic-ai v1.80.0+, released 2026-04-10, actively maintained
- Provides 15+ model providers: OpenAI, Anthropic, Gemini, Groq, Mistral,
  Ollama, Bedrock, Cohere, HuggingFace, OpenRouter, xAI, Cerebras, Outlines
- **NOT** using pydantic-ai-backend (vstorm-co community package) — we implement
  our own file tools to avoid dependency on a community-maintained project

**Implementation timing:** Wait 2-4 weeks after v1.80.0 release before starting
implementation, to allow early-adopter bug reports to surface. Add weekly CI job
running against latest pydantic-ai to detect breakage early.

### Backward Compatibility Guarantee

- `claude-code` remains the **default backend** when no `--backend` flag is set
- Zero behavior change for existing users
- The Claude Code path is an adapter wrapping the existing `ClaudeSDKClient`
  logic — same code, reorganized into `backends/claude_code.py`
- The `claude-agent-sdk` dependency remains; pydantic-ai is an optional extra

---

## 2. Architecture

### Host/Guest Relationship

**Claudechic is the host. pydantic-ai is the guest.**

Claudechic owns the TUI, workflow engine, guardrails, multi-agent orchestration,
and user experience. pydantic-ai is imported as a dependency underneath — it
provides the LLM-calling engine and tool execution loop for non-Claude-Code
backends. This is the same architectural position that `claude-agent-sdk`
occupies today.

Why not the reverse (claudechic as a pydantic-ai plugin):

- pydantic-ai's `Agent` owns the run loop; claudechic's `Agent` class owns
  connection lifecycle, message history, permission queue, observer pattern,
  and TUI integration — two different "Agent" concepts that would collide
- pydantic-ai's multi-agent model is synchronous delegation (agent-as-tool);
  claudechic's is concurrent autonomous agents with fire-and-forget messaging
- Claudechic's value (TUI + workflow + guardrails) would need to be rebuilt on
  pydantic-ai primitives for no gain

### Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    USER LAYER (claudechic)                   │
│  TUI · Workflow Engine · Guardrails · AgentManager · Widgets│
│  Observer pattern: on_text_chunk, on_tool_use, on_complete  │
└────────────────────────────┬────────────────────────────────┘
                             │ AgentBackend protocol
                             │ (BackendEvent iterator)
┌────────────────────────────┴────────────────────────────────┐
│                   INTEGRATION LAYER (new)                    │
│  AgentBackend protocol · BackendEvent types · Backend factory│
│  Tool bridge (MCP ↔ FunctionToolset) · Guardrails adapter   │
│  Permission bridge · Error normalization                     │
└──────────┬──────────────────────────────────┬───────────────┘
           │                                  │
┌──────────┴──────────┐          ┌────────────┴───────────────┐
│ ClaudeCodeBackend   │          │ PydanticAIBackend          │
│                     │          │                             │
│ claude-agent-sdk    │          │ pydantic-ai Agent.iter()   │
│ ClaudeSDKClient     │          │ FunctionToolset (file ops) │
│ CLI subprocess      │          │ Hooks (guardrails +        │
│ MCP server (chic)   │          │        permissions)        │
│                     │          │ Model abstraction (15+)    │
│ Tools: built into   │          │                             │
│ Claude Code CLI     │          │ Tools: implemented by      │
│                     │          │ claudechic locally         │
└─────────────────────┘          └─────────────────────────────┘
```

### How `Agent.iter()` Maps to the Observer Pattern

Today, `agent.py:_process_response` (line 750) iterates over SDK messages:

```python
await self.client.query(prompt)
async for msg in self.client.receive_response():
    # dispatch msg → observer callbacks
```

With the backend protocol, it iterates over `BackendEvent` objects:

```python
async for event in self.backend.send_and_stream(prompt):
    if isinstance(event, TextChunkEvent):       → observer.on_text_chunk()
    elif isinstance(event, ToolUseEvent):       → observer.on_tool_use()
    elif isinstance(event, ToolResultEvent):    → observer.on_tool_result()
    elif isinstance(event, PermissionRequestEvent): → observer.on_prompt_added()
    elif isinstance(event, ErrorEvent):         → observer.on_error()
    elif isinstance(event, CompleteEvent):      → observer.on_complete()
```

Inside `PydanticAIBackend.send_and_stream()`, pydantic-ai's `Agent.iter()` runs
node-by-node, translating each node into `BackendEvent` objects:

```
ModelRequestNode  →  stream PartDeltaEvents  →  yield TextChunkEvent
                     stream PartStartEvents  →  accumulate tool args
                     PartStartEvent complete →  yield ToolUseEvent (with full input)
CallToolsNode     →  before_tool_execute     →  yield PermissionRequestEvent (if needed)
                     after execution         →  yield ToolResultEvent
End               →                          →  yield CompleteEvent
```

The existing observer callbacks (`AgentObserver` protocol in `protocols.py`) are
**completely unchanged**. `ChatView` receives the same events regardless of
backend.

---

## 3. New Files & Modifications

### New Files

| File | Purpose | Est. LOC |
|------|---------|----------|
| `claudechic/backends/__init__.py` | Exports protocol, factory, event types | ~30 |
| `claudechic/backends/protocol.py` | `AgentBackend` Protocol + `BackendEvent` dataclasses | ~120 |
| `claudechic/backends/claude_code.py` | Wraps `ClaudeSDKClient` — extracted from `agent.py` | ~200 |
| `claudechic/backends/pydantic_ai_backend.py` | Wraps `pydantic_ai.Agent.iter()` | ~350 |
| `claudechic/backends/tools/__init__.py` | Tool registry exports | ~10 |
| `claudechic/backends/tools/filesystem.py` | Read, Write, Edit, Glob, Grep implementations | ~300 |
| `claudechic/backends/tools/shell.py` | Bash, Ls implementations | ~100 |
| `claudechic/backends/tools/chic_toolset.py` | Orchestration tools as `FunctionToolset` | ~150 |
| `claudechic/backends/tools/mcp_impl.py` | Shared implementation functions for MCP/toolset | ~200 |
| `tests/test_backends.py` | Unit tests: protocol, tools, integration | ~250 |
| `tests/test_backend_security.py` | Security tests: path traversal, bash injection, OOM | ~150 |
| `tests/test_backend_characterization.py` | Characterization tests for ClaudeCodeBackend | ~100 |
| **Total new code** | | **~1960** |

### Modified Files

| File | Changes | Est. Lines Changed |
|------|---------|-------------------|
| `agent.py` | Replace `ClaudeSDKClient` with `AgentBackend`; refactor `connect()`, `disconnect()`, `_process_response()`, `interrupt()`; move drain logic to backend | ~150 |
| `agent_manager.py` | Replace `ClaudeAgentOptions` with backend factory; update `create()`, `connect_agent()` | ~40 |
| `app.py` | Add `--backend` handling; `_make_options()` becomes `_make_backend()`; add config loading | ~60 |
| `mcp.py` | Extract tool impl functions into `mcp_impl.py`; keep MCP `@tool` wrappers calling shared impls | ~60 |
| `guardrails/hooks.py` | Add pydantic-ai hook adapter alongside existing `HookMatcher` path | ~30 |
| `protocols.py` | Replace `ResultMessage`/`SystemMessage` TYPE_CHECKING imports with canonical types | ~15 |
| `messages.py` | Replace SDK type imports with canonical `ToolUseData`/`ToolResultData` types; update all Message classes | ~30 |
| `widgets/content/tools.py` | Replace runtime `ToolUseBlock`/`ToolResultBlock` imports with canonical types | ~20 |
| `widgets/base/tool_protocol.py` | Replace `ToolResultBlock` in protocol signature | ~5 |
| `widgets/layout/chat_view.py` | Replace `ToolUseBlock` construction (L293, L351) with canonical types | ~15 |
| `workflows/agent_folders.py` | Note: imports `HookMatcher` — coupling level LIGHT not NONE | ~0 |
| `enums.py` | No change (tool names are strings, backend-agnostic) | 0 |
| `pyproject.toml` | Add `[project.optional-dependencies]` for pydantic-ai | ~5 |
| `tests/test_agent_permission.py` | Update SDK imports to canonical types | ~10 |
| `tests/test_app_ui.py` | Update SDK imports to canonical types | ~10 |
| `tests/test_widgets.py` | Update SDK imports to canonical types | ~10 |
| **Total modified** | | **~460** |

### Specific Function-Level Changes

**`agent.py`:**

| Function | Line | Change |
|----------|------|--------|
| Top-level imports | 20-39 | Remove `from claude_agent_sdk import ...`; add `from claudechic.backends.protocol import AgentBackend, ...` |
| `Agent.__init__` | 194 | `self.client: ClaudeSDKClient` → `self.backend: AgentBackend` |
| `Agent.connect()` | 287-319 | Accept `AgentBackend` instead of `ClaudeAgentOptions`; remove PID capture |
| `Agent.disconnect()` | 321-338 | `self.client.disconnect()` → `self.backend.disconnect()` |
| `Agent.interrupt()` | 536-601 | `self.client.interrupt()` → `self.backend.interrupt()`; remove `_sigint_fallback()` |
| `Agent._is_transport_alive()` | 650-665 | → `self.backend.is_alive()` |
| `Agent._process_response()` | 750-855 | Replace SDK message iteration with `BackendEvent` iteration; add `ErrorEvent` + `PermissionRequestEvent` handling |
| `Agent._handle_sdk_message()` | 939-1001 | Remove (logic moves into backend adapters) |
| `Agent._receive_with_watchdog()` | 895-937 | Remove (liveness check moves into backend) |
| `Agent._drain_stale_on_next_response` | 772-787 | Move into `ClaudeCodeBackend` (SDK-specific behavior) |

**`agent_manager.py`:**

| Function | Line | Change |
|----------|------|--------|
| `__init__` | 32-34 | `options_factory: Callable[..., ClaudeAgentOptions]` → `backend_factory: Callable[..., AgentBackend]` |
| `create()` | 120-171 | `self._options_factory(...)` → `self._backend_factory(...)` |
| `connect_agent()` | 173-193 | Same pattern — use factory |

**`app.py`:**

| Function | Line | Change |
|----------|------|--------|
| `_make_options()` | 719-768 | Rename to `_make_backend()`; branch on `self.backend_type` |
| `on_mount()` | 770+ | Pass `_make_backend` as factory to `AgentManager` |
| CLI arg parsing | `__main__.py` | Add `--backend` flag |

**`messages.py`:**

| Class | Change |
|-------|--------|
| `ResponseComplete` | `result: ResultMessage` → `result: CompleteEvent` |
| `ToolUseMessage` | `block: ToolUseBlock` → `block: ToolUseData` (new canonical dataclass) |
| `ToolResultMessage` | `block: ToolResultBlock` → `block: ToolResultData` (new canonical dataclass) |
| `SDKSystemMessage` (import) | → `SystemEvent` from protocol |

**Widget files:**

| File | Change |
|------|--------|
| `widgets/content/tools.py` | Replace `ToolUseBlock` / `ToolResultBlock` with `ToolUseData` / `ToolResultData` |
| `widgets/base/tool_protocol.py` | Replace `ToolResultBlock` in `ToolWidget.update_result()` signature |
| `widgets/layout/chat_view.py` | Replace `ToolUseBlock(...)` construction at L293, L351 with `ToolUseData(...)` |

---

## 4. AgentBackend Protocol

### Protocol Definition

```python
# claudechic/backends/protocol.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Protocol


# ---------------------------------------------------------------------------
# BackendEvent types
# ---------------------------------------------------------------------------

@dataclass
class TextChunkEvent:
    """Streaming text from the LLM."""
    text: str
    new_message: bool = False
    parent_tool_use_id: str | None = None


@dataclass
class ToolUseEvent:
    """LLM is requesting a tool call."""
    id: str
    name: str
    input: dict[str, Any]
    parent_tool_use_id: str | None = None


@dataclass
class ToolResultEvent:
    """Result from a tool execution."""
    tool_use_id: str
    output: str
    is_error: bool = False


@dataclass
class PermissionRequestEvent:
    """Backend is requesting user approval for a tool call.

    Emitted by pydantic-ai backend when a tool call needs interactive
    approval. The backend pauses execution and waits for approval/denial
    via the approval_event before continuing.

    For Claude Code backend, permissions are handled internally by the
    SDK's can_use_tool callback and this event is never emitted.
    """
    tool_use_id: str
    tool_name: str
    tool_input: dict[str, Any]
    approval_event: asyncio.Event  # Set by UI when user responds
    approved: bool = False         # Set by UI before setting approval_event


@dataclass
class ErrorEvent:
    """Backend error that may be recoverable.

    Emitted for API errors, rate limits, network issues, etc.
    The agent layer decides whether to retry, notify user, or abort.
    """
    code: str                      # Machine-readable: "auth", "rate_limit", "timeout",
                                   # "network", "empty_response", "context_overflow",
                                   # "unsupported_model", "tool_error", "unknown"
    message: str                   # Human-readable description
    recoverable: bool = True       # Whether retry might succeed
    retry_after_ms: int | None = None  # Suggested retry delay (e.g., 429 Retry-After)


@dataclass
class CompleteEvent:
    """LLM response is complete."""
    session_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    cost_usd: float | None = None
    model: str | None = None


@dataclass
class SystemEvent:
    """Backend system message (informational)."""
    subtype: str
    data: dict[str, Any] = field(default_factory=dict)


BackendEvent = (
    TextChunkEvent | ToolUseEvent | ToolResultEvent | PermissionRequestEvent
    | ErrorEvent | CompleteEvent | SystemEvent
)


# ---------------------------------------------------------------------------
# Canonical tool data types (replacing SDK ToolUseBlock/ToolResultBlock)
# ---------------------------------------------------------------------------

@dataclass
class ToolUseData:
    """Backend-agnostic tool use representation.

    Replaces claude_agent_sdk.ToolUseBlock in all widget and message code.
    Both ClaudeCodeBackend and PydanticAIBackend produce these.
    """
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolResultData:
    """Backend-agnostic tool result representation.

    Replaces claude_agent_sdk.ToolResultBlock in all widget and message code.
    """
    tool_use_id: str
    output: str
    is_error: bool = False


# ---------------------------------------------------------------------------
# Backend configuration
# ---------------------------------------------------------------------------

@dataclass
class BackendConfig:
    """Common configuration for all backends."""
    cwd: Path
    model: str | None = None
    agent_name: str | None = None
    agent_type: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    resume_id: str | None = None


# ---------------------------------------------------------------------------
# AgentBackend protocol
# ---------------------------------------------------------------------------

class AgentBackend(Protocol):
    """Protocol for LLM backend adapters.

    Each claudechic Agent owns one AgentBackend instance. The backend
    handles LLM communication, tool execution (if applicable), and
    streaming events back to the agent via an async iterator.
    """

    async def connect(self) -> None:
        """Establish connection to the backend.

        For Claude Code: spawns CLI subprocess via ClaudeSDKClient.
        For pydantic-ai: validates model is reachable (quick ping).
        """
        ...

    async def disconnect(self) -> None:
        """Gracefully shut down the backend connection."""
        ...

    async def send_and_stream(
        self,
        prompt: str,
        *,
        images: list[bytes] | None = None,
    ) -> AsyncIterator[BackendEvent]:
        """Send a prompt and stream events back.

        This is the core agentic loop. For Claude Code, this wraps
        client.query() + client.receive_response(). For pydantic-ai,
        this wraps Agent.iter() with node-by-node streaming.

        The iterator yields events until the LLM response is complete.
        The final event should be a CompleteEvent.

        Args:
            prompt: The user message text.
            images: Optional list of image bytes (PNG/JPEG). Supported by
                    ClaudeCodeBackend (existing functionality). PydanticAIBackend
                    ignores this in Phase 1 (raises NotImplementedError if provided).
        """
        ...

    async def interrupt(self) -> None:
        """Interrupt the current response.

        For Claude Code: calls client.interrupt() + SIGINT fallback.
        For pydantic-ai: cancels the iter() async context.
        """
        ...

    def is_alive(self) -> bool:
        """Check whether the backend is still connected.

        For Claude Code: checks CLI subprocess PID.
        For pydantic-ai: always True (stateless HTTP).
        """
        ...

    @property
    def session_id(self) -> str | None:
        """Current session ID, if the backend supports session persistence."""
        ...

    @property
    def supports_resume(self) -> bool:
        """Whether the backend supports session resume."""
        ...

    @property
    def supports_permission_modes(self) -> bool:
        """Whether the backend supports permission mode cycling."""
        ...
```

### Error Handling Behavior

The `ErrorEvent` enables consistent error handling across backends:

| Error Scenario | `code` | `recoverable` | Agent Behavior |
|---|---|---|---|
| Bad API key / auth failure | `"auth"` | `False` | Show error, prompt user to fix config |
| Rate limit (429) | `"rate_limit"` | `True` | Auto-retry after `retry_after_ms`; show toast |
| Network timeout | `"timeout"` | `True` | Retry once; if repeated, notify user |
| Empty LLM response | `"empty_response"` | `True` | Retry with "Please provide a response" |
| Model doesn't support function calling | `"unsupported_model"` | `False` | Show error: "Model X doesn't support tool use. Choose a different model." |
| Context window exceeded | `"context_overflow"` | `False` | Show error: "Context window full. Start a new agent or use /compact (Claude Code only)." |
| Model not found | `"unsupported_model"` | `False` | Show error with list of available models |

For `ClaudeCodeBackend`, SDK exceptions are caught and translated to `ErrorEvent`:
- `CLIConnectionError` → `ErrorEvent(code="network", ...)`
- `CLIJSONDecodeError` → `ErrorEvent(code="tool_error", ..., recoverable=True)`

### ClaudeCodeBackend Implementation

Wraps the existing `ClaudeSDKClient` logic extracted from `agent.py`:

**WARNING:** This extraction accesses private SDK attributes
(`client._query.transport._process.pid` in `_is_transport_alive`, and
`client._transport.write()` for image messages). These are fragile coupling
points. Write characterization tests BEFORE refactoring to catch any breakage.

```python
# claudechic/backends/claude_code.py

class ClaudeCodeBackend:
    """Backend adapter for Claude Code CLI via claude-agent-sdk."""

    def __init__(self, options: ClaudeAgentOptions):
        self._options = options
        self._client: ClaudeSDKClient | None = None
        self._claude_pid: int | None = None
        self._session_id: str | None = None
        self._drain_stale_on_next: bool = False  # SDK-specific stale message drain

    async def connect(self) -> None:
        self._client = ClaudeSDKClient(self._options)
        await self._client.connect()
        self._claude_pid = get_claude_pid_from_client(self._client)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.disconnect()
            self._client = None
        self._claude_pid = None

    async def send_and_stream(
        self,
        prompt: str,
        *,
        images: list[bytes] | None = None,
    ) -> AsyncIterator[BackendEvent]:
        # Handle image attachments (existing agent.py:757-764 logic)
        if images:
            message = self._build_message_with_images(prompt, images)
            await self._client._transport.write(json.dumps(message) + "\n")
        else:
            await self._client.query(prompt)

        # Drain stale messages from previous interrupted response
        # (SDK-specific behavior — see agent.py:772-787)
        if self._drain_stale_on_next:
            self._drain_stale_on_next = False
            async for msg in self._client.receive_response():
                if isinstance(msg, (AssistantMessage, StreamEvent)):
                    yield from self._translate_message(msg)
                    break
                # Stale message from interrupted response — skip
            else:
                pass  # Iterator exhausted, fresh response next

        async for msg in self._client.receive_response():
            # Translate SDK messages → BackendEvent
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolUseBlock):
                        yield ToolUseEvent(id=block.id, name=block.name,
                                           input=block.input)
                    elif isinstance(block, ToolResultBlock):
                        yield ToolResultEvent(tool_use_id=block.tool_use_id,
                                              output=block.output or "",
                                              is_error=block.is_error)
            elif isinstance(msg, StreamEvent):
                # Extract text deltas
                yield TextChunkEvent(text=delta_text)
            elif isinstance(msg, ResultMessage):
                self._session_id = msg.session_id
                yield CompleteEvent(session_id=msg.session_id,
                                    input_tokens=msg.input_tokens,
                                    output_tokens=msg.output_tokens,
                                    model=msg.model)

    async def interrupt(self) -> None:
        # Existing interrupt + SIGINT fallback logic from agent.py:536-641
        if self._client:
            try:
                await asyncio.wait_for(self._client.interrupt(), timeout=5.0)
            except asyncio.TimeoutError:
                self._sigint_fallback()
            except Exception:
                pass
        self._drain_stale_on_next = True

    def _sigint_fallback(self) -> None:
        """Send SIGINT directly to CLI subprocess (last-resort interrupt).

        WARNING: Accesses private SDK attributes. See R8 risk entry.
        """
        import signal, os
        try:
            client = self._client
            if not client:
                return
            query = getattr(client, "_query", None)
            transport = getattr(query, "transport", None) if query else None
            process = getattr(transport, "_process", None) if transport else None
            if process and process.pid and process.returncode is None:
                os.kill(process.pid, signal.SIGINT)
        except (ProcessLookupError, OSError):
            pass

    def is_alive(self) -> bool:
        # Existing _is_transport_alive logic from agent.py:650-665
        # WARNING: Accesses private SDK attributes. See R8 risk entry.
        try:
            client = self._client
            if not client:
                return False
            query = getattr(client, "_query", None)
            transport = getattr(query, "transport", None) if query else None
            process = getattr(transport, "_process", None) if transport else None
            return bool(process and process.pid and process.returncode is None)
        except Exception:
            return False

    @property
    def supports_resume(self) -> bool:
        return True

    @property
    def supports_permission_modes(self) -> bool:
        return True
```

### PydanticAIBackend Implementation

```python
# claudechic/backends/pydantic_ai_backend.py

import json
from pydantic_ai import Agent as PaiAgent
from pydantic_ai.hooks import Hooks, SkipToolExecution
from pydantic_ai.agent import PartDeltaEvent, PartStartEvent

class PydanticAIBackend:
    """Backend adapter using pydantic-ai Agent.iter()."""

    def __init__(
        self,
        model: str,                           # e.g. "openai:gpt-4o"
        cwd: Path,
        toolsets: list,                        # FunctionToolsets
        hooks: Hooks,                          # guardrails + permissions
        agent_name: str | None = None,
        system_prompt: str | None = None,      # includes available tools list
    ):
        self._model = model
        self._cwd = cwd
        self._messages: list = []              # conversation history
        self._cancel_event = asyncio.Event()
        self._current_run = None
        self._tool_result_queue: asyncio.Queue[ToolResultEvent] = asyncio.Queue()

        self._pai_agent = PaiAgent(
            model,
            toolsets=toolsets,
            hooks=hooks,
            system_prompt=system_prompt or self._default_system_prompt(),
        )

    def _default_system_prompt(self) -> str:
        """System prompt explicitly listing available/unavailable tools."""
        return (
            "You have access to these tools: Read, Write, Edit, Glob, Grep, "
            "Bash, Ls, spawn_agent, tell_agent, ask_agent, close_agent, "
            "list_agents, advance_phase, get_phase, acknowledge_warning, "
            "request_override, whoami.\n\n"
            "The following tools are NOT available in this backend and you "
            "must NOT attempt to call them: WebSearch, WebFetch, "
            "NotebookEdit, TodoWrite, AskUserQuestion. "
            "Use Bash + curl for web requests. "
            "Edit notebooks manually or via Bash."
        )

    async def connect(self) -> None:
        # Validate model is reachable (optional quick check)
        pass

    async def disconnect(self) -> None:
        self._messages.clear()

    async def send_and_stream(
        self,
        prompt: str,
        *,
        images: list[bytes] | None = None,
    ) -> AsyncIterator[BackendEvent]:
        if images:
            # Phase 1: image support not implemented for pydantic-ai
            yield ErrorEvent(
                code="unsupported_feature",
                message="Image input not supported on pydantic-ai backend (Phase 1). "
                        "Use Claude Code backend for image tasks.",
                recoverable=False,
            )
            return

        self._cancel_event.clear()

        try:
            async with self._pai_agent.iter(
                prompt,
                message_history=self._messages,
            ) as agent_run:
                self._current_run = agent_run

                async for node in agent_run:
                    if self._cancel_event.is_set():
                        break

                    # ModelRequestNode: LLM is generating
                    if PaiAgent.is_model_request_node(node):
                        async with node.stream(agent_run.ctx) as stream:
                            # Tool argument accumulator
                            # PartStartEvent fires when a new tool call begins.
                            # PartDeltaEvents carry incremental args_delta JSON.
                            # We accumulate args and emit ToolUseEvent only when
                            # the tool call part is complete (next PartStart or
                            # stream ends).
                            pending_tool: dict | None = None
                            pending_args_json: str = ""

                            async for event in stream:
                                if isinstance(event, PartStartEvent):
                                    # Flush previous pending tool if any
                                    if pending_tool is not None:
                                        try:
                                            parsed_args = json.loads(pending_args_json) if pending_args_json else {}
                                        except json.JSONDecodeError:
                                            parsed_args = {"_raw": pending_args_json}
                                        yield ToolUseEvent(
                                            id=pending_tool["id"],
                                            name=pending_tool["name"],
                                            input=parsed_args,
                                        )
                                        pending_tool = None
                                        pending_args_json = ""

                                    # New part starting
                                    if hasattr(event.part, 'tool_name'):
                                        # Start accumulating a new tool call
                                        pending_tool = {
                                            "id": event.part.tool_call_id,
                                            "name": event.part.tool_name,
                                        }
                                        pending_args_json = ""
                                    # else: text part — no accumulation needed

                                elif isinstance(event, PartDeltaEvent):
                                    if pending_tool is not None:
                                        # Accumulate tool argument deltas
                                        if hasattr(event.delta, 'args_delta'):
                                            pending_args_json += event.delta.args_delta
                                    elif hasattr(event.delta, 'content_delta'):
                                        if event.delta.content_delta:
                                            yield TextChunkEvent(
                                                text=event.delta.content_delta
                                            )

                            # Flush final pending tool at end of stream
                            if pending_tool is not None:
                                try:
                                    parsed_args = json.loads(pending_args_json) if pending_args_json else {}
                                except json.JSONDecodeError:
                                    parsed_args = {"_raw": pending_args_json}
                                yield ToolUseEvent(
                                    id=pending_tool["id"],
                                    name=pending_tool["name"],
                                    input=parsed_args,
                                )

                    # CallToolsNode: tool results available
                    elif PaiAgent.is_call_tools_node(node):
                        # Drain tool results from the node directly.
                        # pydantic-ai stores results on the node after execution.
                        # Also drain any results pushed via the hook queue
                        # (for permission-gated tools).
                        for part in node.data.parts:
                            if hasattr(part, 'tool_name'):
                                yield ToolResultEvent(
                                    tool_use_id=part.tool_call_id,
                                    output=str(part.content) if hasattr(part, 'content') else "",
                                    is_error=False,
                                )
                        # Also drain any queued results from hooks
                        while not self._tool_result_queue.empty():
                            yield self._tool_result_queue.get_nowait()

                # Run complete
                if agent_run.result:
                    self._messages = agent_run.result.all_messages()
                    usage = agent_run.usage()
                    yield CompleteEvent(
                        input_tokens=usage.request_tokens,
                        output_tokens=usage.response_tokens,
                        model=self._model,
                    )

        except Exception as e:
            # Translate pydantic-ai exceptions to ErrorEvents
            error_event = self._translate_exception(e)
            yield error_event
            if not error_event.recoverable:
                return

    def _translate_exception(self, e: Exception) -> ErrorEvent:
        """Map pydantic-ai / HTTP exceptions to ErrorEvent."""
        error_str = str(e).lower()
        error_type = type(e).__name__

        if "401" in error_str or "unauthorized" in error_str or "api key" in error_str:
            return ErrorEvent(code="auth", message=f"Authentication failed: {e}", recoverable=False)
        elif "429" in error_str or "rate limit" in error_str:
            return ErrorEvent(code="rate_limit", message=f"Rate limited: {e}", recoverable=True, retry_after_ms=60000)
        elif "timeout" in error_str or "TimeoutError" in error_type:
            return ErrorEvent(code="timeout", message=f"Request timed out: {e}", recoverable=True)
        elif "context" in error_str and ("length" in error_str or "window" in error_str or "token" in error_str):
            return ErrorEvent(code="context_overflow", message=f"Context window exceeded: {e}", recoverable=False)
        elif "connection" in error_str or "network" in error_str:
            return ErrorEvent(code="network", message=f"Network error: {e}", recoverable=True)
        else:
            return ErrorEvent(code="unknown", message=f"Backend error: {e}", recoverable=False)

    async def interrupt(self) -> None:
        self._cancel_event.set()

    def is_alive(self) -> bool:
        return True  # HTTP-based, no subprocess

    @property
    def session_id(self) -> str | None:
        return None  # Phase 1: no session persistence

    @property
    def supports_resume(self) -> bool:
        return False

    @property
    def supports_permission_modes(self) -> bool:
        return False
```

---

## 5. Tool Implementations

For non-Claude-Code backends, claudechic must provide its own tool
implementations. Claude Code's built-in tools (Read, Write, Edit, Bash, Glob,
Grep) are provided by the CLI subprocess and are not available via pydantic-ai.

### Tool List

| Tool | Description | Est. LOC | Security Notes |
|------|-------------|----------|----------------|
| `Read` | Read file with line numbers (cat -n format) | ~40 | Path traversal check; configurable line limit (default 2000); **file size check (10MB cap)** |
| `Write` | Write/overwrite file | ~25 | Path traversal check; parent directory must exist |
| `Edit` | String replacement in file | ~45 | Unique match validation; `replace_all` flag support; file size check |
| `Glob` | File pattern matching | ~25 | Rooted to cwd; sorted by mtime |
| `Grep` | Regex content search (via ripgrep or stdlib) | ~45 | Output truncation at 30K chars; timeout for large repos |
| `Bash` | Shell command execution | ~60 | Configurable timeout (default 120s); **output truncation at 30K chars**; subprocess resource limits |
| `Ls` | List directory contents | ~20 | Rooted to cwd |
| **Total** | | **~260** | |

### Registration as FunctionToolset

```python
# claudechic/backends/tools/filesystem.py

from pydantic_ai.toolsets import FunctionToolset

# Maximum file size for Read/Edit operations (prevent OOM on large files)
_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB

# Maximum tool output length (prevent token explosion)
_MAX_OUTPUT_CHARS = 30_000  # ~30K chars ≈ ~7.5K tokens

def _resolve_and_check(cwd: Path, file_path: str) -> Path:
    """Resolve path and enforce cwd jail."""
    path = (cwd / file_path).resolve()
    if not path.is_relative_to(cwd.resolve()):
        raise ToolError(f"Path escapes working directory: {file_path}")
    return path

def _check_file_size(path: Path) -> None:
    """Reject files over the size limit to prevent OOM."""
    try:
        size = path.stat().st_size
    except OSError:
        return  # File doesn't exist yet; let the caller handle it
    if size > _MAX_FILE_SIZE_BYTES:
        raise ToolError(
            f"File too large ({size / 1024 / 1024:.1f}MB > "
            f"{_MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f}MB limit). "
            f"Use offset/limit parameters or Bash to read portions."
        )

def _truncate_output(text: str) -> str:
    """Truncate output to prevent token explosion."""
    if len(text) > _MAX_OUTPUT_CHARS:
        return text[:_MAX_OUTPUT_CHARS] + f"\n\n... (truncated, {len(text)} total chars)"
    return text

def create_file_toolset(cwd: Path) -> FunctionToolset:
    """Create toolset with file operation tools rooted at cwd."""
    ts = FunctionToolset()

    @ts.tool_plain
    async def Read(file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """Read a file from the filesystem. Returns numbered lines."""
        path = _resolve_and_check(cwd, file_path)
        _check_file_size(path)
        content = await asyncio.to_thread(
            path.read_text, encoding="utf-8", errors="replace"
        )
        lines = content.splitlines()
        selected = lines[offset:offset + limit]
        result = "\n".join(f"{i + offset + 1}\t{line}" for i, line in enumerate(selected))
        return _truncate_output(result)

    @ts.tool_plain
    async def Edit(file_path: str, old_string: str, new_string: str,
                   replace_all: bool = False) -> str:
        """Replace text in a file. old_string must be unique unless replace_all=True."""
        path = _resolve_and_check(cwd, file_path)
        _check_file_size(path)
        content = await asyncio.to_thread(path.read_text)
        count = content.count(old_string)
        if count == 0:
            raise ToolError(f"old_string not found in {file_path}")
        if count > 1 and not replace_all:
            raise ToolError(f"old_string matches {count} times (not unique)")
        result = content.replace(old_string, new_string, -1 if replace_all else 1)
        await asyncio.to_thread(path.write_text, result)
        return f"Edited {file_path}"

    @ts.tool_plain
    async def Write(file_path: str, content: str) -> str:
        """Write content to a file, overwriting if it exists."""
        path = _resolve_and_check(cwd, file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_text, content)
        return f"Wrote {file_path}"

    # ... Glob, Grep, Bash, Ls similarly

    return ts
```

### Security Considerations

- **Path traversal**: All paths resolved against `cwd`; refuse paths that
  resolve outside cwd (e.g., `../../etc/passwd`). Use `Path.resolve()` and
  check `path.is_relative_to(cwd)`.
- **File size limits**: Read and Edit check file size before loading into memory.
  Files over 10MB are rejected with instructions to use `offset`/`limit` or Bash.
  This prevents OOM conditions on large binary files or logs.
- **Output truncation**: Tool outputs capped at 30K characters (~7.5K tokens) to
  avoid context window explosion. 30K is chosen to stay well under pydantic-ai's
  default tool output limits while being large enough for most tool results.
  Large files should use `offset`/`limit` parameters.
- **Bash timeouts**: Default 120 seconds, configurable. Subprocess killed on
  timeout. Use `asyncio.create_subprocess_shell` with `communicate(timeout=)`.
  Bash output also truncated at 30K chars.
- **Bash security**: Guardrails rules apply before tool execution (see Section 7).
  Dangerous commands (rm -rf, git push --force, etc.) are caught by the same
  rules that protect Claude Code usage today. Semantic command filtering via
  guardrails is the **primary gate**; tool-level restrictions are defense-in-depth
  only.
- **Encoding**: All file reads use `utf-8` with `errors="replace"` to handle
  binary files gracefully.
- **NFS considerations**: This project runs on HPC cluster with NFS-mounted
  filesystems. File I/O is wrapped in `asyncio.to_thread()` to avoid blocking
  the event loop on NFS latency spikes. Avoid `os.stat()` in hot paths; prefer
  catching `OSError` over pre-checking existence. No mtime caching (NFS may
  have stale attribute caches).

---

## 6. Orchestration Tool Bridge

### Problem

Claudechic's MCP tools (`spawn_agent`, `tell_agent`, `ask_agent`, `close_agent`,
`list_agents`, `advance_phase`, `get_phase`, `acknowledge_warning`,
`request_override`, `whoami`) are currently registered using
`claude_agent_sdk`'s `@tool` decorator and served via
`create_sdk_mcp_server()` (see `mcp.py:23`, `mcp.py:160-287`).

For the pydantic-ai backend, these same tools need to be registered as a
pydantic-ai `FunctionToolset` so the LLM can call them via function calling.

### Solution: Dual Registration with Shared Implementations

Extract the business logic from `mcp.py`'s `@tool`-decorated functions into
standalone `async def _impl_*()` functions. Both the MCP path and the
FunctionToolset path call the same implementation.

```
mcp.py (Claude Code path)          chic_toolset.py (pydantic-ai path)
┌─────────────────────────┐        ┌──────────────────────────────────┐
│ @tool("spawn_agent")    │        │ @ts.tool_plain                   │
│ async def spawn_agent() │        │ async def spawn_agent()          │
│     return _impl_spawn()│        │     return _impl_spawn()         │
└────────────┬────────────┘        └────────────────┬─────────────────┘
             │                                      │
             └──────────────┬───────────────────────┘
                            │
                  ┌─────────┴─────────┐
                  │ _impl_spawn()     │
                  │ (shared logic in  │
                  │  mcp_impl.py)     │
                  └───────────────────┘
```

### App Reference: Dependency Injection

The shared implementation functions need access to the `ChatApp` instance
(specifically `app.agent_mgr` and `app._workflow_engine`). Instead of
relying on the `_app` global from `mcp.py`, the shared module uses an
explicit registration pattern:

```python
# claudechic/backends/tools/mcp_impl.py

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from claudechic.app import ChatApp

_app: ChatApp | None = None

def register_app(app: ChatApp) -> None:
    """Register the app instance for shared tool implementations.

    Called once from ChatApp.on_mount(). Both mcp.py and chic_toolset.py
    call into this module's _impl_* functions, which use _app to access
    the AgentManager and WorkflowEngine.

    This is the same pattern as mcp.py's set_app() — we consolidate
    both into a single registration point.
    """
    global _app
    _app = app

def _require_app():
    """Get app reference or raise clear error."""
    if _app is None or _app.agent_mgr is None:
        raise RuntimeError("App not initialized — register_app() not called")
    return _app
```

### Shared Implementation Module

```python
# claudechic/backends/tools/mcp_impl.py (continued)

async def _impl_spawn_agent(
    name: str, path: str, prompt: str,
    model: str = "", agent_type: str = "",
    caller_name: str | None = None,
    requires_answer: bool = False,
) -> str:
    """Shared spawn_agent logic (extracted from mcp.py:179-287)."""
    app = _require_app()
    # Exactly the current mcp.py logic:
    # - validate path exists
    # - check agent name uniqueness
    # - call app.agent_mgr.create()
    # - inject workflow agent folder prompt
    # - fire-and-forget initial prompt
    ...

async def _impl_tell_agent(name: str, message: str, caller_name: str | None) -> str:
    """Shared tell_agent logic (extracted from mcp.py)."""
    app = _require_app()
    ...

# etc. for ask_agent, close_agent, list_agents, advance_phase, get_phase,
# acknowledge_warning, request_override, whoami
```

### pydantic-ai FunctionToolset Registration

```python
def create_chic_toolset(caller_name: str | None = None) -> FunctionToolset:
    ts = FunctionToolset()

    @ts.tool_plain
    async def spawn_agent(name: str, path: str, prompt: str,
                          model: str = "", type: str = "",
                          requires_answer: bool = False) -> str:
        """Create a new agent in claudechic."""
        return await _impl_spawn_agent(
            name, path, prompt, model, type,
            caller_name=caller_name,
            requires_answer=requires_answer,
        )

    @ts.tool_plain
    async def tell_agent(name: str, message: str) -> str:
        """Send a message to another agent (no reply expected)."""
        return await _impl_tell_agent(name, message, caller_name)

    @ts.tool_plain
    async def ask_agent(name: str, prompt: str) -> str:
        """Ask another agent a question (expects reply)."""
        return await _impl_ask_agent(name, prompt, caller_name)

    @ts.tool_plain
    async def advance_phase() -> str:
        """Advance the workflow to its next phase."""
        return await _impl_advance_phase()

    @ts.tool_plain
    async def get_phase() -> str:
        """Get current workflow phase and loaded rules."""
        return await _impl_get_phase()

    # ... close_agent, list_agents, acknowledge_warning, request_override, whoami

    return ts
```

---

## 7. Guardrails Integration

### Current Architecture

Claudechic's guardrails evaluate rules via `PreToolUse` hooks
(`guardrails/hooks.py:36-58`). The `create_guardrail_hooks()` function returns
a `dict[str, list[HookMatcher]]` that the Claude Code SDK evaluates before each
tool call. The two-step pipeline:

1. **Injections** — mutate `tool_input` in-place (e.g., append system prompts)
2. **Enforcement** — evaluate rules: `deny` → block, `warn` → require ack,
   `log` → audit only

### pydantic-ai Mapping

pydantic-ai's hook system provides `before_tool_execute` and
`after_tool_execute` hooks that fire for every tool call. The mapping is direct:

| Claudechic Guardrail | pydantic-ai Hook | Mechanism |
|---------------------|------------------|-----------|
| `deny` enforcement | `before_tool_execute` | Raise `SkipToolExecution("Blocked: ...")` |
| `warn` enforcement | `before_tool_execute` | Raise `SkipToolExecution` with ack instructions |
| `log` enforcement | `after_tool_execute` | Log hit, allow execution |
| Injections | `before_tool_execute` | Mutate `args` dict, return modified args |
| Override tokens | `before_tool_execute` | Check `consume_override` callback |

### Implementation

```python
# In pydantic_ai_backend.py

def _create_guardrail_hooks(
    loader: ManifestLoader,
    hit_logger: HitLogger,
    agent_role: str | None,
    get_phase: Callable[[], str | None],
    get_active_wf: Callable[[], str | None],
    consume_override: Callable,
    permission_callback: Callable | None = None,  # NEW: interactive permissions
    tool_result_queue: asyncio.Queue | None = None,  # NEW: result event queue
) -> Hooks:
    """Create pydantic-ai Hooks that evaluate claudechic guardrails."""
    hooks = Hooks()

    @hooks.on.before_tool_execute
    async def evaluate_guardrails(ctx, *, call, tool_def, args):
        tool_name = call.tool_name
        tool_input = dict(args)  # copy for mutation safety

        result = loader.load()

        # Fail-closed
        if result.errors and not result.rules:
            fatal = any(e.source == "discovery" for e in result.errors)
            if fatal:
                raise SkipToolExecution(
                    "Rules unavailable — global/ or workflows/ unreadable"
                )

        current_phase = get_phase()
        active_wf = get_active_wf()

        # Step 1: Injections
        for injection in result.injections:
            if injection.namespace not in ("global", active_wf):
                continue
            if not matches_trigger(injection, tool_name):
                continue
            if should_skip_for_role(injection, agent_role):
                continue
            if should_skip_for_phase(injection, current_phase):
                continue
            apply_injection(injection, tool_input)

        # Step 2: Enforcement rules
        for rule in result.rules:
            if rule.namespace not in ("global", active_wf):
                continue
            if not matches_trigger(rule, tool_name):
                continue
            if should_skip_for_role(rule, agent_role):
                continue
            if should_skip_for_phase(rule, current_phase):
                continue
            if rule.exclude_pattern:
                field_value = _get_field(tool_input, rule.detect_field)
                if rule.exclude_pattern.search(field_value):
                    continue
            if rule.detect_pattern:
                field_value = _get_field(tool_input, rule.detect_field)
                if not rule.detect_pattern.search(field_value):
                    continue

            # Rule matches
            hit = HitRecord(
                rule_id=rule.id, agent_role=agent_role,
                tool_name=tool_name, enforcement=rule.enforcement,
                timestamp=time.time(),
            )

            if rule.enforcement == "log":
                hit_logger.record(replace(hit, outcome="allowed"))
                continue
            elif rule.enforcement == "warn":
                if consume_override(rule.id, tool_name, tool_input, "warn"):
                    hit_logger.record(replace(hit, outcome="ack"))
                    continue
                hit_logger.record(replace(hit, outcome="blocked"))
                raise SkipToolExecution(
                    f"{rule.message}\n"
                    f'acknowledge_warning(rule_id="{rule.id}", ...)'
                )
            elif rule.enforcement == "deny":
                if consume_override(rule.id, tool_name, tool_input, "deny"):
                    hit_logger.record(replace(hit, outcome="overridden"))
                    continue
                hit_logger.record(replace(hit, outcome="blocked"))
                raise SkipToolExecution(
                    f"{rule.message}\n"
                    f'request_override(rule_id="{rule.id}", ...)'
                )

        # Step 3: Interactive permission check (NEW)
        if permission_callback:
            approved = await permission_callback(tool_name, tool_input)
            if not approved:
                raise SkipToolExecution(
                    f"Tool '{tool_name}' denied by user."
                )

        # Return potentially-mutated args (injection support)
        return tool_input

    @hooks.on.after_tool_execute
    async def emit_tool_result(ctx, *, call, tool_def, args, result):
        """Push ToolResultEvent into the queue for send_and_stream to yield."""
        if tool_result_queue is not None:
            tool_result_queue.put_nowait(ToolResultEvent(
                tool_use_id=call.tool_call_id,
                output=str(result),
                is_error=False,
            ))

    return hooks
```

### Key Design Decision

The guardrails rule evaluation functions (`matches_trigger`, `should_skip_for_role`,
`should_skip_for_phase`, `apply_injection`, `_get_field`) in
`guardrails/rules.py` are **pure functions with no SDK imports**. They work
identically in both the Claude Code hook path and the pydantic-ai hook path.
Only the hook *wrapper* differs — `HookMatcher` closure (Claude Code) vs
`Hooks.on.before_tool_execute` decorator (pydantic-ai).

### 7b. Interactive Tool Permissions (pydantic-ai backend)

#### Problem

Claude Code's SDK has a built-in `can_use_tool` callback that pauses execution
and asks the user for permission before running tools. The pydantic-ai backend
has no equivalent — tools execute immediately unless blocked. Without interactive
permissions, the pydantic-ai backend would auto-approve ALL tool calls, which
conflicts with claudechic's safety model.

#### Solution: Permission Bridge via `before_tool_execute` Hook

The permission system is implemented as part of the `before_tool_execute` hook
chain. After guardrails evaluation passes, the hook checks whether the tool
requires interactive approval and, if so, pauses via an `asyncio.Event` until
the TUI responds.

```python
# In pydantic_ai_backend.py

class PermissionBridge:
    """Bridges pydantic-ai tool execution to claudechic's TUI permission flow.

    When a tool call requires approval:
    1. Hook fires → creates PermissionRequestEvent with an asyncio.Event
    2. Event is pushed into the backend's event queue
    3. send_and_stream() yields the PermissionRequestEvent
    4. Agent._process_response() receives it → calls observer.on_prompt_added()
    5. TUI shows SelectionPrompt → user approves/denies
    6. TUI sets event.approved and signals the asyncio.Event
    7. Hook resumes → continues or raises SkipToolExecution
    """

    def __init__(
        self,
        event_queue: asyncio.Queue,
        session_allowed_tools: set[str],
    ):
        self._event_queue = event_queue
        self._session_allowed_tools = session_allowed_tools

    async def check_permission(
        self, tool_name: str, tool_input: dict
    ) -> bool:
        """Check if tool needs permission and wait for user response.

        Returns True if approved, False if denied.
        """
        # Tools already approved for this session (user chose "allow all")
        if tool_name in self._session_allowed_tools:
            return True

        # Read-only tools can be auto-approved in Phase 1
        # (matches Claude Code's "default" permission mode behavior)
        if tool_name in {"Read", "Glob", "Grep", "Ls", "list_agents",
                         "get_phase", "whoami"}:
            return True

        # Create approval event and push to stream
        approval_event = asyncio.Event()
        request = PermissionRequestEvent(
            tool_use_id=f"perm-{tool_name}-{id(approval_event)}",
            tool_name=tool_name,
            tool_input=tool_input,
            approval_event=approval_event,
        )
        self._event_queue.put_nowait(request)

        # Wait for TUI to respond
        await approval_event.wait()

        # If user chose "allow all for session", remember it
        if request.approved and getattr(request, 'allow_session', False):
            self._session_allowed_tools.add(tool_name)

        return request.approved
```

#### Integration with `_process_response()`

The Agent's response loop handles `PermissionRequestEvent` like any other event:

```python
# In agent.py _process_response():
async for event in self.backend.send_and_stream(prompt):
    if isinstance(event, PermissionRequestEvent):
        # Route to TUI permission prompt
        perm_request = PermissionRequest(
            tool_name=event.tool_name,
            tool_input=event.tool_input,
        )
        # Observer shows SelectionPrompt in TUI
        if self.observer:
            self.observer.on_prompt_added(self, perm_request)
        # The PermissionBridge is waiting on event.approval_event —
        # TUI will set it when user responds
```

**Note:** This creates a cooperative blocking pattern: the `before_tool_execute`
hook is `await`-ing the `approval_event` while `send_and_stream()` is yielding
the `PermissionRequestEvent` to the caller. This works because pydantic-ai's
tool execution hook and the `send_and_stream()` iterator share the same async
context — the hook blocks its coroutine while the iterator's next() is free to
yield events from the queue.

**Important concurrency detail:** The `PermissionRequestEvent` is pushed via a
shared `asyncio.Queue` between the hook (running inside pydantic-ai's tool
execution) and the `send_and_stream()` generator. The generator must poll
this queue between node iterations.

---

## 8. Multi-Agent

### Architecture

Each claudechic `Agent` gets its own `AgentBackend` instance. For
`PydanticAIBackend`, this means each agent has:

- Its own `pydantic_ai.Agent` instance
- Its own `message_history` list (conversation isolation)
- Its own toolset instances (with `caller_name` bound for MCP tool routing)

```
AgentManager
├── Agent "Coordinator" (id=abc)
│   └── PydanticAIBackend (model="openai:gpt-4o")
│       ├── pydantic_ai.Agent instance
│       ├── message_history: [...]
│       └── toolsets: [file_tools, chic_tools(caller="Coordinator")]
├── Agent "Implementer" (id=def)
│   └── PydanticAIBackend (model="openai:gpt-4o")
│       ├── pydantic_ai.Agent instance
│       ├── message_history: [...]
│       └── toolsets: [file_tools, chic_tools(caller="Implementer")]
└── Agent "Reviewer" (id=ghi)
    └── PydanticAIBackend (model="openai:gpt-4o-mini")  # cheaper model
        ├── pydantic_ai.Agent instance
        ├── message_history: [...]
        └── toolsets: [file_tools, chic_tools(caller="Reviewer")]
```

### spawn_agent / tell_agent / ask_agent / close_agent

**No changes to the semantics.** The routing happens at the `AgentManager` level,
not the backend level:

- `spawn_agent` → `agent_mgr.create()` → creates new `Agent` + new backend
- `tell_agent` → `agent_mgr.find_by_name()` → `agent.send(prompt)` → backend
- `ask_agent` → same as `tell_agent` but with reply-tracking metadata
- `close_agent` → `agent_mgr.close()` → `agent.disconnect()` → backend cleanup

The `_send_prompt_fire_and_forget()` function in `mcp.py:116-154` calls
`agent.send(prompt)`, which calls `backend.send_and_stream()`. This code path
is backend-agnostic.

### Mixed Backends (Future)

The backend factory could return different backends per agent. For example,
Coordinator on Claude Code, sub-agents on pydantic-ai with a cheaper model.
This is architecturally possible but out of scope for Phase 1 (config
complexity).

---

## 9. Configuration

### New Config Options in `.claudechic.yaml`

```yaml
# Backend selection (default: claude-code)
backend: pydantic-ai

# pydantic-ai backend settings
pydantic_ai:
  model: openai:gpt-4o           # pydantic-ai model string
  # model: ollama/qwen3:32b      # local Ollama
  # model: anthropic:claude-sonnet-4-5  # Anthropic direct API
  # model: google-gla:gemini-2.5-pro   # Google Gemini
  api_key: ${OPENAI_API_KEY}     # env var expansion (optional)
  temperature: 0.7               # model settings (optional)
  max_tokens: 16384              # model settings (optional)
```

### CLI Flags

```
--backend <name>    Backend to use: "claude-code" (default) or "pydantic-ai"
--model <string>    Model for pydantic-ai backend (e.g., "openai:gpt-4o")
```

CLI flags override `.claudechic.yaml` config.

### Optional Dependency

```toml
# pyproject.toml
[project.optional-dependencies]
pydantic-ai = ["pydantic-ai>=1.80.0,<1.90.0"]
```

Installation:

```bash
pip install claudechic                  # Claude Code only (default)
pip install claudechic[pydantic-ai]     # Adds pydantic-ai backend support
```

At runtime, if `--backend pydantic-ai` is specified but pydantic-ai is not
installed, claudechic shows a clear error:

```
Error: pydantic-ai backend requires 'pydantic-ai' package.
Install with: pip install claudechic[pydantic-ai]
```

### Getting Started with Alternative Backends

Quick start guide for users switching to a non-Claude-Code backend:

1. **Install the extra:**
   ```bash
   pip install claudechic[pydantic-ai]
   ```

2. **Set your API key:**
   ```bash
   # For OpenAI:
   export OPENAI_API_KEY=sk-...

   # For Anthropic direct API (not Claude Code):
   export ANTHROPIC_API_KEY=sk-ant-...

   # For Google Gemini:
   export GOOGLE_API_KEY=...

   # For Ollama (local, no key needed):
   ollama serve  # ensure Ollama is running
   ```

3. **Choose a model** (use pydantic-ai model string format):
   ```
   openai:gpt-4o             # OpenAI GPT-4o
   openai:gpt-4o-mini        # Cheaper OpenAI
   anthropic:claude-sonnet-4-5  # Anthropic direct API
   google-gla:gemini-2.5-pro # Google Gemini
   ollama:qwen3:32b          # Local Ollama
   ```

4. **Run claudechic:**
   ```bash
   # One-time via CLI flags:
   claudechic --backend pydantic-ai --model openai:gpt-4o

   # Or set in config (~/.claude/.claudechic.yaml):
   backend: pydantic-ai
   pydantic_ai:
     model: openai:gpt-4o
   ```

5. **Verify:** Look for the model name in the status footer (e.g., `● gpt-4o pydantic-ai` instead of `● opus default`). Workflows, guardrails, and multi-agent all work as normal.

### Template-Specific Notes

The template's MCP tools (`template/mcp_tools/slurm.py` and
`template/mcp_tools/lsf.py`) import from `claude_agent_sdk` directly and
remain **Claude Code-only**. They are not bridged to the pydantic-ai backend
in Phase 1. When using pydantic-ai backend, SLURM/LSF job submission must be
done via the `Bash` tool.

---

## 10. Terminology / Naming

### The "Agent" Collision

Both claudechic and pydantic-ai have an `Agent` class with different meanings:

| Term | claudechic meaning | pydantic-ai meaning |
|------|-------------------|---------------------|
| Agent | Autonomous entity with SDK connection, message history, permissions, TUI | Stateless LLM-calling container with tools and output types |

### Resolution: Wrapping Approach (Option C)

Claudechic's `Agent` class remains the public, user-facing concept. The
pydantic-ai `Agent` is an internal implementation detail, never exposed to
users or to claudechic code outside of `backends/pydantic_ai_backend.py`.

**Import conventions:**

```python
# Inside backends/pydantic_ai_backend.py ONLY:
from pydantic_ai import Agent as PaiAgent

# Everywhere else in claudechic:
from claudechic.agent import Agent          # claudechic's Agent
from claudechic.backends.protocol import AgentBackend  # the abstraction
```

The pydantic-ai `Agent` (aliased as `PaiAgent`) is never imported outside of
`pydantic_ai_backend.py`.

### User-Facing Vocabulary

| User sees | Developer term | Notes |
|-----------|---------------|-------|
| "backend" | `AgentBackend` | Shown in config, CLI flags, status footer |
| "model" | Model string | e.g. "openai:gpt-4o" — pydantic-ai format |
| "agent" | `Agent` | Always claudechic's Agent — TUI sidebar entity |
| "tool" | Tool name | e.g. "Read", "Bash" — same names regardless of backend |
| "workflow" | Workflow/phases | Unchanged |
| "guardrail" | Rule | Unchanged |

### Status Footer Display

When using pydantic-ai backend, the model label in the status footer shows
the pydantic-ai model string instead of "opus"/"sonnet":

```
claude-code backend:    ● opus    default
pydantic-ai backend:    ● gpt-4o  pydantic-ai
```

---

## 11. Known Limitations (Phase 1)

| Limitation | Impact | User Experience | Workaround |
|-----------|--------|-----------------|------------|
| **No session resume** | Cannot `/resume` a pydantic-ai session | `/resume` → toast: "Session resume not available on pydantic-ai backend. Planned for Phase 2." | Conversation history lost on restart; use Claude Code backend for long sessions |
| **No `/compact`** | Context window fills up over long conversations | `/compact` → toast: "Context compaction not available on pydantic-ai backend." | Start fresh agent; manually summarize; future phase will add summarization |
| **No file checkpointing** | No `/rewind` support | `/rewind` → toast: "File checkpointing not available on pydantic-ai backend." | Use git for undo |
| **No permission mode cycling** | Shift+Tab has no effect | Shift+Tab → grey out mode indicator + toast: "Permission modes not available on pydantic-ai backend. Guardrails rules still enforce safety." | Guardrails rules still enforce safety; manual approval via `request_override` |
| **No real-time tool streaming** | Tool results appear after completion (not streamed line-by-line) | Slightly delayed tool result display | Functional but slightly different UX from Claude Code |
| **Model quality varies** | Cheaper/smaller models make more mistakes in multi-agent workflows | More retry prompts, occasional broken tool calls | Use capable models (GPT-4o, Gemini 2.5 Pro) for Coordinator agents |
| **No WebSearch/WebFetch/NotebookEdit** | Only 7 core tools + orchestration tools available | LLM may hallucinate unavailable tools (mitigated by system prompt) | Use Bash + curl for web; edit notebooks manually |
| **No image input** | pydantic-ai supports images but integration not in Phase 1 | Image paste → toast: "Image input not available on pydantic-ai backend." | Use Claude Code backend for image tasks |
| **Token tracking approximate** | pydantic-ai reports tokens differently from Claude Code | Usage bar may be less accurate | Informational only |
| **No SLURM/LSF MCP tools** | Template MCP tools are Claude Code-only | Tools not available; use Bash instead | `sbatch`, `bsub` via Bash tool |

### First-Launch Banner

On the first launch with the pydantic-ai backend, show an informational banner:

```
╭─────────────────────────────────────────────────────╮
│ Running with pydantic-ai backend (openai:gpt-4o)    │
│                                                     │
│ Available: Read, Write, Edit, Bash, Glob, Grep, Ls  │
│           Multi-agent, Workflows, Guardrails        │
│                                                     │
│ Not available: /resume, /compact, /rewind,          │
│   WebSearch, WebFetch, NotebookEdit, images         │
│                                                     │
│ Run /backend for current backend status.            │
╰─────────────────────────────────────────────────────╯
```

Add `/backend` command that shows current backend type, model, available tools,
and known limitations.

---

## 12. Risks & Mitigations

### R1: Streaming Impedance Mismatch (HIGH)

**Risk:** Claude Code streams tool results in real-time (you see a file being
read line by line). pydantic-ai's tool execution is synchronous — the tool runs
to completion, then returns the full result. This creates a UX difference.

**Mitigation:** The TUI already handles non-streaming tool results (it shows the
collapsible widget, then fills in output when `on_tool_result` fires). The only
difference is timing — results appear slightly later. Accept this as a Phase 1
limitation; Phase 2 could add chunked tool output emission.

### R2: Cancellation / Interrupt Race Conditions (HIGH)

**Risk:** When the user presses Escape to interrupt, `agent.interrupt()` sets a
cancel event and exits the `agent.iter()` async context. But pydantic-ai may be
mid-tool-execution (e.g., a Bash command running). The tool's subprocess needs
cleanup.

**Mitigation:** Tool implementations must handle `asyncio.CancelledError`
gracefully — kill subprocesses, close file handles. The Bash tool should use
`try/finally` with `proc.kill()`. pydantic-ai's context manager cleanup should
handle most cases; add explicit subprocess tracking as defense in depth.

### R3: Conversation History Desync (MEDIUM)

**Risk:** Claudechic maintains its own `Agent.messages: list[ChatItem]` for TUI
rendering. pydantic-ai maintains `message_history: list[ModelMessage]` for LLM
context. These could diverge if errors occur mid-conversation.

**Mitigation:** The pydantic-ai backend is the source of truth for LLM history.
Claudechic's `ChatItem` list is for display only. After each `send_and_stream`
completes, update `self._messages = agent_run.result.all_messages()`. On error,
the pydantic-ai history rolls back naturally (the failed turn isn't added).

### R4: Tool Argument Validation with Weaker Models (MEDIUM)

**Risk:** Smaller models (Ollama, GPT-4o-mini) may produce malformed tool
arguments — wrong types, missing required fields, invalid JSON. Claude Code
handles retries internally; pydantic-ai uses `ModelRetry` + retry count.

**Mitigation:** pydantic-ai validates tool arguments via Pydantic models
(automatic from function signatures). Invalid arguments trigger automatic
retries (configurable via `retries=` parameter, default 1). Set retries=2 for
file tools with weaker models.

### R5: pydantic-ai API Instability (MEDIUM)

**Risk:** pydantic-ai is actively developed (v1.80.0). The `Agent.iter()` API,
hook system, or toolset interface could change in future versions.

**Mitigation:** Pin `pydantic-ai>=1.80.0,<1.90.0` in optional dependencies
(tighter than `<2.0.0` to catch minor-version API changes). The integration is
contained to a single file (`pydantic_ai_backend.py` + `chic_toolset.py`), so
API changes only affect ~370 lines. Add **weekly CI job** running against latest
pydantic-ai to detect breakage early. Wait 2-4 weeks after v1.80.0 before
starting implementation.

### R6: Guardrail Hook Timing (LOW)

**Risk:** Claude Code's guardrails evaluate *before* the tool runs (PreToolUse
hook). pydantic-ai's `before_tool_execute` fires at the same point. But
pydantic-ai handles tool arguments as already-parsed dicts, while Claude Code
may pass raw strings. Pattern matching on `detect_field` must work identically.

**Mitigation:** Both paths use the same `_get_field()` + `detect_pattern.search()`
logic from `guardrails/rules.py`. The pure function doesn't care about the
calling context. Test with both backends to verify identical rule matching.

### R7: Cost Overrun with API Backends (LOW)

**Risk:** Users on OpenAI/Gemini API pay per token. Long multi-agent workflows
could generate unexpected bills, unlike Claude Max subscription (flat rate).

**Mitigation:** Expose pydantic-ai's `UsageLimits` via config:
```yaml
pydantic_ai:
  usage_limits:
    request_limit: 50
    response_tokens_limit: 100000
```
Show running cost estimate in the status footer (pydantic-ai reports cost
if the model supports it).

### R8: Private SDK Attribute Breakage (CRITICAL)

**Risk:** `ClaudeCodeBackend` accesses private SDK attributes for subprocess
management: `client._query.transport._process.pid` (in `_is_transport_alive`
and `_sigint_fallback`), and `client._transport.write()` (for image messages).
These are undocumented internals that could change in any `claude-agent-sdk`
release without warning.

**Mitigation:**
- Write **characterization tests** that verify these private attribute paths
  exist and behave as expected BEFORE starting the extraction refactor.
- Wrap each private attribute access in a try/except with graceful degradation.
- File feature request with claude-agent-sdk for public API equivalents
  (get_subprocess_pid, send_raw_message).
- Allocate extra time: **3 days** for ClaudeCodeBackend (was 1 day) to account
  for discovery of additional private attribute usage.

### R9: Fire-and-Forget Message Loss (HIGH)

**Risk:** `_send_prompt_fire_and_forget()` in `mcp.py:116-154` creates an
asyncio task that calls `agent.send(prompt)`. If the agent is busy (already
processing a response), the message is queued in `_pending_messages`. With the
pydantic-ai backend, if the agent disconnects or errors mid-response, queued
messages are lost silently.

**Mitigation:** Add logging when pending messages are dropped during disconnect.
Consider adding a `drain_on_error` flag to replay queued messages after error
recovery. For Phase 1, accept this limitation with explicit logging.

### R10: NFS / Filesystem Latency (MEDIUM)

**Risk:** This project runs on HPC cluster NFS. File operations (Read, Write,
Edit, Glob, Grep) may block the event loop on NFS latency spikes (100ms+
typical, seconds under load). Claude Code handles this in its subprocess; our
local tools run in-process.

**Mitigation:** All file I/O wrapped in `asyncio.to_thread()` (see Section 5
tool implementations). Avoid `os.stat()` calls in hot paths. Set generous
timeouts for Glob/Grep operations. Add NFS-specific integration tests if
possible.

### R11: Context Window Exhaustion (MEDIUM-HIGH)

**Risk:** Without `/compact`, long conversations on pydantic-ai backend will
hit context window limits. Different models have vastly different context sizes
(GPT-4o: 128K, Ollama models: 8-32K). There is no automatic recovery.

**Mitigation:**
- Track token usage in `CompleteEvent` and show context bar in TUI (same as
  Claude Code path).
- Emit `ErrorEvent(code="context_overflow")` when the API returns a context
  error — TUI shows "Context window full. Start a new agent."
- Phase 2 will add client-side summarization for pydantic-ai backend.
- For Ollama/small models, recommend starting new agents frequently.

### R12: Concurrent Tool Execution Race Conditions (MEDIUM)

**Risk:** pydantic-ai may execute multiple tools concurrently in a single
`CallToolsNode`. If two tools write to the same file simultaneously (e.g.,
two Edit calls), results are undefined.

**Mitigation:** Phase 1 tools use synchronous-style execution (one at a time
via `asyncio.to_thread`). pydantic-ai's default is sequential tool execution.
If parallel execution is enabled in future, add file-level locking in the
toolset.

### R13: API Key Exposure in Config (LOW-MEDIUM)

**Risk:** Users may put raw API keys in `.claudechic.yaml` which could be
committed to version control.

**Mitigation:**
- Support `${ENV_VAR}` expansion syntax so keys stay in environment variables.
- Add `.claudechic.yaml` to the project's `.gitignore` template.
- At startup, warn if `api_key` field contains a literal key (not an env var
  reference).
- Document best practice: always use environment variables for API keys.

---

## 13. Effort Estimate

### Component Breakdown

| Component | LOC | Time (days) | Notes |
|-----------|-----|-------------|-------|
| `backends/protocol.py` + event types + canonical types | 120 | 0.5 | Protocol + dataclasses + ToolUseData/ToolResultData |
| `backends/claude_code.py` | 200 | **3** | Extract from agent.py; **private SDK attrs = high risk**; characterization tests first |
| `backends/pydantic_ai_backend.py` | 350 | **3** | Core integration; iter() + streaming + arg accumulation + permissions |
| `backends/tools/filesystem.py` | 300 | 2 | Read/Write/Edit/Glob/Grep; needs testing; NFS considerations |
| `backends/tools/shell.py` | 100 | 0.5 | Bash/Ls |
| `backends/tools/chic_toolset.py` + `mcp_impl.py` | 350 | **1.5** | Extract from mcp.py; dual registration; app injection |
| `agent.py` modifications | 150 | **2** | Replace SDK types; refactor _process_response; drain logic to backend; PermissionRequestEvent handling |
| `agent_manager.py` modifications | 40 | 0.5 | Factory pattern |
| `app.py` modifications | 60 | 0.5 | Config + backend selection |
| `messages.py` + widget SDK type replacement | 50 | **1** | ToolUseData/ToolResultData swap across messages.py, chat_view.py, tools.py, tool_protocol.py |
| Guardrails hook adapter + permission bridge | 80 | **1** | pydantic-ai hook wrapper + interactive permissions |
| Config + CLI flags + onboarding | 30 | 0.5 | .claudechic.yaml + argparse + first-launch banner |
| `pyproject.toml` + packaging | 5 | 0.25 | Optional dependency |
| Tests: characterization (ClaudeCodeBackend) | 100 | 1 | Verify private SDK attrs before refactoring |
| Tests: security (path traversal, bash, OOM) | 150 | 1 | Path escape, file size, output truncation |
| Tests: guardrail parity | 100 | 0.5 | Same rules produce same results on both backends |
| Tests: error propagation | 50 | 0.5 | ErrorEvent handling, recovery flows |
| Tests: integration + protocol | 200 | 1 | Backend protocol, tools, multi-agent |
| Edge cases + debugging | — | 2 | Streaming, cancellation, error handling |
| Security hardening | — | 1 | NFS edge cases, output limits, key exposure warnings |
| **Total** | **~2440** | **~24 days** | |

### Working Prototype vs Production-Hardened

| Milestone | Scope | Time |
|-----------|-------|------|
| **Prototype** | Backend protocol + Claude Code adapter (with characterization tests) + pydantic-ai adapter + 3 tools (Read, Edit, Bash) + chic toolset. Single model, no guardrails/permissions. | ~9 days |
| **Functional** | All 7 tools, guardrails integration, permission bridge, config system, multi-agent working. Basic testing. | ~17 days |
| **Production** | Full test suite (characterization + security + parity + integration), error handling, edge cases, NFS hardening, onboarding UX, cost tracking, UsageLimits. | ~24 days |

---

## 14. Future Phases (Out of Scope for Phase 1)

### Phase 2: Session Persistence & Compaction

- Implement conversation history serialization for pydantic-ai backend
- Save/restore `message_history` to `.chicsessions/` format
- Implement context compaction (summarize old messages to free tokens)
- Enable `/resume` for pydantic-ai sessions

### Phase 3: Enhanced Tool Parity

- Implement WebSearch, WebFetch (via pydantic-ai MCP client or direct HTTP)
- Implement NotebookEdit (Jupyter cell manipulation)
- Image input support for multi-modal models
- File checkpointing (git-based snapshots for `/rewind`)

### Phase 4: Ollama "Lite Mode"

- Optimized configuration for local models (smaller context, fewer tools)
- Automatic tool filtering based on model capability
- Reduced system prompt for smaller context windows
- Local-only mode with no API calls

### Phase 5: MCP Server Mode

- Expose claudechic as an MCP server that Cursor/Cline/other editors consume
- Clients call claudechic's workflow/guardrails/multi-agent tools via MCP
- Editor-agnostic workflow orchestration

### Phase 6: Feature Parity Matrix

| Feature | Claude Code | pydantic-ai (Phase 1) | pydantic-ai (Full) |
|---------|------------|----------------------|-------------------|
| Core tools (Read/Write/Edit/Bash/Glob/Grep) | ✅ | ✅ | ✅ |
| Multi-agent | ✅ | ✅ | ✅ |
| Workflows/Phases | ✅ | ✅ | ✅ |
| Guardrails | ✅ | ✅ | ✅ |
| Interactive permissions | ✅ | ✅ | ✅ |
| Session resume | ✅ | ❌ | ✅ (Phase 2) |
| Context compaction | ✅ | ❌ | ✅ (Phase 2) |
| File checkpointing | ✅ | ❌ | ✅ (Phase 3) |
| Permission modes | ✅ | ❌ | ⚠️ (partial) |
| Web tools | ✅ | ❌ | ✅ (Phase 3) |
| Image input | ✅ | ❌ | ✅ (Phase 3) |
| MCP server mode | ❌ | ❌ | ✅ (Phase 5) |
| 15+ LLM providers | ❌ | ✅ | ✅ |
| Local models (Ollama) | ❌ | ✅ | ✅ |
| Cost control | ❌ | ✅ | ✅ |

---

## Appendix A: File Reference

All paths relative to `submodules/claudechic/claudechic/`:

| File | Key Functions | SDK Coupling Level |
|------|--------------|-------------------|
| `agent.py` | `Agent.connect()` (L287), `Agent._process_response()` (L750), `Agent._handle_sdk_message()` (L939), `Agent.interrupt()` (L536) | DEEP — primary refactor target |
| `agent_manager.py` | `AgentManager.__init__` (L32), `AgentManager.create()` (L120), `AgentManager.connect_agent()` (L173) | MODERATE — factory pattern change |
| `app.py` | `ChatApp._make_options()` (L719), `ChatApp.on_mount()` (L770), `ChatApp._merged_hooks()` | MODERATE — config + factory |
| `mcp.py` | `_make_spawn_agent()` (L157), `_send_prompt_fire_and_forget()` (L116), `create_chic_server()` | MODERATE — tool extraction |
| `guardrails/hooks.py` | `create_guardrail_hooks()` (L36), `evaluate()` (L60) | MODERATE — hook adapter |
| `protocols.py` | `AgentObserver`, `AgentManagerObserver`, `PermissionHandler` | LIGHT — type import swap; `on_system_message` signature update |
| `messages.py` | `ResponseComplete`, `ToolUseMessage`, `ToolResultMessage` | LIGHT — replace SDK types with canonical `ToolUseData`/`ToolResultData` |
| `widgets/content/tools.py` | `ToolUseWidget`, tool rendering | LIGHT — runtime `ToolUseBlock`/`ToolResultBlock` imports → canonical types |
| `widgets/base/tool_protocol.py` | `ToolWidget.update_result()` | LIGHT — `ToolResultBlock` in signature → `ToolResultData` |
| `widgets/layout/chat_view.py` | `ChatView._append_tool_use()` (L293), `ChatView._handle_tool_result()` (L351) | LIGHT — constructs `ToolUseBlock` at runtime → `ToolUseData` |
| `workflows/agent_folders.py` | `assemble_phase_prompt()` | LIGHT — imports `HookMatcher` from SDK |
| `enums.py` | `ToolName`, `AgentStatus`, `ResponseState` | NONE — already backend-agnostic |
| `workflows/` (other modules) | All modules | NONE — already backend-agnostic |
| `guardrails/rules.py` | All functions | NONE — pure functions |
| `guardrails/hits.py` | `HitLogger`, `HitRecord` | NONE — pure functions |
| `features/worktree/` | All functions | NONE — pure git operations |
| `sessions.py` | All functions | NONE — pure file I/O |
| `formatting.py` | All functions | NONE — pure functions |
| `file_index.py` | `FileIndex` | NONE — git ls-files |

**Test files requiring SDK import updates:**
- `tests/test_agent_permission.py` — imports `ToolUseBlock` etc.
- `tests/test_app_ui.py` — imports SDK message types
- `tests/test_widgets.py` — imports SDK block types

## Appendix B: pydantic-ai API Surface Used

| pydantic-ai API | Used For | Stable? |
|----------------|----------|---------|
| `Agent(model, toolsets=, hooks=, system_prompt=)` | Create LLM agent | ✅ Core API |
| `Agent.iter(prompt, message_history=)` | Node-by-node run | ✅ Core API |
| `Agent.is_model_request_node()` | Node type checking | ✅ Core API |
| `Agent.is_call_tools_node()` | Node type checking | ✅ Core API |
| `node.stream(ctx)` | Streaming from nodes | ✅ Core API |
| `PartDeltaEvent`, `PartStartEvent` | Stream event types | ✅ Core API |
| `FunctionToolset` | Tool registration | ✅ Core API |
| `Hooks.on.before_tool_execute` | Guardrails + permissions hook | ✅ Core API |
| `Hooks.on.after_tool_execute` | Result emission | ✅ Core API |
| `SkipToolExecution` | Block tool call | ✅ Core API |
| `UsageLimits` | Token/request limits | ✅ Core API |
| `FallbackModel` | Model fallback | ✅ Core API |
| `RunUsage` | Token usage reporting | ✅ Core API |
| `ModelSettings` | Temperature, max_tokens | ✅ Core API |

All APIs used are from pydantic-ai's documented core — no private APIs or
undocumented features. (Note: `ClaudeCodeBackend` does access private
`claude-agent-sdk` attributes — see R8.)

---

## Amendment Log

**2026-04-11 — Fresh Architecture Review**

Four independent reviewers analyzed the spec against the actual codebase.
The following amendments were incorporated:

### Critical Additions
1. **Permission system for pydantic-ai backend** (Section 7b) — Added
   `PermissionRequestEvent`, `PermissionBridge` class, and integration with
   `_process_response()`. Without this, pydantic-ai would auto-approve all tools.
2. **Tool argument accumulation** (Section 4, PydanticAIBackend) — Replaced
   empty `input={}` with proper `PartDeltaEvent` argument accumulator that
   collects `args_delta` JSON incrementally and emits `ToolUseEvent` only
   when complete.
3. **Bash/file tool security hardening** (Section 5) — Added 10MB file size
   cap, 30K char output truncation, NFS latency considerations with
   `asyncio.to_thread()`.
4. **4 missed files** (Section 3, Appendix A) — Added `widgets/content/tools.py`,
   `widgets/base/tool_protocol.py`, `widgets/layout/chat_view.py`,
   `workflows/agent_folders.py` to modification list with correct SDK coupling.
5. **ClaudeCodeBackend extraction risk** (Section 4, R8) — Documented private
   SDK attribute access, mandated characterization tests, increased estimate
   from 1 to 3 days.

### High-Priority Additions
6. **`ErrorEvent`** (Section 4) — Added to `BackendEvent` union with `code`,
   `message`, `recoverable`, `retry_after_ms` fields. Added error handling
   behavior table and exception translation.
7. **Unsupported command UX** (Section 11) — Added "User Experience" column
   specifying toast messages for each unavailable feature.
8. **Testing budget** (Section 13) — Increased from 2 days/200 LOC to
   4 days/500 LOC across 4 categories: characterization, security, parity,
   integration.
9. **`_app` global extraction** (Section 6) — Added `register_app()` pattern
   and `_require_app()` helper for shared implementation module.
10. **Onboarding guide** (Section 9) — Added "Getting Started with Alternative
    Backends" quick start.
11. **pydantic-ai pin** (Sections 1, 9, R5) — Tightened to `>=1.80.0,<1.90.0`.
    Added weekly CI and 2-4 week wait recommendation.
12. **Risks R8-R13** (Section 12) — Added: private SDK breakage (Critical),
    fire-and-forget message loss (High), NFS latency (Medium), context exhaustion
    (Medium-High), concurrent tool races (Medium), API key exposure (Low-Medium).
13. **Revised effort** (Section 13) — Total increased from 15 to 24 days.
14. **`send_and_stream()` image support** (Section 4) — Updated signature to
    accept `images: list[bytes] | None`.
15. **Widget SDK type replacement** (Sections 3, 4) — Added `ToolUseData` and
    `ToolResultData` canonical dataclasses. Detailed widget file changes.
16. **Test file modifications** (Section 3, Appendix A) — Listed test files
    needing SDK import updates.
17. **Template MCP tools** (Section 9) — Noted `slurm.py`/`lsf.py` remain
    Claude Code-only.
18. **LLM tool hallucination** (Section 4) — Added system prompt in
    `PydanticAIBackend` explicitly listing available/unavailable tools.
19. **First-launch banner** (Section 11) — Added info banner design and
    `/backend` command.
20. **Function name fix** — Corrected `_make_sdk_options()` to `_make_options()`
    throughout (actual name in app.py L719).
