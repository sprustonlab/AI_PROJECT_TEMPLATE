#!/usr/bin/env python3
"""Audit workflow CLI -- JSONL extraction, regex scoring, and database operations.

Entry point for the audit workflow's Python layer. Handles:
- JSONL parsing (absorbed from mine_patterns.py)
- Pre-filtering system boilerplate
- Regex scoring (Tier 1 pattern banks)
- Incremental extraction with dedup
- Chicsession integration via ChicsessionManager
- Database queries and batch store operations

All analysis, classification, and suggestion generation happens in agents.
This script is a thin helper that agents call via subprocess.

Cross-platform: encoding='utf-8' everywhere, pathlib.Path, ASCII only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Resolve project root and ensure importability
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Ensure project root is on sys.path so `from scripts.audit import db` works
# when invoked directly as `python scripts/audit/audit.py`.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# JSONL format constants (absorbed from mine_patterns.py)
# ---------------------------------------------------------------------------

KNOWN_VERSIONS = {
    "2.1.59",
    "2.1.60",
    "2.1.61",
    "2.1.62",
    "2.1.63",
    "2.1.85",
    "2.1.87",
    "2.2.0",
    "2.2.1",
}

# ---------------------------------------------------------------------------
# Boilerplate prefixes -- messages starting with these are system noise
# ---------------------------------------------------------------------------

BOILERPLATE_PREFIXES = (
    "[Spawned by agent",
    "[Request interrupted",
    "<task-notification>",
    "You have been idle",
    "[Message from agent",
    "[Question from agent",
    "<system-reminder>",
    "This session is being continued",
    "[Redirected by",
    "Workflow '",
)

# ---------------------------------------------------------------------------
# Regex pattern banks (absorbed from mine_patterns.py)
# ---------------------------------------------------------------------------

NEGATION_PATTERNS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\bno[,.]?\s+that'?s\b", re.I), 0.45, "no, that's"),
    (re.compile(r"\bnot what I\b", re.I), 0.50, "not what I"),
    (
        re.compile(r"\bthat'?s not\s+(right|correct|what)\b", re.I),
        0.50,
        "that's not right",
    ),
    (re.compile(r"\bthat'?s\s+wrong\b", re.I), 0.55, "that's wrong"),
    (
        re.compile(r"\bno[,.]?\s+(I\s+)?(said|meant|asked|wanted)\b", re.I),
        0.50,
        "no, I said",
    ),
    (re.compile(r"\bwrong\b", re.I), 0.30, "wrong"),
    (re.compile(r"\bincorrect\b", re.I), 0.35, "incorrect"),
    (re.compile(r"\bnot\s+correct\b", re.I), 0.40, "not correct"),
]

FRUSTRATION_PATTERNS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\bgaslighting\b", re.I), 0.70, "gaslighting"),
    (
        re.compile(r"\byou'?re\s+not\s+listening\b", re.I),
        0.65,
        "you're not listening",
    ),
    (re.compile(r"\bstop\s+(doing|it|that)\b", re.I), 0.50, "stop doing"),
    (
        re.compile(r"\bI\s+already\s+(said|told|explained)\b", re.I),
        0.55,
        "I already said",
    ),
    (re.compile(r"\bhow\s+many\s+times\b", re.I), 0.55, "how many times"),
    (re.compile(r"\bplease\s+(just\s+)?read\b", re.I), 0.35, "please read"),
    (re.compile(r"\bpay\s+attention\b", re.I), 0.55, "pay attention"),
    (re.compile(r"\byou\s+keep\b", re.I), 0.40, "you keep"),
    (re.compile(r"\bfrustrat", re.I), 0.45, "frustration"),
]

ERROR_PATTERNS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\bbug\b", re.I), 0.25, "bug"),
    (re.compile(r"\bbroken\b", re.I), 0.30, "broken"),
    (re.compile(r"\berror\b", re.I), 0.20, "error"),
    (re.compile(r"\bcrash(es|ed|ing)?\b", re.I), 0.25, "crash"),
    (re.compile(r"\bfail(s|ed|ing|ure)?\b", re.I), 0.20, "fail"),
    (re.compile(r"\bdoesn'?t\s+work\b", re.I), 0.35, "doesn't work"),
    (re.compile(r"\bnot\s+working\b", re.I), 0.35, "not working"),
]

CORRECTION_PATTERNS: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\bI\s+said\b", re.I), 0.40, "I said"),
    (re.compile(r"\bdon'?t\s+do\b", re.I), 0.40, "don't do"),
    (re.compile(r"\brevert\b", re.I), 0.45, "revert"),
    (re.compile(r"\bundo\b", re.I), 0.35, "undo"),
    (re.compile(r"\broll\s*back\b", re.I), 0.40, "rollback"),
    (re.compile(r"\binstead\b", re.I), 0.20, "instead"),
    (re.compile(r"\bactually\b", re.I), 0.20, "actually"),
    (re.compile(r"\bI\s+(meant|wanted|asked\s+for)\b", re.I), 0.40, "I meant"),
    (re.compile(r"\bnot\s+what\s+I\b", re.I), 0.50, "not what I"),
    (re.compile(r"\bshould\s+(be|have)\b", re.I), 0.20, "should be"),
    (
        re.compile(r"\byou\s+(missed|forgot|skipped|ignored|overlooked)\b", re.I),
        0.50,
        "you missed",
    ),
    (
        re.compile(r"\bdo(n'?t|es\s*n'?t)\s+(modify|change|touch|edit|alter)\b", re.I),
        0.40,
        "don't modify",
    ),
    (re.compile(r"\bI\s+told\s+you\b", re.I), 0.50, "I told you"),
    (re.compile(r"\blike\s+I\s+said\b", re.I), 0.45, "like I said"),
]

ALL_PATTERN_BANKS = [
    ("negation", NEGATION_PATTERNS),
    ("frustration", FRUSTRATION_PATTERNS),
    ("error", ERROR_PATTERNS),
    ("correction", CORRECTION_PATTERNS),
]


# ---------------------------------------------------------------------------
# JSONL parsing dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """A single message extracted from a JSONL session."""

    role: str  # "user" | "assistant"
    text: str
    timestamp: str | None
    session_id: str | None


@dataclass
class ParseStats:
    """Statistics from parsing a single JSONL file."""

    total_lines: int = 0
    json_errors: int = 0
    skipped_tool_results: int = 0
    empty_messages: int = 0
    unknown_types: int = 0
    version: str | None = None
    version_known: bool = True


@dataclass
class ParseResult:
    """Complete result of parsing a JSONL session file."""

    messages: list[Message] = field(default_factory=list)
    session_id: str | None = None
    stats: ParseStats = field(default_factory=ParseStats)
    path: Path | None = None


# ---------------------------------------------------------------------------
# JSONL parsing (absorbed from mine_patterns.py)
# ---------------------------------------------------------------------------


def _extract_text(content: Any) -> str:
    """Extract text from a message content field (str or list-of-dicts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(parts)
    return ""


def _detect_version(obj: dict[str, Any]) -> str | None:
    """Try to extract a Claude Code version from a JSONL object."""
    for key in ("version", "codeVersion", "clientVersion"):
        val = obj.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def parse_session(path: Path) -> ParseResult:
    """Parse a JSONL session file into structured messages.

    This is the SOLE entry point for JSONL format handling.
    """
    result = ParseResult(path=path)
    stats = result.stats
    session_id_found = False

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            stats.total_lines += 1
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                stats.json_errors += 1
                continue

            # Version detection
            if stats.version is None:
                detected = _detect_version(obj)
                if detected:
                    stats.version = detected
                    if detected not in KNOWN_VERSIONS:
                        stats.version_known = False
                        warnings.warn(
                            f"Unknown JSONL version '{detected}' in "
                            f"{path.name}. Parser may produce incorrect "
                            f"results.",
                            stacklevel=2,
                        )

            msg_type = obj.get("type")
            if msg_type not in ("user", "assistant"):
                stats.unknown_types += 1
                continue

            if not session_id_found:
                sid = obj.get("sessionId")
                if sid:
                    result.session_id = sid
                    session_id_found = True

            # Skip tool-result user messages
            if msg_type == "user" and "toolUseResult" in obj:
                stats.skipped_tool_results += 1
                continue

            msg_body = obj.get("message", {})
            content = msg_body.get("content", "")
            text = _extract_text(content)

            if not text.strip():
                stats.empty_messages += 1
                continue

            result.messages.append(
                Message(
                    role=msg_type,
                    text=text,
                    timestamp=obj.get("timestamp"),
                    session_id=obj.get("sessionId"),
                )
            )

    return result


# ---------------------------------------------------------------------------
# Regex scoring (Tier 1)
# ---------------------------------------------------------------------------


def tier1_score_message(
    text: str,
    preceding_agent_text: str | None,
    prev_user_text: str | None,
) -> tuple[float, str | None]:
    """Score a user message using regex pattern banks.

    Returns (score 0.0-1.0, best_indicator_label_or_None).
    Simplified from mine_patterns.py -- drops behavioral heuristics that
    require full-session context (session-end detection, turn counts).
    """
    scores: list[float] = []
    best_indicator: str | None = None
    best_score = 0.0

    for _bank_name, bank in ALL_PATTERN_BANKS:
        for pattern, weight, label in bank:
            if pattern.search(text):
                scores.append(weight)
                if weight > best_score:
                    best_score = weight
                    best_indicator = label

    # Behavioral: short response after agent message
    if preceding_agent_text and 2 < len(text.strip()) < 50:
        w = 0.30
        scores.append(w)
        if w > best_score:
            best_score = w
            best_indicator = "short_response"

    # Behavioral: user repeats themselves
    if prev_user_text:
        words_a = set(text.lower().split())
        words_b = set(prev_user_text.lower().split())
        if words_a and words_b:
            jaccard = len(words_a & words_b) / len(words_a | words_b)
            if jaccard > 0.6:
                w = 0.45
                scores.append(w)
                if w > best_score:
                    best_score = w
                    best_indicator = "user_repeat"

    if not scores:
        return 0.0, None

    scores.sort(reverse=True)
    combined = scores[0]
    for s in scores[1:]:
        combined += s * 0.3
    combined = min(combined, 1.0)

    return combined, best_indicator


# ---------------------------------------------------------------------------
# Phase transition extraction
# ---------------------------------------------------------------------------


def _extract_phase_timeline(
    messages: list[Message],
) -> list[tuple[int, str]]:
    """Scan messages for phase transition markers.

    Returns list of (message_index, phase_id) tuples, sorted by index.
    """
    transitions: list[tuple[int, str]] = []

    advance_re = re.compile(r"advance_phase|Advanced to phase:\s*(\S+)")
    user_advance_re = re.compile(r"/advance\s+(\S+)")

    for idx, msg in enumerate(messages):
        if msg.role == "assistant":
            m = advance_re.search(msg.text)
            if m and m.group(1):
                transitions.append((idx, m.group(1)))
        elif msg.role == "user":
            m = user_advance_re.search(msg.text)
            if m:
                transitions.append((idx, m.group(1)))

    transitions.sort(key=lambda t: t[0])
    return transitions


def _phase_for_index(idx: int, timeline: list[tuple[int, str]]) -> str | None:
    """Return phase_id for the most recent transition before *idx*."""
    phase = None
    for t_idx, t_phase in timeline:
        if t_idx <= idx:
            phase = t_phase
        else:
            break
    return phase


# ---------------------------------------------------------------------------
# Session file discovery helpers
# ---------------------------------------------------------------------------


def _resolve_jsonl_paths(
    session_id: str,
    project_dir: Path | None = None,
) -> list[Path]:
    """Resolve a session_id to possible JSONL file paths.

    Checks both ``<session_id>.jsonl`` and ``agent-<session_id>.jsonl``
    across all project directories (or a specific one).
    """
    candidates: list[str] = [
        f"{session_id}.jsonl",
        f"agent-{session_id}.jsonl",
    ]
    found: list[Path] = []

    if project_dir and project_dir.is_dir():
        for name in candidates:
            p = project_dir / name
            if p.is_file():
                found.append(p)
        return found

    # Search all project directories
    if not CLAUDE_PROJECTS_DIR.is_dir():
        return found
    for subdir in CLAUDE_PROJECTS_DIR.iterdir():
        if not subdir.is_dir():
            continue
        for name in candidates:
            p = subdir / name
            if p.is_file():
                found.append(p)

    return found


def _estimate_messages(path: Path) -> int:
    """Rough estimate of user messages from JSONL file size.

    Heuristic: ~500 bytes per JSONL line, ~40% are user messages.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return 0
    lines_est = size // 500
    return max(1, int(lines_est * 0.4))


# ---------------------------------------------------------------------------
# Dedup hash
# ---------------------------------------------------------------------------


def _message_hash(session_id: str, turn_index: int, user_text: str) -> str:
    """SHA256(session_id + turn_index + user_text) for dedup."""
    raw = f"{session_id}|{turn_index}|{user_text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Extract command
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cmd_extract(
    args: argparse.Namespace,
    project_root: Path,
) -> None:
    """Extract messages from chicsession JSONL files into the database."""
    # Late import to avoid hard dependency when db.py is tested standalone
    from scripts.audit import db

    try:
        sys.path.insert(0, str(PROJECT_ROOT / "submodules" / "claudechic"))
        from claudechic.chicsessions import ChicsessionManager
    except ImportError:
        _err(
            "Could not import ChicsessionManager. "
            "Ensure claudechic submodule is available."
        )
        sys.exit(1)

    mgr = ChicsessionManager(project_root)
    all_names = mgr.list_chicsessions()

    if args.all:
        selected = all_names
    elif args.sessions:
        selected = [s.strip() for s in args.sessions.split(",") if s.strip()]
    else:
        _err("Either --all or --sessions is required.")
        sys.exit(1)

    if not selected:
        _err("No chicsessions selected.")
        sys.exit(1)

    conn = db.open_db(project_root)

    project_dir_override = None
    if hasattr(args, "project_dir") and args.project_dir:
        project_dir_override = Path(args.project_dir)

    _err(f"Processing {len(selected)} chicsessions: {', '.join(selected)}")

    for cs_name in selected:
        try:
            cs = mgr.load(cs_name)
        except (FileNotFoundError, ValueError) as exc:
            _err(f"  WARNING: Could not load chicsession '{cs_name}': {exc}")
            continue

        workflow_id = None
        cs_phase = None
        if cs.workflow_state:
            workflow_id = cs.workflow_state.get("workflow_id")
            cs_phase = cs.workflow_state.get("current_phase")

        agents = cs.agents
        _err(f"  {cs_name}: {len(agents)} agents")

        total_new = 0
        total_skipped_files = 0
        total_dupes = 0
        total_boilerplate = 0
        total_regex_flagged = 0
        files_count = 0

        for entry in agents:
            paths = _resolve_jsonl_paths(entry.session_id, project_dir_override)
            if not paths:
                _err(
                    f"    WARNING: No JSONL found for agent "
                    f"'{entry.name}' (session {entry.session_id})"
                )
                continue

            for jsonl_path in paths:
                files_count += 1
                file_key = jsonl_path.as_posix()

                # Incremental skip check
                try:
                    st = jsonl_path.stat()
                    file_size = st.st_size
                    file_mtime = str(st.st_mtime)
                except OSError:
                    _err(f"    WARNING: Cannot stat {jsonl_path}")
                    continue

                existing = db.get_processed_file(conn, file_key)
                if (
                    existing
                    and existing["file_size"] == file_size
                    and existing["file_mtime"] == file_mtime
                ):
                    total_skipped_files += 1
                    continue

                # Parse the JSONL
                parsed = parse_session(jsonl_path)
                messages = parsed.messages
                session_id = parsed.session_id or jsonl_path.stem

                # Build phase timeline
                phase_timeline = _extract_phase_timeline(messages)

                # Build rows for user messages
                rows: list[dict[str, Any]] = []
                user_turn = 0
                prev_user_text: str | None = None

                for i, msg in enumerate(messages):
                    if msg.role != "user":
                        continue

                    text = msg.text
                    is_boilerplate = 0
                    for prefix in BOILERPLATE_PREFIXES:
                        if text.startswith(prefix):
                            is_boilerplate = 1
                            break

                    # Context window (truncate to avoid multi-MB payloads)
                    context_before: str | None = None
                    context_after: str | None = None
                    if i > 0 and messages[i - 1].role == "assistant":
                        context_before = messages[i - 1].text[:500]
                    if i + 1 < len(messages) and messages[i + 1].role == "assistant":
                        context_after = messages[i + 1].text[:500]

                    # Regex scoring (non-boilerplate only)
                    regex_score = 0.0
                    regex_indicator: str | None = None
                    if not is_boilerplate:
                        regex_score, regex_indicator = tier1_score_message(
                            text, context_before, prev_user_text
                        )

                    # Phase inference
                    phase_id = _phase_for_index(i, phase_timeline)
                    phase_confidence = "unknown"
                    if phase_id:
                        phase_confidence = "inferred"
                    elif cs_phase:
                        phase_id = cs_phase
                        phase_confidence = "snapshot"

                    mhash = _message_hash(session_id, user_turn, text)

                    rows.append(
                        {
                            "message_hash": mhash,
                            "session_id": session_id,
                            "session_file": file_key,
                            "chicsession_name": cs_name,
                            "turn_index": user_turn,
                            "user_text": text,
                            "context_before": context_before,
                            "context_after": context_after,
                            "regex_score": regex_score,
                            "regex_indicator": regex_indicator,
                            "phase_id": phase_id,
                            "phase_confidence": phase_confidence,
                            "agent_name": entry.name,
                            "workflow_id": workflow_id,
                            "is_boilerplate": is_boilerplate,
                            "created_at": _now_iso(),
                        }
                    )

                    if is_boilerplate:
                        total_boilerplate += 1
                    elif regex_score >= 0.3:
                        total_regex_flagged += 1

                    prev_user_text = text
                    user_turn += 1

                inserted = db.insert_messages(conn, rows)
                dupes = len(rows) - inserted
                total_new += inserted
                total_dupes += dupes

                db.upsert_processed_file(
                    conn,
                    file_key,
                    file_size,
                    file_mtime,
                    len(rows),
                )

        _err(f"    {files_count} JSONL files found")
        if total_skipped_files:
            _err(f"    Skipped {total_skipped_files} files (unchanged)")
        _err(
            f"    Extracted {total_new} new messages ({total_dupes} duplicates skipped)"
        )
        _err(f"    Pre-filtered {total_boilerplate} boilerplate messages")
        _err(f"    Regex flagged {total_regex_flagged} messages (score >= 0.3)")

    # Summary
    status = db.get_status(conn)
    _err(
        f"Database total: {status['messages']} messages, "
        f"{status['classified']} classified, "
        f"{status['corrections']} corrections"
    )
    conn.close()


# ---------------------------------------------------------------------------
# list-sessions command
# ---------------------------------------------------------------------------


def cmd_list_sessions(
    args: argparse.Namespace,
    project_root: Path,
) -> None:
    """List available chicsessions with DB status."""
    from scripts.audit import db

    try:
        sys.path.insert(0, str(PROJECT_ROOT / "submodules" / "claudechic"))
        from claudechic.chicsessions import ChicsessionManager
    except ImportError:
        _err(
            "Could not import ChicsessionManager. "
            "Ensure claudechic submodule is available."
        )
        sys.exit(1)

    mgr = ChicsessionManager(project_root)
    all_names = mgr.list_chicsessions()

    conn = None
    if db.db_exists(project_root):
        conn = db.open_db(project_root, create=False)

    unanalyzed: list[dict[str, Any]] = []
    analyzed: list[dict[str, Any]] = []

    for name in all_names:
        try:
            cs = mgr.load(name)
        except (FileNotFoundError, ValueError):
            continue

        entry: dict[str, Any] = {
            "name": name,
            "agent_count": len(cs.agents),
            "workflow_id": None,
            "current_phase": None,
        }

        if cs.workflow_state:
            entry["workflow_id"] = cs.workflow_state.get("workflow_id")
            entry["current_phase"] = cs.workflow_state.get("current_phase")

        if conn:
            info = db.messages_for_chicsession(conn, name)
            if info["messages_in_db"] > 0:
                entry["in_db"] = True
                entry["messages_in_db"] = info["messages_in_db"]
                entry["corrections_found"] = info["corrections_found"]
                entry["last_extracted"] = info["last_extracted"]
                analyzed.append(entry)
                continue

        entry["in_db"] = False
        est = 0
        for agent_entry in cs.agents:
            for p in _resolve_jsonl_paths(agent_entry.session_id):
                est += _estimate_messages(p)
        entry["estimated_messages"] = est
        unanalyzed.append(entry)

    # Sort: unanalyzed first, then analyzed
    output = unanalyzed + analyzed

    if conn:
        conn.close()

    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Query commands
# ---------------------------------------------------------------------------


def cmd_unclassified(
    args: argparse.Namespace,
    project_root: Path,
) -> None:
    """Output unclassified messages as JSON for the classifier."""
    from scripts.audit import db

    conn = db.open_db(project_root, create=False)
    chunk_size = getattr(args, "chunk_size", 200) or 200
    result = db.query_unclassified(conn, chunk_size=chunk_size)
    conn.close()
    print(json.dumps(result, indent=2))


def cmd_corrections(
    args: argparse.Namespace,
    project_root: Path,
) -> None:
    """Output classified corrections as JSON for the judge."""
    from scripts.audit import db

    conn = db.open_db(project_root, create=False)
    chunk_size = getattr(args, "chunk_size", 200) or 200
    result = db.query_corrections(
        conn,
        phase=getattr(args, "phase", None),
        category=getattr(args, "category", None),
        min_confidence=getattr(args, "min_confidence", None),
        chunk_size=chunk_size,
    )
    conn.close()
    print(json.dumps(result, indent=2))


def cmd_aggregate(
    args: argparse.Namespace,
    project_root: Path,
) -> None:
    """Output aggregated correction patterns as JSON."""
    from scripts.audit import db

    conn = db.open_db(project_root, create=False)
    min_count = getattr(args, "min_count", 2) or 2
    patterns = db.aggregate_corrections(conn, min_count=min_count)
    conn.close()
    print(json.dumps(patterns, indent=2))


# ---------------------------------------------------------------------------
# Batch store commands
# ---------------------------------------------------------------------------


def cmd_store_classifications(
    args: argparse.Namespace,
    project_root: Path,
) -> None:
    """Read JSON array from stdin and store classifications."""
    from scripts.audit import db

    raw = sys.stdin.read()
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        _err(f"Invalid JSON on stdin: {exc}")
        sys.exit(1)

    if not isinstance(items, list):
        _err("Expected a JSON array on stdin.")
        sys.exit(1)

    conn = db.open_db(project_root)
    stored, skipped = db.store_classifications(conn, items)
    conn.close()
    _err(f"Stored {stored} classifications ({skipped} duplicates skipped).")


def cmd_store_suggestions(
    args: argparse.Namespace,
    project_root: Path,
) -> None:
    """Read JSON array from stdin and store suggestions."""
    from scripts.audit import db

    raw = sys.stdin.read()
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        _err(f"Invalid JSON on stdin: {exc}")
        sys.exit(1)

    if not isinstance(items, list):
        _err("Expected a JSON array on stdin.")
        sys.exit(1)

    conn = db.open_db(project_root)
    new_ids = db.store_suggestions(conn, items)
    conn.close()
    print(json.dumps(new_ids))


# ---------------------------------------------------------------------------
# Update suggestion
# ---------------------------------------------------------------------------


def cmd_update_suggestion(
    args: argparse.Namespace,
    project_root: Path,
) -> None:
    """Update fields on an existing suggestion."""
    from scripts.audit import db

    updates: dict[str, Any] = {}
    if getattr(args, "critic_verdict", None):
        updates["critic_verdict"] = args.critic_verdict
    if getattr(args, "critic_reasoning", None):
        updates["critic_reasoning"] = args.critic_reasoning
    if getattr(args, "apply_status", None):
        updates["apply_status"] = args.apply_status
    if getattr(args, "applied_at", None):
        updates["applied_at"] = args.applied_at

    if not updates:
        _err("No update fields provided.")
        sys.exit(1)

    conn = db.open_db(project_root)
    ok = db.update_suggestion(conn, args.suggestion_id, updates)
    conn.close()
    if ok:
        _err(f"Updated suggestion {args.suggestion_id}.")
    else:
        _err(f"Suggestion {args.suggestion_id} not found.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Check command
# ---------------------------------------------------------------------------


def cmd_check(
    args: argparse.Namespace,
    project_root: Path,
) -> None:
    """Run a structured advance check."""
    from scripts.audit import db

    use_json = getattr(args, "json", False)
    check_name = args.check_name

    if check_name == "has-db":
        ok, msg = db.check_has_db(project_root)
        if use_json:
            print(json.dumps({"check": check_name, "pass": ok, "message": msg}))
        else:
            _err(msg)
        sys.exit(0 if ok else 1)

    if not db.db_exists(project_root):
        if use_json:
            print(
                json.dumps(
                    {
                        "check": check_name,
                        "pass": False,
                        "message": "database not found",
                    }
                )
            )
        else:
            _err("FAIL: database not found")
        sys.exit(1)

    conn = db.open_db(project_root, create=False)

    checks = {
        "has-messages": db.check_has_messages,
        "all-classified": db.check_all_classified,
        "all-reviewed": db.check_all_reviewed,
        "all-decided": db.check_all_decided,
    }

    func = checks.get(check_name)
    if func is None:
        _err(f"Unknown check: {check_name}")
        conn.close()
        sys.exit(1)

    ok, msg = func(conn)
    conn.close()
    if use_json:
        print(json.dumps({"check": check_name, "pass": ok, "message": msg}))
    else:
        _err(msg)
    sys.exit(0 if ok else 1)


# ---------------------------------------------------------------------------
# Reset command
# ---------------------------------------------------------------------------


def cmd_reset(
    args: argparse.Namespace,
    project_root: Path,
) -> None:
    """Clear derived data for re-iteration."""
    from scripts.audit import db

    if not getattr(args, "confirm", False):
        _err("Use --confirm to confirm data deletion.")
        sys.exit(1)

    conn = db.open_db(project_root)
    target = args.target

    if target == "classifications":
        n = db.reset_classifications(conn)
        _err(f"Deleted {n} classifications.")
    elif target == "suggestions":
        n = db.reset_suggestions(conn)
        _err(f"Deleted {n} suggestions (and evidence links).")
    else:
        _err(f"Unknown reset target: {target}")
        conn.close()
        sys.exit(1)

    conn.close()


# ---------------------------------------------------------------------------
# Status command
# ---------------------------------------------------------------------------


def cmd_status(
    args: argparse.Namespace,
    project_root: Path,
) -> None:
    """Display database status dashboard."""
    from scripts.audit import db

    use_json = getattr(args, "json", False)

    if not db.db_exists(project_root):
        empty: dict[str, Any] = {
            "db_exists": False,
            "messages": 0,
            "classified": 0,
            "unclassified": 0,
            "corrections": 0,
            "regex_flagged": 0,
            "suggestions": 0,
            "pending": 0,
            "applied": 0,
            "skipped": 0,
            "unreviewed": 0,
            "files_processed": 0,
            "last_extract": None,
            "chicsessions_processed": "",
        }
        if use_json:
            print(json.dumps(empty, indent=2))
        else:
            for k, v in empty.items():
                print(f"{k}: {v if v is not None else ''}")
        return

    conn = db.open_db(project_root, create=False)
    s = db.get_status(conn)
    conn.close()
    s["db_exists"] = True

    if use_json:
        print(json.dumps(s, indent=2))
    else:
        for k, v in s.items():
            if v is None:
                print(f"{k}: ")
            elif isinstance(v, bool):
                print(f"{k}: {'true' if v else 'false'}")
            else:
                print(f"{k}: {v}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _err(msg: str) -> None:
    """Print to stderr."""
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit workflow CLI",
        prog="audit.py",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Project root directory (default: auto-detect)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list-sessions
    sub.add_parser("list-sessions", help="Show available chicsessions")

    # extract
    p_extract = sub.add_parser("extract", help="Extract messages from JSONL")
    g = p_extract.add_mutually_exclusive_group(required=True)
    g.add_argument("--sessions", type=str, help="Comma-separated chicsession names")
    g.add_argument("--all", action="store_true", help="Process all chicsessions")
    p_extract.add_argument(
        "--project-dir", type=str, help="Override project directory for JSONL"
    )

    # unclassified
    p_uncl = sub.add_parser("unclassified", help="Output unclassified messages")
    p_uncl.add_argument("--chunk-size", type=int, default=200)

    # corrections
    p_corr = sub.add_parser("corrections", help="Output corrections")
    p_corr.add_argument("--phase", type=str)
    p_corr.add_argument("--category", type=str)
    p_corr.add_argument("--min-confidence", type=str)
    p_corr.add_argument("--chunk-size", type=int, default=200)

    # aggregate
    p_agg = sub.add_parser("aggregate", help="Aggregate correction patterns")
    p_agg.add_argument("--min-count", type=int, default=2)

    # store-classifications
    sub.add_parser("store-classifications", help="Store classifications from stdin")

    # store-suggestions
    sub.add_parser("store-suggestions", help="Store suggestions from stdin")

    # update-suggestion
    p_upd = sub.add_parser("update-suggestion", help="Update suggestion fields")
    p_upd.add_argument("suggestion_id", type=int)
    p_upd.add_argument("--critic-verdict", type=str)
    p_upd.add_argument("--critic-reasoning", type=str)
    p_upd.add_argument("--apply-status", type=str)
    p_upd.add_argument("--applied-at", type=str)

    # check
    p_chk = sub.add_parser("check", help="Run advance check")
    p_chk.add_argument(
        "check_name",
        type=str,
        choices=[
            "has-db",
            "has-messages",
            "all-classified",
            "all-reviewed",
            "all-decided",
        ],
    )
    p_chk.add_argument("--json", action="store_true", help="Output result as JSON")

    # reset
    p_rst = sub.add_parser("reset", help="Clear derived data")
    p_rst.add_argument("target", type=str, choices=["classifications", "suggestions"])
    p_rst.add_argument("--confirm", action="store_true")

    # status
    p_stat = sub.add_parser("status", help="Database status dashboard")
    p_stat.add_argument("--json", action="store_true", help="Output result as JSON")

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.project_root:
        project_root = Path(args.project_root).resolve()
    else:
        project_root = PROJECT_ROOT

    dispatch = {
        "list-sessions": cmd_list_sessions,
        "extract": cmd_extract,
        "unclassified": cmd_unclassified,
        "corrections": cmd_corrections,
        "aggregate": cmd_aggregate,
        "store-classifications": cmd_store_classifications,
        "store-suggestions": cmd_store_suggestions,
        "update-suggestion": cmd_update_suggestion,
        "check": cmd_check,
        "reset": cmd_reset,
        "status": cmd_status,
    }

    func = dispatch.get(args.command)
    if func:
        func(args, project_root)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
