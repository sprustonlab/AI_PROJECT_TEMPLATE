"""Tests for copier template generation with various configurations.

Verifies:
- Standard vs developer claudechic mode in pixi.toml
- Cluster scheduler file inclusion/exclusion (LSF, SLURM, none)
- _exclude rules: docs/, .ao_project_team/, submodules/, tests/ never in output

Requires: copier (pip install copier). Tests are skipped if copier is not installed.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest
from pathlib import Path

def _copier_available():
    try:
        import copier  # noqa: F401
        return True
    except ImportError:
        return False


# Skip entire module if copier is not available
pytestmark = [
    pytest.mark.skipif(
        not _copier_available(),
        reason="copier not installed",
    ),
    pytest.mark.copier,
]


# ---------------------------------------------------------------------------
# claudechic mode tests
# ---------------------------------------------------------------------------


class TestClaudechicMode:
    """Test standard vs developer mode in pixi.toml."""

    def test_standard_mode_has_git_url(self, copier_output):
        """Standard mode → pixi.toml has git URL dependency."""
        dest = copier_output({
            "project_name": "std_project",
            "claudechic_mode": "standard",
            "use_cluster": False,
        })
        pixi_toml = dest / "pixi.toml"
        assert pixi_toml.exists(), "pixi.toml not generated"
        content = pixi_toml.read_text()
        assert 'git = "https://github.com/sprustonlab/claudechic"' in content
        assert "editable" not in content

    def test_developer_mode_has_editable_path(self, copier_output):
        """Developer mode → pixi.toml has editable path dependency."""
        dest = copier_output({
            "project_name": "dev_project",
            "claudechic_mode": "developer",
            "use_cluster": False,
        })
        pixi_toml = dest / "pixi.toml"
        assert pixi_toml.exists(), "pixi.toml not generated"
        content = pixi_toml.read_text()
        assert 'path = "submodules/claudechic"' in content
        assert "editable = true" in content
        assert "github.com/sprustonlab/claudechic" not in content


# ---------------------------------------------------------------------------
# Cluster scheduler tests
# ---------------------------------------------------------------------------


class TestClusterScheduler:
    """Test conditional cluster file inclusion."""

    def test_lsf_scheduler(self, copier_output):
        """use_cluster=true + lsf → lsf.py present, slurm.py absent."""
        dest = copier_output({
            "project_name": "lsf_project",
            "claudechic_mode": "standard",
            "use_cluster": True,
            "cluster_scheduler": "lsf",
            "cluster_ssh_target": "login1.example.com",
        })
        mcp = dest / "mcp_tools"
        assert (mcp / "lsf.py").exists(), "lsf.py should be present"
        assert (mcp / "lsf.yaml").exists(), "lsf.yaml should be present"
        assert (mcp / "_cluster.py").exists(), "_cluster.py should be present"
        assert not (mcp / "slurm.py").exists(), "slurm.py should NOT be present"
        assert not (mcp / "slurm.yaml").exists(), "slurm.yaml should NOT be present"

    def test_slurm_scheduler(self, copier_output):
        """use_cluster=true + slurm → slurm.py present, lsf.py absent."""
        dest = copier_output({
            "project_name": "slurm_project",
            "claudechic_mode": "standard",
            "use_cluster": True,
            "cluster_scheduler": "slurm",
            "cluster_ssh_target": "",
        })
        mcp = dest / "mcp_tools"
        assert (mcp / "slurm.py").exists(), "slurm.py should be present"
        assert (mcp / "slurm.yaml").exists(), "slurm.yaml should be present"
        assert (mcp / "_cluster.py").exists(), "_cluster.py should be present"
        assert not (mcp / "lsf.py").exists(), "lsf.py should NOT be present"
        assert not (mcp / "lsf.yaml").exists(), "lsf.yaml should NOT be present"

    def test_no_cluster(self, copier_output):
        """use_cluster=false → no cluster files in mcp_tools/."""
        dest = copier_output({
            "project_name": "no_cluster",
            "claudechic_mode": "standard",
            "use_cluster": False,
        })
        mcp = dest / "mcp_tools"
        # mcp_tools/ directory may or may not exist, but cluster files must be absent
        if mcp.exists():
            assert not (mcp / "lsf.py").exists()
            assert not (mcp / "slurm.py").exists()
            assert not (mcp / "_cluster.py").exists()
            assert not (mcp / "lsf.yaml").exists()
            assert not (mcp / "slurm.yaml").exists()

    def test_lsf_yaml_has_ssh_target(self, copier_output):
        """LSF YAML config should contain the provided ssh_target."""
        dest = copier_output({
            "project_name": "lsf_ssh",
            "claudechic_mode": "standard",
            "use_cluster": True,
            "cluster_scheduler": "lsf",
            "cluster_ssh_target": "mylogin.janelia.org",
        })
        yaml_content = (dest / "mcp_tools" / "lsf.yaml").read_text()
        assert "mylogin.janelia.org" in yaml_content

    def test_cluster_adds_pyyaml(self, copier_output):
        """use_cluster=true → pixi.toml includes pyyaml dependency."""
        dest = copier_output({
            "project_name": "yaml_dep",
            "claudechic_mode": "standard",
            "use_cluster": True,
            "cluster_scheduler": "lsf",
            "cluster_ssh_target": "",
        })
        content = (dest / "pixi.toml").read_text()
        assert "pyyaml" in content.lower()


# ---------------------------------------------------------------------------
# _exclude tests
# ---------------------------------------------------------------------------


class TestExclude:
    """Verify _exclude rules prevent certain dirs from appearing in output."""

    def test_always_excluded_dirs(self, copier_output):
        """docs/, .ao_project_team/, submodules/, tests/ never in generated project."""
        dest = copier_output({
            "project_name": "excl_test",
            "claudechic_mode": "standard",
            "use_cluster": False,
        })
        assert not (dest / "docs").exists(), "docs/ should be excluded"
        assert not (dest / ".ao_project_team").exists(), ".ao_project_team/ should be excluded"
        assert not (dest / "submodules").exists(), "submodules/ should be excluded"
        assert not (dest / "tests").exists(), "tests/ should be excluded"

    def test_guardrails_excluded_when_disabled(self, copier_output):
        """use_guardrails=false → no guardrail files in .claude/guardrails/."""
        dest = copier_output({
            "project_name": "no_guard",
            "claudechic_mode": "standard",
            "use_guardrails": False,
            "use_cluster": False,
        })
        guardrails = dest / ".claude" / "guardrails"
        if guardrails.exists():
            files = list(guardrails.rglob("*"))
            files = [f for f in files if f.is_file()]
            assert files == [], f"Guardrail files should be excluded: {files}"

    def test_project_team_excluded_when_disabled(self, copier_output):
        """use_project_team=false → no agent role files in AI_agents/."""
        dest = copier_output({
            "project_name": "no_team",
            "claudechic_mode": "standard",
            "use_project_team": False,
            "use_cluster": False,
        })
        ai_agents = dest / "AI_agents"
        if ai_agents.exists():
            files = list(ai_agents.rglob("*"))
            files = [f for f in files if f.is_file()]
            assert files == [], f"AI_agents files should be excluded: {files}"
