# =============================================================================
# test_claudechic.ps1 - E2E test for `claudechic` command (PowerShell)
# =============================================================================
# Tests that the claudechic command can be launched and produces expected output:
# 1. Environment activation (prerequisite via the activate script)
# 2. claudechic command availability
# 3. claudechic conda environment installation (via claudechic command --help)
# 4. claudechic conda environment directory exists at platform layout path
#    (envs\{platform_subdir}\claudechic\)
# 5. claudechic Python package imports successfully
#
# Must work on BOTH PowerShell 5.1 (powershell) and PowerShell 7.x (pwsh).
# PS 5.1 constraints:
#   - No Join-Path with 3+ arguments
#   - Watch encoding (PYTHONIOENCODING=utf-8 recommended)
#   - No <> in double-quoted strings
#
# Exit codes:
#   0 - All tests passed
#   1 - One or more tests failed
# =============================================================================

$ErrorActionPreference = "Continue"

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------

$SCRIPT_DIR = $PSScriptRoot
# PS 5.1 safe: two nested Join-Path calls instead of three args
$PROJECT_ROOT = (Resolve-Path (Join-Path $SCRIPT_DIR (Join-Path ".." ".."))).Path

# Platform layout: Windows is always win-64
$PLATFORM_SUBDIR = "win-64"

# Counters
$script:TESTS_PASSED = 0
$script:TESTS_FAILED = 0

# Color output helpers
function Write-Banner {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Blue
}

function Write-TestPass {
    param([string]$Message)
    Write-Host "  PASS: $Message" -ForegroundColor Green
    $script:TESTS_PASSED++
}

function Write-TestFail {
    param([string]$Message)
    Write-Host "  FAIL: $Message" -ForegroundColor Red
    $script:TESTS_FAILED++
}

function Write-Note {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor Yellow
}

function Write-Detail {
    param([string]$Message)
    Write-Host "    $Message"
}

# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------

Write-Host ""
Write-Banner "================================================================"
Write-Banner "  TEST: claudechic (PowerShell)"
Write-Banner "================================================================"
Write-Host ""

$psVersionLabel = "PS $($PSVersionTable.PSVersion)"
Write-Detail "PowerShell version: $psVersionLabel"
Write-Host ""

# --------------------------------------------------------------------------
# Prerequisite: Activate environment
# --------------------------------------------------------------------------

Write-Banner "Step 1: Activating project environment..."

Set-Location $PROJECT_ROOT

$activateScript = Join-Path $PROJECT_ROOT "activate.ps1"
if (-not (Test-Path $activateScript)) {
    Write-TestFail "activate.ps1 not found at $PROJECT_ROOT (prerequisite)"
    Write-Host ""
    Write-Banner "================================================================"
    Write-Host "  RESULT: Cannot continue without activate.ps1" -ForegroundColor Red
    Write-Banner "================================================================"
    Write-Host ""
    exit 1
}

$activateError = $null
try {
    . $activateScript
}
catch {
    $activateError = $_
}

if ($activateError) {
    Write-TestFail "activate script failed (prerequisite): $activateError"
    exit 1
}

if (-not $env:PROJECT_ROOT) {
    Write-TestFail "activate did not set PROJECT_ROOT (prerequisite)"
    exit 1
}

Write-TestPass "Project environment activated"

# --------------------------------------------------------------------------
# Test: SLC_PLATFORM is set to expected platform_subdir value
# --------------------------------------------------------------------------

Write-Banner "Checking: SLC_PLATFORM set to platform_subdir..."

if ($env:SLC_PLATFORM -eq $PLATFORM_SUBDIR) {
    Write-TestPass "SLC_PLATFORM is set to '$($env:SLC_PLATFORM)'"
} elseif ($env:SLC_PLATFORM) {
    Write-TestFail "SLC_PLATFORM has unexpected value: '$($env:SLC_PLATFORM)' (expected '$PLATFORM_SUBDIR')"
} else {
    Write-TestFail "SLC_PLATFORM is not set (expected '$PLATFORM_SUBDIR')"
}

# --------------------------------------------------------------------------
# Test 1: claudechic command exists in PATH
# --------------------------------------------------------------------------

Write-Banner "Step 2: Checking claudechic command availability..."

$claudechicCmd = Join-Path (Join-Path $PROJECT_ROOT "commands") "claudechic.ps1"
if (Test-Path $claudechicCmd) {
    Write-TestPass "claudechic.ps1 command script exists"
} else {
    Write-TestFail "claudechic.ps1 not found at $claudechicCmd"
    exit 1
}

# Also verify commands/ is in PATH (set by activate.ps1)
$commandsDir = Join-Path $PROJECT_ROOT "commands"
if ($env:PATH -like "*$commandsDir*") {
    Write-TestPass "commands/ directory is in PATH"
} else {
    Write-TestFail "commands/ directory not found in PATH"
    exit 1
}

# --------------------------------------------------------------------------
# Test 2: Run claudechic --help (triggers conda environment installation via require_env)
# --------------------------------------------------------------------------

Write-Banner "Step 3: Running claudechic command (E2E test -- triggers conda environment installation)..."

# Platform layout: envs\{platform_subdir}\claudechic
# PS 5.1: nested Join-Path (2 args max)
$envsDir = Join-Path $PROJECT_ROOT "envs"
$platformDir = Join-Path $envsDir $PLATFORM_SUBDIR
$envDir = Join-Path $platformDir "claudechic"

$envPreexisted = $false
if (Test-Path $envDir) {
    Write-Note "Note: claudechic conda environment already exists at platform layout path"
    $envPreexisted = $true
} else {
    Write-Note "Conda environment not installed - claudechic command will trigger installation..."
}

# Set SETUPTOOLS_SCM_PRETEND_VERSION to work around submodule version detection issue
# when installing the claudechic Python package in editable mode (git submodules lack full .git history)
$env:SETUPTOOLS_SCM_PRETEND_VERSION = "0.0.0+test"

Write-Banner "    Running: claudechic.ps1 --help (timeout: 5 minutes)"
Write-Host ""

# Run claudechic --help with a timeout using Start-Process (NOT Start-Job).
# Start-Job runs in a remoting runspace that wraps errors as RemoteException
# and fails to initialize conda hooks on PS 5.1. A real child process avoids
# these issues. A real child process inherits all env vars from activate.ps1
# (PROJECT_ROOT, SLC_BASE, SLC_PLATFORM, PATH, CONDA_ENVS_PATH,
# SETUPTOOLS_SCM_PRETEND_VERSION) and claudechic.ps1 -> require_env.ps1
# handles conda initialization internally.
#
# Timeout: 300 seconds (5 minutes) to allow for:
#   1. require_env to detect missing conda environment
#   2. conda environment installation (can take several minutes)
#   3. pip install -e for claudechic Python package (editable install)
#   4. Actually running --help
$timeoutSeconds = 300

# Create temp files for output capture and the helper script
$tempDir = [System.IO.Path]::GetTempPath()
$tempScript = Join-Path $tempDir "test_claudechic_run_$PID.ps1"
$outputFile = Join-Path $tempDir "test_claudechic_stdout_$PID.txt"
$errorFile = Join-Path $tempDir "test_claudechic_stderr_$PID.txt"

# Build helper script that runs claudechic.ps1 --help
$scriptContent = @"
`$ErrorActionPreference = "Continue"
Set-Location "$PROJECT_ROOT"
& "$claudechicCmd" --help
exit `$LASTEXITCODE
"@
[System.IO.File]::WriteAllText($tempScript, $scriptContent)

# Determine the PowerShell executable (same version as current session)
$psExePath = (Get-Process -Id $PID -ErrorAction SilentlyContinue).Path
if (-not $psExePath) {
    # Fallback if process path unavailable
    if ($PSVersionTable.PSVersion.Major -ge 7) { $psExePath = "pwsh.exe" }
    else { $psExePath = "powershell.exe" }
}

$process = $null
try {
    $process = Start-Process -FilePath $psExePath `
        -ArgumentList "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$tempScript`"" `
        -PassThru -NoNewWindow `
        -RedirectStandardOutput $outputFile `
        -RedirectStandardError $errorFile

    $exited = $process.WaitForExit($timeoutSeconds * 1000)

    if (-not $exited) {
        try { $process.Kill() } catch { }
        Write-TestFail "claudechic --help timed out after $timeoutSeconds seconds"
        Write-Detail "This may indicate conda environment installation is hanging"
    } else {
        $exitCode = $process.ExitCode
        # PS 5.1: ExitCode can be $null after WaitForExit; treat as 0 (success)
        if ($null -eq $exitCode) { $exitCode = 0 }

        # Read captured output from temp files
        $stdout = ""
        if (Test-Path $outputFile) {
            $stdout = [System.IO.File]::ReadAllText($outputFile)
        }
        $stderr = ""
        if (Test-Path $errorFile) {
            $stderr = [System.IO.File]::ReadAllText($errorFile)
        }

        # Display output in CI logs
        if ($stdout) {
            foreach ($outLine in ($stdout -split "\r?\n")) {
                if ($outLine) { Write-Host "    $outLine" }
            }
        }
        if ($stderr) {
            foreach ($errLine in ($stderr -split "\r?\n")) {
                if ($errLine) { Write-Host "    [stderr] $errLine" -ForegroundColor Yellow }
            }
        }
        Write-Host ""

        # Evaluate results:
        # Exit 0 = success, Exit 2 = argparse help (normal for --help)
        # Also scan for error patterns to catch silent failures where the exit
        # code is 0 but installation actually failed (prevents false PASS).
        $hasErrorPatterns = $false
        $combinedOutput = "$stdout $stderr"
        if ($combinedOutput -match '(?i)(Error:.*install|Error:.*failed|Exception:.*install)') {
            $hasErrorPatterns = $true
        }

        if (($exitCode -eq 0 -or $exitCode -eq 2) -and -not $hasErrorPatterns) {
            if ($stdout -and $stdout.Trim().Length -gt 0) {
                Write-TestPass "claudechic --help executed successfully"
            } else {
                Write-TestFail "claudechic --help produced no output"
            }
        } elseif ($hasErrorPatterns) {
            Write-TestFail "claudechic --help completed but output contains errors (exit code: $exitCode)"
            Write-Detail "Check output above for error details"
        } else {
            Write-TestFail "claudechic --help failed with exit code $exitCode"
            Write-Detail "Output was shown above"
        }
    }
} finally {
    if ($process) { $process.Dispose() }
    Remove-Item -Path $tempScript -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $outputFile -Force -ErrorAction SilentlyContinue
    Remove-Item -Path $errorFile -Force -ErrorAction SilentlyContinue
}

# --------------------------------------------------------------------------
# Test 3: Verify claudechic conda environment was created at platform layout path
# --------------------------------------------------------------------------

Write-Banner "Step 4: Verifying claudechic conda environment was installed..."

if (Test-Path $envDir) {
    if ($envPreexisted) {
        Write-TestPass "claudechic conda environment exists at platform layout path (was pre-existing)"
    } else {
        Write-TestPass "claudechic conda environment was installed by running claudechic command"
    }
} else {
    Write-TestFail "claudechic conda environment not found at $envDir"
    Write-Detail "Expected platform layout path: envs\$PLATFORM_SUBDIR\claudechic"
    Write-Detail "The claudechic command should have triggered installation via require_env"
}

# --------------------------------------------------------------------------
# Step 4b: Show environment contents in CI logs
# --------------------------------------------------------------------------

Write-Banner "Step 4b: Listing claudechic conda environment contents..."
if (Test-Path $envDir) {
    Write-Detail "Environment directory: $envDir"
    Write-Detail "Contents (top-level):"
    $items = Get-ChildItem -Path $envDir -ErrorAction SilentlyContinue | Select-Object -First 20
    foreach ($item in $items) {
        if ($item.PSIsContainer) { $itemType = "[DIR] " } else { $itemType = "      " }
        Write-Detail "  $itemType$($item.Name)"
    }
    Write-Host ""

    # Show Scripts directory (Windows equivalent of bin/)
    $scriptsDir = Join-Path $envDir "Scripts"
    if (Test-Path $scriptsDir) {
        Write-Detail "Scripts directory (first 15 entries):"
        $scripts = Get-ChildItem -Path $scriptsDir -ErrorAction SilentlyContinue | Select-Object -First 15
        foreach ($s in $scripts) {
            Write-Detail "  $($s.Name)"
        }
    }
}

# --------------------------------------------------------------------------
# Test 4: Verify claudechic Python module imports
# --------------------------------------------------------------------------

Write-Banner "Step 5: Verifying claudechic Python module imports..."

if (Test-Path $envDir) {
    # Use the conda from SLCenv to activate the claudechic conda environment
    # Platform layout: SLCenv is at envs\{platform_subdir}\SLCenv
    $slcEnvDir = Join-Path $platformDir "SLCenv"
    $condaHook = Join-Path (Join-Path (Join-Path $slcEnvDir "shell") "condabin") "conda-hook.ps1"

    $condaReady = $false
    if (Test-Path $condaHook) {
        try {
            . $condaHook
            conda activate $envDir
            $condaReady = $true
        }
        catch {
            Write-Detail "Warning: conda activate via hook failed: $_"
        }
    }

    if (-not $condaReady) {
        # Fallback: try conda.exe shell hook
        $condaExe = Join-Path (Join-Path $slcEnvDir "Scripts") "conda.exe"
        if (Test-Path $condaExe) {
            try {
                $condaInit = & $condaExe shell.powershell hook 2>$null
                if ($condaInit) {
                    Invoke-Expression $condaInit
                }
                conda activate $envDir
                $condaReady = $true
            }
            catch {
                Write-Detail "Warning: conda activate via exe fallback failed: $_"
            }
        }
    }

    if ($condaReady) {
        $importOutput = & python -c "import claudechic; print('claudechic version: ' + str(claudechic.__version__))" 2>&1
        $importExit = $LASTEXITCODE

        if ($importExit -eq 0) {
            Write-Detail "$importOutput"
            Write-TestPass "claudechic Python module imports successfully"
        } else {
            Write-TestFail "claudechic Python module failed to import"
            Write-Detail "Error: $importOutput"
        }
    } else {
        Write-TestFail "Could not activate claudechic conda environment for import test"
    }
} else {
    Write-TestFail "Cannot test import - claudechic conda environment not found"
}

# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

Write-Host ""
Write-Banner "================================================================"
if ($script:TESTS_FAILED -eq 0) {
    Write-Host "  RESULT: ALL $($script:TESTS_PASSED) TESTS PASSED" -ForegroundColor Green
    Write-Banner "================================================================"
    Write-Host ""
    exit 0
} else {
    Write-Host "  RESULT: $($script:TESTS_FAILED) TESTS FAILED, $($script:TESTS_PASSED) PASSED" -ForegroundColor Red
    Write-Banner "================================================================"
    Write-Host ""
    exit 1
}
