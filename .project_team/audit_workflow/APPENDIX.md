# audit_workflow -- APPENDIX

## Design History

This appendix preserves design context and rationale removed from SPECIFICATION.md to keep that document operational-only.

### Version History

- v1-v3: Initial specification rounds with leadership review (Composability, TerminologyGuardian, Skeptic, UserAlignment -- two rounds each).
- v4: Addressed blocking issues from fresh review: output paths, template shipping, LLM validation, GapDetector role.
- v4.1: Added apply phase -- auditor agent directly edits files (no manual copy-paste).
- v4.2: Added dated output files for audit history, interactive review flow corrections.
- v5: Replaced regex scoring with GLiClass NLI pipeline: binary detection -> 6-category classification + BERTopic clustering -> LLM-as-judge.
- v5.1: Restored regex as PARALLEL detector alongside GLiClass. Empirically validated on 76 sessions, 310 messages: zero overlap, complementary coverage.
- v6: Dropped GLiClass entirely (1.3% recall -- useless). LLM classifier (Haiku) is primary detector (24.1% recall, $0.005/session). Multi-role workflow: classifier, judge, critic (TBD), auditor. Removed nli.py module and transformers/torch dependencies.

### Leadership Review Findings

Two rounds of leadership review shaped the architecture:

**Round 1:**
| Agent | Key Finding |
|-------|-------------|
| Composability | 5-axis decomposition, GapDetector protocol, chicsession join risk |
| TerminologyGuardian | 6 new terms, 14 reused, collision rules |
| Skeptic | Suggestion quality risk, phase mapping, mine_patterns extraction |
| UserAlignment | Invocation UX, machine-applicable output, priority ranking |

**Round 2 (Fresh Review of v3):**
| Agent | Verdict | Key Finding |
|-------|---------|-------------|
| Composability2 | SOUND | GapDetectors should be advisory not gatekeeping, findings budget needed |
| Terminology2 | CLEAN | 3 minor items, "suggester" term replaced |
| Skeptic2 | IMPROVED | LLM validation must be programmatic, import chain needs scripts/__init__.py |
| UserAlignment2 | STRONG | Output paths must be end-user appropriate, suggest.md needs examples |

### Resolved Decisions

| # | Decision | User Direction |
|---|----------|---------------|
| 1 | Lives in root repo AND ships in template | Audit exists at root level for template developers to use directly, AND is mirrored into template/ for end users of generated projects. Both audiences benefit from auditing their agent interactions. |
| 2 | LLM-as-judge suggestions | This IS the core feature. The auditor agent (LLM-as-judge) reviews category/cluster representatives + actual workflow content and generates meaningful suggestions. GLiClass NLI detects and categorizes corrections; BERTopic discovers themes; the LLM generates the fixes. |
| 3 | No git workflow coupling | User checkpoints = user saying "advance to next phase." No PRs, commits, or git operations in the workflow itself. |
| 4 | Apply phase (agent edits files) | User does NOT manually copy-paste suggestions. After report review, the auditor agent directly edits target files for approved suggestions in a dedicated apply phase. |

### Key Design Rationale

- **5-axis decomposition** (from Composability review): Source Parsing, Analysis Strategy, Reference Corpus, Suggestion Type, Report Format -- each axis maps to a module.
- **GapDetectors advisory, not gatekeeping** (from Composability2 + Skeptic2): Over-generate findings, let LLM filter. This avoids false negatives from simple heuristics blocking valid signals.
- **Programmatic LLM validation** (from Skeptic2): `validate_suggestions()` runs post-write because LLMs cannot reliably self-validate structured output.
- **session_lib.py extraction** (from Skeptic + Composability): Avoids coupling to 1229-line mine_patterns.py. Nested inside `scripts/audit/` so the template ships as one clean package.
- **Parallel regex + GLiClass** (v5.1 empirical revision): POC on 76 real sessions / 310 messages showed zero overlap between regex (keyword-driven, 2.6%) and GLiClass (semantic, 1.6%). Neither subsumes the other.
- **GLiClass config locked** (v5.1): Multi-label (sigmoid) produces 93.7% flag rate. The `examples=` parameter is broken (`<<EXAMPLE>>` token missing from tokenizer). Single-label + no prompt + no examples is the only working config.
- **Pre-filter stage** (v5.1): System boilerplate (agent spawns, interrupts, reminders) pollutes detection results if not stripped first.
- **Large model as default** (empirical): 90% accuracy vs 80% base, 35.5% vs 56% flag rate. Load time (17.7s) acceptable for offline audit.

### GLiClass Rejection Data (v6)

GLiClass NLI was tested extensively and rejected in favor of LLM classifier:

| Detector | Corrections Found | Recall | Cost | Status |
|----------|------------------|--------|------|--------|
| LLM classifier (Haiku) | 76/315 | 24.1% | $0.005/session | PRIMARY |
| Regex (session_lib) | 7/76 | 9.2% | Free | Optional parallel |
| GLiClass NLI (large) | 1/76 | 1.3% | Free | REJECTED |

GLiClass config that was tested (before rejection):
- Model: `knowledgator/gliclass-modern-large-v3.0` (Apache-2.0)
- `classification_type="single-label"` (softmax). Multi-label (sigmoid) produced 93.7% flag rate.
- NO prompt, NO few-shot examples. `examples=` parameter broken (`<<EXAMPLE>>` token missing).
- Performance: 12.4 msgs/sec, 17.7s load, 90% synthetic accuracy, 35.5% flag rate.
- Despite good synthetic accuracy, real-world recall was 1.3% -- the model could not detect actual user corrections in real conversations.

### GapDetector Protocol (Removed in data model simplification)

The GapDetector protocol was removed when the data model was simplified from 8+ types to 3. The LLM (judge agent) now performs gap detection directly by reading workflow definitions alongside correction signals. The protocol had 4 implementations:
- PhaseGapDetector: keyword extraction from signal vs phase markdown
- CheckGapDetector: structural check for phases with <2 advance checks
- RuleGapDetector: signal tool mentions vs rule triggers
- HintGapDetector: signal text overlap vs existing hint messages

### Risk Attribution

Original risk identification sources for traceability:

| Risk | Identified By |
|------|--------------|
| LLM generates invalid YAML | Skeptic2 |
| LLM hallucinated file paths | Skeptic2 |
| LLM exceeds context window | Composability2 |
| GLiClass model loading latency | v5.1 empirical validation |
| GLiClass config regression | v5.1 empirical validation |
| BERTopic empty clusters | v5 architecture |
| Phase-to-correction mapping | Skeptic |
| mine_patterns.py coupling | Skeptic + Composability |
| Import chain in generated projects | Skeptic2 |
| Hardcoded agent roles | Skeptic2 |
| JSONL format instability | Skeptic |
| Stale session ID references | Skeptic |
| Cold-start (zero sessions) | Skeptic2 + UserAlignment2 |
| Cross-platform (Windows) | Skeptic + Skeptic2 |
| Duplicate suggestions | UserAlignment |
| Chicsession adapter join complexity | Composability |
| Non-deterministic LLM testing | Skeptic2 |
