"""POC: Use GLiClass to detect user corrections in Claude Code sessions.

Best configuration found through experimentation (see FINDINGS.md):
- classification_type="single-label" (softmax, forces labels to compete)
- Minimal prompt (one sentence, no embedded examples)
- Do NOT use examples= parameter (broken on v3.0 -- <<EXAMPLE>> token missing)
- Pre-filter system/agent boilerplate before classification

This is "Config C" from the experiments -- 1.6% flag rate, 95.8% agreement
with regex, perfectly complementary (zero overlap).
"""

import json
import re
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Pre-filter: remove system/agent boilerplate (not real user speech)
# ---------------------------------------------------------------------------

NOISE_PREFIXES = [
    "[Spawned by agent",
    "[Request interrupted",
    "<task-notification>",
    "You have been idle",
    "[Message from agent",
    "[Question from agent",
    "[Redirected by",
    "This session is being continued",
    "Workflow '",
    "<system-reminder>",
]


def is_system_message(text: str) -> bool:
    """Return True if text is system/agent boilerplate, not real user speech."""
    return any(text.startswith(p) for p in NOISE_PREFIXES)


# ---------------------------------------------------------------------------
# JSONL loader
# ---------------------------------------------------------------------------


def _extract_text(content):
    """Extract text from a message content field (str or list-of-dicts)."""
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


def load_user_messages(
    session_dir: Path,
    max_files: int | None = None,
    filter_system: bool = True,
) -> list[dict]:
    """Extract user messages from JSONL session files.

    Args:
        session_dir: Path to the directory containing JSONL files.
        max_files: Limit to first N files (for quick testing).
        filter_system: If True, remove system/agent boilerplate messages.

    Returns:
        List of dicts with 'text', 'session', 'uuid' keys.
    """
    files = sorted(session_dir.glob("*.jsonl"))
    if max_files:
        files = files[:max_files]

    messages = []
    for f in files:
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    obj.get("type") == "user"
                    and obj.get("message", {}).get("role") == "user"
                ):
                    content = obj["message"].get("content", "")
                    text = _extract_text(content).strip()
                    if not text:
                        continue
                    if filter_system and is_system_message(text):
                        continue
                    messages.append(
                        {
                            "text": text,
                            "session": f.stem,
                            "uuid": obj.get("uuid", ""),
                        }
                    )
        except Exception as e:
            print(f"  Warning: failed to read {f.name}: {e}")

    return messages


# ---------------------------------------------------------------------------
# Regex tier-1 scorer (from scripts/mine_patterns.py)
# ---------------------------------------------------------------------------

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


def regex_score(text: str) -> float:
    """Score a message using regex pattern banks. Returns 0.0-1.0."""
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


# ---------------------------------------------------------------------------
# GLiClass Config C: single-label + minimal prompt
#
# Why this config:
# - single-label uses softmax (labels compete), not sigmoid (independent)
# - Minimal prompt: just enough context, no examples (broken on v3.0)
# - Do NOT use examples= parameter (<<EXAMPLE>> token not in vocabulary)
# - See FINDINGS.md for full experiment history
# ---------------------------------------------------------------------------

# Binary labels: correction vs normal
LABELS = [
    "correction or disagreement",
    "normal request or question",
]

# Minimal prompt -- more text biases the model, less is better
PROMPT = (
    "Classify whether a user is correcting/disagreeing with the assistant, "
    "or making a normal request. Most messages are normal."
)

CORR_LABEL = LABELS[0]
REGEX_THRESHOLD = 0.3


def main():
    session_dir = (
        Path.home()
        / ".claude"
        / "projects"
        / "-Users-moharb-Documents-Repos-AI-PROJECT-TEMPLATE"
    )

    if not session_dir.exists():
        print(f"Session directory not found: {session_dir}")
        return

    # --- Load messages ---
    print("=" * 70)
    print("PHASE 0: Loading session data (with system message pre-filter)")
    print("=" * 70)

    t0 = time.time()
    all_messages = load_user_messages(session_dir, filter_system=True)
    raw_count = len(load_user_messages(session_dir, filter_system=False))
    load_time = time.time() - t0

    print(f"  Total JSONL files: {len(list(session_dir.glob('*.jsonl')))}")
    print(f"  Raw user messages: {raw_count}")
    print(
        f"  After pre-filter: {len(all_messages)} ({raw_count - len(all_messages)} system msgs removed)"
    )
    print(f"  Load time: {load_time:.2f}s")

    # --- Regex tier-1 ---
    print("\n" + "=" * 70)
    print("PHASE 1: Regex tier-1 scoring")
    print("=" * 70)

    t0 = time.time()
    for m in all_messages:
        m["rx_score"] = regex_score(m["text"])
    regex_time = time.time() - t0

    rx_flagged = [m for m in all_messages if m["rx_score"] >= REGEX_THRESHOLD]
    print(f"  Time: {regex_time * 1000:.1f}ms")
    print(
        f"  Flagged (>={REGEX_THRESHOLD}): {len(rx_flagged)} ({len(rx_flagged) / max(len(all_messages), 1) * 100:.1f}%)"
    )

    # --- Load GLiClass model ---
    print("\n" + "=" * 70)
    print("PHASE 2: Loading GLiClass model (Config C: single-label + minimal prompt)")
    print("=" * 70)

    t0 = time.time()
    from gliclass import GLiClassModel, ZeroShotClassificationPipeline
    from transformers import AutoTokenizer

    model_name = "knowledgator/gliclass-modern-base-v3.0"
    print(f"  Model: {model_name}")
    print("  Config: single-label, minimal prompt, NO examples")

    model = GLiClassModel.from_pretrained(model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # CRITICAL: single-label (softmax), NOT multi-label (sigmoid)
    pipeline = ZeroShotClassificationPipeline(
        model=model,
        tokenizer=tokenizer,
        classification_type="single-label",
        device="mps",
    )

    model_time = time.time() - t0
    print(f"  Model load time: {model_time:.2f}s")

    # --- GLiClass classification ---
    print("\n" + "=" * 70)
    print("PHASE 3: GLiClass classification (all messages)")
    print("=" * 70)

    texts = [m["text"][:512] for m in all_messages]  # truncate long messages
    t0 = time.time()
    # Do NOT pass examples= (broken on v3.0)
    results = pipeline(texts, LABELS, threshold=0.5, prompt=PROMPT)
    gli_time = time.time() - t0

    for m, result in zip(all_messages, results, strict=False):
        if isinstance(result, list):
            scores = {r["label"]: r["score"] for r in result}
        else:
            scores = {result["label"]: result["score"]}
        m["gli_corr"] = scores.get(CORR_LABEL, 0.0)
        m["gli_norm"] = scores.get(LABELS[1], 0.0)
        m["gli_flag"] = m["gli_corr"] > m["gli_norm"]

    gli_flagged = [m for m in all_messages if m["gli_flag"]]
    print(
        f"  Time: {gli_time:.2f}s ({len(all_messages) / max(gli_time, 0.01):.1f} msgs/sec)"
    )
    print(
        f"  Flagged: {len(gli_flagged)} ({len(gli_flagged) / max(len(all_messages), 1) * 100:.1f}%)"
    )

    # --- Comparison ---
    print("\n" + "=" * 70)
    print("PHASE 4: Regex vs GLiClass comparison")
    print("=" * 70)

    rx_set = {m["uuid"] for m in rx_flagged}
    gli_set = {m["uuid"] for m in gli_flagged}
    both = rx_set & gli_set
    rx_only = rx_set - gli_set
    gli_only = gli_set - rx_set
    neither = {m["uuid"] for m in all_messages} - rx_set - gli_set

    print(f"  Total human messages:  {len(all_messages)}")
    print(
        f"  Regex flagged:         {len(rx_set)} ({len(rx_set) / len(all_messages) * 100:.1f}%)"
    )
    print(
        f"  GLiClass flagged:      {len(gli_set)} ({len(gli_set) / len(all_messages) * 100:.1f}%)"
    )
    print(f"  Both:                  {len(both)}")
    print(f"  Regex only:            {len(rx_only)}")
    print(f"  GLiClass only:         {len(gli_only)}")
    print(f"  Neither (clean):       {len(neither)}")
    print(
        f"  Combined flag rate:    {(len(rx_set | gli_set)) / len(all_messages) * 100:.1f}%"
    )
    print(
        f"  Agreement rate:        {(len(both) + len(neither)) / len(all_messages) * 100:.1f}%"
    )

    msg_by_uuid = {m["uuid"]: m for m in all_messages}

    # Show flagged messages
    for title, uuids in [
        ("BOTH flagged", both),
        ("REGEX ONLY", rx_only),
        ("GLiClass ONLY", gli_only),
    ]:
        print(f"\n  {title} ({len(uuids)}):")
        items = sorted(
            [msg_by_uuid[u] for u in uuids], key=lambda m: -m.get("gli_corr", 0)
        )
        for m in items[:10]:
            text = m["text"][:100].replace("\n", " ")
            print(f'    rx={m["rx_score"]:.2f} gli={m["gli_corr"]:.3f}  "{text}"')

    # --- Timing summary ---
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Model: {model_name}")
    print("  Config: single-label + minimal prompt (Config C)")
    print(f"  Model load: {model_time:.2f}s (one-time)")
    print(f"  Regex: {regex_time * 1000:.1f}ms")
    print(
        f"  GLiClass: {gli_time:.2f}s ({len(all_messages) / max(gli_time, 0.01):.1f} msgs/sec)"
    )
    print(
        f"  Total corrections found: {len(rx_set | gli_set)} ({(len(rx_set | gli_set)) / len(all_messages) * 100:.1f}%)"
    )


if __name__ == "__main__":
    main()
