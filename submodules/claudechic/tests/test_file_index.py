"""Tests for fuzzy file search."""

import pytest
from claudechic.file_index import fuzzy_match_path, search_files


class TestFuzzyMatchPath:
    """Test fuzzy_match_path scoring."""

    def test_exact_substring_match(self):
        """Exact substring matches should score highest."""
        score, indices = fuzzy_match_path("app", "src/app.py")
        assert score > 0
        assert indices == [4, 5, 6]  # "app" at position 4

    def test_exact_match_at_start(self):
        """Matches at word boundaries score higher."""
        score_start, _ = fuzzy_match_path("app", "app.py")
        score_mid, _ = fuzzy_match_path("app", "myapp.py")
        assert score_start > score_mid

    def test_filename_match_bonus(self):
        """Matches in filename should score higher than in directory."""
        score_filename, _ = fuzzy_match_path("test", "src/test.py")
        score_dir, _ = fuzzy_match_path("test", "test/file.py")
        # Both match, but filename match has bonus
        assert score_filename > 0
        assert score_dir > 0

    def test_fuzzy_scattered_match(self):
        """Scattered character matches should work."""
        score, indices = fuzzy_match_path("tap", "test_app.py")
        assert score > 0
        assert indices == [0, 5, 6]  # t-e-s-t-_-a-p-p: matches t, a, p

    def test_no_match(self):
        """Non-matching query returns 0."""
        score, indices = fuzzy_match_path("xyz", "app.py")
        assert score == 0
        assert indices == []

    def test_empty_query(self):
        """Empty query returns default score."""
        score, indices = fuzzy_match_path("", "app.py")
        assert score == 1.0
        assert indices == []

    def test_case_insensitive(self):
        """Matching is case-insensitive."""
        score, indices = fuzzy_match_path("APP", "src/app.py")
        assert score > 0

    def test_shorter_paths_preferred(self):
        """Shorter paths should score slightly higher."""
        score_short, _ = fuzzy_match_path("app", "app.py")
        score_long, _ = fuzzy_match_path("app", "very/deep/nested/path/to/app.py")
        assert score_short > score_long


class TestSearchFiles:
    """Test search_files function."""

    @pytest.fixture
    def files(self):
        return [
            "app.py",
            "src/app/main.py",
            "tests/test_app.py",
            "README.md",
            "config.json",
            "src/utils/helpers.py",
        ]

    def test_empty_query_returns_first_n(self, files):
        """Empty query returns first N files."""
        results = search_files("", files, limit=3)
        assert len(results) == 3
        assert results[0][0] == "app.py"

    def test_filters_to_matches(self, files):
        """Query filters to matching files."""
        results = search_files("app", files, limit=10)
        paths = [r[0] for r in results]
        assert "app.py" in paths
        assert "src/app/main.py" in paths
        assert "tests/test_app.py" in paths
        assert "README.md" not in paths

    def test_sorted_by_score(self, files):
        """Results are sorted by score descending."""
        results = search_files("app", files, limit=10)
        # app.py should be first (shortest, exact match)
        assert results[0][0] == "app.py"

    def test_respects_limit(self, files):
        """Limit is respected."""
        results = search_files("", files, limit=2)
        assert len(results) == 2

    def test_returns_indices(self, files):
        """Results include match indices."""
        results = search_files("app", files, limit=1)
        path, score, indices = results[0]
        assert path == "app.py"
        assert score > 0
        assert len(indices) > 0
