# Project: subagent_phase_injection
# Issue: #37

## Phase: setup
## Status: in-progress

## Vision
Investigate and fix how sub-agents receive (or fail to receive) their role-specific
phase instructions in the project-team workflow -- both at spawn time and during
phase transitions. Also address premature agent closure.

## What We Know
- phase_context.md is assembled for the coordinator only
- Sub-agents receive coordinator-authored prompts, not their role phase files
- No automated mechanism to inject context to running sub-agents on phase transition
- Coordinator can close agents at any point

## What We Need to Discover
- What exactly does the coordinator send to sub-agents vs. the actual phase markdown?
- What happens to running sub-agents when a phase advances?
- Which phases and roles are most affected?
- What fix patterns work best (guardrails, claudechic changes, workflow changes, hybrid)?

## Possible Fix Directions
1. Guardrail rules (warn/deny on spawn_agent, close_agent, advance_phase, tell_agent)
2. claudechic system fix (auto-inject at spawn/transition)
3. Workflow-level fix (restructure project-team to handle context delivery)
4. Hybrid across layers
5. Team-discovered alternatives
