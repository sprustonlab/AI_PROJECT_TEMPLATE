# Seam Analysis: Environment Management

> The env management system has a universal four-verb pattern that exists in every language ecosystem. This document analyzes what's generic vs conda-specific in the current implementation, defines the abstract interface a backend must implement, and walks through a concrete multi-backend scenario.

---

## 1. The Four Verbs (Abstract)

Every environment management system, regardless of language or package manager, performs four operations:

### Spec — Declare Dependencies

**What it does:** Declares what the environment needs — packages, versions, channels/registries, and optionally editable/local installs.

**Concrete examples across ecosystems:**

| Ecosystem | Spec File | Format |
|-----------|-----------|--------|
| conda | `envs/<name>.yml` | YAML: name, channels, dependencies (conda + pip) |
| pip | `requirements.txt` or `pyproject.toml` | Text: one package per line, or TOML `[project.dependencies]` |
| R/renv | `renv.lock` (acts as both spec and lock) | JSON: packages, versions, repos |
| Rust/cargo | `Cargo.toml` | TOML: `[dependencies]` section |
| C++/conan | `conanfile.txt` or `conanfile.py` | INI or Python: requires list |
| Node/npm | `package.json` | JSON: dependencies, devDependencies |

**What the rest of the template needs:** A file at a discoverable, conventional path that names the environment and lists what it needs. The template never reads spec contents — it just needs to know the file exists.

### Install — Get the Environment

**What it does:** Reads the spec (or preferably the lockfile) and creates a usable, isolated environment with all dependencies available.

**Universal substructure:**
1. Find best source: lockfile (exact, fast) > spec (solved, slow, needs network)
2. Create isolated environment directory
3. Download/install packages
4. Handle editable/local packages specially

**What the rest of the template needs:** After install, a directory exists at `envs/<name>/` that contains the environment. The template checks `[[ -d envs/<name> ]]` — that's it.

### Lock — Freeze Exact Versions

**What it does:** Reads the currently installed (solved) environment and writes a platform-specific lockfile with exact versions, hashes, and provenance metadata.

**Universal properties:**
- Input: an installed environment + the original spec
- Output: a file that enables byte-identical recreation on the same platform
- Metadata: origin hash (link to spec), platform, timestamp

**What the rest of the template needs:** A lockfile appears at a conventional path. The template never reads lockfile contents.

### Activate/Check — Make Available / Verify

**What it does:** Makes the environment's binaries and libraries available in the current shell (PATH, library paths, env vars). Check verifies the environment is installed without activating.

**What the rest of the template needs:** A command that, when sourced, puts the environment's tools on PATH. The template needs to be able to source/call this from command wrappers.

---

## 2. What the Template Actually Assumes (Current Contracts)

I mapped every assumption the four touchpoints (`activate`, `require_env`, `install_env.py`, `commands/*`) make about the env backend:

### `activate` script — Assumptions

| Line(s) | Assumption | Generic or Conda-specific? |
|---------|------------|---------------------------|
| 40-41 | `SLCENV_DIR="$BASEDIR/envs/SLCenv"` — base env at fixed path | **Conda-specific.** The "base env" concept (a bootstrap environment that installs other envs) is conda's model. pip/renv/cargo don't need a base env. |
| 45-77 | SLC bootstrap (install Miniforge if missing) | **Conda-specific.** The entire bootstrap flow assumes conda. Other backends bootstrap differently (pip is usually already present, renv auto-bootstraps). |
| 80-84 | `source conda.sh`, `source mamba.sh`, `conda activate` | **Conda-specific.** Activation mechanism. |
| 186-193 | `envs/*.yml` glob to discover environments | **Nearly generic.** The discovery pattern (scan `envs/` for spec files) is good. The `.yml` extension is conda-specific. |
| 189 | `[[ -d "$BASEDIR/envs/$envname" ]]` to check installed | **Generic.** Directory existence check works for any backend that installs to `envs/<name>/`. |
| 202 | `conda activate <name>` in status display | **Conda-specific.** Activation command. |

### `commands/require_env` — Assumptions

| Line(s) | Assumption | Generic or Conda-specific? |
|---------|------------|---------------------------|
| 36-39 | Checks `PROJECT_ROOT` is set | **Generic.** |
| 50-56 | Checks `SLC_BASE` is set | **Conda-specific.** Assumes SLC is the backend. |
| 68-69 | Sources `conda.sh`, `mamba.sh` | **Conda-specific.** |
| 98-100 | `check_slc_installed()` checks for `SLCenv/bin/conda` | **Conda-specific.** |
| 136-138 | `check_env_installed()` checks `[[ -d envs/$name ]]` | **Generic.** Directory existence works for any backend. |
| 168-169 | Checks `envs/${name}.yml` exists | **Conda-specific extension.** Pattern is generic, extension is not. |
| 277-281 | `conda activate "$SLC_DIR/envs/$ENV_NAME"` | **Conda-specific.** |

### `install_env.py` — Assumptions

| Line(s) | Assumption | Generic or Conda-specific? |
|---------|------------|---------------------------|
| 100-103 | Requires `SLC_BASE` env var | **Conda-specific.** |
| 109-114 | Requires `SLC_PYTHON == sys.executable` | **Conda-specific.** Ensures running in base conda env. |
| 53-71 | `find_env_source()`: looks for `<name>.<platform>.lock` then `<name>.yml` | **Mostly generic pattern.** Lockfile-first, spec-fallback is universal. Platform-specific lockfile naming is conda-specific but a good generic pattern. |
| 167-171 | `conda env create -f <spec> -p <path>` | **Conda-specific.** Install command. |
| 267-277 | `conda create --prefix <path> --offline` | **Conda-specific.** Install from lockfile. |
| 281-332 | pip install within conda env | **Conda-specific hybrid.** Pip-inside-conda is a conda pattern. |

### `commands/claudechic` and `commands/jupyter` — Assumptions

| Line(s) | Assumption | Generic or Conda-specific? |
|---------|------------|---------------------------|
| claudechic:24 | `source require_env claudechic` | **Generic pattern.** The wrapper pattern (source require_env + run tool) is backend-agnostic. |
| claudechic:27-29 | `python -c "import claudechic"`, `pip install -e` | **Python-specific** (not conda-specific). Would work with any Python env backend. |
| jupyter:8 | `source require_env jupyter` | **Generic pattern.** |

### Summary: What's Already Generic

The **directory conventions** are largely backend-agnostic:

- `envs/<name>.{ext}` — spec file (extension varies by backend)
- `envs/<name>.<platform>.lock` — lockfile (could work for any backend)
- `envs/<name>/` — installed environment directory
- `commands/<name>` — wrapper that sources `require_env <name>`
- `[[ -d envs/<name> ]]` — installed check

The **operations** are conda-specific:
- Bootstrap (SLC/Miniforge install)
- Install (`conda create`/`conda env create`)
- Lock (`conda env export` + postprocessing)
- Activate (`conda activate`)

---

## 3. Concrete Test Case: R User with Claudechic

### Scenario

A neuroscience postdoc has:
- An R project doing statistical analysis (uses tidyverse, lme4, brms)
- Wants claudechic for AI-assisted coding
- Their R packages are managed with `renv`

### What They Create

```
my-neuro-project/
├── activate
├── install_env.py
├── lock_env.py
├── install_SLC.py
├── envs/
│   ├── claudechic.yml                    # Conda spec (Python + claudechic deps)
│   ├── claudechic.linux-64.lock          # Conda lockfile
│   ├── claudechic/                       # Installed conda env
│   ├── r-analysis.renv                   # R spec (renv format)  ← NEW
│   ├── r-analysis.linux-64.lock          # renv lockfile (or renv.lock copy)  ← NEW
│   └── r-analysis/                       # Installed R env (renv library)  ← NEW
├── commands/
│   ├── claudechic                        # sources require_env claudechic → conda
│   ├── require_env                       # the dispatch helper
│   └── r-analysis                        # sources require_env r-analysis → renv  ← NEW
├── repos/
│   └── neuro-stats/                      # Their R project code
├── .claude/
│   ├── commands/
│   │   └── ao_project_team.md
│   └── guardrails/
│       └── ...
└── AI_agents/
    └── project_team/
```

### What `activate` Shows

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  my-neuro-project environment activated
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✔ SLC is active

📦 Installed environments:
    ✔ claudechic
📋 Available to install:
    ○ r-analysis

🛠  CLI commands:
    claudechic
    r-analysis
```

### What `require_env r-analysis` Does

This is where the seam matters. Currently `require_env` hard-calls `conda activate`. For the R env, it needs to:

1. Check if `envs/r-analysis/` exists → if not, install
2. Install: detect backend from spec file extension (`.renv` → renv backend), call the renv install procedure
3. Activate: set `R_LIBS_USER=envs/r-analysis/library`, add R to PATH

### How `install_env.py` Knows to Use renv

**Option A: Spec file extension dispatch.** The spec file extension tells you the backend:

| Extension | Backend | Install command |
|-----------|---------|----------------|
| `.yml` | conda | `conda env create -f <spec> -p envs/<name>` |
| `.renv` | renv | `Rscript -e "renv::restore(lockfile='<spec>', library='envs/<name>/library')"` |
| `.toml` | pip/uv (pyproject.toml) | `uv venv envs/<name> && uv pip install -r <spec>` |
| `.cargo.toml` | cargo | `cargo install --root envs/<name>` |

**Option B: Explicit backend field in a thin wrapper file.** Each environment has a `envs/<name>.env` metafile:

```yaml
# envs/r-analysis.env
backend: renv
spec: r-analysis.renv
```

Option A is simpler and sufficient — the extension IS the backend declaration. No extra files needed.

### Key Insight from This Walkthrough

The `require_env` activation step is the hardest part. Conda has `conda activate` which modifies shell state. R's renv modifies `R_LIBS_USER`. Rust's cargo puts binaries in `envs/<name>/bin/`. Each backend activates differently, but they all need to end up with the right things on PATH or in the right env vars.

**The contract:** after activation, running `<tool>` (e.g., `R`, `python`, `cargo`) finds the environment's version, not the system version. How that happens is the backend's problem.

---

## 4. Backend Interface (The Seam Contract)

A backend must provide **scripts** at conventional paths. Not a Python class hierarchy — shell scripts that the template's infrastructure (`require_env`, `install_env.py`, `activate`) can call.

### 4.1 Required Backend Scripts

Each backend is a directory under `envs/backends/<backend-name>/` containing:

```
envs/backends/conda/
├── detect.sh        # Does this spec file belong to me?
├── install.sh       # Install env from spec or lockfile
├── lock.sh          # Generate lockfile from installed env
├── activate.sh      # Source this to activate the env
├── check.sh         # Is the env installed and valid?
└── info.sh          # Print backend-specific status info
```

### 4.2 Script Contracts

Each script receives standard arguments and env vars. All scripts must be POSIX-compatible and sourceable (for `activate.sh`) or executable (for the rest).

**Standard env vars (set by caller):**

```bash
ENV_NAME="claudechic"                    # Environment name
ENV_SPEC="/path/to/envs/claudechic.yml"  # Path to spec file
ENV_DIR="/path/to/envs/claudechic"       # Install target directory
ENVS_DIR="/path/to/envs"                 # Parent envs/ directory
PROJECT_ROOT="/path/to/project"          # Project root
```

#### `detect.sh <spec-file>`
**Purpose:** Given a spec file path, exit 0 if this backend handles it, exit 1 otherwise.
**Contract:** Pure detection — no side effects. Used by `install_env.py` to find the right backend.

```bash
# Example: envs/backends/conda/detect.sh
#!/bin/bash
# Conda backend handles .yml files with conda-style content
[[ "$1" == *.yml ]] && grep -q "channels:" "$1" 2>/dev/null
```

```bash
# Example: envs/backends/renv/detect.sh
#!/bin/bash
[[ "$1" == *.renv ]] || [[ "$1" == */renv.lock ]]
```

#### `check.sh`
**Purpose:** Exit 0 if env is installed and valid, exit 1 otherwise.
**Contract:** No output on success. Error message on failure.

```bash
# Example: envs/backends/conda/check.sh
#!/bin/bash
[[ -d "$ENV_DIR" ]] && [[ -x "$ENV_DIR/bin/python" ]]
```

```bash
# Example: envs/backends/renv/check.sh
#!/bin/bash
[[ -d "$ENV_DIR/library" ]] && [[ -f "$ENV_DIR/.renv_initialized" ]]
```

#### `install.sh [--from-lock <lockfile>]`
**Purpose:** Install the environment. Prefers lockfile if provided, falls back to spec.
**Contract:** Creates `$ENV_DIR/`. Exits 0 on success, non-zero on failure. Handles its own download/caching.

#### `lock.sh`
**Purpose:** Generate a lockfile from the installed environment.
**Contract:** Writes lockfile to `$ENVS_DIR/<name>.<platform>.lock`. Includes `_meta:origin_hash` header for staleness detection.

#### `activate.sh`
**Purpose:** Sourced (not executed) to make the environment active in the current shell.
**Contract:**
- Modifies PATH, env vars, etc. so the backend's tools are available
- MUST NOT call `exit` (it's sourced)
- MUST be idempotent
- MUST NOT produce output (the caller handles display)
- After sourcing, the environment's primary tool (python, R, cargo, etc.) resolves to the env's version

```bash
# Example: envs/backends/conda/activate.sh
#!/bin/bash
source "$ENV_DIR/../SLCenv/etc/profile.d/conda.sh"
conda activate "$ENV_DIR"
```

```bash
# Example: envs/backends/renv/activate.sh
#!/bin/bash
export R_LIBS_USER="$ENV_DIR/library"
export PATH="$ENV_DIR/bin:$PATH"
```

#### `info.sh`
**Purpose:** Print backend-specific status information (installed packages, versions, etc.).
**Contract:** Output to stdout. Used by `activate` for status display.

### 4.3 Backend Detection Order

When `install_env.py` (or `require_env`) encounters a spec file, it iterates backends in order:

```bash
for backend_dir in "$ENVS_DIR/backends"/*/; do
    if "$backend_dir/detect.sh" "$spec_file"; then
        BACKEND="$backend_dir"
        break
    fi
done
```

The first backend whose `detect.sh` returns 0 wins.

### 4.4 Bootstrap: The Special Case

Conda's SLC bootstrap (Miniforge installation) is unique — it's a one-time system-level setup that creates the base environment which all conda envs inherit from. Other backends don't have this concept:

| Backend | Bootstrap needed? | How? |
|---------|-------------------|------|
| conda | Yes — install Miniforge into `envs/SLCenv/` | `install_SLC.py` (existing) |
| pip/uv | No — Python is already available (system or SLC) | N/A |
| renv | Minimal — needs R installed, renv auto-bootstraps | `Rscript -e "install.packages('renv')"` |
| cargo | No — cargo is installed via rustup (user's responsibility) | N/A |

**Resolution:** The `activate` script handles the conda bootstrap as a special case BEFORE the generic backend loop. This is acceptable because:
1. Conda is the foundational backend (claudechic needs it)
2. Other backends can assume basic system tools exist
3. The bootstrap only runs once

An optional `bootstrap.sh` script in the backend directory handles backend-specific one-time setup if needed.

---

## 5. What's Conda-Specific vs What's Already Generic

### Already Generic (keep as-is or with minimal changes)

| Component | Why it's generic |
|-----------|-----------------|
| `envs/` directory convention | Any backend can store envs here |
| `envs/<name>/` as installed marker | Directory existence check is universal |
| `envs/<name>.<platform>.lock` naming | Platform-specific lockfiles work for any backend |
| `commands/<name>` wrapper pattern | `source require_env <name> && exec <tool>` works for anything |
| `activate` env discovery loop | `for yml in envs/*.*` finds all specs regardless of backend |
| `_meta:origin_hash` in lockfiles | Hash-based staleness detection is backend-agnostic |
| Offline/online install modes | Download-then-install is universal |

### Conda-Specific (must be abstracted)

| Component | What changes |
|-----------|-------------|
| `activate` lines 40-84 | SLC bootstrap + `conda activate` → delegate to `backends/conda/activate.sh` |
| `require_env` lines 50-69 | `SLC_BASE` check + conda init → generic backend detection + `backends/*/activate.sh` |
| `require_env` line 278 | `conda activate` → `source backends/<backend>/activate.sh` |
| `install_env.py` lines 100-114 | `SLC_BASE`/`SLC_PYTHON` checks → detect backend from spec extension, delegate to `backends/*/install.sh` |
| `install_env.py` lines 167-332 | conda create + pip install → delegate to `backends/*/install.sh` |
| `lock_env.py` entire file | conda env export + postprocessing → delegate to `backends/*/lock.sh` |
| `activate` line 202 | `conda activate <name>` display → generic activation command display |

### The Refactoring Pattern

The current code has this shape:

```python
# install_env.py (current — conda-specific)
source_path, source_type = find_env_source(env_name, ENVS_DIR)  # generic
if source_type == "spec":
    subprocess.run(["conda", "env", "create", ...])  # conda-specific
elif source_type == "lockfile":
    subprocess.run(["conda", "create", "--prefix", ...])  # conda-specific
```

The refactored shape:

```python
# install_env.py (refactored — backend-agnostic)
source_path, source_type = find_env_source(env_name, ENVS_DIR)  # generic
backend = detect_backend(source_path, ENVS_DIR / "backends")    # NEW: dispatch
if source_type == "lockfile":
    subprocess.run([backend / "install.sh", "--from-lock", str(lockfile_path)], ...)
else:
    subprocess.run([backend / "install.sh"], ...)
```

The same pattern applies to `require_env`:

```bash
# require_env (refactored activation)
if [[ "${BASH_SOURCE[0]}" != "${0}" ]] && [[ -n "$ENV_NAME" ]]; then
    _backend=$(_detect_backend "$SLC_DIR/envs" "$ENV_NAME")
    source "$_backend/activate.sh"
fi
```

---

## 6. What Happens to the Existing Files

No files are deleted. The existing conda implementation becomes the first backend:

| Current file | Becomes |
|-------------|---------|
| `install_SLC.py` | Stays at root (conda bootstrap is special) |
| `install_env.py` | Refactored: generic dispatch + delegates to backend scripts |
| `lock_env.py` | Refactored: generic dispatch + delegates to backend scripts |
| `commands/require_env` | Refactored: generic check/install/activate via backend scripts |
| `activate` | Refactored: conda bootstrap stays, env display becomes generic |
| *(new)* `envs/backends/conda/` | Conda-specific scripts extracted from install_env.py, lock_env.py, require_env |

The conda backend scripts are mostly cut-and-paste from the existing files — the logic doesn't change, it just moves behind the backend interface.

---

## 7. The Env Convention Template (How to Add an Environment)

### For an Existing Backend (e.g., adding a new conda environment)

```
1. Create envs/<name>.yml with your conda spec
2. Run: python lock_env.py <name>          → generates envs/<name>.<platform>.lock
3. Copy commands/claudechic to commands/<name>, edit to:
   - source require_env <name>
   - exec your tool
4. Test: source activate → shows ○ <name> (available)
5. Test: python install_env.py <name> → installs to envs/<name>/
6. Test: source activate → shows ✔ <name> (installed)
7. Test: commands/<name> → runs your tool in the correct env
```

### For a New Backend (e.g., adding renv for R)

```
1. Create envs/backends/renv/ with:
   - detect.sh   — check for .renv extension
   - install.sh  — call renv::restore()
   - lock.sh     — call renv::snapshot()
   - activate.sh — set R_LIBS_USER, update PATH
   - check.sh    — verify library dir exists
2. Create envs/<name>.renv with your R package spec
3. Create commands/<name> wrapper (same pattern as any other env)
4. Test: install_env.py auto-detects renv backend from .renv extension
5. Test: require_env <name> installs and activates R environment
```

### Command Wrapper Template

Every environment command wrapper follows the same 4-line pattern:

```bash
#!/bin/bash
# <name> — Launch <tool> in its managed environment
source "$(dirname "$0")/require_env" <name> || exit 1
exec <tool> "$@"
```

This is the same for conda, pip, renv, cargo — the backend is invisible to the wrapper.

---

## 8. Swap Test

**The seam is clean if:** you can swap the backend for an environment without changing anything outside `envs/backends/<backend>/` and the spec file.

**Test: Change claudechic from conda to pip/uv.**

1. Create `envs/backends/uv/` with the 5 scripts
2. Create `envs/claudechic.toml` (pyproject.toml format with claudechic deps)
3. Remove or rename `envs/claudechic.yml`

**What should NOT change:**
- `commands/claudechic` — still says `source require_env claudechic && python -m claudechic`
- `activate` — still shows claudechic as available/installed
- `require_env claudechic` — still auto-installs and activates
- `install_env.py claudechic` — still installs (now via uv)

**What DOES change:**
- The spec file (`.yml` → `.toml`)
- The backend scripts called internally
- The lockfile format (conda lock → uv lock)

If only those three things change, the seam is clean.

---

## 9. Seam Summary

| Property | Value |
|----------|-------|
| **Seam location** | `envs/backends/*/` — each backend provides 5 standard scripts |
| **What crosses the seam** | Env name, spec file path, install directory path, platform string |
| **What does NOT cross** | Package manager commands, dependency resolution logic, activation mechanism details |
| **The law** | Every backend implements detect/install/lock/activate/check. The rest of the template calls these scripts — never conda/renv/cargo directly. |
| **Discovery convention** | Spec file extension → `detect.sh` dispatch → backend scripts |
| **Directory convention** | `envs/<name>.{ext}` (spec), `envs/<name>.<platform>.lock` (lock), `envs/<name>/` (installed) |
| **Current hole** | 100% of install/lock/activate code is conda-specific. Refactoring needed to extract conda into `envs/backends/conda/`. |
| **Minimum viable change** | Extract conda logic into backend scripts. `install_env.py` and `require_env` become thin dispatchers. ~200 lines of code movement, ~50 lines of new dispatch logic. |
