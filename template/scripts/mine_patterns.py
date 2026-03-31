#!/usr/bin/env python3
"""
Conversation History Mining Tool for PATTERNS.md maintenance.

3-tier detection pipeline for extracting user corrections from Claude
conversation history JSONL files.

Tier 1: Fast regex + behavioral heuristics (stdlib only, always runs)
Tier 2: Zero-shot semantic classification (--semantic flag)
Tier 3: Embedding similarity + HDBSCAN clustering (--cluster flag)

Ported from DECODE-PRISM/scripts/mine_patterns.py with the following changes:
  1. JSONL parsing isolation (ParseResult/Message dataclasses)
  2. Version checking (KNOWN_VERSIONS set, warn on unknown)
  3. Configurable project directories (no hard-coded paths)
  4. Validation mode (--validate flag)
  5. Configurable role detection (DEFAULT_AGENT_ROLES list)

Usage:
    # Tier 1 only - fast bulk scan
    python scripts/mine_patterns.py --scan-all

    # Tier 1 + semantic enrichment
    python scripts/mine_patterns.py --scan-all --semantic

    # Full pipeline (Tier 1 + 2 + 3)
    python scripts/mine_patterns.py --scan-all --semantic --cluster

    # Incremental (new/modified sessions only)
    python scripts/mine_patterns.py

    # Dry run
    python scripts/mine_patterns.py --dry-run

    # Validate parsing only (no pipeline)
    python scripts/mine_patterns.py --validate

    # Scan specific project directories
    python scripts/mine_patterns.py --project-dirs dir1 dir2

    # Scan ALL directories under ~/.claude/projects/
    python scripts/mine_patterns.py --project-dirs auto
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
STATE_FILE = Path(__file__).resolve().parent.parent / ".patterns_mining_state.json"
DEFAULT_THRESHOLD = 0.3
DEFAULT_OUTPUT = "corrections_report.json"

# Known-good JSONL format versions.  When Claude Code updates its session
# format, add the new version here after verifying the parser handles it.
KNOWN_VERSIONS = {
    "2.1.59",
    "2.1.60",
    "2.1.61",
    "2.1.62",
    "2.1.63",
    "2.2.0",
    "2.2.1",
}

# Default agent roles for sub-agent detection.  Override with --roles.
DEFAULT_AGENT_ROLES = [
    "Coordinator",
    "Implementer",
    "Test Engineer",
    "TestEngineer",
    "Skeptic",
    "Composability",
    "Researcher",
    "Terminology Guardian",
    "User Alignment",
    "Lab Notebook",
    "UI Designer",
    "Experiment Designer",
    "Cluster Operations",
    "Results Analyst",
    "Project Integrator",
    "Sync Coordinator",
]

# ---------------------------------------------------------------------------
# JSONL Parsing Layer (Change #1: Parsing Isolation)
#
# This is the ONLY code that touches the JSONL format.  Everything above
# and below works with ParseResult / Message dataclasses.
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """A single user or assistant message extracted from a JSONL session."""
    role: str               # "user" | "assistant"
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
    session_type: str = "main"          # "main" | "sub-agent"
    agent_type: str | None = None
    workflow: str = "solo"              # "ao_project_team" | "ao_experiment_team" | "solo"
    session_date: str = "unknown"
    session_id: str | None = None
    stats: ParseStats = field(default_factory=ParseStats)
    path: Path | None = None


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
    # Version may appear in metadata fields
    for key in ("version", "codeVersion", "clientVersion"):
        val = obj.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def parse_session(
    path: Path,
    agent_roles: list[str] | None = None,
) -> ParseResult:
    """Parse a JSONL session file into structured data.

    This function is the SOLE entry point for JSONL format handling.
    All format-specific logic is contained here (Change #1).

    Args:
        path: Path to the JSONL session file.
        agent_roles: List of known agent role names for sub-agent detection.
                     Defaults to DEFAULT_AGENT_ROLES.

    Returns:
        ParseResult with messages, metadata, and parse statistics.
    """
    if agent_roles is None:
        agent_roles = DEFAULT_AGENT_ROLES

    result = ParseResult(path=path)
    stats = result.stats
    session_date_found = False
    session_id_found = False

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
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

            # --- Version detection (Change #2) ---
            if stats.version is None:
                detected = _detect_version(obj)
                if detected:
                    stats.version = detected
                    if detected not in KNOWN_VERSIONS:
                        stats.version_known = False
                        warnings.warn(
                            f"Unknown JSONL version '{detected}' in {path.name}. "
                            f"Known versions: {sorted(KNOWN_VERSIONS)}. "
                            f"Parser may produce incorrect results.",
                            stacklevel=2,
                        )

            msg_type = obj.get("type")
            if msg_type not in ("user", "assistant"):
                stats.unknown_types += 1
                continue

            # Record session date from first timestamped message
            ts = obj.get("timestamp")
            if ts and not session_date_found:
                try:
                    result.session_date = ts[:10]  # YYYY-MM-DD
                    session_date_found = True
                except (TypeError, IndexError):
                    pass

            if not session_id_found:
                sid = obj.get("sessionId")
                if sid:
                    result.session_id = sid
                    session_id_found = True

            # Skip tool-result user messages -- not real user input
            if msg_type == "user" and "toolUseResult" in obj:
                stats.skipped_tool_results += 1
                continue

            msg_body = obj.get("message", {})
            content = msg_body.get("content", "")
            text = _extract_text(content)

            if not text.strip():
                stats.empty_messages += 1
                continue

            result.messages.append(Message(
                role=msg_type,
                text=text,
                timestamp=ts,
                session_id=obj.get("sessionId"),
            ))

    # Detect sub-agent sessions and agent type from first user message
    if result.messages:
        first_user_text = ""
        for m in result.messages:
            if m.role == "user":
                first_user_text = m.text
                break

        if "[Spawned by agent" in first_user_text:
            result.session_type = "sub-agent"
            result.agent_type = _detect_agent_type(first_user_text, agent_roles)

        # Detect workflow from any user message
        for m in result.messages:
            if m.role == "user":
                if "/ao_project_team" in m.text:
                    result.workflow = "ao_project_team"
                    break
                if "/ao_experiment_team" in m.text:
                    result.workflow = "ao_experiment_team"
                    break

    return result


def _detect_agent_type(
    text: str,
    agent_roles: list[str],
) -> str | None:
    """Extract agent type from a sub-agent spawn message.

    Uses a configurable list of known roles (Change #5) instead of
    hard-coded regex alternatives.
    """
    # Build a regex alternation from the configured role list
    escaped_roles = [re.escape(role) for role in agent_roles]
    roles_pattern = "|".join(escaped_roles)

    patterns = [
        # Match "You are the **RoleName**" with optional decorations
        rf"You\s+are\s+(?:the\s+)?\*{{0,2}}({roles_pattern})\b",
        # Fallback: generic pattern for unknown roles
        r"You\s+are\s+(?:the\s+)?\*{0,2}([\w\s]+?)\*{0,2}\s*(?:\u2014|agent|Agent|\.|$)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).strip().strip("*")
    return None


# ---------------------------------------------------------------------------
# Session Discovery (Change #3: Configurable Project Directories)
# ---------------------------------------------------------------------------


def discover_session_files(
    project_dirs: list[str] | None = None,
) -> list[Path]:
    """Find all JSONL session files.

    Args:
        project_dirs: Explicit list of subdirectory names under
                      ~/.claude/projects/, or None / ["auto"] to scan
                      ALL subdirectories.

    Returns:
        Sorted list of JSONL file paths.
    """
    files: list[Path] = []

    if not CLAUDE_PROJECTS_DIR.is_dir():
        return files

    if project_dirs is None or project_dirs == ["auto"]:
        # Auto-discover: scan every subdirectory
        for subdir in sorted(CLAUDE_PROJECTS_DIR.iterdir()):
            if subdir.is_dir():
                files.extend(subdir.glob("*.jsonl"))
    else:
        for dir_name in project_dirs:
            proj_dir = CLAUDE_PROJECTS_DIR / dir_name
            if proj_dir.is_dir():
                files.extend(proj_dir.glob("*.jsonl"))

    return sorted(files)


# ---------------------------------------------------------------------------
# Tier 1: Regex pattern banks
# ---------------------------------------------------------------------------

# Each pattern has (compiled_regex, weight, label).  Weight is the base
# contribution to the 0-1 score for a single match.

NEGATION_PATTERNS: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"\bno[,.]?\s+that'?s\b", re.I), 0.45, "no, that's"),
    (re.compile(r"\bnot what I\b", re.I), 0.50, "not what I"),
    (re.compile(r"\bthat'?s not\s+(right|correct|what)\b", re.I), 0.50, "that's not right"),
    (re.compile(r"\bthat'?s\s+wrong\b", re.I), 0.55, "that's wrong"),
    (re.compile(r"\bno[,.]?\s+(I\s+)?(said|meant|asked|wanted)\b", re.I), 0.50, "no, I said"),
    (re.compile(r"\bwrong\b", re.I), 0.30, "wrong"),
    (re.compile(r"\bincorrect\b", re.I), 0.35, "incorrect"),
    (re.compile(r"\bnot\s+correct\b", re.I), 0.40, "not correct"),
]

FRUSTRATION_PATTERNS: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"\bgaslighting\b", re.I), 0.70, "gaslighting"),
    (re.compile(r"\byou'?re\s+not\s+listening\b", re.I), 0.65, "you're not listening"),
    (re.compile(r"\bstop\s+(doing|it|that)\b", re.I), 0.50, "stop doing"),
    (re.compile(r"\bI\s+already\s+(said|told|explained)\b", re.I), 0.55, "I already said"),
    (re.compile(r"\bhow\s+many\s+times\b", re.I), 0.55, "how many times"),
    (re.compile(r"\bplease\s+(just\s+)?read\b", re.I), 0.35, "please read"),
    (re.compile(r"\bpay\s+attention\b", re.I), 0.55, "pay attention"),
    (re.compile(r"\byou\s+keep\b", re.I), 0.40, "you keep"),
    (re.compile(r"\bfrustrat", re.I), 0.45, "frustration"),
]

ERROR_PATTERNS: list[tuple[re.Pattern, float, str]] = [
    (re.compile(r"\bbug\b", re.I), 0.25, "bug"),
    (re.compile(r"\bbroken\b", re.I), 0.30, "broken"),
    (re.compile(r"\berror\b", re.I), 0.20, "error"),
    (re.compile(r"\bcrash(es|ed|ing)?\b", re.I), 0.25, "crash"),
    (re.compile(r"\bfail(s|ed|ing|ure)?\b", re.I), 0.20, "fail"),
    (re.compile(r"\bdoesn'?t\s+work\b", re.I), 0.35, "doesn't work"),
    (re.compile(r"\bnot\s+working\b", re.I), 0.35, "not working"),
]

CORRECTION_PATTERNS: list[tuple[re.Pattern, float, str]] = [
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
    (re.compile(r"\byou\s+(missed|forgot|skipped|ignored|overlooked)\b", re.I), 0.50, "you missed"),
    (re.compile(r"\bdo(n'?t|es\s*n'?t)\s+(modify|change|touch|edit|alter)\b", re.I), 0.40, "don't modify"),
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
# Tier 1: Regex + behavioral heuristics
# ---------------------------------------------------------------------------


def _jaccard_similarity(a: str, b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def tier1_score_message(
    text: str,
    preceding_agent_text: str | None,
    prev_user_text: str | None,
    is_near_session_end: bool,
    turn_index: int,
    total_user_turns: int,
    extra_keywords: list[str] | None = None,
) -> tuple[float, str | None]:
    """Score a user message using Tier 1 regex + behavioral heuristics.

    Returns (score 0-1, best_indicator_label_or_None).
    """
    scores: list[float] = []
    best_indicator: str | None = None
    best_indicator_score = 0.0

    # --- Regex pattern matching ---
    for _bank_name, bank in ALL_PATTERN_BANKS:
        for pattern, weight, label in bank:
            if pattern.search(text):
                scores.append(weight)
                if weight > best_indicator_score:
                    best_indicator_score = weight
                    best_indicator = label

    # --- Extra user-provided keywords ---
    if extra_keywords:
        text_lower = text.lower()
        for kw in extra_keywords:
            if kw.lower() in text_lower:
                w = 0.35
                scores.append(w)
                if w > best_indicator_score:
                    best_indicator_score = w
                    best_indicator = kw

    # --- Behavioral heuristics ---

    # Short message after agent response (<50 chars = likely rejection/correction)
    if preceding_agent_text and len(text.strip()) < 50 and len(text.strip()) > 2:
        w = 0.30
        scores.append(w)
        if w > best_indicator_score:
            best_indicator_score = w
            best_indicator = "short_response"

    # User repeats themselves (Jaccard > 0.6 with previous user message)
    if prev_user_text and _jaccard_similarity(text, prev_user_text) > 0.6:
        w = 0.45
        scores.append(w)
        if w > best_indicator_score:
            best_indicator_score = w
            best_indicator = "user_repeat"

    # Session abandonment (session ends within 2 turns of this message)
    if is_near_session_end and total_user_turns > 1 and turn_index >= total_user_turns - 2:
        # Only boost if there's already some signal
        if scores:
            w = 0.15
            scores.append(w)

    # Combine scores: take the max single score + diminishing bonus for
    # additional signals (caps at 1.0).  This means a single strong signal
    # alone can promote, but multiple weak signals also add up.
    if not scores:
        return 0.0, None

    scores.sort(reverse=True)
    combined = scores[0]
    for s in scores[1:]:
        combined += s * 0.3  # diminishing additional signal
    combined = min(combined, 1.0)

    return combined, best_indicator


def run_tier1(
    sessions: list[ParseResult],
    threshold: float,
    extra_keywords: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Run Tier 1 on all sessions, return candidate corrections."""
    candidates: list[dict[str, Any]] = []

    for sess in sessions:
        messages = sess.messages
        # Build list of (index, user_text) for real user messages only
        user_msgs: list[tuple[int, str]] = []
        for idx, m in enumerate(messages):
            if m.role == "user":
                user_msgs.append((idx, m.text))

        if not user_msgs:
            continue

        total_user_turns = len(user_msgs)

        for user_turn_idx, (msg_idx, user_text) in enumerate(user_msgs):
            # Find preceding agent message
            preceding_agent_text = None
            for j in range(msg_idx - 1, -1, -1):
                if messages[j].role == "assistant":
                    preceding_agent_text = messages[j].text
                    break

            # Previous user message
            prev_user_text = None
            if user_turn_idx > 0:
                prev_user_text = user_msgs[user_turn_idx - 1][1]

            # Near session end?
            is_near_end = user_turn_idx >= total_user_turns - 2

            score, indicator = tier1_score_message(
                text=user_text,
                preceding_agent_text=preceding_agent_text,
                prev_user_text=prev_user_text,
                is_near_session_end=is_near_end,
                turn_index=user_turn_idx,
                total_user_turns=total_user_turns,
                extra_keywords=extra_keywords,
            )

            if score >= threshold:
                # Truncate long messages for readability
                user_preview = user_text[:2000] if len(user_text) > 2000 else user_text
                agent_preview = None
                if preceding_agent_text:
                    agent_preview = (
                        preceding_agent_text[:1000]
                        if len(preceding_agent_text) > 1000
                        else preceding_agent_text
                    )

                candidates.append({
                    "session_file": str(sess.path),
                    "session_date": sess.session_date,
                    "session_type": sess.session_type,
                    "agent_type": sess.agent_type,
                    "workflow": sess.workflow,
                    "user_message": user_preview,
                    "preceding_agent_message": agent_preview,
                    "correction_indicator": indicator,
                    "confidence": round(score, 3),
                    "detection_tier": 1,
                    "semantic_label": None,
                    "cluster_id": None,
                    "matched_pattern": None,
                })

    return candidates


# ---------------------------------------------------------------------------
# Tier 2: Zero-shot semantic classification
# ---------------------------------------------------------------------------

TIER2_LABELS = [
    "user corrects mistake",
    "user reports bug",
    "user expresses frustration",
    "user rejects suggestion",
    "user clarifies misunderstood instruction",
]


def run_tier2(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enrich Tier 1 candidates with zero-shot semantic classification.

    NON-FILTERING: all candidates pass through.  Tier 2 adds semantic_label
    and may update confidence if the classifier score is higher.
    """
    if not candidates:
        return candidates

    try:
        from transformers import pipeline as hf_pipeline
    except ImportError:
        print(
            "WARNING: transformers not installed. "
            "Skipping Tier 2 semantic classification.",
            file=sys.stderr,
        )
        return candidates

    import torch
    device = 0 if torch.cuda.is_available() else -1
    device_name = "GPU (CUDA)" if device == 0 else "CPU"
    print(
        f"Tier 2: Loading zero-shot classifier "
        f"(MoritzLaurer/deberta-v3-base-zeroshot-v2.0) on {device_name}...",
        file=sys.stderr,
    )
    classifier = hf_pipeline(
        "zero-shot-classification",
        model="MoritzLaurer/deberta-v3-base-zeroshot-v2.0",
        device=device,
    )

    total = len(candidates)
    print(f"Tier 2: Classifying {total} candidates...", file=sys.stderr)

    batch_size = 16
    for start in range(0, total, batch_size):
        batch = candidates[start : start + batch_size]
        texts = [c["user_message"][:512] for c in batch]  # truncate for model

        results = classifier(
            texts,
            candidate_labels=TIER2_LABELS,
            multi_label=False,
        )

        # classifier returns a single dict if len(texts)==1, else a list
        if isinstance(results, dict):
            results = [results]

        for c, result in zip(batch, results):
            top_label = result["labels"][0]
            top_score = result["scores"][0]
            c["semantic_label"] = top_label

            # Update confidence if semantic score is higher
            if top_score > c["confidence"]:
                c["confidence"] = round(top_score, 3)
                c["detection_tier"] = 2

        done = min(start + batch_size, total)
        if done % 100 == 0 or done == total:
            print(
                f"  Tier 2 progress: {done}/{total} ({done * 100 // total}%)",
                file=sys.stderr,
            )

    return candidates


# ---------------------------------------------------------------------------
# Tier 3: Embedding + HDBSCAN clustering
# ---------------------------------------------------------------------------


def run_tier3(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cluster all candidates by embedding similarity using HDBSCAN."""
    if not candidates:
        return candidates

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print(
            "WARNING: sentence-transformers not installed. "
            "Skipping Tier 3 clustering.",
            file=sys.stderr,
        )
        return candidates

    try:
        from sklearn.cluster import HDBSCAN
    except ImportError:
        print(
            "WARNING: sklearn.cluster.HDBSCAN not available. "
            "Skipping Tier 3 clustering.",
            file=sys.stderr,
        )
        return candidates

    import torch
    device_str = "cuda" if torch.cuda.is_available() else "cpu"
    print(
        f"Tier 3: Loading embedding model "
        f"(sentence-transformers/all-MiniLM-L6-v2) on {device_str}...",
        file=sys.stderr,
    )
    model = SentenceTransformer("all-MiniLM-L6-v2", device=device_str)

    texts = [c["user_message"][:512] for c in candidates]
    print(f"Tier 3: Embedding {len(texts)} candidates...", file=sys.stderr)
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)

    print("Tier 3: Running HDBSCAN clustering...", file=sys.stderr)
    clusterer = HDBSCAN(
        min_cluster_size=3,
        min_samples=2,
        metric="euclidean",
    )
    labels = clusterer.fit_predict(embeddings)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = sum(1 for lbl in labels if lbl == -1)
    print(
        f"Tier 3: Found {n_clusters} clusters, {n_noise} noise points.",
        file=sys.stderr,
    )

    for c, label in zip(candidates, labels):
        c["cluster_id"] = int(label)

    return candidates


# ---------------------------------------------------------------------------
# State tracking
# ---------------------------------------------------------------------------


def load_state() -> dict[str, Any]:
    """Load the mining state file."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "last_run": None,
        "processed_sessions": {},
        "total_corrections": 0,
        "total_sessions_scanned": 0,
    }


def save_state(state: dict[str, Any]) -> None:
    """Save the mining state file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def filter_sessions_incremental(
    files: list[Path], state: dict[str, Any]
) -> list[Path]:
    """Filter session files to only those new or modified since last scan."""
    processed = state.get("processed_sessions", {})
    new_files: list[Path] = []
    for f in files:
        fpath = str(f)
        mtime = f.stat().st_mtime
        if fpath in processed and processed[fpath].get("mtime") == mtime:
            continue
        new_files.append(f)
    return new_files


# ---------------------------------------------------------------------------
# Validation Mode (Change #4)
# ---------------------------------------------------------------------------


def run_validate(
    project_dirs: list[str] | None,
    agent_roles: list[str],
) -> None:
    """Run parsing validation and report stats without executing pipeline.

    This mode is useful for verifying that the parser handles the current
    JSONL format correctly after Claude Code updates.
    """
    files = discover_session_files(project_dirs)
    print(f"Discovered {len(files)} JSONL session files.", file=sys.stderr)

    if not files:
        print("No session files found.", file=sys.stderr)
        return

    total_stats = ParseStats()
    versions_seen: dict[str, int] = {}
    session_types: dict[str, int] = {"main": 0, "sub-agent": 0}
    workflows: dict[str, int] = {}
    agent_types: dict[str, int] = {}
    parse_errors = 0

    for f in files:
        try:
            result = parse_session(f, agent_roles=agent_roles)
        except Exception as e:
            parse_errors += 1
            if parse_errors <= 5:
                print(f"  ERROR: {f.name}: {e}", file=sys.stderr)
            continue

        s = result.stats
        total_stats.total_lines += s.total_lines
        total_stats.json_errors += s.json_errors
        total_stats.skipped_tool_results += s.skipped_tool_results
        total_stats.empty_messages += s.empty_messages
        total_stats.unknown_types += s.unknown_types

        if s.version:
            versions_seen[s.version] = versions_seen.get(s.version, 0) + 1

        session_types[result.session_type] = (
            session_types.get(result.session_type, 0) + 1
        )
        workflows[result.workflow] = workflows.get(result.workflow, 0) + 1
        if result.agent_type:
            agent_types[result.agent_type] = (
                agent_types.get(result.agent_type, 0) + 1
            )

    # Report
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  JSONL Parse Validation Report", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Files scanned:          {len(files)}", file=sys.stderr)
    print(f"  Parse errors (files):   {parse_errors}", file=sys.stderr)
    print(f"  Total JSONL lines:      {total_stats.total_lines}", file=sys.stderr)
    print(f"  JSON decode errors:     {total_stats.json_errors}", file=sys.stderr)
    print(f"  Skipped tool results:   {total_stats.skipped_tool_results}", file=sys.stderr)
    print(f"  Empty messages:         {total_stats.empty_messages}", file=sys.stderr)
    print(f"  Unknown message types:  {total_stats.unknown_types}", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"  Versions seen:", file=sys.stderr)
    for v, count in sorted(versions_seen.items()):
        known = "OK" if v in KNOWN_VERSIONS else "UNKNOWN"
        print(f"    {v}: {count} files [{known}]", file=sys.stderr)
    print(f"", file=sys.stderr)
    print(f"  Session types:  {session_types}", file=sys.stderr)
    print(f"  Workflows:      {workflows}", file=sys.stderr)
    if agent_types:
        print(f"  Agent types:", file=sys.stderr)
        for at, count in sorted(agent_types.items(), key=lambda x: -x[1]):
            print(f"    {at}: {count}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    # Exit with error if there were unknown versions
    unknown_versions = [v for v in versions_seen if v not in KNOWN_VERSIONS]
    if unknown_versions:
        print(
            f"\nWARNING: Unknown versions detected: {unknown_versions}",
            file=sys.stderr,
        )
        print(
            "Add to KNOWN_VERSIONS after verifying parser correctness.",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def load_extra_keywords(path: str | None) -> list[str] | None:
    """Load extra keywords from a file (one per line)."""
    if path is None:
        return None
    keywords: list[str] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                keywords.append(line)
    return keywords if keywords else None


def run_pipeline(args: argparse.Namespace) -> None:
    """Execute the full mining pipeline."""
    # Resolve agent roles (Change #5)
    agent_roles = DEFAULT_AGENT_ROLES
    if args.roles:
        agent_roles = [r.strip() for r in args.roles.split(",")]

    # Resolve project directories (Change #3)
    project_dirs = args.project_dirs  # None, ["auto"], or explicit list

    # Handle --validate mode (Change #4)
    if args.validate:
        run_validate(project_dirs, agent_roles)
        return

    # Discover sessions
    all_files = discover_session_files(project_dirs)
    mode_label = "auto-discover" if project_dirs is None or project_dirs == ["auto"] else "explicit dirs"
    print(
        f"Discovered {len(all_files)} JSONL session files ({mode_label}).",
        file=sys.stderr,
    )

    # Filter for incremental mode
    state = load_state()
    if args.scan_all:
        files = all_files
        print("Mode: full scan (--scan-all)", file=sys.stderr)
    else:
        files = filter_sessions_incremental(all_files, state)
        print(
            f"Mode: incremental ({len(files)} new/modified out of "
            f"{len(all_files)} total)",
            file=sys.stderr,
        )

    if not files:
        print("No new sessions to process.", file=sys.stderr)
        return

    # Dry run
    if args.dry_run:
        print(f"\n--- DRY RUN ---")
        print(f"Would scan {len(files)} session files:")
        for f in files[:20]:
            print(f"  {f}")
        if len(files) > 20:
            print(f"  ... and {len(files) - 20} more")
        print(f"\nTiers enabled: 1{' + 2 (semantic)' if args.semantic else ''}"
              f"{' + 3 (cluster)' if args.cluster else ''}")
        print(f"Threshold: {args.threshold}")
        return

    # Parse sessions
    print(f"\nParsing {len(files)} session files...", file=sys.stderr)
    sessions: list[ParseResult] = []
    parse_errors = 0
    for f in files:
        try:
            sess = parse_session(f, agent_roles=agent_roles)
            sessions.append(sess)
        except Exception as e:
            parse_errors += 1
            if parse_errors <= 5:
                print(f"  WARNING: Failed to parse {f.name}: {e}", file=sys.stderr)

    if parse_errors:
        print(f"  ({parse_errors} files had parse errors)", file=sys.stderr)

    # Session stats
    sub_agents = sum(1 for s in sessions if s.session_type == "sub-agent")
    main_sessions = len(sessions) - sub_agents
    print(
        f"Parsed {len(sessions)} sessions "
        f"({main_sessions} main, {sub_agents} sub-agent)",
        file=sys.stderr,
    )

    # Load extra keywords
    extra_keywords = load_extra_keywords(args.keywords_file)

    # Tier 1
    print(f"\n--- Tier 1: Regex + Behavioral Heuristics ---", file=sys.stderr)
    candidates = run_tier1(sessions, args.threshold, extra_keywords)
    print(
        f"Tier 1: {len(candidates)} candidates above threshold {args.threshold}",
        file=sys.stderr,
    )

    # Tier 2 (if enabled)
    if args.semantic:
        print(f"\n--- Tier 2: Semantic Classification ---", file=sys.stderr)
        candidates = run_tier2(candidates)
        tier2_promoted = sum(1 for c in candidates if c["detection_tier"] == 2)
        print(
            f"Tier 2: {tier2_promoted} candidates had semantic score > regex score",
            file=sys.stderr,
        )

    # Tier 3 (if enabled)
    if args.cluster:
        print(f"\n--- Tier 3: Embedding Clustering ---", file=sys.stderr)
        candidates = run_tier3(candidates)

    # Summary statistics
    print(f"\n--- Summary ---", file=sys.stderr)
    print(f"Total candidates: {len(candidates)}", file=sys.stderr)
    if candidates:
        avg_conf = sum(c["confidence"] for c in candidates) / len(candidates)
        print(f"Average confidence: {avg_conf:.3f}", file=sys.stderr)

        # Breakdown by session type
        by_type: dict[str, int] = {}
        for c in candidates:
            key = c["session_type"]
            by_type[key] = by_type.get(key, 0) + 1
        print(f"By session type: {by_type}", file=sys.stderr)

        # Breakdown by workflow
        by_wf: dict[str, int] = {}
        for c in candidates:
            key = c["workflow"]
            by_wf[key] = by_wf.get(key, 0) + 1
        print(f"By workflow: {by_wf}", file=sys.stderr)

        # Top indicators
        indicators: dict[str, int] = {}
        for c in candidates:
            ind = c["correction_indicator"]
            if ind:
                indicators[ind] = indicators.get(ind, 0) + 1
        top_indicators = sorted(indicators.items(), key=lambda x: -x[1])[:10]
        print(f"Top correction indicators:", file=sys.stderr)
        for ind, count in top_indicators:
            print(f"  {ind}: {count}", file=sys.stderr)

        if args.cluster:
            cluster_ids = set(c["cluster_id"] for c in candidates if c["cluster_id"] is not None)
            real_clusters = cluster_ids - {-1}
            print(f"Clusters: {len(real_clusters)} "
                  f"(+ {sum(1 for c in candidates if c.get('cluster_id') == -1)} noise)",
                  file=sys.stderr)

        if args.semantic:
            by_label: dict[str, int] = {}
            for c in candidates:
                lbl = c.get("semantic_label")
                if lbl:
                    by_label[lbl] = by_label.get(lbl, 0) + 1
            print(f"By semantic label:", file=sys.stderr)
            for lbl, count in sorted(by_label.items(), key=lambda x: -x[1]):
                print(f"  {lbl}: {count}", file=sys.stderr)

    # Write output
    output_path = Path(args.output)
    report = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sessions_scanned": len(sessions),
            "total_candidates": len(candidates),
            "threshold": args.threshold,
            "tiers_enabled": [1]
            + ([2] if args.semantic else [])
            + ([3] if args.cluster else []),
            "scan_mode": "full" if args.scan_all else "incremental",
        },
        "corrections": candidates,
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport written to {output_path}", file=sys.stderr)

    # Update state
    now_iso = datetime.now(timezone.utc).isoformat()
    for sess in sessions:
        fpath = str(sess.path)
        mtime = sess.path.stat().st_mtime
        corrections_in_session = sum(
            1 for c in candidates if c["session_file"] == fpath
        )
        state["processed_sessions"][fpath] = {
            "mtime": mtime,
            "corrections_found": corrections_in_session,
        }
    state["last_run"] = now_iso
    state["total_sessions_scanned"] = len(state["processed_sessions"])
    state["total_corrections"] = sum(
        v["corrections_found"]
        for v in state["processed_sessions"].values()
    )
    save_state(state)
    print(f"State saved to {STATE_FILE}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Mine Claude conversation history for user correction patterns. "
            "3-tier detection pipeline: regex -> semantic -> clustering."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Tier 1 only - fast bulk scan
  python scripts/mine_patterns.py --scan-all

  # Tier 1 + semantic enrichment
  python scripts/mine_patterns.py --scan-all --semantic

  # Full pipeline
  python scripts/mine_patterns.py --scan-all --semantic --cluster

  # Incremental (new sessions only)
  python scripts/mine_patterns.py

  # Dry run
  python scripts/mine_patterns.py --dry-run

  # Validate parsing (no pipeline)
  python scripts/mine_patterns.py --validate

  # Scan specific project dirs
  python scripts/mine_patterns.py --project-dirs my-project another-project

  # Scan all project dirs
  python scripts/mine_patterns.py --project-dirs auto
""",
    )

    parser.add_argument(
        "--scan-all",
        action="store_true",
        default=False,
        help="Scan all sessions (ignore incremental state). Default: incremental.",
    )
    parser.add_argument(
        "--semantic",
        action="store_true",
        default=False,
        help="Enable Tier 2 zero-shot semantic classification.",
    )
    parser.add_argument(
        "--cluster",
        action="store_true",
        default=False,
        help="Enable Tier 3 embedding + HDBSCAN clustering.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON report file (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be scanned without processing.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        default=False,
        help="Validate JSONL parsing and report stats (no pipeline run).",
    )
    parser.add_argument(
        "--keywords-file",
        type=str,
        default=None,
        help="File with extra keywords (one per line) to extend built-in patterns.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Tier 1 score threshold (default: {DEFAULT_THRESHOLD}). "
        "Lower = more candidates, higher = fewer.",
    )
    parser.add_argument(
        "--project-dirs",
        nargs="+",
        default=None,
        help=(
            "Project subdirectory names under ~/.claude/projects/ to scan. "
            "Use 'auto' to scan all subdirectories. "
            "Default: auto (scan everything)."
        ),
    )
    parser.add_argument(
        "--roles",
        type=str,
        default=None,
        help=(
            "Comma-separated list of agent role names for sub-agent detection. "
            "Default: built-in project-team roles."
        ),
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_pipeline(args)


if __name__ == "__main__":
    main()
