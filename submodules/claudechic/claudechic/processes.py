"""Background process tracking and detection for Claude agents.

NOTE: Process tracking relies on Unix shell process names (zsh, bash, sh).
On Windows, this module returns empty results since shell processes are
named differently (cmd.exe, powershell.exe).
"""

import re
import sys
from dataclasses import dataclass
from datetime import datetime

import psutil


@dataclass
class BackgroundProcess:
    """A background process being tracked."""

    pid: int
    command: str  # Short description of the command
    start_time: datetime
    output_file: str | None = None  # Path to output file (for background tasks)


def _extract_command(cmdline: list[str]) -> str | None:
    """Extract the user command from a shell cmdline.

    Claude wraps commands like:
      ['/bin/zsh', '-c', '-l', "source ... && eval 'sleep 30' ..."]

    We want to extract just 'sleep 30'.
    """
    # Find the argument containing the actual command (after -c and optional -l)
    cmd_arg = None
    for i, arg in enumerate(cmdline):
        if arg == "-c" and i + 1 < len(cmdline):
            # Next non-flag arg is the command
            for j in range(i + 1, len(cmdline)):
                if not cmdline[j].startswith("-"):
                    cmd_arg = cmdline[j]
                    break
            break

    if not cmd_arg:
        return None

    # Try to extract from eval '...' pattern
    match = re.search(r"eval ['\"](.+?)['\"] \\< /dev/null", cmd_arg)
    if match:
        return match.group(1)

    # Try simpler eval pattern
    match = re.search(r"eval ['\"](.+?)['\"]", cmd_arg)
    if match:
        return match.group(1)

    # Fall back to full command (truncated)
    return cmd_arg[:50] if len(cmd_arg) > 50 else cmd_arg


def get_child_processes(claude_pid: int) -> list[BackgroundProcess]:
    """Get background processes that are children of a claude process.

    Args:
        claude_pid: PID of the claude binary for an agent

    Returns:
        List of BackgroundProcess objects for active shell children.
        Returns empty list on Windows (shell process names differ).
    """
    # Skip on Windows - shell processes have different names (cmd.exe, powershell.exe)
    if sys.platform == "win32":
        return []

    try:
        claude_proc = psutil.Process(claude_pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return []

    processes = []
    for child in claude_proc.children(recursive=True):
        try:
            name = child.name()
            # Only track shell processes (where commands run)
            if name not in ("zsh", "bash", "sh"):
                continue

            status = child.status()
            if status == psutil.STATUS_ZOMBIE:
                continue

            # Extract the command being run
            cmdline = child.cmdline()
            command = _extract_command(cmdline)
            if not command:
                continue

            # Filter out our own monitoring commands
            if command.startswith("ps "):
                continue

            # Get start time
            create_time = datetime.fromtimestamp(child.create_time())

            processes.append(
                BackgroundProcess(
                    pid=child.pid, command=command, start_time=create_time
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return processes


def parse_background_task_output(result: str) -> str | None:
    """Parse output file path from a background Bash task result.

    Background tasks return messages like:
        "Command running in background with ID: abc123. Output is being written to: /path/to/file"

    Returns the output file path, or None if not a background task.
    """
    match = re.search(r"Output is being written to: (.+)$", result)
    return match.group(1) if match else None


def get_claude_pid_from_client(client) -> int | None:
    """Extract the claude process PID from an SDK client.

    Args:
        client: ClaudeSDKClient instance

    Returns:
        PID of the claude subprocess, or None if not available
    """
    try:
        transport = client._transport
        if transport and hasattr(transport, "_process") and transport._process:
            return transport._process.pid
    except Exception:
        pass
    return None
