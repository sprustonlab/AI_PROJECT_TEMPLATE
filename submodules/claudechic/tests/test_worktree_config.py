"""Tests for worktree path template expansion."""

from pathlib import Path
from unittest.mock import patch

import pytest

from claudechic.features.worktree.git import _expand_worktree_path, start_worktree


@pytest.fixture
def mock_worktree_deps():
    """Mock all external dependencies for start_worktree tests."""
    with (
        patch("claudechic.features.worktree.git.CONFIG") as mock_config,
        patch("claudechic.features.worktree.git.get_main_worktree") as mock_get_main,
        patch("claudechic.features.worktree.git.get_repo_name") as mock_get_repo,
        patch("claudechic.features.worktree.git.subprocess.run") as mock_run,
    ):
        yield {
            "config": mock_config,
            "get_main": mock_get_main,
            "get_repo": mock_get_repo,
            "run": mock_run,
        }


class TestWorktreePathTemplate:
    """Test worktree path template expansion."""

    @pytest.mark.parametrize(
        "template,expected",
        [
            ("/tmp/worktrees/${repo_name}", Path("/tmp/worktrees/my-repo")),
            ("/tmp/worktrees/${branch_name}", Path("/tmp/worktrees/test-feature")),
            ("$HOME/worktrees/test", Path.home() / "worktrees" / "test"),
            ("~/worktrees/test", Path.home() / "worktrees" / "test"),
        ],
    )
    def test_template_variable_expansion(self, template, expected):
        """Test template variable expansion for various variables."""
        result = _expand_worktree_path(template, "my-repo", "test-feature")
        assert result == expected.resolve()

    def test_expand_template_combined(self):
        """Test combined template with multiple variables."""
        result = _expand_worktree_path(
            "$HOME/code/worktrees/${repo_name}/${branch_name}",
            repo_name="my-repo",
            feature_name="test-feature",
        )
        expected = Path.home() / "code" / "worktrees" / "my-repo" / "test-feature"
        assert result == expected

    def test_expand_template_with_spaces_in_names(self):
        """Test handling of spaces in repo/branch names."""
        result = _expand_worktree_path(
            "/tmp/${repo_name}/${branch_name}",
            repo_name="my repo",
            feature_name="test feature",
        )
        assert result == Path("/tmp/my repo/test feature").resolve()

    def test_rejects_path_traversal_in_feature_name(self):
        """Test that path traversal in feature name is rejected."""
        with pytest.raises(ValueError, match="path traversal"):
            _expand_worktree_path(
                "/tmp/${repo_name}/${branch_name}",
                repo_name="my-repo",
                feature_name="../../etc/passwd",
            )

    def test_rejects_path_traversal_in_repo_name(self):
        """Test that path traversal in repo name is rejected."""
        with pytest.raises(ValueError, match="path traversal"):
            _expand_worktree_path(
                "/tmp/${repo_name}/${branch_name}",
                repo_name="../../../etc",
                feature_name="test-feature",
            )

    def test_rejects_relative_path_template(self):
        """Test that relative path templates are rejected."""
        with pytest.raises(ValueError, match="absolute path"):
            _expand_worktree_path(
                "relative/path/${branch_name}",
                repo_name="my-repo",
                feature_name="test-feature",
            )

    def test_rejects_path_traversal_in_template(self):
        """Test that path traversal in template itself is rejected."""
        with pytest.raises(ValueError, match="path traversal"):
            _expand_worktree_path(
                "/tmp/../../../etc/${branch_name}",
                repo_name="my-repo",
                feature_name="test-feature",
            )

    def test_rejects_empty_repo_name(self):
        """Test that empty repository name is rejected."""
        with pytest.raises(ValueError, match="Repository name cannot be empty"):
            _expand_worktree_path(
                "/tmp/${repo_name}/${branch_name}",
                repo_name="",
                feature_name="test-feature",
            )

    def test_rejects_empty_feature_name(self):
        """Test that empty feature name is rejected."""
        with pytest.raises(ValueError, match="Feature name cannot be empty"):
            _expand_worktree_path(
                "/tmp/${repo_name}/${branch_name}",
                repo_name="my-repo",
                feature_name="",
            )

    def test_rejects_whitespace_only_repo_name(self):
        """Test that whitespace-only repository name is rejected."""
        with pytest.raises(ValueError, match="Repository name cannot be empty"):
            _expand_worktree_path(
                "/tmp/${repo_name}/${branch_name}",
                repo_name="   ",
                feature_name="test-feature",
            )


class TestStartWorktreeWithConfig:
    """Test start_worktree() with path_template config."""

    def test_uses_custom_template_when_configured(self, mock_worktree_deps, tmp_path):
        """Test that custom path template is used when configured."""
        mocks = mock_worktree_deps
        mocks["get_repo"].return_value = "test-repo"
        mocks["get_main"].return_value = (Path("/original/test-repo"), "main")

        template = f"{tmp_path}/worktrees/${{repo_name}}/${{branch_name}}"
        mocks["config"].get.return_value = {"path_template": template}

        success, message, path = start_worktree("test-feature")

        expected_path = (
            tmp_path / "worktrees" / "test-repo" / "test-feature"
        ).resolve()
        assert success
        assert path == expected_path
        assert "Created worktree at" in message
        mocks["run"].assert_called_once()

    @pytest.mark.parametrize(
        "config_return",
        [
            {"path_template": None},
            {},
        ],
    )
    def test_uses_sibling_behavior_when_no_template(
        self, mock_worktree_deps, config_return
    ):
        """Test that sibling behavior is preserved when path_template is null or missing."""
        mocks = mock_worktree_deps
        mocks["get_repo"].return_value = "test-repo"
        main_worktree_path = Path("/original/test-repo")
        mocks["get_main"].return_value = (main_worktree_path, "main")
        mocks["config"].get.return_value = config_return

        success, message, path = start_worktree("test-feature")

        expected_path = Path("/original/test-repo-test-feature")
        assert success, f"Expected success but got failure: {message}"
        assert path == expected_path
        mocks["run"].assert_called_once()

    def test_creates_parent_directories_for_custom_path(
        self, mock_worktree_deps, tmp_path
    ):
        """Test that parent directories are created for custom paths."""
        mocks = mock_worktree_deps
        mocks["get_repo"].return_value = "test-repo"
        mocks["get_main"].return_value = (Path("/original/test-repo"), "main")

        template = f"{tmp_path}/deep/nested/path/${{repo_name}}/${{branch_name}}"
        mocks["config"].get.return_value = {"path_template": template}

        success, message, path = start_worktree("test-feature")

        expected_path = (
            tmp_path / "deep" / "nested" / "path" / "test-repo" / "test-feature"
        ).resolve()
        assert success
        assert path == expected_path
        assert expected_path.parent.exists()
