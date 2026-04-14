# UserAlignment Review -- Specification v7

**Reviewer:** UserAlignment (Round 3)
**Date:** 2026-04-13
**Verdict:** ALL USER REQUIREMENTS PRESERVED

---

## Requirement-by-Requirement Verification

### 1. Suggestions for workflow markdown, advance checks, rules, hints
**Status:** PRESERVED
- Section 8.1 defines all 4 artifact types as suggestion targets
- Section 8.2 maps categories to fix types explicitly
- `suggestions` table has `artifact_type` column with exactly these 4 values: `phase-markdown`, `advance-check`, `rule`, `hint`
- Section 10 (suggest.md content) requires YAML reference for all artifact types

### 2. Hints = user-only, rules = warn/deny
**Status:** PRESERVED
- Section 8.1: `style_preference` maps ONLY to hints, explicitly marked "(user-facing ONLY)"
- Section 8.2: rules columns show "warn/deny" for factual_correction, approach_redirect; "deny" for frustration_escalation
- Clean separation maintained throughout

### 3. Interactive apply: agent presents, asks, applies -- no copy-paste
**Status:** PRESERVED
- Section 7.2, `report` phase: auditor presents each suggestion conversationally, asks "Apply this suggestion? (yes/no)"
- Section 7.2, `apply` phase: auditor uses Read + Edit tools to directly modify files
- Machine-applicable fields in suggestions table: `current_content`, `proposed_content`, `insertion_point`, `file_path`
- Decision 14 explicitly states: "no manual copy-paste"

### 4. /audit brings options menu (3 modes)
**Status:** PRESERVED
- Section 2 defines exact UX: current session, saved chicsession, all local conversations
- Table shows context availability per mode
- Cold-start UX included

### 5. Additive/incremental -- rerun only processes new sessions
**Status:** PRESERVED -- AND IMPROVED
- SQLite `processed_files` table tracks file_size + file_mtime
- Section 5.2 incremental logic: skip files where size+mtime match, INSERT OR IGNORE for dedup
- Section 1 explicitly states: "Re-running after new sessions processes only NEW messages"
- v7's SQLite approach is stronger than v5's file-based tracking -- accumulated corrections persist and grow

### 6. Single Python file, agents do thinking
**STATUS:** PRESERVED
- Section 3.1 core principle: "Agents orchestrate, Python is a thin helper. One Python file (audit.py)"
- audit.py is ~300 lines, handles only JSONL extraction and DB operations
- All analysis, classification, suggestion generation happen through agent roles
- No Python-side ML, clustering, or scoring logic in the pipeline

### 7. 3-message context window (before/correction/after)
**Status:** PRESERVED
- DB schema: `context_before`, `user_text`, `context_after` columns on `messages` table
- Section 5.2 explicitly defines extraction: context_before = assistant msg at i-1, context_after = assistant msg at i+1
- Section 9.3: critic uses context to assess severity (agent fixed vs repeated mistake)
- Section 10 item 7: suggest.md must include context usage instructions
- Decision 30 confirms this design

### 8. Critic validates suggestions
**Status:** PRESERVED
- Section 9 defines 6 checks, 3 verdicts (APPROVE/FLAG/REJECT)
- Critic is a dedicated agent role with own identity.md and suggest.md
- Section 9.3 adds context-aware validation using the 3-message window
- Proportionality check enforces evidence thresholds from Section 8.3

### 9. Ships in both root repo and generated projects
**Status:** PRESERVED
- Section 1: "Template developers (this repo) AND end users of generated projects"
- Section 13 file inventory: explicit `template/scripts/audit/` and `template/workflows/audit/` mirrors
- copier.yml modification listed in existing files to modify

---

## What Changed from Earlier Specs (v5) to v7

| Change | Impact on User Requirements |
|--------|---------------------------|
| GLiClass removed, LLM classifier (Haiku) is primary | NEUTRAL -- user never specified detection method, only that corrections be found |
| SQLite replaces flat files | POSITIVE -- stronger incremental behavior, persistent accumulation |
| BERTopic clustering dropped | NEUTRAL -- judge agent spots patterns conversationally instead |
| Regex demoted to optional | NEUTRAL -- detection quality is what matters, not mechanism |
| 4-role workflow (classifier, judge, critic, auditor) | POSITIVE -- cleaner separation, critic is a real role now |
| mine_patterns.py deleted | NEUTRAL -- all useful parsing absorbed into audit.py |

---

## Potential Concerns (Minor)

### A. Classifier Cost Visibility
The user may not realize `/audit` on "all local conversations" with 1000+ sessions costs ~$5 in Haiku calls. The spec mentions budget cap as configurable (Section 15) but does NOT specify where or how. **Suggestion:** auditor identity.md should warn user about estimated cost before proceeding with large scans, and `--limit` on unclassified should be the default batch size.

### B. No Explicit "Rerun Only New" UX Feedback
The incremental skip logic is in audit.py, but the spec doesn't require the auditor to tell the user "Skipped 76 already-processed files, processing 3 new ones." The stderr output (Section 5.2) shows this, but the auditor agent should relay it conversationally. **Suggestion:** parse.md should instruct auditor to summarize incremental skip counts to user.

### C. Mode 3 Suggestion Scoping
When running "all local conversations," suggestions are global/unscoped (Section 2). This is correct but could generate noisy suggestions. The spec handles this implicitly (phase_id = NULL, judge must work without phase context). No action needed but worth noting.

---

## Final Assessment

**The v7 specification fully preserves all 9 user requirements.** The simplification (dropping GLiClass, using SQLite, making audit.py a thin CLI) actually strengthens several requirements -- particularly incrementality (#5) and the single-file constraint (#6). The interactive apply flow (#3) is well-specified with concrete DB fields enabling machine application. The 3-message context window (#7) is threaded through extraction, classification, critic validation, and suggest.md instructions.

No user requirements were lost in the simplification.
