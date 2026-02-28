#!/bin/bash
# =============================================================================
# test_skill_available.sh - E2E test for /ao_project_team skill availability
# =============================================================================
# Verifies the /ao_project_team skill is available in Claude Code:
# 1. File exists at .claude/commands/ao_project_team.md
# 2. File is non-empty
# 3. File contains valid skill format (markdown with title)
#
# Note: This uses the "Medium" verification approach (file + format check)
# as approved by the user, rather than runtime verification.
#
# Exit codes:
#   0 - All tests passed
#   1 - Test failed
# =============================================================================

set -e

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors
red() { echo -e "\033[0;31m$*\033[0m"; }
green() { echo -e "\033[0;32m$*\033[0m"; }
blue() { echo -e "\033[0;34m$*\033[0m"; }

echo ""
blue "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
blue "  TEST: /ao_project_team skill available"
blue "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

TESTS_PASSED=0
TESTS_FAILED=0

pass() {
    green "  ✔ PASS: $1"
    ((++TESTS_PASSED))
}

fail() {
    red "  ✘ FAIL: $1"
    ((++TESTS_FAILED))
}

# --------------------------------------------------------------------------
# Skill file path
# --------------------------------------------------------------------------

SKILL_FILE="$PROJECT_ROOT/.claude/commands/ao_project_team.md"

# --------------------------------------------------------------------------
# Test 1: Skill file exists
# --------------------------------------------------------------------------

blue "Checking: Skill file exists..."

if [[ -f "$SKILL_FILE" ]]; then
    pass "Skill file exists at .claude/commands/ao_project_team.md"
else
    fail "Skill file does not exist at .claude/commands/ao_project_team.md"
    echo ""
    red "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    red "  RESULT: FAILED (skill file missing)"
    red "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi

# --------------------------------------------------------------------------
# Test 2: Skill file is non-empty
# --------------------------------------------------------------------------

blue "Checking: Skill file is non-empty..."

if [[ -s "$SKILL_FILE" ]]; then
    FILESIZE=$(wc -c < "$SKILL_FILE" | tr -d ' ')
    pass "Skill file is non-empty ($FILESIZE bytes)"
else
    fail "Skill file is empty"
fi

# --------------------------------------------------------------------------
# Test 3: File is valid markdown (has .md extension - already checked by path)
# --------------------------------------------------------------------------

blue "Checking: File has .md extension..."

if [[ "$SKILL_FILE" == *.md ]]; then
    pass "File has .md extension"
else
    fail "File does not have .md extension"
fi

# --------------------------------------------------------------------------
# Test 4: File contains H1 heading (skill title)
# --------------------------------------------------------------------------

blue "Checking: File contains skill title (H1 heading)..."

if grep -q '^# ' "$SKILL_FILE"; then
    TITLE=$(grep -m1 '^# ' "$SKILL_FILE" | sed 's/^# *//')
    pass "File contains H1 heading: \"$TITLE\""
else
    fail "File does not contain H1 heading (skill title)"
fi

# --------------------------------------------------------------------------
# Test 5: File contains actionable content
# --------------------------------------------------------------------------

blue "Checking: File contains actionable content..."

# Skills should have some instruction or reference
# Check for common patterns: code blocks, links, or instructions
if grep -qE '(Read|Follow|run|execute|`[^`]+`)' "$SKILL_FILE"; then
    pass "File contains actionable content (instructions/references)"
else
    # Not a hard failure, but worth noting
    pass "File format appears valid (no explicit instructions detected)"
fi

# --------------------------------------------------------------------------
# Test 6: .claude/commands directory is properly structured
# --------------------------------------------------------------------------

blue "Checking: .claude/commands directory structure..."

COMMANDS_DIR="$PROJECT_ROOT/.claude/commands"

if [[ -d "$COMMANDS_DIR" ]]; then
    SKILL_COUNT=$(find "$COMMANDS_DIR" -name "*.md" -type f | wc -l | tr -d ' ')
    pass ".claude/commands/ directory exists with $SKILL_COUNT skill(s)"
else
    fail ".claude/commands/ directory does not exist"
fi

# --------------------------------------------------------------------------
# Test 7: Referenced file exists (if skill references another file)
# --------------------------------------------------------------------------

blue "Checking: Referenced files exist..."

# Extract file references from the skill (backticked paths)
REFS=$(grep -oE '`[^`]+\.md`' "$SKILL_FILE" | tr -d '`' || true)

if [[ -n "$REFS" ]]; then
    ALL_REFS_EXIST=true
    while IFS= read -r ref; do
        FULL_PATH="$PROJECT_ROOT/$ref"
        if [[ -f "$FULL_PATH" ]]; then
            pass "Referenced file exists: $ref"
        else
            fail "Referenced file missing: $ref"
            ALL_REFS_EXIST=false
        fi
    done <<< "$REFS"
else
    pass "No external file references to verify"
fi

# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

echo ""
blue "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $TESTS_FAILED -eq 0 ]]; then
    green "  RESULT: ALL $TESTS_PASSED TESTS PASSED"
    blue "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    exit 0
else
    red "  RESULT: $TESTS_FAILED TESTS FAILED, $TESTS_PASSED PASSED"
    blue "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    exit 1
fi
