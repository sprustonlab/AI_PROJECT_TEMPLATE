"""Intent-based integration tests for the audit workflow.

These tests simulate what a user actually DOES through the audit pipeline:
create JSONL session files, create chicsessions, then drive the full audit
pipeline through the Python API the way agents would.

NOT unit tests of functions -- these are end-to-end workflow simulations.

Cross-platform: encoding='utf-8' everywhere, pathlib.Path, ASCII only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from scripts.audit import db
from scripts.audit.audit import (
    BOILERPLATE_PREFIXES,
    cmd_extract,
    cmd_status,
)

# We need the chicsession classes to build fixtures
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "submodules" / "claudechic")
)
from claudechic.chicsessions import (
    Chicsession,
    ChicsessionEntry,
    ChicsessionManager,
)

# ---------------------------------------------------------------------------
# Mark all tests as integration (>1s each)
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fake JSONL builders -- realistic Claude conversation data
# ---------------------------------------------------------------------------


def _jsonl_line(
    msg_type: str,
    content: str,
    session_id: str = "sess-001",
    timestamp: str = "2026-04-10T12:00:00Z",
    *,
    tool_use_result: bool = False,
    version: str | None = None,
) -> str:
    """Build a single JSONL line mimicking Claude Code session format."""
    obj: dict[str, Any] = {
        "type": msg_type,
        "sessionId": session_id,
        "timestamp": timestamp,
        "message": {"content": content},
    }
    if tool_use_result:
        obj["toolUseResult"] = {"content": "ok"}
    if version:
        obj["version"] = version
    return json.dumps(obj, ensure_ascii=True)


def _build_conversation(
    session_id: str,
    messages: list[tuple[str, str]],
    *,
    version: str = "2.2.1",
) -> str:
    """Build a full JSONL session from a list of (role, text) tuples.

    Adds a version header line automatically.
    """
    lines: list[str] = []
    # Version header
    lines.append(
        json.dumps(
            {"type": "system", "version": version, "sessionId": session_id},
            ensure_ascii=True,
        )
    )
    for role, text in messages:
        lines.append(_jsonl_line(role, text, session_id=session_id))
    return "\n".join(lines) + "\n"


# A realistic first session: normal work + clear corrections + boilerplate
SESSION_1_MESSAGES: list[tuple[str, str]] = [
    ("user", "Please write a function that reads a CSV file and returns a dict"),
    (
        "assistant",
        "Here is a function using the csv module:\n\ndef read_csv(path):\n    import csv\n    ...",
    ),
    ("user", "No, that's wrong -- use pathlib not os.path for the file handling"),
    (
        "assistant",
        "You are right, let me fix that to use pathlib.Path:\n\ndef read_csv(path: Path):\n    ...",
    ),
    ("user", "Actually let's try a different approach -- use pandas instead"),
    ("assistant", "Sure, here is a pandas-based version:\n\nimport pandas as pd\n..."),
    ("user", "Good, now add error handling for missing files"),
    ("assistant", "Added a try/except FileNotFoundError block."),
    ("user", "[Request interrupted by user]"),  # boilerplate
    ("user", "You missed the encoding parameter -- always pass encoding='utf-8'"),
    ("assistant", "Fixed, now passing encoding='utf-8' to all open() calls."),
    ("user", "That's not correct, the pandas read_csv uses a different parameter name"),
    (
        "assistant",
        "Apologies, for pandas it is the encoding= kwarg on pd.read_csv(). Fixed.",
    ),
]

# A second session: more corrections, different patterns
SESSION_2_MESSAGES: list[tuple[str, str]] = [
    ("user", "Write tests for the CSV reader"),
    (
        "assistant",
        "Here are pytest tests for the CSV reader:\n\ndef test_read_csv():\n    ...",
    ),
    ("user", "Don't do that -- use tmp_path fixture, not hardcoded paths"),
    ("assistant", "Updated to use tmp_path fixture."),
    ("user", "I already said to use pathlib everywhere, you keep using os.path"),
    ("assistant", "Sorry about that. Switching to pathlib.Path for all test paths."),
    ("user", "Please just read CLAUDE.md before making more changes"),
    ("assistant", "I have read CLAUDE.md. I see the pathlib requirement now."),
    ("user", "[Spawned by agent 'test-runner']"),  # boilerplate
    ("user", "Run the tests now"),
    ("assistant", "Running pytest... all tests pass."),
]

# A third session added later for incremental testing
SESSION_3_MESSAGES: list[tuple[str, str]] = [
    ("user", "Refactor the config module to use dataclasses"),
    (
        "assistant",
        "Here is the refactored config using dataclasses:\n\n@dataclass\nclass Config:\n    ...",
    ),
    ("user", "That's wrong -- you forgot to add __post_init__ validation"),
    ("assistant", "Added __post_init__ with validation."),
    ("user", "Stop doing that -- don't import typing.Optional, use X | None syntax"),
    ("assistant", "Fixed, now using PEP 604 union syntax throughout."),
    ("user", "Good, looks correct now"),
    ("assistant", "Great, the refactoring is complete."),
]


# ---------------------------------------------------------------------------
# Fixture: project root with chicsessions and JSONL files
# ---------------------------------------------------------------------------


@pytest.fixture()
def audit_project(tmp_path: Path) -> dict[str, Any]:
    """Set up a fake project with chicsessions and JSONL session files.

    Returns a dict with paths and helpers for driving the audit pipeline.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()

    # Create a fake .claude/projects/<key>/ directory for JSONL files
    project_dir = project_root / ".claude" / "projects" / "fake-project"
    project_dir.mkdir(parents=True)

    # Write session 1 JSONL
    sess1_path = project_dir / "sess-001.jsonl"
    sess1_path.write_text(
        _build_conversation("sess-001", SESSION_1_MESSAGES),
        encoding="utf-8",
    )

    # Write session 2 JSONL
    sess2_path = project_dir / "sess-002.jsonl"
    sess2_path.write_text(
        _build_conversation("sess-002", SESSION_2_MESSAGES),
        encoding="utf-8",
    )

    # Create chicsession for sessions 1+2
    mgr = ChicsessionManager(project_root)
    cs1 = Chicsession(
        name="feature-csv-reader",
        active_agent="coder",
        agents=[
            ChicsessionEntry(
                name="coder", session_id="sess-001", cwd=str(project_root)
            ),
            ChicsessionEntry(
                name="tester", session_id="sess-002", cwd=str(project_root)
            ),
        ],
        workflow_state={"workflow_id": "project_team", "current_phase": "implement"},
    )
    mgr.save(cs1)

    return {
        "project_root": project_root,
        "project_dir": project_dir,
        "mgr": mgr,
        "sess1_path": sess1_path,
        "sess2_path": sess2_path,
    }


def _make_namespace(**kwargs: Any) -> Any:
    """Build a fake argparse.Namespace for calling cmd_* functions directly."""
    import argparse

    ns = argparse.Namespace()
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


def _capture_json_stdout(func, args, project_root: Path) -> Any:
    """Call a cmd_* function and capture its JSON stdout output."""
    import io
    from unittest.mock import patch

    buf = io.StringIO()
    with patch("sys.stdout", buf):
        func(args, project_root)
    output = buf.getvalue().strip()
    if not output:
        return None
    return json.loads(output)


def _feed_stdin_and_call(func, args, project_root: Path, stdin_data: str) -> Any:
    """Call a cmd_* function with fake stdin, capture stdout."""
    import io
    from unittest.mock import patch

    stdin_buf = io.StringIO(stdin_data)
    stdout_buf = io.StringIO()
    with patch("sys.stdin", stdin_buf), patch("sys.stdout", stdout_buf):
        func(args, project_root)
    output = stdout_buf.getvalue().strip()
    if not output:
        return None
    return json.loads(output)


# ---------------------------------------------------------------------------
# Helper: classify all unclassified messages with a simple heuristic
# ---------------------------------------------------------------------------


def _auto_classify(conn, *, mark_corrections: bool = True) -> int:
    """Classify all unclassified messages using regex score as a proxy.

    Simulates what the classifier agent would do.
    Returns number of classifications stored.
    """
    result = db.query_unclassified(conn, chunk_size=9999)
    items = result["items"]
    classifications: list[dict[str, Any]] = []
    for item in items:
        text = item["user_text"]
        score = item.get("regex_score", 0.0) or 0.0
        is_correction = 1 if (mark_corrections and score >= 0.2) else 0
        category = None
        confidence = "medium"
        if is_correction:
            if "path" in text.lower() or "pathlib" in text.lower():
                category = "wrong-tool-choice"
            elif "wrong" in text.lower() or "not correct" in text.lower():
                category = "factual-error"
            elif "stop" in text.lower() or "don't" in text.lower():
                category = "instruction-violation"
            elif "missed" in text.lower() or "forgot" in text.lower():
                category = "missing-requirement"
            else:
                category = "other-correction"
            confidence = "high" if score >= 0.4 else "medium"
        classifications.append(
            {
                "message_id": item["id"],
                "is_correction": is_correction,
                "category": category,
                "confidence": confidence,
            }
        )
    stored, skipped = db.store_classifications(conn, classifications)
    return stored


def _make_suggestions(
    conn,
    *,
    evidence_message_ids: list[int] | None = None,
) -> list[int]:
    """Create realistic suggestions linked to correction evidence.

    Simulates what the judge agent would produce.
    """
    if evidence_message_ids is None:
        # Grab all correction message IDs
        rows = conn.execute(
            "SELECT m.id FROM messages m "
            "JOIN classifications c ON m.id = c.message_id "
            "WHERE c.is_correction = 1 ORDER BY m.id"
        ).fetchall()
        evidence_message_ids = [r[0] for r in rows]

    suggestions = [
        {
            "artifact_type": "phase-markdown",
            "file_path": "workflows/project_team/coder/implement.md",
            "suggestion_type": "modify",
            "current_content": "## File handling\nUse standard library.",
            "proposed_content": "## File handling\nALWAYS use pathlib.Path. NEVER use os.path.",
            "rationale": "Multiple corrections about using os.path instead of pathlib",
            "evidence_count": len(evidence_message_ids),
            "priority": 2,
            "evidence_message_ids": evidence_message_ids[:3],
        },
        {
            "artifact_type": "rule",
            "file_path": "global/rules.yaml",
            "suggestion_type": "add",
            "insertion_point": "after: no_pip_install",
            "proposed_content": "- id: always_utf8\n  pattern: open(.*)\n  message: Always pass encoding='utf-8'",
            "rationale": "Repeated corrections about missing encoding parameter",
            "evidence_count": max(1, len(evidence_message_ids) // 2),
            "priority": 1,
            "evidence_message_ids": evidence_message_ids[1:4]
            if len(evidence_message_ids) > 1
            else evidence_message_ids,
        },
        {
            "artifact_type": "hint",
            "file_path": "global/hints.yaml",
            "suggestion_type": "add",
            "proposed_content": "- id: read_claude_md\n  text: Read CLAUDE.md before starting work",
            "rationale": "User asked agent to read CLAUDE.md -- hint could pre-empt this",
            "evidence_count": 1,
            "priority": 3,
            "evidence_message_ids": evidence_message_ids[:1],
        },
    ]
    return db.store_suggestions(conn, suggestions)


# ===========================================================================
# INTENT 1: First audit -- never run before
# ===========================================================================


class TestIntent1_FirstAudit:
    """User has never run the audit. No DB, no previous data."""

    def test_status_shows_no_database(self, audit_project: dict[str, Any]) -> None:
        """status command reports no database when none exists."""
        root = audit_project["project_root"]
        result = _capture_json_stdout(
            cmd_status,
            _make_namespace(json=True),
            root,
        )
        assert result["db_exists"] is False
        assert result["messages"] == 0

    def test_full_first_audit_pipeline(self, audit_project: dict[str, Any]) -> None:
        """End-to-end: extract -> unclassified -> classify -> aggregate -> suggest -> status."""
        root = audit_project["project_root"]
        project_dir = audit_project["project_dir"]

        # -- Step 1: Extract messages from the chicsession --
        ns = _make_namespace(
            sessions="feature-csv-reader",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns, root)

        # Verify DB was created
        assert db.db_exists(root)
        conn = db.open_db(root, create=False)

        # Check messages were extracted
        total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        assert total > 0, "Expected messages to be extracted"

        # Verify boilerplate was marked
        boilerplate = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE is_boilerplate = 1"
        ).fetchone()[0]
        assert boilerplate >= 2, (
            "Expected at least 2 boilerplate messages (interrupted + spawned)"
        )

        # Verify non-boilerplate user messages exist
        non_bp = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE is_boilerplate = 0"
        ).fetchone()[0]
        assert non_bp > 0

        # -- Step 2: Query unclassified --
        uncl = db.query_unclassified(conn)
        assert len(uncl["items"]) == non_bp, (
            "All non-boilerplate messages should be unclassified initially"
        )
        # Verify context is populated
        for item in uncl["items"]:
            assert item["user_text"], "user_text must not be empty"

        # -- Step 3: Classify (simulate classifier agent) --
        classified_count = _auto_classify(conn)
        assert classified_count == non_bp

        # Verify corrections were detected
        corrections = conn.execute(
            "SELECT COUNT(*) FROM classifications WHERE is_correction = 1"
        ).fetchone()[0]
        assert corrections >= 3, (
            f"Expected at least 3 corrections from test data, got {corrections}"
        )

        # Verify no unclassified remain
        uncl_after = db.query_unclassified(conn)
        assert len(uncl_after["items"]) == 0

        # -- Step 4: Aggregate patterns --
        # Use min_count=1 since we have limited test data
        patterns = db.aggregate_corrections(conn, min_count=1)
        assert len(patterns) > 0, "Expected at least one aggregated pattern"

        # Verify pattern structure
        for p in patterns:
            assert "pattern_id" in p
            assert "category" in p
            assert "correction_count" in p
            assert p["correction_count"] >= 1
            assert "top_examples" in p
            assert len(p["top_examples"]) > 0

        # -- Step 5: Store suggestions (simulate judge agent) --
        suggestion_ids = _make_suggestions(conn)
        assert len(suggestion_ids) == 3

        # -- Step 6: Verify status reflects the full pipeline --
        status = db.get_status(conn)
        assert status["messages"] == total
        assert status["classified"] == non_bp
        assert status["unclassified"] == 0
        assert status["corrections"] == corrections
        assert status["suggestions"] == 3
        assert status["pending"] == 3  # all suggestions start as pending
        assert status["unreviewed"] == 3  # no critic verdicts yet
        assert "feature-csv-reader" in status["chicsessions_processed"]

        conn.close()

    def test_regex_scoring_flags_corrections(
        self, audit_project: dict[str, Any]
    ) -> None:
        """Regex scorer should flag obvious corrections with score >= 0.3."""
        root = audit_project["project_root"]
        project_dir = audit_project["project_dir"]

        ns = _make_namespace(
            sessions="feature-csv-reader",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns, root)

        conn = db.open_db(root, create=False)
        flagged = conn.execute(
            "SELECT user_text, regex_score, regex_indicator "
            "FROM messages WHERE regex_score >= 0.3 AND is_boilerplate = 0"
        ).fetchall()
        conn.close()

        assert len(flagged) >= 3, (
            f"Expected at least 3 regex-flagged messages, got {len(flagged)}"
        )

        # Verify the obvious corrections were caught
        flagged_texts = [r["user_text"] for r in flagged]
        # "No, that's wrong" should definitely be caught
        assert any("wrong" in t.lower() for t in flagged_texts)


# ===========================================================================
# INTENT 2: Re-audit -- incremental extraction of new sessions
# ===========================================================================


class TestIntent2_IncrementalAudit:
    """User ran audit before, now has new sessions to process."""

    def test_incremental_extraction(self, audit_project: dict[str, Any]) -> None:
        """Only new messages extracted on second run; old data preserved."""
        root = audit_project["project_root"]
        project_dir = audit_project["project_dir"]
        mgr = audit_project["mgr"]

        # -- First extraction: process feature-csv-reader --
        ns = _make_namespace(
            sessions="feature-csv-reader",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns, root)

        conn = db.open_db(root, create=False)
        count_after_first = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        assert count_after_first > 0

        # Classify the first batch
        _auto_classify(conn)
        first_corrections = conn.execute(
            "SELECT COUNT(*) FROM classifications WHERE is_correction = 1"
        ).fetchone()[0]
        conn.close()

        # -- Add a new session (session 3) and a new chicsession --
        sess3_path = project_dir / "sess-003.jsonl"
        sess3_path.write_text(
            _build_conversation("sess-003", SESSION_3_MESSAGES),
            encoding="utf-8",
        )

        cs2 = Chicsession(
            name="refactor-config",
            active_agent="coder",
            agents=[
                ChicsessionEntry(name="coder", session_id="sess-003", cwd=str(root)),
            ],
            workflow_state={
                "workflow_id": "project_team",
                "current_phase": "implement",
            },
        )
        mgr.save(cs2)

        # -- Second extraction: only new chicsession --
        ns2 = _make_namespace(
            sessions="refactor-config",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns2, root)

        conn = db.open_db(root, create=False)
        count_after_second = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        assert count_after_second > count_after_first, (
            "New messages should have been added"
        )

        # Old classifications still there
        old_classifications = conn.execute(
            "SELECT COUNT(*) FROM classifications WHERE is_correction = 1"
        ).fetchone()[0]
        assert old_classifications == first_corrections

        # Only new messages are unclassified
        uncl = db.query_unclassified(conn)
        new_non_bp = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE is_boilerplate = 0 "
            "AND chicsession_name = 'refactor-config'"
        ).fetchone()[0]
        assert len(uncl["items"]) == new_non_bp

        # Classify the new batch
        _auto_classify(conn)

        # Now aggregate includes both old and new
        all_corrections = conn.execute(
            "SELECT COUNT(*) FROM classifications WHERE is_correction = 1"
        ).fetchone()[0]
        assert all_corrections > first_corrections

        conn.close()

    def test_reextract_same_session_is_noop(
        self, audit_project: dict[str, Any]
    ) -> None:
        """Re-extracting the same unchanged session adds zero new messages."""
        root = audit_project["project_root"]
        project_dir = audit_project["project_dir"]

        ns = _make_namespace(
            sessions="feature-csv-reader",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns, root)

        conn = db.open_db(root, create=False)
        count1 = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        conn.close()

        # Extract again -- same files, same size, same mtime
        cmd_extract(ns, root)

        conn = db.open_db(root, create=False)
        count2 = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        conn.close()

        assert count2 == count1, "No new messages should be added on re-extract"


# ===========================================================================
# INTENT 3: Full re-audit -- process everything again
# ===========================================================================


class TestIntent3_FullReaudit:
    """User wants to re-process all sessions from scratch."""

    def test_extract_all_with_dedup(self, audit_project: dict[str, Any]) -> None:
        """--all processes all chicsessions; dedup prevents duplicates."""
        root = audit_project["project_root"]
        project_dir = audit_project["project_dir"]
        mgr = audit_project["mgr"]

        # Add a second chicsession
        sess3_path = project_dir / "sess-003.jsonl"
        sess3_path.write_text(
            _build_conversation("sess-003", SESSION_3_MESSAGES),
            encoding="utf-8",
        )
        cs2 = Chicsession(
            name="refactor-config",
            active_agent="coder",
            agents=[
                ChicsessionEntry(name="coder", session_id="sess-003", cwd=str(root)),
            ],
        )
        mgr.save(cs2)

        # First: extract just one
        ns1 = _make_namespace(
            sessions="feature-csv-reader",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns1, root)

        conn = db.open_db(root, create=False)
        count_partial = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        conn.close()

        # Now: extract --all (includes both chicsessions)
        ns_all = _make_namespace(
            sessions=None,
            all=True,
            project_dir=str(project_dir),
        )
        cmd_extract(ns_all, root)

        conn = db.open_db(root, create=False)
        count_all = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

        # Should have added session 3 messages on top of the original ones
        # but NOT duplicated sessions 1 and 2 (skipped via processed_files)
        sess3_count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE chicsession_name = 'refactor-config'"
        ).fetchone()[0]
        assert sess3_count > 0, "Session 3 messages should be present"
        assert count_all == count_partial + sess3_count

        # Verify no duplicate hashes
        dup_check = conn.execute(
            "SELECT message_hash, COUNT(*) as cnt FROM messages "
            "GROUP BY message_hash HAVING cnt > 1"
        ).fetchall()
        assert len(dup_check) == 0, "No duplicate message hashes should exist"

        conn.close()


# ===========================================================================
# INTENT 4: Iterate on suggestions -- reset and redo
# ===========================================================================


class TestIntent4_IterateSuggestions:
    """User wants to clear suggestions and regenerate them."""

    def test_reset_suggestions_preserves_classifications(
        self, audit_project: dict[str, Any]
    ) -> None:
        """reset suggestions clears suggestions but keeps classifications."""
        root = audit_project["project_root"]
        project_dir = audit_project["project_dir"]

        # Build up state: extract -> classify -> suggest
        ns = _make_namespace(
            sessions="feature-csv-reader",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns, root)

        conn = db.open_db(root)
        _auto_classify(conn)
        original_classifications = conn.execute(
            "SELECT COUNT(*) FROM classifications"
        ).fetchone()[0]

        _make_suggestions(conn)
        assert conn.execute("SELECT COUNT(*) FROM suggestions").fetchone()[0] == 3

        # Reset suggestions
        deleted = db.reset_suggestions(conn)
        assert deleted == 3

        # Classifications still intact
        after_reset = conn.execute("SELECT COUNT(*) FROM classifications").fetchone()[0]
        assert after_reset == original_classifications

        # Suggestions table is empty
        assert conn.execute("SELECT COUNT(*) FROM suggestions").fetchone()[0] == 0

        # Can re-create fresh suggestions
        new_ids = _make_suggestions(conn)
        assert len(new_ids) == 3
        assert conn.execute("SELECT COUNT(*) FROM suggestions").fetchone()[0] == 3

        conn.close()


# ===========================================================================
# INTENT 5: Critic rejects a suggestion
# ===========================================================================


class TestIntent5_CriticReview:
    """Critic agent reviews suggestions -- approve, flag, reject."""

    def test_critic_verdict_flow(self, audit_project: dict[str, Any]) -> None:
        """Store suggestions, apply critic verdicts, verify checks pass."""
        root = audit_project["project_root"]
        project_dir = audit_project["project_dir"]

        ns = _make_namespace(
            sessions="feature-csv-reader",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns, root)

        conn = db.open_db(root)
        _auto_classify(conn)
        sug_ids = _make_suggestions(conn)
        assert len(sug_ids) == 3

        # Before review: check all-reviewed should FAIL
        ok, msg = db.check_all_reviewed(conn)
        assert not ok
        assert "unreviewed" in msg.lower() or "FAIL" in msg

        # Critic reviews: APPROVE first, FLAG second, REJECT third
        db.update_suggestion(
            conn,
            sug_ids[0],
            {
                "critic_verdict": "APPROVE",
                "critic_reasoning": "Well-supported by evidence, specific and actionable.",
            },
        )
        db.update_suggestion(
            conn,
            sug_ids[1],
            {
                "critic_verdict": "FLAG",
                "critic_reasoning": "Needs more specificity in the rule pattern.",
            },
        )
        db.update_suggestion(
            conn,
            sug_ids[2],
            {
                "critic_verdict": "REJECT",
                "critic_reasoning": "Too vague, hint text needs concrete guidance.",
            },
        )

        # After review: check all-reviewed should PASS
        ok, msg = db.check_all_reviewed(conn)
        assert ok
        assert "PASS" in msg

        # Verify verdicts are stored correctly
        verdicts = {}
        for sid in sug_ids:
            row = conn.execute(
                "SELECT critic_verdict FROM suggestions WHERE id = ?", (sid,)
            ).fetchone()
            verdicts[sid] = row["critic_verdict"]
        assert verdicts[sug_ids[0]] == "APPROVE"
        assert verdicts[sug_ids[1]] == "FLAG"
        assert verdicts[sug_ids[2]] == "REJECT"

        conn.close()


# ===========================================================================
# INTENT 6: Apply approved suggestions
# ===========================================================================


class TestIntent6_ApplyDecisions:
    """User decides which suggestions to apply or skip."""

    def test_apply_skip_flow(self, audit_project: dict[str, Any]) -> None:
        """Mark suggestions as apply/skip, verify check all-decided passes."""
        root = audit_project["project_root"]
        project_dir = audit_project["project_dir"]

        ns = _make_namespace(
            sessions="feature-csv-reader",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns, root)

        conn = db.open_db(root)
        _auto_classify(conn)
        sug_ids = _make_suggestions(conn)

        # Apply critic verdicts first
        for sid in sug_ids:
            db.update_suggestion(conn, sid, {"critic_verdict": "APPROVE"})

        # Before decisions: all-decided should FAIL (all still "pending")
        ok, msg = db.check_all_decided(conn)
        assert not ok
        assert "pending" in msg.lower() or "FAIL" in msg

        # User applies first two, skips the third
        db.update_suggestion(conn, sug_ids[0], {"apply_status": "applied"})
        db.update_suggestion(conn, sug_ids[1], {"apply_status": "applied"})
        db.update_suggestion(conn, sug_ids[2], {"apply_status": "skipped"})

        # After decisions: all-decided should PASS
        ok, msg = db.check_all_decided(conn)
        assert ok
        assert "PASS" in msg

        # Verify status reflects the decisions
        status = db.get_status(conn)
        assert status["applied"] == 2
        assert status["skipped"] == 1
        assert status["pending"] == 0

        # Verify corrections query still works (for report phase)
        corrections = db.query_corrections(conn)
        assert len(corrections["items"]) > 0

        conn.close()


# ===========================================================================
# INTENT cross-cutting: CLI-level invocation through subprocess
# ===========================================================================


class TestCLIInvocation:
    """Verify the CLI can be invoked as a subprocess (like agents do)."""

    def test_status_cli_no_db(self, audit_project: dict[str, Any]) -> None:
        """audit.py status --json works when no DB exists."""
        root = audit_project["project_root"]
        result = subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parent.parent
                    / "scripts"
                    / "audit"
                    / "audit.py"
                ),
                "--project-root",
                str(root),
                "status",
                "--json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["db_exists"] is False

    def test_check_has_db_cli(self, audit_project: dict[str, Any]) -> None:
        """audit.py check has-db returns exit code 1 when no DB."""
        root = audit_project["project_root"]
        result = subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parent.parent
                    / "scripts"
                    / "audit"
                    / "audit.py"
                ),
                "--project-root",
                str(root),
                "check",
                "has-db",
                "--json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert result.returncode == 1
        data = json.loads(result.stdout)
        assert data["pass"] is False

    def test_store_classifications_via_stdin(
        self, audit_project: dict[str, Any]
    ) -> None:
        """store-classifications reads JSON from stdin (how agents use it)."""
        root = audit_project["project_root"]
        project_dir = audit_project["project_dir"]

        # First extract
        ns = _make_namespace(
            sessions="feature-csv-reader",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns, root)

        # Get message IDs
        conn = db.open_db(root, create=False)
        uncl = db.query_unclassified(conn)
        conn.close()

        # Build classification JSON
        classifications = []
        for item in uncl["items"]:
            classifications.append(
                {
                    "message_id": item["id"],
                    "is_correction": 0,
                    "category": None,
                    "confidence": "low",
                }
            )

        # Feed via subprocess stdin
        audit_script = str(
            Path(__file__).resolve().parent.parent / "scripts" / "audit" / "audit.py"
        )
        result = subprocess.run(
            [
                sys.executable,
                audit_script,
                "--project-root",
                str(root),
                "store-classifications",
            ],
            input=json.dumps(classifications),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        # Verify all classified
        conn = db.open_db(root, create=False)
        ok, msg = db.check_all_classified(conn)
        conn.close()
        assert ok


# ===========================================================================
# INTENT cross-cutting: boilerplate filtering
# ===========================================================================


class TestBoilerplateFiltering:
    """Verify that system noise is filtered from the analysis pipeline."""

    def test_boilerplate_excluded_from_unclassified(
        self, audit_project: dict[str, Any]
    ) -> None:
        """Boilerplate messages never appear in unclassified output."""
        root = audit_project["project_root"]
        project_dir = audit_project["project_dir"]

        ns = _make_namespace(
            sessions="feature-csv-reader",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns, root)

        conn = db.open_db(root, create=False)
        uncl = db.query_unclassified(conn)

        for item in uncl["items"]:
            text = item["user_text"]
            for prefix in BOILERPLATE_PREFIXES:
                assert not text.startswith(prefix), (
                    f"Boilerplate message leaked into unclassified: {text[:80]}"
                )
        conn.close()

    def test_boilerplate_count_matches_data(
        self, audit_project: dict[str, Any]
    ) -> None:
        """Boilerplate count in DB matches expected from test data."""
        root = audit_project["project_root"]
        project_dir = audit_project["project_dir"]

        ns = _make_namespace(
            sessions="feature-csv-reader",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns, root)

        conn = db.open_db(root, create=False)
        bp_rows = conn.execute(
            "SELECT user_text FROM messages WHERE is_boilerplate = 1"
        ).fetchall()
        bp_texts = [r["user_text"] for r in bp_rows]
        conn.close()

        # We put 2 boilerplate messages in the test data:
        # "[Request interrupted by user]" in session 1
        # "[Spawned by agent 'test-runner']" in session 2
        assert len(bp_texts) == 2
        assert any("interrupted" in t.lower() for t in bp_texts)
        assert any("spawned" in t.lower() for t in bp_texts)


# ===========================================================================
# INTENT cross-cutting: context windows
# ===========================================================================


class TestContextWindows:
    """Verify that context_before and context_after are populated."""

    def test_context_populated_for_corrections(
        self, audit_project: dict[str, Any]
    ) -> None:
        """Messages following an assistant response have context_before set."""
        root = audit_project["project_root"]
        project_dir = audit_project["project_dir"]

        ns = _make_namespace(
            sessions="feature-csv-reader",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns, root)

        conn = db.open_db(root, create=False)
        # "No, that's wrong" comes after an assistant message
        row = conn.execute(
            "SELECT context_before, context_after FROM messages "
            "WHERE user_text LIKE '%wrong%' AND is_boilerplate = 0 "
            "LIMIT 1"
        ).fetchone()
        conn.close()

        assert row is not None
        # The message before "No, that's wrong" was an assistant message
        assert row["context_before"] is not None
        assert len(row["context_before"]) > 0


# ===========================================================================
# INTENT cross-cutting: phase inference
# ===========================================================================


class TestPhaseInference:
    """Verify phase inference from chicsession workflow_state."""

    def test_phase_from_snapshot(self, audit_project: dict[str, Any]) -> None:
        """Messages get phase_id from chicsession workflow_state snapshot."""
        root = audit_project["project_root"]
        project_dir = audit_project["project_dir"]

        ns = _make_namespace(
            sessions="feature-csv-reader",
            all=False,
            project_dir=str(project_dir),
        )
        cmd_extract(ns, root)

        conn = db.open_db(root, create=False)
        # Our chicsession has workflow_state.current_phase = "implement"
        # Messages without inline phase markers should get "implement" from snapshot
        rows = conn.execute(
            "SELECT phase_id, phase_confidence FROM messages "
            "WHERE phase_id = 'implement' LIMIT 5"
        ).fetchall()
        conn.close()

        assert len(rows) > 0, "Expected messages with phase_id='implement'"
        # Phase confidence should be 'snapshot' (from chicsession state)
        for r in rows:
            assert r["phase_confidence"] in ("snapshot", "inferred")
