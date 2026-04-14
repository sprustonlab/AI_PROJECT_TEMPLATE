"""Categories-direct v2: looser pre-filter + stronger normal anchor + all 76 sessions."""

import json
import re
import time
from pathlib import Path


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
                messages.append(
                    {
                        "text": text,
                        "uuid": obj.get("uuid", ""),
                        "session": path.stem[:12],
                    }
                )
    return messages


# Filter only obvious non-human noise
NOISE_PREFIXES = [
    "<task-notification>",
    "You have been idle",
    "[Request interrupted",
]


def is_noise(text: str) -> bool:
    for prefix in NOISE_PREFIXES:
        if text.startswith(prefix):
            return True
    return False


# Regex tier-1
NEGATION_PATTERNS = [
    (re.compile(r"\bno[,.]?\s+that'?s\b", re.I), 0.45),
    (re.compile(r"\bnot what I\b", re.I), 0.50),
    (re.compile(r"\bthat'?s not\s+(right|correct|what)\b", re.I), 0.50),
    (re.compile(r"\bthat'?s\s+wrong\b", re.I), 0.55),
    (re.compile(r"\bno[,.]?\s+(I\s+)?(said|meant|asked|wanted)\b", re.I), 0.50),
    (re.compile(r"\bwrong\b", re.I), 0.30),
    (re.compile(r"\bincorrect\b", re.I), 0.35),
    (re.compile(r"\bnot\s+correct\b", re.I), 0.40),
]
FRUSTRATION_PATTERNS = [
    (re.compile(r"\bgaslighting\b", re.I), 0.70),
    (re.compile(r"\byou'?re\s+not\s+listening\b", re.I), 0.65),
    (re.compile(r"\bstop\s+(doing|it|that)\b", re.I), 0.50),
    (re.compile(r"\bI\s+already\s+(said|told|explained)\b", re.I), 0.55),
    (re.compile(r"\bhow\s+many\s+times\b", re.I), 0.55),
    (re.compile(r"\bplease\s+(just\s+)?read\b", re.I), 0.35),
    (re.compile(r"\bpay\s+attention\b", re.I), 0.55),
    (re.compile(r"\byou\s+keep\b", re.I), 0.40),
    (re.compile(r"\bfrustrat", re.I), 0.45),
]
ERROR_PATTERNS = [
    (re.compile(r"\bbug\b", re.I), 0.25),
    (re.compile(r"\bbroken\b", re.I), 0.30),
    (re.compile(r"\berror\b", re.I), 0.20),
    (re.compile(r"\bcrash(es|ed|ing)?\b", re.I), 0.25),
    (re.compile(r"\bfail(s|ed|ing|ure)?\b", re.I), 0.20),
    (re.compile(r"\bdoesn'?t\s+work\b", re.I), 0.35),
    (re.compile(r"\bnot\s+working\b", re.I), 0.35),
]
CORRECTION_PATTERNS = [
    (re.compile(r"\bI\s+said\b", re.I), 0.40),
    (re.compile(r"\bdon'?t\s+do\b", re.I), 0.40),
    (re.compile(r"\brevert\b", re.I), 0.45),
    (re.compile(r"\bundo\b", re.I), 0.35),
    (re.compile(r"\broll\s*back\b", re.I), 0.40),
    (re.compile(r"\binstead\b", re.I), 0.20),
    (re.compile(r"\bactually\b", re.I), 0.20),
    (re.compile(r"\bI\s+(meant|wanted|asked\s+for)\b", re.I), 0.40),
    (re.compile(r"\bnot\s+what\s+I\b", re.I), 0.50),
    (re.compile(r"\bshould\s+(be|have)\b", re.I), 0.20),
    (re.compile(r"\byou\s+(missed|forgot|skipped|ignored|overlooked)\b", re.I), 0.50),
    (
        re.compile(r"\bdo(n'?t|es\s*n'?t)\s+(modify|change|touch|edit|alter)\b", re.I),
        0.40,
    ),
    (re.compile(r"\bI\s+told\s+you\b", re.I), 0.50),
    (re.compile(r"\blike\s+I\s+said\b", re.I), 0.45),
]
ALL_BANKS = [
    NEGATION_PATTERNS,
    FRUSTRATION_PATTERNS,
    ERROR_PATTERNS,
    CORRECTION_PATTERNS,
]


def regex_score(text):
    scores = []
    for bank in ALL_BANKS:
        for pattern, weight in bank:
            if pattern.search(text):
                scores.append(weight)
    if not scores:
        return 0.0
    scores.sort(reverse=True)
    combined = scores[0]
    for s in scores[1:]:
        combined += s * 0.3
    return min(combined, 1.0)


def main():
    session_dir = (
        Path.home()
        / ".claude"
        / "projects"
        / "-Users-moharb-Documents-Repos-AI-PROJECT-TEMPLATE"
    )

    # Load ALL sessions
    all_msgs = []
    for f in sorted(session_dir.glob("*.jsonl")):
        all_msgs.extend(load_user_messages(f))

    # Filter noise
    human_msgs = [m for m in all_msgs if not is_noise(m["text"])]
    print(f"Total msgs: {len(all_msgs)}, After noise filter: {len(human_msgs)}")

    # Regex score all
    for m in human_msgs:
        m["rx_score"] = regex_score(m["text"])

    rx_flagged = [m for m in human_msgs if m["rx_score"] >= 0.3]
    print(f"Regex flagged (>=0.3): {len(rx_flagged)}")

    # Load model
    print("\nLoading model...")
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
    print(f"Model loaded in {time.time() - t0:.1f}s")

    # 8 fine-grained labels
    labels = [
        "The user says the assistant is wrong or made a mistake",
        "The user wants to revert, undo, or rollback a change",
        "The user is repeating an instruction they already gave",
        "The user is frustrated or losing patience",
        "The user reports something is broken, failing, or has a bug",
        "The user wants a different approach than what the assistant chose",
        "The user is asking the assistant not to modify or touch something",
        "The user is giving a normal instruction, asking a question, or providing information",
    ]
    label_short = [
        "wrong",
        "revert",
        "repeat",
        "frustrated",
        "broken",
        "diff-approach",
        "dont-touch",
        "NORMAL",
    ]
    normal_label = labels[-1]

    # Run GLiClass on ALL human messages
    print(f"\nRunning GLiClass on {len(human_msgs)} messages...")
    t0 = time.time()
    texts = [m["text"][:512] for m in human_msgs]  # truncate long messages
    batch_size = 32
    all_results = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        all_results.extend(pipeline(batch, labels, threshold=0.0))
    gli_time = time.time() - t0
    print(
        f"GLiClass time: {gli_time:.2f}s ({len(human_msgs) / max(gli_time, 0.01):.1f} msgs/sec)"
    )

    # Analyze
    for m, result in zip(human_msgs, all_results, strict=False):
        sorted_r = sorted(result, key=lambda r: -r["score"])
        top = sorted_r[0]
        m["gli_top_label"] = label_short[labels.index(top["label"])]
        m["gli_top_score"] = top["score"]
        m["gli_is_normal"] = top["label"] == normal_label
        # Best non-normal
        non_normal = [r for r in sorted_r if r["label"] != normal_label]
        if non_normal:
            m["gli_best_cat"] = label_short[labels.index(non_normal[0]["label"])]
            m["gli_best_cat_score"] = non_normal[0]["score"]
        else:
            m["gli_best_cat"] = "-"
            m["gli_best_cat_score"] = 0.0
        m["gli_normal_score"] = next(
            (r["score"] for r in sorted_r if r["label"] == normal_label), 0.0
        )

    # GLiClass flagged = top label is NOT normal
    gli_flagged = [m for m in human_msgs if not m["gli_is_normal"]]
    # GLiClass flagged strict = best non-normal score > 0.7
    gli_flagged_strict = [m for m in human_msgs if m["gli_best_cat_score"] >= 0.7]

    print(f"\n{'=' * 80}")
    print("RESULTS SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Human messages:           {len(human_msgs)}")
    print(
        f"  Regex flagged (>=0.3):    {len(rx_flagged)} ({len(rx_flagged) / len(human_msgs) * 100:.1f}%)"
    )
    print(
        f"  GLi top!=normal:          {len(gli_flagged)} ({len(gli_flagged) / len(human_msgs) * 100:.1f}%)"
    )
    print(
        f"  GLi best-cat>=0.7:        {len(gli_flagged_strict)} ({len(gli_flagged_strict) / len(human_msgs) * 100:.1f}%)"
    )

    # How often does "normal" win as top-1?
    normal_wins = sum(1 for m in human_msgs if m["gli_is_normal"])
    print(
        f"  GLi 'normal' is top-1:    {normal_wins}/{len(human_msgs)} ({normal_wins / len(human_msgs) * 100:.1f}%)"
    )

    # Category distribution for GLi flagged
    print("\n  GLiClass category distribution (top-1, excluding normal):")
    cat_counts = {}
    for m in gli_flagged:
        cat_counts[m["gli_top_label"]] = cat_counts.get(m["gli_top_label"], 0) + 1
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"    {cat:20}: {count}")

    # Venn diagram
    rx_set = {m["uuid"] for m in rx_flagged}
    gli_set = {m["uuid"] for m in gli_flagged_strict}
    both = rx_set & gli_set
    rx_only = rx_set - gli_set
    gli_only = gli_set - rx_set

    print("\n  Venn (regex>=0.3 vs GLi-cat>=0.7):")
    print(f"    Both:          {len(both)}")
    print(f"    Regex only:    {len(rx_only)}")
    print(f"    GLi only:      {len(gli_only)}")

    msg_by_uuid = {m["uuid"]: m for m in human_msgs}

    def show(uuids, title, max_n=10):
        print(
            f"\n  --- {title} ({len(uuids)} total, showing {min(len(uuids), max_n)}) ---"
        )
        items = sorted(
            [msg_by_uuid[u] for u in uuids],
            key=lambda m: -m.get("gli_best_cat_score", 0),
        )
        for m in items[:max_n]:
            text = m["text"][:120].replace("\n", " ")
            print(
                f"    rx={m['rx_score']:.2f} gli={m['gli_best_cat']}/{m['gli_best_cat_score']:.2f} norm={m['gli_normal_score']:.2f}"
            )
            print(f'      "{text}"')

    show(both, "BOTH flagged")
    show(rx_only, "REGEX ONLY")
    show(gli_only, "GLiClass ONLY")

    # Show normal-score distribution for regex-flagged items
    print("\n  --- Regex-flagged items: GLiClass normal-score distribution ---")
    for m in sorted(rx_flagged, key=lambda m: -m["rx_score"])[:15]:
        text = m["text"][:90].replace("\n", " ")
        print(
            f"    rx={m['rx_score']:.2f} top={m['gli_top_label']:15} cat={m['gli_best_cat']:15}/{m['gli_best_cat_score']:.2f} norm={m['gli_normal_score']:.2f}"
        )
        print(f'      "{text}"')


if __name__ == "__main__":
    main()
