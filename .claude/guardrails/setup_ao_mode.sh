#!/usr/bin/env bash
set -euo pipefail

# setup_ao_mode.sh — Activate team mode by creating a session marker.
#
# Required env vars:
#   CLAUDECHIC_APP_PID or AGENT_SESSION_PID — session PID
#   CLAUDE_AGENT_NAME — name of the coordinator agent
# Optional env vars:
#   GUARDRAILS_DIR — override guardrails directory (default: script's own dir)

# --- Resolve PID ---
PID="${AGENT_SESSION_PID:-${CLAUDECHIC_APP_PID:-}}"
if [[ -z "$PID" ]]; then
    echo "ERROR: Neither AGENT_SESSION_PID nor CLAUDECHIC_APP_PID is set." >&2
    exit 1
fi

# --- Resolve agent name ---
if [[ -z "${CLAUDE_AGENT_NAME:-}" ]]; then
    echo "ERROR: CLAUDE_AGENT_NAME is not set." >&2
    exit 1
fi

# --- Resolve guardrails directory ---
GUARDRAILS_DIR="${GUARDRAILS_DIR:-$(dirname "$0")}"

# --- Create sessions directory ---
mkdir -p "${GUARDRAILS_DIR}/sessions"

# --- Check for existing marker (double-activation guard) ---
MARKER="${GUARDRAILS_DIR}/sessions/ao_${PID}"
if [[ -e "$MARKER" ]]; then
    echo "ERROR: Session marker already exists at ${MARKER}. Team mode is already active for PID ${PID}." >&2
    exit 1
fi

# --- Write session marker as JSON ---
printf '{"coordinator": "%s"}' "$CLAUDE_AGENT_NAME" > "$MARKER"

exit 0
