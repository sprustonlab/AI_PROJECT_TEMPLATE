"""Ensure all project Python files use explicit encoding with read_text/write_text/open.

On Windows, Python defaults to the system codepage (e.g. cp1252), not UTF-8.
Bare read_text() / write_text() / open() calls silently work on Linux/macOS
but break on Windows for any file with non-ASCII characters.

This test scans all project Python files and fails if any bare calls are found.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories to scan (project code, not vendored/env)
SCAN_DIRS = [
    REPO_ROOT / "tests",
    REPO_ROOT / "hints",
    REPO_ROOT / "template" / "hints",
    REPO_ROOT / "scripts",
    REPO_ROOT / ".claude" / "guardrails",
]

# Files to skip (self-referential test only)
SKIP_FILES = {
    "test_utf8_encoding.py",  # This file — references patterns in detection logic
}


def _collect_python_files() -> list[Path]:
    """Collect all .py files in scan directories."""
    files = []
    for d in SCAN_DIRS:
        if d.is_dir():
            files.extend(
                f for f in sorted(d.rglob("*.py"))
                if f.name not in SKIP_FILES
            )
    return files


def _is_code_line(line: str) -> bool:
    """Return True if the line contains executable code (not a comment or string)."""
    stripped = line.strip()
    if stripped.startswith("#"):
        return False
    if stripped.startswith(('"""', "'''", '"', "'")):
        return False
    # Lines that are building strings (e.g. lines.append("...open..."))
    if "lines.append(" in stripped:
        return False
    return True


def _find_bare_read_text(path: Path) -> list[tuple[int, str]]:
    """Find lines with .read_text() missing encoding parameter."""
    violations = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not _is_code_line(line):
            continue
        if ".read_text()" in line:
            violations.append((i, line.rstrip()))
    return violations


def _find_bare_write_text(path: Path) -> list[tuple[int, str]]:
    """Find lines with .write_text(...) missing encoding parameter.

    Handles multi-line calls by scanning forward from the opening
    .write_text( to the closing paren, checking if 'encoding' appears
    anywhere in that span.
    """
    violations = []
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not _is_code_line(line):
            i += 1
            continue
        if ".write_text(" in line:
            # Collect the full call (may span multiple lines)
            full_call = line
            paren_depth = line.count("(") - line.count(")")
            j = i + 1
            while paren_depth > 0 and j < len(lines):
                full_call += "\n" + lines[j]
                paren_depth += lines[j].count("(") - lines[j].count(")")
                j += 1
            if "encoding" not in full_call:
                violations.append((i + 1, line.rstrip()))
        i += 1
    return violations


def _find_bare_open(path: Path) -> list[tuple[int, str]]:
    """Find lines with open() in text mode missing encoding parameter."""
    violations = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not _is_code_line(line):
            continue
        if re.search(r'\bopen\s*\(', line) and "encoding" not in line:
            # Skip binary mode: open(..., "rb"), open(..., "wb"), etc.
            if re.search(r'''["'][rwax]+b["']''', line):
                continue
            violations.append((i, line.rstrip()))
    return violations


@pytest.fixture(scope="module")
def python_files() -> list[Path]:
    files = _collect_python_files()
    assert files, "No Python files found to scan — check SCAN_DIRS"
    return files


def test_no_bare_read_text(python_files: list[Path]):
    """All .read_text() calls must specify encoding='utf-8'."""
    all_violations: list[str] = []
    for path in python_files:
        violations = _find_bare_read_text(path)
        for lineno, line in violations:
            rel = path.relative_to(REPO_ROOT)
            all_violations.append(f"  {rel}:{lineno}: {line}")

    if all_violations:
        msg = (
            f"Found {len(all_violations)} bare .read_text() call(s) "
            f"missing encoding='utf-8':\n" + "\n".join(all_violations)
        )
        pytest.fail(msg)


def test_no_bare_write_text(python_files: list[Path]):
    """All .write_text() calls must specify encoding='utf-8'."""
    all_violations: list[str] = []
    for path in python_files:
        violations = _find_bare_write_text(path)
        for lineno, line in violations:
            rel = path.relative_to(REPO_ROOT)
            all_violations.append(f"  {rel}:{lineno}: {line}")

    if all_violations:
        msg = (
            f"Found {len(all_violations)} bare .write_text() call(s) "
            f"missing encoding='utf-8':\n" + "\n".join(all_violations)
        )
        pytest.fail(msg)


def test_no_bare_open(python_files: list[Path]):
    """All text-mode open() calls must specify encoding='utf-8'."""
    all_violations: list[str] = []
    for path in python_files:
        violations = _find_bare_open(path)
        for lineno, line in violations:
            rel = path.relative_to(REPO_ROOT)
            all_violations.append(f"  {rel}:{lineno}: {line}")

    if all_violations:
        msg = (
            f"Found {len(all_violations)} bare open() call(s) "
            f"missing encoding='utf-8':\n" + "\n".join(all_violations)
        )
        pytest.fail(msg)
