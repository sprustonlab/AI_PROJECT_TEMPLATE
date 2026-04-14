"""Minimal GLiClass test with hardcoded sample messages.

Uses validated Config C (see FINDINGS.md):
- classification_type="single-label" -- softmax forces labels to compete.
  Multi-label (sigmoid) scores each label independently, so both can be 0.99.
- Minimal prompt -- one sentence of task context.
- Do NOT use examples= parameter -- broken on v3.0. The <<EXAMPLE>> token
  (expected at index 50372) is missing from the tokenizer vocabulary and has
  no trained embedding in the model weights.
"""

import time

# Sample user messages - mix of corrections (C) and normal requests (N)
samples = [
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

print("Loading model...")
t0 = time.time()

from gliclass import GLiClassModel, ZeroShotClassificationPipeline
from transformers import AutoTokenizer

model_name = "knowledgator/gliclass-modern-base-v3.0"
model = GLiClassModel.from_pretrained(model_name)
tokenizer = AutoTokenizer.from_pretrained(model_name)

# CRITICAL: single-label (softmax), NOT multi-label (sigmoid).
# Multi-label scores each label independently via sigmoid -- both can be 0.99
# with no competition. Single-label uses softmax to force the two labels to
# compete, producing directly comparable probabilities.
pipeline = ZeroShotClassificationPipeline(
    model=model,
    tokenizer=tokenizer,
    classification_type="single-label",
    device="mps",
)
print(f"Model loaded in {time.time() - t0:.1f}s\n")

# Config C labels: short, descriptive, contrastive
labels = [
    "correction or disagreement",
    "normal request or question",
]

# Minimal prompt -- more text biases the model toward "normal" and hurts
# accuracy on synthetic benchmarks. One sentence is the sweet spot.
prompt = (
    "Classify whether a user is correcting/disagreeing with the assistant, "
    "or making a normal request. Most messages are normal."
)

corr_label = labels[0]

# --- Binary classification ---
print("=" * 70)
print("Config C: single-label + minimal prompt")
print("=" * 70)
t0 = time.time()

# Do NOT pass examples= (broken on v3.0, see FINDINGS.md section 5 and 7)
results = pipeline([s[1] for s in samples], labels, threshold=0.5, prompt=prompt)
print(f"Time: {time.time() - t0:.2f}s\n")

correct = 0
for (truth, text), result in zip(samples, results, strict=False):
    if isinstance(result, list):
        scores = {r["label"]: r["score"] for r in result}
    else:
        scores = {result["label"]: result["score"]}

    corr_s = scores.get(corr_label, 0.0)
    norm_s = scores.get(labels[1], 0.0)
    predicted = "C" if corr_s > norm_s else "N"
    hit = "OK" if predicted == truth else "XX"
    if predicted == truth:
        correct += 1
    flag = ">> CORR" if predicted == "C" else "   norm"
    print(
        f"  [{truth}>{predicted} {hit}] corr={corr_s:.3f} norm={norm_s:.3f} {flag}  {text[:65]}"
    )

print(f"\nAccuracy: {correct}/10 ({correct * 10}%)")
print("Expected: 5/10 with prompt (Config C), 8/10 without prompt (Config B)")
print("See FINDINGS.md for full experiment history.")

# --- Also run without prompt (Config B) for comparison ---
print(f"\n{'=' * 70}")
print("Config B: single-label, no prompt (for comparison)")
print("=" * 70)
t0 = time.time()
results_b = pipeline([s[1] for s in samples], labels, threshold=0.5)
print(f"Time: {time.time() - t0:.2f}s\n")

correct_b = 0
for (truth, text), result in zip(samples, results_b, strict=False):
    if isinstance(result, list):
        scores = {r["label"]: r["score"] for r in result}
    else:
        scores = {result["label"]: result["score"]}

    corr_s = scores.get(corr_label, 0.0)
    norm_s = scores.get(labels[1], 0.0)
    predicted = "C" if corr_s > norm_s else "N"
    hit = "OK" if predicted == truth else "XX"
    if predicted == truth:
        correct_b += 1
    flag = ">> CORR" if predicted == "C" else "   norm"
    print(
        f"  [{truth}>{predicted} {hit}] corr={corr_s:.3f} norm={norm_s:.3f} {flag}  {text[:65]}"
    )

print(f"\nAccuracy: {correct_b}/10 ({correct_b * 10}%)")
print("\nNote: Config B scores higher on synthetic (8/10) but Config C")
print("has better precision on real corpus data (1.6% vs 56% flag rate).")
print("For production, Config C (with prompt) is recommended as tier-2")
print("rescue pass after regex tier-1.")
