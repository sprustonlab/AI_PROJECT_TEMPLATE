"""Test that ask_agent properly injects sender identity."""

import asyncio

import pytest
from claudechic.mcp import _make_ask_agent, set_app


class MockAgent:
    def __init__(self, name: str):
        self.name = name
        self.id = name
        self.session_id = f"session-{name}"
        self.cwd = "/tmp"
        self.status = "idle"
        self.worktree = None
        self.client = True  # truthy
        self.received_prompt = None

    @property
    def analytics_id(self) -> str:
        return self.session_id or self.id

    async def send(self, prompt: str) -> None:
        self.received_prompt = prompt


class MockAgentManager:
    def __init__(self):
        self.agents: dict[str, MockAgent] = {}
        self.active: MockAgent | None = None

    def add(self, agent: MockAgent) -> None:
        self.agents[agent.name] = agent
        if self.active is None:
            self.active = agent

    def find_by_name(self, name: str) -> MockAgent | None:
        return self.agents.get(name)

    def __len__(self) -> int:
        return len(self.agents)


class MockApp:
    def __init__(self):
        self.agent_mgr = MockAgentManager()

    def run_worker(self, coro):
        """Mock run_worker - close the coroutine to avoid RuntimeWarning."""
        coro.close()


@pytest.fixture
def mock_app():
    app = MockApp()
    set_app(app)  # type: ignore
    return app


@pytest.mark.asyncio
async def test_ask_agent_injects_sender(mock_app):
    """When agent 'alice' asks agent 'bob' a question, bob should see it's from alice."""
    alice = MockAgent("alice")
    bob = MockAgent("bob")
    mock_app.agent_mgr.add(alice)
    mock_app.agent_mgr.add(bob)

    # Create ask_agent tool bound to alice
    ask_agent = _make_ask_agent(caller_name="alice")

    # Call the handler directly
    await ask_agent.handler({"name": "bob", "prompt": "What's the weather?"})

    # Let the event loop run the fire-and-forget task
    await asyncio.sleep(0)

    # Bob should have received the prompt with alice's identity and reply instruction
    assert bob.received_prompt is not None
    assert "[Question from agent 'alice'" in bob.received_prompt
    assert "please respond back using tell_agent" in bob.received_prompt
    assert "What's the weather?" in bob.received_prompt


@pytest.mark.asyncio
async def test_ask_agent_without_sender(mock_app):
    """When no sender is specified (legacy), prompt should pass through unchanged."""
    bob = MockAgent("bob")
    mock_app.agent_mgr.add(bob)

    # Create ask_agent tool without caller name
    ask_agent = _make_ask_agent()

    await ask_agent.handler({"name": "bob", "prompt": "What's the weather?"})

    # Let the event loop run the fire-and-forget task
    await asyncio.sleep(0)

    # Without sender, prompt should be unchanged
    assert bob.received_prompt == "What's the weather?"


@pytest.mark.asyncio
async def test_ask_agent_nonexistent_returns_error(mock_app):
    """Asking a non-existent agent should return an error with isError=True."""
    alice = MockAgent("alice")
    mock_app.agent_mgr.add(alice)

    ask_agent = _make_ask_agent(caller_name="alice")

    # Ask a non-existent agent
    result = await ask_agent.handler({"name": "ghost", "prompt": "Hello?"})

    # Should return error response with isError flag
    assert result["isError"] is True
    assert "ghost" in result["content"][0]["text"]
    assert "not found" in result["content"][0]["text"]
