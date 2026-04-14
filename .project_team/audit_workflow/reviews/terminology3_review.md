# Terminology Review -- Specification v7

**Reviewer:** Terminology agent
**Date:** 2026-04-13
**Verdict:** APPROVE with 3 minor issues

---

## 1. Role Names: classifier, judge, critic, auditor

**Status: CLEAN -- no collisions.**

All four names are unique across the codebase:
- No existing workflow uses any of these as role IDs.
- Existing roles use different naming patterns (coordinator, researcher, skeptic, implementer, learner, etc.).
- "auditor" is the only one that could conceivably overlap with general English usage in the codebase, but it does not appear as a defined role anywhere.

**Semantic clarity:**
- **classifier** -- clear, unambiguous. Does one thing (categorize messages).
- **judge** -- clear. Generates suggestions based on evidence. The legal metaphor (judge reviews evidence, renders judgment) works well.
- **critic** -- clear. Validates another agent's output. Distinct from "skeptic" (used in project_team workflow) because critic has a formal 3-verdict system, while skeptic is a general review role.
- **auditor** -- clear as orchestrator. The workflow is called "audit" so "auditor" as the main role is natural.

**One concern:** "judge" and "critic" are close in connotation (both evaluate). The spec differentiates them well (judge = generate suggestions, critic = validate suggestions), but the names alone could confuse someone skimming. The current role descriptions in the manifest (Section 11) disambiguate adequately. No change needed -- just noting it.

---

## 2. SQLite Table Names

**Status: CLEAN -- well-chosen.**

| Table | Assessment |
|-------|-----------|
| `messages` | Standard. Does NOT collide with claudechic's `messages.py` module -- that module defines message *types* (ResponseComplete, ToolUseMessage, etc.), not a "Message" class. The audit `messages` table stores raw extracted text, which is a different domain. No confusion risk. |
| `classifications` | New term. Not used anywhere in claudechic. Clear plural of "classification." |
| `suggestions` | New term. Not used anywhere in claudechic. Clear. |
| `suggestion_evidence` | Junction table. Name follows standard `<parent>_<child>` convention. |
| `processed_files` | Descriptive, no collision. |

**No issues.**

---

## 3. CLI Command Names

**Status: MINOR ISSUE -- one inconsistency.**

| Command | Assessment |
|---------|-----------|
| `extract` | Clear verb. No collision. |
| `unclassified` | Adjective used as noun. Works as a filter/query name. |
| `corrections` | See issue below. |
| `store-classification` | Verb-noun. Clear. |
| `store-suggestion` | Verb-noun. Consistent with above. |
| `update-suggestion` | Verb-noun. Consistent. |
| `status` | Standard. |

**Issue T1 (minor): "corrections" vs "correction" inconsistency.**

- The CLI command is `corrections` (plural noun, returns a list).
- The database table is `classifications` (not `corrections`).
- The taxonomy section is called "Classification Taxonomy."
- But the *concept* of a correction is: a message where `is_correction = 1`.

This is actually fine -- `corrections` is a filtered view (classified messages where is_correction=1), not a table name. The command name makes sense as "give me the corrections." No change needed, but the spec should be consistent about whether "correction" is a first-class noun or just a boolean flag on a classification. Currently it is used both ways, which could be slightly confusing.

**Recommendation:** Add a one-line glossary entry in Section 1 or a new Section 1.1: "A **correction** is any message classified with `is_correction = 1`. The `corrections` CLI command returns these."

---

## 4. Collision Check with Existing Terms

### Existing claudechic/template terms (from CLAUDE.md Terminology section):

| Existing Term | Audit Spec Usage | Collision? |
|---------------|-----------------|------------|
| **Message** | `messages` table stores extracted user text | **No collision.** Claudechic's `messages.py` defines typed message objects for the TUI pipeline. The audit `messages` table is raw JSONL extracts. Different domain, different layer. |
| **Phase** | `phase_id` column, phase names (parse, analyze, suggest, report, apply) | **No collision.** These are new phases within the `audit` workflow. The concept of "phase" is reused correctly per the workflow system's design. |
| **Rule** | `artifact_type = "rule"`, also `rules:` in manifest | **No collision.** The spec uses "rule" exactly as the existing system defines it -- guardrail rules in YAML. Suggestions of type "rule" generate new guardrail rules. Correct usage. |
| **Hint** | `artifact_type = "hint"` | **No collision.** Same as above -- hints are used per the existing hints system. |
| **Check** / **Advance check** | `advance_checks` in manifest, also "6 checks" in critic validation | **Minor ambiguity (T2).** The critic's "6 checks" (specificity, actionability, etc.) are validation criteria, not `advance_checks` in the workflow sense. The spec uses "checks" for both meanings. See recommendation below. |
| **Manifest** | `audit.yaml` referred to as "Workflow manifest" | **No collision.** Correct usage per CLAUDE.md: "Manifest (YAML parsed by ManifestLoader)." |
| **Guardrail rules** vs **agent context files** | Spec correctly targets guardrail rules for suggestions | **No collision.** |
| **Workflow activation** | `/audit` activation | **No collision.** Correct usage. |

**Issue T2 (minor): "checks" is overloaded.**

The word "check" appears in three contexts:
1. **Advance checks** -- workflow system concept (command-output-check, manual-confirm, etc.)
2. **Critic validation checks** -- the 6 criteria the critic evaluates (specificity, actionability, etc.)
3. **Advance checks as a suggestion artifact** -- `artifact_type = "advance-check"` (the judge can suggest new advance checks)

Contexts 1 and 3 are the same concept (good). Context 2 uses "checks" for a different thing (critic evaluation criteria).

**Recommendation:** In Section 9, rename "Six Checks" to "Six Validation Criteria" or "Six Evaluation Criteria." This distinguishes the critic's validation process from the workflow system's advance checks. The section body already calls them by individual names (Specificity, Actionability, etc.), so the header is the only place that needs change.

---

## 5. Vocabulary Consistency

**Status: MINOR ISSUE -- one drift.**

**Issue T3 (minor): "chicsession" capitalization/formatting.**

The spec uses:
- "chicsession" (lowercase, no space) -- 15+ occurrences
- "Chicsession" (capitalized) in `ChicsessionManager`, `ChicsessionEntry` -- these are class names, correct
- "chicsession" in CLI flags: `--chicsession NAME`
- "chicsessions" (plural) in file paths: `.chicsessions/*.json`

This is consistent with CLAUDE.md's rule that "claudechic is always lowercase." By extension, "chicsession" should always be lowercase except in class names. The spec follows this correctly. **No issue.**

**Vocabulary audit -- terms used consistently throughout:**

| Term | Occurrences | Consistent? |
|------|-------------|-------------|
| correction | ~30 | Yes -- always means "user correcting agent behavior" |
| classification | ~15 | Yes -- always means "the act/result of classifying a message" |
| suggestion | ~25 | Yes -- always means "a proposed workflow artifact change" |
| verdict | ~10 | Yes -- always means critic's APPROVE/FLAG/REJECT decision |
| evidence | ~8 | Yes -- always means "corrections supporting a suggestion" |
| artifact | ~10 | Yes -- always means "workflow file (phase markdown, rule, hint, check)" |
| boilerplate | ~5 | Yes -- always means "system messages to skip" |
| extraction | ~5 | Yes -- always means "parsing JSONL into messages table" |

**The vocabulary is minimal and consistent.** No unnecessary synonyms detected. The spec does not use "pattern" (the old mine_patterns.py term) except in the regex section (6.3), where it correctly refers to regex patterns, not the old "correction pattern" concept. Clean break.

---

## Summary

| ID | Severity | Issue | Recommendation |
|----|----------|-------|----------------|
| T1 | Minor | "correction" used as both boolean flag and first-class noun | Add glossary line defining "correction" |
| T2 | Minor | "checks" overloaded (advance checks vs critic validation checks) | Rename Section 9 "Six Checks" to "Six Validation Criteria" |
| T3 | Note | -- | No action needed, just confirming chicsession casing is correct |

**Overall:** The terminology is clean, minimal, and well-differentiated from existing claudechic concepts. The four role names have zero collisions and good semantic clarity. The SQLite schema uses standard, unsurprising names. The two minor issues (T1, T2) are low-risk but worth fixing for precision.
