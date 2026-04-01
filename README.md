# AI Project Template

Scaffold a Claude Code project with environments, guardrails, and multi-agent workflows.

## Quick Start

👉 **[One-line install](https://sprustonlab.github.io/AI_PROJECT_TEMPLATE/)** — copy a single command for Linux, macOS, or Windows.

Or, if you already have [pixi](https://pixi.sh):

```bash
pixi exec --spec "copier>=9,<10" --spec git -- copier copy --trust https://github.com/sprustonlab/AI_PROJECT_TEMPLATE my-project
cd my-project && pixi install
```

## What You Get

```
my-project/
├── .claude/
│   ├── commands/           # Claude Code skills (/ao_project_team, /init_project)
│   └── guardrails/         # Permission system (rules.yaml → generated hooks)
├── AI_agents/
│   └── project_team/       # Multi-agent roles (Coordinator, Implementer, Skeptic, etc.)
├── commands/
│   └── claudechic          # CLI wrapper (added to PATH by activate)
├── mcp_tools/              # MCP tool plugins (auto-discovered by claudechic)
├── repos/                  # Your codebases (symlinked/copied, added to PYTHONPATH)
│   └── my_existing_repo/   # ← from existing_codebase option
├── submodules/             # (developer mode only)
│   └── claudechic/         # Local editable clone of claudechic
├── activate                # Source this to set up your environment
├── pixi.toml               # Package manager config
└── copier.yml              # Template answers (for copier update)
```

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

## Usage

```bash
cd my-project
source activate      # Sets up PATH, PYTHONPATH, shows available tools
pixi run claudechic  # Launch the TUI
```

In claudechic, run `/ao_project_team` to start the multi-agent workflow.

## Components

### claudechic

A TUI wrapper around Claude Code with built-in multi-agent support via MCP (Model Context Protocol). Upstream: [mrocklin/claudechic](https://github.com/mrocklin/claudechic). [Video introduction](https://www.youtube.com/watch?v=2HcORToX5sU) by Matthew Rocklin (also the developer of Dask and SymPy).

Start it with `pixi run claudechic` after activating your project. A good "hello world" to see multi-agent functionality: *"Start two subagents that play chess against each other"*.

Our fork adds:
- **`/clearui`** — clears old messages when the session feels sluggish. You lose scroll history but responsiveness returns.
- **Shared permission mode** — when you cycle through default / edit / plan / bypass with `Shift+Tab`, all agents and subagents share the same mode. Note: bypass mode only works when launched with `claudechic --yolo` (agents can run any command — use with caution).

### Guardrails

Rule-based permission system for Claude Code tool calls. Rules are defined in `.claude/guardrails/rules.yaml` and compiled into hook scripts. The default rule (R01) blocks dangerous operations like `rm -rf /` and `git push --force`.

See [`.claude/guardrails/README.md`](.claude/guardrails/README.md) for full documentation on adding rules, roles, enforcement levels, and the ack flow.

### MCP Tools

Drop Python files into `mcp_tools/` and they're automatically discovered by claudechic. Includes LSF and SLURM cluster backends for HPC job management.

See [`mcp_tools/README.md`](template/mcp_tools/README.md) for full documentation on adding tools, cluster backends, and configuration.

### Multi-Agent Project Team

Run `/ao_project_team` in claudechic to start the structured workflow:

1. **Vision** — describe what you want, agent clarifies and confirms
2. **Specification** — leadership agents (Composability, Terminology, UserAlignment, Skeptic) draft a spec
3. **Implementation** — implementer agents write code, guided by leadership
4. **Testing** — tests are written and run, leadership signs off

Each phase has a user checkpoint. See [`AI_agents/project_team/README.md`](AI_agents/project_team/README.md) for detailed documentation and tips.

### Existing Codebase Integration

If you provide a path to an existing codebase during setup, it's linked (Linux/macOS) or copied (Windows) into `repos/`. The `activate` script adds `repos/*/` to PYTHONPATH so your packages are importable.

## Development

This repo uses a `develop` branch for ongoing work. The `main` branch contains release-ready code.

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
