"""Bug #15 -- Hardcoded /bin/bash in _run_ssh().

PRIMARY test: call _run_ssh() with a real command, assert it works.
This passes on Linux (/bin/bash exists) and would FAIL on Windows CI
(FileNotFoundError because /bin/bash doesn't exist) without the fix.

SECONDARY tests: monkeypatch-based checks for platform guard details,
encoding, and SSH argv list.

Parallel-safe: no shared mutable state, uses monkeypatch for platform.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import _cluster module
# ---------------------------------------------------------------------------

TEMPLATE_MCP = Path(__file__).resolve().parent.parent / "template" / "mcp_tools"


def _import_module(name: str, filepath: Path):
    """Import a module from file path, registering in sys.modules."""
    module_name = f"mcp_tools.{name}"
    if module_name in sys.modules:
        del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    assert spec and spec.loader, f"Cannot load {filepath}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


_cluster_mod = _import_module("_cluster", TEMPLATE_MCP / "_cluster.py")


# ---------------------------------------------------------------------------
# PRIMARY test: real behavioral test -- call _run_ssh(), assert it works
# ---------------------------------------------------------------------------


class TestRunSSHBehavioral:
    """Call _run_ssh() for real on ALL platforms.

    - Linux: PASS (/bin/bash exists, commands work)
    - Windows WITHOUT fix: FAIL (FileNotFoundError -- /bin/bash hardcoded)
    - Windows WITH fix: PASS (platform guard omits /bin/bash)
    """

    def test_local_echo_returns_output(self):
        """_run_ssh('echo hello', ssh_target='') runs locally and returns output.

        This is the core TDD test for Bug #15. Before the fix, Windows CI
        would crash with FileNotFoundError because /bin/bash doesn't exist.
        The platform guard makes it work on both Linux and Windows.
        """
        stdout, stderr, rc = _cluster_mod._run_ssh("echo hello", ssh_target="")
        assert rc == 0, f"Expected rc=0, got {rc}. stderr: {stderr}"
        assert "hello" in stdout

    def test_local_command_captures_stderr(self):
        """_run_ssh captures stderr from a real command."""
        # Windows cmd.exe uses different redirect syntax
        if sys.platform == "win32":
            cmd = "echo oops 1>&2"
        else:
            cmd = "echo oops >&2"
        stdout, stderr, rc = _cluster_mod._run_ssh(cmd, ssh_target="")
        assert rc == 0
        assert "oops" in stderr

    def test_local_nonzero_exit_code(self):
        """_run_ssh returns nonzero exit code for failing commands."""
        if sys.platform == "win32":
            cmd = "cmd /c exit 42"
        else:
            cmd = "exit 42"
        stdout, stderr, rc = _cluster_mod._run_ssh(cmd, ssh_target="")
        assert rc == 42


# ---------------------------------------------------------------------------
# SECONDARY: encoding="utf-8" is passed to subprocess.run
# ---------------------------------------------------------------------------


class TestRunSSHEncoding:
    """_run_ssh() must pass encoding='utf-8' to subprocess.run."""

    @patch("subprocess.run")
    def test_encoding_utf8_passed(self, mock_run):
        """subprocess.run must receive encoding='utf-8'."""
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)
        _cluster_mod._run_ssh("echo hello", ssh_target="")
        call_kwargs = mock_run.call_args
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
        assert kwargs.get("encoding") == "utf-8", (
            f"subprocess.run must be called with encoding='utf-8', got kwargs: {kwargs}"
        )


# ---------------------------------------------------------------------------
# SECONDARY: platform guard for /bin/bash
# ---------------------------------------------------------------------------


class TestRunSSHNoBashOnWindows:
    """_run_ssh() must not use /bin/bash executable on Windows."""

    @patch("subprocess.run")
    def test_no_bin_bash_on_win32(self, mock_run, monkeypatch):
        """On win32, executable must NOT be /bin/bash."""
        monkeypatch.setattr(sys, "platform", "win32")
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)

        _cluster_mod._run_ssh("echo hello", ssh_target="")

        call_kwargs = mock_run.call_args
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
        executable = kwargs.get("executable")
        assert executable != "/bin/bash", (
            f"On Windows, executable must not be /bin/bash, got: {executable!r}"
        )

    @patch("subprocess.run")
    def test_bin_bash_on_linux(self, mock_run, monkeypatch):
        """On linux, /bin/bash is used as the shell executable."""
        monkeypatch.setattr(sys, "platform", "linux")
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)

        _cluster_mod._run_ssh("echo hello", ssh_target="")

        call_kwargs = mock_run.call_args
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
        executable = kwargs.get("executable")
        assert executable == "/bin/bash"


# ---------------------------------------------------------------------------
# SECONDARY: SSH execution uses argv list, not shell string
# ---------------------------------------------------------------------------


class TestRunSSHArgvList:
    """SSH execution should use argv list for safety."""

    @patch("subprocess.run")
    @patch("os.makedirs")
    def test_ssh_uses_list_args(self, mock_makedirs, mock_run, monkeypatch):
        """SSH path should pass args as list, not shell=True string."""
        monkeypatch.setattr(sys, "platform", "linux")
        mock_run.return_value = MagicMock(stdout="ok", stderr="", returncode=0)

        _cluster_mod._run_ssh(
            "bjobs -w",
            ssh_target="login.example.com",
            profile="/misc/lsf/conf/profile.lsf",
        )

        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args.kwargs.get("args")
        assert isinstance(cmd, list), f"SSH should use argv list, got {type(cmd)}: {cmd}"
        assert cmd[0] == "ssh"
        assert "login.example.com" in cmd
