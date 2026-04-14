"""GLiClass experiments: contrastive labels and binary phrasing variants."""

import time

# Same 10 messages - corrections (C) vs normal (N)
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

model = GLiClassModel.from_pretrained("knowledgator/gliclass-modern-base-v3.0")
tokenizer = AutoTokenizer.from_pretrained("knowledgator/gliclass-modern-base-v3.0")
pipeline = ZeroShotClassificationPipeline(
    model=model,
    tokenizer=tokenizer,
    classification_type="multi-label",
    device="mps",
)
print(f"Model loaded in {time.time() - t0:.1f}s\n")

texts = [s[1] for s in samples]
truth = [s[0] for s in samples]

# ======================================================================
# EXPERIMENT 1: Contrastive labels
# ======================================================================
print("=" * 80)
print("EXPERIMENT 1: Contrastive Labels (6 labels, rank them)")
print("=" * 80)

contrastive_labels = [
    "The user is correcting a mistake the assistant made",
    "The user is redirecting the assistant to a different approach",
    "The user is expressing frustration or dissatisfaction",
    "The user is making a normal request or follow-up",
    "The user is asking a question",
    "The user is expressing satisfaction or agreement",
]

correction_labels = set(contrastive_labels[:3])
normal_labels = set(contrastive_labels[3:])

results = pipeline(texts, contrastive_labels, threshold=0.0)

correct = 0
for i, (label, text, result) in enumerate(zip(truth, texts, results, strict=False)):
    print(f"\n  [{label}] {text[:75]}")
    # Sort by score descending
    scored = sorted(result, key=lambda r: -r["score"])
    for r in scored:
        marker = "+" if r["label"] in correction_labels else "-"
        print(f"       {marker} {r['score']:.3f}  {r['label'][:60]}")

    # Determine prediction: highest scoring label's group wins
    top_label = scored[0]["label"] if scored else ""
    predicted = "C" if top_label in correction_labels else "N"

    # Also compute aggregate: sum of correction scores vs normal scores
    corr_sum = sum(r["score"] for r in scored if r["label"] in correction_labels)
    norm_sum = sum(r["score"] for r in scored if r["label"] in normal_labels)
    agg_predicted = "C" if corr_sum > norm_sum else "N"

    hit_top = "OK" if predicted == label else "MISS"
    hit_agg = "OK" if agg_predicted == label else "MISS"
    print(
        f"       >> Top-1: {predicted} ({hit_top}) | Aggregate: corr={corr_sum:.2f} vs norm={norm_sum:.2f} -> {agg_predicted} ({hit_agg})"
    )

    if agg_predicted == label:
        correct += 1

print(
    f"\n  AGGREGATE ACCURACY: {correct}/{len(samples)} ({correct / len(samples) * 100:.0f}%)"
)


# ======================================================================
# EXPERIMENT 2: Binary phrasing variants
# ======================================================================
def run_binary_pair(name: str, pos_label: str, neg_label: str):
    """Run a contrastive pair and report results."""
    labels = [pos_label, neg_label]
    results = pipeline(texts, labels, threshold=0.0)

    print(f"\n  {'Truth':5} {'Pred':5} {'Pos':>6} {'Neg':>6}  Message")
    print(f"  {'-' * 5} {'-' * 5} {'-' * 6} {'-' * 6}  {'-' * 50}")

    correct = 0
    for label, text, result in zip(truth, texts, results, strict=False):
        scores = {r["label"]: r["score"] for r in result}
        pos_score = scores.get(pos_label, 0.0)
        neg_score = scores.get(neg_label, 0.0)
        predicted = "C" if pos_score > neg_score else "N"
        hit = "OK" if predicted == label else "XX"
        if predicted == label:
            correct += 1
        print(
            f"  {label:5} {predicted:5} {pos_score:6.3f} {neg_score:6.3f}  {text[:55]} [{hit}]"
        )

    print(f"  ACCURACY: {correct}/{len(samples)} ({correct / len(samples) * 100:.0f}%)")
    return correct


print("\n" + "=" * 80)
print("EXPERIMENT 2A: 'did something wrong' vs 'new task'")
print("=" * 80)
score_a = run_binary_pair(
    "2A",
    "The user is telling the assistant it did something wrong",
    "The user is giving the assistant a new task",
)

print("\n" + "=" * 80)
print("EXPERIMENT 2B: 'unhappy' vs 'satisfied or neutral'")
print("=" * 80)
score_b = run_binary_pair(
    "2B",
    "The user is unhappy with what the assistant did",
    "The user is satisfied or neutral",
)

print("\n" + "=" * 80)
print("EXPERIMENT 2C: 'assistant made error' vs 'proceeding normally'")
print("=" * 80)
score_c = run_binary_pair(
    "2C",
    "The assistant made an error and the user is pointing it out",
    "The conversation is proceeding normally",
)

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("  Experiment 1 (6-label contrastive, aggregate): see above")
print(f"  Experiment 2A accuracy: {score_a}/10")
print(f"  Experiment 2B accuracy: {score_b}/10")
print(f"  Experiment 2C accuracy: {score_c}/10")
print(
    "\n  Litmus test message: 'That's not what I asked for. I wanted a binary classifier, not multi-class.'"
)
print("  Check results above to see if each experiment catches it.")
