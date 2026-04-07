"""Intent-based tests for team mode activation/deactivation scripts.

Red-phase TDD: these tests prove the team mode activation chain is broken
because setup_ao_mode.sh and teardown_ao_mode.sh do not yet exist in the
generated project.

Verifies:
- setup_ao_mode.sh creates a session marker with valid JSON
- teardown_ao_mode.sh removes the session marker
- Double activation with the same PID is rejected

Requires: copier (pip install copier).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


def _copier_available():
    try:
        import copier  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark = [
    pytest.mark.skipif(
        not _copier_available(),
        reason="copier not installed",
    ),
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="bash shell scripts not supported on Windows CI",
    ),
    pytest.mark.copier,
]

# Shared copier data for all tests in this module
_COPIER_DATA = {
    "project_name": "team_activation_test",
    "quick_start": "everything",
    "use_cluster": False,
}


class TestTeamModeActivation:
    """Tests that team mode can be activated and deactivated via shell scripts."""

    def test_setup_ao_mode_creates_session_marker(self, copier_output):
        """setup_ao_mode.sh must create a session marker with coordinator JSON.

        Expected to FAIL: setup_ao_mode.sh does not exist in the generated project.
        """
        dest = copier_output(_COPIER_DATA)
        setup_script = dest / ".claude" / "guardrails" / "setup_ao_mode.sh"

        assert setup_script.exists(), (
            "setup_ao_mode.sh not found in generated project at "
            f"{setup_script.relative_to(dest)} — script referenced in README and "
            "role_guard.py but never created"
        )

        env = os.environ.copy()
        env["CLAUDE_AGENT_NAME"] = "Coordinator"
        env["CLAUDECHIC_APP_PID"] = "12345"

        result = subprocess.run(
            ["bash", str(setup_script)],
            cwd=dest,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, (
            f"setup_ao_mode.sh exited {result.returncode}: {result.stderr}"
        )

        marker = dest / ".claude" / "guardrails" / "sessions" / "ao_12345"
        assert marker.exists(), (
            "Session marker not created at .claude/guardrails/sessions/ao_12345"
        )

        marker_data = json.loads(marker.read_text(encoding="utf-8"))
        assert marker_data == {"coordinator": "Coordinator"}, (
            f"Session marker JSON mismatch: expected "
            f'{{"coordinator": "Coordinator"}}, got {marker_data}'
        )

    def test_teardown_ao_mode_removes_marker(self, copier_output):
        """teardown_ao_mode.sh must delete the session marker.

        Expected to FAIL: teardown_ao_mode.sh does not exist in the generated project.
        """
        dest = copier_output(_COPIER_DATA)
        setup_script = dest / ".claude" / "guardrails" / "setup_ao_mode.sh"
        teardown_script = dest / ".claude" / "guardrails" / "teardown_ao_mode.sh"

        # Both scripts must exist before we can test teardown
        assert setup_script.exists(), (
            "setup_ao_mode.sh not found — cannot test teardown without setup"
        )
        assert teardown_script.exists(), (
            "teardown_ao_mode.sh not found in generated project at "
            f"{teardown_script.relative_to(dest)} — script referenced in README and "
            "role_guard.py but never created"
        )

        env = os.environ.copy()
        env["CLAUDE_AGENT_NAME"] = "Coordinator"
        env["CLAUDECHIC_APP_PID"] = "12345"

        # Activate team mode first
        setup_result = subprocess.run(
            ["bash", str(setup_script)],
            cwd=dest,
            capture_output=True,
            text=True,
            env=env,
        )
        assert setup_result.returncode == 0, (
            f"setup_ao_mode.sh failed: {setup_result.stderr}"
        )

        marker = dest / ".claude" / "guardrails" / "sessions" / "ao_12345"
        assert marker.exists(), "Session marker not created by setup — cannot test teardown"

        # Teardown
        teardown_result = subprocess.run(
            ["bash", str(teardown_script)],
            cwd=dest,
            capture_output=True,
            text=True,
            env=env,
        )
        assert teardown_result.returncode == 0, (
            f"teardown_ao_mode.sh exited {teardown_result.returncode}: "
            f"{teardown_result.stderr}"
        )

        assert not marker.exists(), (
            "Session marker still exists after teardown — "
            "teardown_ao_mode.sh must delete .claude/guardrails/sessions/ao_12345"
        )

    def test_setup_ao_mode_rejects_double_activation(self, copier_output):
        """Running setup_ao_mode.sh twice with the same PID must fail.

        Expected to FAIL: setup_ao_mode.sh does not exist in the generated project.
        """
        dest = copier_output(_COPIER_DATA)
        setup_script = dest / ".claude" / "guardrails" / "setup_ao_mode.sh"

        assert setup_script.exists(), (
            "setup_ao_mode.sh not found — cannot test double-activation guard"
        )

        env = os.environ.copy()
        env["CLAUDE_AGENT_NAME"] = "Coordinator"
        env["CLAUDECHIC_APP_PID"] = "99999"

        # First activation — should succeed
        first = subprocess.run(
            ["bash", str(setup_script)],
            cwd=dest,
            capture_output=True,
            text=True,
            env=env,
        )
        assert first.returncode == 0, (
            f"First setup_ao_mode.sh call failed: {first.stderr}"
        )

        # Second activation with same PID — must fail
        second = subprocess.run(
            ["bash", str(setup_script)],
            cwd=dest,
            capture_output=True,
            text=True,
            env=env,
        )
        assert second.returncode != 0, (
            "Second setup_ao_mode.sh call should fail with non-zero exit when "
            "a session marker already exists for PID 99999, but it exited 0"
        )
