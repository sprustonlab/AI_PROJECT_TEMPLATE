#!/bin/bash
# =============================================================================
# test_claudechic.sh - E2E test for the claudechic command
# =============================================================================
# Tests that the claudechic command can be launched and produces expected output:
# 1. Environment activation (prerequisite via the activate script)
# 2. claudechic conda environment installation (via require_env)
# 3. Process launches and produces TUI output
#
# Strategy:
# - Run the claudechic command with timeout, capture stdout/stderr
# - Verify expected output appears (TUI elements)
# - Kill process cleanly after verification
#
# Shell compatibility:
#   Compatible with both bash and zsh. CI invokes explicitly with the target
#   shell (e.g., `bash test_claudechic.sh` or `zsh test_claudechic.sh`), so
#   the shebang is only used for direct execution.
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
# Test 2: Run claudechic command (triggers conda environment installation via require_env)
# --------------------------------------------------------------------------

blue "Step 3: Running claudechic command (E2E test — triggers conda environment installation)..."

# Check if environment already exists
ENV_PREEXISTED=false
if [[ -d "$PROJECT_ROOT/envs/claudechic" ]]; then
    yellow "    Note: claudechic conda environment already exists"
    ENV_PREEXISTED=true
else
    yellow "    Environment not installed - claudechic command will trigger conda environment installation..."
fi

# Create temp files for output capture
OUTPUT_FILE=$(mktemp)
ERROR_FILE=$(mktemp)

# Cleanup function
cleanup() {
    rm -f "$OUTPUT_FILE" "$ERROR_FILE"
}
trap cleanup EXIT

# Set SETUPTOOLS_SCM_PRETEND_VERSION to work around submodule version detection issue
# when installing the claudechic Python package in editable mode (git submodules don't have full .git history)
export SETUPTOOLS_SCM_PRETEND_VERSION="0.0.0+test"

# Run claudechic --help with a long timeout (5 minutes) to allow for:
# 1. require_env to detect missing environment
# 2. conda environment installation (can take several minutes)
# 3. pip install -e for claudechic package
# 4. Actually running --help

blue "    Running: claudechic --help (timeout: 5 minutes)"
echo ""

set +e
# Enable pipefail to capture the exit status of the timeout command (not tee)
# pipefail works in both bash (3.x+) and zsh (5.x+)
set -o pipefail
# Use gtimeout on macOS if available, otherwise fall back to perl-based timeout
# Use tee to show output in CI logs AND capture it for verification
if command -v gtimeout &> /dev/null; then
    gtimeout 300s "$PROJECT_ROOT/commands/claudechic" --help 2>&1 | tee "$OUTPUT_FILE"
elif command -v timeout &> /dev/null; then
    timeout 300s "$PROJECT_ROOT/commands/claudechic" --help 2>&1 | tee "$OUTPUT_FILE"
else
    # Perl-based timeout for macOS without coreutils
    perl -e 'alarm shift; exec @ARGV' 300 "$PROJECT_ROOT/commands/claudechic" --help 2>&1 | tee "$OUTPUT_FILE"
fi
CLAUDECHIC_EXIT=$?
set +o pipefail
set -e

echo ""

# Check if claudechic responded to --help
if [[ $CLAUDECHIC_EXIT -eq 0 ]] || [[ $CLAUDECHIC_EXIT -eq 2 ]]; then
    # Exit 0 = success, Exit 2 = argparse help (normal)
    if [[ -s "$OUTPUT_FILE" ]]; then
        pass "claudechic --help executed successfully"
    else
        fail "claudechic --help produced no output"
    fi
elif [[ $CLAUDECHIC_EXIT -eq 124 ]] || [[ $CLAUDECHIC_EXIT -eq 142 ]]; then
    # 124 = timeout exit code, 142 = SIGALRM (perl timeout)
    fail "claudechic --help timed out after 5 minutes"
    echo "  This may indicate environment installation is hanging"
else
    fail "claudechic --help failed with exit code $CLAUDECHIC_EXIT"
    echo "  Output was shown above"
fi

# --------------------------------------------------------------------------
# Test 3: Verify claudechic conda environment was created by running the command
# --------------------------------------------------------------------------

blue "Step 4: Verifying claudechic conda environment was installed..."

CLAUDECHIC_ENV="$PROJECT_ROOT/envs/claudechic"
if [[ -d "$CLAUDECHIC_ENV" ]]; then
    if [[ "$ENV_PREEXISTED" == "true" ]]; then
        pass "claudechic conda environment exists (was pre-existing)"
    else
        pass "claudechic conda environment was installed by running claudechic command"
    fi
else
    fail "claudechic conda environment not found at $CLAUDECHIC_ENV"
    echo "  The claudechic command should have triggered installation via require_env"
fi

# --------------------------------------------------------------------------
# Step 4b: Show environment contents in CI logs
# --------------------------------------------------------------------------

blue "Step 4b: Listing claudechic conda environment contents..."
if [[ -d "$CLAUDECHIC_ENV" ]]; then
    echo "    Environment directory: $CLAUDECHIC_ENV"
    echo "    Contents (top-level):"
    ls -la "$CLAUDECHIC_ENV/" | head -20 | sed 's/^/    /'
    echo ""
    echo "    Bin directory (first 15 entries):"
    ls "$CLAUDECHIC_ENV/bin/" | head -15 | sed 's/^/    /'
fi

# --------------------------------------------------------------------------
# Test 4: Verify claudechic module can be imported
# --------------------------------------------------------------------------

blue "Step 5: Verifying claudechic Python module imports..."

if [[ -d "$CLAUDECHIC_ENV" ]]; then
    # Use the conda from SLCenv to activate the claudechic conda environment
    source "$PROJECT_ROOT/envs/SLCenv/etc/profile.d/conda.sh"
    conda activate "$CLAUDECHIC_ENV" 2>/dev/null || true

    set +e
    IMPORT_OUTPUT=$(python -c "import claudechic; print(f'claudechic version: {claudechic.__version__}')" 2>&1)
    IMPORT_EXIT=$?
    set -e

    if [[ $IMPORT_EXIT -eq 0 ]]; then
        echo "    $IMPORT_OUTPUT"
        pass "claudechic Python module imports successfully"
    else
        fail "claudechic Python module failed to import"
        echo "    Error: $IMPORT_OUTPUT"
    fi
else
    fail "Cannot test import - claudechic conda environment not found"
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
