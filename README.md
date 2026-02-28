# AI Project Team (Template Repository)

**Please only use in private repos for now.**

Tested on mac and linux.

The template has three main components: claudechic, the `/ao_project_team` skill, and reproducible python environment management. 

To use this,
- On GitHub, click **"Use this template"** → **"Create a new repository"** (choose Private). This creates your own copy.
- Clone your new repo and run `source ./activate`. (On first run, this installs the base environment `SLCenv`, a miniforge environment.)
- Run `claudechic`. (On first run, this installs the claudechic environment.)
- In claudechic, run `/ao_project_team` to start the project team workflow.

When you run `source ./activate`, you see the available CLI commands and Claude Code skills.

## The three main components

### claudechic

Claudechic is like claude code, but with great built in multi agent support (via MCP - Model Context Protocol) and with a nice layout. This repo contains my fork of claudechic (upstream: https://github.com/mrocklin/claudechic). You can start claudechic by running `claudechic` (available after `source ./activate`). An introductory video to claudechic by Matthew Rocklin (the developer, also the developer of dask and sympy) can be found here: https://www.youtube.com/watch?v=2HcORToX5sU. A good "hello world" command to see its functionality is "Start two subagents that play chess against each other".

My fork has the following modifications
- add a `/clearui` command, that removes old messages. I like to run it when the session starts to feel sluggish. That command makes it respond fast again, but you cannot scroll up to old messages anymore. 
- All agents and subagents share the same permission mode - when you cycle through default / edit / plan / bypass with Shift+Tab, all agents are set to that mode. Note, bypassPermissions mode is only functional when you launch claudechic `claudechic --yolo`. Doing this means that the agents are enabled to run any command, which is risky.

## The `/ao_project_team` skill

In claudechic, run `/ao_project_team` to start the multi-agent workflow (orchestrated by AI_agents/project_team/COORDINATOR.md). The phases are:

**Understand user vision (1 agent)**: You are asked for what you want to do. The agent tries to spell out the 'User Vision' in more detail, and also say what success and failure would look like. You're asked if what the agent has described is correct, and iterate, until it is correct and complete. You're also asked in which directory the project lives - it can be a new directory, or an existing directory. The agent creates a folder under {working_dir}/.ao_project_team/{project_name} and saves a userpromt.md and STATUS.md. The userprompt.md contains the verbatim prompt that you provided, as well as the approved user vision. STATUS.md tracks where along the workflow we are.

*User checkpoint*: You need to approve the 'vision' before work proceeds.

**Specification phase (4 leadership agents)**: Before, there was one agent, the 'coordinator'. The coordinators prime directive is "Delegate, don't do". The coordinator is now instructed to spawn the 'leadership' agents, which are Composability, TerminologyGuardian, UserAlignment and Skeptic. These agents work together to draft a specification, which is saved under {working_dir}/.ao_project_team/{project_name}/specification.

Composability is the agent that I have spent most time developing, and that (subjectively) is the most important. Composabilities goal is to dissect the problem into independent ('orthogonal') axes. This may be a seperation between memory layout, algorithms, frontend. The goal is to write a specification, in which these components are independent with defined 'seams' between them. 

Terminology is instructed to check that the same thing is called the same across components.

UserAlignment is instructed to make sure the other agents actually do implement what the user requested, and not less than that.

Skeptic is instructed to check for a complete yet minimal implementation.

*User checkpoint*: You need to approve the specification before implementation begins. In the Specification phase, the coordinator is instructed to ask composability for the orthogonal axes they have identified, and spawn one composability agent per axis. This sometimes does not happen. If it didn't it is worth reminding the coordinator agent. Also, you can request a fresh review. I find it helpful to say: "Start a fresh review with new agents, this time make sure to start one composability agent per identified axis". I do this until no major problem is remaining. You can also look at the specs yourself. You need to approve the specification before work can proceed.

**Implementation (4 leadership agents + implementers)**
If the specification is approved, implementation can begin. Implementation agents are supposed to write to {working_dir} directly. If the coordinator spawns only one implementer it helps to say "Spawn a sufficient amount of claudechic implementer agents". I find that it works well to have one implementer per file. The coordinator is supposed to also inform the leadership agents that implementation has started, and ask them to guide the implementation. If that does not happen I find that it helps to say "Remember to inform the leadership agents that implementation has started and that it is their role to guide the implementers".

Afterwards, Tests are implemented. Once they pass, Leadership agents are asked to do a final review and sign off.

*User checkpoint*: You can chose to ask for end-to-end tests ... Generally, the tests that claude implements by default are what is seems to call 'smoke' tests that try to have a short runtime, and never actually runs a full real-world use case. The end-to-end tests are supposed to run a full real-world use case. It doesn't work super reliable yet - so I placed the end-to-end test implementation after the user check point as an optional step. Often it is faster to just run it yourself and see.

### Python environment management 

The python environment management in this repo is adapted from my implementation in [SLC - Spruston Lab Commands](https://github.com/sprustonlab).

Key concept: separate "what you want" (spec) from "what you get" (lockfile, exact versions of everything, platform specific), and collect all installers for all packages in a folder so you get a reproducible offline installer. Specs, lockfile, cache folder, and folder containning the installed environment are all in `envs/`. 

Installed environments can be activated with `conda activate <name>`. A more powerful command (which not only activates, but also auto-installs if needed) is `source require_env <name>`. An example of how require_env can be used is in commands/claudechic.

When you use this template, there will already be two environments available: the base environment (SLCenv) and the claudechic environment. Once they are installed, the envs folder looks like this:

```
envs/
├── SLCenv/                      # Bootstrap environment (auto-created on first activate)
├── SLCenv_offline_install_mac/  # Bootstrap cache (platform-specific)
├── claudechic.yml               # Spec file (user edits this)
├── claudechic.osx-arm64.lock    # lockfile (auto-generated, platform-specific, commit this)
├── claudechic/                  # Installed environment (gitignored)
└── claudechic.osx-arm64.cache/  # Package cache for offline reinstall (gitignored)
```

The .gitignore is configured to track .yml and .lock files in the envs folder, but ignore everything else. (Don't try to commit the environment of cache folders - they are too large for github). 

**Workflows:** 

Situation 1: You have a yml file for the environment that you want to install. Place it in the envs folder, then run `python install_env.py <name>`. If a lockfile is available for your platform, it will use the lockfile (lockfile = all packages are fully specified = no dependency resolution = fast). If no lockfile is available, it will install the environment as you would normally do with `conda env create` from the yml file (yml is minimal = each package might itself specify other required packages = dependency resolution required = slow = how dependencies are resolved one year from now may be different) and then create a lockfile and the offline install folder for your platform.

Situation 2: You have some working environment elsehwere outside of this repo and want to freeze it. To freeze it, first activate that environment, and then run `python lock_env.py <name>`. This will create a lockfile for your environment and save it to envs/<name>.{platform}.lock. Next, activate this repo (`source ./activate') and install that environment from the lockfile by running `python install_env.py <name>`, as above, and check that the environment works. 

*Note: In this situation, you just get a lockfile, not a yml file (that 'minimal' description of dependencies). If you want to get this to run on another platform, more work is needed - ask claude to work with you on creating a yml file, and check out Situation 4*

*Note: I block packages from Anacondas defaults channel, since I've heard that we have a policy that doesn't allow us to use that channel due to licensing issues. So if your environment uses the defaults channel (every normal "anaconda" does), the lockfile will not work, as it can't find the packages. You can ask claude to find equivalent packages from other channels (mainly: conda-forge), and iterate with you until you have an environment that is both equivalent to the one you were using before, and doesn't have licensing issues.*.

Situation 3: You have installed an environment, and added additional packages as you were working with it. Now you want to update the yml and lockfiles to include the new packages. If you have written down which packages you installed, just add them to the .yml file, delete the lock files (or add a .old suffix), and reinstall - you are now in situation 1. But often it isn't clear what packages have been added - then it helps to ask claude "I have installed new packages to the <name> environment and want to update the .yml and lock files in envs/ to reflect these updates. Can you compare the actually installed packages in the environment <name> to the .lock and .yml file in envs/ and suggest which additional packages should be added to the .yml file?". Be critical - if there are packages popping up that you don't recognize, challenge claude on why it is included: "I don't remember installing ..., can you check that these are not a dependency of a more high level package that I have installed, like ...?". Once you have suggestions that you agree with: "Can you create a new <name>_2.yml with all packages I agreed to, and install the environment with install_env.py as described in $REPO_ROOT/README.md. Important: sometimes dependency resolution hangs - make sure to use sensible timeouts. Once an environment has been installed, check that the environment is indeed identical". Once that works: "Now update the yml lockfiles for the environment <name> with the new files, and delete the <name_2> files and environment folders.

Situation 4: You have a fully specified environment that you know does what you want, and you want to make sure no changes can be made to it. Install it with `python install_env.py <name> --read-only`. (Or just remove write permissions to envs/<name>/ with chmod).


## Quick Start

1. Create your project from this template:
   - On GitHub: Click **"Use this template"** → **"Create a new repository"**
   - Or via CLI: `gh repo create my-project --template=sprustonlab/AI_PROJECT_TEMPLATE --private --clone`

2. Clone (if you used the web UI) and activate:
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


## Example

The `.ao_project_team/readme_review/` folder contains an example of the workflow output from reviewing this README. It includes the user prompt, specification documents, and final review by all Leadership agents.

## AI_agents/ Version

Copied from: postdoc_monorepo @ commit 5fa199729c6bd586d2c46697597d0f33b8a7503c
Date: 2026-02-27
