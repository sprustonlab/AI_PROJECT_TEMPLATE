"""SQLite database layer for the audit workflow.

Owns schema creation, connection management, WAL mode with Windows fallback,
and all INSERT/SELECT/UPDATE queries. audit.py delegates all database
operations here.

Cross-platform: encoding='utf-8' on all text, pathlib.Path everywhere,
ASCII only, os.replace() for atomics.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DB_DIR = ".audit"
DEFAULT_DB_NAME = "corrections.db"

SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    message_hash TEXT UNIQUE,
    session_id TEXT,
    session_file TEXT,
    chicsession_name TEXT,
    turn_index INTEGER,
    user_text TEXT NOT NULL,
    context_before TEXT,
    context_after TEXT,
    regex_score REAL,
    regex_indicator TEXT,
    phase_id TEXT,
    phase_confidence TEXT DEFAULT 'unknown',
    agent_name TEXT,
    workflow_id TEXT,
    is_boilerplate INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, turn_index)
);

CREATE TABLE IF NOT EXISTS classifications (
    id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES messages(id),
    is_correction INTEGER NOT NULL,
    category TEXT,
    confidence TEXT,
    classified_at TEXT NOT NULL,
    UNIQUE(message_id)
);

CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY,
    artifact_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    suggestion_type TEXT NOT NULL,
    current_content TEXT,
    proposed_content TEXT NOT NULL,
    insertion_point TEXT,
    rationale TEXT NOT NULL,
    evidence_count INTEGER NOT NULL,
    priority INTEGER NOT NULL,
    critic_verdict TEXT,
    critic_reasoning TEXT,
    apply_status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL,
    applied_at TEXT
);

CREATE TABLE IF NOT EXISTS suggestion_evidence (
    suggestion_id INTEGER NOT NULL REFERENCES suggestions(id),
    message_id INTEGER NOT NULL REFERENCES messages(id),
    PRIMARY KEY (suggestion_id, message_id)
);

CREATE TABLE IF NOT EXISTS processed_files (
    file_path TEXT PRIMARY KEY,
    file_size INTEGER NOT NULL,
    file_mtime TEXT NOT NULL,
    messages_extracted INTEGER NOT NULL,
    processed_at TEXT NOT NULL,
    last_offset INTEGER              -- byte offset for future incremental reads
);
"""


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def db_path(project_root: Path) -> Path:
    """Return the path to the corrections database."""
    return project_root / DEFAULT_DB_DIR / DEFAULT_DB_NAME


def db_exists(project_root: Path) -> bool:
    """Check whether the database file exists."""
    return db_path(project_root).is_file()


def open_db(project_root: Path, *, create: bool = True) -> sqlite3.Connection:
    """Open (and optionally create) the corrections database.

    Sets WAL journal mode for concurrent read safety. On Windows, falls back
    to DELETE mode if WAL fails (e.g. network drives).
    """
    p = db_path(project_root)
    if create:
        p.parent.mkdir(parents=True, exist_ok=True)
    elif not p.is_file():
        msg = f"Database not found: {p}"
        raise FileNotFoundError(msg)

    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # WAL mode with Windows fallback
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        if sys.platform == "win32":
            import warnings

            warnings.warn(
                "WAL mode failed; falling back to DELETE journal mode.",
                stacklevel=2,
            )
            conn.execute("PRAGMA journal_mode=DELETE")
        else:
            raise

    if create:
        conn.executescript(SCHEMA_SQL)

    return conn


# ---------------------------------------------------------------------------
# Processed files (incremental tracking)
# ---------------------------------------------------------------------------


def get_processed_file(
    conn: sqlite3.Connection, file_path: str
) -> dict[str, Any] | None:
    """Return processed_files row for *file_path*, or None."""
    row = conn.execute(
        "SELECT * FROM processed_files WHERE file_path = ?", (file_path,)
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def upsert_processed_file(
    conn: sqlite3.Connection,
    file_path: str,
    file_size: int,
    file_mtime: str,
    messages_extracted: int,
) -> None:
    """Insert or update a processed_files record."""
    conn.execute(
        """INSERT INTO processed_files (file_path, file_size, file_mtime,
               messages_extracted, processed_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(file_path) DO UPDATE SET
               file_size=excluded.file_size,
               file_mtime=excluded.file_mtime,
               messages_extracted=excluded.messages_extracted,
               processed_at=excluded.processed_at
        """,
        (file_path, file_size, file_mtime, messages_extracted, _now_iso()),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


def insert_messages(
    conn: sqlite3.Connection,
    rows: list[dict[str, Any]],
) -> int:
    """Batch insert messages. Returns count of newly inserted rows.

    Uses INSERT OR IGNORE to skip duplicates (by message_hash).
    """
    if not rows:
        return 0

    sql = """\
    INSERT OR IGNORE INTO messages (
        message_hash, session_id, session_file, chicsession_name,
        turn_index, user_text, context_before, context_after,
        regex_score, regex_indicator, phase_id, phase_confidence,
        agent_name, workflow_id, is_boilerplate, created_at
    ) VALUES (
        :message_hash, :session_id, :session_file, :chicsession_name,
        :turn_index, :user_text, :context_before, :context_after,
        :regex_score, :regex_indicator, :phase_id, :phase_confidence,
        :agent_name, :workflow_id, :is_boilerplate, :created_at
    )
    """
    before = _count(conn, "messages")
    conn.executemany(sql, rows)
    conn.commit()
    after = _count(conn, "messages")
    return after - before


def _count(conn: sqlite3.Connection, table: str) -> int:
    """Return row count for *table*."""
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608


# ---------------------------------------------------------------------------
# Unclassified query
# ---------------------------------------------------------------------------


def query_unclassified(
    conn: sqlite3.Connection,
    *,
    chunk_size: int = 200,
) -> dict[str, Any]:
    """Return unclassified non-boilerplate messages for the classifier.

    Returns dict with keys: ``items`` (list of dicts), ``has_more`` (bool).
    """
    total_sql = """\
    SELECT COUNT(*) FROM messages m
    WHERE m.is_boilerplate = 0
      AND m.id NOT IN (SELECT message_id FROM classifications)
    """
    total = conn.execute(total_sql).fetchone()[0]

    fetch_limit = chunk_size
    sql = """\
    SELECT m.id, m.user_text, m.context_before, m.context_after,
           m.session_id, m.agent_name, m.phase_id,
           m.regex_score, m.regex_indicator
    FROM messages m
    WHERE m.is_boilerplate = 0
      AND m.id NOT IN (SELECT message_id FROM classifications)
    ORDER BY m.id
    LIMIT ?
    """
    rows = conn.execute(sql, (fetch_limit,)).fetchall()
    items = [dict(r) for r in rows]
    return {"items": items, "has_more": total > len(items)}


# ---------------------------------------------------------------------------
# Corrections query
# ---------------------------------------------------------------------------


def query_corrections(
    conn: sqlite3.Connection,
    *,
    phase: str | None = None,
    category: str | None = None,
    min_confidence: str | None = None,
    chunk_size: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    """Return classified corrections with full context for the judge.

    Returns dict with keys: ``items`` (list of dicts), ``has_more`` (bool).
    """
    conditions: list[str] = ["c.is_correction = 1"]
    params: list[Any] = []
    if phase:
        conditions.append("m.phase_id = ?")
        params.append(phase)
    if category:
        conditions.append("c.category = ?")
        params.append(category)
    if min_confidence:
        conf_order = {"high": 3, "medium": 2, "low": 1}
        min_val = conf_order.get(min_confidence, 0)
        allowed = [k for k, v in conf_order.items() if v >= min_val]
        placeholders = ",".join("?" for _ in allowed)
        conditions.append(f"c.confidence IN ({placeholders})")
        params.extend(allowed)

    where = " AND ".join(conditions)

    count_sql = f"""\
    SELECT COUNT(*) FROM messages m
    JOIN classifications c ON m.id = c.message_id
    WHERE {where}
    """
    total = conn.execute(count_sql, params).fetchone()[0]

    sql = f"""\
    SELECT m.id, m.user_text, m.context_before, m.context_after,
           m.session_id, m.session_file, m.agent_name, m.workflow_id,
           m.phase_id, m.phase_confidence, m.turn_index,
           m.regex_score, m.regex_indicator,
           c.category, c.confidence
    FROM messages m
    JOIN classifications c ON m.id = c.message_id
    WHERE {where}
    ORDER BY m.phase_id, c.category, m.id
    LIMIT ? OFFSET ?
    """
    rows = conn.execute(sql, [*params, chunk_size, offset]).fetchall()
    items = [dict(r) for r in rows]
    return {"items": items, "has_more": (offset + len(items)) < total}


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


def aggregate_corrections(
    conn: sqlite3.Connection,
    *,
    min_count: int = 2,
) -> list[dict[str, Any]]:
    """Group corrections into patterns for the judge.

    Returns list of pattern dicts with category, phase, counts, top examples.
    """
    group_sql = """\
    SELECT c.category, m.phase_id,
           COUNT(*) as correction_count,
           COUNT(DISTINCT m.session_id) as session_count,
           GROUP_CONCAT(DISTINCT m.agent_name) as agent_names
    FROM classifications c
    JOIN messages m ON c.message_id = m.id
    WHERE c.is_correction = 1
    GROUP BY c.category, m.phase_id
    HAVING COUNT(*) >= ?
    ORDER BY COUNT(*) DESC
    """
    groups = conn.execute(group_sql, (min_count,)).fetchall()
    patterns: list[dict[str, Any]] = []

    for g in groups:
        cat = g["category"]
        phase = g["phase_id"]
        pattern_id = f"{cat}:{phase}" if phase else f"{cat}:unknown"

        # Top 3 examples (highest confidence first)
        examples_sql = """\
        SELECT m.id as message_id, m.user_text, m.context_before,
               m.context_after, c.confidence, m.session_id
        FROM messages m
        JOIN classifications c ON m.id = c.message_id
        WHERE c.is_correction = 1 AND c.category = ? AND m.phase_id IS ?
        ORDER BY CASE c.confidence
            WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3
        END, m.id
        LIMIT 3
        """
        top = conn.execute(examples_sql, (cat, phase)).fetchall()
        top_examples = [dict(r) for r in top]

        # All message IDs for evidence linking
        ids_sql = """\
        SELECT m.id FROM messages m
        JOIN classifications c ON m.id = c.message_id
        WHERE c.is_correction = 1 AND c.category = ? AND m.phase_id IS ?
        ORDER BY m.id
        """
        all_ids = [r[0] for r in conn.execute(ids_sql, (cat, phase)).fetchall()]

        agent_names = (
            [a.strip() for a in g["agent_names"].split(",") if a.strip()]
            if g["agent_names"]
            else []
        )

        patterns.append(
            {
                "pattern_id": pattern_id,
                "category": cat,
                "phase_id": phase,
                "correction_count": g["correction_count"],
                "session_count": g["session_count"],
                "agent_names": agent_names,
                "top_examples": top_examples,
                "all_message_ids": all_ids,
            }
        )

    return patterns


# ---------------------------------------------------------------------------
# Batch store: classifications
# ---------------------------------------------------------------------------


def store_classifications(
    conn: sqlite3.Connection,
    items: list[dict[str, Any]],
) -> tuple[int, int]:
    """Batch insert classifications. Returns (stored, skipped)."""
    sql = """\
    INSERT OR IGNORE INTO classifications
        (message_id, is_correction, category, confidence, classified_at)
    VALUES (:message_id, :is_correction, :category, :confidence, :classified_at)
    """
    now = _now_iso()
    prepared = []
    for item in items:
        prepared.append(
            {
                "message_id": item["message_id"],
                "is_correction": item["is_correction"],
                "category": item.get("category"),
                "confidence": item.get("confidence"),
                "classified_at": now,
            }
        )
    before = _count(conn, "classifications")
    conn.executemany(sql, prepared)
    conn.commit()
    after = _count(conn, "classifications")
    stored = after - before
    skipped = len(items) - stored
    return stored, skipped


# ---------------------------------------------------------------------------
# Batch store: suggestions
# ---------------------------------------------------------------------------


def store_suggestions(
    conn: sqlite3.Connection,
    items: list[dict[str, Any]],
) -> list[int]:
    """Batch insert suggestions + evidence links. Returns list of new IDs."""
    now = _now_iso()
    new_ids: list[int] = []
    for item in items:
        cursor = conn.execute(
            """\
            INSERT INTO suggestions (
                artifact_type, file_path, suggestion_type,
                current_content, proposed_content, insertion_point,
                rationale, evidence_count, priority, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["artifact_type"],
                item["file_path"],
                item["suggestion_type"],
                item.get("current_content"),
                item["proposed_content"],
                item.get("insertion_point"),
                item["rationale"],
                item["evidence_count"],
                item["priority"],
                now,
            ),
        )
        sid = cursor.lastrowid
        new_ids.append(sid)

        # Link evidence
        evidence_ids = item.get("evidence_message_ids", [])
        if evidence_ids:
            conn.executemany(
                "INSERT OR IGNORE INTO suggestion_evidence "
                "(suggestion_id, message_id) VALUES (?, ?)",
                [(sid, mid) for mid in evidence_ids],
            )
    conn.commit()
    return new_ids


# ---------------------------------------------------------------------------
# Update suggestion
# ---------------------------------------------------------------------------

# Allowed fields for update-suggestion command
_SUGGESTION_UPDATE_FIELDS = {
    "critic_verdict",
    "critic_reasoning",
    "apply_status",
    "applied_at",
}


def update_suggestion(
    conn: sqlite3.Connection,
    suggestion_id: int,
    updates: dict[str, Any],
) -> bool:
    """Update specific fields on an existing suggestion. Returns True if found."""
    valid = {k: v for k, v in updates.items() if k in _SUGGESTION_UPDATE_FIELDS}
    if not valid:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in valid)
    values = list(valid.values()) + [suggestion_id]
    cursor = conn.execute(
        f"UPDATE suggestions SET {set_clause} WHERE id = ?",  # noqa: S608
        values,
    )
    conn.commit()
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Check commands
# ---------------------------------------------------------------------------


def check_has_messages(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Check: messages table is non-empty."""
    n = _count(conn, "messages")
    if n > 0:
        return True, f"PASS: {n} messages in database"
    return False, "FAIL: no messages extracted yet"


def check_all_classified(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Check: all non-boilerplate messages are classified."""
    total = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE is_boilerplate = 0"
    ).fetchone()[0]
    classified = _count(conn, "classifications")
    remaining = total - classified
    if remaining <= 0:
        return True, f"PASS: {classified} messages classified, 0 remaining"
    return False, f"FAIL: {remaining} messages still unclassified"


def check_all_reviewed(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Check: all suggestions have critic verdicts."""
    total = _count(conn, "suggestions")
    if total == 0:
        return True, "PASS: no suggestions to review"
    unreviewed = conn.execute(
        "SELECT COUNT(*) FROM suggestions WHERE critic_verdict IS NULL"
    ).fetchone()[0]
    if unreviewed == 0:
        return True, f"PASS: all {total} suggestions reviewed"
    return False, f"FAIL: {unreviewed} suggestions still unreviewed"


def check_all_decided(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Check: no suggestions with apply_status='pending'."""
    pending = conn.execute(
        "SELECT COUNT(*) FROM suggestions WHERE apply_status = 'pending'"
    ).fetchone()[0]
    if pending == 0:
        return True, "PASS: all suggestions have decisions"
    return False, f"FAIL: {pending} suggestions still pending"


def check_has_db(project_root: Path) -> tuple[bool, str]:
    """Check: database file exists."""
    if db_exists(project_root):
        return True, "PASS: database exists"
    return False, "FAIL: database not found"


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


def reset_classifications(conn: sqlite3.Connection) -> int:
    """Delete all classifications. Returns count deleted."""
    n = _count(conn, "classifications")
    conn.execute("DELETE FROM classifications")
    conn.commit()
    return n


def reset_suggestions(conn: sqlite3.Connection) -> int:
    """Delete all suggestions and evidence links. Returns count deleted."""
    n = _count(conn, "suggestions")
    conn.execute("DELETE FROM suggestion_evidence")
    conn.execute("DELETE FROM suggestions")
    conn.commit()
    return n


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def get_status(conn: sqlite3.Connection) -> dict[str, Any]:
    """Gather status dashboard data from the database."""
    total_msgs = _count(conn, "messages")
    classified = _count(conn, "classifications")
    non_boilerplate = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE is_boilerplate = 0"
    ).fetchone()[0]
    unclassified = non_boilerplate - classified

    corrections = conn.execute(
        "SELECT COUNT(*) FROM classifications WHERE is_correction = 1"
    ).fetchone()[0]

    regex_flagged = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE regex_score >= 0.3"
    ).fetchone()[0]

    total_suggestions = _count(conn, "suggestions")
    pending = conn.execute(
        "SELECT COUNT(*) FROM suggestions WHERE apply_status = 'pending'"
    ).fetchone()[0]
    applied = conn.execute(
        "SELECT COUNT(*) FROM suggestions WHERE apply_status = 'applied'"
    ).fetchone()[0]
    skipped = conn.execute(
        "SELECT COUNT(*) FROM suggestions WHERE apply_status = 'skipped'"
    ).fetchone()[0]
    unreviewed = conn.execute(
        "SELECT COUNT(*) FROM suggestions WHERE critic_verdict IS NULL"
    ).fetchone()[0]

    files_processed = _count(conn, "processed_files")

    last_row = conn.execute("SELECT MAX(processed_at) FROM processed_files").fetchone()[
        0
    ]

    chicsessions_row = conn.execute(
        "SELECT DISTINCT chicsession_name FROM messages "
        "WHERE chicsession_name IS NOT NULL ORDER BY chicsession_name"
    ).fetchall()
    chicsessions = [r[0] for r in chicsessions_row]

    return {
        "messages": total_msgs,
        "classified": classified,
        "unclassified": unclassified,
        "corrections": corrections,
        "regex_flagged": regex_flagged,
        "suggestions": total_suggestions,
        "pending": pending,
        "applied": applied,
        "skipped": skipped,
        "unreviewed": unreviewed,
        "files_processed": files_processed,
        "last_extract": last_row,
        "chicsessions_processed": ", ".join(chicsessions) if chicsessions else "",
    }


# ---------------------------------------------------------------------------
# Query helpers used by list-sessions
# ---------------------------------------------------------------------------


def messages_for_chicsession(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    """Return message count and correction count for a chicsession."""
    msg_count = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE chicsession_name = ?", (name,)
    ).fetchone()[0]
    corr_count = conn.execute(
        """\
        SELECT COUNT(*) FROM classifications c
        JOIN messages m ON c.message_id = m.id
        WHERE m.chicsession_name = ? AND c.is_correction = 1
        """,
        (name,),
    ).fetchone()[0]
    last_row = conn.execute(
        """\
        SELECT MAX(pf.processed_at) FROM processed_files pf
        JOIN messages m ON pf.file_path = m.session_file
        WHERE m.chicsession_name = ?
        """,
        (name,),
    ).fetchone()[0]
    return {
        "messages_in_db": msg_count,
        "corrections_found": corr_count,
        "last_extracted": last_row,
    }


def processed_file_paths(conn: sqlite3.Connection) -> set[str]:
    """Return set of all processed file paths."""
    rows = conn.execute("SELECT file_path FROM processed_files").fetchall()
    return {r[0] for r in rows}
