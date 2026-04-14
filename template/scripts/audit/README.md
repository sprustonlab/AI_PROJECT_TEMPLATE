# scripts/audit/

Python helpers for the `/audit` workflow -- a multi-agent pipeline that parses
Claude Code session transcripts, detects user corrections, and generates
machine-applicable suggestions for improving workflows.

Two files: `audit.py` (CLI + JSONL parsing + regex scoring) and `db.py`
(SQLite layer). Both are thin helpers called by agents via subprocess. All
analysis, classification, and suggestion generation happens in the agent roles.

---

## Database

- Location: `.audit/corrections.db`
- Journal mode: WAL (falls back to DELETE on Windows network drives)
- Incremental by design: re-runs only process new or changed sessions
- The database is additive -- accumulated evidence improves suggestions over time

Five tables:

| Table | Purpose |
|-------|---------|
| `messages` | Every user message extracted from JSONL sessions |
| `classifications` | Correction labels from the classifier agent |
| `suggestions` | Improvement suggestions from the judge agent |
| `suggestion_evidence` | Links corrections to the suggestions they support |
| `processed_files` | Tracks JSONL files by size + mtime for incremental skip |

---

## CLI

```
python scripts/audit/audit.py <command> [options]
```

| Command | Description |
|---------|-------------|
| `list-sessions` | Show available chicsessions with DB status (in_db, message counts) |
| `extract` | Parse JSONL files into the database (--sessions NAME,... or --all) |
| `unclassified` | Output unclassified messages as JSON for the classifier agent |
| `corrections` | Output classified corrections as JSON for the judge agent |
| `aggregate` | Group corrections by category and phase for the judge agent |
| `store-classifications` | Read a JSON array from stdin and store classifications |
| `store-suggestions` | Read a JSON array from stdin and store suggestions |
| `update-suggestion` | Update verdict, apply status, or applied timestamp on a suggestion |
| `check` | Run a named advance check (has-db, has-messages, all-classified, all-reviewed, all-decided) |
| `reset` | Clear derived data (classifications or suggestions) with --confirm |
| `status` | Database dashboard: message counts, correction breakdown, suggestion status |

`check` and `status` both accept `--json` for structured output.

---

## Workflow Integration

Activated via `/audit` in claudechic. Definition: `workflows/audit/audit.yaml`.

Four agent roles:

| Role | Model | Responsibility |
|------|-------|----------------|
| `auditor` | Standard | Orchestrates all phases, presents results to user |
| `classifier` | Haiku | Binary correction detection + 6-category labeling |
| `judge` | Standard | Reads aggregated patterns, generates suggestions |
| `critic` | Standard | Validates suggestions against 6 criteria |

Five phases:

| Phase | What happens |
|-------|-------------|
| `parse` | User picks scope; auditor runs `extract` |
| `analyze` | Classifier processes unclassified messages in chunks |
| `suggest` | Judge reads `aggregate` output, generates suggestions; critic validates |
| `report` | Auditor presents approved/flagged suggestions; user decides apply/skip |
| `apply` | Auditor edits target files for approved suggestions |

---

## Cross-Platform

- `encoding='utf-8', errors='replace'` on all file reads
- `pathlib.Path` throughout -- no string path concatenation
- `.as_posix()` for values stored in the database
- ASCII only in all output
- WAL journal mode with Windows fallback to DELETE
