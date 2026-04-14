# Researcher Findings -- Multi-Agent Audit Pipeline Design

**Date:** 2026-04-13
**Context:** Architecture has shifted from GLiClass/NLI to LLM-as-primary-classifier. This report covers prompt design for classifier, judge, and critic agents, plus multi-agent evaluation pipeline patterns from the literature.

---

## 1. Best Prompts for LLM-as-Classifier in Dialogue

### 1.1 What the Literature Actually Uses

The most directly relevant paper is **"User Feedback in Human-LLM Dialogues"** (July 2025, arxiv.org/html/2507.23158v2). Their methodology:

- **Model:** GPT-4o-mini
- **Context:** Full conversation provided (not individual turns)
- **Output format:** JSON per turn
- **Categories:** NEG_1 (Rephrasing), NEG_2 (Make Aware), NEG_3 (Make Aware with Correction), NEG_4 (Ask for Clarification), POS (Positive), NEU (Neutral)
- **In-context examples:** Yes -- including examples significantly improved accuracy
- **Scope:** Classify all user turns after the first one

Their prompt structure (from Appendix H.2):
```
Given the full conversation between User and Assistant:
- For each user turn after the first, classify the feedback pattern
- Output JSON: {"User Response Pattern": "[category]", "User Response Text": "[text]"}
- For non-feedback turns: "User Response Pattern": "NEU"
```

**Accuracy results:**

| Setting | Binary (feedback/none) | Fine-grained (5 categories) |
|---------|----------------------|---------------------------|
| Sparse annotation | 81.1% | 60.2% precision, 47.4% recall |
| Dense annotation | 41.6% | 55.4% precision, 49.0% recall |

**Key finding:** Including in-context examples more than doubled accuracy for fine-grained classification in the dense setting. The prompt with examples outperformed the prompt without on every metric.

### 1.2 WildFeedback's Approach (Microsoft Research)

- **Model:** GPT-4
- **Method:** Adapted from SPUR (Supervised Prompting for User satisfaction Rubrics)
- **Process:** GPT-4 learns SAT/DSAT rubrics from thumb-annotated conversations, then applies them at utterance level
- **Inter-annotator agreement:** Cohen's kappa = 0.69 (SAT), 0.50 (DSAT)
- **Dataset:** Applied to WildChat-1M corpus, producing 20,281 labeled samples
- **Key insight:** SAT detection is easier than DSAT detection. Dissatisfaction is often implicit.

### 1.3 Full Conversation Context vs Individual Turns

**The literature strongly favors full conversation context.** Reasons:

1. A correction only makes sense relative to what the agent said. "No, use X" is meaningless without seeing the agent's prior response.
2. The "User Feedback" paper provides the full conversation to the classifier and classifies all turns in one pass.
3. Multi-turn context catches escalation patterns -- a user who says "actually" once is clarifying; a user who says it three times is frustrated.
4. Research warns that "evaluating a 100-turn conversation, you're evaluating the 50th turn -- it is extremely relevant when you take the previous 10 turns" into account.

**However:** LLMs can hallucinate when conversations get very long. For sessions with 50+ turns, consider a sliding window of the last N turns (10-20) around each user message being classified.

**Recommended approach for our audit:** Provide the full session if under 30 turns. For longer sessions, provide a window of [5 turns before, target turn, 2 turns after] plus the session's opening exchange for task context.

### 1.4 Recommended Classifier Prompt Structure

Based on convergence across papers and best practices:

```
SYSTEM PROMPT:
You are a conversation analyst. Your job is to identify user feedback
patterns in human-AI coding assistant sessions.

For each user turn, classify whether it contains feedback about the
assistant's performance, and if so, what type.

Categories:
- CORRECTION: User points out an error, wrong code, wrong file, or
  wrong information in the assistant's response
- REDIRECT: User asks the assistant to take a different approach,
  use a different tool, or change strategy entirely
- CLARIFICATION: User re-explains their intent because the assistant
  misunderstood what they wanted
- FRUSTRATION: User expresses impatience, dissatisfaction, or
  annoyance with the assistant's performance
- REFINEMENT: User asks for adjustments to scope, detail level,
  style, or format (not an error, but a preference)
- POSITIVE: User expresses satisfaction, gratitude, or agreement
- NEUTRAL: Normal continuation of the conversation, no feedback

For each user turn after the first, output JSON:
{
  "turn_index": <int>,
  "category": "<CORRECTION|REDIRECT|CLARIFICATION|FRUSTRATION|REFINEMENT|POSITIVE|NEUTRAL>",
  "confidence": <float 0-1>,
  "brief_reason": "<1-sentence explanation>"
}

IN-CONTEXT EXAMPLE:
[conversation excerpt showing one of each category with correct labels]

NOW ANALYZE THIS SESSION:
[full session or windowed context]
```

**Key design decisions:**
1. **System prompt sets the role** -- "conversation analyst" anchors the model
2. **Categories are defined with coding-assistant-specific language** -- "wrong code, wrong file" not generic "error"
3. **Confidence score** -- allows downstream filtering (high confidence -> skip judge, low confidence -> send to judge)
4. **brief_reason** -- provides chain-of-thought-like reasoning that improves accuracy and is auditable
5. **In-context examples** -- the single most impactful addition per the literature (2x accuracy improvement)
6. **JSON output** -- structured, parseable, unambiguous

### 1.5 Batch Classification vs Turn-by-Turn

Two options:

**Option A: Batch (classify all turns in one call)**
- Pros: Fewer API calls, model sees full conversation context naturally, cheaper
- Cons: Long conversations may exceed context window, harder to parallelize
- Best for: Sessions under 50 turns

**Option B: Turn-by-turn with window**
- Pros: Parallelizable, consistent context size, no context window issues
- Cons: More API calls, misses cross-session patterns
- Best for: Sessions over 50 turns or when parallelism matters

**Recommendation:** Batch for MVP. Most sessions are under 50 turns. Fall back to windowed for long sessions.

---

## 2. Best Prompts for LLM-as-Judge

### 2.1 Seven Best Practices from Literature

From Monte Carlo Data's comprehensive guide (montecarlodata.com/blog-llm-as-judge), Langfuse docs, and the LLM-as-judge survey (arxiv.org/html/2412.05579v2):

| Practice | What It Means | How to Apply |
|----------|--------------|-------------|
| **1. Few-shot prompting** | Include 1-2 examples of good/bad evaluations | Show one example of a well-analyzed correction and one ambiguous case |
| **2. Step decomposition** | Break judgment into sequential reasoning steps | "First, identify what the user wanted. Then, identify what the agent did. Then, identify the gap." |
| **3. Criteria decomposition** | Evaluate one dimension at a time, not holistically | Separate prompts for severity, root cause, and suggestion quality |
| **4. Scoring rubric** | Integer scale with explicit definitions per level | 1-5 severity scale with clear examples per level |
| **5. Structured output** | JSON, not free text | Enforce schema with required fields |
| **6. Chain-of-thought** | Require reasoning before scoring | "Explain your analysis, then provide your scores" |
| **7. Score smoothing** | Aggregate over multiple evaluations for borderline cases | Re-evaluate low-confidence judgments |

### 2.2 Preventing Leniency and Harshness

**Leniency is the #1 bias in LLM judges.** The model tends to rate outputs as "mostly good" unless prompted otherwise. Mitigation strategies from the literature:

1. **Explicit strictness instruction:** "If unsure, mark it as the stricter option"
2. **Counter-prompt technique:** "First evaluate for correctness. Then re-evaluate ignoring tone and focusing only on whether the user's core question was answered"
3. **Calibration against human labels:** Test the judge prompt against 20-30 manually labeled examples and adjust until agreement is >0.7 kappa
4. **Low temperature:** Set temperature to 0.0 or 0.1 for deterministic, repeatable scoring
5. **Avoid self-enhancement bias:** If possible, use a different model family for the judge than the agent being evaluated

### 2.3 Raw Corrections vs Pre-Processed Summaries

**The judge should see raw corrections with context**, not pre-processed summaries. Reasons:

1. Summaries lose nuance -- the exact words a user chooses reveal severity (polite vs frustrated)
2. The judge needs the agent's response that triggered the correction to understand root cause
3. Pre-processing introduces another potential point of error

**However:** The judge should NOT see the entire session for every correction. Provide:
- The user's correction turn
- The agent's response that triggered it
- 2-3 turns of preceding context
- The classifier's label and confidence (as metadata, not as instruction)

### 2.4 Recommended Judge Prompt Structure

```
SYSTEM PROMPT:
You are an expert evaluator analyzing a coding assistant's performance.
You have been given a user correction that was flagged by an automated
classifier. Your job is to analyze this correction in depth.

Be rigorous. If the agent made a real mistake, say so clearly. If the
correction is minor or the user is being unreasonable, say that too.
Do not be lenient -- the goal is honest assessment.

ANALYSIS STEPS:
1. What did the user originally want? (infer from context)
2. What did the agent do instead?
3. What is the gap between intent and execution?
4. How severe is this gap?
5. What type of failure is this?
6. What workflow rule change could prevent this in the future?

OUTPUT FORMAT (JSON):
{
  "user_intent": "<what the user actually wanted>",
  "agent_action": "<what the agent did>",
  "gap_description": "<the mismatch>",
  "severity": <1-5>,
  "severity_rubric": {
    "1": "Cosmetic -- style or formatting preference, no functional impact",
    "2": "Minor -- small inefficiency or suboptimal choice, easy to fix",
    "3": "Moderate -- wrong approach that required user intervention to redirect",
    "4": "Major -- significant error that wasted user time or produced wrong output",
    "5": "Critical -- agent action was harmful, destructive, or fundamentally wrong"
  },
  "failure_type": "<WRONG_OUTPUT|WRONG_APPROACH|MISUNDERSTOOD_INTENT|SCOPE_ERROR|PROCESS_ERROR|STYLE_MISMATCH>",
  "root_cause": "<why the agent failed -- missing context? wrong assumption? tool misuse?>",
  "suggested_rule": "<specific workflow rule that would prevent this>",
  "confidence": <float 0-1>,
  "reasoning": "<2-3 sentence chain-of-thought>"
}

CONTEXT:
[preceding turns]
[agent response that triggered correction]
[user correction turn]
[classifier label and confidence as metadata]
```

### 2.5 G-Eval Pattern (from DeepEval)

G-Eval (Liu et al., EMNLP 2023) is DeepEval's recommended approach: provide a scoring rubric and ask the LLM to generate chain-of-thought evaluation steps before scoring. This consistently outperforms direct scoring.

The pattern: rubric + "generate detailed evaluation steps" -> model produces reasoning -> model produces score. The reasoning step forces calibration.

---

## 3. Critic Agent -- Prior Art and Recommendations

### 3.1 Should We Have a Separate Critic?

**The literature says yes, for high-quality evaluation.** Key evidence:

**CritiqueLLM (arxiv.org/abs/2311.18702):** Found that "critiques from ChatGPT itself have a negative impact on the overall quality of its generated texts." Self-critique is unreliable because of the "self-consistency trap" -- models generate plausible but incorrect content with high internal self-consistency.

**Multi-agent debate research (arxiv.org/html/2511.06396v2):** A three-agent system (Critic, Defender, Judge) outperforms single-agent evaluation. The structured disagreement surfaces errors that self-critique misses.

**Constitutional AI (Anthropic, arxiv.org/abs/2212.08073):** The two-phase process (self-critique then revision) shows that critique improves output, and model-generated critiques can be applied repeatedly to progressively improve quality.

**Self-Refine (arxiv.org/abs/2303.17651):** Iterative feedback-refine loops improve output quality by 5-40% across seven tasks. However, it uses the same model for both generation and critique.

**Agent-as-a-Judge (arxiv.org/html/2508.02994v1):** Found that "diversity of agent roles is critical" for preventing groupthink in evaluation.

### 3.2 The Case FOR a Separate Critic in Our Pipeline

1. **The judge may be systematically lenient** -- it is generating suggestions and may not want to challenge its own suggestions
2. **The judge may miss edge cases** -- a suggestion that sounds good but would break something in the workflow
3. **The critic provides a quality gate** before presenting suggestions to the user
4. **Separate critique catches "hallucinated rules"** -- suggestions that reference nonexistent workflow features

### 3.3 The Case AGAINST a Separate Critic

1. **Added latency and API cost** -- one more LLM call per suggestion cluster
2. **Diminishing returns** -- the judge already has chain-of-thought reasoning
3. **Complexity** -- three agents are harder to debug than two
4. **At our scale (10-30 clusters per audit), the critic processes few items** -- the cost is minimal either way

### 3.4 Recommendation: Lightweight Critic, Not Full Debate

A full Critic-Defender-Judge debate (3 rounds, 3 agents) is overkill for our use case. But a single-pass critic that validates the judge's suggestions is high value at low cost.

**Recommended pattern:** Judge produces suggestions -> Critic reviews each suggestion -> Critic either approves, flags concerns, or rejects. No multi-round debate.

### 3.5 Recommended Critic Prompt

```
SYSTEM PROMPT:
You are a quality reviewer for an automated audit system. You have
been given a suggestion generated by an analyst who reviewed user
corrections in AI coding sessions.

Your job is to validate each suggestion before it reaches the user.
Be skeptical. Check for:

1. SPECIFICITY: Is the suggestion specific enough to act on?
   Bad: "Improve file handling" Good: "Add a rule requiring the
   agent to verify file exists before editing"
2. ACTIONABILITY: Can this actually be implemented as a workflow rule?
   Reject vague advice that cannot be codified.
3. EVIDENCE: Does the suggestion match the corrections it is based on?
   Check that the correction examples actually support the suggestion.
4. SCOPE: Is the suggestion proportionate to the problem?
   A single correction should not trigger a sweeping workflow change.
5. CONFLICTS: Would this suggestion conflict with existing workflow
   rules or create contradictions?
6. FALSE POSITIVE: Was the original "correction" actually a correction?
   Sometimes users change their mind, not correct an error.

OUTPUT FORMAT (JSON):
{
  "suggestion_id": "<id>",
  "verdict": "<APPROVE|FLAG|REJECT>",
  "concerns": ["<list of specific concerns, empty if approved>"],
  "revised_suggestion": "<improved version if flagged, null if approved or rejected>",
  "reasoning": "<1-2 sentence explanation>"
}

APPROVE: Suggestion is specific, actionable, evidence-backed, proportionate
FLAG: Suggestion has merit but needs revision (provide revised version)
REJECT: Suggestion is vague, unsupported, disproportionate, or based on a false positive
```

### 3.6 What the Critic Checks (Checklist from Literature)

Drawing from Constitutional AI's principle-based checking and Agent-as-a-Judge's process evaluation:

| Check | Question | Source |
|-------|----------|--------|
| Specificity | Can this be turned into a concrete rule in rules.yaml? | Best practices |
| Grounding | Do the cited corrections actually demonstrate this problem? | Agent-as-a-Judge |
| Proportionality | Is N corrections enough to justify this rule? (threshold: 3+) | Statistical significance |
| Conflict detection | Would this rule contradict an existing rule? | Constitutional AI |
| Feasibility | Can the agent actually follow this rule? (not a catch-22) | CLAUDE.md: "DON'T write guardrail rules that block their own prerequisites" |
| User alignment | Would the user agree this is a real problem, not a preference? | WildFeedback SAT/DSAT distinction |

---

## 4. Multi-Agent Evaluation Pipelines

### 4.1 Established Patterns from Literature

#### Pattern A: Classifier -> Judge (Two-Agent, Simplest)

```
Classifier scans all turns -> flags corrections -> Judge analyzes each
```

Used by: WildFeedback, SPUR, "User Feedback in Human-LLM Dialogues"

**Pros:** Simple, low latency, low cost
**Cons:** No quality gate on judge output

#### Pattern B: Classifier -> Judge -> Critic (Three-Agent, Recommended)

```
Classifier flags -> Judge analyzes + suggests -> Critic validates suggestions
```

Used by: Constitutional AI (critique + revise), LLM safety debate (Critic + Defender + Judge)

**Pros:** Quality gate catches judge errors, hallucinated rules, disproportionate suggestions
**Cons:** One additional API call per suggestion cluster

#### Pattern C: Classifier -> Judge -> Critic -> Judge (Iterative Refinement)

```
Classifier flags -> Judge suggests -> Critic critiques -> Judge revises -> output
```

Used by: Self-Refine (generate -> feedback -> refine loop)

**Pros:** Suggestions get refined based on critique, highest quality output
**Cons:** 2x judge calls, added latency, diminishing returns after 1 iteration

#### Pattern D: Adversarial Debate (Full Multi-Agent)

```
Classifier flags -> Critic argues "this is a real problem" ->
Defender argues "this is not a problem" -> Judge weighs both sides
```

Used by: Multi-agent safety debate (arxiv.org/html/2511.06396v2), CourtEval

**Pros:** Surfaces the strongest arguments for and against each finding
**Cons:** 3-5x compute cost, complex orchestration, overkill for our scale

### 4.2 Agent-as-a-Judge: Evaluating Process, Not Just Output

The **Agent-as-a-Judge** framework (arxiv.org/html/2508.02994v1) introduces a key insight: evaluate the entire chain of actions, not just the final answer. For our audit, this means:

- The judge should not just evaluate "was the correction valid?"
- It should evaluate "what sequence of agent decisions led to needing this correction?"
- This requires examining the agent's tool calls, file edits, and reasoning chain -- not just the text output

**Implication for our pipeline:** The judge prompt should include not just the conversation text but also metadata about what tools the agent used, what files it edited, and what its stated reasoning was.

### 4.3 Role Specialization Patterns

From the literature, effective multi-agent evaluation uses role specialization:

| Role Pattern | Agents | Source |
|-------------|--------|--------|
| **DEBATE** | Scorer, Critic, Commander | Multi-agent debate |
| **CourtEval** | Judge, Prosecutor, Defense Attorney | Legal adversarial |
| **MAJ-EVAL** | Domain-specific personas (auto-generated) | Stakeholder-based |
| **ChatEval** | Factual accuracy specialist, Style evaluator, Relevance assessor | Expertise-based |
| **RADAR** | Security Auditor, Vulnerability Detector, Counterargument Critic, Holistic Arbiter | Safety-focused |

**For our audit workflow, the closest match is the DEBATE pattern simplified to two roles:**
- **Classifier+Judge** (combined Scorer role) -- identifies and analyzes corrections
- **Critic** (Critic role) -- validates findings before presentation

The Commander role maps to the audit pipeline orchestrator (code, not LLM).

### 4.4 Handoff Structure Between Agents

Based on the Evaluation-Driven Development reference architecture (arxiv.org/html/2411.13768v3):

```
Classifier Agent
  Input:  Full session transcript (or windowed)
  Output: List of {turn_index, category, confidence, brief_reason}
  Handoff: All turns with category != NEUTRAL and category != POSITIVE

Judge Agent
  Input:  Each flagged turn + surrounding context + agent metadata
  Output: {severity, failure_type, root_cause, suggested_rule, reasoning}
  Handoff: All suggestions grouped by cluster (from BERTopic or similar)

Critic Agent
  Input:  Each suggestion + its supporting corrections + existing workflow rules
  Output: {verdict: APPROVE|FLAG|REJECT, concerns, revised_suggestion}
  Handoff: APPROVE and FLAG suggestions -> final report
```

**Key handoff principles:**
1. Each agent receives only what it needs -- no unnecessary context
2. Structured JSON at every boundary -- no ambiguous natural language handoffs
3. Metadata flows forward (classifier confidence informs judge, judge reasoning informs critic)
4. The pipeline orchestrator (code) handles grouping, filtering, and assembly -- agents do analysis

### 4.5 Cost Estimation for Three-Agent Pipeline

Assuming Claude Sonnet for all agents, ~1000 input tokens per turn, ~200 output tokens per classification:

| Stage | Calls | Input/Call | Output/Call | Estimated Cost |
|-------|-------|-----------|-------------|---------------|
| Classifier | 1-5 (batch) | ~50K tokens (full session) | ~5K tokens | ~$0.20-0.50 |
| Judge | 10-30 (per correction cluster) | ~2K tokens | ~500 tokens | ~$0.10-0.30 |
| Critic | 10-30 (per suggestion) | ~1K tokens | ~200 tokens | ~$0.05-0.15 |
| **Total per audit** | | | | **~$0.35-0.95** |

At $0.50-1.00 per audit run covering ~1,300 turns, this is very cost-effective.

---

## 5. Summary Recommendations

### Architecture

**Use Pattern B: Classifier -> Judge -> Critic (three-agent).**

It provides the best quality/cost tradeoff. The critic adds minimal cost (~$0.10) but catches hallucinated rules, disproportionate suggestions, and false positives.

### Classifier Agent

- Use full conversation context (batch classification)
- Include 2-3 in-context examples (2x accuracy improvement per literature)
- Output structured JSON with category + confidence + brief_reason
- 7 categories: CORRECTION, REDIRECT, CLARIFICATION, FRUSTRATION, REFINEMENT, POSITIVE, NEUTRAL

### Judge Agent

- Receives flagged corrections with surrounding context
- Uses step-decomposed reasoning (what did user want -> what did agent do -> what is the gap)
- Outputs severity (1-5 rubric), failure type, root cause, and suggested rule
- Set temperature 0.0 for consistency
- Explicit anti-leniency instruction: "If unsure, mark it as the stricter option"

### Critic Agent

- Lightweight single-pass validation (not multi-round debate)
- Checks: specificity, actionability, evidence grounding, proportionality, conflict detection, feasibility
- Three verdicts: APPROVE, FLAG (with revision), REJECT
- Guards against the known failure mode: "DON'T write guardrail rules that block their own prerequisites"

### What NOT to Do

- Do NOT use self-critique (same model critiquing its own output) -- literature shows this degrades quality
- Do NOT use full adversarial debate (Critic-Defender-Judge) -- overkill for our scale, 3-5x cost
- Do NOT have the classifier process turns individually without context -- accuracy drops significantly
- Do NOT let the judge see the classifier's label as instruction (only as metadata) -- prevents anchoring bias

---

## 6. Sources

- User Feedback in Human-LLM Dialogues: https://arxiv.org/html/2507.23158v2
- WildFeedback (Microsoft): https://arxiv.org/html/2408.15549v3
- WildFeedback dataset: https://huggingface.co/datasets/microsoft/WildFeedback
- SPUR (ACL 2024): https://arxiv.org/abs/2403.12388
- LLM-as-Judge Survey: https://arxiv.org/html/2412.05579v2
- Monte Carlo LLM-as-Judge Best Practices: https://www.montecarlodata.com/blog-llm-as-judge/
- Langfuse LLM-as-Judge: https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge
- DeepEval G-Eval: https://deepeval.com/docs/metrics-llm-evals
- Evidently AI LLM-as-Judge: https://www.evidentlyai.com/llm-guide/llm-as-a-judge
- LLM-as-Judge Calibration (LangChain): https://www.langchain.com/articles/llm-as-a-judge
- LLM-as-Judge Bias Evaluation: https://arxiv.org/html/2506.22316v1
- Constitutional AI: https://arxiv.org/abs/2212.08073
- Self-Refine: https://arxiv.org/abs/2303.17651, https://selfrefine.info/
- CritiqueLLM: https://ar5iv.labs.arxiv.org/html/2311.18702
- CRITIC (Tool-Interactive): https://arxiv.org/abs/2305.11738
- Agent-as-a-Judge: https://arxiv.org/html/2508.02994v1
- Multi-Agent LLM Safety Debate: https://arxiv.org/html/2511.06396v2
- Multi-Agent Meta-Judge: https://arxiv.org/html/2504.17087v1
- Evaluation-Driven Development: https://arxiv.org/html/2411.13768v3
- Multi-turn Dialogue Survey: https://dl.acm.org/doi/full/10.1145/3771090
- Prompt Engineering Guide (Classification): https://www.promptingguide.ai/prompts/classification
- Follow-up Query Taxonomy: https://arxiv.org/html/2407.13166v1
