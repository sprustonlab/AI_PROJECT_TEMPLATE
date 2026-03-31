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
import sys

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

    def test_pyyaml_always_present(self, copier_output):
        """pixi.toml always includes pyyaml (needed by guardrails)."""
        dest = copier_output({
            "project_name": "yaml_dep",
            "claudechic_mode": "standard",
            "use_cluster": False,
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


# ---------------------------------------------------------------------------
# Guardrail system completeness tests
# ---------------------------------------------------------------------------


class TestGuardrails:
    """Verify the guardrail system is complete in generated projects."""

    def test_guardrail_files_present(self, copier_output):
        """use_guardrails=true → all guardrail components are present."""
        dest = copier_output({
            "project_name": "guard_test",
            "claudechic_mode": "standard",
            "use_guardrails": True,
            "use_cluster": False,
        })
        guardrails = dest / ".claude" / "guardrails"
        assert guardrails.exists(), "guardrails/ directory should exist"
        assert (guardrails / "rules.yaml").exists(), "rules.yaml missing"
        assert (guardrails / "generate_hooks.py").exists(), "generate_hooks.py missing"
        assert (guardrails / "role_guard.py").exists(), "role_guard.py missing"
        assert (guardrails / "hooks").is_dir(), "hooks/ directory missing"

    def test_generate_hooks_runs(self, copier_output):
        """generate_hooks.py can parse rules.yaml without errors."""
        import subprocess
        dest = copier_output({
            "project_name": "guard_run",
            "claudechic_mode": "standard",
            "use_guardrails": True,
            "use_cluster": False,
        })
        result = subprocess.run(
            [sys.executable, str(dest / ".claude" / "guardrails" / "generate_hooks.py")],
            cwd=dest,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"generate_hooks.py failed:\nSTDOUT: {result.stdout[:500]}\nSTDERR: {result.stderr[:500]}"
        )
        # After running, hooks/ should have generated scripts
        hooks = list((dest / ".claude" / "guardrails" / "hooks").glob("*.py"))
        assert len(hooks) > 0, "generate_hooks.py should create hook scripts"

    def test_guardrail_files_no_jinja_artifacts(self, copier_output):
        """Guardrail Python files should not have unprocessed Jinja2 artifacts."""
        dest = copier_output({
            "project_name": "guard_jinja",
            "claudechic_mode": "standard",
            "use_guardrails": True,
            "use_cluster": False,
        })
        for pyfile in (dest / ".claude" / "guardrails").glob("*.py"):
            content = pyfile.read_text()
            # Real Jinja2 artifacts like {% or {{ project_name }} should not appear
            # but Python f-string {{ }} is fine
            assert "{%" not in content, f"Jinja artifact in {pyfile.name}"

    def test_generated_hook_blocks_dangerous_command(self, copier_output):
        """Full E2E: generate hooks, then fire bash_guard with 'rm -rf /' → blocked."""
        dest = copier_output({
            "project_name": "guard_e2e",
            "claudechic_mode": "standard",
            "use_guardrails": True,
            "use_cluster": False,
        })
        guardrails = dest / ".claude" / "guardrails"

        # Step 1: generate hooks
        gen_result = subprocess.run(
            [sys.executable, str(guardrails / "generate_hooks.py")],
            cwd=dest, capture_output=True, text=True, timeout=30,
        )
        assert gen_result.returncode == 0, f"generate_hooks.py failed: {gen_result.stderr[:300]}"

        bash_guard = guardrails / "hooks" / "bash_guard.py"
        assert bash_guard.exists(), "bash_guard.py not generated"

        # Step 2: simulate a dangerous tool call (what Claude Code sends on stdin)
        import json
        tool_call = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "session_id": "test-session",
        })

        result = subprocess.run(
            [sys.executable, str(bash_guard)],
            input=tool_call,
            cwd=dest,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Hook should exit non-zero (deny) with R01 message
        assert result.returncode != 0, (
            f"bash_guard should DENY 'rm -rf /' but exited 0.\nSTDOUT: {result.stdout[:300]}"
        )
        output = result.stdout + result.stderr
        assert "R01" in output, (
            f"Expected R01 in output.\nSTDOUT: {result.stdout[:300]}\nSTDERR: {result.stderr[:300]}"
        )
        assert "not allowed" in output.lower() or "blocked" in output.lower(), (
            f"Expected block message.\nOutput: {output[:300]}"
        )

    def test_generated_hook_allows_safe_command(self, copier_output):
        """Full E2E: fire bash_guard with 'ls -la' → allowed."""
        dest = copier_output({
            "project_name": "guard_allow",
            "claudechic_mode": "standard",
            "use_guardrails": True,
            "use_cluster": False,
        })
        guardrails = dest / ".claude" / "guardrails"

        # Generate hooks
        subprocess.run(
            [sys.executable, str(guardrails / "generate_hooks.py")],
            cwd=dest, capture_output=True, text=True, timeout=30,
        )

        bash_guard = guardrails / "hooks" / "bash_guard.py"
        assert bash_guard.exists()

        import json
        tool_call = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
            "session_id": "test-session",
        })

        result = subprocess.run(
            [sys.executable, str(bash_guard)],
            input=tool_call,
            cwd=dest,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, (
            f"bash_guard should ALLOW 'ls -la' but denied.\nSTDOUT: {result.stdout[:300]}\nSTDERR: {result.stderr[:300]}"
        )
