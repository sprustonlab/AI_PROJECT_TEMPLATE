"""Fix the tokenizer/model mismatch and test few-shot properly."""

import json
import re
import time
from pathlib import Path

from gliclass import GLiClassModel, ZeroShotClassificationPipeline
from transformers import AutoTokenizer


def fix_tokenizer_and_model(model_name: str):
    """Load model+tokenizer and fix the missing <<EXAMPLE>> token."""
    tok = AutoTokenizer.from_pretrained(model_name)
    model = GLiClassModel.from_pretrained(model_name)

    expected_idx = model.config.example_token_index  # 50372
    emb_size = model.get_input_embeddings().weight.shape[0]  # 50370

    print(f"  Expected <<EXAMPLE>> at index: {expected_idx}")
    print(f"  Current embedding size: {emb_size}")
    print(f"  <<LABEL>> at {tok.convert_tokens_to_ids('<<LABEL>>')}")
    print(f"  <<SEP>> at {tok.convert_tokens_to_ids('<<SEP>>')}")

    # We need to:
    # 1. Add <<EXAMPLE>> to tokenizer so it lands at index 50372
    # 2. Resize model embeddings to accommodate it

    # First, add placeholder tokens to fill 50370, 50371
    # Then add <<EXAMPLE>> which should get 50372
    tok.add_special_tokens(
        {
            "additional_special_tokens": [
                "<<PLACEHOLDER_0>>",
                "<<PLACEHOLDER_1>>",
                "<<EXAMPLE>>",
            ]
        }
    )

    example_id = tok.convert_tokens_to_ids("<<EXAMPLE>>")
    print(f"  <<EXAMPLE>> now at index: {example_id}")

    if example_id != expected_idx:
        print(f"  WARNING: index mismatch! Expected {expected_idx}, got {example_id}")
        # Try direct approach
        print("  Trying targeted fix...")
        tok2 = AutoTokenizer.from_pretrained(model_name)
        # Add tokens one at a time until we hit the right index
        needed = expected_idx - emb_size
        placeholders = [f"<<PLACEHOLDER_{i}>>" for i in range(needed - 1)]
        placeholders.append("<<EXAMPLE>>")
        tok2.add_special_tokens({"additional_special_tokens": placeholders})
        example_id2 = tok2.convert_tokens_to_ids("<<EXAMPLE>>")
        print(f"  <<EXAMPLE>> now at index: {example_id2}")
        if example_id2 == expected_idx:
            tok = tok2
            example_id = example_id2
        else:
            print("  Still wrong. Falling back to whatever index we got.")

    # Resize embeddings
    model.resize_token_embeddings(len(tok))
    new_emb_size = model.get_input_embeddings().weight.shape[0]
    print(f"  New embedding size: {new_emb_size}")

    # Verify
    test_enc = tok.encode(
        "<<EXAMPLE>>hello<<EXAMPLE>>world<<SEP>>", add_special_tokens=False
    )
    test_dec = tok.convert_ids_to_tokens(test_enc)
    print(f"  Encoding test: {list(zip(test_enc, test_dec, strict=False))}")

    return model, tok


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
        "<system-reminder>",
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
                if not text or any(text.startswith(p) for p in noise_prefixes):
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


LABELS = [
    "correction or disagreement",
    "normal request or question",
]

FEWSHOT_EXAMPLES = [
    # Normal
    {
        "text": "can you get me setup up in this repo to run claudechic",
        "labels": ["normal request or question"],
    },
    {"text": "are you here", "labels": ["normal request or question"]},
    {"text": "approve", "labels": ["normal request or question"]},
    {"text": "what is the status?", "labels": ["normal request or question"]},
    {"text": "show me the plan", "labels": ["normal request or question"]},
    {"text": "commit all please", "labels": ["normal request or question"]},
    {"text": "yes", "labels": ["normal request or question"]},
    {"text": "did it close the issue?", "labels": ["normal request or question"]},
    {"text": "what are they?", "labels": ["normal request or question"]},
    {
        "text": "it worked, I saw the toast the orange and the better msg",
        "labels": ["normal request or question"],
    },
    {
        "text": "yes all pass, please remove the file you created",
        "labels": ["normal request or question"],
    },
    {"text": "all pass can you merge?", "labels": ["normal request or question"]},
    {"text": "can you help with this?", "labels": ["normal request or question"]},
    {
        "text": "can you try again wait for me to move to a different agent",
        "labels": ["normal request or question"],
    },
    # Corrections
    {
        "text": "the tests should have advance check in them not the componants, I want a test for what I am seeing",
        "labels": ["correction or disagreement"],
    },
    {
        "text": "I didn't switch to an agent with a orange dot, that is not implemented yet",
        "labels": ["correction or disagreement"],
    },
    {
        "text": "Do what I say, manual trigger long test please as PR to main!",
        "labels": ["correction or disagreement"],
    },
    {
        "text": "please edit the claude md to make that explicit, use the right language, not what it is, what you should DO",
        "labels": ["correction or disagreement"],
    },
    {
        "text": "no, please look at the git history of this repo",
        "labels": ["correction or disagreement"],
    },
    {
        "text": "submodules/claudechic/ = read-only. is not true the main point is to change it",
        "labels": ["correction or disagreement"],
    },
    {
        "text": "No, integration and long tests as well",
        "labels": ["correction or disagreement"],
    },
    {"text": "that is not what I asked for", "labels": ["correction or disagreement"]},
    {
        "text": "why are you in CI and not local tests?",
        "labels": ["correction or disagreement"],
    },
    {
        "text": "No ignore the rest of the E501, can we remove it?",
        "labels": ["correction or disagreement"],
    },
    {
        "text": "no you sent it to the chat, use the MCP tell agent",
        "labels": ["correction or disagreement"],
    },
    {
        "text": "I was in plan mode by mistake, please try again",
        "labels": ["correction or disagreement"],
    },
]

PROMPT = (
    "Classify whether a user is correcting/disagreeing with the assistant, "
    "or making a normal request. Most messages are normal."
)


def main():
    session_dir = (
        Path.home()
        / ".claude"
        / "projects"
        / "-Users-moharb-Documents-Repos-AI-PROJECT-TEMPLATE"
    )

    # Fix tokenizer
    print("Loading and fixing model/tokenizer...")
    model, tok = fix_tokenizer_and_model("knowledgator/gliclass-modern-base-v3.0")

    corr_label = LABELS[0]
    norm_label = LABELS[1]

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

    configs = [
        # (name, classification_type, examples, prompt)
        (
            "A: single-label, no prompt, no examples (baseline)",
            "single-label",
            None,
            None,
        ),
        ("B: single-label + fixed few-shot", "single-label", FEWSHOT_EXAMPLES, None),
        (
            "C: single-label + prompt + fixed few-shot",
            "single-label",
            FEWSHOT_EXAMPLES,
            PROMPT,
        ),
        ("D: multi-label + fixed few-shot", "multi-label", FEWSHOT_EXAMPLES, None),
        (
            "E: multi-label + prompt + fixed few-shot",
            "multi-label",
            FEWSHOT_EXAMPLES,
            PROMPT,
        ),
    ]

    for name, cls_type, examples, prompt in configs:
        print(f"\n{'=' * 80}")
        print(f"CONFIG: {name}")
        print(f"{'=' * 80}")

        pipe = ZeroShotClassificationPipeline(
            model=model,
            tokenizer=tok,
            classification_type=cls_type,
            device="mps",
        )

        kwargs = {}
        if examples:
            kwargs["examples"] = examples
        if prompt:
            kwargs["prompt"] = prompt

        t0 = time.time()
        results = pipe(synth_texts, LABELS, threshold=0.0, **kwargs)
        elapsed = time.time() - t0

        correct = 0
        for (truth, text), result in zip(synth, results, strict=False):
            if isinstance(result, list):
                scores = {r["label"]: r["score"] for r in result}
            else:
                scores = {result["label"]: result["score"]}

            corr_s = scores.get(corr_label, 0.0)
            norm_s = scores.get(norm_label, 0.0)
            predicted = "C" if corr_s > norm_s else "N"
            hit = "OK" if predicted == truth else "XX"
            if predicted == truth:
                correct += 1
            print(
                f"  [{truth}>{predicted} {hit}] corr={corr_s:.3f} norm={norm_s:.3f}  {text[:60]}"
            )

        print(f"  ACCURACY: {correct}/10 ({correct * 10}%)  Time: {elapsed:.2f}s")

    # ===================================================================
    # FULL CORPUS with best config
    # ===================================================================
    human_msgs = load_human_messages(session_dir)
    print(f"\n\n{'=' * 80}")
    print(f"FULL CORPUS ({len(human_msgs)} messages) — running best configs")
    print(f"{'=' * 80}")

    for m in human_msgs:
        m["rx"] = regex_score(m["text"])

    # Run two most promising configs on full data
    for name, cls_type, examples, prompt in [
        ("single-label + fixed few-shot", "single-label", FEWSHOT_EXAMPLES, None),
        (
            "single-label + prompt + fixed few-shot",
            "single-label",
            FEWSHOT_EXAMPLES,
            PROMPT,
        ),
    ]:
        print(f"\n--- {name} ---")
        pipe = ZeroShotClassificationPipeline(
            model=model,
            tokenizer=tok,
            classification_type=cls_type,
            device="mps",
        )

        kwargs = {}
        if examples:
            kwargs["examples"] = examples
        if prompt:
            kwargs["prompt"] = prompt

        texts = [m["text"][:512] for m in human_msgs]
        t0 = time.time()
        results = pipe(texts, LABELS, threshold=0.0, **kwargs)
        elapsed = time.time() - t0
        print(
            f"  Time: {elapsed:.2f}s ({len(texts) / max(elapsed, 0.01):.1f} msgs/sec)"
        )

        for m, result in zip(human_msgs, results, strict=False):
            if isinstance(result, list):
                scores = {r["label"]: r["score"] for r in result}
            else:
                scores = {result["label"]: result["score"]}
            m["gli_corr"] = scores.get(corr_label, 0.0)
            m["gli_norm"] = scores.get(norm_label, 0.0)
            m["gli_pred"] = "C" if m["gli_corr"] > m["gli_norm"] else "N"

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
                [msg_by_uuid[u] for u in uuids], key=lambda m: -m["gli_corr"]
            )
            for m in items[:max_n]:
                text = m["text"][:100].replace("\n", " ")
                print(
                    f'    rx={m["rx"]:.2f} corr={m["gli_corr"]:.3f} norm={m["gli_norm"]:.3f}  "{text}"'
                )

        show(both, "BOTH flagged")
        show(rx_only, "REGEX ONLY")
        show(gli_only, "GLiClass ONLY")

        # Check training examples
        train_texts = {e["text"] for e in FEWSHOT_EXAMPLES}
        print("\n  Training example check:")
        for m in human_msgs:
            if m["text"] in train_texts:
                expected = (
                    "C"
                    if any(
                        e["text"] == m["text"] and e["labels"][0] == corr_label
                        for e in FEWSHOT_EXAMPLES
                    )
                    else "N"
                )
                hit = "OK" if m["gli_pred"] == expected else "XX"
                text = m["text"][:70].replace("\n", " ")
                print(
                    f'    [{expected}>{m["gli_pred"]} {hit}] corr={m["gli_corr"]:.3f} norm={m["gli_norm"]:.3f}  "{text}"'
                )


if __name__ == "__main__":
    main()
