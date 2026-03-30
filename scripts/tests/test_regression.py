"""Snapshot regression tests for mine_patterns.py JSONL parsing.

These tests ensure that parsing output remains stable across code changes.
When the JSONL format changes (new Claude Code version), capture a new
fixture and update expected values here.

Maintenance rule: On Claude Code updates, capture a sample session as a
new fixture.  If these tests fail, update the parsing layer and re-baseline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mine_patterns import (
    parse_session,
    run_tier1,
    ParseResult,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Snapshot: main session parsing
# ---------------------------------------------------------------------------


class TestMainSessionSnapshot:
    """Regression tests against v2.1.59_main_session.jsonl."""

    @pytest.fixture
    def result(self) -> ParseResult:
        return parse_session(FIXTURES / "v2.1.59_main_session.jsonl")

    def test_message_count(self, result: ParseResult):
        assert len(result.messages) == 6

    def test_user_message_count(self, result: ParseResult):
        user_count = sum(1 for m in result.messages if m.role == "user")
        assert user_count == 3

    def test_assistant_message_count(self, result: ParseResult):
        asst_count = sum(1 for m in result.messages if m.role == "assistant")
        assert asst_count == 3

    def test_first_user_message(self, result: ParseResult):
        first_user = next(m for m in result.messages if m.role == "user")
        assert "refactor the data loading" in first_user.text

    def test_session_metadata(self, result: ParseResult):
        assert result.session_type == "main"
        assert result.session_date == "2026-03-15"
        assert result.session_id == "sess-main-001"
        assert result.workflow == "solo"

    def test_parse_stats_snapshot(self, result: ParseResult):
        s = result.stats
        assert s.total_lines == 8
        assert s.json_errors == 0
        assert s.skipped_tool_results == 1
        assert s.version == "2.1.59"


# ---------------------------------------------------------------------------
# Snapshot: sub-agent session parsing
# ---------------------------------------------------------------------------


class TestSubagentSessionSnapshot:
    """Regression tests against v2.1.59_subagent_session.jsonl."""

    @pytest.fixture
    def result(self) -> ParseResult:
        return parse_session(FIXTURES / "v2.1.59_subagent_session.jsonl")

    def test_message_count(self, result: ParseResult):
        assert len(result.messages) == 4

    def test_session_type(self, result: ParseResult):
        assert result.session_type == "sub-agent"

    def test_agent_type(self, result: ParseResult):
        assert result.agent_type == "Skeptic"

    def test_session_metadata(self, result: ParseResult):
        assert result.session_date == "2026-03-15"
        assert result.session_id == "sess-sub-001"


# ---------------------------------------------------------------------------
# Snapshot: tool results session
# ---------------------------------------------------------------------------


class TestToolResultsSnapshot:
    """Regression tests against v2.1.59_tool_results.jsonl."""

    @pytest.fixture
    def result(self) -> ParseResult:
        return parse_session(FIXTURES / "v2.1.59_tool_results.jsonl")

    def test_message_count(self, result: ParseResult):
        # 10 lines total, 1 system, 2 toolUseResult, 1 with list content
        # Real messages: 3 user + 4 assistant = 7
        assert len(result.messages) == 7

    def test_tool_results_excluded(self, result: ParseResult):
        assert result.stats.skipped_tool_results == 2

    def test_list_content_parsed(self, result: ParseResult):
        """Content in list-of-dicts format should be extracted."""
        user_msgs = [m for m in result.messages if m.role == "user"]
        texts = [m.text for m in user_msgs]
        assert any("run the tests again" in t for t in texts)


# ---------------------------------------------------------------------------
# Tier 1 regression: known correction detection
# ---------------------------------------------------------------------------


class TestTier1Regression:
    """Verify Tier 1 detects known corrections in fixtures."""

    def test_main_session_correction(self):
        result = parse_session(FIXTURES / "v2.1.59_main_session.jsonl")
        candidates = run_tier1([result], threshold=0.3)
        # "No, that's not what I asked for" should be detected
        assert len(candidates) >= 1
        indicators = [c["correction_indicator"] for c in candidates]
        assert any("not what I" in (ind or "") for ind in indicators)

    def test_subagent_correction(self):
        result = parse_session(FIXTURES / "v2.1.59_subagent_session.jsonl")
        candidates = run_tier1([result], threshold=0.3)
        # "You missed the error handling" should be detected
        assert len(candidates) >= 1
        indicators = [c["correction_indicator"] for c in candidates]
        assert any("you missed" in (ind or "").lower() for ind in indicators)

    def test_tool_session_correction(self):
        result = parse_session(FIXTURES / "v2.1.59_tool_results.jsonl")
        candidates = run_tier1([result], threshold=0.3)
        # "That's wrong" should be detected
        assert len(candidates) >= 1
        indicators = [c["correction_indicator"] for c in candidates]
        assert any("wrong" in (ind or "").lower() for ind in indicators)
