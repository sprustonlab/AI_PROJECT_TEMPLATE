"""Head-to-head: GLiClass 2B vs regex tier-1 on 5 real session files."""

import json
import re
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Regex tier-1 scorer (extracted from scripts/mine_patterns.py)
# ---------------------------------------------------------------------------

NEGATION_PATTERNS = [
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

FRUSTRATION_PATTERNS = [
    (re.compile(r"\bgaslighting\b", re.I), 0.70, "gaslighting"),
    (re.compile(r"\byou'?re\s+not\s+listening\b", re.I), 0.65, "you're not listening"),
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

ERROR_PATTERNS = [
    (re.compile(r"\bbug\b", re.I), 0.25, "bug"),
    (re.compile(r"\bbroken\b", re.I), 0.30, "broken"),
    (re.compile(r"\berror\b", re.I), 0.20, "error"),
    (re.compile(r"\bcrash(es|ed|ing)?\b", re.I), 0.25, "crash"),
    (re.compile(r"\bfail(s|ed|ing|ure)?\b", re.I), 0.20, "fail"),
    (re.compile(r"\bdoesn'?t\s+work\b", re.I), 0.35, "doesn't work"),
    (re.compile(r"\bnot\s+working\b", re.I), 0.35, "not working"),
]

CORRECTION_PATTERNS = [
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


def tier1_score_message(text: str) -> tuple[float, str | None]:
    """Simplified tier-1 scorer (regex only, no behavioral heuristics)."""
    scores: list[float] = []
    best_indicator: str | None = None
    best_indicator_score = 0.0

    for _bank_name, bank in ALL_PATTERN_BANKS:
        for pattern, weight, label in bank:
            if pattern.search(text):
                scores.append(weight)
                if weight > best_indicator_score:
                    best_indicator_score = weight
                    best_indicator = label

    if not scores:
        return 0.0, None

    scores.sort(reverse=True)
    combined = scores[0]
    for s in scores[1:]:
        combined += s * 0.3
    combined = min(combined, 1.0)

    return combined, best_indicator


# ---------------------------------------------------------------------------
# JSONL loader
# ---------------------------------------------------------------------------


def _extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def load_user_messages(path: Path) -> list[dict]:
    messages = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "user" and obj.get("message", {}).get("role") == "user":
            content = obj["message"].get("content", "")
            text = _extract_text(content).strip()
            if text:
                messages.append({"text": text, "uuid": obj.get("uuid", "")})
    return messages


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    session_dir = (
        Path.home()
        / ".claude"
        / "projects"
        / "-Users-moharb-Documents-Repos-AI-PROJECT-TEMPLATE"
    )

    # Pick 5 files: 2 large, 1 medium, 2 small
    all_files = sorted(
        session_dir.glob("*.jsonl"), key=lambda f: f.stat().st_size, reverse=True
    )
    picked = [
        all_files[0],  # largest
        all_files[2],  # 3rd largest
        all_files[len(all_files) // 2],  # median
        all_files[-5],  # near smallest
        all_files[-2],  # 2nd smallest
    ]

    print("Selected sessions:")
    for f in picked:
        size_kb = f.stat().st_size / 1024
        print(f"  {f.stem[:12]}... ({size_kb:.0f} KB)")

    # Load all user messages
    all_msgs: list[dict] = []  # each dict gets 'session_stem' added
    session_msg_counts: dict[str, int] = {}
    for f in picked:
        msgs = load_user_messages(f)
        for m in msgs:
            m["session"] = f.stem[:12]
        all_msgs.extend(msgs)
        session_msg_counts[f.stem[:12]] = len(msgs)

    print(f"\nTotal user messages across 5 sessions: {len(all_msgs)}")
    for stem, count in session_msg_counts.items():
        print(f"  {stem}...: {count} turns")

    # --- Regex scoring ---
    print("\n" + "=" * 80)
    print("REGEX TIER-1 SCORING")
    print("=" * 80)
    t0 = time.time()
    regex_results = {}
    for msg in all_msgs:
        score, indicator = tier1_score_message(msg["text"])
        regex_results[msg["uuid"]] = {"score": score, "indicator": indicator}
    regex_time = time.time() - t0
    print(f"  Time: {regex_time * 1000:.1f}ms")

    regex_flagged = {uid for uid, r in regex_results.items() if r["score"] >= 0.3}
    print(f"  Flagged (>=0.3): {len(regex_flagged)}")

    # --- GLiClass scoring ---
    print("\n" + "=" * 80)
    print("GLiClass 2B SCORING")
    print("=" * 80)

    print("  Loading model...")
    t0 = time.time()
    from gliclass import GLiClassModel, ZeroShotClassificationPipeline
    from transformers import AutoTokenizer

    model = GLiClassModel.from_pretrained("knowledgator/gliclass-modern-base-v3.0")
    tokenizer = AutoTokenizer.from_pretrained("knowledgator/gliclass-modern-base-v3.0")
    pipeline = ZeroShotClassificationPipeline(
        model=model,
        tokenizer=tokenizer,
        classification_type="multi-label",
        device="mps",
    )
    model_time = time.time() - t0
    print(f"  Model load: {model_time:.1f}s")

    labels = [
        "The user is unhappy with what the assistant did",
        "The user is satisfied or neutral",
    ]
    pos_label = labels[0]

    t0 = time.time()
    texts = [m["text"] for m in all_msgs]
    batch_size = 32
    gli_scores: dict[str, float] = {}

    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i : i + batch_size]
        batch_msgs = all_msgs[i : i + batch_size]
        results = pipeline(batch_texts, labels, threshold=0.0)
        for msg, result in zip(batch_msgs, results, strict=False):
            scores_map = {r["label"]: r["score"] for r in result}
            pos = scores_map.get(pos_label, 0.0)
            neg = scores_map.get(labels[1], 0.0)
            gli_scores[msg["uuid"]] = pos - neg  # margin

    gli_time = time.time() - t0
    print(
        f"  Inference time: {gli_time:.2f}s ({len(texts) / max(gli_time, 0.01):.1f} msgs/sec)"
    )

    # Flag if pos > neg (margin > 0)
    gli_flagged = {uid for uid, margin in gli_scores.items() if margin > 0}
    print(f"  Flagged (margin > 0): {len(gli_flagged)}")

    # --- Comparison ---
    both = regex_flagged & gli_flagged
    regex_only = regex_flagged - gli_flagged
    gli_only = gli_flagged - regex_flagged
    neither = {m["uuid"] for m in all_msgs} - regex_flagged - gli_flagged

    print("\n" + "=" * 80)
    print("HEAD-TO-HEAD COMPARISON")
    print("=" * 80)
    print(f"  Total user turns:     {len(all_msgs)}")
    print(f"  Flagged by BOTH:      {len(both)}")
    print(f"  Regex ONLY:           {len(regex_only)}")
    print(f"  GLiClass ONLY:        {len(gli_only)}")
    print(f"  Neither (clean):      {len(neither)}")
    print(f"  Regex flag rate:      {len(regex_flagged) / len(all_msgs) * 100:.1f}%")
    print(f"  GLiClass flag rate:   {len(gli_flagged) / len(all_msgs) * 100:.1f}%")
    print(
        f"  Agreement rate:       {(len(both) + len(neither)) / len(all_msgs) * 100:.1f}%"
    )

    # Build lookup
    msg_by_uuid = {m["uuid"]: m for m in all_msgs}

    def print_samples(uuids, label, max_show=15):
        print(f"\n{'=' * 80}")
        print(f"{label} ({len(uuids)} total, showing up to {max_show})")
        print("=" * 80)
        items = []
        for uid in uuids:
            msg = msg_by_uuid[uid]
            r_score = regex_results[uid]["score"]
            r_ind = regex_results[uid]["indicator"] or "-"
            g_margin = gli_scores[uid]
            items.append((r_score, g_margin, r_ind, msg))
        # Sort by combined signal strength
        items.sort(key=lambda x: -(x[0] + max(x[1], 0)))
        for r_score, g_margin, r_ind, msg in items[:max_show]:
            text = msg["text"][:130].replace("\n", " ")
            print(
                f"  regex={r_score:.2f}({r_ind:15s}) gli={g_margin:+.3f}  [{msg['session']}]"
            )
            print(f'    "{text}"')
            print()

    print_samples(both, "FLAGGED BY BOTH (high confidence corrections)")
    print_samples(regex_only, "REGEX ONLY (GLiClass says clean)")
    print_samples(gli_only, "GLiClass ONLY (regex says clean)")

    # Show a few from 'neither' for sanity check
    print(f"\n{'=' * 80}")
    print("NEITHER flagged (sample of 10 clean turns)")
    print("=" * 80)
    clean_sample = list(neither)[:10]
    for uid in clean_sample:
        msg = msg_by_uuid[uid]
        text = msg["text"][:100].replace("\n", " ")
        print(f'  "{text}"')

    # --- Timing summary ---
    print(f"\n{'=' * 80}")
    print("TIMING SUMMARY")
    print("=" * 80)
    print(f"  Regex:     {regex_time * 1000:>8.1f}ms  ({len(all_msgs)} msgs)")
    print(
        f"  GLiClass:  {gli_time * 1000:>8.1f}ms  ({len(all_msgs)} msgs) + {model_time:.1f}s model load"
    )
    print(
        f"  Speedup:   regex is {gli_time / max(regex_time, 0.0001):.0f}x faster (inference only)"
    )


if __name__ == "__main__":
    main()
