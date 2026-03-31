"""Check that files shared between repo root and template/ stay in sync.

Some files exist in both places:
  - scripts/mine_patterns.py  (repo root copy for dev, template copy for generated projects)
  - .claude/guardrails/generate_hooks.py  (same reason)
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
    "scripts/mine_patterns.py",
    ".claude/guardrails/generate_hooks.py",
    ".claude/guardrails/role_guard.py",
    ".claude/guardrails/README.md",
    ".claude/commands/ao_project_team.md",
    ".claude/commands/init_project.md",
    "AI_agents/project_team/IMPLEMENTER.md",
    "AI_agents/project_team/SKEPTIC.md",
    "AI_agents/project_team/TEST_ENGINEER.md",
    "commands/claudechic",
    "commands/mine-patterns",
]


@pytest.mark.parametrize("rel_path", PAIRED_FILES)
def test_template_file_matches_repo(rel_path: str):
    """Repo root and template/ copies must be byte-identical."""
    repo_file = REPO_ROOT / rel_path
    template_file = TEMPLATE_DIR / rel_path

    assert repo_file.exists(), f"Repo file missing: {rel_path}"
    assert template_file.exists(), f"Template file missing: {rel_path}"

    repo_content = repo_file.read_text()
    template_content = template_file.read_text()

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
