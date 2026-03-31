"""Unit tests for the JSONL parsing layer of mine_patterns.py.

Tests the isolated parsing layer (Change #1): ParseResult, Message,
ParseStats dataclasses and the parse_session() function.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

# Ensure scripts/ is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mine_patterns import (
    DEFAULT_AGENT_ROLES,
    KNOWN_VERSIONS,
    Message,
    ParseResult,
    ParseStats,
    _detect_agent_type,
    _extract_text,
    parse_session,
    tier1_score_message,
    _jaccard_similarity,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# _extract_text
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_string_content(self):
        assert _extract_text("hello world") == "hello world"

    def test_list_content(self):
        content = [
            {"type": "text", "text": "part one"},
            {"type": "image", "url": "http://example.com/img.png"},
            {"type": "text", "text": "part two"},
        ]
        result = _extract_text(content)
        assert "part one" in result
        assert "part two" in result
        assert "http://example.com" not in result

    def test_empty_list(self):
        assert _extract_text([]) == ""

    def test_none(self):
        assert _extract_text(None) == ""

    def test_number(self):
        assert _extract_text(42) == ""


# ---------------------------------------------------------------------------
# parse_session — main session fixture
# ---------------------------------------------------------------------------


class TestParseMainSession:
    @pytest.fixture
    def result(self) -> ParseResult:
        return parse_session(FIXTURES / "v2.1.59_main_session.jsonl")

    def test_returns_parse_result(self, result: ParseResult):
        assert isinstance(result, ParseResult)

    def test_messages_are_message_objects(self, result: ParseResult):
        assert all(isinstance(m, Message) for m in result.messages)

    def test_filters_tool_results(self, result: ParseResult):
        """Tool-use result messages should be excluded."""
        roles = [m.role for m in result.messages]
        # The fixture has 1 toolUseResult user message; should not appear
        user_texts = [m.text for m in result.messages if m.role == "user"]
        for t in user_texts:
            assert "toolUseResult" not in t

    def test_session_type_main(self, result: ParseResult):
        assert result.session_type == "main"

    def test_agent_type_none_for_main(self, result: ParseResult):
        assert result.agent_type is None

    def test_session_date(self, result: ParseResult):
        assert result.session_date == "2026-03-15"

    def test_session_id(self, result: ParseResult):
        assert result.session_id == "sess-main-001"

    def test_parse_stats(self, result: ParseResult):
        s = result.stats
        assert s.total_lines > 0
        assert s.json_errors == 0
        assert s.skipped_tool_results == 1  # one toolUseResult line
        assert s.version == "2.1.59"
        assert s.version_known is True

    def test_message_count(self, result: ParseResult):
        # 3 user messages (1 filtered toolUseResult) + 3 assistant = 6
        assert len(result.messages) == 6

    def test_correction_detected(self, result: ParseResult):
        """The fixture contains 'No, that's not what I asked for' — should be scorable."""
        user_msgs = [m for m in result.messages if m.role == "user"]
        # Second real user message is the correction
        correction_msg = user_msgs[1]
        assert "not what I" in correction_msg.text


# ---------------------------------------------------------------------------
# parse_session — sub-agent fixture
# ---------------------------------------------------------------------------


class TestParseSubagentSession:
    @pytest.fixture
    def result(self) -> ParseResult:
        return parse_session(FIXTURES / "v2.1.59_subagent_session.jsonl")

    def test_session_type_subagent(self, result: ParseResult):
        assert result.session_type == "sub-agent"

    def test_agent_type_detected(self, result: ParseResult):
        assert result.agent_type == "Skeptic"

    def test_version(self, result: ParseResult):
        assert result.stats.version == "2.1.59"


# ---------------------------------------------------------------------------
# parse_session — tool results fixture
# ---------------------------------------------------------------------------


class TestParseToolResults:
    @pytest.fixture
    def result(self) -> ParseResult:
        return parse_session(FIXTURES / "v2.1.59_tool_results.jsonl")

    def test_tool_results_filtered(self, result: ParseResult):
        """Two toolUseResult messages should be filtered out."""
        assert result.stats.skipped_tool_results == 2

    def test_list_content_parsed(self, result: ParseResult):
        """The last user message uses list-of-dicts content format."""
        user_msgs = [m for m in result.messages if m.role == "user"]
        last_user = user_msgs[-1]
        assert "run the tests again" in last_user.text

    def test_correction_present(self, result: ParseResult):
        """'That's wrong' message should be present."""
        texts = [m.text for m in result.messages if m.role == "user"]
        assert any("wrong" in t.lower() for t in texts)


# ---------------------------------------------------------------------------
# Version checking (Change #2)
# ---------------------------------------------------------------------------


class TestVersionChecking:
    def test_known_version_no_warning(self):
        result = parse_session(FIXTURES / "v2.1.59_main_session.jsonl")
        assert result.stats.version_known is True

    def test_unknown_version_warns(self, tmp_path: Path):
        """Unknown JSONL version should trigger a warning."""
        session_file = tmp_path / "unknown_version.jsonl"
        session_file.write_text(
            '{"type":"system","version":"99.99.99","timestamp":"2026-01-01T00:00:00Z"}\n'
            '{"type":"user","timestamp":"2026-01-01T00:00:01Z","message":{"content":"hello"}}\n'
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = parse_session(session_file)
            assert result.stats.version == "99.99.99"
            assert result.stats.version_known is False
            assert len(w) == 1
            assert "Unknown JSONL version" in str(w[0].message)


# ---------------------------------------------------------------------------
# Agent type detection (Change #5: configurable roles)
# ---------------------------------------------------------------------------


class TestAgentTypeDetection:
    def test_default_roles(self):
        text = "[Spawned by agent 'X']\n\nYou are the **Skeptic**. Review code."
        assert _detect_agent_type(text, DEFAULT_AGENT_ROLES) == "Skeptic"

    def test_custom_roles(self):
        text = "[Spawned by agent 'X']\n\nYou are the **Data Wizard**. Analyze data."
        # Not in default roles — fallback pattern should catch it
        result = _detect_agent_type(text, DEFAULT_AGENT_ROLES)
        # Fallback may or may not match; test custom list
        custom = _detect_agent_type(text, ["Data Wizard", "Code Guru"])
        assert custom == "Data Wizard"

    def test_coordinator(self):
        text = "You are the Coordinator. Manage the team."
        assert _detect_agent_type(text, DEFAULT_AGENT_ROLES) == "Coordinator"

    def test_test_engineer(self):
        text = "You are **Test Engineer** for this session."
        assert _detect_agent_type(text, DEFAULT_AGENT_ROLES) == "Test Engineer"

    def test_no_match(self):
        text = "Please implement the feature."
        assert _detect_agent_type(text, DEFAULT_AGENT_ROLES) is None


# ---------------------------------------------------------------------------
# Tier 1 scoring
# ---------------------------------------------------------------------------


class TestTier1Scoring:
    def test_correction_scores_above_zero(self):
        score, indicator = tier1_score_message(
            "No, that's not what I asked for",
            preceding_agent_text="Here is the implementation...",
            prev_user_text=None,
            is_near_session_end=False,
            turn_index=1,
            total_user_turns=5,
        )
        assert score > 0.3
        assert indicator is not None

    def test_benign_message_scores_low(self):
        score, indicator = tier1_score_message(
            "That looks great, thank you for the implementation!",
            preceding_agent_text="Here is the code...",
            prev_user_text=None,
            is_near_session_end=False,
            turn_index=1,
            total_user_turns=5,
        )
        assert score < 0.3

    def test_frustration_high_score(self):
        score, indicator = tier1_score_message(
            "You're not listening. I already said to use itertools!",
            preceding_agent_text="Let me use generators...",
            prev_user_text="Use itertools please",
            is_near_session_end=False,
            turn_index=2,
            total_user_turns=5,
        )
        assert score > 0.5
        assert indicator is not None

    def test_extra_keywords(self):
        score, _ = tier1_score_message(
            "The fluxcapacitor is miscalibrated",
            preceding_agent_text=None,
            prev_user_text=None,
            is_near_session_end=False,
            turn_index=0,
            total_user_turns=3,
            extra_keywords=["fluxcapacitor"],
        )
        assert score > 0.0


# ---------------------------------------------------------------------------
# Jaccard similarity
# ---------------------------------------------------------------------------


class TestJaccard:
    def test_identical(self):
        assert _jaccard_similarity("hello world", "hello world") == 1.0

    def test_disjoint(self):
        assert _jaccard_similarity("hello world", "foo bar") == 0.0

    def test_partial(self):
        sim = _jaccard_similarity("hello world foo", "hello world bar")
        assert 0.0 < sim < 1.0

    def test_empty(self):
        assert _jaccard_similarity("", "hello") == 0.0
