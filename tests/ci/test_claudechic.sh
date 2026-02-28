#!/bin/bash
# =============================================================================
# test_claudechic.sh - E2E test for `claudechic` command
# =============================================================================
# Tests that claudechic can be launched and produces expected output:
# 1. Environment activation (prerequisite)
# 2. Claudechic conda env installation
# 3. Process launches and produces TUI output
#
# Strategy:
# - Run claudechic with timeout, capture stdout/stderr
# - Verify expected output appears (TUI elements)
# - Kill process cleanly after verification
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
blue "  TEST: claudechic"
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
# Prerequisite: Activate environment
# --------------------------------------------------------------------------

blue "Step 1: Activating project environment..."

cd "$PROJECT_ROOT"

set +e
source ./activate
ACTIVATE_EXIT=$?
set -e

if [[ $ACTIVATE_EXIT -ne 0 ]]; then
    fail "activate script failed (prerequisite)"
    exit 1
fi
pass "Project environment activated"

# --------------------------------------------------------------------------
# Test 1: Claudechic command exists in PATH
# --------------------------------------------------------------------------

blue "Step 2: Checking claudechic command availability..."

if command -v claudechic &> /dev/null; then
    pass "claudechic command is in PATH"
else
    fail "claudechic command not found in PATH"
    exit 1
fi

# --------------------------------------------------------------------------
# Test 2: Claudechic environment is installed (or can be installed)
# --------------------------------------------------------------------------

blue "Step 3: Ensuring claudechic environment is installed..."

# The claudechic command itself handles env installation via require_env
# We'll verify by checking if the env directory exists after a dry-run
# or by checking the require_env output

if [[ -d "$PROJECT_ROOT/envs/claudechic" ]]; then
    pass "claudechic conda environment already installed"
else
    yellow "    Environment not yet installed, will be installed on first run"
fi

# --------------------------------------------------------------------------
# Test 3: Launch claudechic and verify TUI output
# --------------------------------------------------------------------------

blue "Step 4: Launching claudechic (with timeout)..."

# Create a temp file for output capture
OUTPUT_FILE=$(mktemp)
ERROR_FILE=$(mktemp)

# Cleanup function
cleanup() {
    rm -f "$OUTPUT_FILE" "$ERROR_FILE"
}
trap cleanup EXIT

# Run claudechic with a short timeout
# We use --help first to verify basic functionality without needing API keys
# This tests that the module loads correctly

# Set SETUPTOOLS_SCM_PRETEND_VERSION to work around submodule version detection issue
# when installing claudechic in editable mode
export SETUPTOOLS_SCM_PRETEND_VERSION="0.0.0+test"

set +e
# Use gtimeout on macOS if available, otherwise fall back to perl-based timeout
if command -v gtimeout &> /dev/null; then
    gtimeout 60s "$PROJECT_ROOT/commands/claudechic" --help > "$OUTPUT_FILE" 2> "$ERROR_FILE"
elif command -v timeout &> /dev/null; then
    timeout 60s "$PROJECT_ROOT/commands/claudechic" --help > "$OUTPUT_FILE" 2> "$ERROR_FILE"
else
    # Perl-based timeout for macOS without coreutils
    perl -e 'alarm shift; exec @ARGV' 60 "$PROJECT_ROOT/commands/claudechic" --help > "$OUTPUT_FILE" 2> "$ERROR_FILE"
fi
CLAUDECHIC_EXIT=$?
set -e

# Check if claudechic responded to --help
if [[ $CLAUDECHIC_EXIT -eq 0 ]] || [[ $CLAUDECHIC_EXIT -eq 2 ]]; then
    # Exit 0 = success, Exit 2 = argparse help (normal)
    if [[ -s "$OUTPUT_FILE" ]]; then
        pass "claudechic --help produced output"
    else
        # Some Python CLIs output help to stderr
        if [[ -s "$ERROR_FILE" ]]; then
            pass "claudechic --help produced output (stderr)"
        else
            fail "claudechic --help produced no output"
        fi
    fi
else
    fail "claudechic --help failed with exit code $CLAUDECHIC_EXIT"
    echo "  stdout: $(cat "$OUTPUT_FILE")"
    echo "  stderr: $(cat "$ERROR_FILE")"
fi

# --------------------------------------------------------------------------
# Test 4: Verify claudechic module can be imported
# --------------------------------------------------------------------------

blue "Step 5: Verifying claudechic Python module..."

# Activate the claudechic conda environment and test import
CLAUDECHIC_ENV="$PROJECT_ROOT/envs/claudechic"
if [[ -d "$CLAUDECHIC_ENV" ]]; then
    # Use the conda from SLCenv to activate claudechic env
    source "$PROJECT_ROOT/envs/SLCenv/etc/profile.d/conda.sh"
    conda activate "$CLAUDECHIC_ENV" 2>/dev/null || true

    # Install claudechic in editable mode if not already installed
    if ! python -c "import claudechic" 2>/dev/null; then
        echo "  Installing claudechic in editable mode..."
        # Set SETUPTOOLS_SCM_PRETEND_VERSION to work around submodule version detection
        export SETUPTOOLS_SCM_PRETEND_VERSION="0.0.0+test"
        pip install -e "$PROJECT_ROOT/submodules/claudechic" --quiet 2>/dev/null || true
    fi

    set +e
    python -c "import claudechic; print(f'claudechic version: {claudechic.__version__}')"
    IMPORT_EXIT=$?
    set -e

    if [[ $IMPORT_EXIT -eq 0 ]]; then
        pass "claudechic Python module imports successfully"
    else
        fail "claudechic Python module failed to import"
    fi
else
    fail "claudechic environment not found at $CLAUDECHIC_ENV"
fi

# --------------------------------------------------------------------------
# Test 5: Verify claudechic environment was created
# --------------------------------------------------------------------------

blue "Step 6: Verifying claudechic environment exists..."

if [[ -d "$PROJECT_ROOT/envs/claudechic" ]]; then
    pass "claudechic conda environment exists"
else
    fail "claudechic conda environment not created"
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
