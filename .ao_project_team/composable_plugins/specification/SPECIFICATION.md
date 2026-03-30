# AI_PROJECT_TEMPLATE — Specification

> **Status:** Draft v2
> **Date:** 2026-03-29
> **Terminology:** See `specification/terminology.md` for canonical definitions.

---

## 1. Overview

### 1.1 Insight

AI_PROJECT_TEMPLATE is **already composable**. Five filesystem conventions serve as clean seams — drop a file in the right directory, it's discovered automatically. The work is codifying these conventions, documenting them for contributors, and using Copier to assemble the right combination at project creation time.

There is no plugin framework. No runtime dispatch. No manifest loader. The directory structure IS the plugin system.

### 1.2 Platform Support

| Platform | Status | Activation | Hook Scripts | Notes |
|----------|--------|------------|-------------|-------|
| **Linux (x86_64)** | Primary target | `source activate` (bash) | Pure Python | HPC validated on NFS cluster |
| **macOS (ARM64)** | Validated | `source activate` (bash/zsh) | Pure Python | Cross-platform pixi-pack validated |
| **Windows** | First-class | `. activate.ps1` (PowerShell) | Pure Python | Pixi + pure Python hooks — no bash dependency |

**Cross-platform design principles:**
- All hook scripts are **pure Python** (`#!/usr/bin/env python3`) — no bash wrappers
- Environment activation uses **pixi** natively on all platforms (`pixi run`, `pixi shell-hook`)
- Two activation scripts: `activate` (bash/zsh) and `activate.ps1` (PowerShell)
- Command wrappers have a cross-platform equivalent via **pixi tasks** in `pixi.toml`
- `$CLAUDE_PROJECT_DIR` (provided by Claude Code on all platforms) used in hook paths

### 1.3 The Five Seams

| Seam | Directory | Discovery | What you drop in |
|------|-----------|-----------|-----------------|
| **Environments** | `pixi.toml` features | `activate` calls `pixi info` | Pixi feature (named env) |
| **Commands** | `commands/` + `pixi.toml` tasks | `activate` adds to PATH; `pixi run` on all platforms | Executable script (Unix) or pixi task (cross-platform) |
| **Skills** | `.claude/commands/` | Claude Code auto-discovers | `.md` prompt file |
| **Agent Roles** | `AI_agents/**/*.md` | Coordinator reads; `spawn_type_defined` validates | Role definition `.md` file |
| **Guardrail Rules** | `.claude/guardrails/rules.yaml` (+ `rules.d/`) | `generate_hooks.py` reads | YAML rule entries |

Each seam passes the swap test: you can add, remove, or replace what's on one side without changing anything on the other side.

### 1.3 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  BASE (always present)                                       │
│  activate + env management + claudechic                      │
│  (pixi, pixi.toml, pixi.lock, commands/)                      │
└───────────────┬─────────────────────────────────────────────┘
                │ selected at project creation via Copier
    ┌───────────┼───────────┬───────────────┐
    ▼           ▼           ▼               ▼
 guardrails  project-team  pattern-miner  user envs
 (add-on)    (add-on)      (add-on)       (extensible)
```

**Base:** Pixi (env management on conda-forge), the `activate` script, claudechic, and the `commands/` infrastructure. Always present — this is an AI project template, claudechic IS the point.

**Add-ons:** Guardrails, project-team, and pattern-miner are selected during onboarding via Copier. Each is a set of files that land in the right seam directories.

**User environments:** Anyone can add environments by following the codified convention — `pixi add --feature <name> <packages>`, create a command wrapper. Pixi handles spec, lockfile, and installation.

---

## 2. Running Example: R User with Claudechic

Throughout this spec, we use a concrete scenario: **a neuroscience postdoc who has an R project and wants claudechic for AI-assisted coding.**

```bash
# Create project from template
copier copy https://github.com/<org>/AI_PROJECT_TEMPLATE my-neuro-project
cd my-neuro-project
source activate       # bootstraps pixi, installs base envs, shows claudechic

# Add R environment (the user does this — not part of template)
pixi add --feature r-analysis r-base=4.4 r-tidyverse r-lme4 r-brms r-ggplot2
# → pixi.toml updated with [feature.r-analysis.dependencies]
# → pixi.lock regenerated (all environments, all platforms, one file)

pixi install   # → creates .pixi/envs/r-analysis/

# Create command wrapper
cat > commands/r-analysis << 'EOF'
#!/bin/bash
cd "$PROJECT_ROOT" || exit 1
pixi run -e r-analysis R "$@"
EOF

source activate   # now shows: ✔ r-analysis (installed), r-analysis in CLI commands
```

No code changes. No configuration files. The existing conventions handle it.

---

## 3. The Five Seams

### 3.1 Environments (`envs/`)

**Full analysis:** `specification/seam_env_management.md`

#### Convention

| File | Purpose | Example |
|------|---------|---------|
| `pixi.toml` | **Source of truth** — declares all environments as named features | `[feature.claudechic.dependencies]`, `[feature.r-analysis.dependencies]` |
| `pixi.lock` | Multi-platform lockfile — all environments, all platforms, one file | Auto-generated by `pixi add` or `pixi lock` |
| `.pixi/envs/<name>/` | Installed environment directory (managed by pixi) | `.pixi/envs/claudechic/` |
| `envs/<name>.yml` | **Contributor entry point** — familiar conda yml format, imported into pixi.toml via `scripts/import_env.py` | `envs/r-analysis.yml` |

#### `pixi.toml` Multi-Environment Structure

`pixi.toml` is the **source of truth** for all environments. Each environment is a pixi feature + environment mapping:

```toml
[project]
name = "my-project"
channels = ["conda-forge"]
platforms = ["linux-64", "osx-arm64"]

# ── Base environment (always present) ──────────────────────────
[feature.claudechic.dependencies]
python = ">=3.10"
pip = "*"

[feature.claudechic.pypi-dependencies]
claudechic = { path = "submodules/claudechic", editable = true }

# ── Optional environments (added by user or Copier) ───────────
[feature.jupyter.dependencies]
python = ">=3.10"
jupyterlab = "*"

[feature.r-analysis.dependencies]
r-base = ">=4.3"
r-tidyverse = "*"
r-lme4 = "*"
r-brms = "*"
r-ggplot2 = "*"

# ── Environment mappings ──────────────────────────────────────
[environments]
claudechic = ["claudechic"]
jupyter = ["jupyter"]
r-analysis = ["r-analysis"]
```

**One lockfile for everything.** `pixi.lock` covers all environments and all platforms in a single file. This is a major simplification over the previous per-env per-platform lockfile system (`envs/<name>.<platform>.lock`).

#### Contract

- **Spec** is `pixi.toml` — each named environment is a `[feature.<name>]` section with `[feature.<name>.dependencies]`, mapped to an environment in `[environments]`.
- **Lockfile** is `pixi.lock` — single file covering all environments across all platforms. Auto-generated on `pixi add`, `pixi lock`.
- **Installed directory** is `.pixi/envs/<name>/` — created by `pixi install`.
- **`activate`** parses `pixi.toml` `[feature.*]` sections, checks for corresponding installed directories in `.pixi/envs/`, and displays status.

#### The Four Verbs (Design Language)

Every environment operation maps to one of four verbs. This taxonomy is the design language for discussing env management:

| Verb | Tool | What it does |
|------|------|-------------|
| **Spec** | `pixi add --feature <name> <pkg>` | Adds dependency to `pixi.toml`, auto-locks |
| **Install** | `pixi install` | Creates `.pixi/envs/<name>/` from lockfile |
| **Lock** | `pixi lock` | Freezes exact versions to `pixi.lock` (automatic on `pixi add`) |
| **Activate** | `pixi run -e <name> <cmd>` or `pixi shell -e <name>` | Makes env available for command or interactive shell |

#### Conda-forge via Pixi

Pixi resolves packages from conda-forge (and optionally PyPI). Conda-forge covers the target user base:

| Need | Conda-forge package | Status |
|------|-------------------|--------|
| Python + scientific stack | `python`, `numpy`, `scipy`, `pytorch`, `jax` | Excellent |
| R + statistics | `r-base`, `r-tidyverse`, `r-lme4`, `r-brms` | Good — thousands of R packages |
| C/C++ compilers | `gcc`, `gxx`, `clang`, `cmake` | Excellent |
| CUDA/GPU | `cudatoolkit`, `cuda-nvcc` | Excellent |
| HPC tools | `openmpi`, `mpich`, `hdf5` | Excellent |

Pixi also supports native conda + PyPI co-resolution — packages from both registries in a single environment.

#### 3.1.1 Pixi — The Env Backend

**Pixi** (prefix.dev) is the sole env backend. It replaces ~700 lines of custom Python (`install_env.py`, `lock_env.py`, `install_SLC.py`) with a single Rust binary. Combined with **pixi-pack**, it also solves the offline/air-gapped HPC gap.

**Deleted files (no longer in template):**
- `install_SLC.py` — pixi binary replaces Miniforge bootstrap
- `install_env.py` — `pixi install` replaces this
- `lock_env.py` — `pixi lock` (automatic on `pixi add`) replaces this
- `envs/<name>.<platform>.lock` — `pixi.lock` (single multi-platform file) replaces these
- `commands/require_env` — `pixi run -e <name>` replaces the activate-and-run pattern

**Changed role:**
- `envs/<name>.yml` — no longer the source of truth, but **kept as a contributor-friendly entry point**. Contributors drop a yml, run `scripts/import_env.py` to convert it into a pixi feature in `pixi.toml`. The source of truth is `pixi.toml`.

**New files:**
- `pixi.toml` — project manifest with multi-environment support (see §3.1 Convention)
- `pixi.lock` — single lockfile for all environments, all platforms
- `scripts/import_env.py` — converts `envs/<name>.yml` → pixi feature in `pixi.toml`

**HPC validation results (2026-03-29, `/groups/spruston/home/moharb/`):**

| Test | Result | Notes |
|------|--------|-------|
| Pixi install on NFS cluster | ✅ Pass | `pixi install` works on `/groups/spruston/home/moharb/` |
| Editable local package | ✅ Pass | `pixi add --pypi --editable "claudechic @ file:///absolute/path"` works (requires `SETUPTOOLS_SCM_PRETEND_VERSION` for git submodules) |
| Cross-platform pack | ✅ Pass | `pixi-pack pixi.toml --platform osx-arm64` from linux creates valid 104MB tar |
| Wheel injection | ✅ Pass | `--inject dist/claudechic-0.0.0+dev-py3-none-any.whl` works for local packages |
| Offline unpack on Mac | ✅ Pass | `pixi-unpack environment.tar` + `source activate.sh` → claudechic imports successfully |
| Cross-platform Python | ✅ Pass | Python 3.13 on linux-64 cluster, cross-platform lock to osx-arm64 |

**Not yet tested (not v1 blockers):**
- Concurrent NFS access (multiple users running `pixi install` simultaneously on same NFS mount) — low risk, pixi uses atomic file operations
- SLURM job context (running `pixi run` inside `sbatch` scripts) — expected to work since pixi is a standalone binary with no daemon

**Pixi-pack offline workflow:**

```bash
# On a machine with internet:
pixi-pack pack --platform linux-64     # → creates environment.tar (~all packages bundled)

# Transfer to air-gapped HPC node (scp, rsync, USB):
scp environment.tar compute-node:~/my-project/

# On the compute node (no internet):
pixi-unpack environment.tar            # → creates ./env/ + activate.sh
source env/activate.sh                 # → environment ready
```

**Notes:**
- `pixi-unpack` is a separate binary: install with `pixi global install pixi-unpack`
- The unpacked activate script is `activate.sh` (not `activate`) — no collision with the template's own `activate` script
- The tar contains a self-contained local conda channel — no internet needed on the target

**Editable packages and git submodules (claudechic workflow):**

For packages installed in editable mode from git submodules (like claudechic), pixi-pack cannot bundle the editable install directly. The workflow is:

```bash
# 1. Build a wheel from the editable package
pixi run pip wheel --no-deps -w dist/ submodules/claudechic/

# 2. Pack with wheel injection
pixi-pack pack --platform osx-arm64 --inject dist/claudechic-0.0.0+dev-py3-none-any.whl

# 3. On the target machine:
pixi-unpack environment.tar
source env/activate.sh
python -c "import claudechic"  # ✅ works
```

**`SETUPTOOLS_SCM_PRETEND_VERSION` workaround:** Git submodule packages using `setuptools-scm` for versioning need this env var set during build, because the submodule's `.git` directory may not contain full version tags:

```bash
SETUPTOOLS_SCM_PRETEND_VERSION_FOR_CLAUDECHIC=0.1.0 pixi run pip wheel --no-deps -w dist/ submodules/claudechic/
```

#### 3.1.2 The `activate` Script (Pixi)

The `activate` script is the **seam registry** — the one file that knows about all five seams. It bootstraps pixi, sets up the environment, and displays status. Here is the complete script:

```bash
#!/bin/bash
# =============================================================================
# PROJECT ACTIVATE SCRIPT (pixi)
# =============================================================================
# Source this file to activate the project environment.
#
# What it does:
# 1. Resolves project root from script location
# 2. Bootstraps pixi if not installed
# 3. Runs pixi install if environments are not yet installed
# 4. Sets up PATH and PYTHONPATH
# 5. Shows available environments, commands, and skills
#
# This script is the SEAM REGISTRY — it discovers all five seams:
#   - Environments: pixi.toml features → pixi info
#   - Commands: commands/* → added to PATH
#   - Skills: .claude/commands/*.md → displayed
#   - Agent Roles: AI_agents/**/*.md → displayed (if present)
#   - Guardrail Rules: .claude/guardrails/ → displayed (if present)
# Adding a sixth seam requires updating this script.
# =============================================================================

PROJECT_NAME="my-project"

# ─── Section 1: Path Resolution ──────────────────────────────────────────────
if [[ -n "${BASH_SOURCE[0]}" ]]; then
    _SCRIPT_PATH="${BASH_SOURCE[0]}"
elif [[ -n "$0" && "$0" != "-bash" && "$0" != "bash" ]]; then
    _SCRIPT_PATH="$0"
else
    echo "❌ Error: Unable to determine script location."
    echo "💡 Try: source /full/path/to/activate"
    return 1
fi

_SCRIPT_PATH="${_SCRIPT_PATH/#\~/$HOME}"
BASEDIR="$(cd "$(dirname "$_SCRIPT_PATH")" && pwd)"

# ─── Section 2: Pixi Bootstrap ───────────────────────────────────────────────
if ! command -v pixi &> /dev/null; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  First-time setup: Installing pixi..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    curl -fsSL https://pixi.sh/install.sh | bash || {
        echo "❌ Error: pixi installation failed"
        echo "💡 Install manually: https://pixi.sh"
        return 1
    }
    # Add pixi to PATH for this session
    export PATH="$HOME/.pixi/bin:$PATH"
    echo "✔ pixi installed successfully"
    echo ""
fi

# ─── Section 3: Environment Install ──────────────────────────────────────────
# Run pixi install if pixi.toml exists but environments are not yet installed
if [[ -f "$BASEDIR/pixi.toml" ]] && [[ ! -d "$BASEDIR/.pixi/envs" ]]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Installing environments from pixi.toml..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    (cd "$BASEDIR" && pixi install) || {
        echo "❌ Error: pixi install failed"
        echo "💡 Try: cd $BASEDIR && pixi install"
        return 1
    }
    echo "✔ Environments installed"
    echo ""
fi

# ─── Section 4: Environment Setup ────────────────────────────────────────────
export PROJECT_ROOT="$BASEDIR"

# Add repos/ subdirectories to PYTHONPATH (if repos/ exists)
if [[ -d "$BASEDIR/repos" ]]; then
    setopt NULL_GLOB 2>/dev/null || shopt -s nullglob 2>/dev/null
    for repo in "$BASEDIR/repos"/*/; do
        [[ -d "$repo" ]] && export PYTHONPATH="$repo:$PYTHONPATH"
    done
    unsetopt NULL_GLOB 2>/dev/null || shopt -u nullglob 2>/dev/null
fi

# Ensure scripts in commands/ are executable (skip .md files)
if [[ -d "$BASEDIR/commands" ]]; then
    for script in "$BASEDIR/commands"/*; do
        [[ -f "$script" ]] && [[ "$script" != *.md ]] && chmod +x "$script"
    done
fi

# Add commands/ to PATH
export PATH="$BASEDIR/commands:$PATH"

# Configure git hooks (if present)
if [[ -d "$BASEDIR/.git" ]] && [[ -d "$BASEDIR/.githooks" ]]; then
    git -C "$BASEDIR" config core.hooksPath "$BASEDIR/.githooks"
fi

# ─── Section 5: Submodule Auto-Init ──────────────────────────────────────────
_WARNINGS=()

if [[ -f "$BASEDIR/.gitmodules" ]]; then
    _needs_init=false
    if grep -q "claudechic" "$BASEDIR/.gitmodules"; then
        if [[ ! -f "$BASEDIR/submodules/claudechic/pyproject.toml" ]]; then
            _needs_init=true
        fi
    fi

    if [[ "$_needs_init" == true ]]; then
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  Initializing git submodules..."
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        git -C "$BASEDIR" submodule update --init --recursive || {
            _WARNINGS+=("⚠️  Failed to initialize submodules")
            _WARNINGS+=("   Try manually: cd $BASEDIR && git submodule update --init --recursive")
        }
        if [[ -f "$BASEDIR/submodules/claudechic/pyproject.toml" ]]; then
            echo "✔ Submodules initialized successfully"
            echo ""
        fi
    fi
fi

# ─── Section 6: Status Display ───────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  $PROJECT_NAME environment activated"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✔ pixi $(pixi --version 2>/dev/null || echo '(version unknown)')"

# --- Show pixi environments ---
if [[ -f "$BASEDIR/pixi.toml" ]]; then
    installed_envs=()
    available_envs=()

    # Parse environment names from pixi.toml [feature.*] sections
    while IFS= read -r envname; do
        if [[ -d "$BASEDIR/.pixi/envs/$envname" ]]; then
            installed_envs+=("$envname")
        else
            available_envs+=("$envname")
        fi
    done < <(grep -oP '^\[feature\.\K[^]]+(?=\])' "$BASEDIR/pixi.toml" | sort -u)

    if [[ ${#installed_envs[@]} -gt 0 ]]; then
        echo ""
        echo "📦 Installed environments:"
        for env in "${installed_envs[@]}"; do
            echo "    ✔ $env"
        done
        echo "  Use with: pixi run -e <name> <command>"
        echo "  Or shell: pixi shell -e <name>"
    fi

    if [[ ${#available_envs[@]} -gt 0 ]]; then
        echo ""
        echo "📋 Available to install:"
        for env in "${available_envs[@]}"; do
            echo "    ○ $env"
        done
        echo "  Install with: cd $BASEDIR && pixi install"
    fi
fi

# --- Show CLI commands ---
if [[ -d "$BASEDIR/commands" ]]; then
    cli_commands=()
    for script in "$BASEDIR/commands"/*; do
        basename_script=$(basename "$script")
        if [[ -f "$script" ]] && [[ "$basename_script" != *.md ]] && [[ "$basename_script" != .* ]] && [[ -x "$script" ]]; then
            cli_commands+=("$basename_script")
        fi
    done
    if [[ ${#cli_commands[@]} -gt 0 ]]; then
        echo ""
        echo "🛠  CLI commands:"
        for cmd in "${cli_commands[@]}"; do
            echo "    $cmd"
        done
    fi
fi

# --- Show Claude Code skills ---
if [[ -d "$BASEDIR/.claude/commands" ]]; then
    claude_skills=()
    for skill_file in "$BASEDIR/.claude/commands"/*.md; do
        if [[ -f "$skill_file" ]]; then
            skill_name=$(basename "$skill_file" .md)
            skill_title=$(grep -m1 '^# ' "$skill_file" | sed 's/^# *//')
            claude_skills+=("/$skill_name - $skill_title")
        fi
    done
    if [[ ${#claude_skills[@]} -gt 0 ]]; then
        echo ""
        echo "🤖 Claude Code skills:"
        for skill in "${claude_skills[@]}"; do
            echo "    $skill"
        done
    fi
fi

# --- Show guardrails status ---
if [[ -f "$BASEDIR/.claude/guardrails/rules.yaml" ]]; then
    rule_count=$(grep -c '^- id:' "$BASEDIR/.claude/guardrails/rules.yaml" 2>/dev/null || echo "0")
    rulesd_count=0
    if [[ -d "$BASEDIR/.claude/guardrails/rules.d" ]]; then
        rulesd_count=$(find "$BASEDIR/.claude/guardrails/rules.d" -name '*.yaml' 2>/dev/null | wc -l)
    fi
    echo ""
    echo "🛡  Guardrails: $rule_count core rules"
    if [[ $rulesd_count -gt 0 ]]; then
        echo "    + $rulesd_count contributed rule sets in rules.d/"
    fi
fi

# --- Show warnings ---
if [[ ${#_WARNINGS[@]} -gt 0 ]]; then
    echo ""
    for warning in "${_WARNINGS[@]}"; do
        echo "$warning"
    done
fi

echo ""
```

**Key design decisions in this script:**

1. **Pixi bootstrap:** If `pixi` is not on PATH, auto-installs via the official installer. Single binary, no dependencies.
2. **Auto-install:** If `pixi.toml` exists but `.pixi/envs/` doesn't, runs `pixi install` on first activation.
3. **No `require_env`:** Commands use `pixi run -e <name> <cmd>` directly — pixi handles activation internally.
4. **No `SLC_BASE`, `SLC_PYTHON`, `SLC_VERSION`:** These env vars are gone. Only `PROJECT_ROOT` remains.
5. **No `CONDA_ENVS_PATH`:** Pixi manages its own env directory (`.pixi/envs/`).
6. **Seam registry:** The script explicitly documents that it knows about all five seams — adding a sixth requires an update here.
7. **Env activation via `pixi shell-hook`:** On bash/zsh, `eval "$(pixi shell-hook -s bash)"` activates the default environment. On PowerShell, `pixi shell-hook -s powershell | Invoke-Expression`.

#### `activate.ps1` — PowerShell (Windows)

The PowerShell equivalent of `activate`. Same structure, same five seams, same status display.

```powershell
# =============================================================================
# PROJECT ACTIVATE SCRIPT (pixi) — PowerShell
# =============================================================================
# Dot-source this file to activate the project environment:
#   . .\activate.ps1
#
# Same seam registry as activate (bash) — discovers all five seams.
# =============================================================================

$ErrorActionPreference = "Stop"
$ProjectName = "my-project"

# ─── Section 1: Path Resolution ──────────────────────────────────────────────
$BASEDIR = Split-Path -Parent $MyInvocation.MyCommand.Path

# ─── Section 2: Pixi Bootstrap ───────────────────────────────────────────────
if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    Write-Host "  First-time setup: Installing pixi..."
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    Write-Host ""
    try {
        iwr -useb https://pixi.sh/install.ps1 | iex
    } catch {
        Write-Host "❌ Error: pixi installation failed"
        Write-Host "💡 Install manually: https://pixi.sh"
        return
    }
    $env:PATH = "$HOME\.pixi\bin;$env:PATH"
    Write-Host "✔ pixi installed successfully"
    Write-Host ""
}

# ─── Section 3: Environment Install ──────────────────────────────────────────
if ((Test-Path "$BASEDIR\pixi.toml") -and -not (Test-Path "$BASEDIR\.pixi\envs")) {
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    Write-Host "  Installing environments from pixi.toml..."
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    Write-Host ""
    Push-Location $BASEDIR
    try { pixi install } catch {
        Write-Host "❌ Error: pixi install failed"
        Pop-Location
        return
    }
    Pop-Location
    Write-Host "✔ Environments installed"
    Write-Host ""
}

# ─── Section 4: Environment Setup ────────────────────────────────────────────
$env:PROJECT_ROOT = $BASEDIR

# Activate default pixi environment via shell-hook
Push-Location $BASEDIR
pixi shell-hook -s powershell | Invoke-Expression
Pop-Location

# Add repos/ subdirectories to PYTHONPATH
if (Test-Path "$BASEDIR\repos") {
    Get-ChildItem "$BASEDIR\repos" -Directory | ForEach-Object {
        $env:PYTHONPATH = "$($_.FullName);$env:PYTHONPATH"
    }
}

# Add commands/ to PATH
if (Test-Path "$BASEDIR\commands") {
    $env:PATH = "$BASEDIR\commands;$env:PATH"
}

# Configure git hooks (if present)
if ((Test-Path "$BASEDIR\.git") -and (Test-Path "$BASEDIR\.githooks")) {
    git -C $BASEDIR config core.hooksPath "$BASEDIR\.githooks"
}

# ─── Section 5: Submodule Auto-Init ──────────────────────────────────────────
$Warnings = @()

if (Test-Path "$BASEDIR\.gitmodules") {
    if ((Get-Content "$BASEDIR\.gitmodules" -Raw) -match "claudechic") {
        if (-not (Test-Path "$BASEDIR\submodules\claudechic\pyproject.toml")) {
            Write-Host ""
            Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            Write-Host "  Initializing git submodules..."
            Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            Write-Host ""
            try {
                git -C $BASEDIR submodule update --init --recursive
                Write-Host "✔ Submodules initialized successfully"
            } catch {
                $Warnings += "⚠️  Failed to initialize submodules"
            }
        }
    }
}

# ─── Section 6: Status Display ───────────────────────────────────────────────
# Delegate to cross-platform Python script for consistent output
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "  $ProjectName environment activated"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

$pixiVersion = try { pixi --version 2>$null } catch { "(version unknown)" }
Write-Host "  ✔ pixi $pixiVersion"

# Show pixi environments
if (Test-Path "$BASEDIR\pixi.toml") {
    $features = Select-String -Path "$BASEDIR\pixi.toml" -Pattern '^\[feature\.([^\]]+)\]' |
        ForEach-Object { $_.Matches.Groups[1].Value } | Sort-Object -Unique
    $installed = @()
    $available = @()
    foreach ($f in $features) {
        if (Test-Path "$BASEDIR\.pixi\envs\$f") { $installed += $f }
        else { $available += $f }
    }
    if ($installed.Count -gt 0) {
        Write-Host ""
        Write-Host "📦 Installed environments:"
        $installed | ForEach-Object { Write-Host "    ✔ $_" }
        Write-Host "  Use with: pixi run -e <name> <command>"
    }
    if ($available.Count -gt 0) {
        Write-Host ""
        Write-Host "📋 Available to install:"
        $available | ForEach-Object { Write-Host "    ○ $_" }
        Write-Host "  Install with: pixi install"
    }
}

# Show CLI commands
if (Test-Path "$BASEDIR\commands") {
    $cmds = Get-ChildItem "$BASEDIR\commands" -File |
        Where-Object { $_.Extension -ne ".md" -and $_.Name -notlike ".*" } |
        Select-Object -ExpandProperty Name
    if ($cmds.Count -gt 0) {
        Write-Host ""
        Write-Host "🛠  CLI commands:"
        $cmds | ForEach-Object { Write-Host "    $_" }
    }
}

# Show Claude Code skills
if (Test-Path "$BASEDIR\.claude\commands") {
    $skills = Get-ChildItem "$BASEDIR\.claude\commands\*.md" -ErrorAction SilentlyContinue
    if ($skills.Count -gt 0) {
        Write-Host ""
        Write-Host "🤖 Claude Code skills:"
        foreach ($s in $skills) {
            $name = $s.BaseName
            $title = (Select-String -Path $s.FullName -Pattern '^# (.+)' |
                Select-Object -First 1).Matches.Groups[1].Value
            Write-Host "    /$name - $title"
        }
    }
}

# Show guardrails status
if (Test-Path "$BASEDIR\.claude\guardrails\rules.yaml") {
    $ruleCount = (Select-String -Path "$BASEDIR\.claude\guardrails\rules.yaml" -Pattern '^- id:').Count
    Write-Host ""
    Write-Host "🛡  Guardrails: $ruleCount core rules"
    if (Test-Path "$BASEDIR\.claude\guardrails\rules.d") {
        $rdCount = (Get-ChildItem "$BASEDIR\.claude\guardrails\rules.d\*.yaml" -ErrorAction SilentlyContinue).Count
        if ($rdCount -gt 0) { Write-Host "    + $rdCount contributed rule sets in rules.d/" }
    }
}

# Show warnings
foreach ($w in $Warnings) { Write-Host $w }
Write-Host ""
```

**Both scripts are structurally identical:** same 6 sections, same seam discovery, same status output. The difference is syntax (bash vs PowerShell) and pixi bootstrap method (`curl | bash` vs `iwr | iex`).

**Command wrapper pattern (pixi):**

```bash
#!/bin/bash
# commands/r-analysis — env-activating wrapper
cd "$PROJECT_ROOT" || exit 1
pixi run -e r-analysis R "$@"
```

Two lines. No `require_env` needed — `pixi run` handles env resolution, installation check, and activation internally.

#### How to Add an Environment

**Method A — Direct pixi add (power users):**

```
1. Add packages as a pixi feature:
   pixi add --feature r-analysis r-base=4.4 r-tidyverse r-lme4 r-brms r-ggplot2
   → pixi.toml updated with [feature.r-analysis.dependencies]
   → pixi.lock regenerated automatically (all environments, all platforms)

2. Add environment mapping (if pixi add didn't create it):
   # Append to pixi.toml [environments] section:
   r-analysis = ["r-analysis"]

3. Install:
   pixi install
   → creates .pixi/envs/r-analysis/

4. Create command wrapper:
   cat > commands/r-analysis << 'EOF'
   #!/bin/bash
   cd "$PROJECT_ROOT" || exit 1
   pixi run -e r-analysis R "$@"
   EOF

5. Verify:
   source activate
   → shows ✔ r-analysis (installed)
   → shows r-analysis in CLI commands
   r-analysis --version
   → R 4.4.x
```

**Method B — Drop a yml file (contributor-friendly entry point):**

```
1. Create envs/r-analysis.yml:
   name: r-analysis
   channels: [conda-forge]
   dependencies: [r-base=4.4, r-tidyverse, r-lme4, r-brms, r-ggplot2]

2. Run the import script:
   python scripts/import_env.py envs/r-analysis.yml
   → Reads the yml, adds [feature.r-analysis.dependencies] to pixi.toml
   → Adds r-analysis = ["r-analysis"] to [environments]
   → Runs pixi lock to update pixi.lock

3. Install + create command wrapper (same as Method A steps 3-5)
```

The `envs/*.yml` format is the contributor-friendly entry point. `pixi.toml` is the source of truth. The import script bridges them.

**For a C/C++ toolchain (Method A):**
```bash
pixi add --feature c-toolchain gcc gxx cmake make gdb valgrind
```

Same steps. Same `pixi install`. Same `activate` display. The convention handles it.

#### Cross-seam Connection

Environments connect to **commands** through `pixi run`:

```
pixi.toml [feature.r-analysis]  →  pixi install  →  .pixi/envs/r-analysis/
                                                              ↑
commands/r-analysis  →  pixi run -e r-analysis R "$@"  →  pixi activates env internally
```

---

### 3.2 Commands (`commands/` + pixi tasks)

**Full analysis:** `specification/seam_commands_and_skills.md`

The Commands seam has **two expressions** — shell scripts for Unix, pixi tasks for cross-platform:

#### Convention

| File / Config | Purpose | Platform |
|---------------|---------|----------|
| `commands/<name>` | Executable script — added to PATH by `activate` | Unix (bash/zsh) |
| `commands/<name>.md` | Optional documentation (skipped by discovery) | All |
| `pixi.toml` `[feature.<name>.tasks]` | Pixi task — run via `pixi run <task>` | **All platforms** |

#### Contract (Unix `commands/`)

- Must be a regular file (not directory, not symlink target).
- Must not be a `.md` file or dotfile (those are skipped).
- `activate` auto-chmods everything to executable — author doesn't need to remember.
- Gets `PROJECT_ROOT`, `PATH` (includes `commands/` itself), `PYTHONPATH`.

#### Contract (pixi tasks — cross-platform)

- Defined in `pixi.toml` under `[feature.<name>.tasks]` or top-level `[tasks]`.
- Run via `pixi run <task>` or `pixi run -e <env> <task>`.
- Works on Linux, macOS, and Windows without modification.
- Every `commands/<name>` wrapper SHOULD have a corresponding pixi task.

#### Pixi Tasks in `pixi.toml`

```toml
[feature.claudechic.tasks]
claudechic = "claudechic"

[feature.jupyter.tasks]
jupyter = "jupyter lab"

[feature.r-analysis.tasks]
r-analysis = "R"

# Infrastructure tasks (not env-specific)
[tasks]
generate-hooks = "python3 .claude/guardrails/generate_hooks.py"
mine-patterns = { cmd = "python3 scripts/mine_patterns.py", env = "claudechic" }
```

**Usage (cross-platform):**
```bash
pixi run -e claudechic claudechic    # Works on Linux, macOS, Windows
pixi run -e jupyter jupyter          # Works on Linux, macOS, Windows
pixi run generate-hooks              # Works on Linux, macOS, Windows
```

#### Shell Script Patterns (Unix)

**Pattern A — Env-activating wrapper** (most commands):

```bash
#!/bin/bash
# <name> — Launch <description>
cd "$PROJECT_ROOT" || exit 1
pixi run -e <env-name> <tool> "$@"
```

Examples: `commands/claudechic`, `commands/jupyter`, `commands/r-analysis`.

**Pattern B — Standalone script** (infrastructure utilities):

```bash
#!/bin/bash
# <name> — <description>
# Can assume PROJECT_ROOT is set
<any logic>
```

Example: `commands/generate-hooks` (runs guardrail hook generation).

#### How to Add a Command

```
1. Add a pixi task (cross-platform — do this first):
   # In pixi.toml:
   [feature.<env-name>.tasks]
   <name> = "<tool>"

2. (Unix) Create commands/<name> using Pattern A or B above.

3. (Optional) Create commands/<name>.md with usage docs.

4. Verify:
   pixi run -e <env-name> <name>     # works on all platforms
   source activate → shows <name>     # Unix: also on PATH
```

---

### 3.3 Skills (`.claude/commands/*.md`)

**Full analysis:** `specification/seam_commands_and_skills.md`

#### Convention

| File | Purpose |
|------|---------|
| `.claude/commands/<skill-name>.md` | Claude Code slash command — the file IS the prompt |

#### Contract

- Must be a `.md` file in `.claude/commands/`.
- First `# ` heading becomes the skill title (shown in `activate` display and Claude Code's skill list).
- File content is sent to Claude when user types `/<skill-name>`.
- `$ARGUMENTS` placeholder captures user input after the command.

#### Good Pattern: Short Entry Point

```markdown
# Launch Project Team

Read and follow: `AI_agents/project_team/COORDINATOR.md`
```

Two lines. Delegates to a detailed file. Updates to the workflow don't require skill changes. Context window is preserved.

#### Anti-patterns

| Anti-pattern | Fix |
|--------------|-----|
| 500-line skill file | Move logic to referenced file — skill becomes a pointer |
| Hard-coded absolute paths | Use paths relative to project root |
| No success criteria | Include "Done when:" or "Output:" |

#### How to Add a Skill

```
1. Create .claude/commands/<skill-name>.md:
   # <Title>
   <Instructions for Claude>

2. source activate → shows /<skill-name> - <Title>
3. Type /<skill-name> in Claude Code → Claude follows instructions.
```

#### Skill Template (with arguments)

```markdown
# <Title>

<One-line description.>

The user wants: $ARGUMENTS

<Instructions for Claude.>
```

---

### 3.4 Agent Roles (`AI_agents/**/*.md`)

**Full analysis:** `specification/seam_roles_and_guardrails.md`

#### Convention

| File | Purpose |
|------|---------|
| `AI_agents/project_team/<UPPER_SNAKE>.md` | Role definition for a spawnable agent |

#### Naming Convention

- **Filename:** `UPPER_SNAKE_CASE.md` — e.g., `TEST_ENGINEER.md`
- **Type string (CamelCase):** `TestEngineer` — used in `spawn_agent(type="TestEngineer")`
- **Transform:** CamelCase → UPPER_SNAKE via two-pass regex (bidirectional, deterministic)
- **The `spawn_type_defined` guardrail** validates at spawn time that a matching file exists

#### Contract: Required Elements

| Element | Purpose |
|---------|---------|
| `# <Role Name>` heading | Identity — agent reads this first |
| Responsibility statement | What this agent does (and does NOT do) |
| Output format | Structured template for results (so Coordinator and other agents can parse) |
| Interaction table | Who this role receives from, hands off to |
| Authority bounds | What this agent CAN and CANNOT do |

#### Connection to Guardrails

Roles connect to guardrails through `CLAUDE_AGENT_ROLE` (set from `spawn_agent(type=...)`):

```
spawn_agent(type="Implementer")
    → CLAUDE_AGENT_ROLE = "Implementer"
    → rules.yaml: block: [Implementer] matches
    → role_guard.py enforces the rule
```

Role groups provide broader scoping:
- `Agent` — all agents with `CLAUDE_AGENT_NAME` set
- `TeamAgent` — Coordinator + sub-agents in team mode
- `Subagent` — sub-agents only (Coordinator exempt)

#### How to Add a Role

```
1. Create AI_agents/project_team/<UPPER_SNAKE>.md with required elements.
   Example: DataValidator → DATA_VALIDATOR.md

2. (Optional) Add guardrail rules targeting the role:
   - id: R30
     block: [DataValidator]
     ...

3. Regenerate hooks: python3 .claude/guardrails/generate_hooks.py

4. Tell Coordinator when to spawn this role (edit COORDINATOR.md
   or let Coordinator discover dynamically based on project needs).

5. spawn_type_defined auto-validates: if the file doesn't exist
   when spawn is attempted, the guardrail fires a warning.
```

#### Role Template

```markdown
# <Role Name>

<One sentence: what this agent does.>

## Your Role

You are responsible for <domain>. You:
1. <Primary responsibility>
2. <Secondary responsibility>
3. <Tertiary responsibility>

## Output Format

```markdown
## <Output Title>
### <Section>
- <Structured output>
```

## Interaction with Other Agents

| Agent | Your Relationship |
|-------|-------------------|
| **Coordinator** | <How you interact> |
| **<Other>** | <How you interact> |

## Authority

- You CAN <permitted actions>
- You CANNOT <forbidden actions>
```

---

### 3.5 Guardrail Rules (`.claude/guardrails/`)

**Full analysis:** `specification/seam_roles_and_guardrails.md`

#### Convention

| File | Purpose |
|------|---------|
| `.claude/guardrails/rules.yaml` | Core project rules (source of truth) |
| `.claude/guardrails/rules.d/*.yaml` | **NEW:** Contributed rule sets (merged by `generate_hooks.py`) |
| `.claude/guardrails/generate_hooks.py` | Code generator — emits **pure Python** hook scripts from rules |
| `.claude/guardrails/role_guard.py` | Runtime — role resolution, permission checking, ack tokens |
| `.claude/guardrails/hooks/*.py` | Generated hook scripts — **pure Python**, cross-platform (regenerated, not hand-edited) |
| `.claude/guardrails/messages/<ID>.md` | Long-form messages for rules (optional) |

#### Hook Architecture: Pure Python (Cross-Platform)

Generated hooks are **pure Python scripts** — no bash wrappers. This ensures hooks work on Linux, macOS, and Windows without modification.

**Generated hook structure:**

```python
#!/usr/bin/env python3
"""bash_guard.py — AUTO-GENERATED by generate_hooks.py — DO NOT EDIT"""
import json, os, re, sys
from pathlib import Path

# Read hook input from stdin (Claude Code sends JSON)
data = json.loads(sys.stdin.read())
command = data.get('tool_input', {}).get('command', '')

# [GENERATED] Rule matching code — inlined from rules.yaml at generation time
# ... pattern matching, role checks via role_guard.py ...

# Exit code protocol (same on all platforms):
#   0 = allow (tool call proceeds)
#   2 = block (tool call rejected, message on stderr)
sys.exit(0)
```

**Hook configuration in `.claude/settings.json`:**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/guardrails/hooks/bash_guard.py"
        }]
      },
      {
        "matcher": "Read",
        "hooks": [{
          "type": "command",
          "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/guardrails/hooks/read_guard.py"
        }]
      },
      {
        "matcher": "Write",
        "hooks": [{
          "type": "command",
          "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/guardrails/hooks/write_guard.py"
        }]
      },
      {
        "matcher": "Glob",
        "hooks": [{
          "type": "command",
          "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/guardrails/hooks/glob_guard.py"
        }]
      }
    ]
  }
}
```

**Notes:**
- `$CLAUDE_PROJECT_DIR` is provided by Claude Code on all platforms — resolves to the project root.
- `python3` prefix ensures the script runs as Python regardless of OS file associations.
- Exit code protocol: `0` = allow, `2` = block (with message on stderr). Same on all platforms.
- MCP trigger hooks (`mcp__*_guard.py`) are auto-added to `settings.json` by `generate_hooks.py`.

**Change from previous architecture:** Hooks were previously bash scripts with embedded Python heredocs (`bash_guard.sh` → `python3 << 'PYEOF' ... PYEOF`). The new architecture eliminates the bash wrapper — the Python IS the hook script. This removes the bash dependency from the most critical path (every Claude Code tool call goes through hooks).

#### Rule Anatomy

```yaml
- id: R01                           # Unique identifier
  name: example-rule                 # Human-readable name
  trigger: PreToolUse/Bash           # When to intercept
  enforcement: deny                  # log | warn | deny | inject
  detect:
    type: regex_match                # regex_match | regex_miss | always | spawn_type_defined
    pattern: '\bdangerous\b'         # Regex pattern
  block: [Subagent]                  # (optional) Role scoping
  message: "[R01] Denied."           # Feedback to agent
```

#### ID Namespace Convention

| Range | Owner | Example |
|-------|-------|---------|
| `R01`–`R99` | Core project rules | `R01: no-force-push` |
| `FW01`–`FW99` | Framework test rules (reserved) | `FW01: regex-match-deny` |
| `S01`–`S99` | Spawn validation rules | `S01: spawn-type-defined` |
| `<PREFIX>01`–`99` | Contributed rule sets | `HPC01`, `BIO01`, `SCI01` |

#### `rules.d/` Include Directory (NEW)

`generate_hooks.py` is modified to merge `rules.d/*.yaml` into the rule set before validation. This is the key mechanism for contributed rule sets — drop a YAML file, regenerate hooks.

```
.claude/guardrails/
├── rules.yaml              # Core project rules
├── rules.d/                # Contributed rules (NEW)
│   ├── scientific.yaml     # Scientific guardrails (FOCUS Framework)
│   └── hpc.yaml            # HPC-specific rules
├── generate_hooks.py       # Modified: globs rules.d/*.yaml
└── ...
```

**Change to `generate_hooks.py`:** Before validation, load all `rules.d/*.yaml` files and append their `rules:` lists to the main rule set. IDs must not collide (enforced at validation time).

#### How to Add a Rule Set

```
1. Create .claude/guardrails/rules.d/<name>.yaml:
   rules:
     - id: <PREFIX>01
       name: <descriptive-name>
       trigger: PreToolUse/Bash
       enforcement: warn
       detect:
         type: regex_match
         pattern: '<pattern>'
       message: "[<PREFIX>01] <message>"

2. Use namespaced IDs to avoid collisions with core rules.

3. Regenerate hooks: python3 .claude/guardrails/generate_hooks.py

4. Test: pipe test input to the generated hook script.
```

---

## 4. Onboarding (Copier)

### 4.1 Strategy

| Tier | Implementation | Priority |
|------|---------------|----------|
| **CLI** | Copier questionnaire (`copier copy`) | MVP — implement first |
| **Claude skill** | `/init-project` — primary UX for new users | Second — low marginal cost |
| **Web** | Deferred | Only if demonstrated need |

All tiers produce the same output: a project directory with files in the right seam directories.

### 4.2 Copier Questionnaire (`copier.yml`)

```yaml
_min_copier_version: "9.0.0"
_subdirectory: "template"

project_name:
  type: str
  help: "Your project name (used for directory name and env naming)"
  validator: "{% if not project_name %}Project name is required{% endif %}"

use_guardrails:
  type: bool
  default: true
  help: |
    Enable the guardrails permission system?
    Provides: Role-based access control for Claude Code tool calls.
    Rules defined in rules.yaml, guardrail hooks auto-generated.

use_project_team:
  type: bool
  default: true
  help: |
    Enable multi-agent project team workflow?
    Provides: Coordinator, Implementer, Skeptic, Composability,
    and other agent roles for structured project execution.

use_pattern_miner:
  type: bool
  default: false
  help: |
    Enable the pattern miner?
    Scans Claude session history for user corrections and feeds
    them into PATTERNS.md. Useful for improving agent behavior.

project_type:
  type: str
  default: "general"
  choices:
    general: "General software project"
    scientific: "Scientific computing / research project"
  help: "What kind of project? Scientific projects unlock domain-specific questions."

science_domain:
  type: str
  default: ""
  when: "{{ project_type == 'scientific' }}"
  choices:
    biology: "Biology / Genomics / Neuroscience"
    physics: "Physics / Cosmology / Materials"
    chemistry: "Chemistry / Drug Discovery"
    data_science: "Data Science / ML / Statistics"
    other: "Other scientific domain"
  help: "What scientific domain? Used to suggest relevant skill packs."

autonomous_agents:
  type: bool
  default: false
  when: "{{ project_type == 'scientific' }}"
  help: |
    Will agents run autonomously (overnight / weekend)?
    If yes, scaffolds CLAUDE.md with research goals, CHANGELOG.md
    as agent memory, test oracle directories, and stricter guardrails.

existing_codebase:
  type: str
  default: ""
  help: |
    Path to an existing codebase to integrate (leave empty for fresh project).
    The codebase will be linked/copied into the repos/ directory.

_exclude:
  - "{% if not use_guardrails %}.claude/guardrails/{% endif %}"
  - "{% if not use_project_team %}AI_agents/{% endif %}"
  - "{% if not use_project_team %}.claude/commands/ao_project_team.md{% endif %}"
  - "{% if not use_pattern_miner %}scripts/mine_patterns.py{% endif %}"
  - "{% if not use_pattern_miner %}commands/mine-patterns{% endif %}"
```

**What Copier does:** Selects which files land in which seam directories. Guardrails files go in `.claude/guardrails/`. Project-team roles go in `AI_agents/project_team/`. Pattern-miner script goes in `scripts/`. Copier's Jinja2 conditionals exclude files for disabled add-ons.

**What Copier does NOT do:** No runtime dispatch. No manifest that `activate` reads. The `activate` script stays as-is — it discovers whatever is in `envs/`, `commands/`, and `.claude/commands/` regardless of how it got there.

### 4.3 Onboarding Commands

```bash
# Fresh project
pip install copier
copier copy https://github.com/<org>/AI_PROJECT_TEMPLATE my-project
cd my-project
source activate

# Update to latest template
copier update
```

### 4.4 The "Overnight Agent" Pattern (Scientific Users)

For users who select `autonomous_agents: true`, the template scaffolds:

1. **CLAUDE.md** — Master instructions with research goals, success criteria, design decisions
2. **CHANGELOG.md** — Structured agent memory (completed tasks, failed approaches, metrics)
3. **Test oracle directory** — Reference implementations for self-validation
4. **Git commit patterns** — Agents commit after meaningful work units
5. **Stricter guardrails** — Deny destructive actions for unattended operation

Documented by Anthropic's "Long-Running Claude for Scientific Computing" research — scientists running Claude Code on HPC for 48+ hour GPU allocations.

### 4.5 Claude Skill (`/init-project`) — Primary Onboarding Path

The `/init-project` skill (`.claude/commands/init_project.md`) is the **recommended onboarding path for new users**. It:

1. **Understands user context** — asks about the project, language, existing code
2. **Explains WHY each add-on matters** — not just "enable guardrails?" but explains the value
3. **Handles ambiguity** — "I have a Python project with conda" maps naturally to the right choices
4. **Maps answers to Copier** — translates decisions into `copier copy --data` flags
5. **Reports results** — confirms what was set up, shows next steps

Produces the same files as the CLI. The conversational layer adds UX quality.

---

## 5. Existing Codebase Integration

### 5.1 Two Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Fresh** | `existing_codebase` is empty | Generate full project from template |
| **Integrate** | `existing_codebase` is a path | Generate template around existing code |

### 5.2 Integration Flow

1. **Validate path:** Confirm exists and is a directory.
2. **Detect existing tooling:** Check for `.git/`, `environment.yml`, `requirements.txt`, `.claude/`, `pyproject.toml`.
3. **Link codebase:** Symlink or copy into `repos/<basename>/`.
4. **Handle `.claude/` conflicts (manual merge for v1):**
   - If the existing codebase has a `.claude/` directory, **do not auto-merge**.
   - Detect the conflict and print a diff showing what the template wants to add vs what already exists.
   - Let the user merge manually. Example output:
     ```
     ⚠️  Existing .claude/ directory detected at /path/to/codebase/.claude/

     The template wants to add these files:
       + .claude/commands/ao_project_team.md
       + .claude/guardrails/rules.yaml
       + .claude/guardrails/generate_hooks.py

     These files already exist in your codebase (not overwritten):
       ≡ .claude/settings.json
       ≡ .claude/commands/my-existing-skill.md

     Please review and merge manually:
       cp -n template/.claude/commands/* /path/to/codebase/.claude/commands/
     ```
   - **Rationale:** Auto-merging JSON/YAML files is fragile and hard to debug. For v1, manual merge with clear guidance is safer and more transparent.
5. **PYTHONPATH setup:** `activate` already adds `repos/*/` to PYTHONPATH.

### 5.3 Failure Scenarios

| Scenario | Mitigation |
|----------|------------|
| **File conflicts** (existing `activate`, `commands/`, `.claude/`) | Copier conflict resolution + manual `.claude/` merge with diff output |
| **Path assumptions** (`PROJECT_ROOT` check) | `activate` resolves `BASEDIR` from its own location — no git root assumption |
| **Env collision** (user already has conda/pip) | Pixi manages its own `.pixi/` directory — doesn't modify user's base conda or pip |
| **Nested repos** (template inside larger repo) | `activate` resolves `BASEDIR` from its own location, not git root |

---

## 6. Pattern Miner Port

### 6.1 Source

Port from: `/groups/spruston/home/moharb/DECODE-PRISM/scripts/mine_patterns.py`

### 6.2 Validation

The STELLA biomedical agent system (FutureHouse) independently validates this approach — dynamically expanding tool/reasoning libraries from experience. Pattern mining is a validated self-improvement pattern.

### 6.3 Required Changes

#### 6.3.1 JSONL Parsing Isolation

Extract parsing into a clearly bounded layer — the ONLY code that touches the JSONL format:

```python
KNOWN_VERSIONS = {"2.1.59", "2.1.60", ...}

@dataclass
class Message:
    role: str           # "user" | "assistant"
    text: str
    timestamp: str | None
    session_id: str | None

def parse_session(path: Path) -> ParseResult:
    """Returns ParseResult with messages, metadata, parse_stats."""
```

#### 6.3.2 Version Checking

Warn if JSONL version is not in known-good list. Silent failures are the real risk.

#### 6.3.3 Configurable Project Directories

Replace hard-coded paths with auto-discovery (`~/.claude/projects/`) or explicit CLI args.

#### 6.3.4 Validation Mode

`--validate` flag: report parsing stats without running the pipeline.

#### 6.3.5 Configurable Role Detection

Replace hard-coded role names with a configurable list (defaults to project-team roles).

#### 6.3.6 Snapshot JSONL Integration Tests

```
scripts/tests/
├── fixtures/
│   ├── v2.1.59_main_session.jsonl
│   ├── v2.1.59_subagent_session.jsonl
│   └── v2.1.59_tool_results.jsonl
├── test_parser.py          # Unit tests for parsing layer
└── test_regression.py      # Snapshot comparison tests
```

**Maintenance rule:** On Claude Code updates, capture a sample session as a new fixture. If `test_regression.py` fails, update the parsing layer.

---

## 7. Env Var Abstraction

### 7.1 Change

| Current | New | Rationale |
|---------|-----|-----------|
| `CLAUDECHIC_APP_PID` | `AGENT_SESSION_PID` | Removes runtime-specific name |
| `CLAUDE_AGENT_NAME` | *(unchanged)* | Claude Code's own variable |
| `CLAUDE_AGENT_ROLE` | *(unchanged)* | Claude Code's own variable |

### 7.2 Migration in `role_guard.py`

```python
# Backward-compatible fallback
app_pid = os.environ.get('AGENT_SESSION_PID') or os.environ.get('CLAUDECHIC_APP_PID')
```

### 7.3 Session Marker Path

```
# BEFORE: .claude/guardrails/sessions/ao_<CLAUDECHIC_APP_PID>
# AFTER:  .claude/guardrails/sessions/ao_<AGENT_SESSION_PID>
```

`setup_ao_mode.sh` and `teardown_ao_mode.sh` in claudechic must be updated.

---

## 8. Code Changes Required

Only actual code changes — no new systems:

| # | Change | Files | Effort |
|---|--------|-------|--------|
| 1 | **Pixi `activate` + `activate.ps1`** — rewrite for pixi, add Windows support | Rewrite `activate` (see §3.1.2). Write `activate.ps1`. Delete `install_env.py`, `lock_env.py`, `install_SLC.py`, `commands/require_env`. Add `pixi.toml`, `pixi.lock`. Add `scripts/import_env.py` (yml→pixi feature converter). | Large — core migration |
| 2 | **Pure Python guardrail hooks** — cross-platform | Modify `generate_hooks.py` to emit `.py` scripts instead of `.sh` wrappers. Update `.claude/settings.json` hook paths (`.sh` → `.py` with `python3` prefix). | Medium — ~50 lines in generator |
| 3 | **`rules.d/` support** in `generate_hooks.py` | `generate_hooks.py` | Small — add glob + merge before validation |
| 4 | **Env var rename** in `role_guard.py` | `role_guard.py` | Tiny — one line with fallback |
| 5 | **Env var rename** in claudechic | `setup_ao_mode.sh`, `teardown_ao_mode.sh` | Tiny |
| 6 | **Pattern miner port** with JSONL isolation | `scripts/mine_patterns.py` (new), `commands/mine-patterns` (new) | Medium |
| 7 | **Copier template** | `copier.yml`, `template/` directory (includes both `activate` and `activate.ps1`) | Medium |
| 8 | **Pixi tasks** — add to `pixi.toml` for all command wrappers | `pixi.toml` `[feature.*.tasks]` sections | Small |
| 9 | **Command wrappers** — update to use `pixi run` pattern | `commands/claudechic`, any other env-activating wrappers | Small |
| 10 | **CI: Windows matrix** — add `windows-latest` to GitHub Actions | `.github/workflows/` | Small |
| 11 | **Contributor docs/templates** for each seam | Documentation files | Medium |

### 8.1 CI Testing Matrix

```yaml
# .github/workflows/test.yml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    include:
      - os: ubuntu-latest
        activate: "source activate"
        shell: bash
      - os: macos-latest
        activate: "source activate"
        shell: bash
      - os: windows-latest
        activate: ". activate.ps1"
        shell: pwsh
```

**What's testable cross-platform:**
- `pixi install` succeeds
- Guardrail hook scripts execute (`python3 hooks/bash_guard.py < test_input.json`)
- `activate` / `activate.ps1` sets `PROJECT_ROOT` and adds `commands/` to PATH
- Pixi tasks run (`pixi run -e claudechic claudechic --version`)
- `generate_hooks.py --check` passes (drift detection)

**Linux-only tests (CI runs on Linux):**
- `commands/*` shell scripts execute
- E2E tests (`tests/ci/test_activate.sh`, etc.)

---

## 9. Future Considerations

### 9.1 Future Add-ons

#### General

| Add-on | Description | Evidence |
|--------|-------------|----------|
| CI/CD Templates | GitHub Actions for testing, linting, deploy | Nx generators, ECC |
| Documentation Generator | MkDocs/Sphinx + API docs | Projen, ECC |
| Observability / Tracing | Agent interactions, costs, latencies | OpenAI Agents SDK tracing |
| Linting / Code Quality | ruff, mypy, pre-commit hooks | ECC linting skills |
| Secrets Management | `.env` handling, secret detection | dotenv, git-secrets |
| MCP Server Templates | Scaffold custom MCP servers | Claude Code MCP docs |

#### Scientific

| Add-on | Description | Evidence |
|--------|-------------|----------|
| Scientific Computing Setup | CLAUDE.md + test oracles + git patterns | Anthropic "Long-Running Claude" |
| HPC/SLURM Integration | Job templates, tmux, GPU allocation | Anthropic research blog |
| AI Contribution Tracker | Logs AI outputs, generates disclosures | FOCUS Framework Rule 9 |
| Citation Validator | Check references against PubMed/DOI | FOCUS Rule 6; AI Scientist |
| Domain Skill Packs | Genomics, physics, chemistry skills | K-Dense-AI (170+ skills) |
| Data Science Layout | CCDS-compatible directories | Cookiecutter Data Science |
| Scientific Guardrails | Data provenance, statistical validation | FOCUS Framework |

Each future add-on follows the same pattern: files in the right seam directories. No framework changes needed.

---

## 10. Explicit Scope Limits

What this specification intentionally excludes:

- **No plugin base class or Python interface.** The directory conventions ARE the interface.
- **No runtime manifest or dispatcher.** The `activate` script stays as-is — it discovers files, not plugins.
- **No `plugin.yaml` manifests.** Each seam has its own convention; no unified metadata schema.
- **No dynamic plugin discovery.** Files exist or they don't.
- **No event bus or inter-plugin messaging.** Seams share only the filesystem.
- **No multi-backend env abstraction.** Pixi (resolving from conda-forge + PyPI) is the sole env backend. The seam analysis documents where to cut if a second backend is ever needed.
- **No web-based onboarding.** Deferred until demonstrated need.

Each limit can be revisited when concrete need arises. The seam analyses document where the extension points are.
