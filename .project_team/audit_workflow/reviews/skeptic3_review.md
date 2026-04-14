# Skeptic Review -- Specification v7

**Reviewer**: Skeptic (Leadership Agent)
**Date**: 2026-04-13
**Verdict**: CONDITIONAL APPROVE -- 3 blockers, 5 significant risks, several minor issues

---

## Blockers (Must Fix Before Implementation)

### B1. `--mode current` Has No API -- The Happy Path Is Broken

The spec's first UX option ("1. Current session -- audit the active chicsession") requires knowing which chicsession is currently active. **There is no such API.** `ChicsessionManager` exposes `save()`, `load(name)`, and `list_chicsessions()`. There is no `get_active()` or equivalent. The `active_agent` field on `Chicsession` tells you which agent *within* a session is active, not which session is active in the process.

The only place "current" chicsession is tracked is `_chicsession_name` on the app's command handler -- a private runtime attribute, not persisted, not accessible from an external Python script.

**Impact**: Mode 1 (the default, most intuitive option) literally cannot work as specified.

**Fix options**:
- (a) Have the auditor agent ask the user to pick from `list_chicsessions()` for both modes 1 and 2 (collapse them).
- (b) Have claudechic persist the active session name to a file (`.chicsessions/.active`). Requires a claudechic change.
- (c) Accept that `--mode current` means "the chicsession this audit workflow is running inside of" and have the auditor pass its own chicsession name. But the audit workflow itself may not have one.

### B2. ~300 Lines Is Fantasy -- Real Estimate Is 500-700

`mine_patterns.py` is **1229 lines**. The spec absorbs:
- JSONL parser (`parse_session`, `_extract_text`, `_detect_version`, Message dataclass) -- ~140 lines
- Session discovery (`discover_session_files`) -- ~30 lines
- Pattern banks (4 regex banks, optional but "absorbed") -- ~70 lines
- `tier1_score_message` (optional but "absorbed") -- ~80 lines

That's ~320 lines of absorbed code before writing a single new line. Now add:
- SQLite schema creation + migration -- ~40 lines
- 7 CLI commands with argparse -- ~80 lines
- Incremental file tracking logic -- ~30 lines
- Chicsession integration (load, resolve session_ids to paths) -- ~40 lines
- Pre-filter logic -- ~20 lines
- 3-message context window extraction -- ~30 lines
- Phase transition extraction -- ~40 lines
- Dedup hash computation -- ~15 lines
- `store-classification`, `store-suggestion`, `update-suggestion` -- ~50 lines
- `status` dashboard queries -- ~30 lines
- Imports, constants, error handling -- ~30 lines

**Conservative total: 600+ lines.** With proper error handling and cross-platform guards, 700 is more realistic. A 300-line estimate sets the implementor up to either cut corners or feel like they're failing.

**Fix**: Update the estimate to ~600 lines. Or split into 2 files: `audit_db.py` (schema + queries, ~200 lines) and `audit.py` (CLI + extraction, ~400 lines). The "one file" constraint is arbitrary and hurts maintainability at this size.

### B3. One-at-a-Time store-classification Is an N+1 Antipattern

The classifier must call `audit.py store-classification <id> <0|1> [cat] [conf]` once per message. For 300 unclassified messages, that's 300 subprocess invocations. Each one:
1. Spawns a Python process
2. Imports sqlite3
3. Opens the database
4. Runs one INSERT
5. Exits

At ~200ms per subprocess on macOS (more on Windows), that's **60+ seconds** just for the store calls. This is the single largest performance bottleneck in the entire pipeline.

**Fix**: Add a `store-classifications` (plural) command that accepts a JSON array via stdin:
```
echo '[{"id": 42, "is_correction": 1, "category": "factual_correction", "confidence": "high"}, ...]' | python scripts/audit/audit.py store-classifications
```
Same for `store-suggestion` (batch mode). This is trivial to implement and eliminates the bottleneck entirely.

---

## Significant Risks

### R1. LLM Classifier as Sole Detector -- POC Says Otherwise

The POC findings are unambiguous: regex and GLiClass had **zero overlap** on the full corpus. They catch completely different things. The spec acknowledges this (Section 6.3: "Regex can be activated in v2") but then makes regex dormant.

POC regex-only catches that Haiku will also likely miss:
- "No the bug report I said in sprustonlab!" (keyword: "said")
- "that is not what I asked for" (strong negation pattern)
- "pytest-cov is not running on the right thing, i said to focus on claudechic" (keyword: "said" + "not")

These are textbook corrections with clear keyword signals. Haiku might catch some of them, but the POC proved that even the large GLiClass model (stronger than Haiku at this narrow task) missed them.

**Risk**: You are shipping with one eye closed. The regex patterns are already written, already absorbed, and cost zero API calls.

**Recommendation**: Run regex during `extract` (it's 13ms for 309 messages). Store a `regex_score` column on `messages`. Let the classifier agent see it as a supplemental signal. This is 10 lines of code.

### R2. JSONL Append Growth Makes Incremental Processing Expensive

The spec says: "If file is new or changed: parse all messages, INSERT OR IGNORE (dedup by hash)."

JSONL files are append-only logs. Every new conversation turn appends lines. A session with 500 turns that gets 1 new turn triggers a full re-parse of all 500+ lines, followed by 499 `INSERT OR IGNORE` failures and 1 successful insert.

For `--mode all` scanning dozens of active session files, this means re-parsing the same data repeatedly on every audit run.

**Fix**: Store `last_processed_offset` (byte position) in `processed_files` instead of (or alongside) `file_size`. On re-process, seek to the last offset and parse only new lines. JSONL's append-only nature makes this safe. Falls back to full re-parse if file shrinks (truncation/rotation).

### R3. SQLite on Windows -- WAL Mode and Path Length

Two Windows-specific SQLite issues:

1. **WAL mode requires shared memory**: WAL uses a `-shm` file via `mmap`. On network drives and some Windows configurations, `mmap` fails silently or throws. The spec stores the DB at `.audit/corrections.db` (project-local), which is usually fine, but if the project is on OneDrive, a mapped drive, or a UNC path, WAL will break.

2. **Path length**: `.audit/corrections.db-wal` and `.audit/corrections.db-shm` add suffixes. If the project path is already long (common on Windows with nested user directories), you can hit MAX_PATH. The `.audit/` directory name is fine, but worth noting.

**Mitigation**: Add a fallback: try WAL mode, catch the `OperationalError`, fall back to `journal_mode=DELETE` with a warning. This is 5 lines.

### R4. Four Agents Sharing State via CLI Subprocess Calls

The data flow is: auditor spawns classifier, classifier calls `audit.py store-classification` N times, auditor spawns judge, judge calls `audit.py store-suggestion` M times, auditor spawns critic, critic calls `audit.py update-suggestion` P times.

Every handoff is: agent reads stdout JSON -> reasons about it -> invokes Bash tool -> subprocess -> Python -> SQLite -> exit. The chain of things that can go wrong:

- **JSON too large for Bash tool**: `audit.py corrections` dumps ALL accumulated corrections as a JSON array to stdout. With 500+ corrections, this could be 200KB+ of text that the agent must hold in context.
- **Agent misparses CLI output**: Agents call store-classification with positional args. One misplaced quote or space and the command fails silently (spec says "Fails silently on duplicate").
- **No handshake**: The auditor has no way to verify the classifier actually processed all messages. It checks `status` for `unclassified: 0`, but if the classifier crashed mid-way, some messages are classified and some aren't. The advance check passes as long as unclassified = 0 (it won't be).

Actually, that last point is fine -- the advance check catches partial completion. But the first two are real.

**Recommendation**: Add `--limit N` not just to `unclassified` but pipe output through a size check. If > 100 messages, chunk automatically. The classifier should process in batches of 50.

### R5. Cost Estimate Is Misleading

"Haiku is ~$0.005/session" -- this is not meaningful without defining what a "session" contains. A session with 300 messages, each with 3-message context windows (~500 tokens each), means ~150K input tokens per classification pass. Haiku at $0.25/MTok input = $0.0375 per session. For `--mode all` with 76 sessions (the POC corpus), that's ~$2.85 for a single full audit.

Not expensive in absolute terms, but 570x the claimed cost. And it recurs: the spec says "Agents always see the full accumulated dataset" -- meaning the judge agent reads ALL corrections every run, and the context only grows.

**Fix**: State honest cost estimates. Add `--limit N` to `unclassified` (already there) and document that batching controls cost. Consider: should already-classified messages be re-classified when the user runs audit again? Currently no (dedup), which is correct, but worth stating explicitly.

---

## Minor Issues

### M1. Phase Mapping Will Be Wrong More Often Than Right

Phase inference from JSONL transition markers requires scanning for `advance_phase` tool calls, `"Advanced to phase:"` strings, and `/advance` commands. But:
- Sub-agents don't advance phases -- the orchestrator does
- JSONL files are per-agent, so the sub-agent's JSONL won't contain the phase transitions
- The chicsession fallback gives you the *current* phase at save time, not the phase at each message's time

For `--mode all` (no chicsession), phase_confidence will be "unknown" for almost everything.

**Impact**: The judge gets phase data it can't trust. The spec has `phase_confidence` to handle this, which is good, but the judge instructions (suggest.md) must be very explicit about not weighting "unknown" phase data.

### M2. No Database Migration Strategy

The schema is version 1. What happens when v2 adds `regex_score` to `messages` or a new table? The spec has no migration plan. Users will have accumulated data they don't want to lose.

**Fix**: Add a `schema_version` table (single row). On startup, check version and run migrations. Standard pattern, ~20 lines.

### M3. `store-suggestion` Accepts Raw JSON String as CLI Arg

```
python scripts/audit/audit.py store-suggestion '{"artifact_type": "phase-markdown", ...}'
```

Shell escaping of JSON in a CLI positional argument is fragile, especially on Windows where single quotes don't work. The JSON may contain quotes, newlines, special characters.

**Fix**: Accept JSON via stdin: `echo '...' | python scripts/audit/audit.py store-suggestion --stdin`. Or accept a file path.

### M4. `corrections_report.json` in Repo Root

The grep results show a `corrections_report.json` in the repo root. This appears to be an artifact from mine_patterns.py. Should be in `.gitignore` and cleaned up during the mine_patterns.py deletion.

### M5. Advance Check Fragility

The advance checks parse `audit.py status` output with grep:
```yaml
command: "python scripts/audit/audit.py status 2>/dev/null | grep unclassified"
expected: "unclassified: 0"
```

This couples the advance check to the exact formatting of status output. If status outputs `  unclassified: 0` (leading space) or `Unclassified: 0` (capitalized), the check fails. The status command should have a `--json` flag for machine-readable output, or the advance checks should use a dedicated query command.

### M6. No Rollback for Apply Phase

If the apply phase edits 5 files and the 3rd edit breaks something, there's no rollback. The user is told "Please review the diffs" but the damage is done.

**Recommendation**: The auditor should create a git stash or commit before applying. Or at minimum, document that the user should be on a clean branch.

---

## What's Actually Good

To be fair:
- **SQLite as the persistence layer** is the right call. It's the correct tool for structured, queryable, incremental data.
- **3-message context windows** are smart. The POC showed context matters enormously for classification.
- **Critic agent as validation gate** catches the hallucination problem (bad file paths, vague suggestions).
- **The boilerplate pre-filter list** is thorough and directly informed by POC findings.
- **Incremental by design** is correct architecture. Parse once, query forever.
- **Category taxonomy** is well-scoped. Six categories with clear fix mappings avoid the over-classification trap the POC identified.

---

## Summary

| # | Issue | Severity | Effort to Fix |
|---|-------|----------|---------------|
| B1 | No "current chicsession" API | Blocker | Medium (needs design decision) |
| B2 | 300-line estimate is 2x too low | Blocker | Zero (just update the number) |
| B3 | N+1 store-classification calls | Blocker | Low (add batch command) |
| R1 | Regex dormant despite POC evidence | Significant | Low (10 lines) |
| R2 | Full re-parse on JSONL append | Significant | Low (byte offset tracking) |
| R3 | WAL mode Windows edge cases | Significant | Low (5-line fallback) |
| R4 | Large JSON payloads in agent context | Significant | Low (chunking) |
| R5 | Cost estimate off by 570x | Significant | Zero (fix the docs) |
| M1 | Phase mapping unreliable for sub-agents | Minor | Low (document in suggest.md) |
| M2 | No schema migration | Minor | Low (~20 lines) |
| M3 | JSON-in-CLI-arg fragility | Minor | Low (stdin mode) |
| M4 | Stale corrections_report.json | Minor | Zero (delete + gitignore) |
| M5 | Advance checks coupled to output format | Minor | Low (--json flag) |
| M6 | No rollback in apply phase | Minor | Low (git stash) |

The architecture is sound. The database-centric approach with agent orchestration is the right pattern. But three things will fail on first contact with reality: the nonexistent "current session" API, the implementor hitting 600 lines and wondering what went wrong, and the classifier spending a minute on subprocess overhead instead of actual classification. Fix those three, and this ships.
