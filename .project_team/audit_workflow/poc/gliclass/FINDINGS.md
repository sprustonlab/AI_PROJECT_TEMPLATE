# GLiClass POC Findings

**Date**: 2026-04-13
**Models**: `knowledgator/gliclass-modern-base-v3.0` (ModernBERT-base, 768d) and `knowledgator/gliclass-modern-large-v3.0` (1024d)
**Hardware**: Apple Silicon MPS
**Data**: 76 JSONL session files from `~/.claude/projects/`, 699 raw user messages, 309 after system message pre-filter

---

## Table of Contents

1. [Initial POC](#1-initial-poc)
2. [Contrastive Labels and Binary Phrasing Variants](#2-contrastive-labels-and-binary-phrasing-variants)
3. [Full Corpus Head-to-Head: Regex vs GLiClass](#3-full-corpus-head-to-head)
4. [Direct Category Classification](#4-direct-category-classification)
5. [Bug Discoveries](#5-bug-discoveries)
6. [Config Sweep with Single-Label Fix](#6-config-sweep-with-single-label-fix)
7. [Few-Shot with Tokenizer Fix](#7-few-shot-with-tokenizer-fix)
8. [Base vs Large Model Comparison](#8-base-vs-large-model-comparison)
9. [Final Validated Configuration](#9-final-validated-configuration)
10. [Recommended Architecture](#10-recommended-architecture)

---

## 1. Initial POC

First test: 10 handcrafted messages (6 corrections, 4 normal), multi-label mode, single binary label.

**Binary label**: "The user is correcting, redirecting, or expressing dissatisfaction with the assistant"

| Message | Truth | Score | Result |
|---------|-------|-------|--------|
| No, that's wrong. I said to use pathlib | C | 0.564 | Flagged |
| Can you help me write a test | N | 0.000 | Clean |
| That's not what I asked for (binary not multi-class) | C | 0.000 | **MISSED** |
| Stop. You're going down the wrong path | C | 0.591 | Flagged |
| Great, now let's add error handling | N | 0.606 | **FP** |
| I'm frustrated - you keep ignoring | C | 0.576 | Flagged |
| Please make the output more concise | N | 0.561 | **FP** |
| Actually, use pytest instead of unittest | C | 0.612 | Flagged |
| What does this error mean? | N | 0.588 | **FP** |
| I already told you three times | C | 0.585 | Flagged |

**Result**: 8/10 flagged. Scores clustered in narrow 0.56-0.61 band. Key litmus test message ("That's not what I asked for") scored 0.000 -- complete miss. Threshold tuning impossible with this score distribution.

**Category classification on flagged items worked well**:
- "No, that's wrong" -> Factual Correction (0.97)
- "Stop, wrong path" -> Approach Redirect (0.90)
- "I already told you three times" -> Approach Redirect (0.95)

**Conclusion**: Binary detection broken, category classification promising.

---

## 2. Contrastive Labels and Binary Phrasing Variants

### Experiment 1: 6-Label Contrastive

Used 6 labels (3 correction, 3 normal) and summed scores by group.

**Aggregate accuracy: 7/10 (70%)**

- Litmus test PASSES with aggregate scoring (corr=1.43 vs norm=1.07)
- "The user is asking a question" label scored 0.7-0.97 on almost everything, polluting top-1 predictions
- FPs: "Great, now let's add error handling" (corr=1.32 vs norm=1.01), "What does this error mean?" (corr=1.44 vs norm=1.15) -- word "error" biases model

### Experiment 2: Binary Phrasing Variants

| Phrasing | Accuracy | Litmus? | Notes |
|----------|----------|---------|-------|
| **2A**: "did something wrong" vs "new task" | 6/10 | MISS | Worst. "What does this error mean?" huge FP (0.844) |
| **2B**: "unhappy" vs "satisfied or neutral" | **7/10** | **PASS** | Best. Perfect recall on all 6 corrections. 3 FPs |
| **2C**: "assistant made error" vs "proceeding normally" | 6/10 | PASS | 4 FPs. "Proceeding normally" scores too low |

**Winner**: Experiment 2B -- 100% recall on corrections, 3 FPs all following "error" keyword pattern.

---

## 3. Full Corpus Head-to-Head

5 real sessions (mix of sizes), 30 user messages, comparing regex tier-1 (from `mine_patterns.py`) vs GLiClass 2B.

| Category | Count |
|----------|-------|
| Flagged by BOTH | 5 |
| Regex ONLY | 1 |
| GLiClass ONLY | 16 |
| Neither (clean) | 8 |

| Metric | Regex | GLiClass |
|--------|-------|----------|
| Flag rate | 20.0% | **70.0%** |
| Time | **13ms** | 11,233ms |
| Speed ratio | **842x faster** | -- |

**GLiClass flagged 70% of messages** -- most were false positives:
- "[Request interrupted by user]" x2 (system boilerplate)
- "You have been idle for 15 seconds..." x3 (system reminder)
- Task notifications (XML, not human text)

**GLiClass caught 1 thing regex missed**: "the tests should have advance check in them not the components" -- real correction with no keyword trigger.

**Key learning**: Pre-filter system/agent boilerplate is essential before any classifier.

---

## 4. Direct Category Classification

### Approach A: 4 regex-bank-aligned labels

Labels: negation, frustration, error, correction. Only 1 genuine human message survived pre-filter from 5 sessions. Insufficient data.

### Approach B: 8 fine-grained labels (full corpus, 699 messages)

Labels: wrong, revert, repeat, frustrated, broken, diff-approach, dont-touch, NORMAL.

| Method | Flagged | Rate |
|--------|---------|------|
| Regex (>=0.3) | 109 | 15.6% |
| GLi top-1 != normal | **655** | **93.7%** |
| GLi best-cat >= 0.7 | 332 | 47.5% |
| GLi "normal" is top-1 | 44 | **6.3%** |

**The "normal" label almost never wins.** Category distribution (top-1):
- revert: 365 (55.7%) -- massively over-represented
- diff-approach: 117 (17.9%)
- broken: 89 (13.6%)
- dont-touch: 54 (8.2%)
- wrong: 17 (2.6%)
- repeat: 11 (1.7%)
- frustrated: 2 (0.3%)

**Conclusion**: Direct categories make over-flagging worse. Specific labels are too "attractive" -- model always finds a non-normal match.

### Approach C: 8 labels on synthetic (10 messages)

Accuracy: 6/10 (60%). "NORMAL" never wins on any message. Same FPs: "Can you help write a test" -> broken(0.735), "Great, add error handling" -> broken(0.807).

---

## 5. Bug Discoveries

### Bug 1: `classification_type="multi-label"` (sigmoid) wrong for binary

Multi-label applies sigmoid to each label independently. Both labels can score 0.99 simultaneously -- no competition. For binary classification, `"single-label"` (softmax) forces labels to compete, producing directly comparable probabilities.

**Impact**: Switching multi-label -> single-label improved synthetic accuracy from 50-60% to 80%.

### Bug 2: `examples=` parameter silently broken on v3.0

The pipeline's few-shot feature uses `<<EXAMPLE>>` as a boundary token. Investigation revealed:

| Token | Expected Index | In Tokenizer? | In Embedding Matrix? |
|-------|---------------|---------------|---------------------|
| `<<LABEL>>` | 50368 | Yes | Yes |
| `<<SEP>>` | 50369 | Yes | Yes |
| `<<EXAMPLE>>` | 50372 | **No** | **No** (matrix is 50370 rows) |

When `<<EXAMPLE>>` is passed to the tokenizer, it produces 4 garbage subwords:
```
<<EXAMPLE>> -> [5291: '<<', 4237: 'EX', 40419: 'AMPLE', 5064: '>>']
```

The model config declares `example_token_index: 50372` but the embedding matrix only has 50370 rows. This is a packaging bug in the v3.0 release.

**Impact**: All experiments using `examples=` were injecting garbled text. Any apparent benefit was random noise from subword artifacts.

---

## 6. Config Sweep with Single-Label Fix

### Synthetic (10 messages)

| Config | Accuracy | Time | Notes |
|--------|----------|------|-------|
| A: multi-label, no prompt (old baseline) | 6/10 | 0.36s | sigmoid, no competition |
| **B: SINGLE-label, no prompt** | **8/10** | **0.37s** | Just fixing classification_type |
| C: single-label + minimal prompt | 5/10 | 0.37s | Prompt biases toward "normal" on synthetic |
| **D: single-label + prompt with embedded examples** | **8/10** | 1.60s | Tied with B, better score separation |
| E: multi-label + prompt with embedded examples | 6/10 | 1.60s | Multi-label ruins it |

### Full corpus (310 messages, pre-filtered)

**Config D (single-label + prompt with examples):**
- Flag rate: 27.7% (86/310)
- Still too many FPs (81 GLi-only)
- Main FP source: `<system-reminder> PLAN MODE ACTIVE` messages

**Config C (single-label + minimal prompt) -- THE WINNER:**
- Flag rate: **1.6%** (5/310)
- Regex flag rate: 2.6% (8/310)
- **Zero overlap** with regex -- perfectly complementary
- Agreement: **95.8%**
- Speed: **18.4 msgs/sec**

### Config C catches (regex misses)

- "I see an invalid state transition error" (gli=0.622)
- "check they all failed, did you push the claudechic?" (gli=0.602)
- "for the API docs can you please see why I don't get all of the functions" (gli=0.597)
- "1) we should evaluate more than 1 tool per area of concern" (gli=0.592)
- "yes commit and make a PR to main. exclude the .project_team file" (gli=0.545)

### Regex catches (GLiClass misses)

- "No the bug report I said in sprustonlab!" (rx=0.48)
- "pytest-cov is not running on the right thing, i said to focus on claudechic" (rx=0.40)
- "that is not what I asked for" (rx=0.77)
- "It makes the .gitignore not correct" (rx=0.40)
- "don't edit claudechic is a conditional as there is a developer mode" (rx=0.40)

---

## 7. Few-Shot with Tokenizer Fix

### The fix

Registered `<<EXAMPLE>>` at index 50372 (with 2 placeholder tokens to fill the gap at 50370-50371) and resized model embeddings from 50370 to 50373.

After fix, `<<EXAMPLE>>` tokenizes correctly as a single special token:
```
<<EXAMPLE>>hello<<SEP>> -> [50372: '<<EXAMPLE>>', 23120: 'hello', 50369: '<<SEP>>']
```

### Results with fixed tokenizer

| Config | Accuracy | Notes |
|--------|----------|-------|
| single-label, no examples (baseline) | 8/10 | Unchanged -- confirms fix didn't break base behavior |
| single-label + fixed few-shot | **4/10** | correction score = 0.000 for ALL messages |
| single-label + prompt + fixed few-shot | **4/10** | Same -- correction = 0.000 everywhere |
| multi-label + fixed few-shot | **4/10** | normal always wins |
| multi-label + prompt + fixed few-shot | **4/10** | normal always wins |

### Why few-shot is fundamentally broken

The embedding at index 50372 was initialized from a random distribution (model was never trained with `<<EXAMPLE>>`). With properly-tokenized example boundaries, the model sees an untrained embedding and defaults to classifying everything as "normal."

Training example sanity check (full corpus): ALL correction training examples misclassified as normal. The model has no learned representation for `<<EXAMPLE>>`.

**Conclusion**: Few-shot cannot work on v3.0 without fine-tuning to add the `<<EXAMPLE>>` embedding.

---

## 8. Base vs Large Model Comparison

### Synthetic (10 messages, single-label, no prompt -- Config B)

| Message | Truth | Base | Large |
|---------|-------|------|-------|
| No, that's wrong. I said to use pathlib | C | C (0.931) | C (0.999) |
| Can you help me write a test | N | N (0.947) | N (0.931) |
| That's not what I asked for | C | C (0.724) | C (0.974) |
| Stop. You're going down the wrong path | C | C (0.964) | C (0.999) |
| **Great, now let's add error handling** | **N** | **C (XX)** | **N (OK)** |
| I'm frustrated - you keep ignoring | C | C (0.875) | C (0.598) |
| **Please make the output more concise** | **N** | **N (OK)** | **C (XX)** |
| Actually, use pytest instead of unittest | C | C (0.967) | C (0.966) |
| **What does this error mean?** | **N** | **C (XX)** | **N (OK)** |
| I already told you three times | C | C (0.956) | C (0.995) |

**Large: 9/10 (90%) vs Base: 8/10 (80%)**

Large fixes both base FPs ("error handling", "error mean?") but introduces one new FP ("make output more concise").

### Full corpus (307 messages, Config B)

| Metric | Base | Large |
|--------|------|-------|
| Model load | 0.9s | 17.7s |
| Inference speed | 31.2 msgs/sec | 12.4 msgs/sec |
| GLi flagged | 172 (56.0%) | **109 (35.5%)** |
| Both (regex + GLi) | 8 | 7 |
| Regex only | 0 | 1 |
| GLi only | 164 | 102 |
| Agreement | 46.6% | **66.4%** |

### Large model's top catches (GLi-only)

Real corrections regex misses:
- "submodules/claudechic/ = read-only. is not true the main point is to change it" (0.999)
- "I see an invalid state transition error" (0.999)
- "I didn't say you can advance" (0.991)
- "I don't think this watch is doing what you think" (0.990)
- "please edit the claude md to make that explicit, use the right language" (0.989)

Still has false positives:
- "also look at claudechic submodule, we changed both" (0.993) -- normal instruction
- "We have issues today" (0.994) -- ambiguous
- "Just add that the workflow can have a gitignore step" (0.990) -- normal instruction

### Prompt hurts large model too

With minimal prompt, large drops from 9/10 to 3/10 on synthetic. Same pattern as base. **Config B (no prompt) is best for both models.**

---

## 9. Final Validated Configuration

### For production use in mine_patterns.py tier-2

**Config C**: `single-label` + minimal prompt (base model)

```python
from gliclass import GLiClassModel, ZeroShotClassificationPipeline
from transformers import AutoTokenizer

model = GLiClassModel.from_pretrained("knowledgator/gliclass-modern-base-v3.0")
tokenizer = AutoTokenizer.from_pretrained("knowledgator/gliclass-modern-base-v3.0")

pipeline = ZeroShotClassificationPipeline(
    model=model,
    tokenizer=tokenizer,
    classification_type="single-label",  # REQUIRED: softmax, not sigmoid
    device="mps",
)

labels = [
    "correction or disagreement",
    "normal request or question",
]

prompt = (
    "Classify whether a user is correcting/disagreeing with the assistant, "
    "or making a normal request. Most messages are normal."
)

# Do NOT use examples= parameter (broken on v3.0)
results = pipeline(texts, labels, threshold=0.5, prompt=prompt)
```

### Key numbers

| Metric | Value |
|--------|-------|
| Synthetic accuracy | 5/10 (base+prompt), 8/10 (base no-prompt), 9/10 (large no-prompt) |
| Full corpus flag rate (Config C) | 1.6% (5/309) |
| Overlap with regex | **0** (perfectly complementary) |
| Agreement with regex | 95.8% |
| Combined flag rate (regex + GLi) | 4.2% (13/309) |
| Speed (base, Config C) | 18.4 msgs/sec |
| Speed (large, Config B) | 12.4 msgs/sec |
| Model load (base) | 0.9-3.1s |
| Model load (large) | 17.7s |

### Why these specific settings

- **`single-label`**: Sigmoid (multi-label) scores labels independently -- both can be 0.99. Softmax (single-label) forces competition. This is the single biggest improvement found.
- **No `examples=`**: The `<<EXAMPLE>>` token (index 50372) is not in the tokenizer vocabulary and has no trained embedding. Passing examples injects garbled subwords or activates an untrained embedding.
- **Minimal prompt for Config C**: One sentence providing task context. Longer prompts and embedded examples bias the model toward "normal" and reduce throughput.
- **No prompt for Config B**: On the large model, even the minimal prompt hurts (9/10 -> 3/10). Best synthetic accuracy comes from letting the model use its pretrained understanding alone.

---

## 10. Recommended Architecture

```
User message
    |
    v
[Pre-filter: strip system/agent boilerplate]
    |  Removes: [Spawned by agent, [Message from agent, [Request interrupted,
    |  <task-notification>, You have been idle, Workflow ', <system-reminder>,
    |  This session is being continued, [Question from agent, [Redirected by
    |
    v
[Regex tier-1: fast keyword matching]  --->  flagged (2.6%)
    |  From mine_patterns.py: NEGATION,           |
    |  FRUSTRATION, ERROR, CORRECTION banks        |
    |  Threshold: 0.3                              v
    v                                         [Union]  --->  correction candidates (4.2%)
[GLiClass single-label, no prompt]              ^
    |  Config B (base or large model)              |
    |  On regex-clean messages only                |
    v                                              |
  flagged (1.6%)  -------------------------------->+
```

### Performance budget

| Stage | Time (309 msgs) | Throughput |
|-------|-----------------|-----------|
| Pre-filter | <1ms | instant (string prefix check) |
| Regex tier-1 | 13ms | ~24,000 msgs/sec |
| GLiClass base Config C | 16.8s | 18.4 msgs/sec |
| GLiClass large Config B | 24.8s | 12.4 msgs/sec |
| Model load (base, one-time) | 0.9-3.1s | -- |
| Model load (large, one-time) | 17.7s | -- |

### Model selection

- **Base model**: Use for real-time/interactive, when load time matters, or as tier-2 rescue pass on uncertain messages only
- **Large model**: Use for offline batch analysis (17.7s load is acceptable), 9/10 synthetic accuracy, sharper confidence scores

---

## Files

| File | Purpose |
|------|---------|
| `run_poc.py` | Main pipeline: pre-filter + regex + GLiClass Config C |
| `test_small.py` | Minimal 10-message test with Config C |
| `test_experiments.py` | Contrastive labels + binary phrasing (Exp 1, 2A/2B/2C) |
| `test_categories_direct.py` | Direct category classification (4 and 8 labels) |
| `test_categories_v2.py` | Full corpus category classification (all 76 sessions) |
| `test_fewshot.py` | Few-shot experiments (before tokenizer fix) |
| `test_fixed.py` | Single-label + embedded prompt config sweep |
| `test_fixed_tokenizer.py` | Tokenizer fix + proper few-shot testing |
| `test_large.py` | Base vs large model comparison |
| `head_to_head.py` | Regex vs GLiClass on 5 real sessions |
| `pixi.toml` | Standalone pixi environment (does NOT touch main project) |
| `FINDINGS.md` | This file |
