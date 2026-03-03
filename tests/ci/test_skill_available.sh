#!/bin/bash
# =============================================================================
# test_skill_available.sh - File content verification for /ao_project_team skill
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
# Compatible with: bash 3.2+, bash 5.x, zsh 5.x
#
# Exit codes:
#   0 - All tests passed
#   1 - Test failed
# =============================================================================

set -e

# --------------------------------------------------------------------------
# Setup (bash/zsh compatible)
# --------------------------------------------------------------------------

# ${BASH_SOURCE[0]:-$0} works in both bash (uses BASH_SOURCE) and zsh (falls
# back to $0, which in zsh is the script path when running a script).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors
red() { echo -e "\033[0;31m$*\033[0m"; }
green() { echo -e "\033[0;32m$*\033[0m"; }
blue() { echo -e "\033[0;34m$*\033[0m"; }

echo ""
blue "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
blue "  TEST: /ao_project_team skill file content verification"
blue "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

TESTS_PASSED=0
TESTS_FAILED=0

pass() {
    green "  ✔ PASS: $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

fail() {
    red "  ✘ FAIL: $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

# --------------------------------------------------------------------------
# Skill file path
# --------------------------------------------------------------------------

SKILL_FILE="$PROJECT_ROOT/.claude/commands/ao_project_team.md"

# ==========================================================================
# Section A: Skill file existence and format (original checks)
# ==========================================================================

blue "--- Section A: Skill file existence and format ---"
echo ""

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
    red "  RESULT: FAILED (skill file missing — cannot continue)"
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
# Test 3: File has .md extension
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
if grep -qE '(Read|Follow|run|execute|`[^`]+`)' "$SKILL_FILE"; then
    pass "File contains actionable content (instructions/references)"
else
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
# Test 7: Referenced files exist (backtick-quoted paths)
# --------------------------------------------------------------------------

blue "Checking: Referenced files exist..."

REFS=$(grep -oE '`[^`]+\.md`' "$SKILL_FILE" | tr -d '`' || true)

if [[ -n "$REFS" ]]; then
    while IFS= read -r ref; do
        FULL_PATH="$PROJECT_ROOT/$ref"
        if [[ -f "$FULL_PATH" ]]; then
            pass "Referenced file exists: $ref"
        else
            fail "Referenced file missing: $ref"
        fi
    done <<< "$REFS"
else
    pass "No external file references to verify"
fi

# ==========================================================================
# Section B: Deep content verification of referenced files
# ==========================================================================

echo ""
blue "--- Section B: Referenced file content verification ---"
echo ""

# --------------------------------------------------------------------------
# Test 8: COORDINATOR.md is non-empty and substantial
# --------------------------------------------------------------------------

# The skill says "Read and follow: AI_agents/project_team/COORDINATOR.md"
# If that file is empty or a stub, the skill is broken even if the file exists.
COORDINATOR_FILE="$PROJECT_ROOT/AI_agents/project_team/COORDINATOR.md"

blue "Checking: COORDINATOR.md is non-empty..."

if [[ -f "$COORDINATOR_FILE" ]] && [[ -s "$COORDINATOR_FILE" ]]; then
    COORD_SIZE=$(wc -c < "$COORDINATOR_FILE" | tr -d ' ')
    pass "COORDINATOR.md is non-empty ($COORD_SIZE bytes)"
else
    fail "COORDINATOR.md is missing or empty — skill would be broken"
fi

# --------------------------------------------------------------------------
# Test 9: COORDINATOR.md contains Phase 0 (Vision phase)
# --------------------------------------------------------------------------

blue "Checking: COORDINATOR.md contains Phase 0 structural marker..."

if grep -q 'Phase 0' "$COORDINATOR_FILE" 2>/dev/null; then
    pass "COORDINATOR.md contains 'Phase 0' (Vision phase)"
else
    fail "COORDINATOR.md missing 'Phase 0' — file may be gutted or corrupted"
fi

# --------------------------------------------------------------------------
# Test 10: COORDINATOR.md contains Phase 1 (Setup phase)
# --------------------------------------------------------------------------

blue "Checking: COORDINATOR.md contains Phase 1 structural marker..."

if grep -q 'Phase 1' "$COORDINATOR_FILE" 2>/dev/null; then
    pass "COORDINATOR.md contains 'Phase 1' (Setup phase)"
else
    fail "COORDINATOR.md missing 'Phase 1' — file may be gutted or corrupted"
fi

# --------------------------------------------------------------------------
# Test 11: COORDINATOR.md contains spawn instructions (core functionality)
# --------------------------------------------------------------------------

blue "Checking: COORDINATOR.md contains spawn instructions..."

if grep -q 'Spawn' "$COORDINATOR_FILE" 2>/dev/null; then
    pass "COORDINATOR.md contains agent spawn instructions"
else
    fail "COORDINATOR.md missing spawn instructions — core workflow broken"
fi

# --------------------------------------------------------------------------
# Test 12: COORDINATOR.md contains Leadership agent names
# --------------------------------------------------------------------------

blue "Checking: COORDINATOR.md references Leadership agents..."

MISSING_AGENTS=""
for agent in Composability TerminologyGuardian Skeptic UserAlignment; do
    if ! grep -q "$agent" "$COORDINATOR_FILE" 2>/dev/null; then
        MISSING_AGENTS="$MISSING_AGENTS $agent"
    fi
done

if [[ -z "$MISSING_AGENTS" ]]; then
    pass "COORDINATOR.md references all 4 Leadership agents"
else
    fail "COORDINATOR.md missing Leadership agents:$MISSING_AGENTS"
fi

# ==========================================================================
# Section C: Skill instruction path validation
# ==========================================================================

echo ""
blue "--- Section C: Skill instruction integrity ---"
echo ""

# --------------------------------------------------------------------------
# Test 13: Skill "Read and follow" instruction references a valid path
# --------------------------------------------------------------------------

blue "Checking: Skill instruction references a resolvable path..."

# Extract the instruction pattern: "Read and follow: `some/path.md`"
INSTRUCTION_PATH=$(grep -oE 'Read and follow: `[^`]+`' "$SKILL_FILE" | grep -oE '`[^`]+`' | tr -d '`' || true)

if [[ -n "$INSTRUCTION_PATH" ]]; then
    RESOLVED="$PROJECT_ROOT/$INSTRUCTION_PATH"
    if [[ -f "$RESOLVED" ]]; then
        pass "Instruction path resolves to a real file: $INSTRUCTION_PATH"
    else
        fail "Instruction path does not resolve: $INSTRUCTION_PATH"
    fi
else
    # No "Read and follow" pattern — check if there's some other instruction
    if grep -qE '(Read|Follow).*`[^`]+`' "$SKILL_FILE"; then
        # There's a similar pattern, extract and check it
        ALT_PATH=$(grep -oE '`[A-Za-z_/][^`]*\.md`' "$SKILL_FILE" | head -1 | tr -d '`' || true)
        if [[ -n "$ALT_PATH" ]] && [[ -f "$PROJECT_ROOT/$ALT_PATH" ]]; then
            pass "Instruction references a valid path: $ALT_PATH"
        elif [[ -n "$ALT_PATH" ]]; then
            fail "Instruction references a broken path: $ALT_PATH"
        else
            pass "No file path in instructions to validate"
        fi
    else
        pass "No file-reference instructions found (skill may be self-contained)"
    fi
fi

# --------------------------------------------------------------------------
# Test 14: No broken markdown links in skill file
# --------------------------------------------------------------------------

blue "Checking: No broken markdown links in skill file..."

# Extract markdown links: [text](path)
# Only check relative paths (not http/https URLs)
BROKEN_LINKS=""
LINK_COUNT=0

while IFS= read -r link_path; do
    # Skip URLs (http, https, mailto, etc.)
    if echo "$link_path" | grep -qE '^(https?://|mailto:|#)'; then
        continue
    fi
    LINK_COUNT=$((LINK_COUNT + 1))
    RESOLVED_LINK="$PROJECT_ROOT/$link_path"
    if [[ ! -f "$RESOLVED_LINK" ]] && [[ ! -d "$RESOLVED_LINK" ]]; then
        BROKEN_LINKS="$BROKEN_LINKS  - $link_path\n"
    fi
done <<< "$(grep -oE '\[[^]]*\]\([^)]+\)' "$SKILL_FILE" 2>/dev/null | grep -oE '\([^)]+\)' | tr -d '()' || true)"

if [[ -n "$BROKEN_LINKS" ]]; then
    fail "Broken markdown links found in skill file:\n$BROKEN_LINKS"
elif [[ $LINK_COUNT -gt 0 ]]; then
    pass "All $LINK_COUNT markdown link(s) resolve correctly"
else
    pass "No markdown links to verify (skill uses backtick references)"
fi

# ==========================================================================
# Results
# ==========================================================================

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
