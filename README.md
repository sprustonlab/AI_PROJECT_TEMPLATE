# AI Project Template

**Please only use in private repos for now.**

Scaffold a Claude Code project with environments, guardrails, and multi-agent workflows.

## Quick Start

```bash
# From a clone of this repo:
./install.sh
```

The installer asks for a project name and location, then walks you through configuration options. It installs [pixi](https://pixi.sh) if needed.

Alternatively, if you already have pixi:

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
├── commands/               # CLI scripts (added to PATH by activate)
├── mcp_tools/              # MCP tool plugins (auto-discovered by claudechic)
├── repos/                  # Your codebases (added to PYTHONPATH by activate)
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

Run `/ao_project_team` in claudechic to start the structured workflow. See [`AI_agents/project_team/README.md`](AI_agents/project_team/README.md) for full documentation.

Summary (orchestrated by `AI_agents/project_team/COORDINATOR.md`):

**1. Vision (1 agent)**
You describe what you want. The agent spells out the vision in detail — what success and failure look like — and iterates with you until it's correct. Creates `.ao_project_team/{project_name}/` with `userprompt.md` and `STATUS.md`.

*User checkpoint: approve the vision before work proceeds.*

**2. Specification (4 leadership agents)**
The coordinator spawns leadership agents that draft a specification together:
- **Composability** — dissects the problem into independent axes with defined seams between them. The most important agent.
- **Terminology** — ensures consistent naming across components.
- **UserAlignment** — ensures the spec actually implements what you asked for.
- **Skeptic** — checks for completeness and minimality.

*User checkpoint: approve the specification before implementation begins.*

**Tips:** The coordinator should spawn one Composability agent per identified axis. If it doesn't, say: *"Start a fresh review with new agents, this time make sure to start one composability agent per identified axis."* Repeat until no major issues remain.

**3. Implementation (leadership + implementers)**
Implementer agents write code, guided by leadership. One implementer per file works well. If only one is spawned, say: *"Spawn a sufficient amount of claudechic implementer agents."* If leadership isn't guiding, say: *"Remember to inform the leadership agents that implementation has started and that it is their role to guide the implementers."*

**4. Testing**
Tests are written and run. Leadership does a final review and signs off.

*User checkpoint: optionally request end-to-end tests. By default, agents write "smoke" tests with short runtimes. E2E tests run full real-world use cases but aren't always reliable — sometimes it's faster to run them yourself.*

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
