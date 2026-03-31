#!/bin/bash
# =============================================================================
# test_activate.sh - E2E test for `source ./activate`
# =============================================================================
# Tests the pixi-based activation workflow as a user would experience it:
# 1. Pixi bootstrap (if needed)
# 2. Submodule initialization
# 3. Environment activation and seam registry display
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

# Colors for output
red() { echo -e "\033[0;31m$*\033[0m"; }
green() { echo -e "\033[0;32m$*\033[0m"; }
blue() { echo -e "\033[0;34m$*\033[0m"; }

echo ""
blue "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
blue "  TEST: source ./activate"
blue "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Track test results
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
# Run activation
# --------------------------------------------------------------------------

blue "Running: source ./activate"
echo ""

cd "$PROJECT_ROOT"

# Source the activate script
set +e
source ./activate
ACTIVATE_EXIT=$?
set -e

if [[ $ACTIVATE_EXIT -ne 0 ]]; then
    fail "activate script exited with code $ACTIVATE_EXIT"
    echo ""
    red "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    red "  RESULT: FAILED (activate script error)"
    red "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi

echo ""

# --------------------------------------------------------------------------
# Test 1: pixi is available
# --------------------------------------------------------------------------

blue "Checking: pixi is available..."

if command -v pixi &> /dev/null; then
    pass "pixi command is available: $(pixi --version 2>/dev/null || echo 'version unknown')"
else
    fail "pixi command not found"
fi

# --------------------------------------------------------------------------
# Test 2: pixi.toml exists
# --------------------------------------------------------------------------

blue "Checking: pixi.toml exists..."

if [[ -f "$PROJECT_ROOT/pixi.toml" ]]; then
    pass "pixi.toml exists"
else
    fail "pixi.toml not found"
fi

# --------------------------------------------------------------------------
# Test 3: Submodules are checked out (not empty)
# --------------------------------------------------------------------------

blue "Checking: Submodules initialized..."

if [[ -f "$PROJECT_ROOT/submodules/claudechic/pyproject.toml" ]]; then
    pass "submodules/claudechic/ is not empty (pyproject.toml exists)"
else
    fail "submodules/claudechic/ is empty or pyproject.toml missing"
fi

# --------------------------------------------------------------------------
# Test 4: PROJECT_ROOT is set correctly
# --------------------------------------------------------------------------

blue "Checking: PROJECT_ROOT set..."

if [[ "$PROJECT_ROOT" == "$(pwd)" ]]; then
    pass "PROJECT_ROOT matches current directory"
else
    fail "PROJECT_ROOT mismatch: $PROJECT_ROOT vs $(pwd)"
fi

# --------------------------------------------------------------------------
# Test 5: commands/ is in PATH
# --------------------------------------------------------------------------

blue "Checking: commands/ in PATH..."

if echo "$PATH" | grep -q "$PROJECT_ROOT/commands"; then
    pass "commands/ directory is in PATH"
else
    fail "commands/ directory is not in PATH"
fi

# --------------------------------------------------------------------------
# Test 6: pixi.toml contains expected features
# --------------------------------------------------------------------------

blue "Checking: pixi.toml contains claudechic in base dependencies..."

if grep -q '\[pypi-dependencies\]' "$PROJECT_ROOT/pixi.toml" && grep -q 'claudechic' "$PROJECT_ROOT/pixi.toml"; then
    pass "pixi.toml contains claudechic in base [pypi-dependencies]"
else
    fail "pixi.toml missing claudechic in base dependencies"
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
