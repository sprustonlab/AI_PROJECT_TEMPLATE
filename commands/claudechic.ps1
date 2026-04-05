# claudechic.ps1 - Launch claudechic

$ErrorActionPreference = "Stop"

# Get project root
if (-not $env:PROJECT_ROOT) {
    $env:PROJECT_ROOT = (Resolve-Path "$PSScriptRoot\..").Path
}

Set-Location $env:PROJECT_ROOT

# Check if claudechic submodule is initialized
$CLAUDECHIC_DIR = "$env:PROJECT_ROOT\submodules\claudechic"
if (-not (Test-Path "$CLAUDECHIC_DIR\pyproject.toml")) {
    Write-Host "⚠️  claudechic submodule not initialized" -ForegroundColor Yellow
    Write-Host "Initializing submodule..."
    git submodule update --init submodules/claudechic
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to initialize claudechic submodule" -ForegroundColor Red
        exit 1
    }
    Write-Host "✔ Submodule initialized" -ForegroundColor Green
}

# Ensure claudechic environment is installed and activated
. "$env:PROJECT_ROOT\commands\require_env.ps1" claudechic
if ($LASTEXITCODE -ne 0) {
    exit 1
}

# Install claudechic in editable mode if not already installed
$ErrorActionPreference = "Continue"
$pythonCheck = python -c "import claudechic" 2>&1
$importExitCode = $LASTEXITCODE
$ErrorActionPreference = "Stop"
if ($importExitCode -ne 0) {
    Write-Host "Installing claudechic in editable mode..."
    # claudechic uses setuptools-scm but is embedded in the parent repo (no git tags),
    # so we must fake the version
    $env:SETUPTOOLS_SCM_PRETEND_VERSION_FOR_CLAUDECHIC = "0.1.0"
    pip install -e $CLAUDECHIC_DIR --quiet
    if ($LASTEXITCODE -ne 0) {
        exit 1
    }
}

python -m claudechic @args
