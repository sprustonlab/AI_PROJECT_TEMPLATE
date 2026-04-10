"""Tests for existing codebase integration via copier.

Creates a fake repo with known files, runs copier with existing_codebase,
and verifies symlink/copy behavior, .claude conflict detection, and
cross-platform gating.

Performance: Module-scoped fixtures share copier generations (symlink + copy)
across all tests, reducing 7 copier generations down to 2.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from filelock import FileLock

from conftest import shared_copier_generation, TEMPLATE_ROOT


def _copier_available():
    try:
        import copier  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark = [
    pytest.mark.skipif(not _copier_available(), reason="copier not installed"),
    pytest.mark.copier,
    pytest.mark.integration,
    pytest.mark.timeout(120),
]


# ---------------------------------------------------------------------------
# Module-scoped shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shared_fake_codebase(tmp_path_factory):
    """Create a fake codebase once, shared across module.

    Uses FileLock + shared basetemp for xdist safety.

    WARNING: Tests may mutate this directory (e.g., write new files).
    If you write files here, use a unique name to avoid cross-test interference.
    """
    root_tmp = tmp_path_factory.getbasetemp().parent
    repo = root_tmp / "integrate_fake_codebase"
    lock = root_tmp / "integrate_fake_codebase.lock"
    marker = root_tmp / "integrate_fake_codebase.ready"

    with FileLock(str(lock)):
        if not marker.exists():
            repo.mkdir(parents=True, exist_ok=True)

            # Source files
            (repo / "src").mkdir(exist_ok=True)
            (repo / "src" / "main.py").write_text(
                "print('hello from existing repo')\n", encoding="utf-8"
            )
            (repo / "src" / "__init__.py").write_text("", encoding="utf-8")

            # pyproject.toml
            (repo / "pyproject.toml").write_text(textwrap.dedent("""\
                [project]
                name = "my-existing-repo"
                version = "0.1.0"
            """), encoding="utf-8")

            # Existing .claude directory with a file
            (repo / ".claude").mkdir(exist_ok=True)
            (repo / ".claude" / "CLAUDE.md").write_text(
                "# Existing project config\n", encoding="utf-8"
            )

            marker.touch()

    return repo


@pytest.fixture(scope="module")
def shared_symlink_project(tmp_path_factory, shared_fake_codebase):
    """Module-scoped copier generation with symlink codebase integration."""
    from copier import run_copy

    root_tmp = tmp_path_factory.getbasetemp().parent
    dest = root_tmp / "integrate_symlink"
    lock = root_tmp / "integrate_symlink.lock"
    marker = root_tmp / "integrate_symlink.ready"

    with FileLock(str(lock)):
        if not marker.exists():
            env = os.environ.copy()
            env["GIT_AUTHOR_NAME"] = "Test"
            env["GIT_AUTHOR_EMAIL"] = "test@test.com"
            env["GIT_COMMITTER_NAME"] = "Test"
            env["GIT_COMMITTER_EMAIL"] = "test@test.com"

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
                data={
                    "project_name": "integrate_symlink",
                    "quick_start": "everything",
                    "use_cluster": False,
                    "existing_codebase": str(shared_fake_codebase),
                    "codebase_link_mode": "symlink",
                },
                defaults=True,
                unsafe=True,
                vcs_ref="HEAD",
            )

            marker.touch()

    return dest


@pytest.fixture(scope="module")
def shared_copy_project(tmp_path_factory, shared_fake_codebase):
    """Module-scoped copier generation with copy codebase integration."""
    from copier import run_copy

    root_tmp = tmp_path_factory.getbasetemp().parent
    dest = root_tmp / "integrate_copy"
    lock = root_tmp / "integrate_copy.lock"
    marker = root_tmp / "integrate_copy.ready"

    with FileLock(str(lock)):
        if not marker.exists():
            env = os.environ.copy()
            env["GIT_AUTHOR_NAME"] = "Test"
            env["GIT_AUTHOR_EMAIL"] = "test@test.com"
            env["GIT_COMMITTER_NAME"] = "Test"
            env["GIT_COMMITTER_EMAIL"] = "test@test.com"

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
                data={
                    "project_name": "integrate_copy",
                    "quick_start": "everything",
                    "use_cluster": False,
                    "existing_codebase": str(shared_fake_codebase),
                    "codebase_link_mode": "copy",
                },
                defaults=True,
                unsafe=True,
                vcs_ref="HEAD",
            )

            marker.touch()

    return dest


# Legacy per-test fixtures (kept for tests that don't use copier)

@pytest.fixture
def fake_codebase(tmp_path):
    """Create a fake codebase with known structure (per-test, for script tests)."""
    repo = tmp_path / "my_existing_repo"
    repo.mkdir()

    # Source files
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("print('hello from existing repo')\n", encoding="utf-8")
    (repo / "src" / "__init__.py").write_text("", encoding="utf-8")

    # pyproject.toml
    (repo / "pyproject.toml").write_text(textwrap.dedent("""\
        [project]
        name = "my-existing-repo"
        version = "0.1.0"
    """), encoding="utf-8")

    # Existing .claude directory with a file
    (repo / ".claude").mkdir()
    (repo / ".claude" / "CLAUDE.md").write_text("# Existing project config\n", encoding="utf-8")

    return repo


# ---------------------------------------------------------------------------
# Symlink tests (Linux/macOS)
# ---------------------------------------------------------------------------


class TestSymlinkMode:
    """Test symlink integration of existing codebase."""

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks unreliable on Windows",
    )
    def test_symlink_created(self, shared_symlink_project, shared_fake_codebase):
        """Symlink mode creates a symlink in repos/ pointing to the codebase."""
        dest = shared_symlink_project
        link = dest / "repos" / shared_fake_codebase.name
        assert link.is_symlink(), f"Expected symlink at {link}"
        assert link.resolve() == shared_fake_codebase.resolve()

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks unreliable on Windows",
    )
    def test_symlinked_files_accessible(self, shared_symlink_project, shared_fake_codebase):
        """Files inside the symlinked repo are accessible."""
        dest = shared_symlink_project
        main_py = dest / "repos" / shared_fake_codebase.name / "src" / "main.py"
        assert main_py.exists()
        assert "hello from existing repo" in main_py.read_text(encoding="utf-8")

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks unreliable on Windows",
    )
    def test_symlink_reflects_changes(self, shared_symlink_project, shared_fake_codebase):
        """Changes to original codebase are reflected through symlink."""
        dest = shared_symlink_project

        # Modify the original (use a unique filename to avoid cross-test interference)
        new_file = shared_fake_codebase / "src" / "symlink_test_file.py"
        new_file.write_text("# new\n", encoding="utf-8")

        # Should be visible through symlink
        linked_file = dest / "repos" / shared_fake_codebase.name / "src" / "symlink_test_file.py"
        assert linked_file.exists()


# ---------------------------------------------------------------------------
# Copy tests (all platforms)
# ---------------------------------------------------------------------------


class TestCopyMode:
    """Test copy integration of existing codebase."""

    def test_copy_created(self, shared_copy_project, shared_fake_codebase):
        """Copy mode creates a real directory (not symlink) in repos/."""
        target = shared_copy_project / "repos" / shared_fake_codebase.name
        assert target.is_dir()
        assert not target.is_symlink(), "Copy mode should NOT create a symlink"

    def test_copied_files_present(self, shared_copy_project, shared_fake_codebase):
        """All files from the original codebase are copied."""
        target = shared_copy_project / "repos" / shared_fake_codebase.name

        assert (target / "src" / "main.py").exists()
        assert "hello from existing repo" in (target / "src" / "main.py").read_text(encoding="utf-8")
        assert (target / "pyproject.toml").exists()

    def test_copy_is_independent(self, shared_copy_project, shared_fake_codebase):
        """Changes to original codebase are NOT reflected in copy."""
        # Modify the original (use a unique filename to avoid cross-test interference)
        new_file = shared_fake_codebase / "src" / "copy_test_file.py"
        new_file.write_text("# new\n", encoding="utf-8")

        # Should NOT be visible in copy (copy was made at fixture time)
        copied_file = shared_copy_project / "repos" / shared_fake_codebase.name / "src" / "copy_test_file.py"
        assert not copied_file.exists()


# ---------------------------------------------------------------------------
# .claude conflict detection tests
# ---------------------------------------------------------------------------


class TestClaudeConflicts:
    """Test .claude directory conflict detection."""

    def test_existing_claude_detected(self, shared_copy_project, shared_fake_codebase):
        """When codebase has .claude/, the script detects it (doesn't crash)."""
        dest = shared_copy_project
        # The project should still be created successfully
        assert (dest / "pixi.toml").exists()
        # The codebase's .claude should be in the copy
        assert (dest / "repos" / shared_fake_codebase.name / ".claude" / "CLAUDE.md").exists()


# ---------------------------------------------------------------------------
# Script direct invocation tests
# ---------------------------------------------------------------------------


class TestIntegrateScript:
    """Test integrate_codebase.py directly (not through copier)."""

    def test_no_args_exits_cleanly(self, tmp_path):
        """Script exits 0 when no codebase path given."""
        # Copy the script to a temp location
        script = Path(__file__).parent.parent / "template" / "scripts" / "integrate_codebase.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=tmp_path,
            capture_output=True,
            encoding="utf-8",
            timeout=10,
        )
        assert result.returncode == 0

    def test_invalid_path_exits_nonzero(self, tmp_path):
        """Script exits 1 when given a nonexistent path."""
        script = Path(__file__).parent.parent / "template" / "scripts" / "integrate_codebase.py"
        result = subprocess.run(
            [sys.executable, str(script), "/nonexistent/path/foobar"],
            cwd=tmp_path,
            capture_output=True,
            encoding="utf-8",
            timeout=10,
        )
        assert result.returncode == 1
        assert "does not exist" in result.stdout or "does not exist" in result.stderr

    def test_copy_mode_direct(self, tmp_path, fake_codebase):
        """Direct invocation with copy mode creates a real copy."""
        script = Path(__file__).parent.parent / "template" / "scripts" / "integrate_codebase.py"
        project_dir = tmp_path / "my_project"
        project_dir.mkdir()
        (project_dir / "repos").mkdir()
        (project_dir / ".claude").mkdir()

        result = subprocess.run(
            [sys.executable, str(script), str(fake_codebase), "copy"],
            cwd=project_dir,
            capture_output=True,
            encoding="utf-8",
            timeout=10,
        )
        assert result.returncode == 0
        assert "Copied" in result.stdout

        target = project_dir / "repos" / fake_codebase.name
        assert target.is_dir()
        assert not target.is_symlink()
        assert (target / "src" / "main.py").exists()

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks unreliable on Windows",
    )
    def test_symlink_mode_direct(self, tmp_path, fake_codebase):
        """Direct invocation with symlink mode creates a symlink."""
        script = Path(__file__).parent.parent / "template" / "scripts" / "integrate_codebase.py"
        project_dir = tmp_path / "my_project"
        project_dir.mkdir()
        (project_dir / "repos").mkdir()

        result = subprocess.run(
            [sys.executable, str(script), str(fake_codebase), "symlink"],
            cwd=project_dir,
            capture_output=True,
            encoding="utf-8",
            timeout=10,
        )
        assert result.returncode == 0
        assert "Linked" in result.stdout

        target = project_dir / "repos" / fake_codebase.name
        assert target.is_symlink()
        assert target.resolve() == fake_codebase.resolve()
