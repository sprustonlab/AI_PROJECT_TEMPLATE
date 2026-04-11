"""Tests for codebase integration intent via copier.

Copier now records only the intent (use_existing_codebase: bool).
Actual integration is handled by the codebase-setup workflow.
These tests verify copier correctly records the intent in .copier-answers.yml.

Previous tests for symlink/copy integration via integrate_codebase.py were
removed when that script was deleted (Phase A: Copier Simplification).
"""
from __future__ import annotations

import pytest

from conftest import shared_copier_generation


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
# Copier intent recording tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def codebase_intent_project(tmp_path_factory):
    """Project generated with use_existing_codebase=true."""
    return shared_copier_generation(tmp_path_factory, "copier_codebase_intent", {
        "project_name": "codebase_intent_test",
        "claudechic_mode": "standard",
        "quick_start": "defaults",
        "use_cluster": False,
        "use_existing_codebase": True,
    })


class TestCodebaseIntent:
    """Verify copier records codebase intent without performing integration."""

    def test_copier_answers_has_intent(self, codebase_intent_project):
        """use_existing_codebase is recorded in .copier-answers.yml."""
        answers_file = codebase_intent_project / ".copier-answers.yml"
        assert answers_file.exists(), ".copier-answers.yml should exist"
        content = answers_file.read_text(encoding="utf-8")
        assert "use_existing_codebase" in content

    def test_repos_dir_empty(self, codebase_intent_project):
        """repos/ is created but empty — workflow handles integration later."""
        repos = codebase_intent_project / "repos"
        if repos.exists():
            # No subdirectories should be created by copier
            subdirs = [p for p in repos.iterdir() if p.is_dir() and not p.name.startswith(".")]
            assert len(subdirs) == 0, "Copier should not integrate codebase — workflow does that"
