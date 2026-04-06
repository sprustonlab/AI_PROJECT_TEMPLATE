# Project Status

**EVERY TURN: Re-read AI_agents/project_team/COORDINATOR.md**

## Current Phase
Phase 8: E2E Checkpoint — User hands-on walkthrough of /tutorial workflow

## Vision (from Phase 0)
**Goal:** Write the architecture specification for a Workflow Guidance System — infrastructure in claudechic that lets workflows define phases, guardrail rules, checks, and hints via YAML manifests and markdown files.

**Value:** Unifies currently scattered guidance (rules, checks, hints) into one system — YAML manifests + markdown content in `global/` and `workflows/`. Users get a single pattern and a clear 2x2 mental model (advisory/enforced x positive/negative).

**Domain terms:** Manifests, phases, checks, hints, guardrails, SDK hooks, agent folders, ManifestSection protocol, 2x2 guidance framing, enforcement levels (deny/user_confirm/warn/log)

**Success looks like:** A complete architecture specification that a team can implement — covering the unified manifest loader, workflow engine, check protocol, agent folders, phase-scoped evaluation, and `/compact` recovery. The project-team workflow is the first workflow built on it.

**Failure looks like:** A spec that's too vague to implement, misses the interaction between subsystems (e.g., how checks bridge to hints, how phase transitions gate on checks), or fails to identify which existing claudechic code needs to change and how (refactors, new modules, modified interfaces).

## Next Steps
1. User restarts claudechic and runs `/tutorial` to manually verify all features
2. Fix any issues found during walkthrough
3. Phase 9: Final sign-off

## Workflows Ready
- `/tutorial` — 4-phase guided walkthrough of all features (basics → rules → checks → graduation)
- `/project-team` — 7-phase multi-agent workflow (vision → setup → leadership → specification → implementation → testing → signoff)

## Implementation Plan

6 Implementer agents, grouped by package (dependency order: leaf packages first, orchestration second, integration last):

| Agent | Package | Files | Dependencies |
|-------|---------|-------|-------------|
| Impl-Guardrails | `guardrails/` | tokens.py, hits.py, hooks.py, parsers.py, rules.py mods | Leaf — stdlib only |
| Impl-Checks | `checks/` | protocol.py, builtins.py, adapter.py, parsers.py | Leaf — protocol.py stdlib, adapter imports hints/types |
| Impl-Hints | `hints/` | types.py, engine.py, state.py, parsers.py | Leaf — stdlib only |
| Impl-WorkflowLoader | `workflows/` loader side | __init__.py, loader.py, phases.py, parsers.py | Imports from checks/, hints/, guardrails/ |
| Impl-WorkflowEngine | `workflows/` runtime | engine.py, agent_folders.py | Imports from checks/, hints/, workflows/phases |
| Impl-Integration | app.py + mcp.py + commands.py | app.py mods, mcp.py new tools, commands.py routing | Imports from all packages |

## Completed
- Phase 0: Vision confirmed ✓
- Phase 1: Setup complete ✓
- Phase 2: Leadership spawned ✓
- Phase 3: Specification approved ✓ (SPECIFICATION.md + APPENDIX.md finalized)
- Phase 4: Implementation complete ✓
  - All new modules created (tokens.py, hits.py, hooks.py, protocol.py, builtins.py, adapter.py, types.py, engine.py, state.py, loader.py, phases.py, agent_folders.py, engine.py)
  - All ManifestSection parsers implemented (guardrails/parsers.py, checks/parsers.py, hints/parsers.py, workflows/parsers.py)
  - Parser registration wired into app.py via register_default_parsers()
  - End-to-end parser integration verified
  - app.py and mcp.py integration layers complete
  - Bugs fixed: B1 (should_skip_for_phase), SEC1 (enforcement-tagged tokens), B1 (stale get_phase), B1 (qualified phase ID as filename), C1 (wf_data.manifest), M1 (injection namespace filter), M1 (parser crash protection)
- Phase 5: Testing complete ✓
  - 24/24 E2E intent-based tests passing in ~5s
  - Real ChatApp + DOM inspection (not unit tests)
  - Critical safety properties tested: R2 fail-closed, SEC1 token isolation
  - 5 test files: loading, guardrails, phases, activation, hits logging
- Phase 6: Sign-off complete ✓
  - All 4 Leadership confirmed READY: Composability, Skeptic, Terminology, UserAlignment
- Phase 7: Integration complete ✓
  - Created workflow content: project-team (7 phases, 6 roles, 17 markdown files) + tutorial (4 phases, 1 role, 5 markdown files)
  - Created global guidance: global/rules.yaml (3 rules) + global/hints.yaml (2 hints)
  - Both workflows parse with 0 errors: 8 rules, 1 injection, 14 hints, 11 phases
