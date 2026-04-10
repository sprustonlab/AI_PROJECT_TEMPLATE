"""Check that files shared between repo root and template/ stay in sync.

Some files exist in both places:
  - scripts/mine_patterns.py  (repo root copy for dev, template copy for generated projects)
  - etc.

This test fails if any paired file drifts, preventing silent staleness.
"""
from __future__ import annotations

import difflib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "template"

# Files that must be identical between repo root and template/.
# Add new pairs here when you copy a file into the template.
# To add a pair: list the path relative to repo root.
# To exclude a file that's intentionally different between repo and template,
# don't add it here. Example: commands/claudechic differs by design
# (bash wrapper in repo, Python with submodule init in template).
PAIRED_FILES = [
    # Scripts and commands
    "scripts/mine_patterns.py",
    "commands/claudechic",
    "commands/mine-patterns",

    # Global config
    "global/rules.yaml",

    # Workflow YAMLs
    "workflows/project_team/project_team.yaml",
    "workflows/project_team/README.md",
    "workflows/project_team/project_types.md",

    # Core role identity files
    "workflows/project_team/coordinator/identity.md",
    "workflows/project_team/composability/identity.md",
    "workflows/project_team/implementer/identity.md",
    "workflows/project_team/skeptic/identity.md",
    "workflows/project_team/terminology/identity.md",
    "workflows/project_team/user_alignment/identity.md",
    "workflows/project_team/test_engineer/identity.md",

    # Specialist role identity files
    "workflows/project_team/researcher/identity.md",
    "workflows/project_team/lab_notebook/identity.md",
    "workflows/project_team/ui_designer/identity.md",
    "workflows/project_team/git_setup/identity.md",
    "workflows/project_team/binary_portability/identity.md",
    "workflows/project_team/memory_layout/identity.md",
    "workflows/project_team/project_integrator/identity.md",
    "workflows/project_team/sync_coordinator/identity.md",

    # Coordinator phase files
    "workflows/project_team/coordinator/implementation.md",
    "workflows/project_team/coordinator/leadership.md",
    "workflows/project_team/coordinator/setup.md",
    "workflows/project_team/coordinator/signoff.md",
    "workflows/project_team/coordinator/specification.md",
    "workflows/project_team/coordinator/testing.md",
    "workflows/project_team/coordinator/vision.md",

    # Tutorial workflow files
    "workflows/tutorial_extending/tutorial_extending.yaml",
    "workflows/tutorial_extending/learner/identity.md",
]


@pytest.mark.parametrize("rel_path", PAIRED_FILES)
def test_template_file_matches_repo(rel_path: str):
    """Repo root and template/ copies must be byte-identical."""
    repo_file = REPO_ROOT / rel_path
    template_file = TEMPLATE_DIR / rel_path

    assert repo_file.exists(), f"Repo file missing: {rel_path}"
    assert template_file.exists(), f"Template file missing: {rel_path}"

    repo_content = repo_file.read_text(encoding="utf-8")
    template_content = template_file.read_text(encoding="utf-8")

    if repo_content != template_content:
        diff = difflib.unified_diff(
            repo_content.splitlines(keepends=True),
            template_content.splitlines(keepends=True),
            fromfile=f"repo/{rel_path}",
            tofile=f"template/{rel_path}",
            n=3,
        )
        diff_text = "".join(list(diff)[:50])  # First 50 lines of diff
        pytest.fail(
            f"File drift detected: {rel_path}\n"
            f"Repo root and template/ copies differ.\n\n"
            f"{diff_text}"
        )
