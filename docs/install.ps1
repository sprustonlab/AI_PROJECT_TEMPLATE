$ErrorActionPreference = "Continue"

$TemplateUrl = "https://github.com/sprustonlab/AI_PROJECT_TEMPLATE"

Write-Host ""
Write-Host "==================================================="
Write-Host "  AI Project Template -- setup"
Write-Host "==================================================="
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
            return
        }
        Write-Host "Git installed successfully." -ForegroundColor Green
    } else {
        Write-Host "Error: git is required but not found, and winget is not available to install it." -ForegroundColor Red
        Write-Host "  Please install git manually: https://git-scm.com/downloads" -ForegroundColor Yellow
        return
    }
}

# 2. Verify GitHub access (claudechic is a private dependency)
$PrivateRepo = "https://github.com/sprustonlab/claudechic.git"
$lsRemote = git ls-remote $PrivateRepo HEAD 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Error: Cannot access sprustonlab/claudechic (private repository)." -ForegroundColor Red
    Write-Host ""
    Write-Host "This template requires access to a private GitHub repo."
    Write-Host "Please authenticate with GitHub first, then re-run this installer."
    Write-Host ""
    Write-Host "  Windows:" -ForegroundColor Cyan
    Write-Host "    winget install GitHub.cli    # install GitHub CLI"
    Write-Host "    gh auth login               # authenticate (opens browser)"
    Write-Host "    gh auth setup-git           # configure git credentials"
    Write-Host ""
    return
}

# 3. Ask where to create the project and what to name it
$DefaultDir = (Get-Location).Path
$InstallDir = Read-Host "Where should the project be created? [$DefaultDir]"
if (-not $InstallDir) { $InstallDir = $DefaultDir }

$ProjectName = Read-Host "Project name"
if (-not $ProjectName) {
    Write-Host "Error:" -ForegroundColor Red; Write-Host "Project name is required."
    return
}

$ProjectDir = Join-Path $InstallDir $ProjectName
if (Test-Path $ProjectDir) {
    Write-Host "Error:" -ForegroundColor Red; Write-Host "$ProjectDir already exists."
    return
}

# 4. Install pixi if not present
if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    Write-Host "Installing pixi..."
    iwr -useb https://pixi.sh/install.ps1 | iex
    $env:PATH = "$HOME\.pixi\bin;$env:PATH"
}

# 5. Ensure git is on PATH (winget install may not update current session)
$GitCmd = Get-Command git -ErrorAction SilentlyContinue
if ($GitCmd) {
    $GitDir = Split-Path (Split-Path $GitCmd.Source)
    $env:PATH = "$GitDir\cmd;$env:PATH"
}

# 6. Run copier (project_name is passed so copier won't re-ask)
Write-Host ""
Write-Host "Copier will now ask you a few questions to configure your project."
Write-Host ""
pixi exec --spec "copier>=9,<10" --spec git -- copier copy --trust -d "project_name=$ProjectName" $TemplateUrl $ProjectDir

# 7. Install environments
Write-Host ""
Write-Host "Installing environments..."
Push-Location $ProjectDir
pixi install
Pop-Location

# 8. Check Claude Code is installed and authenticated
$ClaudeCmd = Get-Command claude -ErrorAction SilentlyContinue
if (-not $ClaudeCmd) {
    Write-Host ""
    Write-Host "[OK] Project is ready!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Claude Code is not installed. To get started:"
    Write-Host ""
    Write-Host "  npm install -g @anthropic-ai/claude-code"
    Write-Host "  claude login"
    Write-Host "  cd $ProjectDir"
    Write-Host "  . .\activate.ps1"
    Write-Host "  pixi run claudechic"
    return
}

$ClaudeAuth = claude auth status 2>&1 | Out-String
if ($ClaudeAuth -match '"loggedIn":\s*false') {
    Write-Host ""
    Write-Host "[OK] Project is ready!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Claude Code is installed but not logged in. To get started:"
    Write-Host ""
    Write-Host "  claude login"
    Write-Host "  cd $ProjectDir"
    Write-Host "  . .\activate.ps1"
    Write-Host "  pixi run claudechic"
    return
}

Write-Host ""
Write-Host "[OK] Project is ready! Launching claudechic..." -ForegroundColor Green
Write-Host ""
Push-Location $ProjectDir
. .\activate.ps1
pixi run claudechic
Pop-Location
