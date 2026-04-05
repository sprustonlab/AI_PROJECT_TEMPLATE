#!/bin/bash
# =============================================================================
# test_activate.sh - E2E test for `source ./activate`
# =============================================================================
# Tests the complete activate script workflow as a user would experience it:
# 1. SLCenv bootstrap (Miniforge installation)
# 2. Submodule initialization
# 3. SLCenv conda environment is activated (conda activate)
# 4. Platform layout paths are set correctly (envs/{platform_subdir}/SLCenv)
#
# Shell compatibility:
#   Compatible with both bash and zsh. CI invokes explicitly with the target
#   shell (e.g., `bash test_activate.sh` or `zsh test_activate.sh`), so the
#   shebang is only used for direct execution.
#
# Exit codes:
#   0 - All tests passed
#   1 - Test failed
# =============================================================================

set -e

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------

# Get script location (portable: bash uses BASH_SOURCE, zsh uses $0)
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
fi
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
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

fail() {
    red "  ✘ FAIL: $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

# --------------------------------------------------------------------------
# Source the activate script
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
# Test 1: SLC_PLATFORM is set to a platform_subdir value
# --------------------------------------------------------------------------

blue "Checking: SLC_PLATFORM set to platform_subdir..."

if [[ -n "$SLC_PLATFORM" ]]; then
    pass "SLC_PLATFORM is set: $SLC_PLATFORM"
else
    fail "SLC_PLATFORM is not set"
fi

# Use SLC_PLATFORM as the platform_subdir for path checks
PLATFORM_SUBDIR="${SLC_PLATFORM:-linux-64}"

# --------------------------------------------------------------------------
# Test 2: SLCenv conda binary exists (platform layout path)
# --------------------------------------------------------------------------

blue "Checking: SLCenv bootstrap completed (platform layout)..."

if [[ -x "$PROJECT_ROOT/envs/$PLATFORM_SUBDIR/SLCenv/bin/conda" ]]; then
    pass "envs/$PLATFORM_SUBDIR/SLCenv/bin/conda exists and is executable"
else
    fail "envs/$PLATFORM_SUBDIR/SLCenv/bin/conda does not exist or is not executable"
fi

# --------------------------------------------------------------------------
# Test 3: Submodules are checked out (not empty)
# --------------------------------------------------------------------------

blue "Checking: Submodules initialized..."

# Check for claudechic specifically (main submodule)
if [[ -f "$PROJECT_ROOT/submodules/claudechic/pyproject.toml" ]]; then
    pass "submodules/claudechic/ is not empty (pyproject.toml exists)"
else
    fail "submodules/claudechic/ is empty or pyproject.toml missing"
fi

# --------------------------------------------------------------------------
# Test 4: CONDA_PREFIX is set (SLCenv base environment activated)
# --------------------------------------------------------------------------

blue "Checking: SLCenv base environment activated..."

if [[ -n "$CONDA_PREFIX" ]]; then
    pass "CONDA_PREFIX is set: $CONDA_PREFIX"
else
    fail "CONDA_PREFIX is not set"
fi

# --------------------------------------------------------------------------
# Test 5: PROJECT_ROOT is set correctly
# --------------------------------------------------------------------------

blue "Checking: PROJECT_ROOT set..."

if [[ "$PROJECT_ROOT" == "$(pwd)" ]]; then
    pass "PROJECT_ROOT matches current directory"
else
    fail "PROJECT_ROOT mismatch: $PROJECT_ROOT vs $(pwd)"
fi

# --------------------------------------------------------------------------
# Test 6: SLC_BASE is set
# --------------------------------------------------------------------------

blue "Checking: SLC_BASE set..."

if [[ -n "$SLC_BASE" ]]; then
    pass "SLC_BASE is set: $SLC_BASE"
else
    fail "SLC_BASE is not set"
fi

# --------------------------------------------------------------------------
# Test 7: commands/ is in PATH
# --------------------------------------------------------------------------

blue "Checking: commands/ in PATH..."

if echo "$PATH" | grep -q "$PROJECT_ROOT/commands"; then
    pass "commands/ directory is in PATH"
else
    fail "commands/ directory is not in PATH"
fi

# --------------------------------------------------------------------------
# Test 8: CONDA_ENVS_PATH points to platform layout directory
# --------------------------------------------------------------------------

blue "Checking: CONDA_ENVS_PATH uses platform layout..."

if [[ -n "$CONDA_ENVS_PATH" ]]; then
    if echo "$CONDA_ENVS_PATH" | grep -q "envs/$PLATFORM_SUBDIR"; then
        pass "CONDA_ENVS_PATH includes platform layout path: $CONDA_ENVS_PATH"
    else
        fail "CONDA_ENVS_PATH does not include 'envs/$PLATFORM_SUBDIR': $CONDA_ENVS_PATH"
    fi
else
    fail "CONDA_ENVS_PATH is not set"
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
