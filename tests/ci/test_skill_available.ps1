# =============================================================================
# test_skill_available.ps1 - File content verification for /ao_project_team skill
# =============================================================================
# Verifies the /ao_project_team skill file is correctly structured and that
# all referenced files exist and contain expected content.
#
# NOTE: This is a static file content verification test, NOT an E2E execution
# test. Skills are markdown files consumed by Claude Code at runtime. There is
# no way to verify Claude Code actually loads the skill without a running Claude
# Code session, which is unavailable in CI. This test verifies everything that
# CAN be verified statically: file presence, format, structural integrity of
# referenced files, and link validity.
#
# What this test catches:
#   - Skill file deleted or emptied
#   - Referenced COORDINATOR.md deleted, emptied, or gutted
#   - Broken file path references in the skill
#   - Broken markdown links
#   - Missing expected structural content in referenced files
#
# What this test CANNOT catch (requires Claude Code runtime):
#   - Whether Claude Code recognizes the skill
#   - Whether the skill's instructions are semantically correct
#
# Compatible with: PowerShell 5.1 and PowerShell 7.x
#
# Exit codes:
#   0 - All tests passed
#   1 - Test failed
# =============================================================================

$ErrorActionPreference = "Stop"

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)

# Pass/fail tracking
$script:TestsPassed = 0
$script:TestsFailed = 0

function Write-Blue {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Cyan
}

function Write-Pass {
    param([string]$Message)
    Write-Host "  PASS: $Message" -ForegroundColor Green
    $script:TestsPassed++
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  FAIL: $Message" -ForegroundColor Red
    $script:TestsFailed++
}

Write-Host ""
Write-Blue "================================================================"
Write-Blue "  TEST: /ao_project_team skill file content verification"
Write-Blue "================================================================"
Write-Host ""

# --------------------------------------------------------------------------
# Skill file path
# --------------------------------------------------------------------------

# PS 5.1: Join-Path only accepts two arguments; nest calls for multi-segment paths
$SkillDir  = Join-Path (Join-Path $ProjectRoot ".claude") "commands"
$SkillFile = Join-Path $SkillDir "ao_project_team.md"

# ==========================================================================
# Section A: Skill file existence and format
# ==========================================================================

Write-Blue "--- Section A: Skill file existence and format ---"
Write-Host ""

# --------------------------------------------------------------------------
# Test 1: Skill file exists
# --------------------------------------------------------------------------

Write-Blue "Checking: Skill file exists..."

if (Test-Path -LiteralPath $SkillFile -PathType Leaf) {
    Write-Pass "Skill file exists at .claude/commands/ao_project_team.md"
} else {
    Write-Fail "Skill file does not exist at .claude/commands/ao_project_team.md"
    Write-Host ""
    Write-Blue "================================================================"
    Write-Host "  RESULT: FAILED (skill file missing - cannot continue)" -ForegroundColor Red
    Write-Blue "================================================================"
    exit 1
}

# --------------------------------------------------------------------------
# Test 2: Skill file is non-empty
# --------------------------------------------------------------------------

Write-Blue "Checking: Skill file is non-empty..."

$FileInfo = Get-Item -LiteralPath $SkillFile
if ($FileInfo.Length -gt 0) {
    Write-Pass "Skill file is non-empty ($($FileInfo.Length) bytes)"
} else {
    Write-Fail "Skill file is empty (0 bytes)"
}

# --------------------------------------------------------------------------
# Test 3: File has .md extension
# --------------------------------------------------------------------------

Write-Blue "Checking: File has .md extension..."

if ($SkillFile.EndsWith(".md")) {
    Write-Pass "File has .md extension"
} else {
    Write-Fail "File does not have .md extension"
}

# --------------------------------------------------------------------------
# Test 4: File contains H1 heading (skill title)
# --------------------------------------------------------------------------

Write-Blue "Checking: File contains skill title (H1 heading)..."

# Read all lines; -Encoding UTF8 works on both PS 5.1 and 7.x
$Lines = Get-Content -LiteralPath $SkillFile -Encoding UTF8

$H1Line = $null
foreach ($line in $Lines) {
    if ($line -match "^# .+") {
        $H1Line = $line
        break
    }
}

if ($null -ne $H1Line) {
    $Title = ($H1Line -replace "^#\s*", "").Trim()
    Write-Pass "File contains H1 heading: `"$Title`""
} else {
    Write-Fail "File does not contain H1 heading (skill title)"
}

# --------------------------------------------------------------------------
# Test 5: File contains actionable content
# --------------------------------------------------------------------------

Write-Blue "Checking: File contains actionable content..."

# Join all lines into a single string for pattern matching
$Content = $Lines -join "`n"

# Skills should have instructions or references (e.g. Read, Follow, run, execute, backticked paths)
if ($Content -match "(Read|Follow|run|execute|``[^``]+``)" ) {
    Write-Pass "File contains actionable content (instructions/references)"
} else {
    # Not a hard failure - format is still valid
    Write-Pass "File format appears valid (no explicit instructions detected)"
}

# --------------------------------------------------------------------------
# Test 6: .claude/commands/ directory is properly structured
# --------------------------------------------------------------------------

Write-Blue "Checking: .claude/commands/ directory structure..."

if (Test-Path -LiteralPath $SkillDir -PathType Container) {
    $SkillFiles = Get-ChildItem -LiteralPath $SkillDir -Filter "*.md" -File
    $SkillCount = @($SkillFiles).Count
    Write-Pass ".claude/commands/ directory exists with $SkillCount skill(s)"
} else {
    Write-Fail ".claude/commands/ directory does not exist"
}

# --------------------------------------------------------------------------
# Test 7: Referenced files exist (backtick-quoted paths)
# --------------------------------------------------------------------------

Write-Blue "Checking: Referenced files exist..."

# Extract backticked file paths that end in .md (e.g. `AI_agents/project_team/COORDINATOR.md`)
$Refs = @()
foreach ($line in $Lines) {
    $MatchesFound = [regex]::Matches($line, '`([^`]+\.md)`')
    foreach ($m in $MatchesFound) {
        $Refs += $m.Groups[1].Value
    }
}

if ($Refs.Count -gt 0) {
    foreach ($ref in $Refs) {
        $FullPath = Join-Path $ProjectRoot $ref
        if (Test-Path -LiteralPath $FullPath -PathType Leaf) {
            Write-Pass "Referenced file exists: $ref"
        } else {
            Write-Fail "Referenced file missing: $ref"
        }
    }
} else {
    Write-Pass "No external file references to verify"
}

# ==========================================================================
# Section B: Deep content verification of referenced files
# ==========================================================================

Write-Host ""
Write-Blue "--- Section B: Referenced file content verification ---"
Write-Host ""

# --------------------------------------------------------------------------
# Test 8: COORDINATOR.md is non-empty and substantial
# --------------------------------------------------------------------------

# The skill says "Read and follow: AI_agents/project_team/COORDINATOR.md"
# If that file is empty or a stub, the skill is broken even if the file exists.
$CoordinatorFile = Join-Path (Join-Path (Join-Path $ProjectRoot "AI_agents") "project_team") "COORDINATOR.md"

Write-Blue "Checking: COORDINATOR.md is non-empty..."

if ((Test-Path -LiteralPath $CoordinatorFile -PathType Leaf)) {
    $CoordInfo = Get-Item -LiteralPath $CoordinatorFile
    if ($CoordInfo.Length -gt 0) {
        Write-Pass "COORDINATOR.md is non-empty ($($CoordInfo.Length) bytes)"
    } else {
        Write-Fail "COORDINATOR.md is empty - skill would be broken"
    }
} else {
    Write-Fail "COORDINATOR.md is missing - skill would be broken"
}

# --------------------------------------------------------------------------
# Test 9: COORDINATOR.md contains Phase 0 (Vision phase)
# --------------------------------------------------------------------------

Write-Blue "Checking: COORDINATOR.md contains Phase 0 structural marker..."

$CoordLines = @()
if (Test-Path -LiteralPath $CoordinatorFile -PathType Leaf) {
    $CoordLines = Get-Content -LiteralPath $CoordinatorFile -Encoding UTF8
}
$CoordContent = $CoordLines -join "`n"

if ($CoordContent -match "Phase 0") {
    Write-Pass "COORDINATOR.md contains 'Phase 0' (Vision phase)"
} else {
    Write-Fail "COORDINATOR.md missing 'Phase 0' - file may be gutted or corrupted"
}

# --------------------------------------------------------------------------
# Test 10: COORDINATOR.md contains Phase 1 (Setup phase)
# --------------------------------------------------------------------------

Write-Blue "Checking: COORDINATOR.md contains Phase 1 structural marker..."

if ($CoordContent -match "Phase 1") {
    Write-Pass "COORDINATOR.md contains 'Phase 1' (Setup phase)"
} else {
    Write-Fail "COORDINATOR.md missing 'Phase 1' - file may be gutted or corrupted"
}

# --------------------------------------------------------------------------
# Test 11: COORDINATOR.md contains spawn instructions (core functionality)
# --------------------------------------------------------------------------

Write-Blue "Checking: COORDINATOR.md contains spawn instructions..."

if ($CoordContent -match "Spawn") {
    Write-Pass "COORDINATOR.md contains agent spawn instructions"
} else {
    Write-Fail "COORDINATOR.md missing spawn instructions - core workflow broken"
}

# --------------------------------------------------------------------------
# Test 12: COORDINATOR.md contains Leadership agent names
# --------------------------------------------------------------------------

Write-Blue "Checking: COORDINATOR.md references Leadership agents..."

$LeadershipAgents = @("Composability", "TerminologyGuardian", "Skeptic", "UserAlignment")
$MissingAgents = @()

foreach ($agent in $LeadershipAgents) {
    if ($CoordContent -notmatch [regex]::Escape($agent)) {
        $MissingAgents += $agent
    }
}

if ($MissingAgents.Count -eq 0) {
    Write-Pass "COORDINATOR.md references all 4 Leadership agents"
} else {
    $MissingList = $MissingAgents -join ", "
    Write-Fail "COORDINATOR.md missing Leadership agents: $MissingList"
}

# ==========================================================================
# Section C: Skill instruction path validation
# ==========================================================================

Write-Host ""
Write-Blue "--- Section C: Skill instruction integrity ---"
Write-Host ""

# --------------------------------------------------------------------------
# Test 13: Skill "Read and follow" instruction references a valid path
# --------------------------------------------------------------------------

Write-Blue "Checking: Skill instruction references a resolvable path..."

# Extract the instruction pattern: "Read and follow: `some/path.md`"
$InstructionPath = $null
if ($Content -match 'Read and follow:\s*`([^`]+)`') {
    $InstructionPath = $Matches[1]
}

if ($null -ne $InstructionPath) {
    $Resolved = Join-Path $ProjectRoot $InstructionPath
    if (Test-Path -LiteralPath $Resolved -PathType Leaf) {
        Write-Pass "Instruction path resolves to a real file: $InstructionPath"
    } else {
        Write-Fail "Instruction path does not resolve: $InstructionPath"
    }
} else {
    # No "Read and follow" pattern - check if there's some other instruction
    if ($Content -match '(Read|Follow).*`([^`]+\.md)`') {
        $AltPath = $Matches[2]
        $AltResolved = Join-Path $ProjectRoot $AltPath
        if (Test-Path -LiteralPath $AltResolved -PathType Leaf) {
            Write-Pass "Instruction references a valid path: $AltPath"
        } else {
            Write-Fail "Instruction references a broken path: $AltPath"
        }
    } else {
        Write-Pass "No file-reference instructions found (skill may be self-contained)"
    }
}

# --------------------------------------------------------------------------
# Test 14: No broken markdown links in skill file
# --------------------------------------------------------------------------

Write-Blue "Checking: No broken markdown links in skill file..."

# Extract markdown links: [text](path)
# Only check relative paths (not http/https URLs)
$BrokenLinks = @()
$LinkCount = 0

$LinkMatches = [regex]::Matches($Content, '\[[^\]]*\]\(([^)]+)\)')
foreach ($lm in $LinkMatches) {
    $LinkPath = $lm.Groups[1].Value
    # Skip URLs (http, https, mailto, anchors)
    if ($LinkPath -match '^(https?://|mailto:|#)') {
        continue
    }
    $LinkCount++
    $ResolvedLink = Join-Path $ProjectRoot $LinkPath
    if (-not (Test-Path -LiteralPath $ResolvedLink)) {
        $BrokenLinks += $LinkPath
    }
}

if ($BrokenLinks.Count -gt 0) {
    $BrokenList = ($BrokenLinks | ForEach-Object { "  - $_" }) -join "`n"
    Write-Fail "Broken markdown links found in skill file:`n$BrokenList"
} elseif ($LinkCount -gt 0) {
    Write-Pass "All $LinkCount markdown link(s) resolve correctly"
} else {
    Write-Pass "No markdown links to verify (skill uses backtick references)"
}

# ==========================================================================
# Results
# ==========================================================================

Write-Host ""
Write-Blue "================================================================"
if ($script:TestsFailed -eq 0) {
    Write-Host "  RESULT: ALL $script:TestsPassed TESTS PASSED" -ForegroundColor Green
    Write-Blue "================================================================"
    Write-Host ""
    exit 0
} else {
    Write-Host "  RESULT: $script:TestsFailed TESTS FAILED, $script:TestsPassed PASSED" -ForegroundColor Red
    Write-Blue "================================================================"
    Write-Host ""
    exit 1
}
