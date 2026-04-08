"""Tests for Windows crash fixes (silent TUI exit).

Covers:
- P0: _is_process_alive() cross-platform correctness
- P0: _sigint_fallback() uses terminate on Windows, os.kill on Unix
- P1: _drain_next_message() CLIConnectionError handling (TOCTOU race)
- P2: Global exception hooks installed in __main__
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.timeout(30)]

# Trigger the full claudechic import chain via app (avoids circular import
# when importing agent.py directly).
from claudechic.app import ChatApp  # noqa: F401, E402
from claudechic.agent import Agent  # noqa: E402


# ---------------------------------------------------------------------------
# Fix 1: _is_process_alive() correctness (cross-platform)
# ---------------------------------------------------------------------------


class TestIsProcessAlive:
    """Test Agent._is_process_alive() with real subprocesses."""

    def test_alive_process_returns_true(self):
        """A running subprocess is detected as alive."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            assert Agent._is_process_alive(proc.pid) is True
        finally:
            proc.terminate()
            proc.wait()

    def test_dead_process_returns_false(self):
        """A terminated subprocess is detected as dead.

        On Windows, OpenProcess can succeed briefly for recently-exited
        processes because the kernel handle isn't fully cleaned up yet.
        We retry with a short timeout to tolerate this.
        """
        import time

        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc.wait()

        # Retry for up to 2 seconds to handle Windows handle cleanup delay
        deadline = time.monotonic() + 2.0
        alive = True
        while time.monotonic() < deadline:
            alive = Agent._is_process_alive(proc.pid)
            if not alive:
                break
            time.sleep(0.1)

        assert alive is False

    def test_nonexistent_pid_returns_false(self):
        """A PID that was never valid returns False."""
        assert Agent._is_process_alive(4_194_304) is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific ctypes path")
    def test_windows_uses_ctypes(self):
        """On Windows, _is_process_alive uses ctypes.windll.kernel32."""
        mock_kernel32 = MagicMock()
        mock_kernel32.OpenProcess.return_value = 0  # not found
        mock_windll = MagicMock()
        mock_windll.kernel32 = mock_kernel32

        with patch("ctypes.windll", mock_windll):
            result = Agent._is_process_alive(99999)

        mock_kernel32.OpenProcess.assert_called_once_with(0x1000, False, 99999)
        assert result is False

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific os.kill path")
    def test_unix_uses_os_kill_signal_zero(self):
        """On Unix, _is_process_alive uses os.kill(pid, 0)."""
        with patch("os.kill", side_effect=ProcessLookupError) as mock_kill:
            result = Agent._is_process_alive(99999)

        mock_kill.assert_called_once_with(99999, 0)
        assert result is False


# ---------------------------------------------------------------------------
# Fix 2: _sigint_fallback() platform-specific behaviour
# ---------------------------------------------------------------------------


class TestSigintFallback:
    """Test that _sigint_fallback uses the correct mechanism per platform."""

    def _make_agent_with_process(self):
        """Create a minimal Agent with a mock SDK client + subprocess."""
        agent = Agent(name="test", cwd=Path("."))

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None  # still running

        mock_transport = MagicMock()
        mock_transport._process = mock_process

        mock_query = MagicMock()
        mock_query.transport = mock_transport

        mock_client = MagicMock()
        mock_client._query = mock_query

        agent.client = mock_client
        return agent, mock_process

    def test_windows_calls_terminate(self):
        """On Windows, _sigint_fallback calls process.terminate()."""
        agent, mock_process = self._make_agent_with_process()

        with patch.object(sys, "platform", "win32"):
            agent._sigint_fallback()

        mock_process.terminate.assert_called_once()

    def test_unix_calls_os_kill_sigint(self):
        """On Unix, _sigint_fallback calls os.kill(pid, SIGINT)."""
        import signal

        agent, mock_process = self._make_agent_with_process()

        with patch.object(sys, "platform", "linux"), \
             patch("os.kill") as mock_kill:
            agent._sigint_fallback()

        mock_kill.assert_called_once_with(12345, signal.SIGINT)

    def test_no_client_is_noop(self):
        """If there's no client, _sigint_fallback does nothing."""
        agent = Agent(name="test", cwd=Path("."))
        agent.client = None
        # Should not raise
        agent._sigint_fallback()

    def test_dead_process_is_noop(self):
        """If the process already exited (returncode set), does nothing."""
        agent, mock_process = self._make_agent_with_process()
        mock_process.returncode = 0  # already exited

        agent._sigint_fallback()
        mock_process.terminate.assert_not_called()


# ---------------------------------------------------------------------------
# Fix 3: _drain_next_message() CLIConnectionError handling
# ---------------------------------------------------------------------------


class TestDrainNextMessageErrorHandling:
    """Test that _drain_next_message catches CLIConnectionError and reconnects."""

    def _make_drainable_agent(self):
        """Create an Agent with a queued message and mock observer."""
        agent = Agent(name="test-drain", cwd=Path("."))

        mock_observer = MagicMock()
        agent.observer = mock_observer

        agent._pending_messages = [("hello world", None)]

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.returncode = None

        mock_transport = MagicMock()
        mock_transport._process = mock_process

        mock_query = MagicMock()
        mock_query.transport = mock_transport

        mock_client = MagicMock()
        mock_client._query = mock_query

        agent.client = mock_client

        return agent, mock_observer

    def test_dead_transport_triggers_reconnect(self):
        """When transport is dead, on_connection_lost is called and messages stay queued."""
        agent, mock_observer = self._make_drainable_agent()

        # Make transport look dead
        agent.client._query.transport._process.returncode = 1

        agent._drain_next_message()

        mock_observer.on_connection_lost.assert_called_once_with(agent)
        assert len(agent._pending_messages) == 1

    def test_cli_connection_error_requeues_and_reconnects(self):
        """CLIConnectionError during _start_response re-queues and triggers reconnect."""
        from claude_agent_sdk import CLIConnectionError

        agent, mock_observer = self._make_drainable_agent()

        with patch.object(agent, "_start_response", side_effect=CLIConnectionError("dead")):
            agent._drain_next_message()

        # Message should be re-queued
        assert len(agent._pending_messages) == 1
        assert agent._pending_messages[0] == ("hello world", None)

        # Reconnection triggered
        mock_observer.on_connection_lost.assert_called_once_with(agent)

    def test_empty_queue_is_noop(self):
        """When no messages are queued, _drain_next_message does nothing."""
        agent = Agent(name="test", cwd=Path("."))
        agent._pending_messages = []
        agent.observer = MagicMock()

        agent._drain_next_message()

        agent.observer.on_connection_lost.assert_not_called()

    def test_successful_drain_pops_message(self):
        """Normal drain pops the message and calls _start_response."""
        agent, mock_observer = self._make_drainable_agent()

        with patch.object(agent, "_start_response") as mock_start:
            agent._drain_next_message()

        mock_start.assert_called_once_with("hello world", display_as=None)
        assert len(agent._pending_messages) == 0
        mock_observer.on_connection_lost.assert_not_called()


# ---------------------------------------------------------------------------
# Fix 4: Error hooks installed in __main__
# ---------------------------------------------------------------------------


class TestErrorHooksInstalled:
    """Verify __main__ installs global exception hooks."""

    def test_sys_excepthook_is_custom(self):
        """sys.excepthook should be set to claudechic's custom handler."""
        import claudechic.__main__ as main_mod  # noqa: F401

        assert sys.excepthook is not sys.__excepthook__
        assert sys.excepthook.__name__ == "_excepthook"

    def test_threading_excepthook_is_custom(self):
        """threading.excepthook should be set to claudechic's custom handler."""
        import threading

        import claudechic.__main__ as main_mod  # noqa: F401

        assert threading.excepthook.__name__ == "_threading_excepthook"

    def test_excepthook_logs_non_keyboard_interrupt(self):
        """The custom excepthook logs critical for non-KeyboardInterrupt."""
        from claudechic.__main__ import _excepthook

        with patch("claudechic.__main__.logger") as mock_logger:
            try:
                raise ValueError("test error")
            except ValueError:
                exc_info = sys.exc_info()
                _excepthook(*exc_info)

        mock_logger.critical.assert_called_once()
        call_args = mock_logger.critical.call_args
        assert "Unhandled exception" in call_args[0][0]

    def test_excepthook_skips_keyboard_interrupt(self):
        """The custom excepthook passes through KeyboardInterrupt."""
        from claudechic.__main__ import _excepthook

        with patch("claudechic.__main__.logger") as mock_logger, \
             patch("sys.__excepthook__"):
            _excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)

        mock_logger.critical.assert_not_called()
