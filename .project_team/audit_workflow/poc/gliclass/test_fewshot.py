"""GLiClass few-shot experiment: real examples + prompt to improve precision."""

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
    """Load all user messages, filtering system boilerplate."""
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


# Regex scorer (simplified)
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
# Few-shot examples from REAL sessions
# -----------------------------------------------------------------------

NORMAL_EXAMPLES = [
    "can you get me setup up in this repo to run claudechic",
    "are you here",
    "can you help with this? github.com/sprustonlab/AI_PROJECT_TEMPLATE/issues/21",
    "approve",
    "what is the status?",
    "show me the plan",
    "commit all please",
    "yes",
    "did it close the issue?",
    "what are they?",
    "it worked, I saw the toast the orange and the better msg",
    "yes all pass, please remove the file you created",
    "all pass can you merge?",
    "can you try again wait for me to move to a different agent",
]

CORRECTION_EXAMPLES = [
    "the tests should have advance check in them not the componants, I want a test for what I am seeing",
    "I didn't switch to an agent with a orange dot, that is not implemented yet",
    "Do what I say, manual trigger long test please as PR to main!",
    "please edit the claude md to make that explicit, use the right language, not what it is, what you should DO",
    "no, please look at the git history of this repo",
    "submodules/claudechic/ = read-only. is not true the main point is to change it",
    "No, integration and long tests as well",
    "that is not what I asked for",
    "why are you in CI and not local tests?",
    "No ignore the rest of the E501, can we remove it?",
    "no you sent it to the chat, use the MCP tell agent",
    "I was in plan mode by mistake, please try again",
]

FEWSHOT_EXAMPLES = [
    {
        "text": t,
        "labels": ["The user is making a normal request, question, or follow-up"],
    }
    for t in NORMAL_EXAMPLES
] + [
    {
        "text": t,
        "labels": [
            "The user is correcting, disagreeing with, or redirecting the assistant"
        ],
    }
    for t in CORRECTION_EXAMPLES
]

LABELS = [
    "The user is correcting, disagreeing with, or redirecting the assistant",
    "The user is making a normal request, question, or follow-up",
]

PROMPT = (
    "Classify whether a user message in a coding assistant conversation is a "
    "correction/disagreement/redirect OR a normal request/question/follow-up. "
    "Most messages are normal. Only flag messages where the user is telling the "
    "assistant it did something wrong, made a mistake, went in the wrong direction, "
    "or needs to change what it is doing. Simple questions, approvals, and new "
    "task requests are NORMAL even if they mention errors or bugs."
)


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
    pipeline = ZeroShotClassificationPipeline(
        model=model,
        tokenizer=tokenizer,
        classification_type="multi-label",
        device="mps",
    )
    print(f"Model loaded in {time.time() - t0:.1f}s")

    # ===================================================================
    # TEST 1: Synthetic 10 messages — baseline vs few-shot vs few-shot+prompt
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

    correction_label = LABELS[0]
    normal_label = LABELS[1]

    configs = [
        ("BASELINE (no examples, no prompt)", {}, {}),
        ("FEW-SHOT only (26 examples)", {"examples": FEWSHOT_EXAMPLES}, {}),
        ("PROMPT only", {"prompt": PROMPT}, {}),
        ("FEW-SHOT + PROMPT", {"examples": FEWSHOT_EXAMPLES, "prompt": PROMPT}, {}),
    ]

    for name, kwargs, _ in configs:
        print(f"\n{'=' * 80}")
        print(f"SYNTHETIC TEST: {name}")
        print(f"{'=' * 80}")

        t0 = time.time()
        results = pipeline(synth_texts, LABELS, threshold=0.0, **kwargs)
        elapsed = time.time() - t0

        correct = 0
        for (truth, text), result in zip(synth, results, strict=False):
            scores = {r["label"]: r["score"] for r in result}
            corr_score = scores.get(correction_label, 0.0)
            norm_score = scores.get(normal_label, 0.0)
            predicted = "C" if corr_score > norm_score else "N"
            hit = "OK" if predicted == truth else "XX"
            if predicted == truth:
                correct += 1
            print(
                f"  [{truth}>{predicted} {hit}] corr={corr_score:.3f} norm={norm_score:.3f}  {text[:65]}"
            )

        print(f"  ACCURACY: {correct}/10 ({correct * 10}%)  Time: {elapsed:.2f}s")

    # ===================================================================
    # TEST 2: ALL real human messages — best config vs regex
    # ===================================================================
    human_msgs = load_human_messages(session_dir)
    print(f"\n\n{'=' * 80}")
    print(f"FULL CORPUS: Few-shot + Prompt on {len(human_msgs)} real human messages")
    print(f"{'=' * 80}")

    # Regex score
    for m in human_msgs:
        m["rx"] = regex_score(m["text"])

    # GLiClass with best config
    t0 = time.time()
    texts = [m["text"][:512] for m in human_msgs]
    gli_results = pipeline(
        texts, LABELS, threshold=0.0, examples=FEWSHOT_EXAMPLES, prompt=PROMPT
    )
    gli_time = time.time() - t0
    print(
        f"  GLiClass time: {gli_time:.2f}s ({len(human_msgs) / max(gli_time, 0.01):.1f} msgs/sec)"
    )

    for m, result in zip(human_msgs, gli_results, strict=False):
        scores = {r["label"]: r["score"] for r in result}
        m["gli_corr"] = scores.get(correction_label, 0.0)
        m["gli_norm"] = scores.get(normal_label, 0.0)
        m["gli_margin"] = m["gli_corr"] - m["gli_norm"]
        m["gli_flag"] = m["gli_corr"] > m["gli_norm"]

    rx_flagged = {m["uuid"] for m in human_msgs if m["rx"] >= 0.3}
    gli_flagged = {m["uuid"] for m in human_msgs if m["gli_flag"]}

    both = rx_flagged & gli_flagged
    rx_only = rx_flagged - gli_flagged
    gli_only = gli_flagged - rx_flagged
    neither = {m["uuid"] for m in human_msgs} - rx_flagged - gli_flagged

    print(f"\n  Total human messages:  {len(human_msgs)}")
    print(
        f"  Regex flagged:         {len(rx_flagged)} ({len(rx_flagged) / len(human_msgs) * 100:.1f}%)"
    )
    print(
        f"  GLi flagged:           {len(gli_flagged)} ({len(gli_flagged) / len(human_msgs) * 100:.1f}%)"
    )
    print(f"  Both:                  {len(both)}")
    print(f"  Regex only:            {len(rx_only)}")
    print(f"  GLi only:              {len(gli_only)}")
    print(f"  Neither:               {len(neither)}")
    print(
        f"  Agreement:             {(len(both) + len(neither)) / len(human_msgs) * 100:.1f}%"
    )

    msg_by_uuid = {m["uuid"]: m for m in human_msgs}

    def show(uuids, title, max_n=15):
        print(f"\n  --- {title} ({len(uuids)}) ---")
        items = sorted(
            [msg_by_uuid[u] for u in uuids], key=lambda m: -abs(m["gli_margin"])
        )
        for m in items[:max_n]:
            text = m["text"][:100].replace("\n", " ")
            print(
                f"    rx={m['rx']:.2f} gli_c={m['gli_corr']:.2f} gli_n={m['gli_norm']:.2f} margin={m['gli_margin']:+.2f}"
            )
            print(f'      "{text}"')

    show(both, "BOTH flagged")
    show(rx_only, "REGEX ONLY (GLi says normal)")
    show(gli_only, "GLiClass ONLY (regex says clean)")

    # Also show messages from the few-shot training set to check overfitting
    print("\n  --- FEW-SHOT TRAINING EXAMPLES (sanity check) ---")
    for m in human_msgs:
        if m["text"] in NORMAL_EXAMPLES or m["text"] in CORRECTION_EXAMPLES:
            tag = "N-ex" if m["text"] in NORMAL_EXAMPLES else "C-ex"
            text = m["text"][:80].replace("\n", " ")
            print(
                f'    [{tag}] rx={m["rx"]:.2f} gli_c={m["gli_corr"]:.2f} gli_n={m["gli_norm"]:.2f}  "{text}"'
            )


if __name__ == "__main__":
    main()
