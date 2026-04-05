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

# +=========================================================================+
# | CUSTOMIZE: Change this to your project name                             |
# +=========================================================================+
$PROJECT_NAME = "my-project"

# --------------------------------------------------------------------------
# Section 1: Path Resolution
# --------------------------------------------------------------------------
# $PSScriptRoot is the directory containing this script
$BASEDIR = $PSScriptRoot
$PLATFORM_SUBDIR = "win-64"
$env:SLC_PLATFORM = $PLATFORM_SUBDIR
$SLCENV_DIR = Join-Path (Join-Path (Join-Path $BASEDIR "envs") $PLATFORM_SUBDIR) "SLCenv"

# --------------------------------------------------------------------------
# Section 1b: Flat-Layout Migration Warning
# --------------------------------------------------------------------------
$oldSlcEnvDir = Join-Path (Join-Path $BASEDIR "envs") "SLCenv"
if ((Test-Path $oldSlcEnvDir) -and -not (Test-Path $SLCENV_DIR)) {
    Write-Host ""
    Write-Host "WARNING: Flat layout detected at envs\SLCenv\" -ForegroundColor Yellow
    Write-Host "   The platform layout uses envs\$PLATFORM_SUBDIR\SLCenv\" -ForegroundColor Yellow
    Write-Host "   Please delete the old flat-layout directories:" -ForegroundColor Yellow
    Write-Host "     Remove-Item -Recurse -Force `"$oldSlcEnvDir`"" -ForegroundColor Yellow
    Write-Host "   Then re-run: . .\activate.ps1" -ForegroundColor Yellow
    Write-Host ""
}

# --------------------------------------------------------------------------
# Section 1c: SLC Bootstrap
# --------------------------------------------------------------------------
if (-not (Test-Path $SLCENV_DIR)) {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "  First-time setup: Installing SLC environment..."
    Write-Host "============================================================"
    Write-Host ""

    # Use native PowerShell installer (no Python dependency)
    $installScript = Join-Path $BASEDIR "install_SLC.ps1"
    if (-not (Test-Path $installScript)) {
        Write-Host "Error: install_SLC.ps1 not found at $BASEDIR" -ForegroundColor Red
        Write-Host "This file is required for SLC bootstrap" -ForegroundColor Yellow
        return
    }

    # Run the PowerShell installer
    & $installScript
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Error: SLC installation failed" -ForegroundColor Red
        Write-Host "Check network connection and try again:" -ForegroundColor Yellow
        Write-Host "   . $installScript"
        return
    }
    Write-Host ""
    Write-Host "SLC environment installed successfully" -ForegroundColor Green
    Write-Host ""
}

# --------------------------------------------------------------------------
# Section 1d: Conda Activation
# --------------------------------------------------------------------------
# Source conda PowerShell hook
$condaHook = Join-Path (Join-Path (Join-Path $SLCENV_DIR "shell") "condabin") "conda-hook.ps1"
if (-not (Test-Path $condaHook)) {
    # Fallback: try conda.exe shell init
    $condaExe = Join-Path (Join-Path $SLCENV_DIR "Scripts") "conda.exe"
    if (Test-Path $condaExe) {
        # Initialize conda for PowerShell
        $condaInit = & $condaExe shell.powershell hook 2>$null
        if ($condaInit) {
            Invoke-Expression $condaInit
        }
    } else {
        Write-Host "Error: Conda not found in SLCenv" -ForegroundColor Red
        Write-Host "Try reinstalling: Remove-Item -Recurse '$SLCENV_DIR'; . .\activate.ps1" -ForegroundColor Yellow
        return
    }
} else {
    . $condaHook
}

# Activate SLCenv (the base conda environment)
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

# +=========================================================================+
# | CUSTOMIZE: Add your project's Python modules here                       |
# +=========================================================================+
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

# Make environments discoverable by conda (platform layout)
$platformEnvsPath = Join-Path (Join-Path $BASEDIR "envs") $PLATFORM_SUBDIR
if ($env:CONDA_ENVS_PATH) {
    $env:CONDA_ENVS_PATH = "$platformEnvsPath;$env:CONDA_ENVS_PATH"
} else {
    $env:CONDA_ENVS_PATH = $platformEnvsPath
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
        $claudechicPyproject = Join-Path (Join-Path (Join-Path $BASEDIR "submodules") "claudechic") "pyproject.toml"
        if (-not (Test-Path $claudechicPyproject)) {
            $needsInit = $true
        }
    }

    # +=========================================================================+
    # | CUSTOMIZE: Add checks for other submodules your project uses            |
    # +=========================================================================+

    # Auto-init submodules if needed
    if ($needsInit) {
        Write-Host ""
        Write-Host "============================================================"
        Write-Host "  Initializing git submodules..."
        Write-Host "============================================================"
        Write-Host ""

        & git -C $BASEDIR submodule update --init --recursive
        if ($LASTEXITCODE -ne 0) {
            $script:WARNINGS += "WARNING: Failed to initialize submodules"
            $script:WARNINGS += "   Try manually: cd $BASEDIR; git submodule update --init --recursive"
        } else {
            # Verify it worked
            $claudechicPyproject = Join-Path (Join-Path (Join-Path $BASEDIR "submodules") "claudechic") "pyproject.toml"
            if (Test-Path $claudechicPyproject) {
                Write-Host "Submodules initialized successfully" -ForegroundColor Green
                Write-Host ""
            }
        }
    }
}

# --------------------------------------------------------------------------
# Section 4: Status Display
# --------------------------------------------------------------------------

Write-Host ""
Write-Host "============================================================"
Write-Host "  $PROJECT_NAME environment activated"
Write-Host "============================================================"
Write-Host "  SLC is active" -ForegroundColor Green

# --- Show installed and available project environments ---
$installedEnvs = @()
$availableEnvs = @()

$envsDir = Join-Path $BASEDIR "envs"
$ymlFiles = Get-ChildItem -Path $envsDir -Filter "*.yml" -File -ErrorAction SilentlyContinue

foreach ($yml in $ymlFiles) {
    $envname = $yml.BaseName
    $envDir = Join-Path (Join-Path $envsDir $PLATFORM_SUBDIR) $envname
    if (Test-Path $envDir) {
        $installedEnvs += $envname
    } else {
        $availableEnvs += $envname
    }
}

if ($installedEnvs.Count -gt 0) {
    Write-Host ""
    Write-Host "Installed environments:"
    foreach ($env in $installedEnvs) {
        Write-Host "    * $env" -ForegroundColor Green
    }
    Write-Host "  Activate with: conda activate <name>"
}

if ($availableEnvs.Count -gt 0) {
    Write-Host ""
    Write-Host "Available to install:"
    foreach ($env in $availableEnvs) {
        Write-Host "    o $env"
    }
    Write-Host ("  Install with: python " + $BASEDIR + "\install_env.py <name>")
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
        Write-Host "CLI commands:"
        foreach ($cmd in $cliCommands) {
            Write-Host "    $cmd"
        }
    }
}

# --- Show Claude Code skills ---
$claudeCommandsDir = Join-Path (Join-Path $BASEDIR ".claude") "commands"
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
        Write-Host "Claude Code skills:"
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
