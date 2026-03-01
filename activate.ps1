# =============================================================================
# PROJECT ACTIVATE SCRIPT (PowerShell)
# =============================================================================
# Dot-source this file to activate the project environment.
#
# Usage: . .\activate.ps1
#
# What it does:
# 1. Bootstraps SLC (Miniforge) if not installed
# 2. Activates the conda environment
# 3. Sets up PATH and PYTHONPATH
# 4. Shows available commands and skills
#
# Customization:
# - Change PROJECT_NAME below for your project
# - Add project-specific PYTHONPATH entries in Section 2
#
# Note: May require: Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
# =============================================================================

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ CUSTOMIZE: Change this to your project name                               ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
$PROJECT_NAME = "my-project"

# --------------------------------------------------------------------------
# Section 1: Path Resolution
# --------------------------------------------------------------------------
# $PSScriptRoot is the directory containing this script
$BASEDIR = $PSScriptRoot
$SLCENV_DIR = Join-Path $BASEDIR "envs" "SLCenv"

# --------------------------------------------------------------------------
# Section 1b: SLC Bootstrap
# --------------------------------------------------------------------------
if (-not (Test-Path $SLCENV_DIR)) {
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    Write-Host "  First-time setup: Installing SLC environment..."
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    Write-Host ""

    # Check for Python 3
    $pythonCmd = $null
    if (Get-Command python -ErrorAction SilentlyContinue) {
        # Verify it's Python 3
        $pyVersion = & python --version 2>&1
        if ($pyVersion -match "Python 3") {
            $pythonCmd = "python"
        }
    }
    if (-not $pythonCmd -and (Get-Command python3 -ErrorAction SilentlyContinue)) {
        $pythonCmd = "python3"
    }

    if (-not $pythonCmd) {
        Write-Host "❌ Error: Python 3 not found" -ForegroundColor Red
        Write-Host "💡 Install Python 3 first, then run: . .\activate.ps1" -ForegroundColor Yellow
        return
    }

    # Check for install_SLC.py
    $installScript = Join-Path $BASEDIR "install_SLC.py"
    if (-not (Test-Path $installScript)) {
        Write-Host "❌ Error: install_SLC.py not found at $BASEDIR" -ForegroundColor Red
        Write-Host "💡 This file is required for SLC bootstrap" -ForegroundColor Yellow
        return
    }

    # Run the installer
    & $pythonCmd $installScript
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "❌ Error: SLC installation failed" -ForegroundColor Red
        Write-Host "💡 Check network connection and try again:" -ForegroundColor Yellow
        Write-Host "   $pythonCmd $installScript"
        return
    }
    Write-Host ""
    Write-Host "✔ SLC environment installed successfully" -ForegroundColor Green
    Write-Host ""
}

# --------------------------------------------------------------------------
# Section 1c: Conda Activation
# --------------------------------------------------------------------------
# Source conda's PowerShell hook
$condaHook = Join-Path $SLCENV_DIR "shell" "condabin" "conda-hook.ps1"
if (-not (Test-Path $condaHook)) {
    # Fallback: try the profile.d location with Invoke-Expression on the shell init
    $condaExe = Join-Path $SLCENV_DIR "Scripts" "conda.exe"
    if (Test-Path $condaExe) {
        # Initialize conda for PowerShell
        $condaInit = & $condaExe shell.powershell hook 2>$null
        if ($condaInit) {
            Invoke-Expression $condaInit
        }
    } else {
        Write-Host "❌ Error: Conda not found in SLC environment" -ForegroundColor Red
        Write-Host "💡 Try reinstalling: Remove-Item -Recurse '$SLCENV_DIR'; . .\activate.ps1" -ForegroundColor Yellow
        return
    }
} else {
    . $condaHook
}

# Activate the base environment
conda activate $SLCENV_DIR

# --------------------------------------------------------------------------
# Section 2: Environment Setup
# --------------------------------------------------------------------------

# Export project root (generic name - not project-specific)
$env:PROJECT_ROOT = $BASEDIR

# SLC environment variables
$env:SLC_BASE = $BASEDIR
$env:SLC_PYTHON = (Get-Command python -ErrorAction SilentlyContinue).Source
$env:SLC_VERSION = "0.0.1"

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║ CUSTOMIZE: Add your project's Python modules here                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
# Add all repos/ subdirectories to PYTHONPATH (if repos/ exists)
$reposDir = Join-Path $BASEDIR "repos"
if (Test-Path $reposDir) {
    $repos = Get-ChildItem -Path $reposDir -Directory
    foreach ($repo in $repos) {
        if ($env:PYTHONPATH) {
            $env:PYTHONPATH = "$($repo.FullName);$env:PYTHONPATH"
        } else {
            $env:PYTHONPATH = $repo.FullName
        }
    }
}

# Make environments discoverable by conda
if ($env:CONDA_ENVS_PATH) {
    $env:CONDA_ENVS_PATH = "$(Join-Path $BASEDIR 'envs');$env:CONDA_ENVS_PATH"
} else {
    $env:CONDA_ENVS_PATH = Join-Path $BASEDIR "envs"
}

# Add commands/ to PATH
$commandsDir = Join-Path $BASEDIR "commands"
if (Test-Path $commandsDir) {
    if ($env:PATH -notlike "*$commandsDir*") {
        $env:PATH = "$commandsDir;$env:PATH"
    }
}

# Configure git hooks (if present)
$gitDir = Join-Path $BASEDIR ".git"
$gitHooksDir = Join-Path $BASEDIR ".githooks"
if ((Test-Path $gitDir) -and (Test-Path $gitHooksDir)) {
    & git -C $BASEDIR config core.hooksPath $gitHooksDir 2>$null
}

# --------------------------------------------------------------------------
# Section 3: Submodule Auto-Init
# --------------------------------------------------------------------------

# Track warnings to display at the end
$script:WARNINGS = @()

# Check if any submodules need initialization
$gitmodulesFile = Join-Path $BASEDIR ".gitmodules"
if (Test-Path $gitmodulesFile) {
    $needsInit = $false

    # Check for claudechic specifically (main submodule)
    $gitmodulesContent = Get-Content $gitmodulesFile -Raw
    if ($gitmodulesContent -match "claudechic") {
        $claudechicPyproject = Join-Path $BASEDIR "submodules" "claudechic" "pyproject.toml"
        if (-not (Test-Path $claudechicPyproject)) {
            $needsInit = $true
        }
    }

    # ╔═══════════════════════════════════════════════════════════════════════════╗
    # ║ CUSTOMIZE: Add checks for other submodules your project uses              ║
    # ╚═══════════════════════════════════════════════════════════════════════════╝

    # Auto-init submodules if needed
    if ($needsInit) {
        Write-Host ""
        Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        Write-Host "  Initializing git submodules..."
        Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        Write-Host ""

        & git -C $BASEDIR submodule update --init --recursive
        if ($LASTEXITCODE -ne 0) {
            $script:WARNINGS += "⚠️  Failed to initialize submodules"
            $script:WARNINGS += "   Try manually: cd $BASEDIR; git submodule update --init --recursive"
        } else {
            # Verify it worked
            $claudechicPyproject = Join-Path $BASEDIR "submodules" "claudechic" "pyproject.toml"
            if (Test-Path $claudechicPyproject) {
                Write-Host "✔ Submodules initialized successfully" -ForegroundColor Green
                Write-Host ""
            }
        }
    }
}

# --------------------------------------------------------------------------
# Section 4: Status Display
# --------------------------------------------------------------------------

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "  $PROJECT_NAME environment activated"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "  ✔ SLC is active" -ForegroundColor Green

# --- Show available conda environments ---
$installedEnvs = @()
$availableEnvs = @()

$envsDir = Join-Path $BASEDIR "envs"
$ymlFiles = Get-ChildItem -Path $envsDir -Filter "*.yml" -File -ErrorAction SilentlyContinue

foreach ($yml in $ymlFiles) {
    $envname = $yml.BaseName
    $envDir = Join-Path $envsDir $envname
    if (Test-Path $envDir) {
        $installedEnvs += $envname
    } else {
        $availableEnvs += $envname
    }
}

if ($installedEnvs.Count -gt 0) {
    Write-Host ""
    Write-Host "📦 Installed environments:"
    foreach ($env in $installedEnvs) {
        Write-Host "    ✔ $env" -ForegroundColor Green
    }
    Write-Host "  Activate with: conda activate <name>"
}

if ($availableEnvs.Count -gt 0) {
    Write-Host ""
    Write-Host "📋 Available to install:"
    foreach ($env in $availableEnvs) {
        Write-Host "    ○ $env"
    }
    Write-Host "  Install with: python $BASEDIR\install_env.py <name>"
}

# --- Show CLI commands ---
if (Test-Path $commandsDir) {
    $cliCommands = @()
    $scripts = Get-ChildItem -Path $commandsDir -File -ErrorAction SilentlyContinue

    foreach ($script in $scripts) {
        $basename = $script.Name
        # Skip .md files and dotfiles, include .ps1 files for PowerShell
        if ($basename -notlike "*.md" -and $basename -notlike ".*") {
            # On Windows, prefer .ps1 scripts; also show scripts without extension
            if ($basename -like "*.ps1" -or $basename -notlike "*.*") {
                $cliCommands += $basename
            }
        }
    }

    if ($cliCommands.Count -gt 0) {
        Write-Host ""
        Write-Host "🛠  CLI commands:"
        foreach ($cmd in $cliCommands) {
            Write-Host "    $cmd"
        }
    }
}

# --- Show Claude Code skills ---
$claudeCommandsDir = Join-Path $BASEDIR ".claude" "commands"
if (Test-Path $claudeCommandsDir) {
    $claudeSkills = @()
    $skillFiles = Get-ChildItem -Path $claudeCommandsDir -Filter "*.md" -File -ErrorAction SilentlyContinue

    foreach ($skillFile in $skillFiles) {
        $skillName = $skillFile.BaseName
        # Extract the first H1 heading (handles frontmatter)
        $content = Get-Content $skillFile.FullName -ErrorAction SilentlyContinue
        $skillTitle = ""
        foreach ($line in $content) {
            if ($line -match "^# (.+)") {
                $skillTitle = $Matches[1]
                break
            }
        }
        $claudeSkills += "/$skillName - $skillTitle"
    }

    if ($claudeSkills.Count -gt 0) {
        Write-Host ""
        Write-Host "🤖 Claude Code skills:"
        foreach ($skill in $claudeSkills) {
            Write-Host "    $skill"
        }
    }
}

# --- Show any warnings ---
if ($script:WARNINGS.Count -gt 0) {
    Write-Host ""
    foreach ($warning in $script:WARNINGS) {
        Write-Host $warning -ForegroundColor Yellow
    }
}

Write-Host ""
