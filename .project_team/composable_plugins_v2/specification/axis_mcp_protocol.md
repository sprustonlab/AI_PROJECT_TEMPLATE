# Axis Deep-Dive: MCP Tool Protocol (Seam #6)

> **Status:** Draft v1
> **Date:** 2026-03-30
> **Author:** Composability axis-agent (MCP Protocol)
> **Parent:** composability.md — Recommended deep-dive #1

---

## 1. Summary

This document specifies the precise contract for seam #6: `mcp_tools/`. It covers:

1. How claudechic discovers tool files at startup
2. The `get_tools()` function contract
3. Tool function signatures and decorator requirements
4. Error handling and graceful degradation
5. Seam cleanliness — what tools may and may not import
6. Testing strategy for isolated tool development

The design goal: **a tool file should be copyable to another project and work unchanged**, provided the host implements the same ~20-line discovery protocol.

---

## 2. Discovery Mechanism

### 2.1 Directory Layout

```
project-root/
  mcp_tools/
    __init__.py          # OPTIONAL — not required, not imported
    cluster.py           # get_tools(**kwargs) -> list[SdkMcpTool]
    my_custom_tool.py    # same contract
    _helpers.py          # skipped (underscore prefix)
    README.md            # skipped (non-.py)
    experimental/        # skipped (subdirectory — flat namespace only)
    __pycache__/         # skipped (dunder prefix)
```

### 2.2 Discovery Rules

The discovery code in claudechic's `mcp.py` walks `mcp_tools/` with these rules:

| Item | Action | Rationale |
|------|--------|-----------|
| `*.py` files (no underscore prefix) | **Import, call `get_tools()`** | These are tool modules |
| Files starting with `_` | **Skip silently** | Convention: private helpers, not tool entry points |
| `__pycache__/`, `__init__.py` | **Skip silently** | Python infrastructure, not tool modules |
| Non-`.py` files (`.md`, `.yaml`, etc.) | **Skip silently** | Only Python modules are tool sources |
| Subdirectories | **Skip silently** | Flat namespace — no recursive walk |

**Why flat (no subdirectories)?** Simplicity. A tool author puts one `.py` file in `mcp_tools/`. If a tool needs helper modules, it uses `_helper.py` files (skipped by discovery but importable by the tool). This matches the "directory conventions ARE the plugin system" principle — no nested discovery, no package scanning.

### 2.3 Discovery Code (~20 lines)

```python
import importlib.util
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

def discover_mcp_tools(
    mcp_tools_dir: Path,
    **kwargs,
) -> list:
    """Walk mcp_tools/, import each eligible .py, call get_tools().

    Returns a flat list of SdkMcpTool instances ready for
    create_sdk_mcp_server().
    """
    tools = []
    if not mcp_tools_dir.is_dir():
        return tools

    for py_file in sorted(mcp_tools_dir.glob("*.py")):
        # Skip private/helper files and __init__.py
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
            log.info(
                "mcp_tools: loaded %d tool(s) from %s",
                len(file_tools), py_file.name,
            )

        except Exception:
            log.warning(
                "mcp_tools: failed to load %s, skipping",
                py_file.name,
                exc_info=True,
            )
            continue

    return tools
```

### 2.4 Discovery Behavior Matrix

| Condition | Behavior | Log Level |
|-----------|----------|-----------|
| `mcp_tools/` doesn't exist | Return empty list, no error | (silent) |
| `mcp_tools/` is empty | Return empty list | (silent) |
| File has `get_tools()` | Call it, extend tool list | INFO |
| File has no `get_tools()` | Skip | DEBUG |
| File raises ImportError | Skip, continue to next file | WARNING (with traceback) |
| `get_tools()` raises exception | Skip, continue to next file | WARNING (with traceback) |
| `get_tools()` returns empty list | Fine — no tools added | INFO ("0 tools") |

**Critical principle: never crash.** A broken tool file must not prevent other tools (or claudechic itself) from loading. Log the warning and move on.

### 2.5 Integration Point in `mcp.py`

The discovery call is added to `create_chic_server()`:

```python
def create_chic_server(caller_name: str | None = None):
    tools = [
        # ... core agent tools (spawn, ask, tell, etc.) ...
    ]

    # Discover and load mcp_tools/ plugins
    mcp_tools_dir = Path.cwd() / "mcp_tools"
    external_tools = discover_mcp_tools(
        mcp_tools_dir,
        caller_name=caller_name,
        send_notification=_send_prompt_fire_and_forget,
        find_agent=_find_agent_by_name,
    )
    tools.extend(external_tools)

    return create_sdk_mcp_server(
        name="chic",
        version="1.0.0",
        tools=tools,
    )
```

**Note:** `Path.cwd()` is the project root (claudechic is started from there). This anchors discovery to the project, not to the claudechic installation — exactly right for a per-project plugin directory.

---

## 3. The `get_tools()` Contract

### 3.1 Signature

```python
def get_tools(**kwargs) -> list[SdkMcpTool]:
    """Return MCP tool functions for registration.

    Args:
        **kwargs: Optional wiring from the host. All kwargs are optional.
            Tools MUST have sensible defaults when any kwarg is absent.

    Returns:
        List of tool functions decorated with @tool from claude_agent_sdk.
        May return an empty list (tool disabled by configuration, etc.).
    """
```

### 3.2 kwargs Protocol (Closed Set for v2)

| kwarg | Type | Purpose | Default if absent |
|-------|------|---------|-------------------|
| `caller_name` | `str \| None` | Identity of the agent using these tools. Used for inter-agent notifications (e.g., "cluster-watch notifying agent X"). | `None` — tool works but can't identify the caller in notifications |
| `send_notification` | `Callable` | `(agent, message: str, *, caller_name: str) -> None`. Fire-and-forget prompt delivery to another agent. | `None` — tools requiring notifications degrade gracefully (e.g., `cluster_watch` returns an error) |
| `find_agent` | `Callable` | `(name: str) -> tuple[agent, error_msg \| None]`. Looks up an agent by name. Returns `(agent, None)` on success, `(None, error_string)` on failure. | `None` — tools requiring agent lookup degrade gracefully |

**Why closed set?** Open `**kwargs` with a documented closed set means:
- Tools only use documented kwargs — no reaching into undocumented internals
- New kwargs can be added in future versions without breaking existing tools
- Tools that don't need wiring simply ignore kwargs: `def get_tools(**kwargs): return [my_simple_tool]`

**Why all optional?** This is the key composability guarantee. A tool file should work (possibly with reduced functionality) regardless of what the host provides. This means:
- Simple tools (no inter-agent features) work with zero kwargs
- Complex tools (cluster_watch) check for required kwargs and degrade gracefully
- The same tool file works in claudechic (full kwargs) and in a minimal test harness (no kwargs)

### 3.3 Return Type: `list[SdkMcpTool]`

Each element must be a function decorated with `@tool` from `claude_agent_sdk`:

```python
from claude_agent_sdk import tool

@tool(
    "my_tool_name",                    # unique tool name
    "Human-readable description.",     # shown to Claude
    {"param1": str, "param2": int},    # input schema
)
async def my_tool(args: dict[str, Any]) -> dict[str, Any]:
    ...
```

The return value is an `SdkMcpTool` instance (the `@tool` decorator wraps the function). These are what `create_sdk_mcp_server(tools=[...])` expects.

### 3.4 Tool Naming Convention

Tool names returned from `mcp_tools/` files should be **globally unique** across all registered tools. Recommended convention:

- Core claudechic tools: `spawn_agent`, `tell_agent`, etc. (short, no prefix)
- Plugin tools from `mcp_tools/`: `cluster_jobs`, `cluster_submit`, etc. (category prefix)

**Name collision handling:** If two tools register the same name, the MCP server will use the last one registered. Discovery sorts files alphabetically, and `mcp_tools/` tools are added after core tools. This means a plugin could theoretically override a core tool — but this is an error, not a feature. The spec does NOT guarantee override semantics. Future versions may warn on collision.

---

## 4. Tool Function Signatures

### 4.1 Required Shape

Every tool function must be:

```python
@tool(name: str, description: str, input_schema: dict | type)
async def tool_name(args: dict[str, Any]) -> dict[str, Any]:
    ...
```

**Key constraints:**
- **Must be async.** The MCP server runs in an asyncio event loop. Use `asyncio.to_thread()` for blocking operations (subprocess, file I/O).
- **Single `args` parameter.** Input comes as a dict matching the `input_schema`. Use `args["key"]` for required params, `args.get("key", default)` for optional.
- **Return MCP response dict.** Must have `"content"` key with list of content items. Use helper pattern (see 4.2).

### 4.2 Response Helper Pattern

Tools should include (or import from a shared `_helpers.py`) these response formatters:

```python
import json
from typing import Any

def _text_response(text: str, *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result

def _json_response(data: Any) -> dict[str, Any]:
    return _text_response(json.dumps(data, indent=2))

def _error_response(text: str) -> dict[str, Any]:
    return _text_response(text, is_error=True)
```

**Note:** These are duplicated from claudechic's `mcp.py` and `cluster.py` intentionally. Tools must NOT import from claudechic — they carry their own response helpers. A shared `mcp_tools/_helpers.py` (underscore-prefixed, skipped by discovery) is the recommended approach for deduplication across tool files within a project.

### 4.3 Factory Pattern for Wired Tools

Tools that need kwargs (caller_name, send_notification, find_agent) use a factory function, exactly as `_make_cluster_watch()` does today:

```python
def get_tools(**kwargs) -> list:
    caller_name = kwargs.get("caller_name")
    send_notification = kwargs.get("send_notification")
    find_agent = kwargs.get("find_agent")

    tools = [simple_tool_a, simple_tool_b]  # no wiring needed

    # Only add wired tools if requirements are met
    tools.append(_make_wired_tool(caller_name, send_notification, find_agent))

    return tools


def _make_wired_tool(caller_name, send_notification, find_agent):
    @tool("wired_tool", "Does something with notifications", {"param": str})
    async def wired_tool(args: dict) -> dict:
        if send_notification is None:
            return _error_response("Notifications not available")
        # ... use send_notification ...
    return wired_tool
```

**Alternative: omit the tool entirely if wiring is absent.**

```python
def get_tools(**kwargs) -> list:
    tools = [simple_tool_a, simple_tool_b]

    # Only register cluster_watch if notification wiring is available
    if kwargs.get("send_notification") and kwargs.get("find_agent"):
        tools.append(_make_cluster_watch(**kwargs))

    return tools
```

Both patterns are valid. The first exposes the tool but returns a clear error. The second hides the tool entirely. Choose based on user experience — if the tool's existence is informative (user knows the feature exists but isn't wired), use the first. If it would just be confusing, use the second.

---

## 5. Error Handling

### 5.1 Failure Modes and Responses

| Failure | Where | Handling |
|---------|-------|----------|
| **Import error** (missing dependency) | Discovery, `exec_module()` | Log WARNING with traceback, skip file, continue |
| **Syntax error** in tool file | Discovery, `exec_module()` | Log WARNING with traceback, skip file, continue |
| **No `get_tools()` function** | Discovery, `getattr()` | Log DEBUG, skip file, continue |
| **`get_tools()` raises exception** | Discovery, function call | Log WARNING with traceback, skip file, continue |
| **`get_tools()` returns non-list** | Discovery | Log WARNING ("expected list, got X"), skip file, continue |
| **Tool function raises at runtime** | MCP handler | Return `_error_response(str(e))` — standard MCP error |
| **Tool function hangs** | MCP handler | MCP server has implicit timeout — returns "stream closed" |

### 5.2 The Iron Rule

**Discovery must never crash.** Every exception during file loading is caught, logged, and skipped. A broken `mcp_tools/experimental_thing.py` must not prevent `mcp_tools/cluster.py` from loading.

This matches the filesystem convention principle: file presence = enabled. If a file is present but broken, it's equivalent to absent (with a warning).

### 5.3 Runtime Error Pattern

Inside tool functions, always catch exceptions and return MCP error responses:

```python
@tool("my_tool", "Does something", {"param": str})
async def my_tool(args: dict) -> dict:
    try:
        result = await asyncio.to_thread(do_thing, args["param"])
        return _json_response(result)
    except Exception as e:
        return _error_response(str(e))
```

Never let exceptions propagate out of a tool function — the MCP protocol requires structured error responses.

---

## 6. Seam Cleanliness Analysis

### 6.1 Current State: cluster.py Imports

The existing `cluster.py` imports from claudechic:

```python
from claude_agent_sdk import tool              # ✅ SDK — acceptable
from claudechic.config import CONFIG           # ❌ claudechic internal
from claudechic.tasks import create_safe_task  # ❌ claudechic internal
```

These are the **only two dirty imports** that need resolution for portability.

### 6.2 Resolution Strategy

| Import | Current Use | v2 Resolution |
|--------|-------------|---------------|
| `claudechic.config.CONFIG` | Read `cluster.ssh_target`, `cluster.watch_poll_interval`, etc. | **Read from tool-local config.** Tool reads its own YAML (`mcp_tools/cluster.yaml` or `~/.claude/.claudechic.yaml`). Config path passed via kwargs or discovered by convention. |
| `claudechic.tasks.create_safe_task` | Fire-and-forget async task for `cluster_watch` | **Replace with `asyncio.create_task()` plus error logging.** The `create_safe_task` wrapper just adds exception logging — a 5-line local helper suffices. |
| `claude_agent_sdk.tool` | Tool decorator | **Keep.** This is the MCP SDK, not claudechic. Any MCP host uses the same SDK. This is infrastructure, not coupling. |

### 6.3 Config Strategy for Portable Tools

**Option A: Tool-local YAML (recommended for v2)**

```python
# Inside mcp_tools/cluster.py
import yaml
from pathlib import Path

def _load_config() -> dict:
    """Load cluster config from standard locations."""
    candidates = [
        Path.cwd() / ".claudechic.yaml",           # project-level
        Path.home() / ".claude" / ".claudechic.yaml",  # user-level
    ]
    for path in candidates:
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
                return data.get("cluster", {})
    return {}
```

**Why this works:** The tool reads config from well-known filesystem locations. It doesn't import claudechic's config machinery. The same config files work whether claudechic loads them or the tool loads them independently. This is the same "filesystem convention" principle applied to configuration.

**Option B: Config passed via kwargs (future consideration)**

```python
def get_tools(**kwargs) -> list:
    config = kwargs.get("config", {}).get("cluster", {})
    return [_make_cluster_tools(config)]
```

This is cleaner but requires the host to provide config. For v2, Option A is preferred because it keeps the tool fully self-contained. Option B could be added later as an override mechanism.

### 6.4 The Portability Test

A properly written `mcp_tools/cluster.py` should pass this test:

```bash
# Copy to a completely different project
cp mcp_tools/cluster.py /other/project/mcp_tools/

# Only requirement: claude_agent_sdk is installed
pip install claude_agent_sdk

# Tool loads and works (reads its own config, has no claudechic imports)
python -c "
from mcp_tools.cluster import get_tools
tools = get_tools()  # no kwargs — still works (reduced functionality)
print(f'{len(tools)} tools loaded')
"
```

### 6.5 Allowed and Forbidden Imports

| Import | Allowed? | Rationale |
|--------|----------|-----------|
| `claude_agent_sdk` | ✅ YES | MCP SDK — the tool protocol itself |
| Python stdlib (`asyncio`, `subprocess`, `pathlib`, etc.) | ✅ YES | Universal |
| PyPI packages (`yaml`, `paramiko`, etc.) | ✅ YES | Declared in project's `pixi.toml` |
| `mcp_tools._helpers` | ✅ YES | Same-directory private helper |
| `claudechic.*` | ❌ NO | Creates coupling to claudechic internals |
| Other `mcp_tools/*.py` (non-underscore) | ❌ NO | Tools must be independent |

---

## 7. Complete Example: cluster.py as mcp_tools/ Plugin

This shows what the ported cluster.py looks like following the v2 contract:

```python
"""LSF cluster tools — mcp_tools plugin.

Drop this file in mcp_tools/ to enable cluster job management.
Config: cluster section in .claudechic.yaml
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from claude_agent_sdk import tool

log = logging.getLogger(__name__)

# ---- Config (self-contained, no claudechic import) ----

def _load_cluster_config() -> dict:
    """Load cluster config from .claudechic.yaml."""
    try:
        import yaml
    except ImportError:
        return {}
    for path in [
        Path.cwd() / ".claudechic.yaml",
        Path.home() / ".claude" / ".claudechic.yaml",
    ]:
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
                return data.get("cluster", {})
    return {}

# ---- Response helpers ----

def _text_response(text, *, is_error=False):
    result = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result

def _json_response(data):
    return _text_response(json.dumps(data, indent=2))

def _error_response(text):
    return _text_response(text, is_error=True)

# ---- Safe task helper (replaces claudechic.tasks.create_safe_task) ----

def _create_safe_task(coro, *, name=None):
    """asyncio.create_task with exception logging."""
    task = asyncio.create_task(coro, name=name)
    def _on_done(t):
        if not t.cancelled() and t.exception():
            log.error("Task %s failed: %s", t.get_name(), t.exception())
    task.add_done_callback(_on_done)
    return task

# ---- Core operations (sync) ----
# ... (same as current cluster.py but using _load_cluster_config()) ...

# ---- Tool definitions ----

@tool("cluster_jobs", "List all running and pending LSF cluster jobs.", {})
async def cluster_jobs(args):
    # ... implementation ...
    pass

# ... other tools ...

# ---- Entry point: the seam contract ----

def get_tools(**kwargs) -> list:
    """Return cluster MCP tools.

    Uses kwargs for notification wiring (cluster_watch).
    All other tools work without kwargs.
    """
    caller_name = kwargs.get("caller_name")
    send_notification = kwargs.get("send_notification")
    find_agent = kwargs.get("find_agent")

    tools = [
        cluster_jobs,
        cluster_status,
        cluster_submit,
        cluster_kill,
        cluster_logs,
    ]

    # cluster_watch needs notification wiring
    tools.append(_make_cluster_watch(caller_name, send_notification, find_agent))

    return tools
```

---

## 8. Testing Strategy

### 8.1 Unit Testing a Tool File in Isolation

```python
# test_cluster_tools.py
import asyncio
import pytest

# Import directly — no claudechic needed
from mcp_tools.cluster import get_tools

class TestDiscovery:
    def test_get_tools_no_kwargs(self):
        """get_tools() works with zero kwargs."""
        tools = get_tools()
        assert isinstance(tools, list)
        assert len(tools) >= 5  # cluster_jobs, status, submit, kill, logs

    def test_get_tools_with_kwargs(self):
        """get_tools() accepts and uses all kwargs."""
        tools = get_tools(
            caller_name="test-agent",
            send_notification=lambda *a, **kw: None,
            find_agent=lambda name: (None, "not found"),
        )
        assert len(tools) >= 6  # includes cluster_watch

    def test_tool_names_unique(self):
        """All returned tools have unique names."""
        tools = get_tools()
        names = [t.name for t in tools]
        assert len(names) == len(set(names))


class TestToolExecution:
    @pytest.fixture
    def tools(self):
        return {t.name: t for t in get_tools()}

    @pytest.mark.asyncio
    async def test_cluster_jobs_returns_mcp_response(self, tools):
        """Tool returns valid MCP response structure."""
        result = await tools["cluster_jobs"]({})
        assert "content" in result
        assert isinstance(result["content"], list)
        assert result["content"][0]["type"] == "text"

    @pytest.mark.asyncio
    async def test_cluster_watch_without_wiring(self):
        """cluster_watch returns error when notifications unavailable."""
        tools = {t.name: t for t in get_tools()}  # no kwargs
        result = await tools["cluster_watch"]({"job_id": "123"})
        assert result.get("isError", False)


class TestKwargsGracefulDegradation:
    def test_missing_send_notification(self):
        """Tools load even without send_notification."""
        tools = get_tools(caller_name="test")
        assert len(tools) > 0

    def test_missing_caller_name(self):
        """Tools load even without caller_name."""
        tools = get_tools(
            send_notification=lambda *a, **kw: None,
            find_agent=lambda name: (None, "not found"),
        )
        assert len(tools) > 0
```

### 8.2 Integration Testing with Discovery

```python
# test_mcp_discovery.py
import tempfile
from pathlib import Path

from claudechic.mcp import discover_mcp_tools  # the ~20-line discovery function

class TestDiscovery:
    def test_empty_directory(self, tmp_path):
        tools = discover_mcp_tools(tmp_path)
        assert tools == []

    def test_nonexistent_directory(self, tmp_path):
        tools = discover_mcp_tools(tmp_path / "nonexistent")
        assert tools == []

    def test_skips_underscore_files(self, tmp_path):
        (tmp_path / "_helpers.py").write_text("def get_tools(): return ['should not load']")
        tools = discover_mcp_tools(tmp_path)
        assert tools == []

    def test_skips_files_without_get_tools(self, tmp_path):
        (tmp_path / "empty.py").write_text("x = 1")
        tools = discover_mcp_tools(tmp_path)
        assert tools == []

    def test_skips_broken_files(self, tmp_path):
        (tmp_path / "broken.py").write_text("raise ImportError('missing dep')")
        (tmp_path / "good.py").write_text("""
from claude_agent_sdk import tool

@tool("good_tool", "A good tool", {})
async def good_tool(args):
    return {"content": [{"type": "text", "text": "ok"}]}

def get_tools(**kwargs):
    return [good_tool]
""")
        tools = discover_mcp_tools(tmp_path)
        assert len(tools) == 1
        assert tools[0].name == "good_tool"

    def test_passes_kwargs_through(self, tmp_path):
        (tmp_path / "echo.py").write_text("""
from claude_agent_sdk import tool

_received_kwargs = {}

@tool("echo_caller", "Echo caller name", {})
async def echo_caller(args):
    return {"content": [{"type": "text", "text": _received_kwargs.get("caller_name", "none")}]}

def get_tools(**kwargs):
    global _received_kwargs
    _received_kwargs = kwargs
    return [echo_caller]
""")
        tools = discover_mcp_tools(tmp_path, caller_name="test-agent")
        assert len(tools) == 1

    def test_skips_non_python_files(self, tmp_path):
        (tmp_path / "README.md").write_text("# Not a tool")
        (tmp_path / "config.yaml").write_text("key: value")
        tools = discover_mcp_tools(tmp_path)
        assert tools == []

    def test_skips_subdirectories(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.py").write_text("def get_tools(**kwargs): return []")
        tools = discover_mcp_tools(tmp_path)
        assert tools == []  # subdirectory not walked

    def test_alphabetical_load_order(self, tmp_path):
        """Files load in sorted order for deterministic behavior."""
        for name in ["z_tool.py", "a_tool.py", "m_tool.py"]:
            (tmp_path / name).write_text(f"""
from claude_agent_sdk import tool

@tool("{name[0]}_tool", "Tool {name[0]}", {{}})
async def the_tool(args):
    return {{"content": [{{"type": "text", "text": "ok"}}]}}

def get_tools(**kwargs):
    return [the_tool]
""")
        tools = discover_mcp_tools(tmp_path)
        assert [t.name for t in tools] == ["a_tool", "m_tool", "z_tool"]
```

### 8.3 Testing Without LSF / Without Cluster

For tools that wrap external systems (LSF, SLURM, etc.), use standard mocking:

```python
@pytest.mark.asyncio
async def test_cluster_submit_builds_correct_bsub(mocker):
    """Verify bsub command construction without actual LSF."""
    mock_run = mocker.patch("mcp_tools.cluster._run_lsf")
    mock_run.return_value = ("Job <12345> submitted", "", 0)

    tools = {t.name: t for t in get_tools()}
    result = await tools["cluster_submit"]({
        "queue": "short",
        "cpus": 4,
        "walltime": "1:00",
        "command": "python train.py",
    })

    assert "12345" in result["content"][0]["text"]
    mock_run.assert_called_once()
    call_cmd = mock_run.call_args[0][0]
    assert "bsub" in call_cmd
    assert "-q short" in call_cmd
```

---

## 9. Compositional Laws

### 9.1 The MCP Tool Protocol Law (restated precisely)

> Every `.py` file in `mcp_tools/` (not starting with `_`) that exposes `get_tools(**kwargs) -> list[SdkMcpTool]` will be discovered and its tools registered. All kwargs are optional. Tools are self-contained — no cross-tool imports, no claudechic imports.

**What this guarantees algebraically:**
- "Does `cluster.py` have `get_tools()`?" YES → it will be discovered
- "Does `custom.py` have `get_tools()`?" YES → it will be discovered
- "Do they conflict?" NO — each returns independent tools
- Therefore: any combination of `mcp_tools/*.py` files composes correctly

### 9.2 The Degradation Law

> A tool file loaded with fewer kwargs than it supports MUST still load without error. Individual tool functions MAY return errors when invoked if required wiring is absent, but `get_tools()` itself MUST NOT raise.

### 9.3 The Isolation Law

> A tool file MUST be testable by importing it directly (`from mcp_tools.cluster import get_tools`) without any claudechic installation. The only required dependency is `claude_agent_sdk`.

---

## 10. Open Questions and Future Considerations

### 10.1 Tool Dependencies Declaration (Future)

Currently there's no way for a tool to declare its pip/conda dependencies. If `cluster.py` needs `pyyaml`, it must be in the project's `pixi.toml`. This is fine for Copier-managed tools (Copier adds the dependency when it copies the file) but limiting for truly drop-in tools.

**Future option:** A `get_requirements()` function or inline metadata (`# requires: pyyaml>=6.0`) that the host could use to validate or auto-install. Not needed for v2.

### 10.2 Tool Lifecycle Hooks (Future)

Some tools may need startup/shutdown hooks (e.g., SSH connection pooling for cluster tools). Currently, initialization happens lazily on first tool call. If this becomes a problem:

**Future option:** Optional `on_startup()` / `on_shutdown()` functions alongside `get_tools()`. Not needed for v2.

### 10.3 Config Schema Validation (Future)

Tools read config from YAML but there's no schema validation. A tool with a typo in its config key silently gets the default. Consider optional config schemas in the future.

### 10.4 Shared Helpers Package

If multiple tool files share significant code (response helpers, SSH utilities), a `mcp_tools/_helpers.py` works for within-project sharing. For cross-project sharing, a PyPI/git-URL package is the right answer. Not needed for v2 — cluster.py is the only tool.

---

## 11. Summary for Parent Specification

**The MCP Tool Protocol seam is compositionally clean.** It follows the established filesystem convention pattern exactly:

1. **Discovery:** Walk `mcp_tools/*.py`, skip `_`-prefixed, call `get_tools(**kwargs)`, flatten results
2. **Contract:** `get_tools(**kwargs) -> list[SdkMcpTool]` — all kwargs optional, graceful degradation
3. **Tool shape:** `@tool(name, desc, schema)` decorator on `async def fn(args) -> dict`
4. **Error handling:** Never crash — log and skip broken files
5. **Seam cleanliness:** Tools must not import from claudechic. Config read from filesystem. `claude_agent_sdk` is the only required dependency.
6. **Testing:** Tools testable in isolation by importing directly and mocking kwargs

**The only migration work** for cluster.py is replacing two claudechic imports (`CONFIG` → local YAML reader, `create_safe_task` → local 5-line helper). Everything else in the existing implementation already follows the right patterns.

**Discovery code:** ~30 lines in claudechic's `mcp.py`. This is the entire framework — there is no framework. The directory convention IS the plugin system.
