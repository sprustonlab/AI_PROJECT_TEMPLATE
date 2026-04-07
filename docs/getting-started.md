# Getting Started with AI_PROJECT_TEMPLATE

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
| **use_guardrails** | `true` | Enables the rule-based permission system |
| **use_project_team** | `true` | Enables the multi-agent Project Team workflow |
| **use_pattern_miner** | `false` | Scans session history for recurring corrections |
| **use_hints** | `true` | Shows contextual toast notifications |
| **target_platform** | `auto` | Platform to solve dependencies for (`linux-64`, `osx-arm64`, `win-64`, or `all`) |
| **claudechic_mode** | `standard` | `standard` installs from git; `developer` clones locally for editing |
| **use_cluster** | `false` | Enables HPC job management tools |
| **cluster_scheduler** | `lsf` | `lsf` (bsub/bjobs) or `slurm` (sbatch/squeue) — only if cluster enabled |
| **init_git** | `true` | Creates a git repo with initial commit |
| **existing_codebase** | *(empty)* | Path to existing code to integrate into `repos/` |

> **For Humans:** If unsure, accept all defaults. You get guardrails + Project
> Team + hints — the recommended setup. To change feature toggles later,
> re-run `copier copy` with different answers, or use `copier update` to pull
> template updates while preserving your local changes.

> **For Agents:** To generate non-interactively:
> ```bash
> copier copy --trust --defaults \
>   --data project_name=my-project \
>   --data use_guardrails=true \
>   --data use_project_team=true \
>   --data use_hints=true \
>   --data target_platform=linux-64 \
>   --data claudechic_mode=standard \
>   --data use_cluster=false \
>   --data init_git=true \
>   --data existing_codebase="" \
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
> # Check guardrails are configured
> test -f .claude/settings.json && echo "hooks: OK"
> test -f .claude/guardrails/rules.yaml && echo "rules: OK"
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
│   ├── rules.yaml               #   Global rules (active during workflows)
│   └── hints.yaml               #   Global hints (shown on workflow activation)
│
├── .claude/
│   ├── settings.json            #   Generated hooks (auto-generated, do not edit)
│   ├── guardrails/
│   │   ├── rules.yaml           #   Guardrail rules (always active)
│   │   ├── generate_hooks.py    #   Regenerates hooks from rules
│   │   ├── hooks/               #   Generated hook scripts
│   │   ├── role_guard.py        #   Role-based permission library
│   │   ├── setup_ao_mode.sh     #   Activates team mode
│   │   └── teardown_ao_mode.sh  #   Deactivates team mode
│   ├── commands/
│   │   ├── ao_project_team.md   #   /ao_project_team slash command
│   │   └── init_project.md      #   /init_project slash command
│   └── skills/hints/
│       └── SKILL.md             #   Hints skill definition
│
├── hints/                       # Hint engine (Python)
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
> - Guardrail rules: `.claude/guardrails/rules.yaml`
> - Global rules: `global/rules.yaml`
> - Generated hooks: `.claude/guardrails/hooks/`
> - Project state: `.ao_project_team/<project_name>/STATUS.md`

---

## Understanding the Rule Systems

AI_PROJECT_TEMPLATE has three layers of rules. They are **not duplicates** —
each layer operates at a different scope and is processed by a different engine.

### Layer 1: Guardrail Rules (Always Active)

**File:** `.claude/guardrails/rules.yaml`
**Processed by:** `generate_hooks.py` → Claude Code hooks (`.claude/settings.json`)
**Scope:** Every Claude Code session, always

These are the safety foundation. They generate Claude Code hooks that fire on
every tool call, regardless of whether a workflow is active.

**Default rules:**

| ID | Name | Enforcement | What It Does |
|----|------|-------------|-------------|
| R01 | deny-dangerous-ops | `deny` | Blocks `rm -rf /`, `git push --force`, `git reset --hard` |
| R02 | pip-install-block | `deny` | Blocks direct `pip install` (use `pixi add` instead) |
| R03 | conda-install-block | `deny` | Blocks direct `conda install` (use `pixi add` instead) |
| R04 | subagent-push-block | `deny` | Only Coordinator can `git push` (team mode only) |
| R05 | subagent-guardrail-config-block | `deny` | Only Coordinator can edit guardrail config (team mode only) |

> R04 and R05 are only present when `use_project_team=true`.

**To add a new guardrail rule:**
1. Edit `.claude/guardrails/rules.yaml`
2. Run `python3 .claude/guardrails/generate_hooks.py`
3. Hooks are regenerated in `.claude/guardrails/hooks/`

### Layer 2: Global Rules (Active During Workflows)

**File:** `global/rules.yaml`
**Processed by:** claudechic workflow engine (runtime)
**Scope:** Active whenever any workflow is running

These rules are loaded by claudechic's ManifestLoader and apply during all
workflow sessions. They use a simpler format than guardrail rules.

**Default rules:**

| ID | Enforcement | What It Does |
|----|-------------|-------------|
| no_rm_rf | `deny` | Blocks `rm -rf` on absolute paths |
| warn_sudo | `warn` | Warns when using `sudo` |
| log_git_operations | `log` | Silently logs all git operations |

### Layer 3: Workflow Rules (Phase-Scoped)

**File:** Inline in workflow YAML (`rules:` section)
**Processed by:** claudechic workflow engine (runtime)
**Scope:** Active only during specific workflow phases

These rules are defined inside a workflow's YAML file and can be scoped to
specific phases or roles.

**Example from `project_team.yaml`:**

| ID | Enforcement | Scope | What It Does |
|----|-------------|-------|-------------|
| no_direct_code_coordinator | `warn` | coordinator role | Reminds Coordinator to delegate code writing |
| no_push_before_testing | `deny` | all phases except testing/signoff | Blocks `git push` until testing |
| no_force_push | `deny` | all phases | Blocks force push entirely |

### How the Layers Interact

```
Tool call happens (e.g., Bash with "pip install foo")
    │
    ├── Layer 1: Guardrail hooks fire (always)
    │   └── R02 matches → DENY (blocked before anything else)
    │
    ├── Layer 2: Global rules checked (if workflow active)
    │   └── (no match in this example)
    │
    └── Layer 3: Workflow rules checked (if workflow active + phase matches)
        └── (no match in this example)
```

Rules do NOT override each other. A `deny` at any layer blocks the action.
A `warn` at any layer shows a warning. They are additive.

---

## Common Workflows

### Starting a Project Team Session

> **For Humans:**
>
> 1. Open Claude Code in your project directory
> 2. Type `/ao_project_team` and describe what you want to build
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
> 3. Agent state is stored in `.ao_project_team/<project_name>/STATUS.md`
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

### Editing Guardrail Rules

1. Open `.claude/guardrails/rules.yaml`
2. Add or modify a rule entry:
   ```yaml
   - id: R06
     name: my-custom-rule
     trigger: PreToolUse/Bash
     enforcement: warn
     detect:
       type: regex_match
       pattern: 'some-pattern'
     message: "[R06] Explanation of why this was blocked."
   ```
3. Regenerate hooks:
   ```bash
   python3 .claude/guardrails/generate_hooks.py
   ```
4. The hook scripts in `.claude/guardrails/hooks/` are updated automatically

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

## Feature Toggle Reference

Features are independently toggleable via `copier.yml` answers. Here is what
each toggle includes and excludes:

| Toggle | When ON | When OFF |
|--------|---------|----------|
| `use_guardrails` | `.claude/guardrails/`, `generate_hooks.py`, `rules.yaml`, hooks, `settings.json` | No hooks, no permission checks |
| `use_project_team` | `workflows/project_team/` (see `workflows/project_team/`), `workflows/`, `global/rules.yaml`, `/ao_project_team` command, R04/R05 rules | No agent roles, no workflows, no global rules |
| `use_hints` | `hints/` (Python engine), `.claude/skills/hints/` | No toast notifications |
| `use_project_team` + `use_hints` | `global/hints.yaml` (requires **both** toggles to be ON) | No global workflow hints |
| `use_pattern_miner` | `scripts/mine_patterns.py`, `commands/mine-patterns` | No pattern mining |
| `use_cluster` | `mcp_tools/_cluster.py`, scheduler-specific tools (LSF or SLURM) | No cluster tools |

> **For Agents:** The toggle gating logic is in `copier.yml` `_exclude` section.
> When a feature is off, its files are excluded from the generated project
> entirely — they do not exist as empty stubs.

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

### Guardrail hooks not firing

Hooks may be stale. Regenerate them:
```bash
python3 .claude/guardrails/generate_hooks.py
```
Check that `.claude/settings.json` exists and references the hook scripts.

### "Subagent" rules appear but I have no Project Team

If you see R04/R05 in `rules.yaml` but `use_project_team=false`, your template
may be from before the fix. Regenerate your project or manually remove R04/R05
from `.claude/guardrails/rules.yaml` and re-run `generate_hooks.py`.

### Agent can't find role file

Agent role files live at `workflows/project_team/<role>/identity.md`. If the directory
is empty or missing, check that `use_project_team=true` was set during
`copier copy`. You can re-run `copier update` to add missing files.

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
| **Phase** | Named stage within a workflow |
| **Advance check** | Gate condition for phase transitions |
| **Guardrails** | Permission/safety system — rules generate hooks |
| **Global rule** | Rule in `global/rules.yaml` — active during workflows |
| **Workflow rule** | Rule in workflow YAML `rules:` — active in specific phases |
| **Hook (generated)** | Claude Code hook in `settings.json`, auto-generated from rules |
| **Hints** | Contextual toast notifications |
| **Enforcement levels** | `deny` (hard block), `warn` (ack required), `log` (silent audit) |

---

## Next Steps

- **Run the tutorial:** Type `/tutorial` in Claude Code to learn by doing
- **Start a project:** Type `/ao_project_team` and describe your goal
- **Customize guardrails:** Edit `.claude/guardrails/rules.yaml` and regenerate hooks
- **Add MCP tools:** Drop Python files into `mcp_tools/` for custom tools
- **Explore workflows:** Read `workflows/project_team/project_team.yaml` to understand phase definitions
