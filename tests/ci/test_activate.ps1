# =============================================================================
# test_activate.ps1 - E2E test for `. .\activate.ps1`
# =============================================================================
# Tests the complete activate script workflow as a user would experience it:
# 1. SLC bootstrap (Miniforge download, SLCenv directory creation)
# 2. Submodule initialization
# 3. SLCenv conda environment is activated (conda activate)
# 4. Platform layout paths are set correctly (envs\{platform_subdir}\SLCenv)
#
# Compatible with: PowerShell 5.1 (powershell) and PowerShell 7.x (pwsh)
#
# Usage:
#   . .\tests\ci\test_activate.ps1      (from repo root)
#
# Exit codes:
#   0 - All tests passed
#   1 - Test failed
# =============================================================================

$ErrorActionPreference = "Stop"

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------

# Resolve project root (two levels up from this script)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)

# Platform layout: Windows is always win-64
$PLATFORM_SUBDIR = "win-64"

# Track test results
$script:TestsPassed = 0
$script:TestsFailed = 0

# Color helpers (PS 5.1 compatible)
function Write-Red    { param([string]$Message) Write-Host $Message -ForegroundColor Red }
function Write-Green  { param([string]$Message) Write-Host $Message -ForegroundColor Green }
function Write-Blue   { param([string]$Message) Write-Host $Message -ForegroundColor Cyan }

function Pass {
    param([string]$Message)
    Write-Green "  PASS: $Message"
    $script:TestsPassed++
}

function Fail {
    param([string]$Message)
    Write-Red "  FAIL: $Message"
    $script:TestsFailed++
}

# --------------------------------------------------------------------------
# Banner
# --------------------------------------------------------------------------

Write-Host ""
Write-Blue "============================================================"
Write-Blue "  TEST: . .\activate.ps1"
Write-Blue "  PowerShell $($PSVersionTable.PSVersion)"
Write-Blue "============================================================"
Write-Host ""

# --------------------------------------------------------------------------
# Source the activate script
# --------------------------------------------------------------------------

Write-Blue "Running: . .\activate.ps1"
Write-Host ""

Set-Location $ProjectRoot

# Source the activate script, capturing any terminating errors
$activateError = $null
try {
    . .\activate.ps1
} catch {
    $activateError = $_
}

if ($activateError) {
    Fail "activate.ps1 threw an error: $activateError"
    Write-Host ""
    Write-Red "============================================================"
    Write-Red "  RESULT: FAILED (activate script error)"
    Write-Red "============================================================"
    exit 1
}

Write-Host ""

# --------------------------------------------------------------------------
# Test 1: PROJECT_ROOT is set
# --------------------------------------------------------------------------

Write-Blue "Checking: PROJECT_ROOT set..."

if ($env:PROJECT_ROOT) {
    Pass "PROJECT_ROOT is set: $env:PROJECT_ROOT"
} else {
    Fail "PROJECT_ROOT is not set"
}

# --------------------------------------------------------------------------
# Test 2: SLC_BASE is set
# --------------------------------------------------------------------------

Write-Blue "Checking: SLC_BASE set..."

if ($env:SLC_BASE) {
    Pass "SLC_BASE is set: $env:SLC_BASE"
} else {
    Fail "SLC_BASE is not set"
}

# --------------------------------------------------------------------------
# Test 3: SLC_PYTHON is set
# --------------------------------------------------------------------------

Write-Blue "Checking: SLC_PYTHON set..."

if ($env:SLC_PYTHON) {
    Pass "SLC_PYTHON is set: $env:SLC_PYTHON"
} else {
    Fail "SLC_PYTHON is not set"
}

# --------------------------------------------------------------------------
# Test 4: SLC_PLATFORM is set to platform_subdir value
# --------------------------------------------------------------------------

Write-Blue "Checking: SLC_PLATFORM set to platform_subdir..."

if ($env:SLC_PLATFORM -eq $PLATFORM_SUBDIR) {
    Pass "SLC_PLATFORM is set to '$($env:SLC_PLATFORM)'"
} elseif ($env:SLC_PLATFORM) {
    Fail "SLC_PLATFORM is set but unexpected value: '$($env:SLC_PLATFORM)' (expected '$PLATFORM_SUBDIR')"
} else {
    Fail "SLC_PLATFORM is not set (expected '$PLATFORM_SUBDIR')"
}

# --------------------------------------------------------------------------
# Test 5: SLCenv directory was created at platform layout path
# --------------------------------------------------------------------------

Write-Blue "Checking: SLCenv bootstrap completed (platform layout)..."

# Platform layout: envs\{platform_subdir}\SLCenv
# PS 5.1: nested Join-Path (2 args max)
$envsDir = Join-Path $ProjectRoot "envs"
$platformDir = Join-Path $envsDir $PLATFORM_SUBDIR
$slcenvDir = Join-Path $platformDir "SLCenv"

if (Test-Path $slcenvDir) {
    Pass "envs\$PLATFORM_SUBDIR\SLCenv directory exists"
} else {
    Fail "envs\$PLATFORM_SUBDIR\SLCenv directory does not exist"
}

# --------------------------------------------------------------------------
# Test 6: conda.exe exists at expected path within SLCenv
# --------------------------------------------------------------------------

Write-Blue "Checking: conda.exe exists..."

# Windows conda path: envs\{platform_subdir}\SLCenv\Scripts\conda.exe
$condaExe = Join-Path (Join-Path $slcenvDir "Scripts") "conda.exe"
if (Test-Path $condaExe) {
    Pass "conda.exe exists at $condaExe"
} else {
    Fail "conda.exe not found at $condaExe"
}

# --------------------------------------------------------------------------
# Test 7: commands\ directory is in PATH
# --------------------------------------------------------------------------

Write-Blue "Checking: commands\ in PATH..."

$commandsDir = Join-Path $ProjectRoot "commands"
if ($env:PATH -like "*$commandsDir*") {
    Pass "commands\ directory is in PATH"
} else {
    Fail "commands\ directory is not in PATH (looked for $commandsDir)"
}

# --------------------------------------------------------------------------
# Test 8: Submodules are checked out (not empty)
# --------------------------------------------------------------------------

Write-Blue "Checking: Submodules initialized..."

# PS 5.1: nested Join-Path (2 args max)
$claudechicPyproject = Join-Path (Join-Path (Join-Path $ProjectRoot "submodules") "claudechic") "pyproject.toml"
if (Test-Path $claudechicPyproject) {
    Pass "submodules\claudechic\ is not empty (pyproject.toml exists)"
} else {
    Fail "submodules\claudechic\ is empty or pyproject.toml missing"
}

# --------------------------------------------------------------------------
# Test 9: CONDA_PREFIX is set (SLCenv base environment activated)
# --------------------------------------------------------------------------

Write-Blue "Checking: SLCenv base environment activated..."

if ($env:CONDA_PREFIX) {
    Pass "CONDA_PREFIX is set: $env:CONDA_PREFIX"
} else {
    Fail "CONDA_PREFIX is not set"
}

# --------------------------------------------------------------------------
# Test 10: CONDA_ENVS_PATH points to platform layout directory
# --------------------------------------------------------------------------

Write-Blue "Checking: CONDA_ENVS_PATH uses platform layout..."

if ($env:CONDA_ENVS_PATH) {
    # CONDA_ENVS_PATH should contain envs\{platform_subdir}
    $expectedEnvsPath = $platformDir
    if ($env:CONDA_ENVS_PATH -like "*$expectedEnvsPath*") {
        Pass "CONDA_ENVS_PATH includes platform layout path: $env:CONDA_ENVS_PATH"
    } else {
        Fail "CONDA_ENVS_PATH does not include '$expectedEnvsPath': $env:CONDA_ENVS_PATH"
    }
} else {
    Fail "CONDA_ENVS_PATH is not set"
}

# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

Write-Host ""
Write-Blue "============================================================"
if ($script:TestsFailed -eq 0) {
    Write-Green "  RESULT: ALL $($script:TestsPassed) TESTS PASSED"
    Write-Blue "============================================================"
    Write-Host ""
    exit 0
} else {
    Write-Red "  RESULT: $($script:TestsFailed) FAILED, $($script:TestsPassed) PASSED"
    Write-Blue "============================================================"
    Write-Host ""
    exit 1
}
