# Project Status

**EVERY TURN: Re-read AI_agents/project_team/COORDINATOR.md**

## Current Phase
Phase 4: Implementation

## Vision (from Phase 0)
**Goal:** Write the architecture specification for a Workflow Guidance System — infrastructure in claudechic that lets workflows define phases, guardrail rules, checks, and hints via YAML manifests and markdown files.

**Value:** Unifies currently scattered guidance (rules, checks, hints) into one system — YAML manifests + markdown content in `global/` and `workflows/`. Users get a single pattern and a clear 2x2 mental model (advisory/enforced x positive/negative).

**Domain terms:** Manifests, phases, checks, hints, guardrails, SDK hooks, agent folders, ManifestSection protocol, 2x2 guidance framing, enforcement levels (deny/user_confirm/warn/log)

**Success looks like:** A complete architecture specification that a team can implement — covering the unified manifest loader, workflow engine, check protocol, agent folders, phase-scoped evaluation, and `/compact` recovery. The project-team workflow is the first workflow built on it.

**Failure looks like:** A spec that's too vague to implement, misses the interaction between subsystems (e.g., how checks bridge to hints, how phase transitions gate on checks), or fails to identify which existing claudechic code needs to change and how (refactors, new modules, modified interfaces).

## Implementation Plan

6 Implementer agents, grouped by package (dependency order: leaf packages first, orchestration second, integration last):

| Agent | Package | Files | Dependencies |
|-------|---------|-------|-------------|
| Impl-Guardrails | `guardrails/` | tokens.py, hits.py, hooks.py, rules.py mods, __init__.py | Leaf — stdlib only |
| Impl-Checks | `checks/` | __init__.py, protocol.py, builtins.py, adapter.py | Leaf — protocol.py stdlib, adapter imports hints/types |
| Impl-Hints | `hints/` | __init__.py, types.py, engine.py, state.py | Leaf — stdlib only |
| Impl-WorkflowLoader | `workflows/` loader side | __init__.py, loader.py, phases.py | Imports from checks/, hints/, guardrails/ |
| Impl-WorkflowEngine | `workflows/` runtime | engine.py, agent_folders.py | Imports from checks/, hints/, workflows/phases |
| Impl-Integration | app.py + mcp.py | app.py mods, mcp.py new tools | Imports from all packages |

## Leadership Spawn Evidence
- Composability: spawned ✓
- TerminologyGuardian: spawned ✓
- Skeptic: spawned ✓
- UserAlignment: spawned ✓

## Agents Active
- (Spawning for Phase 4)

## Completed
- Phase 0: Vision confirmed ✓
- Phase 1: Setup complete ✓
- Phase 2: Leadership spawned ✓
- Phase 3: Specification approved ✓ (SPECIFICATION.md + APPENDIX.md finalized)
