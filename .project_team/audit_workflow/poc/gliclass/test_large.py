"""Test gliclass-large-v3.0 vs base-v3.0 on synthetic + real data."""

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


def load_human_messages(session_dir: Path) -> list[dict]:
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
                if not text or any(text.startswith(p) for p in NOISE_PREFIXES):
                    continue
                msgs.append(
                    {"text": text, "uuid": obj.get("uuid", ""), "session": f.stem[:12]}
                )
    return msgs


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


LABELS = ["correction or disagreement", "normal request or question"]
PROMPT = (
    "Classify whether a user is correcting/disagreeing with the assistant, "
    "or making a normal request. Most messages are normal."
)

SYNTH = [
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


def run_model(model_name: str, human_msgs: list[dict]):
    """Run a model through synthetic + full corpus tests."""
    from gliclass import GLiClassModel, ZeroShotClassificationPipeline
    from transformers import AutoTokenizer

    print(f"\n{'=' * 80}")
    print(f"MODEL: {model_name}")
    print(f"{'=' * 80}")

    t0 = time.time()
    model = GLiClassModel.from_pretrained(model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # Check architecture
    print(f"  Architecture: {model.config.architecture_type}")
    emb = model.get_input_embeddings()
    print(f"  Embedding size: {emb.weight.shape}")
    print(f"  class_token_index: {model.config.class_token_index}")
    print(f"  text_token_index: {model.config.text_token_index}")
    print(
        f"  example_token_index: {getattr(model.config, 'example_token_index', 'N/A')}"
    )

    pipeline = ZeroShotClassificationPipeline(
        model=model,
        tokenizer=tokenizer,
        classification_type="single-label",
        device="mps",
    )
    load_time = time.time() - t0
    print(f"  Load time: {load_time:.1f}s")

    corr_label = LABELS[0]

    # --- Synthetic test ---
    # Config B: no prompt
    print("\n  --- Synthetic: single-label, no prompt ---")
    t0 = time.time()
    results_b = pipeline([s[1] for s in SYNTH], LABELS, threshold=0.5)
    time_b = time.time() - t0
    correct_b = 0
    for (truth, text), result in zip(SYNTH, results_b, strict=False):
        scores = (
            {r["label"]: r["score"] for r in result}
            if isinstance(result, list)
            else {result["label"]: result["score"]}
        )
        pred = "C" if scores.get(corr_label, 0) > scores.get(LABELS[1], 0) else "N"
        hit = "OK" if pred == truth else "XX"
        if pred == truth:
            correct_b += 1
        cs = scores.get(corr_label, 0)
        ns = scores.get(LABELS[1], 0)
        print(f"    [{truth}>{pred} {hit}] corr={cs:.3f} norm={ns:.3f}  {text[:60]}")
    print(f"    ACCURACY: {correct_b}/10  Time: {time_b:.2f}s")

    # Config C: minimal prompt
    print("\n  --- Synthetic: single-label + minimal prompt ---")
    t0 = time.time()
    results_c = pipeline([s[1] for s in SYNTH], LABELS, threshold=0.5, prompt=PROMPT)
    time_c = time.time() - t0
    correct_c = 0
    for (truth, text), result in zip(SYNTH, results_c, strict=False):
        scores = (
            {r["label"]: r["score"] for r in result}
            if isinstance(result, list)
            else {result["label"]: result["score"]}
        )
        pred = "C" if scores.get(corr_label, 0) > scores.get(LABELS[1], 0) else "N"
        hit = "OK" if pred == truth else "XX"
        if pred == truth:
            correct_c += 1
        cs = scores.get(corr_label, 0)
        ns = scores.get(LABELS[1], 0)
        print(f"    [{truth}>{pred} {hit}] corr={cs:.3f} norm={ns:.3f}  {text[:60]}")
    print(f"    ACCURACY: {correct_c}/10  Time: {time_c:.2f}s")

    # --- Full corpus: best synthetic config ---
    best_prompt = PROMPT if correct_c >= correct_b else None
    best_name = "C (prompt)" if best_prompt else "B (no prompt)"
    print(f"\n  --- Full corpus ({len(human_msgs)} msgs): Config {best_name} ---")

    texts = [m["text"][:512] for m in human_msgs]
    t0 = time.time()
    results_full = pipeline(texts, LABELS, threshold=0.5, prompt=best_prompt)
    full_time = time.time() - t0
    print(
        f"    Time: {full_time:.2f}s ({len(texts) / max(full_time, 0.01):.1f} msgs/sec)"
    )

    for m, result in zip(human_msgs, results_full, strict=False):
        scores = (
            {r["label"]: r["score"] for r in result}
            if isinstance(result, list)
            else {result["label"]: result["score"]}
        )
        m["gli_corr"] = scores.get(corr_label, 0)
        m["gli_norm"] = scores.get(LABELS[1], 0)
        m["gli_flag"] = m["gli_corr"] > m["gli_norm"]

    rx_set = {m["uuid"] for m in human_msgs if m["rx"] >= 0.3}
    gli_set = {m["uuid"] for m in human_msgs if m["gli_flag"]}
    both = rx_set & gli_set
    rx_only = rx_set - gli_set
    gli_only = gli_set - rx_set
    neither = {m["uuid"] for m in human_msgs} - rx_set - gli_set

    print(
        f"    Regex flagged:   {len(rx_set)} ({len(rx_set) / len(human_msgs) * 100:.1f}%)"
    )
    print(
        f"    GLi flagged:     {len(gli_set)} ({len(gli_set) / len(human_msgs) * 100:.1f}%)"
    )
    print(f"    Both:            {len(both)}")
    print(f"    Regex only:      {len(rx_only)}")
    print(f"    GLi only:        {len(gli_only)}")
    print(f"    Neither:         {len(neither)}")
    print(
        f"    Agreement:       {(len(both) + len(neither)) / len(human_msgs) * 100:.1f}%"
    )

    msg_by_uuid = {m["uuid"]: m for m in human_msgs}

    for title, uuids in [
        ("BOTH", both),
        ("REGEX ONLY", rx_only),
        ("GLiClass ONLY", gli_only),
    ]:
        items = sorted([msg_by_uuid[u] for u in uuids], key=lambda m: -m["gli_corr"])
        print(f"\n    {title} ({len(uuids)}):")
        for m in items[:8]:
            text = m["text"][:100].replace("\n", " ")
            print(
                f'      rx={m["rx"]:.2f} corr={m["gli_corr"]:.3f} norm={m["gli_norm"]:.3f}  "{text}"'
            )

    return {
        "model": model_name,
        "load_time": load_time,
        "synth_b": correct_b,
        "synth_c": correct_c,
        "full_time": full_time,
        "full_speed": len(texts) / max(full_time, 0.01),
        "rx_flagged": len(rx_set),
        "gli_flagged": len(gli_set),
        "both": len(both),
        "rx_only": len(rx_only),
        "gli_only": len(gli_only),
        "agreement": (len(both) + len(neither)) / len(human_msgs) * 100,
    }


def main():
    session_dir = (
        Path.home()
        / ".claude"
        / "projects"
        / "-Users-moharb-Documents-Repos-AI-PROJECT-TEMPLATE"
    )
    human_msgs = load_human_messages(session_dir)
    for m in human_msgs:
        m["rx"] = regex_score(m["text"])
    print(
        f"Loaded {len(human_msgs)} human messages from {len(list(session_dir.glob('*.jsonl')))} sessions"
    )

    results = []

    # Base model
    r1 = run_model("knowledgator/gliclass-modern-base-v3.0", human_msgs)
    results.append(r1)

    # Large model
    r2 = run_model("knowledgator/gliclass-modern-large-v3.0", human_msgs)
    results.append(r2)

    # --- Comparison table ---
    print(f"\n\n{'=' * 80}")
    print("BASE vs LARGE COMPARISON")
    print(f"{'=' * 80}")
    print(f"  {'Metric':<25} {'base-v3.0':>15} {'large-v3.0':>15}")
    print(f"  {'-' * 25} {'-' * 15} {'-' * 15}")
    for key, label in [
        ("load_time", "Model load (s)"),
        ("synth_b", "Synthetic (no prompt)"),
        ("synth_c", "Synthetic (+ prompt)"),
        ("full_time", "Full corpus time (s)"),
        ("full_speed", "Speed (msgs/sec)"),
        ("gli_flagged", "GLi flagged"),
        ("both", "Both flagged"),
        ("rx_only", "Regex only"),
        ("gli_only", "GLi only"),
        ("agreement", "Agreement (%)"),
    ]:
        v1 = results[0][key]
        v2 = results[1][key]
        fmt = ".1f" if isinstance(v1, float) else "d"
        print(f"  {label:<25} {v1:>15{fmt}} {v2:>15{fmt}}")


if __name__ == "__main__":
    main()
