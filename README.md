# AI Project Template

Scaffold a Claude Code project with environments, guardrails, and multi-agent workflows.

## Quick Start

👉 **[One-line install](https://sprustonlab.github.io/AI_PROJECT_TEMPLATE/install)** — copy a single command for Linux, macOS, or Windows.

Or, if you already have [pixi](https://pixi.sh):

```bash
pixi exec --spec "copier>=9,<10" --spec git -- copier copy --trust https://github.com/sprustonlab/AI_PROJECT_TEMPLATE my-project
cd my-project && pixi install
```

## What You Get

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
├── CLAUDE.md               # Agent orientation — commands, structure, conventions
└── .copier-answers.yml     # Template answers (for copier update)
```

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

## Usage

```bash
cd my-project
source activate      # Sets up PATH, PYTHONPATH, shows available tools
pixi run claudechic  # Launch the TUI
```

In claudechic, type `/project-team` to start the multi-agent workflow. (This is a claudechic workflow, not a Claude Code slash command.)

## Components

### claudechic

A TUI wrapper around Claude Code with built-in multi-agent support via MCP (Model Context Protocol). Upstream: [mrocklin/claudechic](https://github.com/mrocklin/claudechic). [Video introduction](https://www.youtube.com/watch?v=2HcORToX5sU) by Matthew Rocklin (also the developer of Dask and SymPy).

Start it with `pixi run claudechic` after activating your project. A good "hello world" to see multi-agent functionality: *"Start two subagents that play chess against each other"*.

Our fork adds:
- **`/clearui`** — clears old messages when the session feels sluggish. You lose scroll history but responsiveness returns.
- **Shared permission mode** — when you cycle through default / edit / plan / bypass with `Shift+Tab`, all agents and subagents share the same mode. Note: bypass mode only works when launched with `claudechic --yolo` (agents can run any command — use with caution).

### Guardrails & Rules

Rule-based permission system for Claude Code tool calls, processed at runtime by claudechic. Guardrail rules (always active) block dangerous operations like `rm -rf /` and `git push --force`. Global rules in `global/rules.yaml` and workflow rules in workflow YAML add additional enforcement.

See [docs/getting-started.md](docs/getting-started.md) for full documentation on rule layers, enforcement levels, and adding custom rules.

### Agent Context Files (`.claude/rules/`)

In developer mode (`claudechic_mode=developer`), the generated project includes `.claude/rules/*.md` files. These are **agent context files** -- Claude Code's native rules system that auto-loads guidance when agents touch files matching configured glob patterns. They document claudechic internals (hints, checks, guardrails, workflows, manifest YAML) and are distinct from the guardrails engine and rule systems described above. See [docs/getting-started.md](docs/getting-started.md) for details on each file.

### MCP Tools

Drop Python files into `mcp_tools/` and they're automatically discovered by claudechic. Includes LSF and SLURM cluster backends for HPC job management.

See [`mcp_tools/README.md`](template/mcp_tools/README.md) for full documentation on adding tools, cluster backends, and configuration.

### Multi-Agent Project Team

Type `/project-team` in claudechic to start the structured workflow:

1. **Vision** — describe what you want, agent clarifies and confirms
2. **Specification** — leadership agents (Composability, Terminology, UserAlignment, Skeptic) draft a spec
3. **Implementation** — implementer agents write code, guided by leadership
4. **Testing** — tests are written and run, leadership signs off

Each phase has a user checkpoint. See [`workflows/project_team/README.md`](workflows/project_team/README.md) for detailed documentation and tips.

### Core Systems (via claudechic)

claudechic provides several interlocking systems beyond guardrails:

- **Workflows** -- phase-gated processes that structure multi-agent collaboration
- **Phases** -- named workflow stages with scoped rules, hints, and advance checks
- **Hints** -- contextual toast notifications surfaced to agents during workflows
- **Advance Checks** -- gate conditions that must pass before a phase transition proceeds
- **Chicsessions** -- named multi-agent session snapshots for save/restore

→ See [docs/getting-started.md](docs/getting-started.md) for full documentation.

### Existing Codebase Integration

If you provide a path to an existing codebase during setup, it's linked (Linux/macOS) or copied (Windows) into `repos/`. The `activate` script adds `repos/*/` to PYTHONPATH so your packages are importable.

## Development

This repo uses a `develop` branch for ongoing work. The `main` branch contains release-ready code.

> **Note:** `CLAUDE.md` at the project root provides agent-facing orientation
> (commands, layout, pitfalls, extension recipes). `.project_team/` contains
> development history and must not be committed to `main` -- a pre-commit hook
> enforces this.

```bash
git checkout develop
pixi install              # Install dev dependencies
pixi run pytest           # Run fast tests
pixi run pytest -m ""     # Run all tests (including slow E2E)
```

### Template Development

The copier template lives in `template/`. Files ending in `.jinja` are processed by Jinja2; all other files are copied as-is. Test your changes:

```bash
pixi run pytest tests/test_copier_generation.py -v  # Fast copier tests
```

### Setting Up a Local Dev Environment

To clone and set up this repo for development:

```bash
# 1. Clone the repo and switch to the develop branch
git clone https://github.com/sprustonlab/AI_PROJECT_TEMPLATE
cd AI_PROJECT_TEMPLATE
git checkout develop

# 2. Initialize the claudechic submodule
git submodule update --init --recursive

# 3. Install pixi environments (installs claudechic as an editable package)
pixi install

# 4. Activate the project — claudechic will be on your PATH
source activate
```

After step 4, `claudechic` is available directly in your shell for the session.
