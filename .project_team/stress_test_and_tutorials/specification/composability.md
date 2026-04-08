# Composability Analysis

## Domain Understanding

The AI_PROJECT_TEMPLATE is a **Copier template system** that scaffolds Claude Code projects with pluggable subsystems: guardrails (permission rules), multi-agent project teams, hints (user guidance), workflows (phase-gated orchestration), and MCP tools (cluster integration). The user request is to **stress test** this system, fix the stale Copier template (post-claudechic migration), and produce documentation + tutorial workflows.

This is a **multi-type project**: Investigation (stress test), Migration (template update), Documentation (guide), and Workflow (tutorials). Per PROJECT_TYPES.md, I union the relevant axes and refine for this domain.

---

## Project Classification

**Primary signals:** stress test, find bugs, fix, guide, tutorial, workflow
**Matched types:** Investigation + Bug Fix + Documentation + Workflow
**Union axes (starting point):** SymptomVsCause, IsolatedVsSystemic, RootCauseConfirmed, RegressionRisk, AudienceLevel, ReferenceVsTutorial, CurrentVsAspirations, InstructionVsReference, KernelVsInstance, RoleVsPhase

After domain analysis, I've refined these into 6 concrete axes specific to this project:

---

## Identified Axes

### 1. **KernelVsInstance** (Template Fidelity)
- **Values:** kernel (template/ + copier.yml source) | instance (generated project after `copier copy`)
- **Why it's independent:** The template source and a generated project are separate artifacts. You can test the kernel's correctness (Jinja rendering, file exclusion logic) independently from whether a generated instance actually works end-to-end. A template bug might produce a valid-looking instance that fails at runtime, or the template might be correct but the generated project misconfigured.
- **Key stress test questions:**
  - Does `copier copy` with every combination of options produce a working project?
  - Do generated `.claude/settings.json`, `pixi.toml`, and guardrail hooks match current claudechic expectations?
  - Are conditional exclusions (`_exclude` in copier.yml) correctly gating optional subsystems?

### 2. **SubsystemToggle** (Feature Independence)
- **Values:** guardrails | project_team | hints | pattern_miner | cluster | all-combined
- **Why it's independent:** copier.yml exposes boolean toggles (`use_guardrails`, `use_project_team`, `use_hints`, `use_pattern_miner`, `use_cluster`). Each subsystem should be independently enable/disable-able. This is the **core crystal** of the template — every combination of on/off toggles (2⁵ = 32 configurations) should produce a working project.
- **Potential crystal holes:**
  - Does `use_project_team=true` with `use_guardrails=false` work? (Project team references guardrail rules like R04, R05)
  - Does `use_hints=true` without `use_guardrails=true` work? (Hints reference guardrail state)
  - Does `use_cluster=true` without claudechic's MCP infrastructure produce valid config?
- **Compositional law:** Each subsystem should depend only on its own files and a minimal shared interface (the `.claude/` directory structure and environment variables). No subsystem should import from or assume the presence of another.

### 3. **AudienceLevel** (Documentation Target)
- **Values:** human-beginner | human-experienced | ai-agent
- **Why it's independent:** The getting-started guide and tutorials must serve both human users and AI agents. These audiences have different needs: humans need conceptual context and screenshots; agents need precise file paths, exact commands, and machine-parseable structure. The content should be factored so the same underlying information serves all audiences without duplication.
- **Seam:** Factual content (what to do) vs. presentation layer (how to explain it). A clean seam means updating a procedure updates it for all audiences.

### 4. **DeliverableIndependence** (Work Parallelism)
- **Values:** stress-test-fixes | getting-started-guide | tutorial-extending | tutorial-toy-project
- **Why it's independent:** The 4 deliverables can be developed in parallel IF their dependencies are clean. The stress test must complete (or at least identify issues) before the docs can accurately describe the system. But the two tutorials are independent of each other.
- **Dependency graph:**
  ```
  stress-test-fixes ──→ getting-started-guide
       │                        │
       ├──→ tutorial-extending ←┘
       │
       └──→ tutorial-toy-project
  ```
- **Implication for phasing:** Stress test should be the first implementation task. Docs and tutorials follow, but the two tutorials can be parallelized.

### 5. **ClaudechicMode** (Deployment Variant)
- **Values:** standard (git URL install) | developer (local editable install)
- **Why it's independent:** copier.yml offers `claudechic_mode` choice. Each mode has different `pixi.toml` generation, different submodule handling, and different update paths. Both must produce working projects.
- **Stress test concern:** The template was built before claudechic migration. The `standard` mode likely has stale git URLs or dependency specs. The `developer` mode may reference paths that no longer exist.

### 6. **CurrentVsAspirations** (Documentation Accuracy)
- **Values:** documents-current-reality | documents-intended-design | documents-post-fix-state
- **Why it's independent:** A major failure mode (called out in userprompt.md) is docs describing how things *used to work*. Every documentation statement must be tagged (implicitly or explicitly) with whether it describes the system as-is, the intended design, or the post-stress-test state. This axis is orthogonal to audience and deliverable type.
- **Clean seam:** Facts should be verified against running code, not copied from existing (potentially stale) docs.

---

## Compositional Law

**The shared protocol enabling composition across these axes:**

> **Every subsystem speaks "file convention."** Each subsystem occupies a well-defined directory subtree, declares its dependencies via imports and config references, and is activated/deactivated by file presence (not code branches). The seam between subsystems is the filesystem layout + environment variables.

Concretely:
- Guardrails: `.claude/guardrails/` + `rules.yaml` + hooks → activated by `settings.json` hook entries
- Hints: `hints/` module → activated by command availability
- Project team: `AI_agents/project_team/` → activated by `/ao_project_team` command
- Workflows: `workflows/` YAML → activated by claudechic phase system
- Cluster: `mcp_tools/` → activated by MCP config

**If this law holds**, toggling a subsystem = including/excluding its directory. No other subsystem needs to change. **If it doesn't hold**, we've found a crystal hole.

---

## Potential Issues (Predicted Crystal Holes)

### High Priority
1. **Guardrails ↔ Project Team coupling:** Rules R04 (subagent-push-block) and R05 (subagent-guardrail-config-block) are project-team-specific but live in the guardrails subsystem. If `use_project_team=false` but `use_guardrails=true`, these rules reference roles that don't exist. This is a **dirty seam** — guardrails leak project-team assumptions.

2. **Template ↔ claudechic version drift:** The template's `pixi.toml.jinja` and `settings.json` reference specific claudechic APIs, paths, and behaviors. Post-migration, these references are likely stale. This isn't a composability issue per se, but it's the **primary bug source** for the stress test.

3. **Workflow YAML ↔ guardrails rules duplication:** The `project_team.yaml` workflow defines its own rules (`no_direct_code_coordinator`, `no_push_before_testing`, `no_force_push`) separately from `rules.yaml`. Are these the same system or parallel systems? If parallel, which takes precedence? This is a **wrong decomposition smell** — rules should live in one place.

### Medium Priority
4. **Hints ↔ guardrails state coupling:** The `GuardrailsOnlyDefault` hint trigger checks guardrail state. If guardrails are disabled, does this hint gracefully no-op or crash?

5. **Platform axis under-tested:** `target_platform` choices (linux-64, osx-arm64, win-64, all) affect `pixi.toml` generation but may not be tested in CI for all combinations with subsystem toggles.

6. **`global/rules.yaml` vs `.claude/guardrails/rules.yaml`:** Two rule files exist. Their relationship is unclear — is `global/` a template for what gets copied, or a runtime override? This is a **structural smell** (ambiguous file authority).

### Lower Priority
7. **Tutorial workflow assumes all subsystems enabled:** The tutorial teaches guardrails, hints, and project team in sequence. It likely assumes all are present. A user who disabled some via Copier won't get a working tutorial.

8. **MCP tools only have cluster backends:** The MCP tools directory only contains LSF/SLURM. The framework implies extensibility, but there's only one axis value demonstrated. Not a bug, but a documentation gap.

---

## Recommended Stress Test Matrix

Based on the axes above, here are **10 crystal points** to test (the "10-point test"):

| # | SubsystemToggle | ClaudechicMode | Platform | Expected Result |
|---|----------------|----------------|----------|-----------------|
| 1 | all on | standard | linux-64 | Happy path — must work |
| 2 | all on | developer | linux-64 | Developer mode — must work |
| 3 | guardrails only | standard | linux-64 | Minimal viable project |
| 4 | project_team only (no guardrails) | standard | linux-64 | **Likely fails** — test this |
| 5 | hints only | standard | linux-64 | Should work if independent |
| 6 | none (all off) | standard | linux-64 | Bare project — must work |
| 7 | all on | standard | osx-arm64 | Cross-platform |
| 8 | guardrails + hints (no team) | standard | linux-64 | Common subset |
| 9 | all on + cluster(lsf) | standard | linux-64 | Full features |
| 10 | all on + cluster(slurm) | developer | linux-64 | Max complexity |

---

## Recommended Deep-Dive Axes

1. **SubsystemToggle** — This is the primary composability axis. A focused agent should systematically test all 32 toggle combinations (or at least the 10 above) and document which ones have holes.

2. **KernelVsInstance** — A focused agent should diff the template/ source against the actual project root to find drift introduced by the claudechic migration.

3. **Workflow rules vs guardrail rules** — A focused agent should clarify the relationship between `workflows/*.yaml` rules and `.claude/guardrails/rules.yaml` rules, and recommend a clean decomposition.

---

## File Structure Assessment

The current structure **mostly reflects the axes well**:
- ✅ Each subsystem has its own directory (`hints/`, `workflows/`, `AI_agents/`, `.claude/guardrails/`)
- ✅ Copier exclusions map to subsystem directories
- ⚠️ `global/` directory's role is ambiguous relative to `.claude/guardrails/`
- ⚠️ `template/mcp_tools/` lives inside template but cluster config lives in `copier.yml` — split concern
- ⚠️ Workflow-level rules in YAML files duplicate guardrails concepts — unclear seam

---

## Summary for Coordinator

**This project's composability hinges on one central question: Are the template's subsystems truly independent toggles, or do they have hidden couplings?**

The stress test should systematically verify the SubsystemToggle crystal (32 combinations). The documentation should be factored by audience. The tutorials should be built after the stress test confirms (or fixes) subsystem independence.

**Top 3 actions:**
1. Test point #4 (project_team without guardrails) — most likely crystal hole
2. Diff template/ against project root to find claudechic migration drift
3. Clarify the two-rules-systems issue (workflow YAML rules vs guardrails rules.yaml)
