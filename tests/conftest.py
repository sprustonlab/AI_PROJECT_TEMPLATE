"""Shared fixtures for AI_PROJECT_TEMPLATE tests."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from collections.abc import Generator
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from filelock import FileLock

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


def shared_copier_generation(tmp_path_factory, name: str, data: dict) -> Path:
    """Run copier once per unique name, shared across xdist workers via FileLock.

    Uses the same pattern as e2e_project: FileLock + shared basetemp parent.
    Call from module-scoped fixtures to avoid redundant copier generations.
    """
    from copier import run_copy

    root_tmp = tmp_path_factory.getbasetemp().parent
    dest = root_tmp / name
    lock = root_tmp / f"{name}.lock"
    marker = root_tmp / f"{name}.ready"

    with FileLock(str(lock)):
        if not marker.exists():
            # Clean stale output so non-idempotent _tasks (e.g. git clone) succeed
            if dest.exists():
                shutil.rmtree(dest)

            env = os.environ.copy()
            env["GIT_AUTHOR_NAME"] = "Test"
            env["GIT_AUTHOR_EMAIL"] = "test@test.com"
            env["GIT_COMMITTER_NAME"] = "Test"
            env["GIT_COMMITTER_EMAIL"] = "test@test.com"

            dest.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "init"],
                cwd=dest,
                capture_output=True,
                check=True,
                env=env,
            )
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "init"],
                cwd=dest,
                capture_output=True,
                check=True,
                env=env,
            )

            run_copy(
                str(TEMPLATE_ROOT),
                dest,
                data=data,
                defaults=True,
                unsafe=True,
                overwrite=True,
                vcs_ref="HEAD",
            )

            marker.touch()

    return dest


@pytest.fixture
def copier_output(tmp_path):
    """Factory fixture for running copier copy with given data.

    Uses copier's Python API directly for correct type handling
    (booleans, choice values).

    NOTE: Prefer module-scoped fixtures using shared_copier_generation()
    when multiple tests share the same config.  This fixture remains for
    tests that need a unique, isolated generation (e.g. containment tests).
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
            cwd=dest,
            capture_output=True,
            check=True,
            env=env,
        )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=dest,
            capture_output=True,
            check=True,
            env=env,
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


# ---------------------------------------------------------------------------
# E2E fixtures
# ---------------------------------------------------------------------------


async def _empty_async_gen():
    """Empty async generator for mocking receive_response."""
    return
    yield  # noqa: unreachable - makes this an async generator


@pytest.fixture(scope="module")
def e2e_project(tmp_path_factory) -> Generator[Path, None, None]:
    """Copier copy with 'everything' preset into a clean temp directory.

    Module-scoped so the generated project is shared across all test steps.
    Uses shared_copier_generation() for FileLock + xdist safety.
    """
    dest = shared_copier_generation(
        tmp_path_factory,
        "e2e_cross_platform",
        {
            "project_name": "e2e_cross_platform",
            "claudechic_mode": "standard",
            "quick_start": "everything",
            "use_cluster": False,
            "use_guardrails": True,
            "use_project_team": True,
        },
    )

    yield dest

    # No per-worker cleanup — shared resource, pytest cleans basetemp


@pytest.fixture
def mock_sdk_e2e():
    """Mock SDK to prevent real Claude connections. 4 patches only.

    Patches both app.py and agent.py imports since agents create their own clients.
    Also patches FileIndex to avoid subprocess transport leaks during test cleanup.
    Disables analytics to avoid httpx connection leaks.
    """
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.query = AsyncMock()
    mock_client.interrupt = AsyncMock()
    mock_client.get_server_info = AsyncMock(return_value={"commands": [], "models": []})
    mock_client.set_permission_mode = AsyncMock()
    mock_client.receive_response = lambda: _empty_async_gen()
    mock_client._transport = None

    mock_file_index = MagicMock()
    mock_file_index.refresh = AsyncMock()
    mock_file_index.files = []

    with ExitStack() as stack:
        # Patch 1+2: SDK client in both app.py and agent.py
        stack.enter_context(
            patch("claudechic.app.ClaudeSDKClient", return_value=mock_client)
        )
        stack.enter_context(
            patch("claudechic.agent.ClaudeSDKClient", return_value=mock_client)
        )
        # Patch 3: FileIndex (prevents subprocess leaks)
        stack.enter_context(
            patch("claudechic.app.FileIndex", return_value=mock_file_index)
        )
        stack.enter_context(
            patch("claudechic.agent.FileIndex", return_value=mock_file_index)
        )
        # Patch 4: Analytics (prevents httpx connections)
        stack.enter_context(
            patch.dict("claudechic.analytics.CONFIG", {"analytics": {"enabled": False}})
        )
        yield mock_client


@pytest.fixture
def fast_sleep():
    """Patch asyncio.sleep to resolve immediately (no real delays)."""
    original = asyncio.sleep

    async def _fast(delay, *a, **kw):
        await original(0)

    with patch.object(asyncio, "sleep", side_effect=_fast):
        yield
