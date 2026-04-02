#!/usr/bin/env bash
set -euo pipefail

# teardown_ao_mode.sh — Deactivate team mode by removing the session marker.
#
# Required env vars:
#   CLAUDECHIC_APP_PID or AGENT_SESSION_PID — session PID
# Optional env vars:
#   GUARDRAILS_DIR — override guardrails directory (default: script's own dir)

# --- Resolve PID ---
PID="${AGENT_SESSION_PID:-${CLAUDECHIC_APP_PID:-}}"
if [[ -z "$PID" ]]; then
    echo "ERROR: Neither AGENT_SESSION_PID nor CLAUDECHIC_APP_PID is set." >&2
    exit 1
fi

# --- Resolve guardrails directory ---
GUARDRAILS_DIR="${GUARDRAILS_DIR:-$(dirname "$0")}"

# --- Remove session marker if it exists ---
MARKER="${GUARDRAILS_DIR}/sessions/ao_${PID}"
if [[ -e "$MARKER" ]]; then
    rm "$MARKER"
fi

exit 0
