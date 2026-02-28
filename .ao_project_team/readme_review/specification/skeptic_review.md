# Skeptic Review: README.md Accuracy Verification

## Summary

The README is **mostly accurate** but has several technical errors and missing information that would confuse new users.

---

## Critical Issues

### 1. Wrong Keybinding for Permission Mode Cycling
**README claims (line ~17):** "You can cycle through modes with Alt+Tab"
**Actual implementation:** The keybinding is **Shift+Tab**, not Alt+Tab.

Evidence from `claudechic/screens/chat.py`:
```python
Binding("shift+tab", "cycle_permission_mode", "Auto-edit", priority=True, show=False)
```

This is a direct error that will confuse users.

### 2. Incorrect Line Reference for PROJECT_NAME
**README claims (line 85):** "Line ~165: Change `PROJECT_NAME=\"my-project\"`"
**Actual location:** Line **21** of the activate script.

The activate script is only 241 lines total. Line 165 is in the middle of environment listing logic, nowhere near the PROJECT_NAME definition.

---

## Inaccuracies in Environment Management Section

### 3. Vague Description of What Gets Created
**README claims:** "two subfolders will be created in envs. One subfolder contains the environment. The other subfolder contains all packages downloaded from pip and conda."

**What actually happens:** Looking at the activate script:
- `envs/SLCenv/` - the base Miniforge installation (created by install_SLC.py on first run)
- `envs/{envname}/` - additional environments when you run install_env.py

The README doesn't mention:
- `SLCenv` is the base installation that happens automatically
- Lock files are platform-specific (this is mentioned but location isn't clear)
- The package cache location (what is the "other subfolder"?)

### 4. Missing Details on Lock/Install Workflow
The Quick Start says:
```bash
python lock_env.py myenv
python install_env.py myenv
```

Missing information:
- What does `lock_env.py` actually do? Create lock files for reproducibility?
- What platforms are lock files generated for?
- Can you install without locking first?
- What if lock files already exist?

---

## Verified as Working

### Commands and File Paths
| Claim | Status |
|-------|--------|
| `source ./activate` exists and is executable | ✅ |
| `install_SLC.py`, `install_env.py`, `lock_env.py` exist | ✅ |
| `envs/` folder exists with .yml files | ✅ (claudechic.yml, jupyter.yml) |
| `submodules/claudechic` exists | ✅ |
| `AI_agents/project_team/` exists | ✅ |
| `.claude/commands/ao_project_team.md` exists | ✅ |
| `commands/claudechic` exists | ✅ |

### Claudechic Fork Modifications
| Claim | Status |
|-------|--------|
| `/clearui` command | ✅ Verified in commands.py |
| Shared permission mode for agents | ✅ Verified in agent_manager.py, agent.py |
| `bypassPermissions` mode exists | ✅ Verified in config.py, tests |
| `claudechic --yolo` flag | ✅ Verified in __main__.py, app.py |

### Git Submodule Claim
**README says:** "Claudechic is added as submodule, so after cloning this repo, you need to run `git submodule update --init --recursive`"
**Status:** ✅ Correct - .gitmodules exists and references claudechic.

---

## Missing Information for New Users

### 1. What is "SLC"?
The README uses "SLC" repeatedly but never defines it. New users will have no idea what this acronym means. The activate script shows `SLC_VERSION="0.0.1"` but that doesn't help explain what it is.

### 2. Prerequisites
The README doesn't list:
- Python 3 is required (checked by activate script)
- Git is required (for submodules)
- No mention of whether this works on Windows

### 3. Environment Management Workflow Clarity
A new user would benefit from:
- What files to create/edit when starting a new project
- What the lock file format looks like
- Whether to commit lock files to git
- How to update dependencies after initial setup

### 4. Where is the package cache?
The README says "The other subfolder contains all packages downloaded from pip and conda" but doesn't specify where this is. This matters for disk space management.

---

## Recommendations

1. **Fix keybinding:** Change "Alt+Tab" to "Shift+Tab"
2. **Fix line reference:** Change "Line ~165" to "Line ~21"
3. **Expand SLC acronym:** At least once, define what SLC stands for
4. **Clarify env structure:** Be explicit about what folders get created:
   - `envs/SLCenv/` - base conda (auto-created on first activate)
   - `envs/{name}/` - your project environments
   - Where package cache lives
5. **Add prerequisites:** Python 3, Git, Mac/Linux only

---

## Sign-Off Recommendation

**Cannot approve README as-is.** The Alt+Tab vs Shift+Tab error and line ~165 error are factual mistakes that will directly mislead users trying to follow the instructions.
