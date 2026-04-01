# Project Status

**EVERY TURN: Re-read AI_agents/project_team/COORDINATOR.md**

## Current Phase
Phase 4: Implementation — Red phase (failing tests)

## Vision (from Phase 0)
**Goal:** Write intent-based integration tests that fail today (proving features are broken/unwired), then fix the code to make them pass.
**Approach:** Red → Green. No fixing until the test proves the failure.
**Value:** Current tests validate components in isolation but never prove the system works end-to-end. Features are documented as working but never exercised through real entry points.
**Domain terms:** Intent-based tests, guardrail wiring, settings merge
**Success looks like:** Failing tests that prove guardrails don't fire, settings.json isn't wired, features are dead. A settings.json merge strategy that preserves existing values. Targeted fixes that turn red tests green.
**Failure looks like:** Tests that mock everything and prove nothing. generate_hooks.py that blindly overwrites settings.json. Guardrails that still silently fail.

**Key concerns:**
1. settings.json may already have permissions, mcpServers, custom settings — must merge, not replace
2. Hook entries need to be idempotent (running twice doesn't duplicate)
3. Tests must verify merge behavior with pre-existing content

## Active Axes
| Axis | Status | Agent | Notes |
|------|--------|-------|-------|
| (populated by Composability) | | | |

## Leadership Spawn Evidence
- Composability: spawned ✓
- TerminologyGuardian: spawned ✓
- Skeptic: spawned ✓
- UserAlignment: spawned ✓

## Agents Active
- Composability (busy)
- TerminologyGuardian (busy)
- Skeptic (busy)
- UserAlignment (busy)

## Optional Agents
| Agent | Status | Notes |
|-------|--------|-------|
| Researcher | not spawned | Spawn if project involves prior art, external libraries, or scientific methods |
| LabNotebook | not spawned | Spawn if project involves experiments, ablations, or iterative hypothesis testing |

## Completed
- Phase 0: Vision confirmed ✓
- Phase 1: Setup complete ✓
