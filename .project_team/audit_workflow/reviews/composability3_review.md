# Composability Review -- Specification v7

**Reviewer:** Composability Leadership Agent
**Date:** 2026-04-13
**Verdict:** STRONG APPROVE with minor recommendations

---

## Executive Summary

v7 is a well-decomposed, composable design. The single-file Python approach (audit.py) with a clean CLI boundary between Python and agents is the right call. The SQLite schema is sound. The 4-role division maps cleanly to responsibilities. I have a few composability concerns around CLI ergonomics and a missing seam, but nothing structural.

---

## 1. audit.py Decomposition: GOOD

The CLI commands form a clean CRUD-like interface over the database:

| Command | Role | Pattern |
|---------|------|---------|
| `extract` | Writer | ETL into messages table |
| `unclassified` | Reader | Feed for classifier |
| `corrections` | Reader | Feed for judge |
| `store-classification` | Writer | Classifier writes back |
| `store-suggestion` | Writer | Judge writes back |
| `update-suggestion` | Writer | Critic/auditor write back |
| `status` | Reader | Dashboard |

This is a proper command-query separation. Each command does one thing. Agents never need to understand SQLite -- they only interact through the CLI. This is the right seam.

**One concern:** At ~300 lines, this is feasible as a single file. But watch the `extract` command -- it absorbs JSONL parsing, chicsession integration, pre-filtering, dedup hashing, context window extraction, phase inference, and incremental skip logic. That's 6+ responsibilities in one subcommand. If it pushes past 150 lines for `extract` alone, consider splitting the JSONL parser into a private helper module (`_parser.py`) alongside `audit.py`. The CLI surface stays the same -- this is an internal decomposition, not an API change.

---

## 2. SQLite Schema: SOUND

5 tables, each with a clear purpose:

- **messages** -- immutable fact store (extraction output)
- **classifications** -- append-only (classifier output)
- **suggestions** -- mutable lifecycle (judge -> critic -> auditor -> apply)
- **suggestion_evidence** -- join table (many-to-many)
- **processed_files** -- incremental tracking (bookkeeping)

This is the right number. I specifically checked for over-normalization and under-normalization:

- **Not over-normalized:** No separate `sessions` or `agents` tables. Good -- those would add JOINs for no benefit since session_id and agent_name are just string attributes.
- **Not under-normalized:** Classifications are a separate table from messages (not a column on messages). Good -- this preserves the clean "messages are immutable extraction output, classifications are agent decisions" boundary.

**The suggestion_evidence join table is important.** It enables the critic to trace back from a suggestion to its supporting corrections, and it lets the judge cite evidence without denormalizing. This is a composability enabler -- without it, suggestions would be opaque blobs.

**Minor schema note:** The `suggestions` table mixes judge output (artifact_type through priority), critic output (critic_verdict, critic_reasoning), and auditor output (apply_status, applied_at). This is pragmatic for a single-table approach, but if you ever need to support re-judging or re-critiquing the same suggestion, you'd want to split these into separate tables. For v1, this is fine.

---

## 3. Agent-Python Interaction: CLEAN

The interaction pattern is:

```
Agent -> reads JSON from stdout <- audit.py query
Agent -> calls audit.py store-* -> writes to DB
```

This is a pipe-friendly, Unix-philosophy design. Agents never hold database connections. Python never holds conversation state. Clean separation.

**One composability issue: store-classification is chatty.** The classifier must call `store-classification` once per message. For 100 unclassified messages, that's 100 subprocess invocations. Each one opens SQLite, inserts one row, closes.

**Recommendation:** Add a `store-classifications` (plural) command that accepts a JSON array of `[{message_id, is_correction, category, confidence}, ...]` on stdin. The classifier can then batch all classifications in one call. The singular form stays for simple cases. This is backward-compatible and cuts subprocess overhead by 10-100x.

Same applies to `store-suggestion` -- the judge likely generates multiple suggestions. A batch `store-suggestions` accepting a JSON array would be cleaner.

---

## 4. Incremental Processing: COMPOSES WELL

The incremental design is sound:

1. `processed_files` tracks size+mtime for file-level skip
2. `INSERT OR IGNORE` with dedup hash for message-level skip
3. `classifications` table JOIN exclusion for classification-level skip
4. Suggestions always read ALL corrections (intentional -- full-dataset analysis)

This means you can run the workflow repeatedly and it converges:
- First run: extracts 100 messages, classifies 100, generates 5 suggestions
- Second run (no new sessions): extracts 0, classifies 0, regenerates suggestions from 100 corrections (might find new patterns)
- Third run (10 new sessions): extracts 47 new messages, classifies 47, regenerates from 147 corrections

**This is the right incremental model.** Extraction and classification are incremental (don't redo work). Suggestion generation is always full-pass (sees all evidence). The critic is also full-pass on new suggestions.

**One edge case to document:** If a JSONL file is appended to (new messages added to existing session), the size+mtime check triggers re-processing, but `INSERT OR IGNORE` deduplicates existing messages. This is correct but should be documented -- the `messages_extracted` count in `processed_files` will be overwritten with the total, not incremented. Not a bug, but potentially confusing in `status` output.

---

## 5. Role Division: WELL-MOTIVATED

| Role | Responsibility | Model | Why Separate |
|------|---------------|-------|-------------|
| Classifier | Per-message yes/no + category | Haiku | High volume, low complexity -- cheap model |
| Judge | Pattern analysis + suggestion generation | Default | Needs to read workflow files, reason about fixes |
| Critic | Validation of suggestions | Default | Adversarial separation from judge |
| Auditor | Orchestration + user interaction + file edits | Default | Needs tool access (Read/Edit), user trust |

The classifier-judge split is the key composability decision. It means:
- Classifier can be swapped for a different model or even regex-only without touching judge logic
- Judge always operates on the same input format (classified corrections) regardless of how they were classified
- You can re-run classification with a better model without re-extracting

The critic-judge separation enforces adversarial review. Good -- without it, the judge would self-validate.

The auditor as orchestrator is correct. It's the only role that talks to the user and edits files.

**No missing roles.** I considered whether a "reporter" role should be separate from auditor, but the report phase is just queries + presentation -- no heavy reasoning. Auditor handles it fine.

---

## 6. Coupling Analysis

**Low coupling (good):**
- Agents couple only to the CLI interface, not to Python internals
- Database schema is the contract between phases
- Each phase reads from DB and writes to DB -- no direct phase-to-phase data passing

**Acceptable coupling:**
- `extract` command depends on `claudechic.chicsessions` for modes 1 and 2. This is necessary and well-isolated (mode 3 has no dependency).
- Judge depends on knowing workflow file paths. This is inherent to its job.

**One coupling concern:** The advance checks in the workflow manifest use `audit.py status` output with grep. This couples the manifest to the exact text format of `status` output. If the status output format changes, advance checks break silently.

**Recommendation:** Add a `audit.py check <check_name>` command that returns exit code 0/1 for specific checks:
```
python scripts/audit/audit.py check has-messages      # exit 0 if messages > 0
python scripts/audit/audit.py check all-classified     # exit 0 if unclassified = 0
python scripts/audit/audit.py check all-reviewed       # exit 0 if unreviewed = 0
python scripts/audit/audit.py check all-decided        # exit 0 if pending = 0
```

This replaces fragile `status | grep` patterns with purpose-built checks. The `status` command remains for human consumption. The advance checks become:
```yaml
advance_checks:
  - type: command-output-check
    command: "python scripts/audit/audit.py check has-messages"
    expected: "ok"
```

---

## 7. Missing Seams

**7.1 No way to reset/re-classify.** If the classifier produces bad results (wrong model, bad prompt), there's no `audit.py reset-classifications` command. You'd need to manually DELETE from the SQLite database. Add a `reset` command:
```
python scripts/audit/audit.py reset classifications    # DELETE FROM classifications
python scripts/audit/audit.py reset suggestions        # DELETE FROM suggestions + suggestion_evidence
```

This is important for iterability -- the team WILL need to tune the classifier prompt and re-run.

**7.2 No dry-run for extract.** `extract` immediately writes to the database. A `--dry-run` flag that reports what WOULD be extracted (file count, estimated message count) without writing would help debugging. Low priority but useful for composability -- it lets you validate the discovery step independently of the storage step.

---

## 8. Template Composability

The spec says this ships in both root repo AND generated projects. Two concerns:

**8.1 `scripts/audit/` path assumption.** Generated projects may not have a `scripts/` directory. The CLI commands hardcode `python scripts/audit/audit.py`. If copier generates the project into a different structure, all the agent markdown files need path updates.

**Recommendation:** The workflow manifest should define the script path once, and agent markdown should reference it symbolically. Or: make audit.py invocable as `python -m scripts.audit.audit` so it's package-relative.

**8.2 chicsession import.** `from claudechic.chicsessions import ChicsessionManager` -- this import must be available in generated projects. Confirm that claudechic is always installed (editable or otherwise) in generated project environments. If not, modes 1 and 2 should gracefully degrade with a clear error.

---

## 9. Summary of Recommendations

| # | Priority | Recommendation |
|---|----------|---------------|
| 1 | Medium | Add batch `store-classifications` and `store-suggestions` commands (JSON array on stdin) |
| 2 | Medium | Add `audit.py check <name>` commands to replace fragile `status | grep` in advance checks |
| 3 | Low | Add `audit.py reset classifications|suggestions` for iterability |
| 4 | Low | Watch `extract` command size -- split parser if it exceeds ~150 lines |
| 5 | Low | Add `--dry-run` to `extract` |
| 6 | Info | Document JSONL append re-processing behavior |
| 7 | Info | Confirm claudechic availability in generated projects for chicsession modes |

---

## 10. Final Assessment

This is a **well-composed design**. The key architectural decisions are correct:

- One Python file with a CLI boundary (not a library API) is the right abstraction for agent interaction
- SQLite as the shared state store between phases is clean and inspectable
- The 4-role split follows natural responsibility boundaries
- Incremental processing composes correctly across re-runs
- The suggestion lifecycle (judge -> critic -> user -> apply) has clear state transitions in one table

The spec is implementation-ready. My recommendations are enhancements, not blockers. Ship it.
