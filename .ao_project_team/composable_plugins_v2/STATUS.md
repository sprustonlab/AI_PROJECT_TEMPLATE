# Project Status

**EVERY TURN: Re-read AI_agents/project_team/COORDINATOR.md**

## Current Phase
Phase 6: Sign-Off

## Vision (from Phase 0)
**Goal:** Implement composable plugins v2 — upgrading AI_PROJECT_TEMPLATE with git URL claudechic dependency, MCP tools seam, cluster MCP port, simplified bootstrap, and cluster onboarding question.

**Value:** Makes the template more maintainable (claudechic not committed), more extensible (MCP tools seam = drop-in plugins), simpler to bootstrap (pixi-only, 2 commands), and cluster-ready out of the box.

**Domain terms:** seam, MCP tools, claudechic, Copier, pixi, LSF cluster, developer mode, git URL dependency, `get_tools()` contract

**Success looks like:**
- `pixi.toml` references claudechic via git URL (with developer mode toggle)
- `mcp_tools/` directory with discovery in claudechic's `mcp.py` (~20 lines)
- `mcp_tools/cluster.py` ported and working, toggled by `use_cluster` Copier question
- Bootstrap docs show 2-command `pixi exec --spec copier` workflow
- All existing v1 seams still pass the swap test

**Failure looks like:** Breaking existing v1 seams, over-engineering the MCP discovery, requiring runtime frameworks instead of directory conventions, or making bootstrap harder.

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
- Composability (Leadership)
- TerminologyGuardian (Leadership)
- Skeptic (Leadership)
- UserAlignment (Leadership)

## Optional Agents
| Agent | Status | Notes |
|-------|--------|-------|
| Researcher | not spawned | Spawn if project involves prior art, external libraries, or scientific methods |
| LabNotebook | not spawned | Spawn if project involves experiments, ablations, or iterative hypothesis testing |

## Completed
- Phase 0: Vision confirmed ✓
- Phase 1: Setup complete ✓
- Phase 2: Leadership spawned ✓
- Phase 3 Leadership reviews: all 4 approved ✓
- Phase 3 user feedback: bootstrap expanded (landing page + dual install scripts) ✓
- Phase 3 user feedback: boazmohar fork sync added as Step 0 ✓
- Phase 3 user feedback: upstream (abast) features identified for sync ✓
- Phase 3 user feedback: docs/ exclusion from Copier clarified ✓
- Phase 3 user feedback: SLURM backend added (Option B: separate files) ✓
- Phase 3 user feedback: landing page + install scripts with location prompt ✓
- Phase 3 user feedback: per-tool YAML config (not .claudechic.yaml) ✓
- Phase 3 user feedback: submodules/ stays in repo, excluded via _exclude ✓
- Phase 3 user feedback: testing infrastructure (local + CI) ✓
- Phase 3 user feedback: develop/main branch workflow ✓
- Phase 3: Spec rewritten for operational clarity (949→~580 lines) ✓
- Phase 3: APPROVED ✓
- Note: README update deferred to separate spec
