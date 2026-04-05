# Project Status

**EVERY TURN: Re-read AI_agents/project_team/COORDINATOR.md**

## Current Phase
Phase 3: Specification (waiting for Leadership reports)

## Vision (from Phase 0)
**Goal:** Add a "tutorial" system to the template that guides users through common tasks using markdown content, agent teams, hints, and guardrails in a dedicated tutorial mode.

**Value:** New users (scientists) struggle with foundational dev tasks. The template itself teaches them interactively with AI guidance, safety rails, and checkpoint guardrails that verify actual completion.

**Key insight:** Guardrails serve dual purpose — preventing mistakes AND verifying step completion (agent can't fake success).

**Success:** User picks a tutorial, gets interactive walkthrough with agents helping, hints nudging, guardrails preventing mistakes and proving each step was actually done.

**Failure:** Static markdown with no interactivity, or agent claiming success without verification.

## Active Axes
| Axis | Status | Agent | Notes |
|------|--------|-------|-------|
| Verification | ✅ Complete | Axis-Verification | Checkpoint guardrails, 5 built-in checks, rich VerificationResult |
| Content | ✅ Complete | Axis-Content | tutorial.yaml manifest, step markdown format, auto-discovery |
| Guidance | ✅ Complete | Axis-Guidance | 3 new TriggerConditions, HintSpec integration, agent-assist |

## Leadership Spawn Evidence
- Composability: spawned ✓
- TerminologyGuardian: spawned ✓
- Skeptic: spawned ✓
- UserAlignment: spawned ✓

## Agents Active
- Composability [busy]
- TerminologyGuardian [busy]
- Skeptic [busy]
- UserAlignment [busy]

## Optional Agents
| Agent | Status | Notes |
|-------|--------|-------|
| Researcher | spawned ✓ | Researching prior art: rustlings, exercism, GitHub Learning Lab, CLI tutorial systems |
| LabNotebook | not spawned | Spawn if project involves experiments, ablations, or iterative hypothesis testing |

## Completed
- Phase 0: Vision confirmed
- Phase 1: Setup complete
