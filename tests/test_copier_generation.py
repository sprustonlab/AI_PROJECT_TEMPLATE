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
        content = pixi_toml.read_text(encoding="utf-8")
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
        content = pixi_toml.read_text(encoding="utf-8")
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
        yaml_content = (dest / "mcp_tools" / "lsf.yaml").read_text(encoding="utf-8")
        assert "mylogin.janelia.org" in yaml_content

    def test_pyyaml_always_present(self, copier_output):
        """pixi.toml always includes pyyaml (needed by guardrails)."""
        dest = copier_output({
            "project_name": "yaml_dep",
            "claudechic_mode": "standard",
            "use_cluster": False,
        })
        content = (dest / "pixi.toml").read_text(encoding="utf-8")
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
            content = pyfile.read_text(encoding="utf-8")
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


# ---------------------------------------------------------------------------
# Hints system generation tests
# ---------------------------------------------------------------------------


class TestHints:
    """Verify hints/ folder inclusion/exclusion based on use_hints."""

    def test_hints_included_when_enabled(self, copier_output):
        """use_hints=true → hints/ folder with all 5 files."""
        dest = copier_output({
            "project_name": "hints_on",
            "claudechic_mode": "standard",
            "use_hints": True,
            "use_cluster": False,
        })
        hints = dest / "hints"
        assert hints.is_dir(), "hints/ directory should exist when use_hints=true"
        expected_files = [
            "__init__.py",
            "_types.py",
            "_state.py",
            "_engine.py",
            "hints.py",
        ]
        for fname in expected_files:
            assert (hints / fname).is_file(), f"hints/{fname} should exist"

    def test_hints_skill_included_when_enabled(self, copier_output):
        """use_hints=true → /hints skill exists."""
        dest = copier_output({
            "project_name": "hints_skill_on",
            "claudechic_mode": "standard",
            "use_hints": True,
            "use_cluster": False,
        })
        assert (dest / ".claude" / "skills" / "hints" / "SKILL.md").is_file(), (
            "hints SKILL.md should exist when use_hints=true"
        )

    def test_hints_skill_excluded_when_disabled(self, copier_output):
        """use_hints=false → /hints skill excluded."""
        dest = copier_output({
            "project_name": "hints_skill_off",
            "claudechic_mode": "standard",
            "use_hints": False,
            "use_cluster": False,
        })
        skill_dir = dest / ".claude" / "skills" / "hints"
        if skill_dir.exists():
            assert not (skill_dir / "SKILL.md").exists(), (
                "hints SKILL.md should NOT exist when use_hints=false"
            )

    def test_hints_excluded_when_disabled(self, copier_output):
        """use_hints=false → no hint files in generated project.

        Note: Copier may create an empty hints/ directory (the _exclude
        pattern excludes contents, not the directory itself). The key
        assertion is that no hint Python files are present.
        """
        dest = copier_output({
            "project_name": "hints_off",
            "claudechic_mode": "standard",
            "use_hints": False,
            "use_cluster": False,
        })
        hints = dest / "hints"
        if hints.exists():
            py_files = list(hints.glob("*.py"))
            assert py_files == [], (
                f"hints/ should have no Python files when use_hints=false, "
                f"found: {[f.name for f in py_files]}"
            )



# ---------------------------------------------------------------------------
# Install script containment tests
# ---------------------------------------------------------------------------


class TestProjectContainment:
    """Verify copier output is fully contained in the project directory."""

    def test_no_files_leak_to_parent(self, tmp_path):
        """copier copy into a subdirectory must not create files in the parent.

        This catches the bug where `copier copy $URL .` dumps template files
        into the current directory instead of a named subdirectory.
        """
        from copier import run_copy
        import os
        import subprocess

        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "Test"
        env["GIT_AUTHOR_EMAIL"] = "test@test.com"
        env["GIT_COMMITTER_NAME"] = "Test"
        env["GIT_COMMITTER_EMAIL"] = "test@test.com"

        # Record what's in tmp_path before copier runs
        parent_dir = tmp_path / "workspace"
        parent_dir.mkdir()
        before = set(parent_dir.iterdir())

        # Simulate the WRONG way: copy into "." (parent_dir itself)
        project_in_parent = parent_dir / "my_project"
        project_in_parent.mkdir()
        subprocess.run(
            ["git", "init"], cwd=project_in_parent,
            capture_output=True, check=True, env=env,
        )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "init"],
            cwd=project_in_parent, capture_output=True, check=True, env=env,
        )

        run_copy(
            str(Path(__file__).resolve().parent.parent),
            project_in_parent,
            data={
                "project_name": "my_project",
                "claudechic_mode": "standard",
                "use_cluster": False,
            },
            defaults=True,
            unsafe=True,
        )

        # After copier, parent_dir should only contain the project subdir
        after = set(parent_dir.iterdir())
        leaked = after - before - {project_in_parent}
        assert not leaked, (
            f"Files leaked to parent directory outside project folder: "
            f"{[p.name for p in leaked]}"
        )

        # The project dir itself should have content
        project_files = list(project_in_parent.iterdir())
        assert len(project_files) > 0, "Project directory should have files"

        # Key template files should be INSIDE the project dir
        assert (project_in_parent / "pixi.toml").exists(), (
            "pixi.toml should be inside project directory"
        )
        assert (project_in_parent / "activate").exists(), (
            "activate should be inside project directory"
        )

    def test_install_script_uses_project_subdir(self):
        """install.sh must pass a project subdirectory to copier, not '.'."""
        docs = Path(__file__).resolve().parent.parent / "docs"

        sh_content = (docs / "install.sh").read_text(encoding="utf-8")
        assert 'copier copy --trust "$TEMPLATE_URL" .' not in sh_content, (
            "install.sh should NOT copy into '.', must use a project subdirectory"
        )

        ps1_content = (docs / "install.ps1").read_text(encoding="utf-8")
        assert "copier copy --trust $TemplateUrl ." not in ps1_content, (
            "install.ps1 should NOT copy into '.', must use a project subdirectory"
        )

    def test_install_sh_reads_from_tty(self):
        """install.sh must read user input from /dev/tty, not stdin.

        When run via `curl | bash`, stdin is the script itself.
        All `read` calls must redirect from /dev/tty to get user input.
        """
        import re
        docs = Path(__file__).resolve().parent.parent / "docs"
        sh_content = (docs / "install.sh").read_text(encoding="utf-8")

        # Find all `read` commands
        read_calls = re.findall(r'^.*\bread\b.*$', sh_content, re.MULTILINE)
        for line in read_calls:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "/dev/tty" in stripped, (
                f"install.sh `read` must use < /dev/tty for curl|bash compat: "
                f"{stripped}"
            )


# ---------------------------------------------------------------------------
# Copier answers file test
# ---------------------------------------------------------------------------


class TestAnswersFile:
    """Verify .copier-answers.yml generation."""

    def test_copier_answers_file_generated(self, copier_output):
        """Generated project contains .copier-answers.yml with correct values."""
        dest = copier_output({
            "project_name": "answers_test",
            "claudechic_mode": "standard",
            "use_hints": True,
            "use_cluster": False,
        })
        answers_file = dest / ".copier-answers.yml"
        assert answers_file.is_file(), ".copier-answers.yml should be generated"

        import yaml

        data = yaml.safe_load(answers_file.read_text(encoding="utf-8"))
        assert isinstance(data, dict), ".copier-answers.yml should be a YAML dict"
        assert data.get("project_name") == "answers_test"
        assert data.get("use_hints") is True
