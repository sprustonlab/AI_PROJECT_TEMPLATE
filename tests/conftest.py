"""Shared fixtures for AI_PROJECT_TEMPLATE tests."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Root of the template repo
TEMPLATE_ROOT = Path(__file__).resolve().parent.parent

# Path to discover_mcp_tools
CLAUDECHIC_MCP = TEMPLATE_ROOT / "submodules" / "claudechic" / "claudechic" / "mcp.py"


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a clean temporary directory."""
    return tmp_path


@pytest.fixture
def mcp_tools_dir(tmp_path):
    """Provide a clean mcp_tools/ directory for discovery tests."""
    d = tmp_path / "mcp_tools"
    d.mkdir()
    return d


@pytest.fixture
def copier_output(tmp_path):
    """Factory fixture for running copier copy with given data.

    Uses copier's Python API directly for correct type handling
    (booleans, choice values).
    """

    def _run(data: dict, dest_name: str = "test_project"):
        from copier import run_copy

        dest = tmp_path / dest_name

        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "Test"
        env["GIT_AUTHOR_EMAIL"] = "test@test.com"
        env["GIT_COMMITTER_NAME"] = "Test"
        env["GIT_COMMITTER_EMAIL"] = "test@test.com"

        # Initialize a git repo in dest first (copier requires it)
        dest.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init"],
            cwd=dest, capture_output=True, check=True, env=env,
        )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=dest, capture_output=True, check=True, env=env,
        )

        run_copy(
            str(TEMPLATE_ROOT),
            dest,
            data=data,
            defaults=True,
            unsafe=True,
            vcs_ref="HEAD",
        )

        return dest

    return _run
