# jupyter.ps1 - Launch Jupyter Lab locally

$ErrorActionPreference = "Stop"

# Ensure jupyter environment is installed and activated
. "$PSScriptRoot\require_env.ps1" jupyter
if ($LASTEXITCODE -ne 0) {
    exit 1
}

# Launch Jupyter Lab
Write-Host "🚀 Starting Jupyter Lab..." -ForegroundColor Cyan
Write-Host "   Press Ctrl+C to stop the server"
Write-Host ""

jupyter lab @args
