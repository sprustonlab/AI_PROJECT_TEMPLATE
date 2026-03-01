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
$pythonCheck = python -c "import claudechic" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing claudechic in editable mode..."
    pip install -e $CLAUDECHIC_DIR --quiet
    if ($LASTEXITCODE -ne 0) {
        exit 1
    }
}

python -m claudechic @args
