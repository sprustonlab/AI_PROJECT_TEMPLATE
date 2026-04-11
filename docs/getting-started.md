# Getting Started with AI_PROJECT_TEMPLATE

> **[Back to README](../README.md)**

> This guide is for **humans** and **agents**. Sections marked with
> **For Humans** or **For Agents** contain audience-specific details.
> Everything else applies to both.

---

## What Is AI_PROJECT_TEMPLATE?

AI_PROJECT_TEMPLATE is a Copier-based project generator for Claude Code. It creates
ready-to-use project directories with:

- **Guardrails** — rule-based permission system that controls what Claude Code
  tool calls are allowed (deny, warn, or log)
- **Project Team** — multi-agent workflow with Coordinator, Implementer, Skeptic,
  and 14 other specialized agent roles
- **Workflows** — phase-gated processes defined in YAML, with advance checks
  that gate transitions between phases
- **Hints** — contextual toast notifications that help you discover features
- **Cluster tools** — optional HPC job submission (LSF or SLURM)

You generate a new project with `copier copy`, answer a few prompts, and get a
working project with all selected features wired together.

---

## Prerequisites

| Requirement | Why |
|------------|-----|
| **Python 3.10+** | claudechic and guardrails require it |
| **Git** | Copier reads templates from git repos |
| **Claude Code** | The generated project is a Claude Code workspace |
| **pixi** (optional) | Manages environments; auto-installed by `activate` if missing |

> **For Agents:** Verify prerequisites programmatically:
> ```bash
> python3 --version   # >= 3.10
> git --version
> which pixi || echo "pixi will be installed by activate script"
> ```

---

## Installation

### Step 1: Generate a Project

```bash
copier copy https://github.com/sprustonlab/AI_PROJECT_TEMPLATE my-project
```

Or from a local clone:

```bash
copier copy /path/to/AI_PROJECT_TEMPLATE my-project
```

### Step 2: Answer the Prompts

Copier will ask you to configure your project. Here is every option:

| Prompt | Default | What It Does |
|--------|---------|-------------|
| **project_name** | *(required)* | Names your project directory and pixi environment |
| **quick_start** | `defaults` | How much example content to include (see below) |
| **target_platform** | `auto` | Platform to solve dependencies for (`linux-64`, `osx-arm64`, `win-64`, or `all`) |
| **claudechic_mode** | `standard` | `standard` installs from git; `developer` clones locally for editing |
| **use_cluster** | `false` | Enables HPC job management tools |
| **init_git** | `true` | Creates a git repo with initial commit |
| **use_existing_codebase** | `false` | Record intent to integrate an existing codebase (the codebase-setup workflow guides you through it) |

**Conditional options** -- these appear only when a parent option enables them:

| Prompt | Default | Condition | What It Does |
|--------|---------|-----------|-------------|
| **example_rules** | `true` | `quick_start` is `custom` | Include example global rules in `global/rules.yaml` |
| **example_agent_roles** | `true` | `quick_start` is `custom` | Include specialist agent roles beyond the core 7 |
| **example_workflows** | `true` | `quick_start` is `custom` | Include tutorial workflows |
| **example_hints** | `true` | `quick_start` is `custom` | Include global hints (welcome message + workflow tips) |
| **example_patterns** | `false` | `quick_start` is `custom` | Include the pattern miner (session history analysis) |

The **quick_start** preset controls how much example content ships with your project.
Infrastructure (guardrails, workflows, hints engine, Project Team) is always included.

| Preset | Example content included |
|--------|------------------------|
| **everything** | All example rules, specialist agent roles, tutorial workflows, hints, pattern miner |
| **defaults** | Example rules, specialist roles, onboarding hints. No tutorials, no pattern miner. |
| **empty** | Infrastructure only — no examples, no tutorials, no hints |
| **custom** | You choose each category individually (rules, roles, workflows, hints, patterns) |

> **For Humans:** If unsure, accept `defaults`. You get all infrastructure plus
> useful examples — the recommended setup. Choose `everything` if you want to
> explore the full system. Use `copier update` later to pull template updates.

> **For Agents:** To generate non-interactively:
> ```bash
> copier copy --trust --defaults \
>   --data project_name=my-project \
>   --data quick_start=defaults \
>   --data target_platform=linux-64 \
>   --data claudechic_mode=standard \
>   --data use_cluster=false \
>   --data init_git=true \
>   --data use_existing_codebase=false \
>   https://github.com/sprustonlab/AI_PROJECT_TEMPLATE my-project
> ```

### Step 3: Activate

```bash
cd my-project
source activate
```

The activate script:
1. Installs pixi if needed
2. Runs `pixi install` to set up environments
3. Adds `commands/` to your PATH
4. Displays a status summary of all project features

### Step 4: Verify

```bash
pixi run claudechic    # Start the claudechic TUI
```

> **For Agents:** Verify the generated project programmatically:
> ```bash
> # Check Claude Code settings exist
> test -f .claude/settings.json && echo "settings: OK"
>
> # Check global rules are configured
> test -f global/rules.yaml && echo "global rules: OK"
>
> # Check Project Team agent roles exist
> ls workflows/project_team/*/identity.md    # Should list coordinator, implementer, etc.
>
> # Check workflows exist
> ls workflows/project_team/project_team.yaml && echo "workflows: OK"
>
> # Check pixi.toml is valid
> grep '^\[dependencies\]' pixi.toml && echo "pixi: OK"
> ```

---

## Project Layout

After generation with all features enabled, your project looks like this:

```
my-project/
├── activate                     # Source this to set up the environment
├── pixi.toml                    # Dependency management (pixi)
├── .copier-answers.yml          # Your template answers (for copier update)
│
├── workflows/project_team/      # Agent role directories
│   ├── coordinator/identity.md  #   Lead agent — delegates, never codes
│   ├── implementer/identity.md  #   Writes code
│   ├── skeptic/identity.md      #   Critical review
│   ├── composability/identity.md#   Architecture
│   ├── terminology/identity.md  #   Naming consistency
│   ├── user_alignment/identity.md#  User intent verification
│   ├── test_engineer/identity.md#   Testing
│   └── ... (8 more roles)
│
├── workflows/                   # Workflow definitions (YAML + phase files)
│   ├── project_team/            #   Project Team workflow
│   │   ├── project_team.yaml    #     Workflow definition
│   │   ├── coordinator/         #     Phase files for coordinator role
│   │   ├── implementer/         #     Phase files for implementer role
│   │   └── ...
│   └── tutorial/                #   Tutorial workflow
│       ├── tutorial.yaml
│       └── learner/
│
├── global/                      # Global configuration
│   ├── rules.yaml               #   Project rules (always active when claudechic is running)
│   └── hints.yaml               #   Global hints (shown on workflow activation)
│
├── .claude/
│   ├── settings.json            #   Claude Code settings (managed by claudechic)
│   ├── rules/                   #   Context rule files (agent guidance)
│   │   ├── hints-system.md      #     Hints system context
│   │   ├── checks-system.md     #     Checks system context
│   │   ├── guardrails-system.md #     Guardrails system context
│   │   ├── workflows-system.md  #     Workflows system context
│   │   ├── manifest-yaml.md     #     Manifest YAML context
│   │   └── claudechic-overview.md #   Overview context
│   └── commands/
│       └── git_setup.md         #   /git_setup slash command
│
├── commands/                    # CLI commands (added to PATH by activate)
├── scripts/                     # Utility scripts
├── repos/                       # Your integrated codebases
├── envs/                        # Environment configurations
└── mcp_tools/                   # Custom MCP tools (optional)
```

> **For Agents:** Key paths to remember:
> - Agent roles: `workflows/project_team/<role>/identity.md`
> - Workflow YAML: `workflows/<workflow_name>/<workflow_name>.yaml`
> - Phase files: `workflows/<workflow_name>/<role>/<phase>.md`
> - Global rules: `global/rules.yaml`
> - Context rule files: `.claude/rules/*.md`
> - Project state: `.project_team/<project_name>/STATUS.md`

### Agent Context Files (`.claude/rules/`)

In developer mode (`claudechic_mode=developer`), the generated project includes
`.claude/rules/*.md` files. These are **agent context files** -- Claude Code's
native rules system that auto-loads guidance when agents touch files matching
configured glob patterns. They document claudechic internals and are distinct
from the guardrails engine and rule systems described above.

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

---

## Understanding the Rule System

claudechic's guardrails engine evaluates rules on every tool call. Rules are
defined in YAML manifests at two scopes:

### Global Rules (Always Active)

**File:** `global/rules.yaml`
**Scope:** Always active when claudechic is running

These are project-level rules loaded by the ManifestLoader. They apply to every
claudechic session, regardless of whether a workflow is active.

**Default rules** (shipped with `quick_start=defaults` or `everything`):

| ID | Enforcement | What It Does |
|----|-------------|-------------|
| no_rm_rf | `deny` | Blocks `rm -rf` on absolute paths |
| warn_sudo | `warn` | Warns when using `sudo` |
| log_git_operations | `log` | Silently logs all git operations |

### Workflow Rules (Scoped to Active Workflow)

**File:** `rules:` section in workflow YAML (e.g., `workflows/project_team/project_team.yaml`)
**Scope:** Active only when that workflow is running; can be scoped to specific phases or roles

**Rules in `project_team.yaml`:**

| ID | Enforcement | Scope | What It Does |
|----|-------------|-------|-------------|
| no_direct_code_coordinator | `warn` | coordinator role | Reminds Coordinator to delegate code writing |
| no_push_before_testing | `deny` | all phases except testing/signoff | Blocks `git push` until testing |
| no_force_push | `deny` | all phases | Blocks force push entirely |

### How Rules Interact

Rules are additive across both scopes. A `deny` at any scope blocks the action.
A `warn` at any scope shows a warning. Rules do not override each other.

To add a custom rule, edit `global/rules.yaml` (always active) or add it to
a workflow's YAML `rules:` section (workflow-scoped).

---

## Core Systems

claudechic provides several core systems that work together. The rule system above is part of the guardrails engine; the others are summarized here.

### Hints

Advisory toast notifications surfaced to agents during workflows. A 6-stage
pipeline (activation → trigger → lifecycle → sort → budget → present) selects
which hints to show. Each hint has a **trigger condition** — a `TriggerCondition`
protocol implementation whose `check(state)` method decides whether the hint is
relevant. Hints are defined in manifests (`global/hints.yaml` or inline in
workflow YAML) and can also be generated from failed advance checks via the
checks-to-hints adapter. State is persisted to `.claude/hints_state.json`.

→ See `.claude/rules/hints-system.md` (context rule file) and `submodules/claudechic/claudechic/hints/` for details.

### Checks

A verification protocol used primarily as **advance checks** — the gate
conditions that control phase transitions. The `Check` protocol defines
`async def check(self) -> CheckResult`. Built-in types include
`command-output-check`, `file-exists-check`, `file-content-check`, and
`manual-confirm`. Advance checks use AND semantics: all must pass (sequential,
short-circuit on first failure) before a phase transition proceeds. Failed
checks are bridged into the hints pipeline via `check_failed_to_hint()`.

→ See `.claude/rules/checks-system.md` (context rule file) and `submodules/claudechic/claudechic/checks/` for details.

### Workflows, Phases & Chicsessions

The orchestration layer. A **ManifestLoader** discovers and parses all manifest
files (`global/*.yaml` + `workflows/*/*.yaml`), dispatching sections to
registered parsers. The `WorkflowEngine` manages phase state and executes
advance checks at phase boundaries. **Phases** are named stages containing
`advance_checks` and `hints` declarations. Agent prompts are assembled from
`identity.md` + `{phase}.md` files in each role directory.

**Chicsessions** are named multi-agent session snapshots stored at
`.chicsessions/{name}.json`. They capture `workflow_state` as an opaque dict,
enabling save/restore of the full multi-agent context.

→ See `.claude/rules/workflows-system.md` (context rule file) and `submodules/claudechic/claudechic/workflows/` for details.

---

## Common Workflows

### Starting a Project Team Session

> **For Humans:**
>
> 1. Open Claude Code in your project directory
> 2. Type `/project-team` and describe what you want to build
> 3. The Coordinator agent takes over — it will:
>    - Ask clarifying questions about your vision
>    - Spawn Leadership agents (Composability, Skeptic, etc.)
>    - Present a specification for your approval
>    - Spawn Implementer agents to write code
>    - Run tests via TestEngineer
>    - Present the finished work for sign-off
> 4. You interact at decision points — approve, modify, or redirect

> **For Agents:**
>
> To start a Project Team session programmatically:
> 1. Read `workflows/project_team/coordinator/identity.md` for behavioral instructions
> 2. The workflow YAML (`workflows/project_team/project_team.yaml`) defines 7 phases:
>    - **vision** — understand user intent
>    - **setup** — determine working directory, check for existing state
>    - **leadership** — spawn Composability, TerminologyGuardian, Skeptic, UserAlignment
>    - **specification** — synthesize findings, present to user (advance check: manual-confirm)
>    - **implementation** — spawn Implementers, delegate work (advance check: manual-confirm)
>    - **testing** — spawn TestEngineer, run tests (advance check: manual-confirm)
>    - **signoff** — final user sign-off
> 3. Agent state is stored in `.project_team/<project_name>/STATUS.md`
> 4. Inter-agent communication uses claudechic MCP tools:
>    - `mcp__chic__spawn_agent` — create a new agent
>    - `mcp__chic__ask_agent` — send message, wait for reply (reliable)
>    - `mcp__chic__tell_agent` — fire-and-forget message
>    - `mcp__chic__advance_phase` — move to next workflow phase
>    - `mcp__chic__get_phase` — query current phase
>    - `mcp__chic__whoami` — check your own agent identity
>    - `mcp__chic__list_agents` — list all running agents and their status

### Running the Tutorial

```bash
# In Claude Code, type:
/tutorial
```

The tutorial workflow teaches you the basics in 4 phases:
1. **basics** — workflow activation, phases, and hints
2. **rules** — deny, warn, and log enforcement in action
3. **checks** — advance checks and phase transitions
4. **graduation** — you've seen all features

Each phase has advance checks — you create marker files
(`tutorial_basics_done.txt`, etc.) and call `advance_phase` to progress.

### Adding Global and Workflow Rules

Global and workflow rules are defined in YAML manifests. To add a global rule (active
during all workflows), edit `global/rules.yaml`:

```yaml
rules:
  - id: my-custom-rule
    trigger: PreToolUse/Bash
    enforcement: warn
    detect:
      type: regex_match
      pattern: 'some-pattern'
    message: "Explanation of why this was flagged."
```

To add a workflow-scoped rule, add it to the `rules:` section of the
workflow's YAML file (e.g., `workflows/project_team/project_team.yaml`).
Workflow rules can be scoped to specific `phases` or `roles`.

### Using Developer Mode (claudechic)

If you chose `claudechic_mode=developer` during setup:
- claudechic is cloned into `submodules/claudechic/`
- `pixi.toml` references it as `{ path = "submodules/claudechic", editable = true }`
- You can edit claudechic source directly and changes take effect immediately

To switch from standard to developer mode later:
```bash
git clone https://github.com/sprustonlab/claudechic submodules/claudechic
# Edit pixi.toml: change the claudechic line to:
# claudechic = { path = "submodules/claudechic", editable = true }
pixi install
```

---

## Quick Start Preset Reference

The `quick_start` preset controls example content. Infrastructure always ships.
The `use_cluster` toggle is separate (hardware capability, not example content).

| Category | `everything` | `defaults` | `empty` | `custom` |
|----------|:---:|:---:|:---:|:---:|
| Guardrails infrastructure | ✅ | ✅ | ✅ | ✅ |
| Core 7 agent roles | ✅ | ✅ | ✅ | ✅ |
| Project Team workflow YAML | ✅ | ✅ | ✅ | ✅ |
| Hints engine (`hints/`) | ✅ | ✅ | ✅ | ✅ |
| Example global rules (`global/rules.yaml`) | ✅ | ✅ | ❌ | per `example_rules` |
| Specialist agent roles (8 extra) | ✅ | ✅ | ❌ | per `example_agent_roles` |
| Onboarding hints (`global/hints.yaml`) | ✅ | ✅ | ❌ | per `example_hints` |
| Tutorial workflows | ✅ | ❌ | ❌ | per `example_workflows` |
| Pattern miner | ✅ | ❌ | ❌ | per `example_patterns` |
| Cluster tools (`mcp_tools/`) | per `use_cluster` | per `use_cluster` | per `use_cluster` | per `use_cluster` |

> **For Agents:** The gating logic is in `copier.yml` `_exclude` section.
> When example content is excluded, its files don't exist in the generated project
> — they are not present as empty stubs.

---

## Troubleshooting

### "task not found" when running `pixi run claudechic`

The generated `pixi.toml` uses default environment dependencies. Run:
```bash
pixi install
pixi run claudechic
```
If that fails, check that `pixi.toml` has `[dependencies]` and
`[pypi-dependencies]` sections (not `[feature.claudechic.*]`).

### Rules not being enforced

Verify that claudechic is running (`pixi run claudechic`) — rules are
evaluated at runtime by the claudechic engine. Check that
`.claude/settings.json` exists and that your rule YAML is valid.

### Workflow rules appear unexpectedly

Workflow-scoped rules (like `no_push_before_testing` or `no_direct_code_coordinator`)
only fire when their workflow is active. They have no effect outside of that workflow.

### Agent can't find role file

Agent role files live at `workflows/project_team/<role>/identity.md`. If the directory
is empty or missing, re-run `copier update` to add missing files. Core roles
(7) always ship; specialist roles (8) require `quick_start` of `everything` or
`defaults`.

---

## Glossary

| Term | Definition |
|------|-----------|
| **AI_PROJECT_TEMPLATE** | The source repository; scaffolds new projects via Copier |
| **claudechic** | CLI/TUI wrapper and MCP tool infrastructure |
| **Copier template** | `copier.yml` + `template/` directory — generates new projects |
| **Project Team** | Multi-agent workflow system (`workflows/project_team/`) |
| **Agent role** | Markdown file defining one agent's responsibilities |
| **Workflow** | Phase-gated process defined by YAML in `workflows/` |
| **Phase** | Named stage within a workflow; contains `advance_checks` and `hints` |
| **Advance check** | Phase-gating condition in workflow YAML — all must pass (AND semantics) before a phase transition proceeds |
| **Guardrails engine** | claudechic's rule evaluation pipeline — processes all global and workflow rules on every tool call via Claude Code hooks |
| **Global rule** | Rule in `global/rules.yaml` — always active when claudechic is running; user-editable project configuration |
| **Workflow rule** | Rule in workflow YAML (e.g., `project_team.yaml`) — active only when that workflow is running; can be scoped to phases/roles |
| **Context rule file** | `.claude/rules/*.md` file — Claude Code's native rules system; auto-loaded by glob when agents touch matching files |
| **Hook (generated)** | Claude Code hook in `settings.json`, managed by claudechic |
| **Manifest** | Any YAML file parsed by ManifestLoader (`global/*.yaml`, `workflows/*/*.yaml`) — the user-facing configuration surface |
| **ManifestLoader** | Universal parser that discovers manifest files and dispatches sections to registered `ManifestSection[T]` parsers |
| **Hints** | Contextual toast notifications surfaced during workflows via a 6-stage pipeline |
| **Trigger condition** | `TriggerCondition` protocol in the hints system — `check(state) -> bool` decides if a hint is relevant |
| **Chicsession** | Named multi-agent session snapshot at `.chicsessions/{name}.json` — stores `workflow_state` for save/restore |
| **Namespace** | Qualifier prefix for IDs (e.g., `global:`, `project-team:`). Bare names in YAML, qualified at runtime. |
| **Enforcement levels** | `deny` (hard block), `warn` (ack required), `log` (silent audit) |

---

## Next Steps

- **Run the tutorial:** Type `/tutorial` in Claude Code to learn by doing
- **Start a project:** Type `/project-team` and describe your goal
- **Customize rules:** Edit `global/rules.yaml` to add global rules
- **Add MCP tools:** Drop Python files into `mcp_tools/` for custom tools
- **Explore workflows:** Read `workflows/project_team/project_team.yaml` to understand phase definitions
