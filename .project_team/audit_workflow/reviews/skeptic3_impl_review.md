# Skeptic Implementation Review -- audit.py + db.py + audit.yaml

**Reviewer**: Skeptic (Leadership Agent)
**Date**: 2026-04-13
**Files**: `scripts/audit/db.py` (706 lines), `scripts/audit/audit.py` (1181 lines), `workflows/audit/audit.yaml` (99 lines)
**Verdict**: SOLID IMPLEMENTATION -- all 3 blockers addressed, most risks mitigated. A few remaining issues.

---

## Blocker Resolution Scorecard

| Blocker | Status | Notes |
|---------|--------|-------|
| B1: No "current chicsession" API | FIXED | Collapsed into `--sessions NAME` and `--all`. Added `list-sessions` command for discovery. Clean solution. |
| B2: 300-line estimate unrealistic | CONFIRMED | audit.py is 1181 lines, db.py is 706 lines. Total: ~1887 lines. The split into two files was the right call. |
| B3: N+1 store-classification | FIXED | `store-classifications` and `store-suggestions` both read JSON arrays from stdin. Batch by design. |

## Risk Mitigation Scorecard

| Risk | Status | Notes |
|------|--------|-------|
| R1: Regex dormant | FIXED | Regex runs during `extract`, stores `regex_score` and `regex_indicator` on every message. Exposed in `unclassified` and `corrections` output. |
| R2: JSONL append re-parse | PARTIAL | `last_offset` column exists in schema but is never written or read. Still does full re-parse on mtime change. See Issue 1 below. |
| R3: WAL Windows fallback | FIXED | Lines 131-143 of db.py: try WAL, catch OperationalError, fall back to DELETE on win32. Correct. |
| R4: Large JSON payloads | FIXED | `chunk_size` parameter (default 200) on both `query_unclassified` and `query_corrections`. Returns `has_more` flag. |
| R5: Cost estimate | N/A | Documentation concern, not code. |

---

## Remaining Issues

### Issue 1: last_offset Column Is a Dead Letter (Low)

The column exists in the schema (db.py line 89) but `upsert_processed_file` (line 168-188) never writes it, and the incremental skip check (audit.py lines 558-564) doesn't use it. This is fine for v1 -- the column is there for future use -- but it should either have a comment saying "reserved for v2 incremental offset tracking" or actually be wired up.

**Severity**: Low. The full re-parse with INSERT OR IGNORE is correct, just slower than necessary for large appended files.

### Issue 2: `from scripts.audit import db` Requires sys.path Setup (Medium)

Every command function does `from scripts.audit import db` as a late import. This works when invoked as `python scripts/audit/audit.py` from the project root (because Python adds the script's parent-parent to path via `__main__`). But it will **fail** if:
- Invoked from a different working directory: `python /abs/path/to/scripts/audit/audit.py`
- Invoked as a module: `python -m scripts.audit.audit`

The `PROJECT_ROOT` is computed (line 36) but never added to `sys.path` for the `scripts.audit` package import. The claudechic import (line 481) correctly does `sys.path.insert(0, ...)` but the local `db` import has no equivalent.

**Fix**: Add `sys.path.insert(0, str(PROJECT_ROOT))` near line 37, or change to a relative import: `from . import db`.

### Issue 3: Advance Check `pattern` vs `expected` Key (Medium)

The audit.yaml advance checks use:
```yaml
command: "python scripts/audit/audit.py check has-messages --json"
pattern: "\"pass\":\\s*true"
```

But the spec (v7 Section 11) used `expected:` not `pattern:`. Need to verify which key the `ManifestLoader` / `command-output-check` actually expects. If the engine expects `expected` (exact string match), then `pattern` (regex match) may be silently ignored, and the checks would pass vacuously.

Looking at the `.claude/rules/manifest-yaml.md`, advance check types include `command-output-check` but the exact field names aren't documented there. This needs verification against the claudechic check execution code.

**Fix**: Verify which field the engine actually reads. If it's `expected`, the checks need rewriting to match exact output. If it's `pattern`, the current implementation is correct and the spec was wrong.

### Issue 4: `_count()` Uses f-string Table Name -- SQL Injection (Very Low)

```python
def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
```

The `# noqa: S608` acknowledges this. All callers pass hardcoded table names ("messages", "classifications", etc.) so there's no actual injection risk. But if this function were ever exposed to user input, it would be dangerous. The noqa suppression is correct for now.

### Issue 5: `check_all_classified` Math Can Go Negative (Very Low)

```python
unclassified = non_boilerplate - classified
```

If somehow there are more classifications than non-boilerplate messages (e.g., a boilerplate message was classified before being marked as boilerplate), `remaining` would be negative, and the check would pass (`remaining <= 0`). The `<=` handles this correctly, so it's not a bug, but the status dashboard would show a negative unclassified count.

**Fix**: `max(0, non_boilerplate - classified)` in `get_status`.

### Issue 6: `store_suggestions` Not Atomic Per Suggestion (Low)

In `db.store_suggestions` (lines 458-492), each suggestion is inserted individually in a loop with `conn.execute`, then evidence links are inserted. If the process crashes mid-batch, some suggestions will be stored and others won't. The final `conn.commit()` is at the end, which means **all or nothing** at the transaction level -- actually, this is fine. The `conn.commit()` at line 492 commits the entire batch atomically.

Wait -- actually there's a subtlety. `conn.executemany` in `insert_messages` implicitly starts a transaction. But the individual `conn.execute` calls in `store_suggestions` -- are they auto-committed? No: Python's sqlite3 module uses implicit transactions. The `conn.commit()` at the end commits all inserts atomically. This is correct.

### Issue 7: `context_before`/`context_after` Can Be Huge (Medium)

The context window extraction (audit.py lines 591-596) captures the FULL text of adjacent assistant messages. An assistant message can be thousands of tokens (code generation, long explanations). These get stored in SQLite and then dumped in the JSON output for `unclassified` and `corrections`.

When the classifier agent receives 200 messages, each with potentially 5KB of context_before and 5KB of context_after, that's up to 2MB of JSON. Multiplied by the chunking, this could exhaust agent context.

**Recommendation**: Truncate context_before and context_after to ~500 characters each during extraction. The classifier needs enough context to judge tone, not the full code output. Add a `--full-context` flag for cases where truncation loses important information.

### Issue 8: No `--mode all` for Non-Chicsession JSONL (Design Choice)

The spec had three modes: current session, saved chicsession, all local conversations. The implementation only supports chicsession-based extraction (`--sessions` or `--all` chicsessions). There's no `--mode all` that scans `~/.claude/projects/` for raw JSONL files without chicsession context.

This is actually a reasonable simplification -- chicsession context is valuable and the uncontextualized mode was the weakest. But it means users who haven't used chicsessions (or whose chicsessions are stale) can't audit at all.

**Verdict**: Acceptable for v1. Document that chicsession context is required.

---

## What's Good

1. **db.py is clean and well-structured.** Separation of concerns is excellent. Every function does one thing. The check functions return (bool, str) tuples that work for both JSON and text output.

2. **Batch stdin pattern works.** `store-classifications` and `store-suggestions` read from stdin, parse JSON, batch insert. This was the critical fix from the review.

3. **Regex is active and integrated.** Runs during extraction, scores stored on messages, exposed in query output. The classifier gets regex signals as supplemental context. This was the #1 risk recommendation.

4. **`list-sessions` command is smart.** It shows unanalyzed sessions first, includes message estimates from file size heuristics, and shows correction counts for already-processed sessions. This gives the auditor agent good data for the session picker UX.

5. **`aggregate` command is a bonus.** Not in the original spec. Groups corrections by category+phase with top examples and all message IDs. This is exactly what the judge needs -- pre-digested patterns rather than raw corrections.

6. **`reset` command with `--confirm` guard.** Lets the workflow re-iterate (re-classify with different prompts, re-generate suggestions) without re-parsing JSONL. Good for tuning.

7. **`check` commands with `--json` flag.** Advance checks in the YAML use `--json` and match against a regex pattern. Much more robust than grepping status output.

8. **Cross-platform compliance.** `encoding='utf-8'` on file opens, `pathlib.Path` everywhere, `.as_posix()` for stored paths, no emoji/non-ASCII. `sys.platform` check on WAL fallback.

---

## Summary

| # | Issue | Severity | Effort |
|---|-------|----------|--------|
| 1 | last_offset column unused | Low | Zero (add comment) or Low (wire up) |
| 2 | `from scripts.audit import db` path dependency | Medium | 1 line fix |
| 3 | advance check `pattern` vs `expected` key | Medium | Needs verification |
| 4 | f-string table name in _count | Very Low | Already suppressed |
| 5 | Negative unclassified count edge case | Very Low | 1 line fix |
| 6 | store_suggestions atomicity | Non-issue | Already correct |
| 7 | Unbounded context_before/context_after | Medium | ~5 lines to truncate |
| 8 | No non-chicsession scan mode | Design choice | Acceptable for v1 |

**Overall**: This is a strong implementation. The three blockers from my spec review are all properly addressed. The batch stdin pattern, active regex scoring, chunked output, and WAL fallback are all present and correct. Issues 2, 3, and 7 are the ones worth fixing before shipping. The rest can wait.
