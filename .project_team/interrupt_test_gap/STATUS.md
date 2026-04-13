# interrupt_test_gap

## Vision
Investigate why interrupt_agent tests pass (724 tests, 0 regressions) while the feature is broken for real TUI users (issue #32). Identify the testing gap patterns and close them.

## Status: SIGN-OFF (APPROVED)
- All 6 agents confirmed READY
- 390 tests passed (22 interrupt + 368 regression), 0 failures
- TUI manual test confirmed both bugs fixed
- Phase: sign-off (project-team workflow)

## Files Changed

### submodules/claudechic/
- claudechic/mcp.py -- Fix A (fire-and-forget redirect) + Fix B (status allowlist)
- claudechic/agent.py -- Fix B addendum (pending_prompts.clear in interrupt)
- tests/test_mcp_interrupt_agent.py -- Updated 5 tests for fire-and-forget behavior
- tests/test_interrupt_agent_integration.py -- 11 NEW integration tests with real Agent
- tests/conftest.py -- Added real_agent_with_mock_sdk fixture
- pyproject.toml -- Registered slow marker

## Agents
- Composability: READY
- Skeptic: READY
- Terminology: READY
- UserAlignment: READY
- Impl-Fixes: READY
- Impl-Tests: READY
