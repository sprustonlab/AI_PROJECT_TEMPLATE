# AI Project Team (Template Repository)

A reusable template for bootstrapping new research projects with integrated environment management, Claude Code project team workflow, and consistent project structure.

Tested on mac and linux.

The template has three main components: claudechic, reproducible python environment management, and - most importantly - the ao_project_team command. To use this, the first step is to clone this repo and run `source ./activate`. On first run, this will install the base environment. Afterwards you can run `claudechic`. On first run, this will install the claudechic environment. 

## The three main components

(1) My fork of claudechic (upstream: https://github.com/mrocklin/claudechic). Claudechic is like claude code, but with great built in multi agent support (via MCP - Model Context Protocol) and with a nice layout. You can start claudechic by running `claudechic` (available after `source ./activate`). An introductory video to claudechic by Matthew Rocklin (the developer, also the developer of dask and sympy) can be found here: https://www.youtube.com/watch?v=2HcORToX5sU. A good "hello world" command to run in claudechic is "Start two subagents that play chess against each other".

My fork has the following modifications
- add a /clearui command, that removes old messages. I like to run it when the session starts to feel sluggish. You lose the ability to look at old messages, but it responds fast again.
- Make it such that all agents and subagents share the same permission mode
- Make it such that the bypassPermissions mode is available. You can cycle through modes with Shift+Tab. Note: This won't do anything, unless you start claudechic with `claudechic --yolo`. Doing this means that the agents are enabled to run any command, which is risky.

(2) **Python environment management** (adapted from [SLC - Spruston Lab Commands](https://github.com/sprustonlab))

The `envs/` folder holds everything. Key concept: separate "what you want" (spec) from "what you get" (lockfile).

```
envs/
├── SLCenv/                      # Bootstrap environment (auto-created on first activate)
├── SLCenv_offline_install_mac/  # Bootstrap cache (platform-specific)
├── claudechic.yml               # Spec file (user edits this)
├── claudechic.osx-arm64.lock    # lockfile (auto-generated, platform-specific, commit this)
├── claudechic/                  # Installed environment (gitignored)
└── claudechic.osx-arm64.cache/  # Package cache for offline reinstall (gitignored)
```

**Workflow:** Edit `*.yml` → `python install_env.py <name>` → `conda activate <name>`

First `source ./activate` bootstraps Miniforge into `envs/SLCenv/` automatically.

(3) The /ao_project_team command that you can run in claudechic. This starts a multi agent coding workflow. It is orchestrated in the AI_agents/project_team/COORDINATOR.md file.

## The three main phases of the ao_project_team workflow

You run /ao_project_team in claudechic. This launches the workflow.

**Understand user vision**: You are asked for what you want to do. The agent tries to spell out the 'User Vision' in more detail, and also say what success and failure would look like. You're asked if what the agent has described is correct, and iterate, until it is correct and complete. You're also asked in which directory the project lives - it can be a new directory, or an existing directory. The agent creates a folder under {working_dir}/.ao_project_team/{project_name} and saves a userpromt.md and STATUS.md. The userprompt.md contains the verbatim prompt that you provided, as well as the approved user vision.

*User checkpoint*: You need to approve the 'vision' before work proceeds.

**Specification phase**: Before, there was one agent, let's now call it the 'coordinator'. The coordinator is now instructed to spawn the 'leadership' agents, which are Composability, Terminology, UserAlignment and Skeptic. These agents work together to draft a specification, which is saved under {working_dir}/.ao_project_team/{project_name}/specification.

Composability is the agent that I have spent most time developing, and that (subjectively) is the most important. Composabilities goal is to dissect the problem into independent ('orthogonal') axes that are independent. This may be a seperation between memory layout, algorithms, frontend. The goal is to write a specification, in which these components are independent with defined 'seams' between them. A leaky seam exists for example if the algorithm needs to know what memory layout is used.

Terminology is instructed to check that the same thing is called the same across components.

UserAlignment is instructed to make sure the other agents actually do implement what the user requested, and not less than that.

Skeptic is instructed to check for a complete yet minimal implementation.

*User checkpoint*: You need to approve the specification before implementation begins. In the Specification phase, the coordinator is instructed to ask composability for the orthogonal axes they have identified, and spawn one composability agent per axis. This sometimes does not happen. If it didn't it is worth reminding the coordinator agent. You can request a fresh review. In that case, the Leadership agents are closed and restarted with fresh context, and work through the specification once more (if only one composability agent was started, I find it helpful to say: "Fresh review with new agents, this time make sure to start one composability agent per identified axis").

**Implementation**
If the specification is approved, implementation can begin. Implementation agents are supposed to write to {working_dir} directly. If the coordinator spawns only one implementer it helps to say "Spawn a sufficient amount of claudechic implementer agents". I find that it works well to have one implementer per file. The coordinator is supposed to also inform the leadership agents that implementation has started, and ask them to guide the implementation. If that does not happen I find that it helps to say "Remember to inform the leadership agents that implementation has started and that it is their role to guide the implementers".

Afterwards, Tests are implemented. Once they pass, Leadership agents are asked to do a final review and sign off.

*User checkpoint*: You can chose to ask for end to end tests ... I found that often the tests did not capture all issues. The end to end tests are supposed to run whatever has been implemented on actual data, as if it was used in the real world. This doesn't work super reliable yet - so I have them after the user check point as an optional step.

## Quick Start

1. Clone this repository:
   ```bash
   git clone <url> <project-name>
   cd <project-name>
   ```

2. Initialize submodules (for claudechic MCP server):
   ```bash
   git submodule update --init --recursive
   ```

3. Activate the project:
   ```bash
   source ./activate
   ```
   On first run, this will:
   - Install Miniforge into `envs/SLCenv/` automatically
   - Set up paths and environment variables
   - Display available commands and skills

4. (Optional) Create a project-specific environment:
   ```bash
   # Edit envs/myenv.yml with your dependencies
   python lock_env.py myenv
   python install_env.py myenv
   conda activate myenv
   ```

## Customization

### Customize the activate script:
- **Line ~21**: Change `PROJECT_NAME="my-project"` to your project name
- **Section 2**: Add project-specific modules to PYTHONPATH
- **Section 3**: Add checks for additional submodules

### What to modify:
- This README
- `envs/*.yml` - your environment spec files
- `commands/*` - your CLI scripts
- `modules/`, `repos/` - your code
- `.claude/commands` - other claudechic commands that you want to have available.

### What to keep as-is:
- `activate` script (except CUSTOMIZE sections)
- `install_SLC.py`, `install_env.py`, `lock_env.py`
- `.gitignore` patterns
- `AI_agents/` directory
- `.claude/commands/` structure

## Available Commands

Run `source ./activate` to see available CLI commands and Claude Code skills.

## AI_agents/ Version

Copied from: postdoc_monorepo @ commit 5fa199729c6bd586d2c46697597d0f33b8a7503c
Date: 2026-02-27
