# Research Report: E2E Testing for Claudechic — Terminal TUI Testing

**Requested by:** Coordinator
**Date:** 2026-03-30
**Tier of best source found:** T1 (official Textual docs, official Claude Agent SDK docs, MCP protocol docs)

## Query

What are the options for end-to-end testing of claudechic (a Textual-based TUI that uses Claude Agent SDK and MCP tools)? We need the terminal app equivalent of Playwright for web apps.

---

## 1. Testing Layers

The E2E testing problem has distinct layers, each with different tools:

```
Layer 5: Full user journey (copier → pixi install → claudechic → agent workflow)
Layer 4: TUI interaction (start app, press keys, verify screen output)
Layer 3: MCP tool testing (call cluster_submit, verify response)
Layer 2: Agent SDK integration (connect client, send prompt, get response)
Layer 1: Unit testing (parsers, command builders, helpers)
```

Claudechic's existing test suite (22 test files) covers **Layer 1** well. The gap is **Layers 2-5**.

### What Already Exists in Claudechic

| Test File | Layer | What It Tests |
|-----------|-------|---------------|
| `test_cluster.py` (1128 lines!) | L1 | All parsers, command builders, SSH dispatch, watch mechanism — with mocked subprocess |
| `test_mcp_ask_agent.py` | L1-L2 | MCP ask_agent with MockAgent/MockApp — tests message routing |
| `test_app.py` | L1 | Image attachment building (no TUI interaction) |
| `test_app_ui.py` | L4? | Likely TUI tests — needs investigation |
| `test_widgets.py` | L4? | Widget tests — needs investigation |
| Others | L1 | Config, sessions, diff, autocomplete, file index, etc. |

The MockAgent/MockApp pattern in `test_mcp_ask_agent.py` is a solid foundation for Layer 2-3 testing without requiring the full TUI.

---

## 2. Tool Evaluation

### Tool 1: Textual's `App.run_test()` + Pilot API (T1 — Official Textual)

**URL:** https://textual.textualize.io/guide/testing/
**License:** MIT ✅
**Tests:** Textual uses this extensively for its own 500+ tests ✅

#### How It Works

```python
@pytest.mark.asyncio
async def test_app_starts():
    app = ChatApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # App is running headlessly — no terminal output
        await pilot.pause()  # Let app initialize

        # Query widgets
        footer = app.query_one(StatusFooter)
        assert footer is not None

        # Simulate keyboard input
        await pilot.press("ctrl+c")  # or any key sequence

        # Simulate clicks
        await pilot.click("#some-widget")
```

#### Pilot Methods Available

| Method | What It Does |
|--------|-------------|
| `await pilot.press(*keys)` | Simulate key presses ("enter", "ctrl+a", "h", "e", "l", "l", "o") |
| `await pilot.click(selector, offset, times)` | Click a widget by CSS selector, class, or ID |
| `await pilot.pause(delay)` | Wait for pending messages to process |
| `await pilot.resize_terminal(width, height)` | Resize the virtual terminal |
| `await pilot.hover(selector, offset)` | Hover over a widget |

#### Configuration

```python
async with app.run_test(size=(100, 50)) as pilot:
    # size=(columns, rows) — default is 80×24
```

#### Evaluation

| Criterion | Assessment |
|-----------|-----------|
| **Setup complexity** | 🟢 Low — just `async with app.run_test()`. No external processes |
| **Reliability** | 🟢 High — deterministic, no timing issues (everything is async/await) |
| **CI compatibility** | ✅ Perfect — headless, no terminal needed, works in GitHub Actions |
| **Closeness to real UX** | 🟡 Medium — tests the Textual widget tree and message handling, but NOT the actual terminal rendering |
| **Can test claudechic?** | ⚠️ **Depends** — ChatApp requires Claude Agent SDK (subprocess connection). Would need to mock the SDK client or use the MockAgent pattern |

#### Key Challenge for Claudechic

The main issue: `ChatApp` immediately tries to connect to the Claude Agent SDK (which spawns a Claude Code subprocess). For headless testing, we need to either:

1. **Mock the SDK connection** — patch `agent.connect()` to return a mock client
2. **Use the existing MockAgent/MockApp pattern** — test MCP tools and agent routing without the TUI
3. **Create a test-mode flag** — skip SDK connection, allow testing of pure UI logic

**Recommendation:** This is the **primary tool for Layer 4 testing**. But it needs a mock SDK layer underneath.

---

### Tool 2: pytest-textual-snapshot (T3 — Textualize official)

**URL:** https://github.com/Textualize/pytest-textual-snapshot
**License:** MIT ✅

#### How It Works

```python
def test_app_snapshot(snap_compare):
    assert snap_compare("path/to/app.py", press=["1", "2"], terminal_size=(120, 40))
```

Captures SVG screenshots of the terminal output and compares against stored baselines. Failed tests show visual diffs.

#### Evaluation

| Criterion | Assessment |
|-----------|-----------|
| **Setup complexity** | 🟢 Low — `pip install pytest-textual-snapshot` |
| **Reliability** | 🟡 Medium — snapshots break on any visual change (font, color, widget size). Harlequin devs note they are "a pain to maintain" |
| **CI compatibility** | ✅ Works in CI, stores SVGs in git |
| **Closeness to real UX** | ✅ High — captures exactly what the user would see |
| **Use case** | Visual regression testing — catch unintended UI changes |

**Recommendation:** Useful as a **supplement** for visual regression, not as primary E2E testing. Too brittle for active development.

---

### Tool 3: pexpect (T5 — Well-maintained community)

**URL:** https://github.com/pexpect/pexpect
**License:** ISC ✅
**Tests:** Yes ✅
**Stars:** 2.5k+

#### How It Works

```python
import pexpect

child = pexpect.spawn("claudechic")
child.expect("Welcome")          # Wait for output
child.sendline("/agent create researcher")  # Type command
child.expect("Created agent")    # Verify response
child.sendline("ctrl+c")
child.close()
```

#### Evaluation

| Criterion | Assessment |
|-----------|-----------|
| **Setup complexity** | 🟢 Low — `pip install pexpect` |
| **Reliability** | 🟡 Medium — timing-dependent. TUI apps have complex escape sequences that confuse expect patterns |
| **CI compatibility** | ✅ Works on Linux/macOS. ❌ Not on Windows (needs `wexpect` fork) |
| **Closeness to real UX** | ✅ **Highest** — actually spawns the real process, real terminal, real everything |
| **Can test claudechic?** | ⚠️ Tricky — claudechic uses Textual's terminal rendering with escape codes, alternate screen, etc. Pattern matching against TUI output is fragile |

**Key limitation for TUI apps:** pexpect matches byte streams. Textual apps output ANSI escape sequences, cursor positioning, alternate screen buffers — the raw output doesn't look like what the user sees. Matching "Welcome" in a Textual app means matching through layers of escape codes.

**Recommendation:** **Best for Layer 5** (end-to-end journey testing where you just need to verify the process starts and doesn't crash). **Not suitable for Layer 4** (detailed TUI interaction testing) — use Textual's Pilot API instead.

---

### Tool 4: microsoft/tui-test (T3 — Microsoft official)

**URL:** https://github.com/microsoft/tui-test
**License:** MIT ✅
**Stars:** New (March 2026)

#### How It Works

TypeScript/Node.js framework using xterm.js to render terminals:

```typescript
test("app starts", async ({ terminal }) => {
  terminal.write("claudechic\n");
  await expect(terminal.getByText("Welcome")).toBeVisible();
});
```

#### Evaluation

| Criterion | Assessment |
|-----------|-----------|
| **Setup complexity** | 🔴 High — requires Node.js, npm install, TypeScript |
| **Reliability** | 🟢 High — auto-waiting, xterm.js rendering (sees what user sees) |
| **CI compatibility** | ✅ Multi-platform including Windows |
| **Closeness to real UX** | ✅ Very high — renders actual terminal output via xterm.js |
| **Language mismatch** | 🔴 TypeScript — claudechic is Python. Different test ecosystem |

**Recommendation:** **Not recommended.** Excellent tool, but wrong language ecosystem. The overhead of maintaining TypeScript tests for a Python project is not justified. If we needed Windows terminal testing, this would be worth reconsidering.

---

### Tool 5: textual-mcp-server (T5 — Community)

**URL:** https://pypi.org/project/textual-mcp-server/
**License:** MIT ✅

#### How It Works

An MCP server that launches Textual apps headlessly and exposes tools:
- `textual_launch` — start an app
- `textual_snapshot` — get widget tree + focus info
- `textual_click` — click elements
- `textual_screenshot` — capture visual output
- `textual_stop` — cleanup

#### Evaluation

| Criterion | Assessment |
|-----------|-----------|
| **Setup complexity** | 🟡 Medium — requires MCP client to drive it |
| **Reliability** | 🟡 Unknown — new project |
| **Relevance** | ⚠️ Designed for AI agents to interact with Textual apps, not for CI testing |

**Recommendation:** Interesting concept but overkill for testing. The Pilot API does everything this does, more simply.

---

### Tool 6: mcptools CLI (T5 — Community, well-documented)

**URL:** https://github.com/f/mcptools
**License:** MIT ✅

#### How It Works

Command-line tool for testing MCP servers directly:

```bash
# List tools from an MCP server
mcp tools --server "python -m claudechic.mcp_server"

# Call a tool
mcp call cluster_jobs --server "python -m claudechic.mcp_server"

# Mock server for testing clients
mcp mock --tools '[{"name": "cluster_jobs", "response": "[]"}]'
```

#### Evaluation

| Criterion | Assessment |
|-----------|-----------|
| **Setup complexity** | 🟢 Low — npm install or binary download |
| **Reliability** | 🟢 High — tests the actual JSON-RPC protocol |
| **CI compatibility** | ✅ CLI tool, works in any CI |
| **Use case** | Perfect for **Layer 3** — verify MCP tools are registered and respond correctly |

**Recommendation:** ✅ **Use for Layer 3 testing** — verify that MCP tools are discoverable and return correct responses. Can be part of CI.

**However:** Claudechic's MCP server is in-process (not standalone). We'd need to either:
1. Extract the MCP tool definitions into a testable module (we're already doing this with `mcp_tools/`)
2. Or test via the MockApp pattern (like test_mcp_ask_agent.py)

---

### Tool 7: Direct Python MCP Testing (MockApp Pattern)

This is what claudechic already does in `test_mcp_ask_agent.py`:

```python
class MockAgent:
    def __init__(self, name):
        self.name = name
        self.received_prompt = None
    async def send(self, prompt):
        self.received_prompt = prompt

class MockApp:
    def __init__(self):
        self.agent_mgr = MockAgentManager()

@pytest.fixture
def mock_app():
    app = MockApp()
    set_app(app)
    return app

@pytest.mark.asyncio
async def test_tool(mock_app):
    tool = _make_spawn_agent(caller_name="alice")
    result = await tool.handler({"name": "bob", "path": "/tmp", "prompt": "hi"})
    assert "Created agent" in result["content"][0]["text"]
```

#### Evaluation

| Criterion | Assessment |
|-----------|-----------|
| **Setup complexity** | 🟢 Zero — pure Python, no external tools |
| **Reliability** | 🟢 Very high — deterministic, no subprocess, no timing |
| **CI compatibility** | ✅ Perfect |
| **Closeness to real UX** | 🟡 Low — tests MCP handlers directly, not the full request flow |
| **Coverage** | ✅ Tests all MCP tool logic, agent routing, error handling |

**Recommendation:** ✅ **Primary tool for Layer 2-3 testing.** Already proven in the codebase. Extend this pattern for cluster tools, mcp_tools/ discovery, etc.

---

## 3. Recommended Testing Strategy by Layer

### Layer 1: Unit Tests (EXISTING — extend)

**Tools:** pytest + unittest.mock
**What to test:** Parsers, command builders, config resolution, log path resolution
**Already exists:** test_cluster.py (1128 lines), test_config.py, test_sessions.py, etc.
**For v2:** Add SLURM parser tests alongside existing LSF parser tests

### Layer 2: MCP Tool Integration (EXISTING — extend)

**Tools:** pytest + MockApp/MockAgent pattern
**What to test:** MCP tool handlers, agent message routing, spawn/close/ask/tell lifecycle
**Already exists:** test_mcp_ask_agent.py
**For v2 additions:**
- Test `mcp_tools/` discovery (`get_tools()` called, tools registered)
- Test cluster tools via MockApp (cluster_submit → verify command built correctly)
- Test `requires_answer` nudge flow (upstream feature)
- Test agent soft-close/reopen (upstream feature)

```python
# Example: Test mcp_tools discovery
async def test_cluster_tools_discovered():
    """Verify cluster.py's get_tools() returns expected tool set."""
    from mcp_tools.cluster import get_tools
    tools = get_tools()
    tool_names = {t.name for t in tools}
    assert "cluster_jobs" in tool_names
    assert "cluster_submit" in tool_names
    assert "cluster_watch" in tool_names
```

### Layer 3: MCP Protocol Testing (NEW)

**Tools:** mcptools CLI OR direct JSON-RPC testing
**What to test:** Tools are discoverable, schema is correct, responses conform to MCP spec

**Option A: mcptools CLI in CI**
```bash
# In CI pipeline
mcp tools --server "python -c 'from mcp_tools.cluster import get_tools; ...'"
mcp call cluster_jobs --params '{}' --server "..."
```

**Option B: Python JSON-RPC testing**
```python
async def test_mcp_protocol_compliance():
    """Verify tool responses conform to MCP JSON-RPC format."""
    from mcp_tools.cluster import cluster_jobs
    response = await cluster_jobs.handler({})
    assert "content" in response
    assert isinstance(response["content"], list)
    assert response["content"][0]["type"] == "text"
```

**Recommendation:** Option B is simpler and doesn't require external tools. Use it.

### Layer 4: TUI Interaction (NEW — optional)

**Tools:** Textual `App.run_test()` + Pilot API
**What to test:** App launches, widgets render, keyboard shortcuts work, agent tabs switch

**Challenge:** Requires mocking the Claude Agent SDK. The app can't connect to a real Claude Code process in CI.

**Proposed approach:**

```python
class TestChatApp(ChatApp):
    """Test-mode ChatApp that skips SDK connection."""

    async def _connect_initial_client(self):
        """Override to create a mock agent instead of real SDK connection."""
        agent = Agent(name="test", cwd=Path.cwd())
        self.agent_mgr.agents[agent.id] = agent
        self.agent_mgr.active_id = agent.id

@pytest.mark.asyncio
async def test_app_launches():
    app = TestChatApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        # Verify the app is running
        assert app.agent_mgr is not None
        assert len(app.agent_mgr) >= 1

@pytest.mark.asyncio
async def test_keyboard_shortcuts():
    app = TestChatApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+1")  # Switch to agent 1
        # ... verify agent switched
```

**Effort:** Medium. Requires creating TestChatApp with mock SDK. ~200 lines of test infrastructure + individual test cases.

**Recommendation:** Worth doing for critical UI paths (app launch, agent switching, /commands). Not needed for every widget.

### Layer 5: Full E2E Journey (NEW — smoke test)

**Tools:** pexpect (Linux/macOS) or shell script
**What to test:** copier → pixi install → claudechic starts without crashing

**This is a smoke test, not a detailed test.** It verifies the entire toolchain works.

```python
import pexpect
import tempfile
import os

def test_full_journey():
    """Smoke test: template → project → claudechic starts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = os.path.join(tmpdir, "test-project")

        # Step 1: Create project from template
        child = pexpect.spawn(
            f"pixi exec --spec copier copier copy --trust "
            f"--defaults https://github.com/sprustonlab/AI_PROJECT_TEMPLATE {project_dir}",
            timeout=120
        )
        child.expect(pexpect.EOF)
        assert child.exitstatus == 0

        # Step 2: Install dependencies
        child = pexpect.spawn(f"pixi install", cwd=project_dir, timeout=300)
        child.expect(pexpect.EOF)
        assert child.exitstatus == 0

        # Step 3: Verify claudechic is importable
        child = pexpect.spawn(
            f"pixi run python -c 'import claudechic; print(\"OK\")'",
            cwd=project_dir, timeout=30
        )
        child.expect("OK")
        assert child.exitstatus == 0
```

**CI note:** This test requires internet access (pixi install downloads packages). Run as a scheduled/nightly test, not on every PR.

**Recommendation:** Implement as a **separate CI job** that runs weekly. Don't block PRs on this.

---

## 4. Testing the MCP Tools Seam Specifically

For v2, the key testable contract is: **`mcp_tools/*.py` files with `get_tools()` are discovered and registered.**

```python
# test_mcp_discovery.py

import importlib
from pathlib import Path

def test_mcp_tools_discovery():
    """All .py files in mcp_tools/ with get_tools() are loadable."""
    mcp_dir = Path("mcp_tools")
    for py_file in mcp_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        module_name = f"mcp_tools.{py_file.stem}"
        module = importlib.import_module(module_name)
        assert hasattr(module, "get_tools"), f"{module_name} missing get_tools()"
        tools = module.get_tools()
        assert isinstance(tools, list), f"{module_name}.get_tools() must return list"
        for tool in tools:
            assert hasattr(tool, "name"), f"Tool in {module_name} missing .name"

def test_cluster_tools_schema():
    """Cluster tools have correct MCP-compatible schemas."""
    from mcp_tools.cluster import get_tools
    tools = {t.name: t for t in get_tools()}

    submit = tools["cluster_submit"]
    # Verify required parameters exist
    assert "queue" in submit.schema["properties"]
    assert "command" in submit.schema["properties"]
```

---

## 5. Summary: Recommended E2E Testing Stack

| Layer | Tool | Priority | Effort | CI? |
|-------|------|----------|--------|-----|
| **L1: Unit** | pytest + mock (existing) | ✅ Already done | Extend | ✅ Every PR |
| **L2: MCP tool integration** | MockApp/MockAgent pattern (existing) | 🔴 High — extend | Low | ✅ Every PR |
| **L3: MCP protocol** | Direct Python testing | 🟡 Medium | Low | ✅ Every PR |
| **L4: TUI interaction** | Textual `run_test()` + Pilot | 🟡 Medium | Medium (~200 lines infra) | ✅ Every PR |
| **L5: Full journey** | pexpect smoke test | 🟢 Low | Medium | ⚠️ Weekly/nightly |
| **Visual regression** | pytest-textual-snapshot | 🟢 Optional | Low | ⚠️ On UI changes |

### What NOT to Use

| Tool | Why Not |
|------|---------|
| **microsoft/tui-test** | TypeScript — wrong ecosystem for Python project |
| **textual-mcp-server** | Over-engineered for testing; Pilot API does the same thing simpler |
| **Playwright** | Web testing tool — doesn't drive terminals. Would need a web terminal emulator layer, massive overkill |
| **tmux scripting** | Brittle, hard to maintain, pexpect is better for everything tmux scripts do |
| **Selenium** | Web only — not applicable |

### Implementation Priority for v2

1. **Extend MockApp pattern** for new MCP tools (cluster, mcp_tools/ discovery) — builds on existing infrastructure
2. **Add mcp_tools/ discovery tests** — verify the seam contract
3. **Create TestChatApp** with mocked SDK for Layer 4 tests — one-time investment
4. **Add pexpect smoke test** as a separate CI job — catches integration failures
5. **Consider snapshot tests** only after UI stabilizes

---

## Sources

- [Textual Testing Guide](https://textual.textualize.io/guide/testing/) — T1, official Textual docs
- [Textual Pilot API](https://textual.textualize.io/api/pilot/) — T1, official API reference
- [pytest-textual-snapshot](https://github.com/Textualize/pytest-textual-snapshot) — T3, Textualize official. MIT ✅
- [Harlequin testing discussion](https://github.com/tconbeer/harlequin/discussions/551) — T6, real-world experience with Textual testing
- [pexpect](https://github.com/pexpect/pexpect) — T5, 2.5k+ stars, ISC license ✅, tests ✅
- [microsoft/tui-test](https://github.com/microsoft/tui-test) — T3, Microsoft official. MIT ✅
- [mcptools CLI](https://github.com/f/mcptools) — T5, MIT ✅, MCP testing CLI
- [MCP protocol specification](https://modelcontextprotocol.io/docs/learn/architecture) — T1, official MCP docs
- [Claude Agent SDK Python](https://github.com/anthropics/claude-agent-sdk-python) — T3, Anthropic official
- [textual-mcp-server](https://pypi.org/project/textual-mcp-server/) — T5, community MCP+Textual bridge
- Direct analysis of claudechic test suite at `/groups/spruston/home/moharb/DECODE-PRISM/Repos/claudechic/tests/` — T1

## Not Recommended (and why)

| Tool/Approach | Why Rejected |
|---------------|-------------|
| **Playwright** | Web testing only — no terminal support |
| **Selenium** | Web testing only |
| **microsoft/tui-test** | TypeScript ecosystem — language mismatch with Python project |
| **tmux scripting** | Brittle, hard to maintain, pexpect is strictly better |
| **Record/replay tools** | Terminal recordings are fragile across versions and environments |
| **Full Docker-based integration tests** | Too heavy for PR-level testing; reserve for nightly |
