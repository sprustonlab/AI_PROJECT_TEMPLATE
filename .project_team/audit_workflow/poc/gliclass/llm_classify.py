"""Classify messages using Claude API (LLM-as-classifier).

Usage:
    export ANTHROPIC_API_KEY=sk-...
    pixi run python llm_classify.py

Reads messages_310.jsonl, classifies each message, writes llm_api_results.jsonl.
Uses Claude 3.5 Haiku for cost efficiency (~$0.01 for 315 messages).
"""

import json
import os
import time
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("Install anthropic: pip install anthropic")
    raise

SYSTEM_PROMPT = """\
You are classifying user messages from a coding assistant conversation.

Classify each message as either:
- "correction": The user is correcting the assistant, disagreeing, pointing out \
the assistant did the wrong thing, redirecting the assistant back on track, \
expressing frustration at the assistant's behavior, or rejecting the assistant's \
approach.
- "normal": The user is making a normal request, asking a question, approving, \
providing information, or giving instructions without indicating the assistant \
did something wrong.

Respond with ONLY a JSON object: {"label": "correction"} or {"label": "normal"}
"""


def classify_batch(messages, model="claude-3-5-haiku-latest", max_rpm=50):
    """Classify messages one by one with rate limiting."""
    client = anthropic.Anthropic()
    results = []
    delay = 60.0 / max_rpm

    for i, msg in enumerate(messages):
        text = msg["text"]
        if len(text) > 2000:
            text = text[:2000] + "..."

        try:
            response = client.messages.create(
                model=model,
                max_tokens=50,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": text}],
            )
            raw = response.content[0].text.strip()
            try:
                parsed = json.loads(raw)
                label = parsed.get("label", "normal")
            except json.JSONDecodeError:
                label = "correction" if "correction" in raw.lower() else "normal"

            results.append(
                {
                    "index": msg["index"],
                    "label": label,
                    "raw_response": raw,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                }
            )

            if (i + 1) % 25 == 0:
                print(f"  Classified {i + 1}/{len(messages)}...")

        except Exception as e:
            print(f"  Error on message {msg['index']}: {e}")
            results.append(
                {
                    "index": msg["index"],
                    "label": "error",
                    "raw_response": str(e),
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
            )

        time.sleep(delay)

    return results


def classify_batch_api(messages, model="claude-3-5-haiku-latest"):
    """Use the Batch API for 50% cost savings (results in ~24h)."""
    client = anthropic.Anthropic()

    requests = []
    for msg in messages:
        text = msg["text"]
        if len(text) > 2000:
            text = text[:2000] + "..."

        requests.append(
            {
                "custom_id": f"msg_{msg['index']}",
                "params": {
                    "model": model,
                    "max_tokens": 50,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": text}],
                },
            }
        )

    # Write requests to JSONL for batch submission
    batch_file = Path(__file__).parent / "batch_requests.jsonl"
    with open(batch_file, "w", encoding="utf-8") as f:
        for req in requests:
            f.write(json.dumps(req) + "\n")

    print(f"Wrote {len(requests)} batch requests to {batch_file}")
    print("Submit via: anthropic batch create --input batch_requests.jsonl")
    return batch_file


def main():
    msgs_path = Path(__file__).parent / "messages_310.jsonl"
    out_path = Path(__file__).parent / "llm_api_results.jsonl"

    messages = []
    for line in msgs_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            messages.append(json.loads(line))

    print(f"Loaded {len(messages)} messages")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("No ANTHROPIC_API_KEY set. Generating batch file instead...")
        classify_batch_api(messages)
        return

    print("Classifying with Claude API...")
    results = classify_batch(messages)

    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    corrections = sum(1 for r in results if r["label"] == "correction")
    total_input = sum(r["input_tokens"] for r in results)
    total_output = sum(r["output_tokens"] for r in results)

    print(f"\nResults: {corrections}/{len(results)} flagged as corrections")
    print(f"Tokens used: {total_input:,} input + {total_output:,} output")
    # Haiku pricing
    cost = (total_input / 1e6 * 0.25) + (total_output / 1e6 * 1.25)
    print(f"Estimated cost: ${cost:.4f}")
    print(f"Wrote results to {out_path}")


if __name__ == "__main__":
    main()
