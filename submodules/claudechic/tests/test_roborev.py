"""Tests for roborev integration - models and CLI parsing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import claudechic.features.roborev.cli as roborev_cli
from claudechic.commands import _format_verdict, _is_user_command, _list_reviews_in_chat
from claudechic.features.roborev.cli import list_reviews, show_review
from claudechic.features.roborev.models import ReviewDetail, ReviewJob
from claudechic.widgets.layout.reviews import (
    ReviewItem,
    _SPINNER_FRAMES,
    has_running_reviews,
)


# =============================================================================
# ReviewJob.from_dict
# =============================================================================


class TestReviewJobFromDict:
    def test_normal_data(self):
        job = ReviewJob.from_dict(
            {
                "id": 42,
                "git_ref": "abc1234def",
                "branch": "main",
                "agent": "codex",
                "status": "done",
                "verdict": "pass",
                "addressed": False,
                "commit_subject": "Fix bug",
            }
        )
        assert job.id == "42"
        assert job.git_ref == "abc1234def"
        assert job.branch == "main"
        assert job.verdict == "pass"
        assert job.addressed is False
        assert job.commit_subject == "Fix bug"

    def test_null_fields(self):
        """Null JSON values should become empty strings, not 'None'."""
        job = ReviewJob.from_dict(
            {
                "id": None,
                "git_ref": None,
                "verdict": None,
                "commit_subject": None,
            }
        )
        assert job.id == ""
        assert job.git_ref == ""
        assert job.verdict == ""
        assert job.commit_subject == ""

    def test_missing_fields(self):
        """Missing keys should use defaults."""
        job = ReviewJob.from_dict({"id": 1})
        assert job.id == "1"
        assert job.git_ref == ""
        assert job.verdict == ""
        assert job.addressed is False

    def test_string_id(self):
        """String IDs should pass through."""
        job = ReviewJob.from_dict({"id": "abc-123"})
        assert job.id == "abc-123"


# =============================================================================
# ReviewDetail.from_dict
# =============================================================================


class TestReviewDetailFromDict:
    def test_with_nested_job(self):
        detail = ReviewDetail.from_dict(
            {
                "id": 99,
                "job_id": 42,
                "agent": "codex",
                "output": "Looks good",
                "addressed": True,
                "job": {
                    "id": 42,
                    "branch": "main",
                    "verdict": "pass",
                },
            }
        )
        assert detail.id == "99"
        assert detail.job_id == "42"
        assert detail.output == "Looks good"
        assert detail.addressed is True
        assert detail.job is not None
        assert detail.job.branch == "main"

    def test_null_job(self):
        detail = ReviewDetail.from_dict(
            {
                "id": 1,
                "job": None,
            }
        )
        assert detail.job is None

    def test_null_ids(self):
        detail = ReviewDetail.from_dict(
            {
                "id": None,
                "job_id": None,
            }
        )
        assert detail.id == ""
        assert detail.job_id == ""


# =============================================================================
# list_reviews CLI parsing
# =============================================================================


class TestListReviews:
    def test_bare_array(self, mock_roborev_output, tmp_path):
        """Parses a bare JSON array from roborev list --json."""
        mock_roborev_output(
            [
                {"id": 1, "branch": "main", "status": "done", "verdict": "pass"},
                {"id": 2, "branch": "main", "status": "running"},
            ]
        )
        reviews = list_reviews(tmp_path, branch="main")
        assert len(reviews) == 2
        assert reviews[0].id == "1"
        assert reviews[0].verdict == "pass"
        assert reviews[1].status == "running"

    def test_empty_array(self, mock_roborev_output, tmp_path):
        mock_roborev_output([])
        reviews = list_reviews(tmp_path)
        assert reviews == []

    def test_roborev_not_available(self, mock_roborev_unavailable, tmp_path):
        reviews = list_reviews(tmp_path)
        assert reviews == []

    def test_invalid_json(self, mock_roborev_output, tmp_path):
        mock_roborev_output("not json")
        reviews = list_reviews(tmp_path)
        assert reviews == []

    def test_filters_addressed(self, mock_roborev_output, tmp_path):
        """Only unaddressed reviews are returned."""
        mock_roborev_output(
            [
                {"id": 1, "status": "done", "verdict": "F", "addressed": False},
                {"id": 2, "status": "done", "verdict": "P", "addressed": True},
                {"id": 3, "status": "running", "addressed": False},
            ]
        )
        reviews = list_reviews(tmp_path)
        assert len(reviews) == 2
        assert reviews[0].id == "1"
        assert reviews[1].id == "3"

    def test_filters_by_status(self, mock_roborev_output, tmp_path):
        """Only done/running/queued/pending reviews shown; canceled/failed excluded."""
        mock_roborev_output(
            [
                {"id": 1, "status": "done", "verdict": "F", "addressed": False},
                {"id": 2, "status": "canceled", "addressed": False},
                {"id": 3, "status": "running", "addressed": False},
                {"id": 4, "status": "Canceled", "addressed": False},
                {"id": 5, "status": "failed", "addressed": False},
                {"id": 6, "status": "queued", "addressed": False},
                {"id": 7, "status": "Failed", "addressed": False},
            ]
        )
        reviews = list_reviews(tmp_path)
        assert [r.id for r in reviews] == ["1", "3", "6"]

    def test_none_or_missing_status_excluded(self, mock_roborev_output, tmp_path):
        """Reviews with None or missing status are excluded without crashing."""
        mock_roborev_output(
            [
                {"id": 1, "status": "done", "addressed": False},
                {"id": 2, "addressed": False},  # missing status -> ""
                {"id": 3, "status": None, "addressed": False},
                {"id": 4, "status": "running", "addressed": False},
            ]
        )
        reviews = list_reviews(tmp_path)
        assert [r.id for r in reviews] == ["1", "4"]

    def test_limit_applied_after_filter(self, mock_roborev_output, tmp_path):
        """Limit is applied after filtering out addressed reviews.

        Addressed reviews are interleaved within the first `limit` window so
        that if an implementation naively sliced before filtering, the test
        would fail — proving the limit is applied *after* filtering.
        """
        # 8 reviews total: 3 addressed items in positions 0, 2, 4 (inside
        # a naive limit=5 window), and 5 unaddressed items (ids 1, 3, 5, 6, 7).
        mock_roborev_output(
            [
                {"id": 0, "status": "done", "addressed": True},
                {"id": 1, "status": "done", "addressed": False},
                {"id": 2, "status": "done", "addressed": True},
                {"id": 3, "status": "done", "addressed": False},
                {"id": 4, "status": "done", "addressed": True},
                {"id": 5, "status": "done", "addressed": False},
                {"id": 6, "status": "done", "addressed": False},
                {"id": 7, "status": "done", "addressed": False},
            ]
        )
        reviews = list_reviews(tmp_path, limit=5)
        # All 5 unaddressed reviews should be returned
        assert len(reviews) == 5
        returned_ids = [r.id for r in reviews]
        assert returned_ids == ["1", "3", "5", "6", "7"]
        # Verify that id 7 (beyond a naive first-5 slice) is included
        assert "7" in returned_ids

    def test_nonzero_exit(self, mock_roborev_output, tmp_path):
        mock_roborev_output([], returncode=1, stderr="error")
        reviews = list_reviews(tmp_path)
        assert reviews == []


# =============================================================================
# show_review CLI parsing
# =============================================================================


class TestShowReview:
    def test_returns_detail(self, mock_roborev_output, tmp_path):
        mock_roborev_output(
            {
                "id": 99,
                "job_id": 42,
                "agent": "codex",
                "output": "No issues found.",
                "job": {"id": 42, "verdict": "pass", "branch": "main"},
            }
        )
        detail = show_review("42", tmp_path)
        assert detail is not None
        assert detail.id == "99"
        assert detail.job is not None
        assert detail.job.verdict == "pass"

    def test_not_found(self, mock_roborev_output, tmp_path):
        mock_roborev_output("", returncode=1, stderr="not found")
        detail = show_review("999", tmp_path)
        assert detail is None


# =============================================================================
# ReviewItem rendering
# =============================================================================


class TestReviewItemRender:
    @pytest.mark.parametrize(
        "params, check",
        [
            pytest.param({"verdict": "pass"}, ("startswith", "P "), id="pass-long"),
            pytest.param({"verdict": "P"}, ("startswith", "P "), id="pass-short"),
            pytest.param({"verdict": "fail"}, ("startswith", "F "), id="fail-long"),
            pytest.param({"verdict": "F"}, ("startswith", "F "), id="fail-short"),
            pytest.param({"verdict": ""}, ("startswith", "? "), id="unknown-verdict"),
            pytest.param({"verdict": "P"}, ("contains", "#1"), id="job-id-shown"),
            pytest.param(
                {"verdict": "", "status": "running"},
                ("spinner",),
                id="running-spinner",
            ),
            pytest.param(
                {"verdict": "", "status": "queued"},
                ("spinner",),
                id="queued-spinner",
            ),
            pytest.param(
                {"verdict": "P", "id": "0"},
                ("contains", "#0 "),
                id="zero-str-id-shown",
            ),
            pytest.param(
                {"verdict": "P", "id": ""},
                ("contains", "#? "),
                id="empty-id-fallback",
            ),
        ],
    )
    def test_render_output(self, review_item_factory, params, check):
        text = review_item_factory(**params).render()
        if check[0] == "startswith":
            assert text.plain.startswith(check[1])
        elif check[0] == "contains":
            assert check[1] in text.plain
        elif check[0] == "spinner":
            assert text.plain[0] in _SPINNER_FRAMES

    def test_non_string_status_renders(self, review_item_factory):
        """Non-string status should not crash rendering."""
        text = review_item_factory(status=123, verdict="P").render()  # type: ignore[arg-type]
        assert "#1 " in text.plain

    def test_none_verdict_renders(self, review_item_factory):
        """None verdict should not crash rendering."""
        text = review_item_factory(verdict=None).render()  # type: ignore[arg-type]
        assert "? " in text.plain

    def test_non_string_verdict_renders(self, review_item_factory):
        """Non-string verdict should not crash rendering."""
        text = review_item_factory(verdict=42).render()  # type: ignore[arg-type]
        assert "? " in text.plain

    def test_int_zero_id_shown(self):
        """Integer 0 id must render as #0, not #? (falsy-int regression guard)."""
        job = ReviewJob(id=0, verdict="P")  # type: ignore[arg-type]
        item = ReviewItem(job)
        text = item.render()
        assert "#0 " in text.plain

    def test_none_id_fallback(self):
        """None id must render as #? (null regression guard)."""
        job = ReviewJob(id=None, verdict="P")  # type: ignore[arg-type]
        item = ReviewItem(job)
        text = item.render()
        assert "#? " in text.plain

    def test_render_via_from_dict(self):
        """Render test using ReviewJob.from_dict to cover the real ingestion path."""
        job = ReviewJob.from_dict(
            {
                "id": 5,
                "git_ref": "deadbeef123",
                "commit_subject": "Add feature",
                "status": "done",
                "verdict": "pass",
            }
        )
        item = ReviewItem(job)
        text = item.render()
        assert text.plain.startswith("P ")
        assert "#5 " in text.plain
        assert "deadbee" in text.plain
        assert "Add feature" in text.plain


# =============================================================================
# has_running_reviews
# =============================================================================


class TestHasRunningReviews:
    def test_empty_list(self):
        assert has_running_reviews([]) is False

    def test_all_done(self, review_job_factory):
        jobs = [review_job_factory(status="done"), review_job_factory(status="done")]
        assert has_running_reviews(jobs) is False

    def test_running(self, review_job_factory):
        jobs = [review_job_factory(status="done"), review_job_factory(status="running")]
        assert has_running_reviews(jobs) is True

    def test_queued(self, review_job_factory):
        assert has_running_reviews([review_job_factory(status="queued")]) is True

    def test_pending(self, review_job_factory):
        assert has_running_reviews([review_job_factory(status="pending")]) is True

    def test_case_insensitive(self, review_job_factory):
        assert has_running_reviews([review_job_factory(status="Running")]) is True
        assert has_running_reviews([review_job_factory(status="QUEUED")]) is True

    def test_none_status(self, review_job_factory):
        """None status should not crash — treated as not running."""
        assert has_running_reviews([review_job_factory(status=None)]) is False  # type: ignore[arg-type]

    def test_empty_status(self, review_job_factory):
        assert has_running_reviews([review_job_factory(status="")]) is False

    def test_non_string_status(self, review_job_factory):
        """Truthy non-string status should not crash — treated as not running."""
        assert has_running_reviews([review_job_factory(status=123)]) is False  # type: ignore[arg-type]


# =============================================================================
# _is_user_command — colon-to-hyphen skill lookup
# =============================================================================


class TestIsUserCommand:
    def test_hyphenated_skill_dir(self, tmp_path):
        """Colon command matches hyphenated skill directory."""
        skill_dir = tmp_path / ".claude" / "skills" / "roborev-fix"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# skill")

        # _is_user_command checks cwd/.claude/skills/... so pass tmp_path as cwd
        assert _is_user_command("/roborev:fix", tmp_path) is True

    def test_colon_skill_dir(self, tmp_path):
        """Colon command also matches colon-named directory if it exists."""
        skill_dir = tmp_path / ".claude" / "skills" / "roborev:fix"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# skill")

        assert _is_user_command("/roborev:fix", tmp_path) is True

    def test_no_skill_dir(self, tmp_path):
        """Returns False when no matching skill directory exists."""
        # Patch Path.home so it doesn't find real skills in ~/.claude/skills/
        with patch("claudechic.commands.Path.home", return_value=tmp_path / "fakehome"):
            assert _is_user_command("/roborev:fix", tmp_path) is False

    def test_simple_skill_no_colon(self, tmp_path):
        """Non-colon skill still works normally."""
        skill_dir = tmp_path / ".claude" / "skills" / "myplugin"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# skill")

        assert _is_user_command("/myplugin", tmp_path) is True


# =============================================================================
# ReviewItem — job ID edge cases
# =============================================================================


class TestReviewItemJobId:
    def test_zero_id_shown(self, review_item_factory):
        """Job ID 0 should render as #0, not #?."""
        item = review_item_factory(verdict="P", id=0)
        text = item.render()
        assert "#0 " in text.plain

    def test_empty_id_shows_fallback(self, review_item_factory):
        """Empty/missing ID should render as #?."""
        item = review_item_factory(verdict="P", id=None)
        text = item.render()
        assert "#? " in text.plain

    def test_explicit_empty_string_id(self):
        """Explicit empty string ID should render as #?."""
        job = ReviewJob(id="", verdict="P", git_ref="abc1234", commit_subject="test")
        item = ReviewItem(job)
        text = item.render()
        assert "#? " in text.plain


# =============================================================================
# ReviewItem — non-string status/verdict resilience
# =============================================================================


class TestReviewItemNonStringFields:
    def test_non_string_status_renders(self):
        """Non-string status should not crash rendering."""
        job = ReviewJob(
            id="1",
            status=123,  # pyright: ignore[reportArgumentType]
            verdict="P",
            git_ref="abc1234",
            commit_subject="test",
        )
        item = ReviewItem(job)
        text = item.render()
        assert "#1 " in text.plain

    def test_none_verdict_renders(self):
        """None verdict should not crash rendering."""
        job = ReviewJob(id="1", verdict=None, git_ref="abc1234", commit_subject="test")  # type: ignore[arg-type]
        item = ReviewItem(job)
        text = item.render()
        assert "? " in text.plain

    def test_non_string_verdict_renders(self):
        """Non-string verdict should not crash rendering."""
        job = ReviewJob(id="1", verdict=42, git_ref="abc1234", commit_subject="test")  # type: ignore[arg-type]
        item = ReviewItem(job)
        text = item.render()
        assert "? " in text.plain


# =============================================================================
# Verdict coercion in /reviews table
# =============================================================================


class TestFormatVerdict:
    """Test _format_verdict from commands.py (used by /reviews table)."""

    def test_normal_pass(self):
        assert _format_verdict("pass") == "P"

    def test_normal_fail(self):
        assert _format_verdict("F") == "F"

    def test_none_verdict(self):
        assert _format_verdict(None) == "…"

    def test_int_verdict(self):
        assert _format_verdict(42) == "…"

    def test_empty_string(self):
        assert _format_verdict("") == "…"


# =============================================================================
# Table escaping in _list_reviews_in_chat
# =============================================================================


class TestListReviewsInChatEscaping:
    """Ensure pipes, newlines, and non-string commit_subject don't break the table."""

    @staticmethod
    def _make_mock_app() -> MagicMock:
        """Build a mock app whose _agent.cwd and _chat_view are wired up."""
        app = MagicMock()
        app._agent.cwd = "/fake"
        chat_view = MagicMock()
        mounted_widgets: list = []
        chat_view.mount = lambda msg: mounted_widgets.append(msg)
        app._chat_view = chat_view
        app._mounted_widgets = mounted_widgets
        return app

    @pytest.mark.asyncio
    async def test_pipe_in_subject_escaped(self):
        """Pipe characters in commit_subject must be escaped in the table."""
        reviews = [
            ReviewJob(
                id="1",
                git_ref="abc1234",
                commit_subject="foo | bar",
                status="done",
                verdict="pass",
                agent="bot",
            )
        ]
        app = self._make_mock_app()
        with (
            patch(
                "claudechic.features.roborev.get_current_branch",
                return_value="main",
            ),
            patch("claudechic.features.roborev.list_reviews", return_value=reviews),
        ):
            await _list_reviews_in_chat(app)

        table = app._mounted_widgets[0].get_raw_content()
        # The pipe must be escaped so it doesn't split the table cell
        assert r"foo \| bar" in table

    @pytest.mark.asyncio
    async def test_newline_in_agent_normalized(self):
        """Newlines in agent name must be replaced with spaces."""
        reviews = [
            ReviewJob(
                id="2",
                git_ref="def5678",
                commit_subject="ok",
                status="done",
                verdict="fail",
                agent="line1\nline2",
            )
        ]
        app = self._make_mock_app()
        with (
            patch(
                "claudechic.features.roborev.get_current_branch",
                return_value="main",
            ),
            patch("claudechic.features.roborev.list_reviews", return_value=reviews),
        ):
            await _list_reviews_in_chat(app)

        table = app._mounted_widgets[0].get_raw_content()
        # No raw newline should appear inside a table row
        for line in table.split("\n"):
            if line.startswith("|") and "2" in line:
                assert "\n" not in line
                assert "line1 line2" in line

    @pytest.mark.asyncio
    async def test_non_string_commit_subject(self):
        """Non-string commit_subject (e.g. int from malformed JSON) doesn't crash."""
        job = ReviewJob.from_dict(
            {
                "id": 3,
                "git_ref": "1234567",
                "commit_subject": 12345,
                "status": "done",
                "verdict": "pass",
                "agent": "bot",
            }
        )
        reviews = [job]
        app = self._make_mock_app()
        with (
            patch(
                "claudechic.features.roborev.get_current_branch",
                return_value="main",
            ),
            patch("claudechic.features.roborev.list_reviews", return_value=reviews),
        ):
            await _list_reviews_in_chat(app)

        table = app._mounted_widgets[0].get_raw_content()
        # Should contain the coerced subject as a string
        assert "12345" in table


# =============================================================================
# is_roborev_available TTL cache
# =============================================================================


class TestIsRoborevAvailableCache:
    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        """Safely reset roborev cache state via patch (auto-restores on teardown)."""
        with (
            patch.object(roborev_cli, "_roborev_available", None),
            patch.object(roborev_cli, "_roborev_checked_at", 0.0),
        ):
            yield

    def test_caches_within_ttl(self):
        """Result is cached — shutil.which is not called again within TTL."""
        with patch(
            "claudechic.features.roborev.cli.shutil.which",
            return_value="/usr/bin/roborev",
        ) as mock_which:
            assert roborev_cli.is_roborev_available() is True
            assert roborev_cli.is_roborev_available() is True
            assert mock_which.call_count == 1  # cached, not called twice

    def test_refreshes_after_ttl(self):
        """Cache refreshes after TTL expires."""
        with (
            patch(
                "claudechic.features.roborev.cli.shutil.which",
                return_value="/usr/bin/roborev",
            ) as mock_which,
            patch(
                "claudechic.features.roborev.cli.time.monotonic",
                side_effect=[0.0, 0.5, 61.0, 61.0],
            ),
        ):
            assert (
                roborev_cli.is_roborev_available() is True
            )  # monotonic=0.0, calls which
            assert roborev_cli.is_roborev_available() is True  # monotonic=0.5, cached
            assert (
                roborev_cli.is_roborev_available() is True
            )  # monotonic=61.0, expired, calls which again
            assert mock_which.call_count == 2
