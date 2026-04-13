# interrupt_agent

## Vision
Add an `interrupt_agent` MCP tool that lets one agent interrupt another mid-task and optionally redirect it with a new prompt. Implements GitHub Issue #10.

## Status: SIGN-OFF (APPROVED)
- All 6 agents confirmed READY
- 724 tests passed, 0 regressions
- Phase: sign-off (project-team workflow)

## Commit Plan
### Step 1: Claudechic submodule (commit to main)
- Branch: fix/code-quality-audit-cleanup -> merge into main
- Files: mcp.py, test_mcp_interrupt_agent.py, test_autocomplete.py, test_hints_integration.py, pyproject.toml, analytics.md, CLAUDE.md

### Step 2: Parent repo (commit to develop, then merge to main)
- Branch: develop -> merge into main
- Files: docs/getting-started.md, template/CLAUDE.md.jinja, submodule pointer
- .project_team/interrupt_agent/ stays on develop only (blocked on main by pre-commit hook)

## Files Changed

### submodules/claudechic/
- claudechic/mcp.py -- interrupt_agent tool (~80 lines, factory pattern)
- tests/test_mcp_interrupt_agent.py -- 11 tests (NEW)
- tests/test_autocomplete.py -- fixed pre-existing fuzzy match failures
- tests/test_hints_integration.py -- fixed pre-existing broken hints test
- pyproject.toml -- registered integration marker
- .ai-docs/analytics.md -- added interrupt_agent to tracked tools
- CLAUDE.md -- added Inter-Agent Communication section

### Parent repo
- docs/getting-started.md -- added interrupt_agent to MCP tools list
- template/CLAUDE.md.jinja -- added Inter-Agent Communication section
- .project_team/interrupt_agent/ -- project state (develop only)

## Agents
- Composability: READY
- Terminology: READY
- Skeptic: READY
- UserAlignment: READY
- Implementer: READY
- TestEngineer: READY
