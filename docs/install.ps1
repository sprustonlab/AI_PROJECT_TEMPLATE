$ErrorActionPreference = "Stop"

$TemplateUrl = "https://github.com/sprustonlab/AI_PROJECT_TEMPLATE"

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "  AI Project Template — setup"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host ""

# 1. Check git is available (required for claudechic install)
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Git not found. Installing via winget..." -ForegroundColor Yellow
        winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
        # Refresh PATH so git is available in this session
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Write-Host "Error: git was installed but not found in PATH. Please restart PowerShell and try again." -ForegroundColor Red
            exit 1
        }
        Write-Host "Git installed successfully." -ForegroundColor Green
    } else {
        Write-Host "Error: git is required but not found, and winget is not available to install it." -ForegroundColor Red
        Write-Host "  Please install git manually: https://git-scm.com/downloads" -ForegroundColor Yellow
        exit 1
    }
}

# 2. Ask where to create the project
$DefaultDir = (Get-Location).Path
$InstallDir = Read-Host "Where should the project be created? [$DefaultDir]"
if (-not $InstallDir) { $InstallDir = $DefaultDir }

# 2. Install pixi if not present
if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    Write-Host "Installing pixi..."
    iwr -useb https://pixi.sh/install.ps1 | iex
    $env:PATH = "$HOME\.pixi\bin;$env:PATH"
}

# 3. Run copier (asks project name and all other questions)
Write-Host ""
Write-Host "Copier will now ask you a few questions to configure your project."
Write-Host ""
Push-Location $InstallDir
pixi exec --spec "copier>=9,<10" --spec git -- copier copy --trust $TemplateUrl .

# 4. Find the created project (most recent directory)
$ProjectDir = Get-ChildItem -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $ProjectDir) {
    Write-Error "No project directory created."
    exit 1
}

# 5. Install environments
Write-Host ""
Write-Host "Installing environments..."
Push-Location $ProjectDir.FullName
pixi install
Pop-Location
Pop-Location

Write-Host ""
Write-Host "✔ Project is ready! Launching claudechic..."
Write-Host ""
Push-Location $ProjectDir.FullName
. .\activate.ps1
pixi run claudechic
Pop-Location
