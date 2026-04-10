# SPECIFICATION — Stress Test & Tutorials

> **APPROVED by user on 2026-04-06.**
>
> Synthesized from Leadership reports: composability.md, terminology.md, skeptic_review.md, user_alignment.md.
> Bugs discovered during this specification session are included.

---

## 1. Project Overview

**Goal:** Stress test and fix the AI Project Template, then produce a Getting Started Guide and two runnable tutorial workflows — one for extending the system, one for running a full agent team project.

**Value:** The Copier template is stale (claudechic migration introduced significant drift — not just cosmetic, but structurally incomplete: 29+ missing files, weakened guardrails, missing agent roles). There is no guided path for users who want to customize or extend the system. These deliverables close both gaps.

**Scope note:** The stress test covers claudechic infrastructure itself — agent messaging reliability (`tell_agent`/`ask_agent`), phase injection timing, workflow-role wiring for spawned agents, and cross-workflow isolation. Bugs found in claudechic during this project are in scope for fixing, not filed separately.

**Success criteria:**
- `copier copy` with every option combination produces a working project that matches current codebase reality
- A new user (human or agent) can follow the Getting Started Guide and be productive within one session
- Both tutorial workflows run end-to-end via the workflow YAML system with no unexplained errors
- "Extending" tutorial leaves the user with real new rules/advance checks they created
- "Toy Project" tutorial produces a complete `labmeta` (Animal Experiment Metadata Manager) built by the agent team

**Failure criteria:**
- Docs describe how things *used to work* instead of how they work now
- Tutorials break mid-way or assume knowledge the reader doesn't have
- Stress test is shallow — only tests the happy path
- Template stays out of sync with claudechic

---

## 2. Canonical Terminology

> **Source of truth:** `specification/terminology.md`. All documents MUST use these terms.

### Resolved Naming Conflicts

| Conflict | Resolution | Rationale |
|----------|-----------|-----------|
| "checkpoint" vs "advance check" | Use **"advance check"** | Matches the YAML key (`advance_checks`). "Checkpoint" is retired. |
| "rule" (guardrail) vs "rule" (workflow) | Use **"global rule"** vs **"workflow rule"** | Same mechanism, different scope. Always qualify when context is ambiguous. |
| "template" (Copier) vs "template" (Jinja file) | Use **"Copier template"** (the system) vs **"template file"** or **"Jinja template"** (individual `.jinja` files) | Avoids confusion between the scaffolding system and its source files. |

### Key Terms (Quick Reference)

| Term | Definition |
|------|-----------|
| **AI_PROJECT_TEMPLATE** | The top-level repository; source of truth for all infrastructure |
| **claudechic** | CLI/TUI wrapper and MCP tool infrastructure. NOT "chic", "the wrapper", "the MCP server" |
| **Copier template** | `copier.yml` + `template/` directory. Scaffolds new projects via `copier copy` |
| **Project Team** | Multi-agent workflow system (`AI_agents/project_team/`). NOT "the agents", "agent team" |
| **Agent role** | A markdown file defining one agent's responsibilities (e.g., `COORDINATOR.md`) |
| **Workflow** | Phase-gated process defined by YAML in `workflows/`. NOT "pipeline", "process" |
| **Phase** | Named stage within a workflow. NOT "step", "stage" |
| **Advance check** | Gate condition for phase transitions. NOT "checkpoint", "gate" |
| **Guardrails** | Permission/safety system. Rules → generated hooks. NOT "permissions", "access control" |
| **Global rule** | Rule in `global/rules.yaml` — applies everywhere |
| **Workflow rule** | Rule in a workflow YAML `rules:` section — applies only during that workflow |
| **Hook (generated)** | Claude Code hook in `settings.json`, auto-generated from rules. Hooks are mechanism; rules are policy |
| **Hints** | Onboarding toast notifications (`hints/`). NOT "tips", "notifications" |
| **Enforcement levels** | `deny` (hard block), `warn` (ack required), `log` (silent audit) |
| **Stress test** | Systematic exercise of all components to surface bugs. NOT a performance/load test |
| **Getting Started Guide** | Reference doc in `docs/` for humans AND agents |
| **Tutorial workflow** | Runnable workflow YAML (in `workflows/`) that teaches step-by-step |

Full terminology: see `specification/terminology.md`.

---

## 3. Composability Axes

### Project Classification

Multi-type project: **Investigation + Bug Fix + Documentation + Workflow**. Axes are the union of default axes from PROJECT_TYPES.md, refined for this domain.

### Identified Axes (6)

| # | Axis | Values | Independence Rationale |
|---|------|--------|----------------------|
| 1 | **KernelVsInstance** | kernel (template/ source) \| instance (generated project) | Template correctness and generated-project correctness are separately testable |
| 2 | **SubsystemToggle** | guardrails \| project_team \| hints \| pattern_miner \| cluster (2⁵ = 32 combinations) | copier.yml exposes boolean toggles; each subsystem should be independently enable/disable-able |
| 3 | **AudienceLevel** | human-beginner \| human-experienced \| ai-agent | Docs serve different audiences with different needs |
| 4 | **DeliverableIndependence** | stress-test-fixes \| getting-started-guide \| tutorial-extending \| tutorial-toy-project | Dependency graph constrains parallelism (see §7) |
| 5 | **ClaudechicMode** | standard (git URL) \| developer (local editable) | Different pixi.toml generation, submodule handling, update paths |
| 6 | **CurrentVsAspirations** | documents-current-reality \| documents-post-fix-state | Every doc statement must reflect post-fix truth, not stale state |

### Compositional Law

> Every subsystem speaks "file convention." Each occupies a well-defined directory subtree, declares dependencies via imports/config, and is activated/deactivated by file presence — not code branches. Toggling a subsystem = including/excluding its directory.

### Predicted Crystal Holes (High Priority)

1. **Guardrails ↔ Project Team coupling:** Rules R04 (`subagent-push-block`) and R05 (`subagent-guardrail-config-block`) reference team roles. If `use_project_team=false` + `use_guardrails=true`, these rules reference roles that don't exist. **Dirty seam.**

2. **Template ↔ claudechic version drift:** `pixi.toml.jinja` and `settings.json` in template/ have stale references post-migration. **Primary bug source.**

3. **Two rules systems:** Workflow YAML defines rules separately from `rules.yaml`. Unclear precedence, possible duplication. **Wrong decomposition smell.**

### Stress Test Matrix (11-Point Crystal Test — All 3 Platforms In Scope)

| # | SubsystemToggle | ClaudechicMode | Platform | Expected |
|---|----------------|----------------|----------|----------|
| 1 | all on | standard | linux-64 | Must work (happy path) |
| 2 | all on | developer | linux-64 | Must work |
| 3 | guardrails only | standard | linux-64 | Minimal viable project |
| 4 | project_team only (no guardrails) | standard | linux-64 | **Likely fails** — priority test |
| 5 | hints only | standard | linux-64 | Should work if independent |
| 6 | none (all off) | standard | linux-64 | Bare project — must work |
| 7 | all on | standard | osx-arm64 | Cross-platform (in scope) |
| 8 | guardrails + hints (no team) | standard | linux-64 | Common subset |
| 9 | all on + cluster(lsf) | standard | linux-64 | Full features |
| 10 | all on + cluster(slurm) | developer | linux-64 | Max complexity |
| 11 | all on | standard | win-64 | Cross-platform (in scope) |

---

## 4. Risk Analysis & Failure Modes

> Source: `specification/skeptic_review.md`

### Critical Risks

| ID | Risk | Impact | Mitigation |
|----|------|--------|------------|
| **F1** | Template generates projects that break on `pixi install` | DOA generated projects | Test `copier copy` + `pixi install` for all option combinations |
| **F2** | Template generates incomplete Project Team (only 4 of 17 agent roles) | Project Team unusable | Inventory all missing files; add to template with Jinja conditionals |
| **F4** | "Extending" tutorial teaches outdated patterns | Users learn wrong things | Write tutorial AFTER template is fixed; reference post-fix file layout |

### High Risks

| ID | Risk | Impact | Mitigation |
|----|------|--------|------------|
| **F3** | Tutorial advance checks fail silently, user gets stuck | Destroyed user confidence | Automated test: start workflow, create expected file, verify phase advances |
| **F7** | Global rules + workflow rules create confusing layering | Onboarding confusion | Document rule layering clearly in Getting Started Guide |

### Medium Risks

| ID | Risk | Impact | Mitigation |
|----|------|--------|------------|
| **F5** | Developer mode path untested | Power users affected | Test `copier copy` with `claudechic_mode=developer` |
| **F6** | Getting Started Guide goes stale immediately | #1 developer tooling complaint | Add companion smoke test that verifies key claims |

### Skeptic's Key Insight

> "Fix the stale Copier template" sounds like a single task. It's actually: (a) inventory all drift, (b) add missing files with Jinja conditionals, (c) update copier.yml exclusions, (d) update `_tasks`, (e) verify all option combinations, (f) update `test_template_freshness.py` paired-files list. Calling it one task masks the scope.

### Template Drift Inventory (from Skeptic)

| Missing from template/ | Impact |
|------------------------|--------|
| `workflows/` directory (29 files) | Generated projects have NO workflow system |
| `global/` directory (`rules.yaml`, `hints.yaml`) | No centralized config |
| 11+ agent role files | Project Team incomplete (only COORDINATOR, IMPLEMENTER, SKEPTIC, TEST_ENGINEER) |
| `commands/jupyter` | Missing command |
| Guardrail enforcement divergence (root=`deny`, template=`warn`) | Weaker guardrails |

---

## 5. User Alignment Notes

> Source: `specification/user_alignment.md`

**Overall status: ✅ ALIGNED** — Vision faithfully captures the user's request. No scope creep or shrink.

### Resolved Ambiguities

| # | Ambiguity | Resolution |
|---|-----------|-----------|
| **#1** | Getting Started Guide audience (human vs agent) | Structure with shared context sections + clearly marked "For Humans" / "For Agents" branches where workflows diverge (per Skeptic recommendation) |
| **#2** | Toy Project vision/goal selection | **RESOLVED:** `labmeta` — Animal Experiment Metadata Manager. Protocols (base configs) + sessions (per-animal overrides). Domain-relevant, exercises rules and advance checks naturally. |
| **#3** | Existing tutorial dependency | Stress test must verify existing tutorial works before building "Extending" tutorial on top |
| **#4** | "Runnable workflow" meaning | **RESOLVED:** Runnable = actual workflow YAML files (`.yaml` in `workflows/`), not markdown guides. Tutorials are executed via the workflow system. |

### Wording Alignment

| User's Words | Our Words | Status |
|---|---|---|
| "stress test" | "stress test" | ✅ |
| "stale Copier template" | "Copier template drift" | ✅ |
| "Getting Started Guide" | "Getting Started Guide" | ✅ |
| "runnable workflow" | "tutorial workflow (YAML)" | ✅ Resolved |
| "reference for agents and humans" | dual-audience guide | ✅ Addressed in structure |

---

## 6. Bugs Found During Specification Session

These bugs were discovered while the Leadership team used the system to produce this specification. They are direct stress-test findings.

### BUG #1: Phase MD Injections Arrive Late/Out-of-Order

**Symptom:** When a workflow phase advances, the phase-specific markdown instructions (injected into the agent's context) arrive late or in unexpected order. Agents may begin work before receiving their phase instructions.

**Impact:** Agents operate without guidance, potentially doing wrong work or missing phase-specific constraints.

**Category:** Workflow system infrastructure bug.

### BUG #2: `spawn_agent` Not Wired to Workflow Role System

**Symptom:** When the Coordinator spawns agents via `spawn_agent`, the spawned agent is not automatically associated with its workflow role. The agent's `CLAUDE_AGENT_ROLE` environment variable may not be set correctly, and workflow-scoped rules may not apply to it.

**Impact:** Workflow rules that target specific roles (e.g., "only Coordinator can push") don't fire. The role-based permission system is bypassed.

**Category:** claudechic ↔ workflow integration bug.

### BUG #3: `tell_agent` Unreliable; `ask_agent` Works; Nudge System Over-Fires

**Symptom:** Messages sent via `tell_agent` are sometimes not delivered or not processed by the target agent. `ask_agent` works reliably (because it blocks for a response). The nudge system (designed to remind idle agents) fires too aggressively — agents that have already reported get re-nudged.

**Impact:** Coordination overhead. The Coordinator receives duplicate reports and must re-request status from agents that already answered. Wastes tokens and creates confusion.

**Category:** claudechic inter-agent communication bug.

### BUG #4: Workflow Activation Does Not Auto-Create ChicSession

**Symptom:** When a workflow is activated via `/{workflow-id}`, no chicsession is created. The `persist_fn` callback exits early because `self._chicsession_name` is None. Workflow state (phase, agents) is never persisted. Sessions cannot be resumed.

**Root cause:** `_activate_workflow()` in `app.py` (lines ~1197-1250) creates the WorkflowEngine and wires up `persist_fn`, but never initializes a chicsession. The `persist_fn` (lines 1317-1333) checks `if not self._chicsession_name: return` and exits.

**Fix location:** `submodules/claudechic/claudechic/app.py` — after creating the engine in `_activate_workflow()`, auto-create a chicsession named after the workflow_id and set `self._chicsession_name`.

**Impact:** Critical — the entire agent team persistence feature is broken. No workflow state survives session restart.

**Category:** claudechic workflow-session integration bug.

### UX Issue: `get_phase` Shows Cross-Workflow Injections

**Symptom:** When calling `get_phase`, the response includes injection content from OTHER active workflows, not just the current one. This pollutes the agent's context with irrelevant phase instructions.

**Impact:** Confusion. Agents may follow instructions from a different workflow.

**Category:** claudechic workflow isolation issue.

---

## 7. Implementation Phasing

### Dependency Graph

```
Phase A: Stress Test (infrastructure verification)
  ├── A.1: Stress test claudechic session — reproduce and fix BUGs #1-3 from §6
  │   ├── BUG #1: Phase MD injection timing
  │   ├── BUG #2: spawn_agent ↔ workflow role wiring
  │   ├── BUG #3: tell_agent reliability + nudge over-firing
  │   └── UX: get_phase cross-workflow isolation
  ├── A.2: Fix chicsession auto-creation on workflow activation (BUG #4)
  │   ├── Root cause: _activate_workflow() never initializes chicsession
  │   ├── Fix: auto-create chicsession named after workflow_id
  │   └── Verify: workflow state persists and restores on session restart
  ├── A.3: Verify workflow system (advance checks, phase-scoped rules, hints)
  ├── A.4: Inventory ALL template drift (not just happy path)
  ├── A.5: Test 10-point crystal matrix (or subset)
  └── A.6: Document bugs found (like §6 above)
      │
Phase B: Template Fix (requires A's inventory)
  ├── Add missing files to template/ with Jinja conditionals
  ├── Update copier.yml exclusions and _tasks
  ├── Align enforcement levels (deny vs warn)
  ├── Update test_template_freshness.py paired-files list
  └── Verify all option combinations generate working projects
      │
Phase C: Getting Started Guide (requires B's fixed template as source of truth)
  ├── Write shared context sections
  ├── Write "For Humans" workflow branches
  ├── Write "For Agents" workflow branches
  └── Add companion freshness smoke test
      │
      ├── Phase D1: Tutorial "Extending the System" (requires C's terminology + file layout)
      │   ├── Workflow YAML definition in workflows/
      │   ├── Phase files teaching: add rule, add advance check, edit agent role, edit YAML config
      │   └── Verify existing tutorial works first (dependency from user_alignment.md)
      │
      └── Phase D2: Tutorial "Toy Project with Agent Team" — labmeta (requires A's verified pipeline)
          ├── Build labmeta (Animal Experiment Metadata Manager)
          ├── Workflow YAML definition in workflows/tutorial_toy_project/
          ├── 5 tutorial rules (R-TOY-01 through R-TOY-05) + 6 advance checks
          └── Exercises full Project Team pipeline start-to-finish
```

**Key constraint:** D1 and D2 can parallelize, but both depend on A and B being complete. C should precede D1 (terminology/layout dependency) but D2 only needs A (verified pipeline).

### Estimated Implementer Allocation

| Phase | Implementer(s) | Notes |
|-------|----------------|-------|
| A: Stress Test | 1-2 | Systematic, needs careful exploration |
| B: Template Fix | 1-2 | File-by-file sync + Jinja conditionals |
| C: Getting Started Guide | 1 | Writing-heavy, needs fixed template |
| D1: Extending Tutorial | 1 | Workflow YAML + phase files |
| D2: Toy Project Tutorial | 1 | Workflow YAML + phase files + toy project code |

---

## 8. Deliverable Definitions

### Deliverable 1: Stress Test + Fixes

**Output:**
- Bug inventory document listing all issues found (template drift, workflow bugs, communication bugs)
- Fixes applied directly to codebase
- Updated `test_template_freshness.py` with complete paired-files list
- Crystal matrix test results (10 points minimum)

**Acceptance criteria:**
- All 11 crystal points tested (all 3 platforms: linux-64, osx-arm64, win-64); failures documented and either fixed or filed
- Template drift fully inventoried (not just spot-checked)
- Bugs from §6 documented with reproduction steps
- All 4 session bugs (§6) reproduced, root-caused, and fixed (BUG #1: phase injection timing, BUG #2: spawn_agent role wiring, BUG #3: tell_agent reliability + nudge system, BUG #4: chicsession auto-creation on workflow activation)
- ChicSession auto-creates on workflow activation; workflow state persists and restores correctly
- Workflow system verified: phase advance, advance checks, scoped rules all work

### Deliverable 2: Getting Started Guide

**Output:** `docs/getting-started.md` (or similar)

**Structure:**
- Shared: What is AI_PROJECT_TEMPLATE? What does it do? Prerequisites.
- Shared: Installation (`copier copy` walkthrough with option explanations)
- **For Humans:** What to expect on screen, where to click, common workflows
- **For Agents:** Exact file paths, tool names, expected return values, error patterns
- Shared: Next steps (link to tutorials)

**Acceptance criteria:**
- A new user (human) can follow it and have a working project in one session
- An agent can parse it and execute the described workflows
- Companion smoke test verifies key claims (referenced paths exist, commands work)
- Uses canonical terminology from §2

### Deliverable 3: Tutorial Workflow — "Extending the System"

**Output:** `workflows/tutorial_extending/` (YAML + phase files)

**Phases teach:**
1. Add a new global rule to `global/rules.yaml`
2. Add a new advance check to a workflow YAML
3. Edit an agent role file in `AI_agents/project_team/`
4. Edit YAML configuration (workflow or copier)

**Acceptance criteria:**
- Runs end-to-end via workflow system (`advance_phase` progresses through all phases)
- Each phase has clear instructions and a `file-exists-check` or equivalent advance check
- User ends with real, working new rules/advance checks they created
- Existing tutorial (`workflows/tutorial/`) verified working as prerequisite

### Deliverable 4: Tutorial Workflow — "Toy Project with Agent Team" (`labmeta`)

**Output:** `workflows/tutorial_toy_project/` (YAML + phase files)

**Pre-selected project:** `labmeta` — Animal Experiment Metadata Manager. A CLI tool that manages experiment protocol templates and per-session metadata with inheritance, validation, and locking.

**CLI name:** `labmeta`

**Core commands:**
```bash
labmeta init protocol mouse_surgery_protocol.yaml    # Create protocol template
labmeta create session mouse_001_session_20260406 --protocol mouse_surgery_protocol.yaml
labmeta validate                                      # Validate all against schema
labmeta resolve mouse_001_session_20260406            # Show merged protocol + overrides
labmeta lock mouse_001_session_20260406               # Immutable after experiment complete
labmeta tree                                          # Protocol → session inheritance tree
labmeta dependents mouse_surgery_protocol             # Which sessions use this protocol
```

**Example data model:**
```yaml
# protocols/mouse_surgery_protocol.yaml
_type: protocol
procedure: cranial_window
anesthesia: isoflurane
brain_region: V1
coordinates:
  ap_mm: -2.5
  ml_mm: 2.5
  dv_mm: 0.3
default_imaging_depth_um: 200

# sessions/mouse_001_session_20260406.yaml
_type: session
_protocol: mouse_surgery_protocol.yaml
_locked: false
animal_id: mouse_001
strain: C57BL/6J
age_weeks: 12
weight_g: 28.5
experimenter: moharb
coordinates:
  ap_mm: -2.7        # override — actual position differed
notes: "Slight bleeding during craniotomy, resolved"

# schema.yaml
animal_id: {type: str, required: true}
strain: {type: str, required: true, enum: [C57BL/6J, Thy1-GCaMP6, PV-Cre, SST-Cre, VIP-Cre]}
age_weeks: {type: int, required: true, min: 1, max: 200}
weight_g: {type: float, required: true, min: 5.0, max: 100.0}
procedure: {type: str, required: true, enum: [cranial_window, injection, perfusion, behavior]}
anesthesia: {type: str, required: true, enum: [isoflurane, ketamine_xylazine, none]}
brain_region: {type: str, enum: [V1, S1, M1, PFC, HPC, VTA]}
coordinates:
  ap_mm: {type: float, min: -10.0, max: 10.0}
  ml_mm: {type: float, min: -10.0, max: 10.0}
  dv_mm: {type: float, min: -10.0, max: 10.0}
experimenter: {type: str, required: true}
notes: {type: str}
```

**Tutorial-specific rules:**
```yaml
rules:
  - id: R-TOY-01
    name: locked-session-edit-block
    enforcement: deny
    trigger: PreToolUse [Write, Edit]
    detect: "Block writes to session YAML files containing _locked: true"
    message: "This session is locked (experiment complete). Unlock first with labmeta unlock."

  - id: R-TOY-02
    name: protocol-delete-block
    enforcement: deny
    trigger: PreToolUse [Bash]
    detect: "rm.*protocols/.*\\.yaml"
    message: "Cannot delete a protocol with active sessions. Run labmeta dependents first."

  - id: R-TOY-03
    name: schema-edit-during-implementation
    enforcement: warn
    trigger: PreToolUse [Write, Edit]
    detect: "schema\\.yaml"
    message: "Editing schema during implementation may invalidate existing configs."

  - id: R-TOY-04
    name: no-hardcoded-paths
    enforcement: warn
    trigger: PreToolUse [Write, Edit]
    detect: "/home/|/Users/|C:\\\\"
    message: "Hardcoded absolute path detected. Use relative or config-driven paths."

  - id: R-TOY-05
    name: test-before-push
    enforcement: deny
    trigger: PreToolUse [Bash]
    detect: "git push"
    message: "Cannot push until testing phase is complete and all tests pass."
```

**Advance checks per phase:**
- **specification → implementation:** `file-exists: protocols/schema.yaml` + `manual-confirm: "User confirmed single-level inheritance model?"`
- **implementation → testing:** `file-exists: protocols/examples/mouse_surgery_protocol.yaml` + `file-exists: sessions/examples/mouse_001_session_20260406.yaml` + `file-exists: labmeta/resolver.py`
- **testing → signoff:** `file-exists: .test_runs/latest_results.txt` + `manual-confirm: "All tests passing?"`

**File structure:**
```
toy_lab_meta/
├── protocols/                      # Protocol templates
│   ├── schema.yaml
│   └── examples/
│       └── mouse_surgery_protocol.yaml
├── sessions/                       # Session records
│   └── examples/
│       └── mouse_001_session_20260406.yaml
├── labmeta/                        # The tool (~380 lines total)
│   ├── __init__.py
│   ├── cli.py                      # CLI entry point (~60 lines)
│   ├── resolver.py                 # Inheritance + merge (~80 lines)
│   ├── schema.py                   # Validation (~50 lines)
│   └── store.py                    # YAML read/write (~40 lines)
├── tests/
│   ├── test_resolver.py
│   ├── test_schema.py
│   ├── test_store.py
│   └── test_cli.py
├── .claude/guardrails/rules.yaml   # R-TOY-01 through R-TOY-05
├── workflows/tutorial_toy_project/
│   └── toy_project.yaml
└── specification/
    ├── composability.md
    └── terminology.md
```

**Domain terminology (enforced by TerminologyGuardian):**
- **protocol** — reusable experiment template (NOT "base config", "template")
- **session record** — per-animal instance inheriting from protocol (NOT "experiment config")
- **resolved config** — merged output of protocol + session overrides
- **lock** — make session immutable after experiment (NOT "freeze", "protect")

**Phases mirror Project Team workflow:**
1. Vision — pre-written goal (labmeta), user confirms
2. Specification — guided specification with Leadership agents
3. Implementation — Implementer builds labmeta (~380 lines, 4 modules)
4. Testing — TestEngineer verifies (resolver, schema, store, CLI)
5. Sign-off — user reviews working labmeta tool

**Acceptance criteria:**
- Runs end-to-end via workflow system
- Exercises full Project Team pipeline (spawn agents, delegate, advance phases)
- All 5 tutorial rules fire correctly in their designated phases
- All advance checks gate phase transitions properly
- Produces a complete, working `labmeta` tool at the end
- User understands the agent team workflow after completing it
