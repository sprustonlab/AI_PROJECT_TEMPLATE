"""Test GLiClass with category labels matching regex pattern banks directly."""

import json
import re
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Same 5 session files, same loader
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


# Pre-filter system boilerplate
SYSTEM_PREFIXES = [
    "[Spawned by agent",
    "[Request interrupted",
    "[Redirected by agent",
    "[Message from agent",
    "[Question from agent",
    "<task-notification>",
    "You have been idle",
    "This session is being continued",
]


def is_system_message(text: str) -> bool:
    for prefix in SYSTEM_PREFIXES:
        if text.startswith(prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# Regex tier-1 (from mine_patterns.py)
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


def tier1_score_message(text):
    scores = []
    best_indicator = None
    best_indicator_score = 0.0
    matched_banks = set()
    for bank_name, bank in ALL_PATTERN_BANKS:
        for pattern, weight, label in bank:
            if pattern.search(text):
                scores.append(weight)
                matched_banks.add(bank_name)
                if weight > best_indicator_score:
                    best_indicator_score = weight
                    best_indicator = label
    if not scores:
        return 0.0, None, matched_banks
    scores.sort(reverse=True)
    combined = scores[0]
    for s in scores[1:]:
        combined += s * 0.3
    combined = min(combined, 1.0)
    return combined, best_indicator, matched_banks


def main():
    session_dir = (
        Path.home()
        / ".claude"
        / "projects"
        / "-Users-moharb-Documents-Repos-AI-PROJECT-TEMPLATE"
    )
    all_files = sorted(
        session_dir.glob("*.jsonl"), key=lambda f: f.stat().st_size, reverse=True
    )
    picked = [
        all_files[0],
        all_files[2],
        all_files[len(all_files) // 2],
        all_files[-5],
        all_files[-2],
    ]

    all_msgs = []
    for f in picked:
        msgs = load_user_messages(f)
        for m in msgs:
            m["session"] = f.stem[:12]
        all_msgs.extend(msgs)

    # Pre-filter system messages
    human_msgs = [m for m in all_msgs if not is_system_message(m["text"])]
    system_count = len(all_msgs) - len(human_msgs)
    print(
        f"Total messages: {len(all_msgs)}, System filtered: {system_count}, Human: {len(human_msgs)}"
    )

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

    # ======================================================================
    # APPROACH A: Regex bank names as GLiClass labels
    # ======================================================================
    print("\n" + "=" * 80)
    print("APPROACH A: Regex-bank-aligned categories (4 labels)")
    print("=" * 80)

    labels_a = [
        "The user is negating or disagreeing with what the assistant said",
        "The user is frustrated or losing patience with the assistant",
        "The user is reporting a bug, error, or broken behavior",
        "The user is correcting, redirecting, or asking the assistant to undo something",
    ]
    label_short_a = ["negation", "frustration", "error", "correction"]

    t0 = time.time()
    results_a = pipeline([m["text"] for m in human_msgs], labels_a, threshold=0.0)
    time_a = time.time() - t0
    print(f"  Time: {time_a:.2f}s ({len(human_msgs) / max(time_a, 0.01):.1f} msgs/sec)")

    # Compare each message
    print(
        f"\n  {'Msg#':>4} {'Regex':>5} {'RxBanks':15} {'GLi-top':>7} {'GLi-label':20} Text"
    )
    print(f"  {'----':>4} {'-----':>5} {'-' * 15} {'-------':>7} {'-' * 20} {'-' * 50}")

    for i, (msg, gli_result) in enumerate(zip(human_msgs, results_a, strict=False)):
        rx_score, rx_ind, rx_banks = tier1_score_message(msg["text"])
        rx_banks_str = "+".join(sorted(rx_banks)) if rx_banks else "-"

        gli_sorted = sorted(gli_result, key=lambda r: -r["score"])
        gli_top_score = gli_sorted[0]["score"] if gli_sorted else 0.0
        gli_top_idx = labels_a.index(gli_sorted[0]["label"]) if gli_sorted else -1
        gli_top_name = label_short_a[gli_top_idx] if gli_top_idx >= 0 else "-"

        text_preview = msg["text"][:60].replace("\n", " ")
        rx_flag = "*" if rx_score >= 0.3 else " "
        gli_flag = "*" if gli_top_score >= 0.5 else " "

        print(
            f"  {i + 1:>3}{rx_flag} {rx_score:5.2f} {rx_banks_str:15} {gli_top_score:6.3f}{gli_flag} {gli_top_name:20} {text_preview}"
        )

        # Show all GLiClass scores for flagged messages
        if rx_score >= 0.3 or gli_top_score >= 0.5:
            for r in gli_sorted:
                idx = labels_a.index(r["label"])
                print(f"       {'':15} {r['score']:6.3f}  {label_short_a[idx]}")

    # ======================================================================
    # APPROACH B: More specific labels (closer to individual regex patterns)
    # ======================================================================
    print("\n" + "=" * 80)
    print("APPROACH B: Fine-grained categories (8 labels)")
    print("=" * 80)

    labels_b = [
        "The user says the assistant is wrong or incorrect",
        "The user wants to revert, undo, or rollback a change",
        "The user is repeating an instruction they already gave",
        "The user is frustrated or losing patience",
        "The user reports something is broken, failing, or has a bug",
        "The user wants a different approach than what the assistant chose",
        "The user is asking the assistant not to modify or touch something",
        "The user is giving a normal instruction or asking a question",
    ]
    label_short_b = [
        "wrong",
        "revert",
        "repeat",
        "frustrated",
        "broken",
        "diff-approach",
        "dont-touch",
        "normal",
    ]

    t0 = time.time()
    results_b = pipeline([m["text"] for m in human_msgs], labels_b, threshold=0.0)
    time_b = time.time() - t0
    print(f"  Time: {time_b:.2f}s ({len(human_msgs) / max(time_b, 0.01):.1f} msgs/sec)")

    print(f"\n  {'Msg#':>4} {'Regex':>5} Text (60 chars)")
    print(f"  {'----':>4} {'-----':>5} {'-' * 60}")

    for i, (msg, gli_result) in enumerate(zip(human_msgs, results_b, strict=False)):
        rx_score, rx_ind, rx_banks = tier1_score_message(msg["text"])
        text_preview = msg["text"][:60].replace("\n", " ")
        rx_flag = "*" if rx_score >= 0.3 else " "

        gli_sorted = sorted(gli_result, key=lambda r: -r["score"])
        # Is "normal" the top label?
        top_is_normal = gli_sorted[0]["label"] == labels_b[-1] if gli_sorted else True
        # Highest non-normal score
        non_normal = [r for r in gli_sorted if r["label"] != labels_b[-1]]
        top_nn_score = non_normal[0]["score"] if non_normal else 0.0
        top_nn_idx = labels_b.index(non_normal[0]["label"]) if non_normal else -1
        top_nn_name = label_short_b[top_nn_idx] if top_nn_idx >= 0 else "-"
        normal_score = next(
            (r["score"] for r in gli_sorted if r["label"] == labels_b[-1]), 0.0
        )

        gli_flag = "*" if not top_is_normal and top_nn_score >= 0.5 else " "

        print(f"  {i + 1:>3}{rx_flag} {rx_score:5.2f}  {text_preview}")
        # Always show top 3 GLiClass scores
        for r in gli_sorted[:4]:
            idx = labels_b.index(r["label"])
            marker = "<<<" if r["label"] != labels_b[-1] and r["score"] >= 0.5 else ""
            print(f"       {r['score']:6.3f}  {label_short_b[idx]:15} {marker}")
        print()

    # ======================================================================
    # APPROACH C: Same labels but on the 10 synthetic test messages
    # ======================================================================
    print("\n" + "=" * 80)
    print("APPROACH C: Fine-grained (8 labels) on 10 synthetic test messages")
    print("=" * 80)

    synth = [
        ("C", "No, that's wrong. I said to use pathlib, not os.path."),
        ("N", "Can you help me write a test for this function?"),
        (
            "C",
            "That's not what I asked for. I wanted a binary classifier, not multi-class.",
        ),
        ("C", "Stop. You're going down the wrong path. Let me clarify what I need."),
        ("N", "Great, now let's add error handling."),
        ("C", "I'm frustrated - you keep ignoring my instructions about encoding."),
        ("N", "Please make the output more concise, less verbose."),
        ("C", "Actually, use pytest instead of unittest."),
        ("N", "What does this error mean?"),
        (
            "C",
            "I already told you three times, do NOT modify pixi.toml in the main project.",
        ),
    ]

    synth_texts = [s[1] for s in synth]
    synth_truth = [s[0] for s in synth]

    results_c = pipeline(synth_texts, labels_b, threshold=0.0)

    correct = 0
    for (truth, text), gli_result in zip(synth, results_c, strict=False):
        gli_sorted = sorted(gli_result, key=lambda r: -r["score"])
        top_is_normal = gli_sorted[0]["label"] == labels_b[-1]
        predicted = "N" if top_is_normal else "C"

        # Also try: correction if any non-normal label > 0.5
        non_normal = [r for r in gli_sorted if r["label"] != labels_b[-1]]
        top_nn = non_normal[0] if non_normal else None
        pred_threshold = "C" if top_nn and top_nn["score"] >= 0.5 else "N"

        hit_top1 = "OK" if predicted == truth else "XX"
        hit_thresh = "OK" if pred_threshold == truth else "XX"
        if pred_threshold == truth:
            correct += 1

        print(f"\n  [{truth}] {text[:70]}")
        print(
            f"    Top-1 pred: {predicted} ({hit_top1})  |  Threshold pred: {pred_threshold} ({hit_thresh})"
        )
        for r in gli_sorted[:4]:
            idx = labels_b.index(r["label"])
            print(f"      {r['score']:.3f}  {label_short_b[idx]}")

    print(f"\n  THRESHOLD ACCURACY: {correct}/10 ({correct * 10}%)")


if __name__ == "__main__":
    main()
