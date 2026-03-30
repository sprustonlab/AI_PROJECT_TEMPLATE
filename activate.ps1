# =============================================================================
# PROJECT ACTIVATE SCRIPT (pixi) — PowerShell
# =============================================================================
# Dot-source this file to activate the project environment:
#   . .\activate.ps1
#
# Same seam registry as activate (bash) — discovers all five seams.
# =============================================================================

$ErrorActionPreference = "Stop"
$ProjectName = "my-project"

# ─── Section 1: Path Resolution ──────────────────────────────────────────────
$BASEDIR = Split-Path -Parent $MyInvocation.MyCommand.Path

# ─── Section 2: Pixi Bootstrap ───────────────────────────────────────────────
if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    Write-Host "  First-time setup: Installing pixi..."
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    Write-Host ""
    try {
        iwr -useb https://pixi.sh/install.ps1 | iex
    } catch {
        Write-Host "❌ Error: pixi installation failed"
        Write-Host "💡 Install manually: https://pixi.sh"
        return
    }
    $env:PATH = "$HOME\.pixi\bin;$env:PATH"
    Write-Host "✔ pixi installed successfully"
    Write-Host ""
}

# ─── Section 3: Environment Install ──────────────────────────────────────────
if ((Test-Path "$BASEDIR\pixi.toml") -and -not (Test-Path "$BASEDIR\.pixi\envs")) {
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    Write-Host "  Installing environments from pixi.toml..."
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    Write-Host ""
    Push-Location $BASEDIR
    try { pixi install } catch {
        Write-Host "❌ Error: pixi install failed"
        Pop-Location
        return
    }
    Pop-Location
    Write-Host "✔ Environments installed"
    Write-Host ""
}

# ─── Section 4: Environment Setup ────────────────────────────────────────────
$env:PROJECT_ROOT = $BASEDIR

# Activate default pixi environment via shell-hook
Push-Location $BASEDIR
$hookOutput = pixi shell-hook -s powershell 2>$null
if ($hookOutput) {
    $hookOutput | Invoke-Expression
}
Pop-Location

# Add repos/ subdirectories to PYTHONPATH
if (Test-Path "$BASEDIR\repos") {
    Get-ChildItem "$BASEDIR\repos" -Directory | ForEach-Object {
        $env:PYTHONPATH = "$($_.FullName);$env:PYTHONPATH"
    }
}

# Add commands/ to PATH
if (Test-Path "$BASEDIR\commands") {
    $env:PATH = "$BASEDIR\commands;$env:PATH"
}

# Configure git hooks (if present)
if ((Test-Path "$BASEDIR\.git") -and (Test-Path "$BASEDIR\.githooks")) {
    git -C $BASEDIR config core.hooksPath "$BASEDIR\.githooks"
}

# ─── Section 5: Submodule Auto-Init ──────────────────────────────────────────
$Warnings = @()

if (Test-Path "$BASEDIR\.gitmodules") {
    if ((Get-Content "$BASEDIR\.gitmodules" -Raw) -match "claudechic") {
        if (-not (Test-Path "$BASEDIR\submodules\claudechic\pyproject.toml")) {
            Write-Host ""
            Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            Write-Host "  Initializing git submodules..."
            Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            Write-Host ""
            try {
                git -C $BASEDIR submodule update --init --recursive
                Write-Host "✔ Submodules initialized successfully"
            } catch {
                $Warnings += "⚠️  Failed to initialize submodules"
            }
        }
    }
}

# ─── Section 6: Status Display ───────────────────────────────────────────────
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "  $ProjectName environment activated"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

$pixiVersion = try { pixi --version 2>$null } catch { "(version unknown)" }
Write-Host "  ✔ pixi $pixiVersion"

# Show pixi environments
if (Test-Path "$BASEDIR\pixi.toml") {
    $features = Select-String -Path "$BASEDIR\pixi.toml" -Pattern '^\[feature\.([^\]]+)\]' |
        ForEach-Object { $_.Matches.Groups[1].Value } | Sort-Object -Unique
    $installed = @()
    $available = @()
    foreach ($f in $features) {
        if (Test-Path "$BASEDIR\.pixi\envs\$f") { $installed += $f }
        else { $available += $f }
    }
    if ($installed.Count -gt 0) {
        Write-Host ""
        Write-Host "📦 Installed environments:"
        $installed | ForEach-Object { Write-Host "    ✔ $_" }
        Write-Host "  Use with: pixi run -e <name> <command>"
    }
    if ($available.Count -gt 0) {
        Write-Host ""
        Write-Host "📋 Available to install:"
        $available | ForEach-Object { Write-Host "    ○ $_" }
        Write-Host "  Install with: pixi install"
    }
}

# Show CLI commands
if (Test-Path "$BASEDIR\commands") {
    $cmds = Get-ChildItem "$BASEDIR\commands" -File |
        Where-Object { $_.Extension -ne ".md" -and $_.Name -notlike ".*" } |
        Select-Object -ExpandProperty Name
    if ($cmds.Count -gt 0) {
        Write-Host ""
        Write-Host "🛠  CLI commands:"
        $cmds | ForEach-Object { Write-Host "    $_" }
    }
}

# Show Claude Code skills
if (Test-Path "$BASEDIR\.claude\commands") {
    $skills = Get-ChildItem "$BASEDIR\.claude\commands\*.md" -ErrorAction SilentlyContinue
    if ($skills.Count -gt 0) {
        Write-Host ""
        Write-Host "🤖 Claude Code skills:"
        foreach ($s in $skills) {
            $name = $s.BaseName
            $title = (Select-String -Path $s.FullName -Pattern '^# (.+)' |
                Select-Object -First 1).Matches.Groups[1].Value
            Write-Host "    /$name - $title"
        }
    }
}

# Show guardrails status
if (Test-Path "$BASEDIR\.claude\guardrails\rules.yaml") {
    $ruleCount = (Select-String -Path "$BASEDIR\.claude\guardrails\rules.yaml" -Pattern '^- id:').Count
    Write-Host ""
    Write-Host "🛡  Guardrails: $ruleCount core rules"
    if (Test-Path "$BASEDIR\.claude\guardrails\rules.d") {
        $rdCount = (Get-ChildItem "$BASEDIR\.claude\guardrails\rules.d\*.yaml" -ErrorAction SilentlyContinue).Count
        if ($rdCount -gt 0) { Write-Host "    + $rdCount contributed rule sets in rules.d/" }
    }
}

# Show warnings
foreach ($w in $Warnings) { Write-Host $w }
Write-Host ""
