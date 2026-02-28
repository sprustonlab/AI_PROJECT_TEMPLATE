# AI Project Team (Template Repository)

Tested on mac and linux.

The template has three main components: claudechic, reproducible python environment management, and - most importantly - the ao_project_team command. 

To use this, 
- fork the template (so you have your own version of it for your project that you can change any way you want).
- clone your forked repo and run `source ./activate`. (If you activate this for the first time, this will install the base environment `SLCenv`, which is a miniforge environment.). 
- Afterwards you can run `claudechic`. (If you run this for the first time, this will install the claudechic environment)
- In claudechic, you can run /ao_project_team, to start the project team workflow. 

## The three main components

### claudechic

Claudechic is like claude code, but with great built in multi agent support (via MCP - Model Context Protocol) and with a nice layout. This repo contains my fork of claudechic (My fork of claudechic (upstream: https://github.com/mrocklin/claudechic). You can start claudechic by running `claudechic` (available after `source ./activate`). An introductory video to claudechic by Matthew Rocklin (the developer, also the developer of dask and sympy) can be found here: https://www.youtube.com/watch?v=2HcORToX5sU. A good "hello world" command to run in claudechic is "Start two subagents that play chess against each other".

My fork has the following modifications
- add a /clearui command, that removes old messages. I like to run it when the session starts to feel sluggish. You lose the ability to look at old messages, but it responds fast again.
- Make it such that all agents and subagents share the same permission mode
- Make it such that the bypassPermissions mode is available. You can cycle through modes with Shift+Tab. Note: This won't do anything, unless you start claudechic with `claudechic --yolo`. Doing this means that the agents are enabled to run any command, which is risky.

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

*User checkpoint*: You can chose to ask for end-to-end tests ... I found that often claude is creating 'smoke' tests that try to have a short runtime, and never actually runs everything for a full real-world use case. The end to end tests are supposed to do that, but it doesn't work super reliable yet - so I have them after the user check point as an optional step.

### Python environment management 

The python environment management in this repo is adapted from my implementation in [SLC - Spruston Lab Commands](https://github.com/sprustonlab).

Key concept: separate "what you want" (spec) from "what you get" (lockfile, exact versions of everything, platform specific), and collect all installers for all packages in a folder so you get a reproducible offline installer. Specs, lockfile, cache folder, and folder containning the installed environment are all in `envs/`. 

Installed environments can be activated with `conda activate <name>`. Environments can be activated (and auto-installed if needed) with `source require_env <name>`

By default (i.e., when you fork / clone this template repo) there are already two environments available: the base environment (SLCenv) and the claudechic environment. Once they are installed, the envs folder looks like this:

```
envs/
├── SLCenv/                      # Bootstrap environment (auto-created on first activate)
├── SLCenv_offline_install_mac/  # Bootstrap cache (platform-specific)
├── claudechic.yml               # Spec file (user edits this)
├── claudechic.osx-arm64.lock    # lockfile (auto-generated, platform-specific, commit this)
├── claudechic/                  # Installed environment (gitignored)
└── claudechic.osx-arm64.cache/  # Package cache for offline reinstall (gitignored)
```

**Workflows:** 

Situation 1: You have a yml file for the environment that you want to install. Place it in the envs folder, then run `python install_env.py <name>`. If a lockfile is available for your platform, it will use the lockfile (lockfile means all packages are fully specified = no dependency resolution = fast). If no lockfile is available, it will install the environment as you would normally do with `conda env create` from the yml file (yml is minimal = each package might itself specify other required packages = dependency resolution required = slow) and then create a lockfile and the offline install folder for your platform.

Situation 2: You have some working environment elsehwere outside of this repo and want to freeze it. To freeze it, first activate that environment, and then run python lock_env.py <name>. This will create a lockfile for your environment and save it to envs/<name>.{platform}.lock. Next, activate this repo (`source ./activate') and install that environment from the lockfile by running `python install_env.py <name>, as above, and check that the environment works. 

*Note: In this situation, you just get a lockfile, not a yml file (that 'minimal' description of dependencies). If you want to get this to run on another platform more work is needed - ask claude to work with you on creating a yml file, and check out Situation 4*

*Note: I block packages from Anacondas defaults channel, since I've heard that we have a policy that doesn't allow us to use that channel due to licensing issues. So if your environment uses the defaults channel (every normal "anaconda" does), the lockfile will not work, as it can't find the packages. You can ask claude to find equivalent packages from other channels (mainly: conda-forge), and iterate with it until you have an environment that is both equivalent to the one you were using before, and doesn't have licensing issues.*.

Situation 3: You have installed an environment, and added additional packages as you were working with it. Now you want to update the yml and lockfiles to include the new packages. If you have written them down, just add them to the .yml file, delete the lock files (or add a .old suffix), and reinstall - you are now in situation 1. But often it isn't clear what packages have been added - then it helps to ask claude "I have installed new packages to the <name> environment and want to update the .yml and lock files in envs/ to reflect these updates. Can you compare the actually installed packages in the environment <name> to the .lock and .yml file in envs/ and suggest which additional packages should be added to the .yml file?". Be critical - if there are packages popping up that you don't recognize, challenge claude on why it is included: "I don't remember installing ..., can you check that these are not a dependency of a more high level package that I have installed, like ...?". Once you have suggestions that you agree with: "Can you create a new <name>_2.yml with all packages I agreed to, and install the environment with install_env.py as described in $REPO_ROOT/README.md. Important: sometimes dependency resolution hangs - make sure to use sensible timeouts. Once an environment has been installed, check that the environment is indeed identical". Once that works: "Now update the yml lockfiles for the environment <name> with the new files, and delete the <name_2> files and environment folders.

Situation 4: You have a fully specified environment that you know does what you want, and you want to make sure no changes can be made to it. Install it with `python install_env.py <name> --read-only. (Or just remove write permissions to envs/<name>/ with chmod).

(3) The ao_project_team multi agent workflow

In claudechic, run /ao_project_team. This starts a multi agent coding workflow. It is orchestrated in the AI_agents/project_team/COORDINATOR.md file.



## Quick Start

1. Clone this repository:
   ```bash
   git clone <url> <project-name>
   cd <project-name>
   ```

2. Activate the project:
   ```bash
   source ./activate
   ```
   On first run, this will initialize git submodules, install Miniforge into `envs/SLCenv/`, and set up paths.

   Note: Submodules are auto-initialized on first run if needed.

3. (Optional) Create a project-specific environment:
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

## Example

The `.ao_project_team/readme_review/` folder contains an example of the workflow output from reviewing this README. It includes the user prompt, specification documents, and final review by all Leadership agents.

## AI_agents/ Version

Copied from: postdoc_monorepo @ commit 5fa199729c6bd586d2c46697597d0f33b8a7503c
Date: 2026-02-27
