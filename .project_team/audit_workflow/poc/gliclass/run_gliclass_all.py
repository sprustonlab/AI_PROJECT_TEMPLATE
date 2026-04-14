"""Run GLiClass Config C on all 315 messages and save results."""

import json
import time
from pathlib import Path

from gliclass import GLiClassModel, GLiClassModelConfig, ZeroShotClassificationPipeline
from transformers import AutoTokenizer


def main():
    msgs_path = Path(__file__).parent / "messages_310.jsonl"
    out_path = Path(__file__).parent / "gliclass_results.jsonl"

    messages = []
    for line in msgs_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            messages.append(json.loads(line))

    print(f"Loaded {len(messages)} messages")

    # Config C: single-label + minimal prompt (best from config sweep)
    model_name = "knowledgator/gliclass-modern-base-v3.0"
    config = GLiClassModelConfig.from_pretrained(model_name)
    model = GLiClassModel.from_pretrained(model_name, config=config)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model.to("mps")

    pipeline = ZeroShotClassificationPipeline(
        model=model,
        tokenizer=tokenizer,
        classification_type="single-label",
        device="mps",
    )

    labels = ["correction or disagreement", "normal request or question"]
    prompt = (
        "Classify whether a user is correcting/disagreeing with the assistant, "
        "or making a normal request. Most messages are normal."
    )

    texts = [m["text"] for m in messages]

    print("Running GLiClass...")
    t0 = time.time()
    results = pipeline(texts, labels, threshold=0.5, prompt=prompt)
    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s ({len(texts) / elapsed:.1f} msgs/sec)")

    with open(out_path, "w", encoding="utf-8") as f:
        for msg, res in zip(messages, results, strict=False):
            scores = {item["label"]: item["score"] for item in res}
            top = max(res, key=lambda x: x["score"])
            obj = {
                "index": msg["index"],
                "label": top["label"],
                "score": top["score"],
                "correction_score": scores.get("correction or disagreement", 0),
                "normal_score": scores.get("normal request or question", 0),
            }
            f.write(json.dumps(obj) + "\n")

    flagged = sum(
        1
        for msg, res in zip(messages, results, strict=False)
        if max(res, key=lambda x: x["score"])["label"] == "correction or disagreement"
    )
    print(f"Flagged: {flagged}/{len(messages)} ({flagged / len(messages) * 100:.1f}%)")
    print(f"Wrote results to {out_path}")


if __name__ == "__main__":
    main()
