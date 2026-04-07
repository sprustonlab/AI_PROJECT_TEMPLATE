"""Tests for existing codebase integration via copier.

Creates a fake repo with known files, runs copier with existing_codebase,
and verifies symlink/copy behavior, .claude conflict detection, and
cross-platform gating.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

def _copier_available():
    try:
        import copier  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark = [
    pytest.mark.skipif(not _copier_available(), reason="copier not installed"),
    pytest.mark.copier,
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_codebase(tmp_path):
    """Create a fake codebase with known structure."""
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


@pytest.fixture
def copier_with_codebase(copier_output):
    """Helper that runs copier with existing_codebase and given link_mode."""
    def _run(fake_repo_path, link_mode="symlink"):
        return copier_output({
            "project_name": f"integrate_{link_mode}",
            "quick_start": "everything",
            "use_cluster": False,
            "existing_codebase": str(fake_repo_path),
            "codebase_link_mode": link_mode,
        })
    return _run


# ---------------------------------------------------------------------------
# Symlink tests (Linux/macOS)
# ---------------------------------------------------------------------------


class TestSymlinkMode:
    """Test symlink integration of existing codebase."""

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks unreliable on Windows",
    )
    def test_symlink_created(self, copier_with_codebase, fake_codebase):
        """Symlink mode creates a symlink in repos/ pointing to the codebase."""
        dest = copier_with_codebase(fake_codebase, "symlink")
        link = dest / "repos" / fake_codebase.name
        assert link.is_symlink(), f"Expected symlink at {link}"
        assert link.resolve() == fake_codebase.resolve()

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks unreliable on Windows",
    )
    def test_symlinked_files_accessible(self, copier_with_codebase, fake_codebase):
        """Files inside the symlinked repo are accessible."""
        dest = copier_with_codebase(fake_codebase, "symlink")
        main_py = dest / "repos" / fake_codebase.name / "src" / "main.py"
        assert main_py.exists()
        assert "hello from existing repo" in main_py.read_text(encoding="utf-8")

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks unreliable on Windows",
    )
    def test_symlink_reflects_changes(self, copier_with_codebase, fake_codebase):
        """Changes to original codebase are reflected through symlink."""
        dest = copier_with_codebase(fake_codebase, "symlink")

        # Modify the original
        (fake_codebase / "src" / "new_file.py").write_text("# new\n", encoding="utf-8")

        # Should be visible through symlink
        new_file = dest / "repos" / fake_codebase.name / "src" / "new_file.py"
        assert new_file.exists()


# ---------------------------------------------------------------------------
# Copy tests (all platforms)
# ---------------------------------------------------------------------------


class TestCopyMode:
    """Test copy integration of existing codebase."""

    def test_copy_created(self, copier_with_codebase, fake_codebase):
        """Copy mode creates a real directory (not symlink) in repos/."""
        dest = copier_with_codebase(fake_codebase, "copy")
        target = dest / "repos" / fake_codebase.name
        assert target.is_dir()
        assert not target.is_symlink(), "Copy mode should NOT create a symlink"

    def test_copied_files_present(self, copier_with_codebase, fake_codebase):
        """All files from the original codebase are copied."""
        dest = copier_with_codebase(fake_codebase, "copy")
        target = dest / "repos" / fake_codebase.name

        assert (target / "src" / "main.py").exists()
        assert "hello from existing repo" in (target / "src" / "main.py").read_text(encoding="utf-8")
        assert (target / "pyproject.toml").exists()

    def test_copy_is_independent(self, copier_with_codebase, fake_codebase):
        """Changes to original codebase are NOT reflected in copy."""
        dest = copier_with_codebase(fake_codebase, "copy")

        # Modify the original
        (fake_codebase / "src" / "new_file.py").write_text("# new\n", encoding="utf-8")

        # Should NOT be visible in copy
        new_file = dest / "repos" / fake_codebase.name / "src" / "new_file.py"
        assert not new_file.exists()


# ---------------------------------------------------------------------------
# .claude conflict detection tests
# ---------------------------------------------------------------------------


class TestClaudeConflicts:
    """Test .claude directory conflict detection."""

    def test_existing_claude_detected(self, copier_with_codebase, fake_codebase):
        """When codebase has .claude/, the script detects it (doesn't crash)."""
        # This test just verifies the integration completes without error
        # when there's a .claude conflict
        dest = copier_with_codebase(fake_codebase, "copy")
        # The project should still be created successfully
        assert (dest / "pixi.toml").exists()
        # The codebase's .claude should be in the copy
        assert (dest / "repos" / fake_codebase.name / ".claude" / "CLAUDE.md").exists()


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
