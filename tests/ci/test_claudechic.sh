#!/bin/bash
# =============================================================================
# test_claudechic.sh - E2E test for `claudechic` command
# =============================================================================
# Tests that claudechic can be installed and launched via pixi:
# 1. pixi install
# 2. claudechic --help
# 3. claudechic module imports in Python
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
yellow() { echo -e "\033[0;33m$*\033[0m"; }

echo ""
blue "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
blue "  TEST: claudechic (pixi)"
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

cd "$PROJECT_ROOT"

# Set SETUPTOOLS_SCM_PRETEND_VERSION for git submodule editable installs
export SETUPTOOLS_SCM_PRETEND_VERSION="0.0.0+test"

# --------------------------------------------------------------------------
# Test 1: pixi install
# --------------------------------------------------------------------------

blue "Step 1: Installing claudechic environment via pixi..."

set +e
pixi install
INSTALL_EXIT=$?
set -e

if [[ $INSTALL_EXIT -eq 0 ]]; then
    pass "pixi install succeeded"
else
    fail "pixi install failed with exit code $INSTALL_EXIT"
    exit 1
fi

# --------------------------------------------------------------------------
# Test 2: claudechic --help
# --------------------------------------------------------------------------

blue "Step 2: Running claudechic --help..."

OUTPUT_FILE=$(mktemp)
cleanup() { rm -f "$OUTPUT_FILE"; }
trap cleanup EXIT

set +e
pixi run claudechic --help > "$OUTPUT_FILE" 2>&1
HELP_EXIT=$?
set -e

cat "$OUTPUT_FILE"

# --help may exit 0 or 2 (argparse), both are fine
if [[ $HELP_EXIT -eq 0 ]] || [[ $HELP_EXIT -eq 2 ]]; then
    if [[ -s "$OUTPUT_FILE" ]]; then
        pass "claudechic --help executed successfully"
    else
        fail "claudechic --help produced no output"
    fi
else
    fail "claudechic --help failed with exit code $HELP_EXIT"
fi

# --------------------------------------------------------------------------
# Test 3: claudechic module imports
# --------------------------------------------------------------------------

blue "Step 3: Verifying claudechic Python module imports..."

set +e
IMPORT_OUTPUT=$(pixi run python -c "import claudechic; print(f'claudechic version: {claudechic.__version__}')" 2>&1)
IMPORT_EXIT=$?
set -e

if [[ $IMPORT_EXIT -eq 0 ]]; then
    echo "    $IMPORT_OUTPUT"
    pass "claudechic Python module imports successfully"
else
    fail "claudechic Python module failed to import"
    echo "    Error: $IMPORT_OUTPUT"
fi

# --------------------------------------------------------------------------
# Test 4: .pixi/envs/default/ directory exists
# --------------------------------------------------------------------------

blue "Step 4: Verifying pixi environment directory..."

if [[ -d "$PROJECT_ROOT/.pixi/envs/default" ]]; then
    pass ".pixi/envs/default/ directory exists"
else
    fail ".pixi/envs/default/ directory not found"
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
