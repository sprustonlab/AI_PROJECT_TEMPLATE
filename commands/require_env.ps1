# require_env.ps1 - Auto-install SLC base environment and specific environments
#
# Usage:
#   . .\require_env.ps1                    # Ensure SLC base is installed
#   . .\require_env.ps1 <env_name>         # Ensure SLC + environment are installed
#   . .\require_env.ps1 -CheckOnly         # Check SLC without installing
#   . .\require_env.ps1 -CheckOnly <env>   # Check SLC + environment without installing
#
# Exit codes:
#   0 - Success (everything installed or already exists)
#   1 - Error (installation failed or missing components in check-only mode)

param(
    [switch]$CheckOnly,
    [Parameter(Position = 0)]
    [string]$EnvName
)

$ErrorActionPreference = "Stop"

# Find repo root (commands/ is at root level)
$script:REPO_ROOT = (Resolve-Path "$PSScriptRoot\..").Path
$script:SLC_DIR = $REPO_ROOT

# Export for sourcing scripts
$env:REPO_ROOT = $REPO_ROOT

# Color output helpers
function Write-Red { param([string]$Message) Write-Host $Message -ForegroundColor Red }
function Write-Green { param([string]$Message) Write-Host $Message -ForegroundColor Green }
function Write-Yellow { param([string]$Message) Write-Host $Message -ForegroundColor Yellow }
function Write-Blue { param([string]$Message) Write-Host $Message -ForegroundColor Blue }

# Check if project activate has been sourced
if (-not $env:PROJECT_ROOT) {
    Write-Red "❌ Error: Project not activated"
    Write-Yellow "💡 Run: . $REPO_ROOT\activate.ps1"
    exit 1
}

# Check if it's the correct project (this repo, not another clone)
if ($env:PROJECT_ROOT -ne $REPO_ROOT) {
    Write-Red "❌ Error: Wrong project activated"
    Write-Yellow "   Expected: $REPO_ROOT"
    Write-Yellow "   Found: $env:PROJECT_ROOT"
    Write-Yellow "💡 Run: . $REPO_ROOT\activate.ps1"
    exit 1
}

# Check if SLC is activated (should be automatic via activate script)
if (-not $env:SLC_BASE) {
    Write-Red "❌ Error: SLC not activated"
    Write-Yellow "💡 This shouldn't happen if activate was sourced correctly"
    Write-Yellow "💡 Try: . $REPO_ROOT\activate.ps1"
    exit 1
}

# Check if correct SLC (from this repo, not another clone)
if ($env:SLC_BASE -ne $SLC_DIR) {
    Write-Red "❌ Error: Wrong SLC activated"
    Write-Yellow "   Expected: $SLC_DIR"
    Write-Yellow "   Found: $env:SLC_BASE"
    Write-Yellow "💡 Run: . $REPO_ROOT\activate.ps1"
    exit 1
}

# Initialize conda/mamba for PowerShell
$condaHook = "$SLC_DIR\envs\SLCenv\shell\condabin\conda-hook.ps1"
if (Test-Path $condaHook) {
    . $condaHook
}

#
# Function: Test-SlcInstalled
# Returns: $true if installed, $false if not
#
function Test-SlcInstalled {
    $condaExe = "$SLC_DIR\envs\SLCenv\Scripts\conda.exe"
    return (Test-Path $condaExe)
}

#
# Function: Install-Slc
# Installs the SLC base environment using install_SLC.py
#
function Install-Slc {
    Write-Blue "🔧 Installing SLC base environment..."

    # Check if install_SLC.py exists
    $installScript = "$SLC_DIR\install_SLC.py"
    if (-not (Test-Path $installScript)) {
        Write-Red "❌ Error: $installScript not found"
        return $false
    }

    # Run the installer using system Python3
    try {
        python3 $installScript
        if ($LASTEXITCODE -ne 0) {
            Write-Red "❌ Error: SLC installation failed"
            return $false
        }
    }
    catch {
        Write-Red "❌ Error: SLC installation failed - $_"
        return $false
    }

    Write-Green "✔ SLC base environment installed successfully"
    return $true
}

#
# Function: Test-EnvInstalled
# Returns: $true if installed, $false if not
#
function Test-EnvInstalled {
    param([string]$Name)
    return (Test-Path "$SLC_DIR\envs\$Name")
}

#
# Function: Show-AvailableEnvs
# Lists all available environment YAML files
#
function Show-AvailableEnvs {
    Write-Blue "💡 Available environments:"
    Get-ChildItem "$SLC_DIR\envs\*.yml" | ForEach-Object {
        $name = $_.BaseName
        # Skip SLCenv if it exists (it's the base, not an installable env)
        if ($name -ne "SLCenv") {
            Write-Host "    - $name"
        }
    }
}

#
# Function: Install-Env
# Installs a specific SLC environment
#
function Install-Env {
    param([string]$Name)

    Write-Blue "🔧 Installing environment: $Name"

    # Check if YAML exists
    $envYml = "$SLC_DIR\envs\$Name.yml"
    if (-not (Test-Path $envYml)) {
        Write-Red "❌ Error: Environment definition not found: $envYml"
        Show-AvailableEnvs
        return $false
    }

    # Check if already installed
    if (Test-EnvInstalled -Name $Name) {
        Write-Green "✔ Environment '$Name' is already installed"
        return $true
    }

    # Set up environment variables required by install_env.py
    $env:SLC_BASE = $SLC_DIR
    $env:SLC_PYTHON = "$SLC_DIR\envs\SLCenv\Scripts\python.exe"
    $env:PYTHONPATH = "$SLC_DIR\modules;$env:PYTHONPATH"
    $env:CONDA_ENVS_PATH = "$SLC_DIR\envs;$env:CONDA_ENVS_PATH"
    $env:PATH = "$SLC_DIR\envs\SLCenv\Scripts;$env:PATH"

    # Initialize conda for PowerShell
    $condaHook = "$SLC_DIR\envs\SLCenv\shell\condabin\conda-hook.ps1"
    if (Test-Path $condaHook) {
        . $condaHook
    }
    else {
        Write-Red "❌ Error: conda-hook.ps1 not found in SLCenv"
        return $false
    }

    # Activate SLCenv
    try {
        conda activate "$SLC_DIR\envs\SLCenv"
    }
    catch {
        Write-Red "❌ Error: Failed to activate SLCenv - $_"
        return $false
    }

    # Run install_env.py
    try {
        & $env:SLC_PYTHON "$SLC_DIR\install_env.py" $Name
        if ($LASTEXITCODE -ne 0) {
            Write-Red "❌ Error: Environment installation failed"
            conda deactivate
            return $false
        }
    }
    catch {
        Write-Red "❌ Error: Environment installation failed - $_"
        conda deactivate
        return $false
    }

    # Deactivate
    conda deactivate

    Write-Green "✔ Environment '$Name' installed successfully"
    return $true
}

#
# Main logic
#

# Check/install SLC base
if (Test-SlcInstalled) {
    if (-not $EnvName) {
        Write-Green "✔ SLC base environment is installed"
    }
}
else {
    if ($CheckOnly) {
        Write-Red "❌ SLC base environment is not installed"
        Write-Yellow "💡 Run: . $REPO_ROOT\commands\require_env.ps1"
        Write-Yellow "   Or: python3 $SLC_DIR\install_SLC.py"
        exit 1
    }
    else {
        if (-not (Install-Slc)) {
            exit 1
        }
    }
}

# Check/install specific environment if requested
if ($EnvName) {
    if (Test-EnvInstalled -Name $EnvName) {
        Write-Green "✔ Environment '$EnvName' is installed"
    }
    else {
        if ($CheckOnly) {
            Write-Red "❌ Environment '$EnvName' is not installed"
            Write-Yellow "💡 Run: . $REPO_ROOT\commands\require_env.ps1 $EnvName"
            Write-Yellow "   Or: python $SLC_DIR\install_env.py $EnvName"
            Show-AvailableEnvs
            exit 1
        }
        else {
            # Make sure SLC is installed first (should already be checked above)
            if (-not (Test-SlcInstalled)) {
                Write-Red "❌ Error: SLC base must be installed before installing environments"
                exit 1
            }

            if (-not (Install-Env -Name $EnvName)) {
                exit 1
            }
        }
    }

    # Activate environment
    $condaHook = "$SLC_DIR\envs\SLCenv\shell\condabin\conda-hook.ps1"
    if (Test-Path $condaHook) {
        . $condaHook
    }
    conda activate "$SLC_DIR\envs\$EnvName"
    if ($LASTEXITCODE -ne 0) {
        Write-Red "❌ Error: Failed to activate environment '$EnvName'"
        exit 1
    }
}

exit 0
