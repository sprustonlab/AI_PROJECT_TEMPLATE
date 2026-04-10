# docs_audit -- Final Specification (v3)

> Compiled by Composability Leadership. Incorporates all leadership feedback and user decisions.
> v2: Removes `/init_project`, refines `.claude/rules/` description.
> v3: CRITICAL fix — global rules are always active, not just during workflows. Fixes 8 locations across 4 files.

## Summary

**9 files changed, 2 files deleted, 2 files created.** Changes are documentation + one YAML fix.

| File | Action |
|------|--------|
| `README.md` | 6 edits (tree, config table, descriptions, new sections) |
| `docs/getting-started.md` | 7 edits (breadcrumb, tree fix, config table, new `.claude/rules/` section, global rules scope x3) |
| `workflows/project_team/README.md` | 2 edits (breadcrumb, agent roster) |
| `template/workflows/project_team/README.md` | 2 edits (same as above, adjusted links) |
| `workflows/project_team/project_team.yaml` | 1 edit (phantom rule fix) |
| `.claude/rules/guardrails-system.md` | 1 edit (global rules scope fix) |
| `template/.claude/rules/guardrails-system.md` | 1 edit (same fix, template copy) |
| `.claude/commands/init_project.md` | **DELETE** |
| `template/.claude/commands/init_project.md` | **DELETE** |
| `.claude/commands/git_setup.md` | **NEW FILE** |
| `template/.claude/commands/git_setup.md` | **NEW FILE** |

---

## FILE 1: `README.md`

### Change 1A: Fix project tree

Remove `/project-team` miscategorization (it's a workflow, not a command). Remove `/init_project` (being deleted). Add `/git_setup`. Clarify `.claude/rules/` as agent context files in developer mode only. Fix `global/rules.yaml` scope description.

**Do NOT add `settings.json`** to the tree (Skeptic: it's managed by claudechic, showing it implies user editing).

**Lines 18-39.** Replace the tree block:

CURRENT:
```
my-project/
├── .claude/
│   ├── commands/           # Claude Code skills (/project-team, /init_project)
│   └── rules/              # Context rule files (auto-loaded by glob for agent guidance)
├── workflows/              # Workflow YAML + role directories (identity.md, phase files)
│   ├── project_team/       #   Multi-agent roles (coordinator/, implementer/, skeptic/, etc.)
│   └── tutorial/           #   Tutorial workflow
├── global/                 # Global configuration
│   ├── rules.yaml          #   Runtime rules (active during workflows)
│   └── hints.yaml          #   Hints configuration
├── commands/
│   └── claudechic          # CLI wrapper (added to PATH by activate)
├── mcp_tools/              # MCP tool plugins (auto-discovered by claudechic)
├── repos/                  # Your codebases (symlinked/copied, added to PYTHONPATH)
├── submodules/             # (developer mode only)
│   └── claudechic/         #   Core systems: hints, checks, guardrails, workflows engine
├── envs/                   # Environment configurations
├── scripts/                # Utility scripts
├── activate                # Source this to set up your environment
├── pixi.toml               # Package manager config
└── .copier-answers.yml     # Template answers (for copier update)
```

REPLACEMENT:
```
my-project/
├── .claude/
│   ├── commands/           # Slash commands (/git_setup)
│   └── rules/              # Agent context files (developer mode only -- see docs)
├── workflows/              # Workflow definitions + agent role directories
│   ├── project_team/       #   Multi-agent workflow (coordinator/, implementer/, skeptic/, ...)
│   ├── tutorial/           #   Tutorial workflow
│   └── ...                 #   Additional workflows (tutorial_extending, etc.)
├── global/                 # Global configuration
│   ├── rules.yaml          #   Project rules (always active when claudechic is running)
│   └── hints.yaml          #   Contextual tips shown to agents (feature discovery, workflow guidance)
├── commands/
│   └── claudechic          # Type this to get started
├── mcp_tools/              # MCP tool plugins (auto-discovered by claudechic)
├── repos/                  # Your codebases (symlinked/copied, added to PYTHONPATH)
├── submodules/             # Developer mode only — for editing claudechic source
│   └── claudechic/         #   Core systems: hints, checks, guardrails, workflows engine
├── envs/                   # Environment configurations
├── scripts/                # Utility scripts
├── activate                # Source this to set up your environment
├── pixi.toml               # Package manager config
└── .copier-answers.yml     # Template answers (for copier update)
```

What changed:
- `.claude/commands/` comment: `"Claude Code skills (/project-team, /init_project)"` -> `"Slash commands (/git_setup)"` -- removed workflow miscategorization, removed deleted `/init_project`, added `/git_setup`
- `.claude/rules/` comment: `"Context rule files (auto-loaded by glob for agent guidance)"` -> `"Agent context files (developer mode only -- see docs)"` -- emphasizes these are for agents (not guardrails), adds developer-mode caveat
- `workflows/project_team/` comment: `"Multi-agent roles"` -> `"Multi-agent workflow"`
- `workflows/` section: added `...` ellipsis entry to indicate additional workflows exist
- `global/rules.yaml` comment: `"Runtime rules (active during workflows)"` -> `"Project rules (always active when claudechic is running)"` -- **CRITICAL scope fix**
- `global/hints.yaml` comment: `"Hints configuration"` -> `"Contextual tips shown to agents (feature discovery, workflow guidance)"`

---

### Change 1B: Fix Configuration Options table

Add `project_name` and `quick_start` (both missing). Keep friendly names with variable names in parentheses (Skeptic: matches the rest of the README's tone). Fix misleading rows.

**Lines 42-56.** Replace:

CURRENT:
```markdown
## Configuration Options

The installer asks these questions:

| Option | Default | Description |
|--------|---------|-------------|
| **Guardrails** | yes | Permission system for Claude Code tool calls |
| **Project team** | yes | Multi-agent workflow (Coordinator, Implementer, Skeptic) |
| **Pattern miner** | no | Scans session history for user corrections |
| **Target platform** | auto | Which OS to solve dependencies for |
| **Claudechic mode** | standard | Standard (git URL) or developer (local editable) |
| **Cluster** | no | HPC job management (LSF or SLURM) |
| **Git init** | yes | Initialize a git repo with initial commit |
| **Existing codebase** | — | Path to integrate an existing project |
```

REPLACEMENT:
```markdown
## Configuration Options

The installer asks these questions (see [getting-started guide](docs/getting-started.md) for full details including quick start presets):

| Option | Default | Description |
|--------|---------|-------------|
| **Project name** (`project_name`) | *(required)* | Directory name and pixi environment name |
| **Quick start** (`quick_start`) | `defaults` | How much example content to include (`everything` / `defaults` / `empty` / `custom`) |
| **Target platform** (`target_platform`) | `auto` | Which OS to solve dependencies for |
| **Claudechic mode** (`claudechic_mode`) | `standard` | Standard (git URL) or developer (local editable) |
| **Cluster** (`use_cluster`) | `false` | HPC job management (LSF or SLURM) |
| **Git init** (`init_git`) | `true` | Initialize a git repo with initial commit |
| **Existing codebase** (`existing_codebase`) | *(empty)* | Path to integrate an existing project |
```

What changed:
- Added cross-reference to getting-started.md
- Added `Project name` and `Quick start` rows (both were missing)
- Removed `Guardrails` and `Project team` rows (these aren't copier prompts -- they're always-included infrastructure)
- Removed `Pattern miner` standalone row (it's a `quick_start` sub-option)
- Added variable names in parentheses after each friendly name
- Fixed defaults to match `copier.yml` values

---

### Change 1C: Clarify `/project-team` is a workflow in Usage section

**Line 65.** Replace:

CURRENT:
```markdown
In claudechic, run `/project-team` to start the multi-agent workflow.
```

REPLACEMENT:
```markdown
In claudechic, type `/project-team` to start the multi-agent workflow. (This is a claudechic workflow, not a Claude Code slash command.)
```

---

### Change 1D: Fix Multi-Agent Project Team heading (was 1E)

**Lines 92-93.** Replace:

CURRENT:
```markdown
### Multi-Agent Project Team

Run `/project-team` in claudechic to start the structured workflow:
```

REPLACEMENT:
```markdown
### Multi-Agent Project Team

Type `/project-team` in claudechic to start the structured workflow:
```

---

### Change 1E: Flesh out "Core Systems" section

**Lines 102-104.** Replace:

CURRENT:
```markdown
### Core Systems (via claudechic)
Hints · Advance Checks · Rules · Phases · Workflows · Chicsessions
→ See [docs/getting-started.md](docs/getting-started.md) for details.
```

REPLACEMENT:
```markdown
### Core Systems (via claudechic)

claudechic provides several interlocking systems beyond guardrails:

- **Workflows** -- phase-gated processes that structure multi-agent collaboration
- **Phases** -- named workflow stages with scoped rules, hints, and advance checks
- **Hints** -- contextual toast notifications surfaced to agents during workflows
- **Advance Checks** -- gate conditions that must pass before a phase transition proceeds
- **Chicsessions** -- named multi-agent session snapshots for save/restore

→ See [docs/getting-started.md](docs/getting-started.md) for full documentation.
```

---

### Change 1F: Add `.claude/rules/` documentation paragraph

**Insert after line 83** (after the end of the "Guardrails & Rules" section, before "### MCP Tools"):

```markdown
### Agent Context Files (`.claude/rules/`)

In developer mode (`claudechic_mode=developer`), the generated project includes `.claude/rules/*.md` files. These are **agent context files** -- Claude Code's native rules system that auto-loads guidance when agents touch files matching configured glob patterns. They document claudechic internals (hints, checks, guardrails, workflows, manifest YAML) and are distinct from the guardrail/runtime rule systems described above. See [docs/getting-started.md](docs/getting-started.md) for details on each file.
```

---

## FILE 2: `workflows/project_team/README.md` (repo root)

### Change 2A: Add navigation breadcrumb

**Insert after line 2** (after the subtitle "A structured multi-agent workflow..."):

```markdown

> **Part of [AI_PROJECT_TEMPLATE](../../README.md)** · Full setup guide: [docs/getting-started.md](../../docs/getting-started.md)
```

### Change 2B: Add Git Setup to Advisory agent roster

**Insert after line 76** (after the Project Integrator row, before the `---` separator):

```markdown
| **Git Setup** | `git_setup/identity.md` | Creates GitHub repos, initializes git, saves user prompts. |
```

---

## FILE 3: `template/workflows/project_team/README.md`

Same content changes as File 2, but with adjusted relative links for the template context.

### Change 3A: Add navigation breadcrumb

**Insert after line 2** (after the subtitle):

```markdown

> **Part of AI_PROJECT_TEMPLATE** · Full setup guide: see `docs/getting-started.md` in the project root
```

(Template version uses plain text references since the relative paths from `template/workflows/project_team/` to the repo-root docs are fragile across copier generation.)

### Change 3B: Add Git Setup to Advisory agent roster

**Insert after line 76** (after the Project Integrator row):

```markdown
| **Git Setup** | `git_setup/identity.md` | Creates GitHub repos, initializes git, saves user prompts. |
```

(Identical to Change 2B.)

---

## FILE 4: `workflows/project_team/project_team.yaml`

### Change 4A: Fix phantom `no_force_push` rule

The `no_force_push` rule (line 62-67) has `detect.pattern` but no `detect.type`, making it inconsistent. The regex alternation `|` requires explicit `regex_match` type.

**Lines 62-67.** Replace:

CURRENT:
```yaml
  - id: no_force_push
    trigger: PreToolUse/Bash
    enforcement: deny
    detect:
      pattern: "git push.*--force|git push.*-f"
    message: "Force push is never allowed"
```

REPLACEMENT:
```yaml
  - id: no_force_push
    trigger: PreToolUse/Bash
    enforcement: deny
    detect:
      type: regex_match
      pattern: "git push.*--force|git push.*-f"
    message: "Force push is never allowed"
```

What changed: Added `type: regex_match` to the `detect` block.

---

## FILE 5: `docs/getting-started.md`

### Change 5A: Add navigation breadcrumb

**Insert after line 1** (after the `# Getting Started with AI_PROJECT_TEMPLATE` title, before the audience note):

```markdown

> **[Back to README](../README.md)**
```

### Change 5B: Fix project tree -- replace `/init_project` with `/git_setup`, fix global rules scope

**Lines 172 and 184-185.** Two changes in the project tree:

**Line 172.** Replace:

CURRENT:
```
│   ├── rules.yaml               #   Runtime rules (active during workflows)
```

REPLACEMENT:
```
│   ├── rules.yaml               #   Project rules (always active when claudechic is running)
```

**Lines 184-185.** Replace:

CURRENT:
```
│   └── commands/
│       └── init_project.md      #   /init_project slash command
```

REPLACEMENT:
```
│   └── commands/
│       └── git_setup.md         #   /git_setup slash command
```

### Change 5C: Fix Layer 2 description -- global rules are always active

**Lines 231-238.** Replace:

CURRENT:
```markdown
### Layer 2: Global Rules (Active During Workflows)

**File:** `global/rules.yaml`
**Processed by:** claudechic workflow engine (runtime)
**Scope:** Active whenever any workflow is running

These are runtime rules loaded by claudechic's ManifestLoader. They apply
during all workflow sessions.
```

REPLACEMENT:
```markdown
### Layer 2: Global Rules (Always Active)

**File:** `global/rules.yaml`
**Processed by:** claudechic guardrails engine (runtime)
**Scope:** Always active when claudechic is running

These are project-level rules loaded by claudechic's ManifestLoader. They apply
to every claudechic session, regardless of whether a workflow is active.
```

### Change 5D: Fix glossary -- runtime rule definition

**Line 492.** Replace:

CURRENT:
```markdown
| **Runtime rule** | Rule in `global/rules.yaml` or workflow YAML — active during workflows (covers both global and phase-scoped rules) |
```

REPLACEMENT:
```markdown
| **Global rule** | Rule in `global/rules.yaml` — always active when claudechic is running; user-editable project configuration |
| **Workflow rule** | Rule in workflow YAML (e.g., `project_team.yaml`) — active only when that workflow is running; can be scoped to phases/roles |
```

What changed: Split the misleading "Runtime rule" entry into two distinct terms that accurately reflect their different scoping behavior. The old entry conflated always-active global rules with workflow-scoped rules under a single name.

### Change 5E: Add `.claude/rules/` documentation section

**Insert after line 201** (after the "Key paths to remember" agent box, before the `---` separator on line 202):

```markdown

### Agent Context Files (`.claude/rules/`)

In developer mode (`claudechic_mode=developer`), the generated project includes
`.claude/rules/*.md` files. These are **agent context files** -- Claude Code's
native rules system that auto-loads guidance when agents touch files matching
configured glob patterns. They document claudechic internals and are distinct
from the guardrail/runtime rule systems described above.

| File | What It Documents |
|------|------------------|
| `hints-system.md` | Hints pipeline: activation, trigger, lifecycle, sort, budget, present |
| `checks-system.md` | Check protocol, advance checks, AND semantics, check-to-hint adapter |
| `guardrails-system.md` | Guardrail rule evaluation, hook integration |
| `workflows-system.md` | ManifestLoader, WorkflowEngine, phases, chicsessions |
| `manifest-yaml.md` | YAML manifest format, sections, namespace qualification |
| `claudechic-overview.md` | High-level system overview |

These files are **not present** in standard mode (`claudechic_mode=standard`)
because they reference `submodules/` paths that only exist in developer mode
(see `copier.yml` `_exclude` logic).

> **For Agents:** These context files guide your behavior when you interact
> with claudechic internals. You don't need to read them manually -- Claude Code
> loads them automatically when relevant files are accessed.
```

### Change 5F: Add all missing conditional options to config table

The table on lines 64-73 claims "every option" but is missing 7 conditional sub-options. Split into main + conditional tables.

**Lines 62-73.** Replace:

CURRENT:
```markdown
Copier will ask you to configure your project. Here is every option:

| Prompt | Default | What It Does |
|--------|---------|-------------|
| **project_name** | *(required)* | Names your project directory and pixi environment |
| **quick_start** | `defaults` | How much example content to include (see below) |
| **target_platform** | `auto` | Platform to solve dependencies for (`linux-64`, `osx-arm64`, `win-64`, or `all`) |
| **claudechic_mode** | `standard` | `standard` installs from git; `developer` clones locally for editing |
| **use_cluster** | `false` | Enables HPC job management tools |
| **cluster_scheduler** | `lsf` | `lsf` (bsub/bjobs) or `slurm` (sbatch/squeue) — only if cluster enabled |
| **init_git** | `true` | Creates a git repo with initial commit |
| **existing_codebase** | *(empty)* | Path to existing code to integrate into `repos/` |
```

REPLACEMENT:
```markdown
Copier will ask you to configure your project. Here is every option:

| Prompt | Default | What It Does |
|--------|---------|-------------|
| **project_name** | *(required)* | Names your project directory and pixi environment |
| **quick_start** | `defaults` | How much example content to include (see below) |
| **target_platform** | `auto` | Platform to solve dependencies for (`linux-64`, `osx-arm64`, `win-64`, or `all`) |
| **claudechic_mode** | `standard` | `standard` installs from git; `developer` clones locally for editing |
| **use_cluster** | `false` | Enables HPC job management tools |
| **init_git** | `true` | Creates a git repo with initial commit |
| **existing_codebase** | *(empty)* | Path to existing code to integrate into `repos/` |

**Conditional options** -- these appear only when a parent option enables them:

| Prompt | Default | Condition | What It Does |
|--------|---------|-----------|-------------|
| **cluster_scheduler** | `lsf` | `use_cluster` is true | `lsf` (bsub/bjobs) or `slurm` (sbatch/squeue) |
| **cluster_ssh_target** | *(empty)* | `use_cluster` is true | SSH login node (leave empty if scheduler is available locally) |
| **codebase_link_mode** | `symlink` | `existing_codebase` is set | `symlink` (saves disk, changes reflect immediately) or `copy` (works everywhere) |
| **example_rules** | `true` | `quick_start` is `custom` | Include example guardrail rules in `global/rules.yaml` |
| **example_agent_roles** | `true` | `quick_start` is `custom` | Include specialist agent roles beyond the core 7 |
| **example_workflows** | `true` | `quick_start` is `custom` | Include tutorial workflows |
| **example_hints** | `true` | `quick_start` is `custom` | Include global hints (welcome message + workflow tips) |
| **example_patterns** | `false` | `quick_start` is `custom` | Include the pattern miner (session history analysis) |
```

What changed:
- Moved `cluster_scheduler` from main table to conditional table (it's gated behind `use_cluster`)
- Added 7 previously missing options: `cluster_ssh_target`, `codebase_link_mode`, and all 5 `example_*` sub-options
- Split into two tables with "Conditional options" subheading

---

## FILE 6: `.claude/rules/guardrails-system.md` (repo root)

### Change 6A: Fix global rules scope in terminology section

**Line 14.** Replace:

CURRENT:
```markdown
- **Runtime rule** — rules in `global/rules.yaml` or workflow YAML, active during workflows.
```

REPLACEMENT:
```markdown
- **Global rule** — rules in `global/rules.yaml`, always active when claudechic is running.
- **Workflow rule** — rules in workflow YAML, active only when that workflow is running.
```

What changed: Split "Runtime rule" into two accurate terms. Global rules are always active (the hooks.py namespace filter `rule.namespace != "global"` means global rules are never skipped). Workflow rules are only active when their workflow is active.

---

## FILE 7: `template/.claude/rules/guardrails-system.md`

### Change 7A: Same fix as Change 6A

**Line 14.** Identical replacement as Change 6A. This is the template copy that ships to generated projects.

---

## FILES TO DELETE

### Delete 1: `.claude/commands/init_project.md` (repo root)

Delete this file entirely. The `/init_project` slash command is being removed.

### Delete 2: `template/.claude/commands/init_project.md`

Delete this file entirely. This is the template version that ships to generated projects.

---

## FILES TO CREATE

### New File 1: `.claude/commands/git_setup.md` (repo root)

```markdown
# Git Setup

You are now the Git Setup agent. Read and follow your role identity:

$PROJECT_ROOT/workflows/project_team/git_setup/identity.md

Follow those instructions exactly. You handle initial git setup for new project components.
```

The slash command transforms the current agent into the git_setup role by pointing it at the identity.md file. The identity.md already has all the instructions -- keep the command minimal.

### New File 2: `template/.claude/commands/git_setup.md`

**Identical content** to New File 1. This ensures the command ships to generated projects.

---

## SCOPE BOUNDARIES -- What NOT to Change

1. **Phase counts**: Do NOT reconcile the 4-phase (README, PT/README) vs 7-phase (getting-started.md) descriptions. User decision: this is intentional -- README/PT show user-facing phases, getting-started shows the full YAML phases.
2. **getting-started.md content depth**: Do NOT remove the deep system documentation (ManifestLoader, TriggerCondition, etc.). It belongs there as the comprehensive reference.
3. **PT/README workflow sections**: Do NOT restructure the 4-section workflow description (Vision/Spec/Impl/Testing). It's the correct operational view.
4. **Guardrail rules table** in getting-started.md: Do NOT change -- already correct.
5. **claudechic section** in README (lines 69-77): Do NOT change -- already well-written.
6. **Development section** in README (lines 111-128): Do NOT change.
7. **copier.yml**: Do NOT change -- the `_exclude` rule for `.claude/rules/` already correctly gates on `claudechic_mode`.
8. **Quick Start Preset Reference table** in getting-started.md (lines 425-441): Do NOT change -- already correct and comprehensive.
9. **Glossary** in getting-started.md: Only change the "Runtime rule" entry (Change 5D). Do NOT change other glossary entries.
10. **`.project_team/` spec files**: Do NOT update old references in `.project_team/` subdirectories -- these are historical project specs, not live documentation.
11. **`hooks.py` or other code**: This audit is docs-only. Do NOT change any Python code.
