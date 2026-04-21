"""Ensure workflow YAML advance-check commands are cross-platform.

On Windows, Unix commands like ``ls``, ``grep``, ``cat`` do not exist.
Advance checks using ``command-output-check`` must use cross-platform
alternatives (e.g. ``python -c "import glob; ..."``) so workflows run
on all three target platforms (linux-64, osx-arm64, win-64).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_DIRS = [
    REPO_ROOT / "workflows",
    REPO_ROOT / "template" / "workflows",
]

# Unix-only commands that break on Windows
UNIX_ONLY_PATTERNS = [
    (re.compile(r"\bls\s"), "ls"),
    (re.compile(r"\bcat\s"), "cat"),
    (re.compile(r"\bgrep\s"), "grep"),
    (re.compile(r"\bhead\s"), "head"),
    (re.compile(r"\btail\s"), "tail"),
]


def _collect_yaml_files() -> list[Path]:
    """Collect all .yaml files in scan directories."""
    files = []
    for d in SCAN_DIRS:
        if d.is_dir():
            files.extend(sorted(d.rglob("*.yaml")))
    return files


def _find_unix_commands(path: Path) -> list[tuple[str, str, str]]:
    """Find Unix-only commands in command-output-check advance checks.

    Returns list of (check_command, unix_cmd_name, phase_id) tuples.
    """
    violations = []
    content = path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        return violations

    for phase in data.get("phases", []):
        phase_id = phase.get("id", "?")
        for check in phase.get("advance_checks", []):
            if check.get("type") != "command-output-check":
                continue
            command = check.get("command", "")
            for pattern, cmd_name in UNIX_ONLY_PATTERNS:
                if pattern.search(command):
                    violations.append((command, cmd_name, phase_id))
    return violations


@pytest.fixture(scope="module")
def yaml_files() -> list[Path]:
    files = _collect_yaml_files()
    assert files, "No YAML files found to scan -- check SCAN_DIRS"
    return files


def test_no_unix_only_commands_in_advance_checks(yaml_files: list[Path]) -> None:
    """All command-output-check commands must be cross-platform."""
    all_violations: list[str] = []
    for path in yaml_files:
        violations = _find_unix_commands(path)
        for command, cmd_name, phase_id in violations:
            rel = path.relative_to(REPO_ROOT)
            all_violations.append(
                f"  {rel} phase={phase_id}: `{cmd_name}` in: {command}"
            )

    if all_violations:
        msg = (
            f"Found {len(all_violations)} Unix-only command(s) in advance checks "
            f"(will fail on Windows):\n" + "\n".join(all_violations)
            + "\n\nUse cross-platform alternatives like: "
            'python -c "import glob; print(\'\\n\'.join(glob.glob(\'pattern\')))"'
        )
        pytest.fail(msg)
