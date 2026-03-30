$ErrorActionPreference = "Stop"

$ProjectName = Read-Host "Enter project name"
if (-not $ProjectName) { Write-Error "Project name required"; exit 1 }
$InstallDir = Read-Host "Install location (default: current directory)"
if (-not $InstallDir) { $InstallDir = "." }
$TemplateUrl = "https://github.com/sprustonlab/AI_PROJECT_TEMPLATE"

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "  AI_PROJECT_TEMPLATE — project setup"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Install pixi if not present
if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    Write-Host "Installing pixi..."
    iwr -useb https://pixi.sh/install.ps1 | iex
    $env:PATH = "$HOME\.pixi\bin;$env:PATH"
}

# 2. Run copier in ephemeral pixi env (pinned version)
Write-Host "Creating project '$ProjectName'..."
pixi exec --spec "copier>=9,<10" -- copier copy $TemplateUrl "$InstallDir\$ProjectName"

# 3. Install environments
Write-Host "Installing environments..."
Push-Location "$InstallDir\$ProjectName"
pixi install
Pop-Location

Write-Host ""
Write-Host "✔ Project '$ProjectName' is ready!"
Write-Host "  cd $ProjectName; . .\activate.ps1"
