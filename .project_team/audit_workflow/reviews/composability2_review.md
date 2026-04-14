# Composability Review -- Audit Workflow Specification v3 (FRESH)

## Overall Assessment: SOUND with 4 actionable issues

The v3 spec's hybrid code+LLM architecture is compositionally well-designed. The 5-axis decomposition maps cleanly to the filesystem, the frozen dataclass seam types are correct, and the module boundaries respect claudechic's import direction rules. The LLM-driven suggestion approach actually *improves* composability by eliminating the regex-to-YAML brittleness that would have plagued a pure-code suggester. I found 4 issues that need attention.

---

## 1. 5-Axis Decomposition: HOLDS, with a refinement

The 5 axes (Source Parsing, Analysis Strategy, Reference Corpus, Suggestion Type, Report Format) still map to distinct modules. The LLM-driven approach makes the Suggestion Type axis *cleaner* -- `suggestions.py` becomes a structural/validation utility rather than a brittle code-based suggestion engine.

**Issue:** The "Suggestion Type" axis is now split across two concerns:
- `suggestions.py` = serialization, validation, deduplication (code)
- `auditor/suggest.md` = actual generation logic (LLM instructions)

If someone extends suggestion types (e.g., adding "workflow-manifest-edit"), they must update BOTH `suggestions.py` (new field in `AuditSuggestions`) AND `suggest.md` (new LLM instructions). **Severity: Low.** Document this dual-update requirement.

## 2. Code/LLM Boundary: EXCELLENT -- strongest compositional decision

The boundary is clean:
- **Code (deterministic):** Parse, Analyze, Cross-reference -- produce structured, testable, reproducible outputs
- **LLM:** Suggest -- reads findings + actual workflow content, generates meaningful fix proposals
- **`findings.json`** is the explicit serialization boundary between code and LLM

**One concern:** `PhaseGapDetector` checking if a "correction topic is addressed in the relevant phase markdown" is a soft semantic check, not deterministic code. **Recommendation:** Acknowledge that GapDetectors use keyword/heuristic matching and are intentionally coarse filters that the LLM refines. This is fine -- just be honest about it in the spec.

## 3. GapDetector Protocol: Role shifts from "generator" to "filter"

With the LLM generating suggestions, GapDetectors serve as pre-filters, structural validators, and deduplication gates. The Protocol shape (`detect() -> AuditFinding | None`) is correct and follows the same pattern as `Check.check() -> CheckResult`.

**Risk:** If GapDetectors are too coarse (false negatives), the LLM won't see important findings. If too fine (false positives), the LLM wastes context on noise.

**Recommendation (Medium severity):** Make GapDetector results advisory rather than gatekeeping. Pass ALL qualifying correction signals to the LLM with gap detection results as metadata. Add optional `gap_detectors_matched: list[str]` to `AuditFinding`. This way GapDetectors enrich rather than gate. The pipeline would emit findings for ALL qualifying signals, not just those where a GapDetector fired.

## 4. Frozen Dataclasses: CORRECT seam types

The audit types follow claudechic's established pattern exactly:

| Audit Type | Claudechic Analog | Seam |
|---|---|---|
| `ParsedInteraction` | `ParseResult` | Parser output |
| `CorrectionSignal` | `CheckResult` | Analysis output |
| `AuditFinding` | (new) | Cross-reference output |
| `AuditSuggestion` | `HintRecord` | Suggestion output |

All frozen, all crossing module boundaries cleanly.

**Minor notes:**
- `CorrectionSignal` has 13 fields (heavy vs. `CheckResult`'s 2 fields). The field count is justified by the information density needed, but consider whether `phase_confidence`, `tier`, and `message_index` need to cross the seam to the LLM, or if they're only used internally by the code stages.
- `ParsedInteraction.messages` is typed as bare `list` and `ParsedInteraction.phase_transitions` as bare `list`. The comments document the contents but the types don't enforce it. Implementation should use proper generic types (`list[Message]`, `list[tuple[int, str]]`).

## 5. Template Shipping: WORKS, with one structural issue

- `workflows/audit/` mirrors cleanly to `template/workflows/audit/` (same as other workflows like `project_team`)
- `scripts/session_lib.py` and `scripts/audit/` need to ship in `template/scripts/`

**The issue:** `scripts/` is currently a dev-tooling directory in this repo (contains `mine_patterns.py` which is dev-only). Shipping `scripts/audit/` to end users means the `template/scripts/` directory mixes dev tools with user tools.

**Recommendations (Medium severity):**
1. Specify exact `copier.yml` `_exclude` changes needed -- include `scripts/session_lib.py` + `scripts/audit/` while excluding `scripts/mine_patterns.py` and other dev scripts
2. Consider nesting `session_lib.py` inside `scripts/audit/` (as `scripts/audit/session_lib.py`) rather than as a sibling, to make the include/exclude boundary one clean directory instead of cherry-picking files
3. The spec mentions modifying `copier.yml` but doesn't specify the exact rules -- this should be specified to prevent accidental inclusion of dev-only scripts

## 6. New Composability Risks from LLM-Driven Approach

### Risk A: Context window pressure (Medium)

The suggest phase requires the LLM to read: `findings.json` (could be large), multiple phase markdown files, existing rules/hints YAML, AND generate structured output. For projects with many workflows and many sessions, this could exceed context.

**Recommendation:** Add a findings budget -- sort findings by severity, cap at top N (e.g., 20) findings passed to the suggest phase. The report can note "X additional lower-severity findings omitted."

### Risk B: LLM output failure modes (Medium)

The spec says `suggestions.py` validates YAML, but doesn't specify what happens when validation fails. The LLM generated invalid YAML -- do we retry, skip, or emit a warning?

**Recommendation:** Skip with warning in the report ("1 suggestion omitted due to invalid YAML"). Do not retry -- retries add complexity and unpredictability.

### Risk C: Non-deterministic testing (Low)

Suggestion content varies between LLM runs. The spec's test strategy correctly avoids testing LLM output with unit tests (`test_audit_suggestions.py` tests utility functions). But there's no guidance on verifying suggestion quality during development.

**Recommendation:** Add a "golden file" structural integration test that runs the full pipeline on a known fixture and checks structural properties (e.g., "at least 1 phase-markdown suggestion produced", "all YAML in suggestions parses", "all ArtifactRef file paths reference valid workflow structure").

---

## Summary of Actionable Items

| # | Issue | Severity | Recommendation |
|---|-------|----------|---------------|
| 1 | Dual-update requirement for suggestion types | Low | Document that extending types requires updating both suggestions.py AND suggest.md |
| 2 | GapDetectors as gatekeepers vs. advisors | Medium | Make gap detection advisory metadata, not gates. Pass all qualifying signals to LLM |
| 3 | Template shipping -- scripts/ directory mixing | Medium | Specify exact copier.yml exclude rules. Consider nesting session_lib.py inside audit/ |
| 4 | LLM output failure modes + context budget | Medium | Specify invalid YAML handling (skip+warn). Add findings budget cap for suggest phase |

## What's Compositionally Excellent

- The `findings.json` serialization boundary between code and LLM stages is clean and testable
- Frozen dataclasses as seam types match claudechic's established patterns perfectly
- The `GapDetector` Protocol follows the same shape as the `Check` Protocol -- consistent extension model
- Phase-to-correction mapping with confidence levels (`inferred`/`snapshot`/`unknown`) is a smart degradation strategy
- The workflow manifest uses only existing check types (`file-exists-check`, `manual-confirm`) -- no new check types needed
- Rules scoped to `[parse, analyze, suggest]` phases (excluding `report`) correctly allow the report phase to write output files
- The `session_lib.py` extraction avoids coupling to the 1229-line `mine_patterns.py` monolith
- Import direction is respected: `scripts/audit/` never imports from `claudechic` internals -- it reads YAML files and uses `ManifestLoader` as a library
