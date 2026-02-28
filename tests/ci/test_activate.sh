#!/bin/bash
# =============================================================================
# test_activate.sh - E2E test for `source ./activate`
# =============================================================================
# Tests the complete activation workflow as a user would experience it:
# 1. SLCenv bootstrap (Miniforge installation)
# 2. Submodule initialization
# 3. Environment activation
#
# Exit codes:
#   0 - All tests passed
#   1 - Test failed
# =============================================================================

set -e

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------

# Get script location
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
# Note: We use set +e temporarily to capture errors gracefully
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
# Test 1: SLCenv conda binary exists
# --------------------------------------------------------------------------

blue "Checking: SLCenv bootstrap completed..."

if [[ -x "$PROJECT_ROOT/envs/SLCenv/bin/conda" ]]; then
    pass "envs/SLCenv/bin/conda exists and is executable"
else
    fail "envs/SLCenv/bin/conda does not exist or is not executable"
fi

# --------------------------------------------------------------------------
# Test 2: Submodules are checked out (not empty)
# --------------------------------------------------------------------------

blue "Checking: Submodules initialized..."

# Check for claudechic specifically (main submodule)
if [[ -f "$PROJECT_ROOT/submodules/claudechic/pyproject.toml" ]]; then
    pass "submodules/claudechic/ is not empty (pyproject.toml exists)"
else
    fail "submodules/claudechic/ is empty or pyproject.toml missing"
fi

# --------------------------------------------------------------------------
# Test 3: CONDA_PREFIX is set (environment activated)
# --------------------------------------------------------------------------

blue "Checking: Environment activated..."

if [[ -n "$CONDA_PREFIX" ]]; then
    pass "CONDA_PREFIX is set: $CONDA_PREFIX"
else
    fail "CONDA_PREFIX is not set"
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
# Test 5: SLC_BASE is set
# --------------------------------------------------------------------------

blue "Checking: SLC_BASE set..."

if [[ -n "$SLC_BASE" ]]; then
    pass "SLC_BASE is set: $SLC_BASE"
else
    fail "SLC_BASE is not set"
fi

# --------------------------------------------------------------------------
# Test 6: commands/ is in PATH
# --------------------------------------------------------------------------

blue "Checking: commands/ in PATH..."

if echo "$PATH" | grep -q "$PROJECT_ROOT/commands"; then
    pass "commands/ directory is in PATH"
else
    fail "commands/ directory is not in PATH"
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
