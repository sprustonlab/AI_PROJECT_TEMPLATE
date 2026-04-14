"""GLiClass FIXED: single-label + prompt-embedded examples (no broken examples= param)."""

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


def load_human_messages(session_dir: Path) -> list[dict]:
    noise_prefixes = [
        "[Spawned by agent",
        "[Request interrupted",
        "<task-notification>",
        "You have been idle",
        "[Message from agent",
        "[Question from agent",
        "[Redirected by",
        "This session is being continued",
        "Workflow '",
    ]
    msgs = []
    for f in sorted(session_dir.glob("*.jsonl")):
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
                if any(text.startswith(p) for p in noise_prefixes):
                    continue
                msgs.append(
                    {"text": text, "uuid": obj.get("uuid", ""), "session": f.stem[:12]}
                )
    return msgs


# Regex scorer
BANKS = [
    [
        (re.compile(r"\bno[,.]?\s+that'?s\b", re.I), 0.45),
        (re.compile(r"\bnot what I\b", re.I), 0.50),
        (re.compile(r"\bthat'?s not\s+(right|correct|what)\b", re.I), 0.50),
        (re.compile(r"\bthat'?s\s+wrong\b", re.I), 0.55),
        (re.compile(r"\bno[,.]?\s+(I\s+)?(said|meant|asked|wanted)\b", re.I), 0.50),
        (re.compile(r"\bwrong\b", re.I), 0.30),
        (re.compile(r"\bincorrect\b", re.I), 0.35),
        (re.compile(r"\bnot\s+correct\b", re.I), 0.40),
    ],
    [
        (re.compile(r"\bgaslighting\b", re.I), 0.70),
        (re.compile(r"\byou'?re\s+not\s+listening\b", re.I), 0.65),
        (re.compile(r"\bstop\s+(doing|it|that)\b", re.I), 0.50),
        (re.compile(r"\bI\s+already\s+(said|told|explained)\b", re.I), 0.55),
        (re.compile(r"\bhow\s+many\s+times\b", re.I), 0.55),
        (re.compile(r"\bplease\s+(just\s+)?read\b", re.I), 0.35),
        (re.compile(r"\bpay\s+attention\b", re.I), 0.55),
        (re.compile(r"\byou\s+keep\b", re.I), 0.40),
        (re.compile(r"\bfrustrat", re.I), 0.45),
    ],
    [
        (re.compile(r"\bbug\b", re.I), 0.25),
        (re.compile(r"\bbroken\b", re.I), 0.30),
        (re.compile(r"\berror\b", re.I), 0.20),
        (re.compile(r"\bcrash(es|ed|ing)?\b", re.I), 0.25),
        (re.compile(r"\bfail(s|ed|ing|ure)?\b", re.I), 0.20),
        (re.compile(r"\bdoesn'?t\s+work\b", re.I), 0.35),
        (re.compile(r"\bnot\s+working\b", re.I), 0.35),
    ],
    [
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
        (
            re.compile(r"\byou\s+(missed|forgot|skipped|ignored|overlooked)\b", re.I),
            0.50,
        ),
        (
            re.compile(
                r"\bdo(n'?t|es\s*n'?t)\s+(modify|change|touch|edit|alter)\b", re.I
            ),
            0.40,
        ),
        (re.compile(r"\bI\s+told\s+you\b", re.I), 0.50),
        (re.compile(r"\blike\s+I\s+said\b", re.I), 0.45),
    ],
]


def regex_score(text):
    scores = []
    for bank in BANKS:
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


# -----------------------------------------------------------------------
# Prompt with embedded examples (since examples= param is broken on v3.0)
# -----------------------------------------------------------------------

PROMPT_WITH_EXAMPLES = (
    "Classify user messages in a coding assistant conversation. "
    "A 'correction' is when the user tells the assistant it did something wrong, "
    "went the wrong direction, or needs to change its approach. "
    "A 'normal' message is a request, question, approval, or follow-up. "
    "Most messages are normal. "
    "Examples of corrections: "
    "'No, integration and long tests as well' "
    "'that is not what I asked for' "
    "'Do what I say, manual trigger long test please as PR to main!' "
    "'submodules/claudechic/ = read-only. is not true the main point is to change it' "
    "'no you sent it to the chat, use the MCP tell agent' "
    "'the tests should have advance check in them not the componants' "
    "Examples of normal messages: "
    "'can you help with this?' "
    "'what is the status?' "
    "'commit all please' "
    "'yes' "
    "'approve' "
    "'did it close the issue?' "
    "'can you try again wait for me to move to a different agent' "
)

PROMPT_MINIMAL = (
    "Classify whether a user is correcting/disagreeing with the assistant, "
    "or making a normal request. Most messages are normal."
)

LABELS = [
    "correction or disagreement",
    "normal request or question",
]


def run_config(name, pipeline, texts, labels, prompt=None):
    """Run a config and return list of (winning_label, score) tuples."""
    t0 = time.time()
    results = pipeline(texts, labels, threshold=0.5, prompt=prompt)
    elapsed = time.time() - t0

    predictions = []
    for result in results:
        if isinstance(result, list):
            # single-label returns list with one dict
            if result:
                predictions.append((result[0]["label"], result[0]["score"]))
            else:
                predictions.append((labels[1], 0.5))  # default to normal
        elif isinstance(result, dict):
            predictions.append((result["label"], result["score"]))
        else:
            predictions.append((labels[1], 0.5))

    return predictions, elapsed


def main():
    session_dir = (
        Path.home()
        / ".claude"
        / "projects"
        / "-Users-moharb-Documents-Repos-AI-PROJECT-TEMPLATE"
    )

    # Load model
    print("Loading model...")
    t0 = time.time()
    from gliclass import GLiClassModel, ZeroShotClassificationPipeline
    from transformers import AutoTokenizer

    model = GLiClassModel.from_pretrained("knowledgator/gliclass-modern-base-v3.0")
    tokenizer = AutoTokenizer.from_pretrained("knowledgator/gliclass-modern-base-v3.0")

    # KEY FIX: single-label mode (softmax, not sigmoid)
    pipeline_single = ZeroShotClassificationPipeline(
        model=model,
        tokenizer=tokenizer,
        classification_type="single-label",
        device="mps",
    )
    # Also test multi-label for comparison
    pipeline_multi = ZeroShotClassificationPipeline(
        model=model,
        tokenizer=tokenizer,
        classification_type="multi-label",
        device="mps",
    )
    print(f"Model loaded in {time.time() - t0:.1f}s")

    corr_label = LABELS[0]
    norm_label = LABELS[1]

    # ===================================================================
    # TEST 1: Synthetic 10 messages
    # ===================================================================
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

    configs = [
        ("A: multi-label, no prompt (old baseline)", pipeline_multi, None),
        ("B: SINGLE-label, no prompt", pipeline_single, None),
        ("C: SINGLE-label + minimal prompt", pipeline_single, PROMPT_MINIMAL),
        (
            "D: SINGLE-label + prompt with examples",
            pipeline_single,
            PROMPT_WITH_EXAMPLES,
        ),
        ("E: multi-label + prompt with examples", pipeline_multi, PROMPT_WITH_EXAMPLES),
    ]

    for name, pipe, prompt in configs:
        print(f"\n{'=' * 80}")
        print(f"CONFIG: {name}")
        print(f"{'=' * 80}")

        preds, elapsed = run_config(name, pipe, synth_texts, LABELS, prompt=prompt)

        correct = 0
        for (truth, text), (pred_label, pred_score) in zip(synth, preds, strict=False):
            predicted = "C" if pred_label == corr_label else "N"
            hit = "OK" if predicted == truth else "XX"
            if predicted == truth:
                correct += 1
            print(
                f"  [{truth}>{predicted} {hit}] {pred_score:.3f} {pred_label[:20]:20}  {text[:60]}"
            )

        print(f"  ACCURACY: {correct}/10 ({correct * 10}%)  Time: {elapsed:.2f}s")

    # ===================================================================
    # TEST 2: Full corpus with best config
    # ===================================================================
    human_msgs = load_human_messages(session_dir)
    print(f"\n\n{'=' * 80}")
    print(f"FULL CORPUS: Best config on {len(human_msgs)} real human messages")
    print(f"{'=' * 80}")

    # Try the two most promising configs on full data
    for config_name, pipe, prompt in [
        ("SINGLE-label + prompt with examples", pipeline_single, PROMPT_WITH_EXAMPLES),
        ("SINGLE-label + minimal prompt", pipeline_single, PROMPT_MINIMAL),
    ]:
        print(f"\n--- {config_name} ---")

        texts = [m["text"][:512] for m in human_msgs]
        t0 = time.time()
        preds, elapsed = run_config(config_name, pipe, texts, LABELS, prompt=prompt)
        print(
            f"  Time: {elapsed:.2f}s ({len(texts) / max(elapsed, 0.01):.1f} msgs/sec)"
        )

        # Compare with regex
        for m, (pred_label, pred_score) in zip(human_msgs, preds, strict=False):
            m["rx"] = regex_score(m["text"])
            m["gli_pred"] = "C" if pred_label == corr_label else "N"
            m["gli_score"] = pred_score
            m["gli_label"] = pred_label

        rx_set = {m["uuid"] for m in human_msgs if m["rx"] >= 0.3}
        gli_set = {m["uuid"] for m in human_msgs if m["gli_pred"] == "C"}
        both = rx_set & gli_set
        rx_only = rx_set - gli_set
        gli_only = gli_set - rx_set
        neither = {m["uuid"] for m in human_msgs} - rx_set - gli_set

        print(
            f"  Regex flagged:   {len(rx_set)} ({len(rx_set) / len(human_msgs) * 100:.1f}%)"
        )
        print(
            f"  GLi flagged:     {len(gli_set)} ({len(gli_set) / len(human_msgs) * 100:.1f}%)"
        )
        print(f"  Both:            {len(both)}")
        print(f"  Regex only:      {len(rx_only)}")
        print(f"  GLi only:        {len(gli_only)}")
        print(f"  Neither:         {len(neither)}")
        print(
            f"  Agreement:       {(len(both) + len(neither)) / len(human_msgs) * 100:.1f}%"
        )

        msg_by_uuid = {m["uuid"]: m for m in human_msgs}

        def show(uuids, title, max_n=12):
            print(f"\n  {title} ({len(uuids)}):")
            items = sorted(
                [msg_by_uuid[u] for u in uuids], key=lambda m: -m["gli_score"]
            )
            for m in items[:max_n]:
                text = m["text"][:100].replace("\n", " ")
                print(
                    f'    rx={m["rx"]:.2f} gli={m["gli_score"]:.3f} [{m["gli_pred"]}]  "{text}"'
                )

        show(both, "BOTH flagged")
        show(rx_only, "REGEX ONLY")
        show(gli_only, "GLiClass ONLY")

        # Sample of clean messages
        print("\n  NEITHER flagged (sample 8):")
        clean = list(neither)[:8]
        for uid in clean:
            m = msg_by_uuid[uid]
            text = m["text"][:80].replace("\n", " ")
            print(
                f'    rx={m["rx"]:.2f} gli={m["gli_score"]:.3f} [{m["gli_pred"]}]  "{text}"'
            )


if __name__ == "__main__":
    main()
