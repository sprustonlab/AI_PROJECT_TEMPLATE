# =============================================================================
# install_SLC.ps1 — Pure PowerShell bootstrap installer for SLCenv (Windows)
# =============================================================================
# Downloads and installs Miniforge as SLCenv, then installs PyYAML.
# No Python dependency — this script is called by activate.ps1 before
# Python is available.
#
# Usage: .\install_SLC.ps1
#
# Installs to: envs\win-64\SLCenv\
# Cache dir:   envs\win-64\SLCenv_offline_install\
# =============================================================================

$ErrorActionPreference = "Stop"

# --- Configuration ---
$ENV_NAME = "SLCenv"
$MINIFORGE_VERSION = "24.11.3-0"
$PLATFORM_SUBDIR = "win-64"

# --- Path setup (PS 5.1 compat: nested Join-Path with max 2 args) ---
$SCRIPT_DIR = $PSScriptRoot
$ENVS_DIR = Join-Path $SCRIPT_DIR "envs"
$PLATFORM_DIR = Join-Path $ENVS_DIR $PLATFORM_SUBDIR

$DOWNLOAD_DIR = Join-Path $PLATFORM_DIR "${ENV_NAME}_offline_install"
$INSTALLER_PATH = Join-Path $DOWNLOAD_DIR "Miniforge3.exe"
$INSTALL_DIR = Join-Path $PLATFORM_DIR $ENV_NAME  # envs\win-64\SLCenv

$CONDA_BIN = Join-Path (Join-Path $INSTALL_DIR "Scripts") "conda.exe"
$PIP_BIN = Join-Path (Join-Path $INSTALL_DIR "Scripts") "pip.exe"

$PIP_CACHE_DIR = Join-Path $DOWNLOAD_DIR "pip"
$CONDA_CACHE_DIR = Join-Path $DOWNLOAD_DIR "conda"

$MINIFORGE_URL = "https://github.com/conda-forge/miniforge/releases/download/$MINIFORGE_VERSION/Miniforge3-Windows-x86_64.exe"

# --- Helper: CleanEnv wrapper ---
# Temporarily set USERPROFILE to a temp dir and remove PYTHONPATH to prevent
# modification of global user settings during install.
function Invoke-CleanEnv {
    param([scriptblock]$ScriptBlock)

    $tempHome = Join-Path $ENVS_DIR "temp_home"
    $savedUserProfile = $env:USERPROFILE
    $savedPythonPath = $env:PYTHONPATH

    try {
        if (-not (Test-Path $tempHome)) {
            New-Item -ItemType Directory -Path $tempHome -Force | Out-Null
        }
        $env:USERPROFILE = $tempHome
        $env:PYTHONPATH = $null

        & $ScriptBlock
    }
    finally {
        $env:USERPROFILE = $savedUserProfile
        $env:PYTHONPATH = $savedPythonPath
        if (Test-Path $tempHome) {
            Remove-Item -Recurse -Force $tempHome -ErrorAction SilentlyContinue
        }
    }
}

# --- Download Miniforge ---
function Download-Miniforge {
    if (Test-Path $INSTALLER_PATH) {
        Write-Host "[OK] Miniforge installer already cached."
        return
    }

    # Ensure download directory exists
    if (-not (Test-Path $DOWNLOAD_DIR)) {
        New-Item -ItemType Directory -Path $DOWNLOAD_DIR -Force | Out-Null
    }

    Write-Host "[DL] Downloading Miniforge $MINIFORGE_VERSION..."
    try {
        # Use TLS 1.2 for GitHub downloads
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

        # Prefer Invoke-WebRequest but handle PS 5.1 progress bar performance
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $MINIFORGE_URL -OutFile $INSTALLER_PATH -UseBasicParsing
        $ProgressPreference = 'Continue'
    }
    catch {
        Write-Host "[ERR] Download failed: $_" -ForegroundColor Red
        if (Test-Path $INSTALLER_PATH) {
            Remove-Item $INSTALLER_PATH -Force
        }
        throw
    }
    Write-Host "[OK] Download complete."
}

# --- Install Miniforge ---
function Install-Miniforge {
    if (Test-Path $CONDA_BIN) {
        Write-Host "[OK] SLCenv already installed."
    }
    else {
        Write-Host "[..] Installing Miniforge as SLCenv (silent install)..."

        # Ensure platform directory exists
        if (-not (Test-Path $PLATFORM_DIR)) {
            New-Item -ItemType Directory -Path $PLATFORM_DIR -Force | Out-Null
        }

        # Windows .exe installer flags:
        # /InstallationType=JustMe - Install for current user only
        # /AddToPath=0 - Don't modify PATH
        # /RegisterPython=0 - Don't register as system Python
        # /S - Silent install
        # /D= - Installation directory (must be last argument)
        $installerArgs = @(
            "/InstallationType=JustMe",
            "/AddToPath=0",
            "/RegisterPython=0",
            "/S",
            "/D=$INSTALL_DIR"
        )

        $process = Start-Process -FilePath $INSTALLER_PATH -ArgumentList $installerArgs -Wait -PassThru -NoNewWindow
        if ($process.ExitCode -ne 0) {
            throw "Miniforge installer exited with code $($process.ExitCode)"
        }
        Write-Host "[OK] Miniforge installed as SLCenv."
    }

    # --- Install PyYAML ---
    # Ensure pip cache directory exists
    if (-not (Test-Path $PIP_CACHE_DIR)) {
        New-Item -ItemType Directory -Path $PIP_CACHE_DIR -Force | Out-Null
    }

    # Check if PyYAML is already cached
    $cachedPyYAML = Get-ChildItem -Path $PIP_CACHE_DIR -Filter "*pyyaml*" -ErrorAction SilentlyContinue
    if ($cachedPyYAML) {
        Write-Host "[pkg] Installing PyYAML from cache..."
        & $PIP_BIN install --no-index --find-links $PIP_CACHE_DIR PyYAML
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install PyYAML from cache"
        }
    }
    else {
        Write-Host "[net] Downloading and caching PyYAML..."
        & $PIP_BIN download --no-deps -d $PIP_CACHE_DIR PyYAML
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to download PyYAML"
        }
        & $PIP_BIN install --no-index --find-links $PIP_CACHE_DIR PyYAML
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install PyYAML"
        }
    }
    Write-Host "[OK] PyYAML installed."
}

# --- Main ---
function Main {
    Write-Host "[?] Checking Miniforge setup..."

    Invoke-CleanEnv {
        Download-Miniforge
    }

    Invoke-CleanEnv {
        Install-Miniforge
    }
}

Main
