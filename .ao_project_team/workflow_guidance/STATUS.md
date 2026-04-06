# Project Status

**EVERY TURN: Re-read AI_agents/project_team/COORDINATOR.md**

## Current Phase
Phase 3: Specification (SpecWriter synthesizing all findings into SPECIFICATION.md)

## Vision (from Phase 0)
**Goal:** Write the architecture specification for a Workflow Guidance System — infrastructure in claudechic that lets workflows define phases, guardrail rules, checks, and hints via YAML manifests and markdown files.

**Value:** Unifies currently scattered guidance (rules, checks, hints) into one system — YAML manifests + markdown content in `workflows/`. Users get a single pattern and a clear 2x2 mental model (advisory/enforced x positive/negative).

**Domain terms:** Manifests, phases, checks, hints, guardrails, SDK hooks, agent folders, ManifestSection protocol, 2x2 guidance framing, enforcement levels (deny/user_confirm/warn/log)

**Success looks like:** A complete architecture specification that a team can implement — covering the unified manifest loader, workflow engine, check protocol, agent folders, phase-scoped evaluation, and `/compact` recovery. The project-team workflow is the first workflow built on it.

**Failure looks like:** A spec that's too vague to implement, misses the interaction between subsystems (e.g., how checks bridge to hints, how phase transitions gate on checks), or fails to identify which existing claudechic code needs to change and how (refactors, new modules, modified interfaces).

## Active Axes (from Composability)
| Axis | Status | Agent | Notes |
|------|--------|-------|-------|
| Section Type (ManifestSection[T]) | pending deep-dive | — | Parser protocol design |
| Check Type | pending deep-dive | — | Async check protocol + ManualConfirm TUI seam |
| Scope | covered | — | Composable filters: namespace, phase, role, conditional |
| Enforcement / Delivery | covered | — | SDK hooks, hints, prompt injection |
| Lifecycle | covered | — | Reuses existing HintLifecycle |
| Content vs Infrastructure | critical seam | — | Guard: no workflow-specific code in claudechic |

## Leadership Findings Summary
- **UserAlignment:** Vision aligned. 2 ambiguities (hint scoping, CheckFailed adapter scope). 7 examples required.
- **TerminologyGuardian:** 40+ canonical terms. Key: rule≠check, guidance≠guardrail, advisory≠hint, engine≠loader.
- **Skeptic:** 6 risk areas (NFS perf, interface migration, ManualConfirm TUI coupling, fail-closed on NFS, completeness gaps, warn enforcement). 10 recommendations.
- **Composability:** 6 axes. Crystal clean. 3 seam concerns (rules↔TUI, content↔infra, loader two-mode). 3 deep-dives recommended.

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
| Researcher | spawned ✓ | Mapping existing claudechic codebase for refactoring boundaries |
| LabNotebook | not spawned | Spawn if project involves experiments, ablations, or iterative hypothesis testing |

## Completed
- Phase 0: Vision confirmed ✓
- Phase 1: Setup complete ✓
