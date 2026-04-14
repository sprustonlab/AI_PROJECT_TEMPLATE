# audit_workflow -- STATUS

## Phase: Specification
## Status: v5.1 Ready for User Review

## Vision (Approved)

**Goal:** Build an `audit` workflow that ships in generated projects, parses JSONL session logs and chicsession snapshots, analyzes agent-human interaction quality, and uses the auditor agent (LLM) to generate machine-applicable suggestions for improving workflow phase markdown, advance checks, rules, and hints. After user review, the auditor agent directly applies approved suggestions.

## Specification Summary

Architecture: Multi-agent pipeline with 4 roles (classifier, judge, critic, auditor). LLM classifier (Haiku) is primary detector (24.1% recall, $0.005/session). Regex optional parallel signal (9.2% recall, free). GLiClass rejected (1.3% recall). Pre-filter strips system boilerplate. BERTopic clusters flagged items. Judge agent reads signals + workflow definitions, generates suggestions. Auditor orchestrates user review + applies edits. 3 dataclasses only.

### Key decisions:
- `session_lib.py` nested inside `scripts/audit/` (works as one clean package in both root repo and template)
- Output directory: `.audit/` (not `.project_team/` -- end-user appropriate)
- `validate_suggestions()` programmatically validates LLM output post-write
- 3 dataclasses max (ParsedInteraction, CorrectionSignal, AuditSuggestion) -- no wrapper types
- LLM classifier (Haiku) is primary detector, regex is optional parallel signal
- Multi-role workflow: classifier, judge, critic, auditor
- Findings budget: top 20 by severity passed to suggest phase
- judge/suggest.md includes worked examples, anti-patterns, output schema, YAML reference
- Cold-start UX handled in identity.md
- Post-report: apply phase where auditor agent directly edits files for user-approved suggestions
- 5 phases: parse -> analyze -> suggest -> report -> apply

### Blocking issues resolved (from fresh review):
1. Output paths: `.audit/` instead of `.project_team/audit_workflow/`
2. Template shipping: explicit file inventory (ships vs repo-only), `scripts/__init__.py`, copier.yml changes
3. LLM validation: `validate_suggestions()` -- skip invalid with warning, never retry
4. LLM is the gap detector: all qualifying signals forwarded, LLM reads workflow definitions
5. suggest.md: concrete guidance (examples, anti-patterns, schema, YAML reference)

## Leadership Reports (Two Rounds)

### Round 1
| Agent | Key Finding |
|-------|-------------|
| Composability | 5-axis decomposition, GapDetector protocol, chicsession join risk |
| Terminology | 6 new terms, 14 reused, collision rules |
| Skeptic | Suggestion quality risk, phase mapping, mine_patterns extraction |
| UserAlignment | Invocation UX, machine-applicable output, priority ranking |

### Round 2 (Fresh Review of v3)
| Agent | Verdict | Key Finding |
|-------|---------|-------------|
| Composability2 | SOUND | GapDetectors should be advisory not gatekeeping, findings budget needed, template scripts/ mixing |
| Terminology2 | CLEAN | 3 minor items, "suggester" term replaced, collision rule added |
| Skeptic2 | IMPROVED | LLM validation must be programmatic, import chain needs scripts/__init__.py, GapDetector algorithms underspecified |
| UserAlignment2 | STRONG | Output paths must be end-user appropriate, suggest.md needs concrete examples, cold-start UX needed |

## Decision Log

| # | Decision | Rationale | Date |
|---|----------|-----------|------|
| 1 | Vision approved | User approved v2 vision summary | 2026-04-13 |
| 2 | Extract session_lib.py | Avoid coupling to 1229-line mine_patterns.py | 2026-04-13 |
| 3 | Hybrid phase mapping | JSONL transition markers + chicsession fallback + None | 2026-04-13 |
| 4 | Default invocation = current chicsession | Most natural UX | 2026-04-13 |
| 5 | Minimum evidence thresholds | 2+ for markdown/hints, 3+ for checks/rules | 2026-04-13 |
| 6 | GapDetector protocol (advisory) | Over-generate, LLM filters. Not gatekeeping. | 2026-04-13 |
| 7 | Lives in root repo AND ships in template | Audit exists at root for template devs AND mirrors into template for end users | 2026-04-13 |
| 8 | LLM-as-judge suggestions are core | Auditor agent generates suggestions, GLiClass NLI detects + categorizes | 2026-04-13 |
| 9 | No git workflow coupling | User checkpoints = user approval | 2026-04-13 |
| 10 | Output to .audit/ | End-user appropriate, not dev convention | 2026-04-13 |
| 11 | session_lib.py inside scripts/audit/ | Ships as one clean package in template | 2026-04-13 |
| 12 | validate_suggestions() post-write | Programmatic LLM output validation, skip+warn on failure | 2026-04-13 |
| 13 | Findings budget (top 20) | Prevent context window exhaustion in suggest phase | 2026-04-13 |
| 14 | Apply phase (agent edits files) | User correction: no manual copy-paste. Auditor agent directly edits files for approved suggestions in dedicated apply phase. User marks [APPLY]/[SKIP] in report. | 2026-04-13 |
| 15 | Machine-applicable suggestions | Suggestions include exact file paths, current_content for replacements, insertion_point for additions -- enabling automated application | 2026-04-13 |
| 16 | Dated output files | All audit output files include datetime stamp ({YYYY-MM-DD_HHmm}) for audit history. Multiple runs coexist in .audit/. Advance checks use command-output-check with globs. | 2026-04-13 |
| 17 | Kill regex as scoring tier | GLiClass NLI on all turns replaces regex cascade. Regex stays in session_lib.py for mine_patterns.py only. | 2026-04-13 |
| 18 | Two-level NLI classification | Level 1: binary (correction/not). Level 2: 6-category on L1 positives. GLiClass single forward pass. | 2026-04-13 |
| 19 | Configurable label taxonomy | General (default) vs coding-specific (alternative). 6 categories each. | 2026-04-13 |
| 20 | Category-to-workflow-fix mapping | Factual/Approach->phase+rules. Intent/Scope->phase. Style->hints (user-only). Frustration->rules(deny)+checks. Rules=warn/deny. Hints=user-only. | 2026-04-13 |
| 21 | Parallel Level 2 + BERTopic | L2 category classification and BERTopic clustering run in parallel on L1 positives, not sequentially. | 2026-04-13 |
| 22 | Deferred tools to APPENDIX.md | Spotlight, Marimo, DeepEval, Cleanlab, active learning, timeline viz, drift detection -- NOT in v1. | 2026-04-13 |
| 23 | Regex restored as parallel detector | Empirically validated on 76 sessions/310 msgs: regex (2.6%) + GLiClass (1.6%) = 4.2%, zero overlap. Not a cascade -- parallel and complementary. | 2026-04-13 |
| 24 | GLiClass config LOCKED | single-label (softmax), minimal prompt, NO examples param. Multi-label=93.7% flag rate. examples= broken (<<EXAMPLE>> token missing). | 2026-04-13 |
| 25 | Pre-filter stage added | Strip system boilerplate before detection: agent spawns, interrupts, system reminders, task notifications, idle reminders. | 2026-04-13 |
| 26 | Zero-overlap parallel architecture | Validated on 310 real messages: regex catches keyword corrections, GLiClass catches semantic corrections. Zero redundancy. | 2026-04-13 |
| 27 | GLiClass large model as default | Empirically validated: 90% accuracy vs 80% base, 35.5% vs 56% flag rate (better precision). 12.4 msgs/sec, 17.7s load -- acceptable for offline audit. Base available as faster alternative. | 2026-04-13 |
| 28 | Drop GLiClass, LLM is primary detector | GLiClass found 1/76 corrections (1.3% recall -- useless). LLM classifier (Haiku) found 76/315 (24.1% recall) at $0.005/session. Regex optional parallel signal (9.2% recall, free). Removes transformers/torch dependencies. | 2026-04-13 |
| 29 | Multi-role workflow | 4 roles: classifier (Haiku, detects corrections), judge (analyzes corrections, generates suggestions), critic (validates suggestions), auditor (orchestrates, presents to user, applies edits). Replaces single-role auditor-does-everything design. | 2026-04-13 |
| 30 | Critic finalized with 3-message context window | Critic checks 6 things: specificity, actionability, evidence grounding, proportionality, conflict detection, feasibility. 3 verdicts: APPROVE, FLAG (with revision), REJECT. CorrectionSignal includes context_before (agent msg before) + user_text + context_after (agent msg after) -- gives critic root-cause context. Classifier extracts context window. | 2026-04-13 |
