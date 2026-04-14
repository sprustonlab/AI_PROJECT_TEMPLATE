# Researcher Findings -- Interaction Pattern Mining Landscape

## Summary

The current spec uses tier-1 regex scoring (from `mine_patterns.py`) for detecting user corrections. This report surveys the external landscape for better approaches across six areas: multi-tier scoring, clustering, embeddings, interactive exploration, evaluation metrics, and data quality. The findings support a **three-tier scoring pipeline** with **BERTopic-based clustering** and **interactive exploration** as the recommended architecture.

**Tier of best sources found:** T1-T5 across categories. All recommended tools are MIT or Apache-2.0 licensed.

---

## 1. Multi-Tier Scoring Architecture

The single biggest improvement over regex-only scoring is a cascading pipeline where each tier processes fewer turns at higher accuracy.

### Tier 1: Regex (Current -- mine_patterns.py)

Keep as-is. Fast, high recall, low precision. Its job is to flag candidate correction turns for deeper analysis. No changes needed.

### Tier 2: Zero-Shot NLI Classification (DeBERTa)

- **Model:** `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` (HuggingFace)
- **Tier:** T1/T2 (official HuggingFace model, peer-reviewed NLI approach)
- **License:** MIT
- **How it works:** Natural Language Inference reformulates classification as hypothesis testing. For each user turn, pose candidate labels as hypotheses:
  - "The user is correcting the assistant's mistake"
  - "The user is expressing frustration"
  - "The user is redirecting the conversation to a different approach"
  - "The user is clarifying a requirement"
  - "The user is satisfied with the response"
- **Accuracy:** ~70-85% depending on label quality, zero training data required
- **Performance:** ~400MB model (base variant), runs on CPU. A newer ModernBERT-based variant (GLiClass) handles up to 8k tokens with faster inference.
- **Dependencies:** `transformers`, `torch`
- **Integration:** `pipeline("zero-shot-classification", model="MoritzLaurer/deberta-v3-base-zeroshot-v2.0")` -- returns confidence scores per label. Classify every turn flagged by tier-1 regex.
- **Risks:** Zero-shot accuracy varies by label wording. Needs validation against a manually-labeled sample of real session corrections. Model download is ~400MB on first use.

### Tier 3: LLM-as-Judge (Claude API)

- **Tier:** T1 (well-documented technique, peer-reviewed survey at arxiv.org/html/2412.05579v2)
- **License:** N/A (technique, not library)
- **How it works:** Use Claude to classify corrections with a structured prompt asking for correction type, severity, root cause, and suggested fix category. Achieves 80%+ agreement with human preferences at 500x-5000x cost reduction vs human review.
- **Integration:** Run only on turns that tier-2 NLI scores as high-confidence corrections. This keeps API costs low -- typically <5% of total turns.
- **Risks:** API costs scale with conversation volume. Potential "preference leakage" if using same model family as the agent being evaluated. Mitigate by using a different model or explicit debiasing instructions.
- **Key reference:** Langfuse documents LLM-as-judge patterns at langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge

### Why Three Tiers?

Each tier processes progressively fewer turns:
- Tier 1 (regex): All turns, ~0ms per turn
- Tier 2 (NLI): ~10-30% of turns (flagged by regex), ~50ms per turn on CPU
- Tier 3 (LLM): ~2-5% of turns (high-confidence corrections), ~1-2s per turn

This keeps the pipeline fast and cheap while achieving high accuracy where it matters.

---

## 2. Clustering & Pattern Discovery

### BERTopic (TOP RECOMMENDATION)

- **URL:** https://github.com/MaartenGr/BERTopic
- **Tier:** T5 (well-maintained community repo)
- **License:** MIT
- **Stars:** 7.5k
- **Tests:** Yes (GitHub Actions CI)
- **Last update:** January 2025
- **Python:** 3.10+
- **Dependencies:** `sentence-transformers`, `umap-learn`, `hdbscan`, `scikit-learn`, `plotly`

**Why BERTopic:** It provides a modular pipeline (embeddings -> UMAP dimensionality reduction -> HDBSCAN clustering -> c-TF-IDF topic representation) where any component can be swapped. Key features for our use case:

1. **Automatic topic discovery** -- no need to pre-specify number of clusters
2. **HDBSCAN clustering** -- handles noise/outliers natively (not every correction fits a pattern)
3. **c-TF-IDF topic labeling** -- extracts representative keywords per cluster
4. **LLM-powered cluster labeling** -- can use Claude to auto-generate human-readable labels like "File path handling errors" or "Test approach disagreements" instead of raw keywords
5. **Built-in visualizations** -- interactive topic maps, hierarchies, heatmaps via Plotly
6. **Guided/zero-shot topics** -- can seed with known correction categories
7. **Dynamic topic modeling** -- track how correction patterns evolve over time

**Integration approach:**
1. Collect correction messages from tier-2/tier-3 scoring
2. Feed to BERTopic as documents
3. Get automatic clusters with labels
4. Output: "Your top 5 correction patterns: file handling (23%), test approach (18%), ..."

**Minimum data:** Recommend 50+ correction examples for meaningful clusters. For fewer, use guided topic modeling with seed topics.

### BERTopic vs Top2Vec

Top2Vec (https://github.com/ddangelov/Top2Vec) was considered but BERTopic outperforms it by 34%+ on clustering quality (per published comparison at link.springer.com/chapter/10.1007/978-981-99-9109-9_37). BERTopic also has better modularity, active maintenance, and LLM-based labeling support.

### HDBSCAN Details

- **License:** BSD-3-Clause
- **Tier:** T1/T2 (peer-reviewed algorithm)
- Best clustering algorithm for this use case: does not require pre-specifying cluster count, handles noise natively, finds clusters of varying density
- Key parameter: `min_cluster_size` determines minimum cluster membership. Start with 5-10 for our expected data volumes.

---

## 3. Embedding Models for Short Conversation Turns

For embedding individual conversation turns (typically 1-5 sentences), the following models were evaluated:

| Model | Dims | Speed (ms/1K tokens) | MTEB Accuracy | License | Best For |
|-------|------|---------------------|---------------|---------|----------|
| `all-MiniLM-L6-v2` | 384 | 14.7 (fastest) | ~78% | Apache-2.0 | Quick local analysis, CPU-friendly, BERTopic default |
| `e5-base-v2` | 768 | 79 | ~84% | MIT | Balanced, no prefix prompts needed |
| `BGE-base-v1.5` | 768 | ~80 | ~85% | MIT | Best accuracy in size class |
| `nomic-embed-text-v1` | 768 | ~80 | ~83% | Apache-2.0 | Long context (8192 tokens), fully reproducible |
| `nomic-embed-text-v2-moe` | 768 | ~80 | Higher | Apache-2.0 | MoE, multilingual, flexible dims (768-256) |

**Recommendation:** Start with `all-MiniLM-L6-v2` -- it is BERTopic's default, fastest on CPU, and good enough for clustering short correction messages. If quality becomes an issue, upgrade to `nomic-embed-text-v1` (fully open source, long context support, Apache-2.0).

All models are available via `sentence-transformers` library and run locally without API calls.

---

## 4. Interactive Exploration Tools

### Option A: Renumics Spotlight (RECOMMENDED for standalone UI)

- **URL:** https://github.com/Renumics/spotlight
- **Tier:** T5 (maintained, active)
- **License:** MIT
- **Stars:** 1.3k
- **Last update:** March 2026 (v1.7.3)
- **Python:** 3.9-3.13
- **Dependencies:** pandas, datasets, React/TypeScript frontend

**Why Spotlight:** Purpose-built for interactive exploration of unstructured data with embeddings. Feed a DataFrame with text, embeddings, and metadata -> get a browser-based visualization with:
- Similarity maps (2D embedding projections)
- Filterable, sortable data tables
- Drill-down into individual data points
- Custom layouts for debugging workflows

**Integration:** After BERTopic clusters corrections, load results into Spotlight:
```python
from renumics import spotlight
spotlight.show(corrections_df, dtype={"embedding": spotlight.Embedding})
```

### Option B: Marimo + Plotly (RECOMMENDED for notebook-based exploration)

- **URL:** https://github.com/marimo-team/marimo
- **Tier:** T5 (very active, well-maintained)
- **License:** Apache-2.0
- **Stars:** 10k+
- **Last update:** Active (2026)
- **Python:** 3.9+

**Why Marimo:** Next-generation reactive Python notebook. Key advantages:
- Reactive cells: change a filter -> visualization updates automatically
- Built-in interactive widgets (sliders, dropdowns, selectable plots)
- Stored as pure Python (Git-friendly, no JSON notebooks)
- Supports Plotly for interactive scatter plots of UMAP projections
- Can be deployed as a web app for sharing
- DuckDB/SQL integration for querying correction data

**Integration:** Build the entire audit exploration as a marimo notebook:
1. Load session data
2. Show correction timeline with quality scores
3. Interactive UMAP scatter plot colored by cluster
4. Drill-down table filtered by selected cluster
5. Correction detail view

### Option C: UMAP + Plotly (Lightweight DIY)

- **URL:** https://plotly.com/python/t-sne-and-umap-projections/
- **Tier:** T1 (official Plotly docs)
- **License:** MIT (both umap-learn and plotly)
- Minimal code (~20 lines) for a 2D scatter with hover text
- Good enough for an MVP; upgrade to Spotlight or Marimo later

### Not Recommended

| Tool | Why Not |
|------|---------|
| Lilac (Databricks) | Archived July 2025, no longer maintained |
| Nomic Atlas (cloud) | Cloud-only, we need local capability |
| TensorBoard Projector | Dated, limited interactivity for text |

---

## 5. Evaluation Metrics (DeepEval)

### DeepEval

- **URL:** https://github.com/confident-ai/deepeval
- **Tier:** T5 (very active community repo)
- **License:** Open source (see LICENSE.md)
- **Stars:** 14.7k
- **Tests:** Yes (pre-commit + CI)
- **Python:** 3.9+
- **Dependencies:** Poetry-managed; integrates with OpenAI, Anthropic, LangChain

**Why DeepEval:** Has purpose-built conversational evaluation metrics:

| Metric | What It Measures | Relevance to Audit |
|--------|-----------------|-------------------|
| **Knowledge Retention** | Factual consistency across turns | Did agent lose context mid-session? |
| **Conversation Completeness** | Whether agent satisfies user needs | Did the session achieve its goal? |
| **Turn Relevancy** | Response consistency across turns | Did agent go off-topic? |
| **Turn Faithfulness** | Factual grounding in context | Did agent hallucinate? |
| **Role Adherence** | Persona consistency | Did agent stay in its assigned role? |

**Integration approach:** Feed session turns as `ConversationalTestCase` objects, get structured quality scores. These metrics can augment (or replace) hand-coded scoring in the audit pipeline. DeepEval's LLM-as-judge runs locally via its own evaluation pipeline.

**Risk:** Heavy dependency. Needs LLM API access for judge-based metrics. Consider using it as a reference for metric design rather than a hard dependency if we want to keep the audit workflow lightweight.

---

## 6. Data Quality Tools

### Cleanlab

- **URL:** https://github.com/cleanlab/cleanlab
- **Tier:** T5 (well-maintained, research-backed)
- **License:** Apache-2.0
- **Stars:** 11.4k
- **Last update:** January 2026 (v2.9.0)
- **Python:** 3.10+
- **Tests:** Yes (CI configured)

**Why Cleanlab:** After auto-classifying corrections (via tier-2 NLI), Cleanlab can find misclassified examples using its "confident learning" algorithm. It assigns a label quality score (0-1) to each example, flagging likely errors.

**Integration approach:**
1. Run tier-2 NLI classification on all flagged turns
2. Feed classifications + model confidence to Cleanlab
3. Cleanlab identifies turns that are probably misclassified
4. These become candidates for human review (active learning loop)

This is especially valuable because zero-shot NLI has ~15-30% error rate -- Cleanlab helps catch the worst misclassifications without requiring human review of every turn.

---

## 7. Related Projects & Prior Art

### LMSYS FastChat / Chatbot Arena

- **URL:** https://github.com/lm-sys/FastChat
- **License:** Apache-2.0
- **Stars:** 37k+
- **Relevance:** Their pairwise comparison methodology (Bradley-Terry model) and 1M conversation dataset provide templates for conversation quality analysis. Their data format (multi-turn conversations with metadata) is a useful reference for our session log schema.
- **How it informs us:** Adopt their conversation data format conventions. Their approach to measuring "which response was preferred" maps to our "did the user correct this?"

### AgentBench (THUDM)

- **URL:** https://github.com/THUDM/AgentBench
- **License:** Apache-2.0
- **Stars:** 3.3k
- **Relevance:** ICLR'24 paper benchmarking LLMs as agents across 8 environments. Their evaluation taxonomy is directly relevant:
  1. Can the agent understand user intent?
  2. Can it select the appropriate tool?
  3. Can it generate correct parameters?
  4. Does it complete the task?
- **Risk:** No CI. Designed for benchmarking, not retrospective analysis. Use as conceptual framework, not library.

### Amazon Multi-Layer Agent Evaluation

- **URL:** https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/
- **Tier:** T3 (official Amazon/AWS)
- **Relevance:** Three-layer evaluation framework maps to our audit phases:
  1. **Component level:** Intent detection, tool selection correctness
  2. **Agent level:** Reasoning quality, response quality
  3. **End-to-end level:** Task completion, user satisfaction

### Agent-Sentry (Intent Alignment)

- **URL:** https://arxiv.org/html/2603.22868
- **Tier:** T2 (academic preprint, 2026)
- **Relevance:** Introduces "intent-alignment check" -- verifying whether an agent's action is consistent with the user's original request. Uses execution provenance tracking. Conceptual framework for measuring "did the agent stay on task?"

### RLHFlow RLHF-Reward-Modeling

- **URL:** https://github.com/RLHFlow/RLHF-Reward-Modeling
- **Tier:** T4 (accompanies published papers)
- **Relevance:** Tools for training reward/preference models. The concept of learning from preference data (chosen vs rejected responses) maps to learning from corrections (user's correction = rejected agent behavior, user's preferred behavior = chosen).
- **Risk:** Overkill for our scope. Useful as conceptual inspiration, not as a dependency.

---

## 8. Creative / Outside-the-Box Ideas

### Idea A: Active Learning Annotation Loop

Use corrections as a self-improving feedback mechanism:
1. Run tier-1+2 scoring to find candidate corrections
2. Present the most uncertain ones to the user in a simple UI
3. User labels 20-50 examples as "real correction" / "not a correction" / correction type
4. Use Cleanlab to find label errors in the auto-classified data
5. Retrain or update classification thresholds based on user feedback

This creates a personalized correction detector that improves over time. Label Studio (https://github.com/HumanSignal/label-studio, Apache-2.0, 20k+ stars) provides a full annotation platform, but a simpler marimo-based widget may suffice.

### Idea B: Correction-to-Rule Pipeline

Close the loop from observation to workflow improvement:
1. Cluster corrections by type (BERTopic)
2. For each cluster, use LLM-as-judge to suggest workflow rule changes
3. Example: "Based on these 15 corrections about file handling, consider adding this guardrail rule: 'Always verify file exists before editing'"
4. Human reviews and approves suggested rules
5. Rules are written to `global/rules.yaml` or workflow phase definitions

### Idea C: Session Timeline Visualization

Build a timeline view of each session showing:
- Agent actions (tool calls, file edits) as events on a timeline
- User interventions (corrections, redirects) highlighted in red/orange
- Quality scores per turn (color gradient)
- Correction clusters color-coded
- Clickable drill-down to individual turns

Could be implemented as a Panel/HoloViz dashboard (https://github.com/holoviz/panel, BSD-3, 4.7k stars) or a marimo notebook.

### Idea D: Embedding Drift Detection

Track how the agent's responses drift from the user's intent over a session:
1. Embed user's initial request
2. Embed each agent response
3. Plot cosine similarity over time
4. Corrections should show as "dips" where the agent drifted, followed by "recovery"
5. Sessions with many dips = systematic alignment issues

---

## 9. Recommended Implementation Stack

| Layer | Tool | License | Rationale |
|-------|------|---------|-----------|
| Tier-1 scoring | Existing regex (`mine_patterns.py`) | N/A | Already built, fast, high recall |
| Tier-2 scoring | `deberta-v3-base-zeroshot-v2.0` via `transformers` | MIT | Zero-shot, no training, runs locally |
| Tier-3 scoring | Claude API (LLM-as-judge) | N/A | Best accuracy, structured output |
| Embeddings | `all-MiniLM-L6-v2` (default) or `nomic-embed-text-v1` (upgrade) | Apache-2.0 | Fast, good quality for short text |
| Clustering | BERTopic (HDBSCAN + c-TF-IDF) | MIT | Best topic modeling, auto-labels |
| Cluster labeling | BERTopic + Claude representation model | MIT | Human-readable pattern names |
| Interactive exploration | Renumics Spotlight or Marimo + Plotly | MIT / Apache-2.0 | Local, interactive, Python-native |
| Data quality | Cleanlab | Apache-2.0 | Find misclassified corrections |
| Evaluation metrics | DeepEval (reference) | Open source | Pre-built conversation quality scoring |

### Key Dependencies (all pixi-compatible)

```
transformers
sentence-transformers
bertopic
hdbscan
umap-learn
plotly
renumics-spotlight  # or marimo
cleanlab
deepeval  # optional, for evaluation metrics
```

### Domain Validation Required

- The zero-shot NLI classification labels need validation against a manually-labeled sample of real session corrections before production use. Label wording significantly affects accuracy.
- BERTopic cluster quality depends on having enough data points (50+ correction examples recommended) and appropriate `min_cluster_size` tuning.
- LLM-as-judge prompts need iterative refinement to avoid preference leakage when evaluating sessions from the same model family.

---

## 10. Sources

- DeepEval: https://github.com/confident-ai/deepeval
- BERTopic: https://github.com/MaartenGr/BERTopic
- BERTopic clustering docs: https://maartengr.github.io/BERTopic/getting_started/clustering/clustering.html
- DeBERTa zero-shot: https://huggingface.co/MoritzLaurer/deberta-v3-base-zeroshot-v2.0
- Cleanlab: https://github.com/cleanlab/cleanlab
- Renumics Spotlight: https://github.com/Renumics/spotlight
- Marimo: https://github.com/marimo-team/marimo
- Langfuse: https://github.com/langfuse/langfuse
- LMSYS FastChat: https://github.com/lm-sys/FastChat
- AgentBench: https://github.com/THUDM/AgentBench
- Agent-Sentry: https://arxiv.org/html/2603.22868
- Amazon agent evaluation: https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon/
- LLM-as-judge survey: https://arxiv.org/html/2412.05579v2
- Evidently AI LLM-as-judge guide: https://www.evidentlyai.com/llm-guide/llm-as-a-judge
- Nomic Embed: https://huggingface.co/nomic-ai/nomic-embed-text-v1
- Embedding model benchmarks: https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models
- Label Studio: https://github.com/HumanSignal/label-studio
- UMAP + Plotly: https://plotly.com/python/t-sne-and-umap-projections/
- Act2P dialogue act classification: https://aclanthology.org/2025.findings-acl.1052.pdf
- RLHFlow: https://github.com/RLHFlow/RLHF-Reward-Modeling
- Panel/HoloViz: https://github.com/holoviz/panel

---

## ADDENDUM: Architecture Correction -- Removing the Regex Ceiling

**Date:** 2026-04-13
**Triggered by:** User feedback that cascading tier-1 regex as gatekeeper creates a recall ceiling. If regex misses a correction, tiers 2 and 3 never see it. This defeats the purpose of multi-tier scoring.

**Verdict: The user is correct.** The cascade architecture is flawed. This section presents revised architectures and the performance data that makes them feasible.

---

### A1. Can NLI Run on ALL Turns? (Yes -- and it should)

The critical question: is running zero-shot classification on every turn (not just regex-flagged ones) feasible for 50-500 user turns?

#### The DeBERTa NLI Cost Problem

Traditional NLI-based zero-shot classification (DeBERTa cross-encoder approach) requires **one forward pass per candidate label per sample**. With 5 correction-type labels, that means 5 forward passes per turn. For 500 turns, that is 2,500 forward passes.

DeBERTa-base inference on CPU: ~30ms per forward pass (per HuggingFace forum benchmarks on A10 GPU; CPU is slower, ~50-100ms depending on hardware and sequence length).

**Worst case for DeBERTa NLI on 500 turns with 5 labels:**
- 500 turns x 5 labels x 100ms/pass (CPU) = **250 seconds (~4 minutes)**
- 500 turns x 5 labels x 30ms/pass (GPU) = **75 seconds (~1.25 minutes)**

This is tolerable for an offline audit but not ideal. However, there is a much better option.

#### GLiClass: The Game Changer (REVISED RECOMMENDATION)

GLiClass (https://github.com/Knowledgator/GLiClass) is a newer architecture that processes **all labels in a single forward pass** -- not one pass per label like DeBERTa cross-encoder NLI.

- **URL:** https://github.com/Knowledgator/GLiClass
- **Tier:** T4/T5 (accompanies arxiv paper, active development)
- **License:** Apache-2.0
- **Stars:** 208 (newer project, but backed by Knowledgator with published research)
- **Tests:** Yes (`test_gliclass.py`)
- **Install:** `pip install gliclass`
- **Paper:** https://arxiv.org/html/2508.07662v1

**Key performance data:**

| Metric | DeBERTa-v3-Large (cross-encoder) | GLiClass-v3 (uni-encoder) |
|--------|----------------------------------|---------------------------|
| Forward passes per sample | 1 per label (N passes for N labels) | 1 total (all labels) |
| Throughput at 128 labels | 0.25 examples/sec | 82.6 examples/sec |
| Speed vs DeBERTa | Baseline | **Up to 50x faster** |
| Throughput drop 1->128 labels | ~50x slower | Only 7-20% slower |
| F1 accuracy (zero-shot) | 0.6821 | 0.7193 (+5.5%) |
| Model size (base) | 184M params | 151M params |
| Context length | 512 tokens | **8192 tokens** (ModernBERT) |

**Estimated time for 500 turns with GLiClass on CPU:**
- Single forward pass per turn (all labels at once)
- Optimized BERT-class model on CPU: ~10-50ms per inference (based on ONNX-optimized BERT-class benchmarks achieving p50 of 9ms, p99 of <50ms)
- **500 turns x ~30ms = ~15 seconds** (conservative estimate)
- With batching (batch_size=32): potentially **5-10 seconds**

This makes running on ALL turns completely feasible, even on CPU, even without GPU.

#### Model Variants

| Model | Params | Best For |
|-------|--------|----------|
| `gliclass-modern-base-v3.0` | 151M | Best balance of speed/accuracy, ModernBERT backbone |
| `gliclass-modern-large-v2.0` | 399M | Higher accuracy when GPU available |
| `gliclass-edge-v3.0` | Small | Edge/constrained environments |
| `gliclass-base-v3.0` | 186M | DeBERTa backbone variant |

**Recommendation:** Use `gliclass-modern-base-v3.0` (ModernBERT backbone, 151M params, Apache-2.0). It is faster than DeBERTa, more accurate, and handles all labels in one pass.

---

### A2. Revised Architecture Options

Given that NLI can feasibly run on all turns, here are four alternative architectures that eliminate the regex recall ceiling:

#### Option 1: PARALLEL (Recommended)

```
All user turns
  |
  +--> Regex patterns (fast, ~0ms) ---------> regex_flags
  |                                              |
  +--> GLiClass NLI (all turns, ~15s) -------> nli_scores
  |                                              |
  v                                              v
  UNION: turn is flagged if regex OR nli detects it
  |
  v
  Tier 3: LLM-as-judge (on union of flagged turns)
```

**Pros:**
- Regex catches keyword-obvious corrections ("no", "wrong", "stop")
- NLI catches subtle corrections regex misses ("I was thinking more along the lines of...", "Actually, let me reconsider the approach")
- Union of both maximizes recall
- Both run independently -- can run in parallel
- Regex results become a feature/signal that boosts NLI confidence

**Cons:**
- Slightly more total compute than cascade (but ~15s for NLI on 500 turns is negligible)
- May flag more false positives (union is broader), but tier-3 LLM-as-judge filters those

**This is the recommended architecture.** It preserves regex's speed advantage for obvious patterns while eliminating its role as a recall ceiling.

#### Option 2: NLI-FIRST

```
All user turns
  |
  v
  GLiClass NLI (all turns) --> correction_scores per turn
  |
  +--> Regex patterns run as FEATURES (not gates)
  |    (regex match = +0.2 confidence boost to NLI score)
  |
  v
  Combined score = nli_score + regex_bonus
  |
  v
  Threshold filter (score > 0.5 = candidate correction)
  |
  v
  Tier 3: LLM-as-judge (on candidates above threshold)
```

**Pros:**
- NLI sees everything -- zero recall ceiling
- Regex adds signal without gatekeeping
- Single scoring pathway (simpler to reason about)
- Threshold is tunable

**Cons:**
- Regex becomes a secondary signal rather than a first-class detector
- Slightly more complex scoring logic (combining signals)

#### Option 3: EMBEDDING-FIRST

```
All user turns
  |
  v
  Embed all turns (all-MiniLM-L6-v2, ~5s for 500 turns)
  |
  v
  Cluster with HDBSCAN (find natural groupings)
  |
  v
  Classify CLUSTERS (not individual turns):
    - GLiClass NLI on cluster centroids/representatives
    - Regex patterns on cluster keywords
    - LLM-as-judge on ambiguous clusters
  |
  v
  All turns in "correction clusters" are flagged
```

**Pros:**
- Embedding is extremely fast (~10ms per turn for MiniLM)
- Clustering finds patterns humans would miss
- Classification cost scales with number of clusters (5-15), not number of turns (500)
- Natural integration with BERTopic exploration

**Cons:**
- Requires enough turns for meaningful clusters (works better at 100+ turns)
- Individual corrections that do not cluster (outliers) may be missed by HDBSCAN (assigned to noise cluster -1)
- Need a fallback for outlier/noise turns (could run NLI on noise cluster)
- More complex pipeline

#### Option 4: HYBRID EMBEDDING + NLI

```
All user turns
  |
  v
  Embed all turns (fast, ~5s)
  |
  +--> GLiClass NLI on all turns (parallel, ~15s)
  |
  v
  Combine: each turn has [embedding_vector, nli_scores, regex_flags]
  |
  v
  BERTopic clustering uses combined features
  |
  v
  Clusters are auto-labeled with correction types
  |
  v
  Tier 3: LLM-as-judge on cluster representatives + high-score individuals
```

**Pros:**
- Richest feature set for clustering (embeddings + NLI scores + regex)
- No recall ceiling at any stage
- Clusters informed by both semantics and classification scores
- Best exploration experience

**Cons:**
- Most complex pipeline
- May be overengineered for MVP

---

### A3. Performance Estimates: DeBERTa NLI vs GLiClass on Full Turn Sets

Based on published benchmarks and inference optimization research:

#### CPU Performance (no GPU)

| Scenario | DeBERTa NLI (5 labels) | GLiClass (5 labels) | Embedding (MiniLM) |
|----------|----------------------|--------------------|--------------------|
| 50 turns | ~25s | ~1.5s | ~0.5s |
| 100 turns | ~50s | ~3s | ~1s |
| 200 turns | ~100s | ~6s | ~2s |
| 500 turns | ~250s | ~15s | ~5s |

*DeBERTa estimates: 5 labels x ~100ms/pass x N turns. GLiClass estimates: 1 pass x ~30ms x N turns. MiniLM: ~10ms/turn.*

#### With ONNX Optimization on CPU

ONNX Runtime with quantization achieves 2-5x speedup over vanilla PyTorch for BERT-class models (source: getstream.io benchmark achieving p50=9ms for optimized DistilBERT):

| Scenario | GLiClass + ONNX | Embedding + ONNX |
|----------|----------------|-----------------|
| 50 turns | ~0.5-1s | ~0.2s |
| 100 turns | ~1-2s | ~0.5s |
| 500 turns | ~5-8s | ~2s |

#### With GPU (if available)

| Scenario | GLiClass (batch=32) | Embedding (batch=32) |
|----------|--------------------|--------------------|
| 500 turns | ~2-3s | ~1s |

**Bottom line:** GLiClass on all 500 turns takes ~15 seconds on CPU without optimization. This is fast enough to make the cascade architecture unnecessary. With ONNX optimization, it drops to ~5-8 seconds. There is no performance reason to gate on regex.

#### Batching Details

The HuggingFace `pipeline` API supports `batch_size` parameter. For GLiClass, the dedicated `ZeroShotClassificationPipeline` handles batching natively. Key considerations:
- On CPU, batch_size > 1 may not help much (CPU parallelism is limited)
- On GPU, batch_size=32 is a good default
- GLiClass's uni-encoder architecture means batching is straightforward (no cross-product of texts x labels)

---

### A4. Does Removing the Cascade Improve BERTopic Clustering?

**Yes, significantly.** Here is why:

#### With cascade (old architecture)
- BERTopic only sees turns that regex flagged
- If regex catches 60% of actual corrections, clustering operates on a biased subset
- Clusters reflect "things regex can catch" not "things the user actually corrects"
- Subtle correction patterns (polite redirects, implicit disagreements) are systematically excluded
- Cluster labels are skewed toward regex-obvious patterns

#### Without cascade (NLI on all turns)
- BERTopic sees ALL corrections, including subtle ones
- Clusters reflect the true distribution of user correction behavior
- New pattern types emerge that regex would never find:
  - "Polite redirects" -- "Maybe we should try a different approach"
  - "Implicit corrections" -- User re-explains the same requirement differently
  - "Escalating frustration" -- Repeated similar requests with increasing directness
  - "Style preferences" -- "Can you be more concise?" / "Show me the code"
- Cluster quality improves because more data points means better density estimation for HDBSCAN
- Outlier detection (HDBSCAN noise cluster) becomes meaningful -- true one-off corrections vs systematic patterns

#### Embedding-first is especially good for clustering

If we embed ALL turns (not just corrections), we can use BERTopic in a richer way:
1. Cluster all turns to understand session structure
2. Overlay NLI correction scores as a heatmap on the cluster map
3. "Correction-heavy clusters" emerge naturally -- these are the problem areas
4. Non-correction clusters provide context (what the agent does well)

This gives users a holistic view: not just "here is what went wrong" but "here is the full landscape of your interactions, with problem areas highlighted."

---

### A5. Revised Recommendation

**Replace the cascading architecture with Option 1 (PARALLEL) for the MVP:**

```
All user turns
  |
  +--[parallel]---> Regex patterns ----------> regex_flags (per turn)
  |
  +--[parallel]---> GLiClass NLI (all turns) -> nli_scores (per turn)
  |
  +--[parallel]---> Embed all turns ----------> embeddings (per turn)
  |
  v
  Merge: each turn has {text, regex_flags, nli_scores, embedding}
  |
  v
  Flag corrections: nli_score > threshold OR regex_flag == True
  |
  v
  BERTopic clustering on flagged corrections (using pre-computed embeddings)
  |
  v
  Tier 3: LLM-as-judge on cluster representatives
  |
  v
  Output: correction patterns with labels, counts, examples, and suggestions
```

**Why this works:**
- All three signals (regex, NLI, embedding) computed in parallel on all turns
- Total wall time on CPU: ~15-20 seconds for 500 turns (dominated by GLiClass)
- No recall ceiling -- NLI catches what regex misses
- Regex still adds value as a cheap high-confidence signal
- Pre-computed embeddings feed directly to BERTopic (no recomputation)
- LLM-as-judge only runs on cluster representatives (~5-15 calls), keeping costs low

**Key dependency change:** Replace `deberta-v3-base-zeroshot-v2.0` with `gliclass-modern-base-v3.0` (GLiClass). Same accuracy or better, 10-50x faster, single forward pass for all labels. Install: `pip install gliclass`.

---

### A6. Updated Dependency List

```
# Core classification (CHANGED from transformers DeBERTa)
gliclass                    # GLiClass zero-shot classifier (Apache-2.0)
torch                       # PyTorch backend

# Embeddings and clustering (unchanged)
sentence-transformers       # Embedding models
bertopic                    # Topic modeling pipeline
hdbscan                     # Density-based clustering
umap-learn                  # Dimensionality reduction

# Visualization (unchanged)
plotly                      # Interactive plots
renumics-spotlight          # or marimo for notebook exploration

# Data quality (unchanged)
cleanlab                    # Find misclassified corrections

# Optional optimization
onnxruntime                 # 2-5x CPU speedup via ONNX export
```

### A7. Sources for This Addendum

- GLiClass repo: https://github.com/Knowledgator/GLiClass
- GLiClass paper: https://arxiv.org/html/2508.07662v1
- GLiClass ModernBERT blog: https://huggingface.co/blog/Ihor/refreshing-zero-shot-classification
- GLiClass v3 announcement: https://x.com/gm8xx8/status/1948088533618487440
- GLiClass models: https://huggingface.co/knowledgator/gliclass-modern-base-v3.0
- DeBERTa batch latency discussion: https://discuss.huggingface.co/t/what-is-the-latency-expectation-of-deberta-when-doing-batch-inference/45057
- Transformer inference optimization to 9ms: https://getstream.io/blog/optimize-transformer-inference/
- HuggingFace pipeline batching: https://huggingface.co/docs/transformers/en/main_classes/pipelines
- Zero-shot NLI forward pass cost: https://jaketae.github.io/study/zero-shot-classification/
- HuggingFace zero-shot batching issue: https://github.com/huggingface/transformers/issues/24005
- Text clustering with embeddings: https://arxiv.org/html/2403.15112v1
- BERT CPU scaling: https://huggingface.co/blog/bert-cpu-scaling-part-1

---

## ADDENDUM 2: Real-World Volume Calibration

**Date:** 2026-04-13
**Triggered by:** Actual session data from the user's projects.

### B1. Real Volume Data

| Scope | Sessions | User Turns | Turns/Day |
|-------|----------|------------|-----------|
| This project | 75 | 4,044 | ~1,300 |
| All projects | 124 | 5,601 | -- |
| Today alone | 21 | 1,042 | 1,042 |

The previous estimates of "50-500 turns" were based on a single audit run. Real usage is **~1,300 turns/day** for active development on a single project, and **~4,000 turns** for a full project history audit.

### B2. Revised Performance Table (Real Volumes)

All estimates assume CPU-only, no ONNX optimization, unbatched (worst case):

| Volume | Regex | DeBERTa NLI (5 labels) | GLiClass (5 labels) | MiniLM Embedding |
|--------|-------|----------------------|--------------------|--------------------|
| 1,042 turns (1 day) | <1s | ~8.7 min | ~31s | ~10s |
| 1,300 turns (busy day) | <1s | ~10.8 min | ~39s | ~13s |
| 4,044 turns (full project) | <1s | ~33.7 min | ~2 min | ~40s |
| 5,601 turns (all projects) | <1s | ~46.7 min | ~2.8 min | ~56s |

*DeBERTa: 5 labels x 100ms x N. GLiClass: 30ms x N. MiniLM: 10ms x N.*

With batching on CPU (conservative 2x speedup):

| Volume | DeBERTa NLI batched | GLiClass batched | MiniLM batched |
|--------|-------------------|-----------------|----------------|
| 1,042 turns | ~4.3 min | ~16s | ~5s |
| 1,300 turns | ~5.4 min | ~20s | ~7s |
| 4,044 turns | ~16.9 min | ~1 min | ~20s |
| 5,601 turns | ~23.3 min | ~1.4 min | ~28s |

With ONNX optimization + batching (3-5x over vanilla):

| Volume | GLiClass + ONNX | MiniLM + ONNX |
|--------|----------------|---------------|
| 1,300 turns | ~8-13s | ~3-4s |
| 4,044 turns | ~24-40s | ~8-13s |
| 5,601 turns | ~34-56s | ~11-19s |

### B3. Verdict: Cascade is Unnecessary at Every Volume

Even the **worst case** -- DeBERTa NLI unbatched on 1,300 turns -- is ~11 minutes. For an offline audit that a user runs once per day or per project review, this is acceptable.

But with GLiClass:
- **Daily audit (1,300 turns): ~20 seconds** unbatched, ~10 seconds with ONNX
- **Full project audit (4,044 turns): ~1 minute** unbatched, ~30 seconds with ONNX
- **All projects (5,601 turns): ~1.4 minutes** unbatched, ~45 seconds with ONNX

**There is zero performance justification for a regex gatekeeper at these volumes.** The parallel architecture (regex + NLI + embedding, all on all turns) is the correct design.

Even DeBERTa is viable if GLiClass proves unsuitable for any reason -- ~5 minutes batched for a daily audit is still acceptable for an offline tool. But GLiClass is the clear winner.

### B4. Architecture Implications of Real Volumes

The real data changes several design assumptions:

**1. BERTopic clustering gets MUCH better with 1,000+ turns.**
The earlier concern about "need 50+ corrections for meaningful clusters" is moot. At 4,044 turns, even if only 10% are corrections, that is ~400 corrections -- more than enough for rich clustering with HDBSCAN. Expect 10-30 meaningful clusters to emerge.

**2. Full-project audit is the high-value use case.**
A single day's audit (1,042 turns) reveals acute issues. A full-project audit (4,044 turns) reveals **systematic patterns** -- recurring correction types, phase-specific problems, drift over time. The full-project audit is where BERTopic's dynamic topic modeling (tracking clusters over time) becomes powerful.

**3. Embeddings are the cheapest signal and should always run.**
At ~10ms/turn, embedding all 4,044 turns takes ~40 seconds. These embeddings are reusable:
- Feed to BERTopic for clustering
- Feed to Spotlight/Marimo for interactive exploration
- Use for similarity search ("find turns similar to this correction")
- Use for drift detection (cosine similarity over time)
Pre-computing embeddings for all turns is a no-brainer at this cost.

**4. LLM-as-judge tier scales well.**
If BERTopic produces ~15 clusters from 400 corrections, tier-3 LLM-as-judge only needs ~15-30 API calls (1-2 per cluster for representative analysis). This is trivial cost and latency regardless of total turn volume.

### B5. Final Recommended Architecture (Calibrated to Real Data)

```
All user turns (1,000-5,600 per audit run)
  |
  +--[parallel, <1s]--> Regex patterns ---------> regex_flags[]
  |
  +--[parallel, ~20s]-> GLiClass NLI (all) -----> nli_scores[]
  |
  +--[parallel, ~13s]-> MiniLM embed (all) ------> embeddings[]
  |
  v  (~20s wall time, dominated by GLiClass)
  |
  Merge: each turn = {text, regex_flags, nli_scores, embedding}
  |
  v
  Flag corrections: nli_score > threshold OR regex_match
  (expect ~10-20% of turns = 100-800 corrections)
  |
  v
  BERTopic on flagged corrections (using pre-computed embeddings)
  --> 10-30 clusters with auto-generated labels
  |
  v
  LLM-as-judge on cluster representatives (~15-30 API calls)
  --> structured analysis: correction type, severity, root cause
  |
  v
  Output: ranked correction patterns with examples and suggestions
  Total pipeline time: ~30-60 seconds (CPU) for full project audit
```

**This is an offline audit tool, not a real-time system.** A 30-60 second pipeline for comprehensive analysis of 4,000+ turns is excellent UX. The user kicks it off, gets a coffee, and comes back to a complete analysis.

### B6. Scaling Headroom

If usage grows beyond current volumes:

| Volume | GLiClass + ONNX | Total Pipeline |
|--------|----------------|---------------|
| 10,000 turns | ~1-2 min | ~2-3 min |
| 50,000 turns | ~5-8 min | ~10-15 min |
| 100,000 turns | ~10-17 min | ~20-30 min |

At 100K turns, consider chunked/incremental processing (only analyze turns since last audit). But even brute-force full re-analysis stays under 30 minutes, which is fine for an offline tool.

The parallel architecture scales linearly and has no architectural bottlenecks up to volumes far beyond what any individual developer would generate.

---

## ADDENDUM 3: Prior Art for Correction Detection & Label Taxonomy Design

**Date:** 2026-04-13
**Triggered by:** User questions: (1) Has zero-shot NLI actually been used for correction detection in human-AI dialogue? (2) How do we design the right classification labels?

---

### C1. Has NLI/Zero-Shot Been Used for Correction Detection in Human-AI Dialogue?

**Short answer: Yes, but the field is young and the best work uses LLM-as-classifier, not traditional NLI.** The most directly relevant research emerged in 2024-2025. No one has published work using GLiClass or DeBERTa NLI specifically for coding assistant correction detection. But closely adjacent work exists and provides strong foundations.

#### Most Relevant Paper: "User Feedback in Human-LLM Dialogues" (July 2025)

- **URL:** https://arxiv.org/html/2507.23158
- **Tier:** T2 (peer-reviewed, very recent)
- **Directly on-point:** Analyzes user feedback in conversations with ChatGPT and Chatbot Arena

This paper defines a **5-category taxonomy** for user feedback in LLM conversations:

| Category | Definition | Example Signal |
|----------|-----------|----------------|
| **Positive Feedback** | User praises the response | "Great job!", "That's exactly right" |
| **Rephrasing** | User rephrases their prior request to elicit a better response | Restating the same question differently |
| **Make Aware (no correction)** | User signals the response was wrong but does not provide fix | "That's not what I asked for" |
| **Make Aware (with correction)** | User signals wrong AND provides instruction on how to fix | "No, use X instead of Y" |
| **Ask for Clarification** | User asks for additional missing information | "Can you explain what you mean by...?" |

**Detection method:** GPT-4o-mini prompting with in-context examples. Achieved Cohen's kappa of 0.70 (binary), 0.74 (three-way), 0.60 (fine-grained).

**Key insight for us:** They tested at three granularity levels -- binary (feedback/none), three-way (positive/negative/none), and fine-grained (all 5 categories). **Binary detection was most reliable. Fine-grained was hardest.** This directly informs our label design.

**Dataset:** 109 conversations (443 user turns) from LMSYS-chat-1M and WildChat. Small but densely annotated.

#### Second Key Paper: WildFeedback (Microsoft Research, August 2024)

- **URL:** https://arxiv.org/html/2408.15549v3
- **Tier:** T3 (Microsoft Research, published with dataset)
- **License:** Dataset available

WildFeedback defines **18 rubrics** (9 satisfaction, 9 dissatisfaction) for classifying user feedback in real ChatGPT conversations:

**9 DSAT (Dissatisfaction) Rubrics -- directly relevant to correction detection:**

| DSAT Rubric | Definition | Maps to Our Use Case |
|-------------|-----------|---------------------|
| **Negative Feedback** | User explicitly expresses frustration, annoyance, or anger | General dissatisfaction signal |
| **Revision** | User asks agent to revise response OR repeatedly asks similar questions | Direct correction request |
| **Factual Error** | User points out factual mistakes, inaccuracies, or self-contradiction | Agent gave wrong information |
| **Unrealistic Expectation** | User does not accept agent's limitations | Scope mismatch |
| **No Engagement** | User does not respond to agent's questions or suggestions | Passive dissatisfaction |
| **Ignored** | User implies their query was ignored or response missed their intent | Intent misalignment |
| **Lower Quality** | User perceives decline compared to other agents | Comparative dissatisfaction |
| **Insufficient Detail** | User wants more specific/useful information | Depth mismatch |
| **Style** | User feels mismatch in style (bullet vs paragraph, formal vs casual) | Style preference correction |

**9 SAT (Satisfaction) Rubrics -- useful as negative signals (absence = potential issue):**

| SAT Rubric | Definition |
|------------|-----------|
| **Gratitude** | User thanks the agent |
| **Learning** | User indicates curiosity and satisfaction with information |
| **Compliance** | User follows agent's suggestions |
| **Praise** | User uses positive words (excellent, amazing) |
| **Personal Details** | User shares more personal context (sign of trust) |
| **Humor** | User jokes with agent in friendly manner |
| **Acknowledgment** | User confirms understanding or agreement |
| **Positive Closure** | User ends conversation on positive note |
| **Getting There** | User acknowledges merit but is not fully satisfied |

**Detection method:** GPT-4 classification at utterance level. Cohen's kappa: 0.69 (SAT), 0.50 (DSAT).

**Dataset:** WildFeedback dataset of 20,281 samples from WildChat corpus.

**Key insight:** DSAT detection is harder than SAT detection (kappa 0.50 vs 0.69). Dissatisfaction is often implicit.

#### Third Key Paper: SPUR -- Interpretable User Satisfaction Estimation (ACL 2024)

- **URL:** https://arxiv.org/abs/2403.12388
- **Tier:** T2 (ACL 2024, peer-reviewed)

SPUR uses LLMs to extract satisfaction signals, summarize reasons into rubrics, and apply rubrics to predict satisfaction. The key finding for us: "conversations where users explicitly correct a bot's mistakes can suggest examples for model alignment." They use 10 SAT and 10 DSAT rubrics (WildFeedback adapted from this work).

#### Fourth Key Paper: User Frustration Detection (COLING 2025)

- **URL:** https://aclanthology.org/2025.coling-industry.23.pdf
- **Tier:** T2 (COLING 2025 Industry Track)

Specifically addresses frustration detection in task-oriented dialog. Key insight: "frustration can be subtle and does not always involve negative language" -- it occurs when the system fails to help accomplish a task even without explicit complaints.

#### Follow-up Query Patterns (July 2024)

- **URL:** https://arxiv.org/html/2407.13166v1
- **Tier:** T2 (peer-reviewed)

Defines 18 follow-up query patterns (7 motivations x 11 actions). Dissatisfaction signals include:
- **Clarifying Queries** -- user rephrases to align with system
- **Excluding Condition** -- user removes constraints from previous query
- **Substituting Condition** -- user changes approach entirely
- **Criticizing Response** -- user points out inappropriate answers

---

### C2. Established Taxonomies for Dialogue Corrections and Repairs

#### ISO 24617-2 (International Standard for Dialogue Act Annotation)

- **Tier:** T1 (international standard, peer-reviewed)
- **URL:** https://www.iso.org/standard/51967.html

ISO 24617-2 defines 56 communicative functions across 9 dimensions. The correction-relevant functions:

| Function | Dimension | Definition |
|----------|----------|-----------|
| **Correction** | General-purpose | Speaker corrects information from a previous utterance |
| **Disagreement** | General-purpose | Speaker disagrees with content of previous utterance |
| **Disconfirm** | General-purpose | Speaker denies a proposition (stronger than disagreement) |
| **Negative Feedback (auto)** | Auto-Feedback | Speaker signals own processing difficulty |
| **Negative Feedback (allo)** | Allo-Feedback | Speaker signals partner's utterance caused difficulty |
| **Signal Non-Understanding** | Auto-Feedback | Speaker indicates failure to understand |

ISO 24617-2 also defines **5 levels of feedback processing:**

1. **Attention** -- did the listener attend to the utterance?
2. **Perception** -- did they perceive/hear it correctly?
3. **Interpretation** -- did they understand the meaning?
4. **Evaluation** -- do they agree/accept it?
5. **Execution** -- did they act on it?

**Relevance:** This hierarchy maps well to our use case. In a coding assistant context:
- Level 3 failure (interpretation) = agent misunderstood the task
- Level 4 failure (evaluation) = agent understood but chose wrong approach
- Level 5 failure (execution) = agent understood and chose correctly but implemented wrong

#### SWBD-DAMSL (Switchboard Dialogue Act Markup)

- **Tier:** T1/T2 (widely-used standard, Jurafsky et al.)
- **URL:** https://web.stanford.edu/~jurafsky/ws97/manual.august1.html

The SWBD-DAMSL tagset defines 42 dialogue act types. Correction-relevant tags:

| Tag | Name | Definition |
|-----|------|-----------|
| `bc` | **Correct-misspeaking** | Correction of error by other speaker |
| `ar` | **Reject** | Disagreement with previous proposal, opinion, or statement |
| `arp` | **Reject-part** | Partial rejection of a previous utterance |
| `br` | **Signal-non-understanding** | Request for repetition or clarification (next-turn-repair-initiator) |
| `bf` | **Summarize/reformulate** | Paraphrase of other's utterance to check understanding |
| `nd` | **Dispreferred answers** | Hedged negative response ("Well...") |
| `b^m` | **Repeat-phrase** | Recycling lexical material from other speaker |
| `^2` | **Collaborative Completion** | Completing another speaker's utterance |

#### Conversation Analysis Repair Taxonomy (Schegloff et al. 1977)

- **Tier:** T1 (foundational CA framework)

Four types of conversational repair:

| Type | Who Initiates | Who Repairs | In Human-AI Context |
|------|--------------|-------------|-------------------|
| Self-initiated self-repair (SISR) | Agent | Agent | Agent catches own mistake |
| Self-initiated other-repair (SIOR) | Agent | User | Agent asks user to fix (rare) |
| Other-initiated self-repair (OISR) | User | Agent | User flags problem, agent fixes |
| Other-initiated other-repair (OIOR) | User | User | User flags AND provides fix |

**For our audit workflow, we care about OISR and OIOR** -- cases where the user initiates repair. The distinction between "user flags problem" (OISR) and "user flags AND fixes" (OIOR) maps directly to WildFeedback's "Make Aware without Correction" vs "Make Aware with Correction."

#### Virtual Assistant Error Categories (Motta & Quaresma 2022)

- **Tier:** T2 (peer-reviewed, Frontiers in Robotics and AI)
- **URL:** https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2024.1356847/full

Eight error categories for virtual assistant failures:

| Category | Definition | Coding Assistant Equivalent |
|----------|-----------|---------------------------|
| **Different Task** | Assistant performs unintended activity | Wrong tool used, wrong file edited |
| **Wrong Information** | Incorrect details provided | Wrong API, wrong syntax, hallucinated function |
| **Input Failure** | No command captured | Agent didn't understand prompt |
| **Interruption** | Partial command capture | Agent acted on incomplete instruction |
| **Misrecognition** | Words misunderstood | Agent misinterpreted technical terms |
| **Request for Manual** | User must manually complete | Agent couldn't automate the task |
| **Error Messages** | Explicit error notification | Agent's code crashes |
| **Instructions** | Guidance on proceeding | Agent asks how to proceed after failure |

---

### C3. Label Design Recommendations for Our Audit Workflow

Based on ALL of the above research, here is the recommended label taxonomy. The design follows three principles from the literature:

**Principle 1: Start binary, then go granular** (from "User Feedback in Human-LLM Dialogues" -- binary detection is most reliable, kappa 0.70 vs 0.60 for fine-grained)

**Principle 2: Use 2-6 distinct labels per level** (from NLI best practices -- zero-shot accuracy degrades with too many labels)

**Principle 3: Phrase labels as natural language hypotheses** (from NLI methodology -- "This text is about {}" template)

#### Recommended Two-Level Classification

**Level 1: Binary Detection (run on ALL turns)**

Two hypotheses, high reliability:

```
HYPOTHESIS A: "The user is correcting, redirecting, or expressing dissatisfaction with the assistant's response"
HYPOTHESIS B: "The user is continuing the conversation normally or expressing satisfaction"
```

This catches everything -- explicit corrections, subtle redirects, frustration -- in a single binary pass. Based on WildFeedback's results, binary detection should achieve kappa ~0.70.

**Level 2: Correction Type Classification (run only on Level 1 positives)**

Six categories, informed by the convergence across WildFeedback, ISO 24617-2, SWBD-DAMSL, and the User Feedback paper:

| Label | NLI Hypothesis Phrasing | Source Basis |
|-------|------------------------|-------------|
| **Factual Correction** | "The user is pointing out a factual error, wrong information, or incorrect code in the assistant's response" | WildFeedback "Factual Error" + ISO "Correction" + Motta "Wrong Information" |
| **Approach Redirect** | "The user is asking the assistant to take a completely different approach or strategy" | WildFeedback "Revision" + SWBD "Reject" + CA "Other-initiated other-repair" |
| **Intent Clarification** | "The user is clarifying or re-explaining what they actually wanted because the assistant misunderstood" | WildFeedback "Ignored" + ISO "Signal Non-Understanding" + SWBD "Signal-non-understanding" |
| **Scope/Detail Adjustment** | "The user is asking for more detail, less detail, or a different scope than what the assistant provided" | WildFeedback "Insufficient Detail" + Follow-up "Narrowing Down" |
| **Style/Format Preference** | "The user is requesting a different style, format, or presentation of the response" | WildFeedback "Style" + Follow-up "Converting Format" |
| **Frustration/Escalation** | "The user is expressing frustration, impatience, or dissatisfaction with the assistant's overall performance" | WildFeedback "Negative Feedback" + COLING 2025 frustration detection |

**Why these 6 categories:**

1. They are the intersection of 4+ independent taxonomies (WildFeedback, ISO, SWBD-DAMSL, Motta). When multiple frameworks agree on a category, it reflects a real phenomenon.
2. They map to actionable workflow improvements:
   - Factual Correction -> improve knowledge/context rules
   - Approach Redirect -> improve planning/strategy rules
   - Intent Clarification -> improve requirement gathering phase
   - Scope/Detail -> improve output verbosity rules
   - Style/Format -> improve output formatting rules
   - Frustration -> systemic issue, review multiple factors
3. Six categories is within the 2-6 optimal range for zero-shot NLI accuracy.
4. The hypothesis phrasings are natural language sentences (not keywords), which is what NLI models expect.

#### Alternative: Coding-Assistant-Specific Labels

If the six general categories above are too broad, here is a coding-assistant-specific variant that maps to agent tool-use patterns:

| Label | Hypothesis | When Agent... |
|-------|-----------|--------------|
| **Wrong File/Target** | "The user is telling the assistant it edited the wrong file or targeted the wrong code" | Edited wrong file, wrong function |
| **Wrong Implementation** | "The user is telling the assistant the code it wrote is incorrect or has bugs" | Code is wrong, has errors |
| **Wrong Approach** | "The user is telling the assistant to use a different library, pattern, or architecture" | Chose wrong strategy |
| **Misunderstood Task** | "The user is re-explaining what they want because the assistant did the wrong thing entirely" | Misinterpreted the request |
| **Too Much/Too Little** | "The user is telling the assistant it did too much, too little, or the wrong scope of changes" | Over/under-scoped |
| **Process Complaint** | "The user is frustrated with the assistant's process, speed, or interaction style" | UX/workflow issue |

This variant has not been validated by prior research (no published taxonomy for coding assistants exists), but it is derived from the general categories by mapping them to coding-specific failure modes.

#### Label Phrasing Best Practices (from NLI literature)

1. **Use complete sentences as hypotheses**, not keywords. "The user is correcting an error" works better than "correction" or "error".
2. **Include both the actor and the action**. "The user is telling the assistant..." anchors the NLI model on who is doing what.
3. **Be specific enough to distinguish categories** but not so specific that you miss variants. "Wrong file" is too narrow; "factual error, wrong information, or incorrect code" covers more ground.
4. **Test alternative phrasings**. The template "This text is about {}" vs "The user is {}" vs "The speaker is expressing {}" can yield different accuracy. WildFeedback found utterance-level classification most effective.
5. **Use `multi_label=True`** for Level 2. A single turn can be BOTH a factual correction AND express frustration. The categories are not mutually exclusive.

---

### C4. Validation Strategy

The research consistently shows that **label design is the #1 factor in zero-shot accuracy**. Before deploying:

1. **Manually label 50-100 turns** from real sessions as ground truth
2. **Test multiple hypothesis phrasings** for each category and measure precision/recall
3. **Compare binary vs 6-class accuracy** -- if 6-class is too noisy, fall back to binary + LLM-as-judge for fine-grained
4. **Use Cleanlab** to identify systematic misclassifications and refine labels
5. **Consider the "Getting There" category** from WildFeedback -- turns where the user acknowledges partial correctness but wants changes. These are correction-adjacent and easy to miss.

The COLING 2025 frustration paper warns: "frustration can be subtle and does not always involve negative language." This means our Level 1 binary hypothesis must be broad enough to catch implicit dissatisfaction, not just explicit corrections.

---

### C5. Summary: What the Literature Tells Us

| Question | Answer |
|----------|--------|
| Has NLI been used for this? | Not NLI specifically, but LLM-as-classifier (GPT-4/4o-mini) has been validated on this exact task with kappa 0.60-0.74 |
| Do established taxonomies exist? | Yes: ISO 24617-2, SWBD-DAMSL, CA repair taxonomy, plus 3 recent LLM-specific papers |
| Is there a coding-assistant-specific taxonomy? | No. We would be the first. But we can derive one from general taxonomies. |
| What label granularity works best? | Binary first (highest reliability), then 5-6 fine-grained categories |
| How many labels for zero-shot NLI? | 2-6 optimal range. Our 6-category Level 2 is at the upper bound. |
| What phrasing works best? | Full natural language hypotheses with actor + action + context |
| Biggest risk? | Implicit dissatisfaction (no negative language). Must test on real data. |

---

### C6. Sources for This Addendum

- User Feedback in Human-LLM Dialogues: https://arxiv.org/html/2507.23158
- WildFeedback (Microsoft Research): https://arxiv.org/html/2408.15549v3
- SPUR User Satisfaction Estimation (ACL 2024): https://arxiv.org/abs/2403.12388
- User Frustration Detection (COLING 2025): https://aclanthology.org/2025.coling-industry.23.pdf
- Follow-up Query Taxonomy: https://arxiv.org/html/2407.13166v1
- ISO 24617-2 Standard: https://www.iso.org/standard/51967.html
- ISO 24617-2 Paper (LREC 2020): https://aclanthology.org/2020.lrec-1.69.pdf
- SWBD-DAMSL Coders Manual: https://web.stanford.edu/~jurafsky/ws97/manual.august1.html
- Virtual Assistant Repair Analysis: https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2024.1356847/full
- Schegloff et al. repair taxonomy: referenced via CA literature
- NLI Zero-Shot Best Practices: https://jaketae.github.io/study/zero-shot-classification/
- NLI Label Design Issues: https://aclanthology.org/2021.acl-short.99.pdf
