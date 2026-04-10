# Project Status

**EVERY TURN: Re-read AI_agents/project_team/COORDINATOR.md**

## Current Phase
Phase 9: Live Testing

## Vision (from Phase 0)
**Goal:** Build a contextual onboarding & feature discovery system for AI_PROJECT_TEMPLATE projects that surfaces helpful hints via ClaudeChic's toast notifications, helping users discover and use the template's features (guardrails, project team, pattern miner, MCP tools, cluster support).

**Value:** Users install the template and get a project with many powerful features, but may not know what's available or when to use them. Contextual hints at the right moment bridge the gap between installation and mastery.

## What Was Built

### Source Files
| File | Purpose |
|------|---------|
| `hints/__init__.py` | Public API: `evaluate()` — single entry point called by ClaudeChic |
| `hints/_types.py` | Protocols (TriggerCondition, HintLifecycle), lifecycle policies, HintSpec, HintRecord |
| `hints/_state.py` | CopierAnswers, ProjectState, HintStateStore, ActivationConfig |
| `hints/_engine.py` | Pipeline: activation → trigger → lifecycle → sort → budget → present |
| `hints/hints.py` | 6 triggers, LearnCommand (DI), combinators, 7 built-in hints |
| `template/hints/*` | Identical copies for Copier template generation |
| `template/{{_copier_conf.answers_file}}.jinja` | Enables `.copier-answers.yml` generation |
| `copier.yml` | Added `use_hints` question + `_exclude` for `hints/` |
| `submodules/claudechic/claudechic/app.py` | `_run_hints()`, startup hook, 2h periodic timer |

### 7 Built-in Hints
| ID | Trigger | Priority | Lifecycle |
|----|---------|----------|-----------|
| `git-setup` | No `.git` directory | 1 (blocking) | ShowUntilResolved |
| `guardrails-default-only` | Only default rule in guardrails | 2 (high-value) | ShowUntilResolved |
| `project-team-discovery` | `/ao_project_team` never used | 2 (high-value) | ShowOnce |
| `pattern-miner-ready` | 10+ sessions, miner never run | 3 (enhancement) | ShowOnce |
| `mcp-tools-empty` | No custom MCP tools | 3 (enhancement) | ShowOnce |
| `cluster-ready` | Cluster configured but unused | 3 (enhancement) | ShowOnce |
| `learn-command` | Rotating slash command lessons | 4 (lesson) | ShowEverySession |

### Tests
| File | Tests | What |
|------|-------|------|
| `tests/test_hints.py` | 90 | Unit + pipeline + multi-evaluation integration |
| `tests/test_hints_e2e.py` | 3 | MinimalApp E2E — Toast widgets in DOM |
| `tests/test_copier_generation.py` | 18 (3 new) | Copier: hints included/excluded, .copier-answers.yml |
| `tests/test_template_freshness.py` | 16 (5 new) | Root ↔ template file sync |
| `submodules/claudechic/tests/test_hints_integration.py` | 5 | Real ChatApp E2E |
| **Total** | **216 all passing** | 64s with 8 workers |

### Architecture
- **5-axis composability**: Activation, TriggerCondition, HintLifecycle, EvaluationTiming, Presentation
- **Iron rule**: every trigger wrapped in try-except, top-level catch in evaluate(), hints never crash ClaudeChic
- **Discovery**: ClaudeChic checks `hints/__init__.py` at startup via `importlib.util.spec_from_file_location` (no sys.path mutation)
- **State**: `.claude/hints_state.json` — activation + lifecycle sections, atomic writes
- **Activation**: `/hints on/off/disable <id>/enable <id>/status/reset`

## Completed
- Phase 0: Vision confirmed ✓
- Phase 1: Setup complete ✓
- Phase 2: Leadership spawned ✓
- Phase 3: Specification complete (9 docs, Rev 6) ✓
- Phase 4: Implementation complete ✓
- Phase 5: Testing complete (216 tests, all passing) ✓
- Phase 6: All Leadership signed off (Skeptic, Composability, TerminologyGuardian, UserAlignment) ✓
- Phase 7: ClaudeChic integration complete ✓
- Phase 8: E2E checkpoint — Copier generation tests added ✓

## Pending
- Phase 9: Live testing — user restarting ClaudeChic to see hints in action
- Commit all changes
- ClaudeChic submodule changes need committing to a branch

## Known Issues
- `test_e2e_smoke.py::test_claudechic_starts` times out (30s) on `pixi run` in fresh project — pre-existing, not hints-related
- Copier leaves empty `hints/` dir when `use_hints=false` — harmless, `_run_hints()` checks for `__init__.py`

## Agents Used
Composability, TerminologyGuardian, Skeptic, UserAlignment, UIDesigner, Axis-TriggerCondition, Axis-HintLifecycle, Axis-Activation, Impl-Types, Impl-State, Impl-Engine, Impl-Hints, Impl-Init, Impl-Copier, Impl-Integration, TestEngineer, TestCopier
