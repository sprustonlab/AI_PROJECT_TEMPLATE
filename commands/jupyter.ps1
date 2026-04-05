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

# Use the conda env's jupyter directly to avoid recursing into this script
# (commands/ is on PATH, so bare "jupyter" resolves back here).
$jupyterExe = (Get-Command jupyter -CommandType Application -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -notlike "*\commands\*" } |
    Select-Object -First 1).Source

if (-not $jupyterExe) {
    Write-Host "❌ Error: jupyter executable not found in conda environment" -ForegroundColor Red
    exit 1
}

& $jupyterExe lab @args
