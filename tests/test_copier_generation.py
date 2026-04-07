"""Tests for copier template generation with various configurations.

Verifies:
- Standard vs developer claudechic mode in pixi.toml
- Cluster scheduler file inclusion/exclusion (LSF, SLURM, none)
- _exclude rules: docs/, .project_team/, submodules/, tests/ never in output
- quick_start presets: everything, defaults, empty, custom

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
            "quick_start": "defaults",
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
            "quick_start": "defaults",
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
            "quick_start": "defaults",
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
            "quick_start": "defaults",
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
            "quick_start": "defaults",
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
            "quick_start": "defaults",
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
            "quick_start": "defaults",
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
        """docs/, .project_team/, submodules/, tests/ never in generated project."""
        dest = copier_output({
            "project_name": "excl_test",
            "claudechic_mode": "standard",
            "quick_start": "defaults",
            "use_cluster": False,
        })
        assert not (dest / "docs").exists(), "docs/ should be excluded"
        assert not (dest / ".project_team").exists(), ".project_team/ should be excluded"
        assert not (dest / "submodules").exists(), "submodules/ should be excluded"
        assert not (dest / "tests").exists(), "tests/ should be excluded"


# ---------------------------------------------------------------------------
# quick_start preset tests
# ---------------------------------------------------------------------------


class TestQuickStartPresets:
    """Verify quick_start presets control example content correctly."""

    # Core roles that ALWAYS ship (regardless of preset)
    CORE_ROLES = [
        "coordinator", "composability", "implementer", "skeptic",
        "terminology", "user_alignment", "test_engineer",
    ]

    # Specialist roles (only with everything/defaults/custom+example_agent_roles)
    SPECIALIST_ROLES = [
        "researcher", "lab_notebook", "ui_designer", "git_setup",
        "binary_portability", "memory_layout", "project_integrator",
        "sync_coordinator",
    ]

    # Tutorial workflows (only with everything/custom+example_workflows)
    TUTORIAL_WORKFLOWS = [
        "tutorial_extending",
        "tutorial_toy_project",
    ]

    def test_everything_mode(self, copier_output):
        """quick_start=everything → ALL content: specialists, tutorials, global, patterns."""
        dest = copier_output({
            "project_name": "everything_test",
            "claudechic_mode": "standard",
            "quick_start": "everything",
            "use_cluster": False,
        })

        # Core infrastructure always present
        assert (dest / ".claude" / "guardrails" / "rules.yaml").exists()
        assert (dest / "pixi.toml").exists()
        assert (dest / "activate").exists()

        # Core roles always present
        for role in self.CORE_ROLES:
            assert (dest / "workflows" / "project_team" / role / "identity.md").exists(), (
                f"Core role {role} should always be present"
            )

        # Specialist roles present in everything mode
        for role in self.SPECIALIST_ROLES:
            assert (dest / "workflows" / "project_team" / role / "identity.md").exists(), (
                f"Specialist role {role} should be present in everything mode"
            )

        # Tutorial workflows present in everything mode
        for wf in self.TUTORIAL_WORKFLOWS:
            assert (dest / "workflows" / wf).is_dir(), (
                f"Tutorial workflow {wf} should be present in everything mode"
            )

        # Global config present
        assert (dest / "global" / "rules.yaml").exists(), "global/rules.yaml should be present"

        # Pattern miner present in everything mode
        assert (dest / "scripts" / "mine_patterns.py").exists(), (
            "Pattern miner should be present in everything mode"
        )
        assert (dest / "commands" / "mine-patterns").exists(), (
            "mine-patterns command should be present in everything mode"
        )

        # project_team workflow YAML always present
        assert (dest / "workflows" / "project_team" / "project_team.yaml").exists()

    def test_defaults_mode(self, copier_output):
        """quick_start=defaults → core + specialists + global, NO tutorials, NO patterns."""
        dest = copier_output({
            "project_name": "defaults_test",
            "claudechic_mode": "standard",
            "quick_start": "defaults",
            "use_cluster": False,
        })

        # Core roles present
        for role in self.CORE_ROLES:
            assert (dest / "workflows" / "project_team" / role / "identity.md").exists(), (
                f"Core role {role} should be present in defaults mode"
            )

        # Specialist roles present in defaults mode
        for role in self.SPECIALIST_ROLES:
            assert (dest / "workflows" / "project_team" / role / "identity.md").exists(), (
                f"Specialist role {role} should be present in defaults mode"
            )

        # Global config present in defaults
        assert (dest / "global" / "rules.yaml").exists(), "global/rules.yaml should be present"

        # Tutorial workflows NOT present in defaults
        for wf in self.TUTORIAL_WORKFLOWS:
            wf_dir = dest / "workflows" / wf
            if wf_dir.exists():
                files = list(wf_dir.rglob("*"))
                files = [f for f in files if f.is_file()]
                assert files == [], f"Tutorial {wf} should be excluded in defaults mode"

        # Pattern miner NOT present in defaults
        assert not (dest / "scripts" / "mine_patterns.py").exists(), (
            "Pattern miner should NOT be present in defaults mode"
        )
        assert not (dest / "commands" / "mine-patterns").exists(), (
            "mine-patterns should NOT be present in defaults mode"
        )

    def test_empty_mode(self, copier_output):
        """quick_start=empty → infrastructure + core roles ONLY. No specialists, no examples."""
        dest = copier_output({
            "project_name": "empty_test",
            "claudechic_mode": "standard",
            "quick_start": "empty",
            "use_cluster": False,
        })

        # Infrastructure always present
        assert (dest / ".claude" / "guardrails" / "rules.yaml").exists()
        assert (dest / "pixi.toml").exists()
        assert (dest / "activate").exists()

        # Core roles always present
        for role in self.CORE_ROLES:
            assert (dest / "workflows" / "project_team" / role / "identity.md").exists(), (
                f"Core role {role} should be present even in empty mode"
            )

        # Specialist roles NOT present in empty mode
        for role in self.SPECIALIST_ROLES:
            role_dir = dest / "workflows" / "project_team" / role
            if role_dir.exists():
                files = list(role_dir.rglob("*"))
                files = [f for f in files if f.is_file()]
                assert files == [], (
                    f"Specialist role {role} should be excluded in empty mode"
                )

        # Global example rules NOT present
        global_rules = dest / "global" / "rules.yaml"
        assert not global_rules.exists(), (
            "global/rules.yaml should NOT be present in empty mode"
        )

        # Tutorials NOT present
        for wf in self.TUTORIAL_WORKFLOWS:
            wf_dir = dest / "workflows" / wf
            if wf_dir.exists():
                files = list(wf_dir.rglob("*"))
                files = [f for f in files if f.is_file()]
                assert files == [], f"Tutorial {wf} should be excluded in empty mode"

        # Pattern miner NOT present
        assert not (dest / "scripts" / "mine_patterns.py").exists()

    def test_custom_selective(self, copier_output):
        """custom with example_workflows=False but example_agent_roles=True works."""
        dest = copier_output({
            "project_name": "custom_test",
            "claudechic_mode": "standard",
            "quick_start": "custom",
            "example_rules": True,
            "example_agent_roles": True,
            "example_workflows": False,
            "example_hints": False,
            "example_patterns": False,
            "use_cluster": False,
        })

        # Core roles always present
        for role in self.CORE_ROLES:
            assert (dest / "workflows" / "project_team" / role / "identity.md").exists(), (
                f"Core role {role} should be present"
            )

        # Specialist roles present (example_agent_roles=True)
        for role in self.SPECIALIST_ROLES:
            assert (dest / "workflows" / "project_team" / role / "identity.md").exists(), (
                f"Specialist role {role} should be present when example_agent_roles=True"
            )

        # Tutorial workflows NOT present (example_workflows=False)
        for wf in self.TUTORIAL_WORKFLOWS:
            wf_dir = dest / "workflows" / wf
            if wf_dir.exists():
                files = list(wf_dir.rglob("*"))
                files = [f for f in files if f.is_file()]
                assert files == [], (
                    f"Tutorial {wf} should be excluded when example_workflows=False"
                )

        # Global rules present (example_rules=True)
        assert (dest / "global" / "rules.yaml").exists()

        # Pattern miner NOT present (example_patterns=False)
        assert not (dest / "scripts" / "mine_patterns.py").exists()

        # Hints NOT present (example_hints=False)
        global_hints = dest / "global" / "hints.yaml"
        assert not global_hints.exists(), (
            "global/hints.yaml should NOT be present when example_hints=False"
        )


# ---------------------------------------------------------------------------
# Guardrail system completeness tests
# ---------------------------------------------------------------------------


class TestGuardrails:
    """Verify the guardrail system is complete in generated projects."""

    def test_guardrail_files_present(self, copier_output):
        """Guardrails always present → all guardrail components exist."""
        dest = copier_output({
            "project_name": "guard_test",
            "claudechic_mode": "standard",
            "quick_start": "defaults",
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
            "quick_start": "defaults",
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

    def test_generate_hooks_registers_in_settings_json(self, copier_output):
        """generate_hooks.py must create/update .claude/settings.json with hook entries.

        Without settings.json, Claude Code never invokes the hooks — the guardrail
        system is non-operational even though hook scripts exist.
        """
        import json
        dest = copier_output({
            "project_name": "guard_settings",
            "claudechic_mode": "standard",
            "quick_start": "defaults",
            "use_cluster": False,
        })
        # Run generate_hooks.py
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

        # settings.json must exist
        settings_path = dest / ".claude" / "settings.json"
        assert settings_path.exists(), (
            ".claude/settings.json not created by generate_hooks.py — "
            "hooks will never fire without it"
        )

        settings = json.loads(settings_path.read_text(encoding="utf-8"))

        # Must have hooks.PreToolUse entries
        hooks = settings.get("hooks", {})
        pre_tool_use = hooks.get("PreToolUse", [])
        assert len(pre_tool_use) > 0, (
            "settings.json has no PreToolUse hooks — guardrails are non-operational"
        )

        # Each generated hook script must have a matching entry
        hook_scripts = list((dest / ".claude" / "guardrails" / "hooks").glob("*.py"))
        hook_scripts = [h for h in hook_scripts if h.name != ".gitkeep"]
        for hook in hook_scripts:
            matched = any(
                hook.name in (e.get("hooks", [{}])[0].get("command", ""))
                for e in pre_tool_use
            )
            assert matched, (
                f"Hook script {hook.name} exists but has no entry in "
                f"settings.json — it will never be invoked by Claude Code"
            )

    def test_guardrail_files_no_jinja_artifacts(self, copier_output):
        """Guardrail Python files should not have unprocessed Jinja2 artifacts."""
        dest = copier_output({
            "project_name": "guard_jinja",
            "claudechic_mode": "standard",
            "quick_start": "defaults",
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
            "quick_start": "defaults",
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
            "quick_start": "defaults",
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
    """Verify hints/ folder is always present (infrastructure, not gated)."""

    def test_hints_always_present(self, copier_output):
        """Hints infrastructure always ships — 5 Python files."""
        dest = copier_output({
            "project_name": "hints_on",
            "claudechic_mode": "standard",
            "quick_start": "defaults",
            "use_cluster": False,
        })
        hints = dest / "hints"
        assert hints.is_dir(), "hints/ directory should always exist"
        expected_files = [
            "__init__.py",
            "_types.py",
            "_state.py",
            "_engine.py",
            "hints.py",
        ]
        for fname in expected_files:
            assert (hints / fname).is_file(), f"hints/{fname} should exist"


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
                "quick_start": "defaults",
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
            "quick_start": "defaults",
            "use_cluster": False,
        })
        answers_file = dest / ".copier-answers.yml"
        assert answers_file.is_file(), ".copier-answers.yml should be generated"

        import yaml

        data = yaml.safe_load(answers_file.read_text(encoding="utf-8"))
        assert isinstance(data, dict), ".copier-answers.yml should be a YAML dict"
        assert data.get("project_name") == "answers_test"
        assert data.get("quick_start") == "defaults"
