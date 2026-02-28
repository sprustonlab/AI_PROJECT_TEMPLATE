# Terminology Review: README.md

## Executive Summary

The README has significant terminology issues around "SLC" - a core concept that is used but never defined. Additionally, there's inconsistent terminology for environment files and folder structures, and some terms in the README don't match code terminology exactly.

---

## Orphan Definitions (Terms Used, Never Defined)

### Critical: "SLC" - Used 10+ times, defined nowhere

| Location | Usage | Problem |
|----------|-------|---------|
| README line 20 | "Python environment management, copied from what I implemented for SLC" | What IS SLC? |
| README line 70 | "Install SLC (Miniforge) automatically" | Is SLC = Miniforge? Contradicts other uses |
| activate line 8 | "Bootstraps SLC (Miniforge)" | Same confusion |
| install_env.py docstring | "Install SLC environment from lockfile" | SLC is a system? Or an environment? |

**Analysis:**
- SLC appears to be a broader project/system the env management was copied FROM
- But README line 70 and activate line 8 conflate SLC with Miniforge
- The reader cannot tell if "SLC" is: (a) a conda distribution, (b) a project name, (c) an environment management approach, or (d) something else

**Recommendation:** Add definition at first use:
> "Python environment management, copied from what I implemented for SLC (my Stellar/Lightcurve processing project). This approach uses Miniforge as the base conda distribution..."

OR if SLC is irrelevant to users, remove the reference entirely.

### Minor Orphan: "Miniforge"

- Used in activate and install_SLC.py
- Mentioned in README line 70 but not explained
- Newcomers may not know Miniforge is a minimal conda distribution

**Recommendation:** Brief parenthetical: "SLC (Miniforge - a minimal conda distribution)"

---

## Overloaded/Ambiguous Terms

### "environment" - Three distinct meanings

| Context | Meaning | Example |
|---------|---------|---------|
| README line 9 | The shell/project environment | "source ./activate" sets up "the environment" |
| README line 21 | A conda environment | "yml files that specify the environment" |
| README line 76 | A specific project env | "Activate with: conda activate <name>" |

**Current ambiguity (README line 65):**
> "Activate the environment:"
> `source ./activate`

This activates the PROJECT environment (shell setup), NOT a conda environment.

**Recommendation:** Disambiguate:
- "project environment" = what `source ./activate` does (shell setup, paths, base conda)
- "conda environment" = specific envs like `claudechic`, `jupyter`

---

## Synonyms Found (Same Thing, Different Names)

### "yml file" / "spec file" / "environment definition"

| Location | Term Used |
|----------|-----------|
| README line 21 | "yml files" |
| README line 76 | "envs/myenv.yml" |
| install_env.py | "spec file", "spec" |
| lock_env.py | "origin spec", "spec file" |

**Recommendation:** Standardize on "**spec file**" (or "**environment spec**") for `*.yml`, since "yml file" is generic and lock files are also YAML.

### "lock file" vs "lockfile"

| Location | Spelling |
|----------|----------|
| README line 21 | "lock files" (two words) |
| install_env.py | "lockfile" (one word) |
| lock_env.py | "lockfile" (one word) |
| userprompt.md | "Lock files" (two words) |

**Recommendation:** Use "**lockfile**" (one word) consistently - this matches code usage.

---

## Terms in README vs Actual Code

### Folder Structure

| README says | Code actually creates |
|-------------|----------------------|
| "two subfolders will be created in envs" (line 21) | Creates: `envs/{name}/` (env) and `envs/{name}.{platform}.cache/` (cache) |
| "One subfolder contains the environment. The other subfolder contains all packages downloaded" | Accurate, but doesn't mention the `.cache` naming convention |

**Issue:** README doesn't tell user WHAT the folders are named. User prompt explicitly wants to know "what files / folders it will create."

**Recommendation:** Be explicit about naming:
> "When installed, creates:
> - `envs/{name}/` - the conda environment
> - `envs/{name}.{platform}.cache/` - downloaded packages for offline reinstall
> - `envs/{name}.{platform}.lock` - the generated lockfile"

### Scripts Named in README

| README Reference | Actual File | Match? |
|------------------|-------------|--------|
| `install_SLC.py` (line 98) | `install_SLC.py` | ✓ |
| `install_env.py` (line 98) | `install_env.py` | ✓ |
| `lock_env.py` (line 98, 77) | `lock_env.py` | ✓ |
| `python lock_env.py myenv` (line 77) | Correct usage | ✓ |
| `python install_env.py myenv` (line 78) | Correct usage | ✓ |

---

## Claudechic Terminology

### Current usage is clear and consistent:
- "claudechic" - the tool name (lowercase, one word)
- "agents", "subagents" - entities within claudechic
- "MCP" - used but not defined (Model Context Protocol)

### Minor issue: "/ao_project_team" vs "ao_project_team"

| Location | Form |
|----------|------|
| README line 23 | "/ao_project_team command" |
| README line 27 | "/ao_project_team" |
| .claude/commands/ file | `ao_project_team.md` |

**Note:** The "/" prefix is correct for claudechic commands. Consistent.

### MCP - Not defined

Line 11: "Claudechic is like claude, but with multi agent support (via MCP)"

**Recommendation:** Add: "(via MCP - Model Context Protocol)"

---

## Implicit Context / Newcomer Blockers

### "the environment" (line 65)

> "3. Activate the environment:"

Which environment? The base SLC? A project env? This is the first mention of "activate" in Quick Start and doesn't clarify that this is the PROJECT activation (not a conda env).

**Recommendation:**
> "3. Activate the project (sets up SLC, paths, shows available commands):"

### "SLC is active" (activate line 159)

After sourcing activate, user sees:
> "✔ SLC is active"

But user was never told what SLC IS. This message assumes prior knowledge.

---

## Canonical Home Violations

### "SLC" definition

- Currently defined nowhere
- Should have ONE definition location (README, first occurrence)

### Environment management mental model

- Scattered across README lines 20-21 and Quick Start section
- User prompt requests a clear mental model in one place

---

## Summary of Required Fixes

### Critical (Must Fix)
1. **Define "SLC"** at first use - currently a complete orphan definition
2. **Clarify "environment"** disambiguation - project vs conda env

### Important (Should Fix)
3. **Standardize "lockfile"** (one word) throughout
4. **Document folder names** explicitly (what gets created in envs/)
5. **Define "Miniforge"** parenthetically

### Nice-to-Have
6. Define "MCP" parenthetically
7. Consistent "spec file" terminology for yml files

---

## Verification Checklist

After fixes, verify:
- [ ] First occurrence of "SLC" has a definition
- [ ] "lockfile" spelled consistently (one word)
- [ ] README documents exact folder names created
- [ ] "Activate the environment" clarifies which environment
- [ ] A newcomer can understand the env management section without prior context
