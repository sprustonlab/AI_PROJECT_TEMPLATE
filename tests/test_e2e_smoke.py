"""Layer 5: Pexpect Smoke Test.

End-to-end test that exercises the full user journey:
1. Copier copy → generates project
2. pixi install → installs dependencies
3. import claudechic → verifies installation
4. MCP server creation → verifies tools are registered
5. claudechic TUI startup → verifies no crash on launch

This test is slow (pixi install can take minutes) and requires network access.
Intended to run as a weekly CI job, not on every commit.

Requires: pexpect (Linux/macOS only), copier, pixi
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Skip on Windows — pexpect doesn't work there
pytestmark = [
    pytest.mark.skipif(
        platform.system() == "Windows",
        reason="pexpect not available on Windows",
    ),
    pytest.mark.skipif(
        shutil.which("pixi") is None,
        reason="pixi not installed",
    ),
    pytest.mark.slow,
    pytest.mark.network,
    pytest.mark.unix_only,
]

TEMPLATE_ROOT = Path(__file__).resolve().parent.parent


def _copier_available():
    try:
        import copier  # noqa: F401
        return True
    except ImportError:
        return False


def _pexpect_available():
    try:
        import pexpect  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def generated_project():
    """Generate a project with copier (LSF cluster, standard mode).

    This is module-scoped so pixi install only runs once for all tests.
    """
    if not _copier_available():
        pytest.skip("copier not installed")

    from copier import run_copy

    tmp = tempfile.mkdtemp(prefix="e2e_smoke_")
    dest = Path(tmp) / "smoke_project"

    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "Test"
    env["GIT_AUTHOR_EMAIL"] = "test@test.com"
    env["GIT_COMMITTER_NAME"] = "Test"
    env["GIT_COMMITTER_EMAIL"] = "test@test.com"

    dest.mkdir(parents=True)
    subprocess.run(
        ["git", "init"], cwd=dest, capture_output=True, check=True, env=env,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init"],
        cwd=dest, capture_output=True, check=True, env=env,
    )

    run_copy(
        str(TEMPLATE_ROOT),
        dest,
        data={
            "project_name": "smoke_test",
            "claudechic_mode": "standard",
            "use_cluster": True,
            "cluster_scheduler": "lsf",
            "cluster_ssh_target": "",
            "use_guardrails": True,
            "use_project_team": True,
        },
        defaults=True,
        unsafe=True,
    )

    yield dest

    # Cleanup
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 1: Copier generates expected files
# ---------------------------------------------------------------------------


class TestCopierGeneration:
    """Verify copier generated the expected project structure."""

    def test_pixi_toml_exists(self, generated_project):
        assert (generated_project / "pixi.toml").exists()

    def test_activate_script_exists(self, generated_project):
        assert (generated_project / "activate").exists()

    def test_lsf_tools_present(self, generated_project):
        mcp = generated_project / "mcp_tools"
        assert (mcp / "lsf.py").exists()
        assert (mcp / "lsf.yaml").exists()
        assert (mcp / "_cluster.py").exists()

    def test_no_slurm_tools(self, generated_project):
        mcp = generated_project / "mcp_tools"
        assert not (mcp / "slurm.py").exists()

    def test_excluded_dirs_absent(self, generated_project):
        assert not (generated_project / "tests").exists()
        assert not (generated_project / "docs").exists()
        assert not (generated_project / ".project_team").exists()

    def test_guardrail_system_complete(self, generated_project):
        """All guardrail components are present in generated project."""
        guardrails = generated_project / ".claude" / "guardrails"
        assert (guardrails / "rules.yaml").exists(), "rules.yaml missing"
        assert (guardrails / "generate_hooks.py").exists(), "generate_hooks.py missing"
        assert (guardrails / "role_guard.py").exists(), "role_guard.py missing"
        assert (guardrails / "hooks").is_dir(), "hooks/ directory missing"


# ---------------------------------------------------------------------------
# Test 2: pixi install succeeds
# ---------------------------------------------------------------------------


class TestPixiInstall:
    """Run pixi install and verify it succeeds."""

    @pytest.mark.timeout(300)
    @pytest.mark.skipif(
        os.environ.get("CI_SKIP_PIXI_INSTALL") == "1",
        reason="CI_SKIP_PIXI_INSTALL set",
    )
    def test_pixi_install(self, generated_project):
        """pixi install completes without error."""
        env = os.environ.copy()
        env["SETUPTOOLS_SCM_PRETEND_VERSION"] = "0.0.1"

        result = subprocess.run(
            ["pixi", "install"],
            cwd=generated_project,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        # pixi install may fail if git URL is unreachable; soft-fail in that case
        if result.returncode != 0 and "git" in result.stderr.lower():
            pytest.skip(f"pixi install failed (git unreachable): {result.stderr[:200]}")
        assert result.returncode == 0, (
            f"pixi install failed:\nSTDOUT: {result.stdout[:500]}\nSTDERR: {result.stderr[:500]}"
        )


# ---------------------------------------------------------------------------
# Test 3: import claudechic succeeds (after pixi install)
# ---------------------------------------------------------------------------


class TestClaudechicImport:
    """Verify claudechic can be imported in the generated project."""

    @pytest.mark.skipif(
        os.environ.get("CI_SKIP_PIXI_INSTALL") == "1",
        reason="CI_SKIP_PIXI_INSTALL set",
    )
    def test_import_claudechic(self, generated_project):
        """'import claudechic' succeeds inside generated project's pixi env."""
        result = subprocess.run(
            ["pixi", "run", "python", "-c", "import claudechic; print('OK')"],
            cwd=generated_project,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 and "No such environment" in result.stderr:
            pytest.skip("pixi env not installed")
        assert result.returncode == 0, (
            f"import claudechic failed:\nSTDERR: {result.stderr[:500]}"
        )
        assert "OK" in result.stdout


# ---------------------------------------------------------------------------
# Test 4: MCP server creation with tools
# ---------------------------------------------------------------------------


class TestMCPServerCreation:
    """Verify MCP tools are discoverable in the generated project."""

    def test_mcp_tools_discoverable(self, generated_project):
        """discover_mcp_tools() finds LSF tools in the generated project's mcp_tools/."""
        # We can test this directly using our test infrastructure
        # (no need for pixi — just import and point at the directory)
        from pathlib import Path
        from claudechic.mcp import discover_mcp_tools

        mcp_dir = generated_project / "mcp_tools"
        if not mcp_dir.exists():
            pytest.skip("mcp_tools/ not generated")

        from unittest.mock import MagicMock, patch

        with patch("subprocess.run", return_value=MagicMock(stdout="", stderr="", returncode=0)):
            tools = discover_mcp_tools(
                mcp_dir,
                caller_name="smoke_test",
                send_notification=lambda *a, **kw: None,
                find_agent=lambda n: (None, "not found"),
            )

        tool_names = [getattr(t, "name", None) or getattr(t, "_tool_name", None) for t in tools]
        assert "cluster_jobs" in tool_names, f"Expected cluster_jobs in {tool_names}"
        assert "cluster_submit" in tool_names
        assert len(tools) == 6  # 6 LSF tools


# ---------------------------------------------------------------------------
# Test 5: claudechic TUI startup (pexpect)
# ---------------------------------------------------------------------------


class TestExistingCodebaseImport:
    """Verify that an existing codebase integrated via repos/ is importable after activate."""

    @pytest.mark.timeout(300)
    @pytest.mark.skipif(
        os.environ.get("CI_SKIP_PIXI_INSTALL") == "1",
        reason="CI_SKIP_PIXI_INSTALL set",
    )
    def test_import_existing_codebase_after_activate(self):
        """Full E2E: copier + existing_codebase → source activate → import works."""
        if not _copier_available():
            pytest.skip("copier not installed")

        from copier import run_copy

        tmp = tempfile.mkdtemp(prefix="e2e_codebase_")
        try:
            # 1. Create a fake codebase with a Python package
            fake_repo = Path(tmp) / "my_lib"
            fake_repo.mkdir()
            pkg_dir = fake_repo / "my_lib"
            pkg_dir.mkdir()
            (pkg_dir / "__init__.py").write_text("VERSION = '0.42'\n", encoding="utf-8")
            (pkg_dir / "core.py").write_text("def greet():\n    return 'hello from my_lib'\n", encoding="utf-8")

            # 2. Generate project with existing_codebase pointing to fake repo
            dest = Path(tmp) / "test_project"

            env = os.environ.copy()
            env["GIT_AUTHOR_NAME"] = "Test"
            env["GIT_AUTHOR_EMAIL"] = "test@test.com"
            env["GIT_COMMITTER_NAME"] = "Test"
            env["GIT_COMMITTER_EMAIL"] = "test@test.com"

            dest.mkdir(parents=True)
            subprocess.run(
                ["git", "init"], cwd=dest, capture_output=True, check=True, env=env,
            )
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "init"],
                cwd=dest, capture_output=True, check=True, env=env,
            )

            run_copy(
                str(TEMPLATE_ROOT),
                dest,
                data={
                    "project_name": "codebase_import_test",
                    "claudechic_mode": "standard",
                    "use_cluster": False,
                    "use_guardrails": False,
                    "use_project_team": False,
                    "init_git": False,
                    "existing_codebase": str(fake_repo),
                    "codebase_link_mode": "copy",
                },
                defaults=True,
                unsafe=True,
            )

            # 3. Verify the codebase landed in repos/
            assert (dest / "repos" / "my_lib" / "my_lib" / "__init__.py").exists()

            # 4. Source activate and try to import
            # We simulate what activate does: add repos/*/ to PYTHONPATH
            # then run python to import the package.
            # Write the test script to a file to avoid shell quoting issues.
            test_script = dest / "_test_import.py"
            test_script.write_text(
                "from my_lib import VERSION\n"
                "from my_lib.core import greet\n"
                "print('version=' + VERSION + ' greeting=' + greet())\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["bash", "-c",
                 f'source "{dest}/activate" && python3 "{test_script}"'],
                cwd=dest,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            assert result.returncode == 0, (
                f"Import failed after activate:\nSTDOUT: {result.stdout[:500]}\nSTDERR: {result.stderr[:500]}"
            )
            assert "version=0.42" in result.stdout
            assert "greeting=hello from my_lib" in result.stdout

        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 6: claudechic TUI startup (pexpect)
# ---------------------------------------------------------------------------


class TestTUIStartup:
    """Verify claudechic TUI starts without crashing (pexpect)."""

    @pytest.mark.timeout(60)
    @pytest.mark.skipif(
        not _pexpect_available(),
        reason="pexpect not installed",
    )
    @pytest.mark.skipif(
        os.environ.get("CI_SKIP_PIXI_INSTALL") == "1",
        reason="CI_SKIP_PIXI_INSTALL set",
    )
    def test_claudechic_starts(self, generated_project):
        """claudechic process starts without immediate crash.

        We use pexpect to spawn the process and verify it doesn't
        exit with an error within 5 seconds. We don't test interactive
        features — that's Layer 4's job.
        """
        import pexpect

        # Check if pixi env is ready
        check = subprocess.run(
            ["pixi", "run", "python", "-c", "import claudechic"],
            cwd=generated_project,
            capture_output=True,
            timeout=30,
        )
        if check.returncode != 0:
            pytest.skip("claudechic not installed in pixi env")

        # Spawn claudechic via pixi
        child = pexpect.spawn(
            "pixi run claudechic",
            cwd=str(generated_project),
            timeout=10,
            encoding="utf-8",
        )

        try:
            # Wait a few seconds for the app to initialize
            # The TUI should NOT exit immediately
            idx = child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=5)

            if idx == 0:  # EOF — process exited
                output = child.before or ""
                # Check if it crashed vs graceful exit
                exitstatus = child.exitstatus
                if exitstatus != 0:
                    pytest.fail(
                        f"claudechic exited immediately with code {exitstatus}:\n{output[:500]}"
                    )
                # Exit code 0 is acceptable (e.g., if no Claude login)
            else:
                # TIMEOUT — app is still running (this is the success case)
                pass
        finally:
            # Clean up — send Ctrl+C to exit
            child.sendcontrol("c")
            try:
                child.expect(pexpect.EOF, timeout=5)
            except pexpect.TIMEOUT:
                child.terminate(force=True)
            child.close()
