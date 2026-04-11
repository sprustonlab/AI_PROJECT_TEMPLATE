"""Tests for onboarding health checks and welcome screen.

These tests live in the root tests/ directory (not in claudechic's tests/)
because they test the bridge between Copier template answers (use_cluster,
use_existing_codebase) and claudechic's onboarding system.

Two tiers:
  Tier 1 — Real filesystem tests (no mocking except SSH/network)
  Tier 2 — Integration tests against real copier-generated projects

Plus widget/persistence unit tests and ChatApp E2E tests.
"""

from __future__ import annotations

import shutil
import subprocess
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from claudechic.hints.state import CopierAnswers, HintStateStore
from claudechic.onboarding import (
    FacetStatus,
    _codebase_configured,
    _cluster_configured,
    _cluster_detail,
    _codebase_detail,
    _git_configured,
    _is_dismissed,
    check_onboarding,
    write_dismiss_marker,
)

# Import shared copier helper for Tier 2 fixtures
from conftest import shared_copier_generation


# ---------------------------------------------------------------------------
# Skip markers
# ---------------------------------------------------------------------------

_HAS_GIT = shutil.which("git") is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_copier_answers(project_root: Path, answers: dict) -> None:
    """Write a .copier-answers.yml file with the given answers."""
    (project_root / ".copier-answers.yml").write_text(
        yaml.dump(answers), encoding="utf-8"
    )


def _git_init_with_remote(project_root: Path, remote_url: str = "git@github.com:user/repo.git") -> None:
    """Run real git init + add origin remote."""
    subprocess.run(["git", "init"], cwd=project_root, capture_output=True, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", remote_url],
        cwd=project_root, capture_output=True, check=True,
    )


def _create_workflow_manifests(project_root: Path) -> None:
    """Create minimal workflow YAML manifests so _workflow_exists() passes."""
    for name in ("cluster_setup", "git_setup", "codebase_setup"):
        d = project_root / "workflows" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.yaml").write_text(
            f"workflow_id: {name.replace('_', '-')}\nphases: []\n",
            encoding="utf-8",
        )


def _three_unconfigured_facets() -> list[FacetStatus]:
    """Return 3 unconfigured facets for widget tests."""
    return [
        FacetStatus("cluster-setup", "Cluster access", False, "not configured"),
        FacetStatus("git-setup", "Git remote", False, "no remote set"),
        FacetStatus("codebase-setup", "Codebase integration", False, "not integrated"),
    ]


def _mixed_facets() -> list[FacetStatus]:
    """Return facets: cluster configured, git+codebase not."""
    return [
        FacetStatus("cluster-setup", "Cluster access", True, "LSF (local)"),
        FacetStatus("git-setup", "Git remote", False, "no remote set"),
        FacetStatus("codebase-setup", "Codebase integration", False, "not integrated"),
    ]


# ===========================================================================
# Tier 1: Real filesystem tests (no mocking except SSH)
# ===========================================================================


class TestGitConfiguredReal:
    """Test _git_configured with real git operations."""

    pytestmark = pytest.mark.skipif(not _HAS_GIT, reason="git not installed")

    def test_git_with_remote_is_configured(self, tmp_path):
        """Real git init + remote add -> configured."""
        _git_init_with_remote(tmp_path)
        assert _git_configured(tmp_path) is True

    def test_git_init_without_remote_is_not_configured(self, tmp_path):
        """Real git init but no remote -> not configured."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        assert _git_configured(tmp_path) is False

    def test_no_git_dir_is_not_configured(self, tmp_path):
        """No .git directory -> not configured."""
        assert _git_configured(tmp_path) is False


class TestClusterConfiguredReal:
    """Test _cluster_configured with real YAML files (only mock SSH)."""

    def test_no_cluster_yaml_no_local_scheduler(self, tmp_path):
        """No cluster.yaml and no local scheduler -> not configured."""
        # Only mock shutil.which to prevent false positives from test machine
        with patch("claudechic.onboarding.shutil.which", return_value=None):
            assert _cluster_configured(tmp_path) is False

    def test_cluster_yaml_empty_backend(self, tmp_path):
        """cluster.yaml with empty backend -> not configured."""
        mcp = tmp_path / "mcp_tools"
        mcp.mkdir()
        (mcp / "cluster.yaml").write_text(
            yaml.dump({"backend": "", "ssh_target": ""}), encoding="utf-8"
        )
        with patch("claudechic.onboarding.shutil.which", return_value=None):
            assert _cluster_configured(tmp_path) is False

    def test_cluster_yaml_with_backend_and_ssh_target(self, tmp_path):
        """cluster.yaml with backend+ssh_target -> configured (no SSH liveness check)."""
        mcp = tmp_path / "mcp_tools"
        mcp.mkdir()
        (mcp / "cluster.yaml").write_text(
            yaml.dump({"backend": "lsf", "ssh_target": "login.hpc.edu"}),
            encoding="utf-8",
        )
        with patch("claudechic.onboarding.shutil.which", return_value=None):
            assert _cluster_configured(tmp_path) is True

    def test_local_bsub_on_path(self, tmp_path):
        """bsub found on PATH -> configured without YAML or SSH."""
        with patch(
            "claudechic.onboarding.shutil.which",
            side_effect=lambda cmd: "/usr/bin/bsub" if cmd == "bsub" else None,
        ):
            assert _cluster_configured(tmp_path) is True


class TestCodebaseConfiguredReal:
    """Test _codebase_configured with real filesystem."""

    def test_repos_with_package(self, tmp_path):
        """repos/ with a non-hidden subdir -> configured."""
        (tmp_path / "repos" / "mypackage").mkdir(parents=True)
        assert _codebase_configured(tmp_path) is True

    def test_repos_empty(self, tmp_path):
        """repos/ exists but empty -> not configured."""
        (tmp_path / "repos").mkdir()
        assert _codebase_configured(tmp_path) is False

    def test_no_repos_dir(self, tmp_path):
        """No repos/ directory -> not configured."""
        assert _codebase_configured(tmp_path) is False

    def test_repos_only_hidden(self, tmp_path):
        """repos/ with only hidden dirs -> not configured."""
        (tmp_path / "repos" / ".git").mkdir(parents=True)
        assert _codebase_configured(tmp_path) is False


class TestCheckOnboardingRealFilesystem:
    """Test check_onboarding with real .copier-answers.yml and filesystem state."""

    pytestmark = pytest.mark.skipif(not _HAS_GIT, reason="git not installed")

    def test_fresh_project_all_features_unconfigured(self, tmp_path):
        """Fresh project with all features -> 3 unconfigured facets."""
        _write_copier_answers(tmp_path, {
            "use_cluster": True,
            "use_existing_codebase": True,
        })
        _create_workflow_manifests(tmp_path)
        # No git, no cluster.yaml, no repos/ -> all unconfigured
        with patch("claudechic.onboarding.shutil.which", return_value=None):
            facets = check_onboarding(tmp_path)

        assert facets is not None
        assert len(facets) == 3
        assert all(not f.configured for f in facets)

    def test_git_configured_others_not(self, tmp_path):
        """Git remote set, cluster and codebase not -> 2 unconfigured facets shown."""
        _write_copier_answers(tmp_path, {
            "use_cluster": True,
            "use_existing_codebase": True,
        })
        _create_workflow_manifests(tmp_path)
        _git_init_with_remote(tmp_path)

        with patch("claudechic.onboarding.shutil.which", return_value=None):
            facets = check_onboarding(tmp_path)

        assert facets is not None
        git_facet = next(f for f in facets if f.workflow_id == "git-setup")
        assert git_facet.configured is True
        unconfigured = [f for f in facets if not f.configured]
        assert len(unconfigured) == 2

    def test_all_configured_returns_none(self, tmp_path):
        """Everything set up -> check_onboarding returns None."""
        _write_copier_answers(tmp_path, {
            "use_cluster": True,
            "use_existing_codebase": True,
        })
        _create_workflow_manifests(tmp_path)
        _git_init_with_remote(tmp_path)
        (tmp_path / "repos" / "mypackage").mkdir(parents=True)

        # Mock local bsub for cluster + mock SSH away
        with patch(
            "claudechic.onboarding.shutil.which",
            side_effect=lambda cmd: "/usr/bin/bsub" if cmd == "bsub" else None,
        ):
            result = check_onboarding(tmp_path)

        assert result is None

    def test_cluster_false_skips_cluster_facet(self, tmp_path):
        """use_cluster=False -> no cluster facet, only git + codebase."""
        _write_copier_answers(tmp_path, {
            "use_cluster": False,
            "use_existing_codebase": True,
        })
        _create_workflow_manifests(tmp_path)

        facets = check_onboarding(tmp_path)
        assert facets is not None
        workflow_ids = [f.workflow_id for f in facets]
        assert "cluster-setup" not in workflow_ids
        assert "git-setup" in workflow_ids
        assert "codebase-setup" in workflow_ids

    def test_codebase_false_skips_codebase_facet(self, tmp_path):
        """use_existing_codebase=False -> no codebase facet."""
        _write_copier_answers(tmp_path, {
            "use_cluster": False,
            "use_existing_codebase": False,
        })
        _create_workflow_manifests(tmp_path)

        facets = check_onboarding(tmp_path)
        assert facets is not None
        assert len(facets) == 1
        assert facets[0].workflow_id == "git-setup"


class TestDetailFunctionsReal:
    """Test detail functions with real filesystem."""

    def test_codebase_detail_lists_dirs(self, tmp_path):
        """_codebase_detail lists directory names in repos/."""
        (tmp_path / "repos" / "alpha").mkdir(parents=True)
        (tmp_path / "repos" / "beta").mkdir(parents=True)
        detail = _codebase_detail(tmp_path)
        assert "alpha" in detail
        assert "beta" in detail
        assert "repos/" in detail

    def test_cluster_detail_remote(self, tmp_path):
        """Remote cluster detail reads from cluster.yaml."""
        mcp = tmp_path / "mcp_tools"
        mcp.mkdir()
        (mcp / "cluster.yaml").write_text(
            yaml.dump({"backend": "slurm", "ssh_target": "login.hpc.edu"}),
            encoding="utf-8",
        )
        with patch("claudechic.onboarding.shutil.which", return_value=None):
            detail = _cluster_detail(tmp_path)
        assert "SLURM" in detail
        assert "login.hpc.edu" in detail


# ===========================================================================
# Tier 2: Integration tests against real copier-generated projects
# ===========================================================================


@pytest.fixture(scope="module")
def lsf_cluster_project(tmp_path_factory):
    """Reuse copier generation: LSF cluster config."""
    return shared_copier_generation(tmp_path_factory, "copier_lsf_cluster", {
        "project_name": "lsf_project",
        "claudechic_mode": "standard",
        "quick_start": "defaults",
        "use_cluster": True,
    })


@pytest.fixture(scope="module")
def no_cluster_project(tmp_path_factory):
    """Reuse copier generation: no cluster."""
    return shared_copier_generation(tmp_path_factory, "copier_std_defaults", {
        "project_name": "std_defaults",
        "claudechic_mode": "standard",
        "quick_start": "defaults",
        "use_cluster": False,
    })


def _copier_available():
    try:
        import copier  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _copier_available(), reason="copier not installed")
@pytest.mark.integration
@pytest.mark.timeout(120)
class TestOnboardingWithCopierProjects:
    """Run check_onboarding against real copier-generated projects."""

    def test_cluster_project_has_cluster_facet(self, lsf_cluster_project):
        """use_cluster=True copier project -> cluster facet appears."""
        dest = lsf_cluster_project

        # Verify real .copier-answers.yml exists and has use_cluster=True
        answers = yaml.safe_load(
            (dest / ".copier-answers.yml").read_text(encoding="utf-8")
        )
        assert answers.get("use_cluster") is True

        # Verify real cluster.yaml was generated
        assert (dest / "mcp_tools" / "cluster.yaml").exists()

        # Run check_onboarding — only mock SSH (network boundary)
        with patch("claudechic.onboarding.shutil.which", return_value=None), \
             patch("claudechic.onboarding.subprocess.run") as mock_run:
            # SSH check for cluster (will fail -> unconfigured)
            mock_run.return_value = MagicMock(returncode=255)
            facets = check_onboarding(dest)

        assert facets is not None
        workflow_ids = [f.workflow_id for f in facets]
        assert "cluster-setup" in workflow_ids
        assert "git-setup" in workflow_ids

    def test_no_cluster_project_omits_cluster_facet(self, no_cluster_project):
        """use_cluster=False copier project -> no cluster facet."""
        dest = no_cluster_project

        answers = yaml.safe_load(
            (dest / ".copier-answers.yml").read_text(encoding="utf-8")
        )
        assert answers.get("use_cluster") is False

        facets = check_onboarding(dest)
        assert facets is not None
        workflow_ids = [f.workflow_id for f in facets]
        assert "cluster-setup" not in workflow_ids
        # Git facet should still be present
        assert "git-setup" in workflow_ids

    def test_cluster_project_cluster_yaml_empty_backend(self, lsf_cluster_project):
        """Generated cluster.yaml has empty backend (not yet configured)."""
        cluster_yaml = lsf_cluster_project / "mcp_tools" / "cluster.yaml"
        data = yaml.safe_load(cluster_yaml.read_text(encoding="utf-8"))
        # Template generates empty strings — cluster is unconfigured by default
        assert data.get("backend") == ""

    def test_copier_project_git_facet_reflects_real_state(self, lsf_cluster_project):
        """Git facet configured status matches real .git state."""
        dest = lsf_cluster_project

        with patch("claudechic.onboarding.shutil.which", return_value=None), \
             patch("claudechic.onboarding.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=255)
            facets = check_onboarding(dest)

        assert facets is not None
        git_facet = next(f for f in facets if f.workflow_id == "git-setup")
        # copier project has .git/ from shared_copier_generation's git init,
        # and has an origin remote (the copier-generated project gets git init
        # + commit from the test fixture). Check real state:
        has_remote = _git_configured(dest)
        assert git_facet.configured == has_remote

    def test_dismiss_works_in_copier_project(self, lsf_cluster_project):
        """Dismiss marker works with real copier-generated project.

        Note: uses a temporary copy to avoid polluting the shared fixture.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Copy the copier answers file (minimal footprint)
            answers_src = lsf_cluster_project / ".copier-answers.yml"
            (tmp_path / ".copier-answers.yml").write_bytes(answers_src.read_bytes())
            # Create workflow manifests so _workflow_exists() passes
            _create_workflow_manifests(tmp_path)

            # Before dismiss: should show facets
            with patch("claudechic.onboarding.shutil.which", return_value=None), \
                 patch("claudechic.onboarding.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=255)
                assert check_onboarding(tmp_path) is not None

            # Dismiss
            store = HintStateStore(tmp_path)
            write_dismiss_marker(store)

            # After dismiss: should return None
            assert check_onboarding(tmp_path) is None


# ===========================================================================
# Unit tests: dismiss marker persistence
# ===========================================================================


class TestDismissMarker:
    """write_dismiss_marker / _is_dismissed round-trip."""

    def test_dismiss_persists(self, tmp_path):
        """write_dismiss_marker writes, reload reads it back."""
        store = HintStateStore(tmp_path)
        write_dismiss_marker(store)

        store2 = HintStateStore(tmp_path)
        assert _is_dismissed(store2)

    def test_dismissed_skips_welcome(self, tmp_path):
        """check_onboarding returns None after dismiss."""
        _write_copier_answers(tmp_path, {"use_cluster": True, "use_existing_codebase": True})
        _create_workflow_manifests(tmp_path)

        store = HintStateStore(tmp_path)
        write_dismiss_marker(store)

        result = check_onboarding(tmp_path)
        assert result is None

    def test_dismiss_survives_activation_config_sync(self, tmp_path):
        """ActivationConfig._sync_to_store() must not clobber onboarding_dismissed."""
        from claudechic.hints.state import ActivationConfig

        store = HintStateStore(tmp_path)
        write_dismiss_marker(store)
        assert _is_dismissed(store)

        config = ActivationConfig(store)
        config.disable_globally()

        assert _is_dismissed(store)

        store.save()
        store2 = HintStateStore(tmp_path)
        assert _is_dismissed(store2)
        config2 = ActivationConfig(store2)
        assert not config2.is_globally_enabled

    def test_dismiss_survives_disable_hint(self, tmp_path):
        """disable_hint() also must not clobber onboarding_dismissed."""
        from claudechic.hints.state import ActivationConfig

        store = HintStateStore(tmp_path)
        write_dismiss_marker(store)

        config = ActivationConfig(store)
        config.disable_hint("some-hint")

        store.save()
        store2 = HintStateStore(tmp_path)
        assert _is_dismissed(store2)
        config2 = ActivationConfig(store2)
        assert not config2.is_active("some-hint")


# ===========================================================================
# Unit tests: no copier answers
# ===========================================================================


class TestNoCopierAnswers:
    """check_onboarding gracefully handles missing .copier-answers.yml."""

    def test_missing_copier_answers_returns_none(self, tmp_path):
        result = check_onboarding(tmp_path)
        assert result is None


# ===========================================================================
# Unit tests: WelcomeScreen widget construction
# ===========================================================================


class TestWelcomeScreenWidget:
    """Test the WelcomeScreen widget construction and message types."""

    def test_selectable_indices_skip_configured(self):
        """Only unconfigured facets are selectable."""
        from claudechic.widgets.welcome import WelcomeScreen

        facets = _mixed_facets()
        ws = WelcomeScreen(facets, steal_focus=False)
        assert ws._selectable_indices == [1, 2]


# ===========================================================================
# E2E: Welcome screen in ChatApp (mock SDK only)
# ===========================================================================


def _app_context(tmp_path, facets):
    """ExitStack context manager suppressing auto-tasks and injecting facets."""
    stack = ExitStack()
    stack.enter_context(
        patch("claudechic.tasks.create_safe_task", return_value=MagicMock())
    )
    stack.enter_context(
        patch("claudechic.sessions.count_sessions", return_value=1)
    )
    stack.enter_context(
        patch.object(
            __import__("claudechic.app", fromlist=["ChatApp"]).ChatApp,
            "_check_onboarding",
            lambda self: None,
        )
    )
    stack.enter_context(
        patch("claudechic.onboarding.check_onboarding", return_value=facets)
    )
    return stack


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
class TestWelcomeScreenInApp:
    """E2E tests: WelcomeScreen mounts in ChatApp and responds to keys."""

    pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(30)]

    async def test_welcome_screen_mounts_with_unconfigured_facets(
        self, mock_sdk_e2e, tmp_path
    ):
        """Welcome screen appears when check_onboarding returns facets."""
        from claudechic.app import ChatApp
        from claudechic.widgets.welcome import WelcomeScreen

        app = ChatApp()

        with _app_context(tmp_path, _three_unconfigured_facets()):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app._cwd = tmp_path

                await app._check_onboarding_worker()
                await pilot.pause()

                welcome_widgets = list(app.screen.query(WelcomeScreen))
                assert len(welcome_widgets) == 1, "WelcomeScreen not mounted"

                ws = welcome_widgets[0]
                assert len(ws.facets) == 3
                assert ws._selectable_indices == [0, 1, 2]

    async def test_welcome_screen_skip_with_s_key(self, mock_sdk_e2e, tmp_path):
        """Skip removes WelcomeScreen, no persist."""
        from claudechic.app import ChatApp
        from claudechic.widgets.welcome import WelcomeScreen

        app = ChatApp()

        with _app_context(tmp_path, _three_unconfigured_facets()):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app._cwd = tmp_path

                await app._check_onboarding_worker()
                await pilot.pause()

                ws = app.screen.query_one(WelcomeScreen)
                ws.focus()
                await pilot.pause()

                ws._select_option(ws._skip_idx)
                await pilot.pause()
                await pilot.pause()

                assert len(list(app.screen.query(WelcomeScreen))) == 0

                store = HintStateStore(tmp_path)
                assert not _is_dismissed(store)

    async def test_welcome_screen_dismiss_with_d_key(self, mock_sdk_e2e, tmp_path):
        """Dismiss removes WelcomeScreen and persists marker."""
        from claudechic.app import ChatApp
        from claudechic.widgets.welcome import WelcomeScreen

        app = ChatApp()

        with _app_context(tmp_path, _three_unconfigured_facets()):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app._cwd = tmp_path

                await app._check_onboarding_worker()
                await pilot.pause()

                ws = app.screen.query_one(WelcomeScreen)
                ws.focus()
                await pilot.pause()

                ws._select_option(ws._dismiss_idx)
                await pilot.pause()
                await pilot.pause()

                assert len(list(app.screen.query(WelcomeScreen))) == 0

                store = HintStateStore(tmp_path)
                assert _is_dismissed(store)

    async def test_welcome_screen_arrow_keys_navigate(self, mock_sdk_e2e, tmp_path):
        """Arrow keys move cursor among unconfigured facets."""
        from claudechic.app import ChatApp
        from claudechic.widgets.welcome import WelcomeScreen

        app = ChatApp()

        with _app_context(tmp_path, _three_unconfigured_facets()):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app._cwd = tmp_path

                await app._check_onboarding_worker()
                await pilot.pause()

                ws = app.screen.query_one(WelcomeScreen)
                ws.focus()
                await pilot.pause()

                assert ws.selected_idx == 0

                await pilot.press("down")
                await pilot.pause()
                assert ws.selected_idx == 1

                await pilot.press("down")
                await pilot.pause()
                assert ws.selected_idx == 2

                await pilot.press("down")
                await pilot.pause()
                assert ws.selected_idx == 3  # wraps to skip option

                await pilot.press("up")
                await pilot.pause()
                assert ws.selected_idx == 2

    async def test_enter_selects_facet_and_activates_workflow(
        self, mock_sdk_e2e, tmp_path
    ):
        """Select first facet -> _activate_workflow called with cluster-setup."""
        from claudechic.app import ChatApp
        from claudechic.widgets.welcome import WelcomeScreen

        app = ChatApp()

        with _app_context(tmp_path, _three_unconfigured_facets()):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app._cwd = tmp_path

                await app._check_onboarding_worker()
                await pilot.pause()

                ws = app.screen.query_one(WelcomeScreen)
                ws.focus()
                await pilot.pause()

                captured_calls = []
                mock_create = MagicMock(
                    side_effect=lambda coro, **kw: captured_calls.append(
                        kw.get("name", "")
                    )
                )

                with patch("claudechic.tasks.create_safe_task", mock_create):
                    ws._select_option(ws.selected_idx)
                    await pilot.pause()
                    await pilot.pause()

                assert len(list(app.screen.query(WelcomeScreen))) == 0
                assert any(
                    "onboarding-cluster-setup" in c for c in captured_calls
                ), f"Expected onboarding-cluster-setup, got: {captured_calls}"

    async def test_enter_after_navigate_selects_correct_facet(
        self, mock_sdk_e2e, tmp_path
    ):
        """Navigate to second facet, select -> git-setup activated."""
        from claudechic.app import ChatApp
        from claudechic.widgets.welcome import WelcomeScreen

        app = ChatApp()

        with _app_context(tmp_path, _three_unconfigured_facets()):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app._cwd = tmp_path

                await app._check_onboarding_worker()
                await pilot.pause()

                ws = app.screen.query_one(WelcomeScreen)
                ws.focus()
                await pilot.pause()

                await pilot.press("down")
                await pilot.pause()
                assert ws.selected_idx == 1

                captured_calls = []
                mock_create = MagicMock(
                    side_effect=lambda coro, **kw: captured_calls.append(
                        kw.get("name", "")
                    )
                )

                with patch("claudechic.tasks.create_safe_task", mock_create):
                    ws._select_option(ws.selected_idx)
                    await pilot.pause()
                    await pilot.pause()

                assert any(
                    "onboarding-git-setup" in c for c in captured_calls
                ), f"Expected onboarding-git-setup, got: {captured_calls}"

