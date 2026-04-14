# Audit Workflow -- Specification v7

---

## 1. Overview

The audit workflow parses JSONL session logs and chicsession snapshots, classifies user corrections using an LLM classifier (Haiku), accumulates results in a persistent SQLite database, and uses specialized agents to generate and apply workflow improvements.

**Core principle:** Agents orchestrate, Python is a thin helper. The `scripts/audit/` package handles JSONL extraction, regex pre-scoring, and database operations. All analysis, classification, suggestion generation, and user interaction happen conversationally through agent roles.

**Incremental by design.** The database grows over time. Re-running after new sessions processes only NEW messages. Agents always see the full accumulated dataset, so suggestions improve as evidence accumulates.

**Replaces:** `scripts/mine_patterns.py` (deleted). All useful functionality (JSONL parsing, regex pattern banks, session discovery) is absorbed into `scripts/audit/`. See Section 6.

**Audience:** Template developers (this repo) AND end users of generated projects.
**Workflow ID:** `audit`
**Roles:** `classifier`, `judge`, `critic`, `auditor` (orchestrator)
**Location:** `workflows/audit/` (root repo) + `template/workflows/audit/` (generated projects)

### 1.1 Glossary

| Term | Definition |
|------|------------|
| **Correction** | A user message that corrects, redirects, or expresses dissatisfaction with the agent's previous action. Detected by the classifier agent and/or regex scoring. |
| **Validation criteria** | The 6 quality criteria the critic agent applies to each suggestion (specificity, actionability, evidence grounding, proportionality, conflict detection, feasibility). Not to be confused with advance checks. |

---

## 2. Invocation UX

1. User types `/audit`
2. Workflow engine shows the standard `ChicsessionScreen` picker -- user picks or creates a workspace chicsession (e.g., "audit-run-1"). This is where the audit workflow saves its state, NOT what gets analyzed.
3. Auditor agent activates in the workspace chicsession
4. In the parse phase, the auditor asks conversationally: **"What would you like to audit?"**
5. User answers in plain text -- e.g., "all sessions", "just the tutorial workflow", "ImplementFeatureX and BugFixY", "the last 3 sessions"
6. Auditor runs `audit.py list-sessions` to see what's available, matches the user's request to chicsession names, and calls `extract` with the right args

No custom picker, no numbered menu. Just a conversation.

**Chicsession metadata access:** `audit.py` imports `ChicsessionManager` from `claudechic.chicsessions`. Each `Chicsession` object has: `name`, `active_agent`, `agents: list[ChicsessionEntry]` (with `name`, `session_id`, `cwd`), and `workflow_state: dict | None` (with `workflow_id` and `current_phase`). The `session_id` on each agent entry is the join key to resolve JSONL files at `~/.claude/projects/<project_key>/<session_id>.jsonl`.

**Cold start:** If no chicsessions exist and no JSONL files are found, the auditor shows: "No sessions found. Run some workflows first, then come back to audit."

**Cost warning:** Before the analyze phase, the auditor reports estimated scope: "Found N new messages to classify. Estimated cost: ~$X (Haiku). Proceed?" The user confirms before classification begins.

---

## 3. Architecture

### 3.1 Data Flow

```
/audit --> [ChicsessionScreen] --> workspace chicsession
                                         |
                                   auditor asks "What would you like to audit?"
                                   user answers conversationally
                                         |
                                         v
  [audit.py list-sessions]         (auditor checks what's available)
  [audit.py extract --sessions NAME1,NAME2 (or --all)]
       |  - Load target chicsession(s) via ChicsessionManager
       |  - Resolve session_ids to JSONL paths
       |  - Skip already-processed files (size + mtime check)
       |  - Parse messages, compute dedup hashes
       |  - Pre-filter system boilerplate
       |  - Run regex scoring on non-boilerplate messages
       |  - Extract 3-message context windows
       |  - Infer phase from JSONL transition markers / chicsession state
       |  - INSERT OR IGNORE into SQLite
       |
       v
  [.audit/corrections.db]  -- persistent, grows over time
       |
       v
  [audit.py unclassified] --> JSON --> [Classifier agent (Haiku)]
       |                                      |
       |                         classifies each message
       |                                      |
       |              [audit.py store-classifications] <-- JSON via stdin
       |
  [audit.py aggregate] --> pattern summary JSON
       |  - GROUP BY category, phase
       |  - Counts, session counts, top examples
       |  - Pure SQL/code, no agent needed
       |
       v
  [Judge agent reads aggregated patterns + workflow definitions]
       |                         generates suggestions
       |                                      |
       |              [audit.py store-suggestions] <-- JSON via stdin
       |
       v
  [Critic agent] validates suggestions in DB
       |
       v
  [Auditor agent] presents to user, applies approved edits
```

### 3.2 Module Structure

```
scripts/
  audit/
    __init__.py            -- empty, enables package imports
    audit.py               -- CLI entry point + orchestration
    db.py                  -- SQLite schema, queries, batch operations (optional split)

workflows/audit/
  audit.yaml               -- Workflow manifest (4 roles, 5 phases)
  classifier/
    identity.md            -- Role: detect corrections using Haiku
    analyze.md             -- Phase: classify unclassified messages
  judge/
    identity.md            -- Role: analyze corrections, generate suggestions
    suggest.md             -- Phase: suggestion generation (examples, schema, anti-patterns)
  critic/
    identity.md            -- Role: validate suggestion quality
    suggest.md             -- Phase: 6 validation criteria, 3 verdicts
  auditor/
    identity.md            -- Role: orchestrate workflow, present to user
    parse.md               -- Phase: run audit.py extract
    report.md              -- Phase: present suggestions, record decisions
    apply.md               -- Phase: edit target files for approved suggestions
```

**File split guidance:** If `audit.py` exceeds ~400 lines, split database operations (schema creation, queries, batch inserts) into `db.py`. The split is along a natural boundary: `audit.py` owns CLI parsing, JSONL extraction, regex scoring, and pre-filtering; `db.py` owns SQLite schema, connection management, and all INSERT/SELECT/UPDATE queries.

---

## 4. SQLite Database Schema

Database file: `.audit/corrections.db`

**Connection setup:** Open with `PRAGMA journal_mode=WAL` for concurrent read safety. On Windows, if WAL fails (e.g., network drives), fall back to `PRAGMA journal_mode=DELETE` with a logged warning.

```sql
-- Every user message ever extracted
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    message_hash TEXT UNIQUE,           -- SHA256(session_id + turn_index + user_text)
    session_id TEXT,
    session_file TEXT,                  -- source JSONL path
    chicsession_name TEXT,             -- which chicsession this came from (nullable)
    turn_index INTEGER,
    user_text TEXT NOT NULL,
    context_before TEXT,                -- agent message immediately before
    context_after TEXT,                 -- agent message immediately after
    regex_score REAL,                  -- tier1_score_message() result (0.0-1.0)
    regex_indicator TEXT,              -- best pattern match label (nullable)
    phase_id TEXT,                      -- inferred from transition markers or chicsession
    phase_confidence TEXT DEFAULT 'unknown',  -- "inferred" | "snapshot" | "unknown"
    agent_name TEXT,                    -- from chicsession entry name
    workflow_id TEXT,                   -- from chicsession workflow_state
    is_boilerplate INTEGER DEFAULT 0,   -- 1 = system message, pre-filtered
    created_at TEXT NOT NULL,           -- ISO timestamp of extraction
    UNIQUE(session_id, turn_index)
);

-- Classification results from classifier agent
CREATE TABLE classifications (
    id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES messages(id),
    is_correction INTEGER NOT NULL,     -- 1 = correction, 0 = normal
    category TEXT,                      -- one of 6 categories (NULL if not correction)
    confidence TEXT,                    -- "high" | "medium" | "low"
    classified_at TEXT NOT NULL,
    UNIQUE(message_id)
);

-- Suggestions from judge agent, validated by critic
CREATE TABLE suggestions (
    id INTEGER PRIMARY KEY,
    artifact_type TEXT NOT NULL,         -- "phase-markdown" | "advance-check" | "rule" | "hint"
    file_path TEXT NOT NULL,            -- relative path to target file
    suggestion_type TEXT NOT NULL,       -- "add" | "modify"
    current_content TEXT,               -- text to replace (NULL if new addition)
    proposed_content TEXT NOT NULL,      -- replacement text or YAML
    insertion_point TEXT,               -- for "add": marker after which to insert
    rationale TEXT NOT NULL,
    evidence_count INTEGER NOT NULL,
    priority INTEGER NOT NULL,          -- 1=critical, 2=high, 3=medium, 4=low
    critic_verdict TEXT,                -- "APPROVE" | "FLAG" | "REJECT" (NULL = unreviewed)
    critic_reasoning TEXT,
    apply_status TEXT DEFAULT 'pending', -- "pending" | "applied" | "skipped"
    created_at TEXT NOT NULL,
    applied_at TEXT
);

-- Which corrections support which suggestion
CREATE TABLE suggestion_evidence (
    suggestion_id INTEGER NOT NULL REFERENCES suggestions(id),
    message_id INTEGER NOT NULL REFERENCES messages(id),
    PRIMARY KEY (suggestion_id, message_id)
);

-- Track processed JSONL files for incremental extraction
CREATE TABLE processed_files (
    file_path TEXT PRIMARY KEY,
    file_size INTEGER NOT NULL,
    file_mtime TEXT NOT NULL,
    messages_extracted INTEGER NOT NULL,
    processed_at TEXT NOT NULL
);
```

---

## 5. audit.py CLI Interface

### 5.1 Commands

```
python scripts/audit/audit.py list-sessions                      # show available chicsessions + DB status
python scripts/audit/audit.py extract --sessions NAME1,NAME2 [--project-dir DIR]
python scripts/audit/audit.py extract --all [--project-dir DIR]
python scripts/audit/audit.py unclassified [--limit N] [--chunk-size N]
python scripts/audit/audit.py corrections [--phase PHASE] [--category CAT] [--min-confidence LEVEL] [--chunk-size N]
python scripts/audit/audit.py aggregate [--min-count N]           # group corrections into patterns
python scripts/audit/audit.py store-classifications              # reads JSON array from stdin
python scripts/audit/audit.py store-suggestions                  # reads JSON array from stdin
python scripts/audit/audit.py update-suggestion ID --field VALUE
python scripts/audit/audit.py check <name>                       # structured advance checks
python scripts/audit/audit.py reset classifications|suggestions  # clear for re-iteration
python scripts/audit/audit.py status
```

### 5.2 `list-sessions` -- Show Available Chicsessions

Lists all chicsessions with metadata and database status. The auditor uses this in the parse phase to present scope options to the user.

1. Load all chicsessions via `ChicsessionManager(project_root)` from `.chicsessions/*.json`
2. For each chicsession: load name, agent count, workflow_id, current_phase
3. Cross-reference against `processed_files` table to determine which are already in the DB
4. Output to stdout: JSON array sorted by status (unanalyzed first, then analyzed):

```json
[
  {"name": "ImplementFeatureX", "in_db": false, "agent_count": 3,
   "workflow_id": "project-team", "current_phase": "implementation",
   "estimated_messages": 142},
  {"name": "BugFixY", "in_db": false, "agent_count": 2,
   "workflow_id": "project-team", "current_phase": "testing",
   "estimated_messages": 68},
  {"name": "InitialSetup", "in_db": true, "agent_count": 2,
   "messages_in_db": 87, "corrections_found": 5,
   "last_extracted": "2026-04-12T14:30:00"},
  {"name": "RefactorModule", "in_db": true, "agent_count": 4,
   "messages_in_db": 203, "corrections_found": 12,
   "last_extracted": "2026-04-10T09:15:00"}
]
```

The `in_db` flag indicates whether any messages from that chicsession are already in the database. For analyzed sessions, includes `messages_in_db` and `corrections_found` counts. For unanalyzed sessions, includes `estimated_messages` (heuristic from JSONL file size).

### 5.3 `extract` -- Incremental Message Extraction

**Arguments:** Either `--sessions NAME1,NAME2` (comma-separated chicsession names to analyze) or `--all` (process every chicsession). One is required. The auditor uses `--sessions` with chicsession names the user selected, or `--all` when the user requests a full re-audit.

**For each selected chicsession:**

1. Load chicsession JSON via `ChicsessionManager`
2. For each `ChicsessionEntry` in `cs.agents`:
   - `entry.session_id` is the join key
   - Resolve to JSONL path: `~/.claude/projects/<project_key>/<session_id>.jsonl`
   - Also check for `agent-<session_id>.jsonl` (sub-agent sessions)
   - If JSONL not found: warn and skip (stale reference)
3. Annotate extracted messages with:
   - `chicsession_name` = `cs.name`
   - `agent_name` = `entry.name`
   - `workflow_id` = `cs.workflow_state["workflow_id"]` (if present)
   - `phase_id` = from JSONL transition markers (primary) or `cs.workflow_state["current_phase"]` (fallback)

**Incremental logic:**

1. For each resolved JSONL file, check `processed_files` table
2. If file_path exists AND file_size + file_mtime match: skip entirely
3. If file is new or changed: parse all messages, INSERT OR IGNORE (dedup by hash)
4. Update `processed_files` with new size/mtime

**JSONL parsing** (absorbed from mine_patterns.py):

- Read file line-by-line with `encoding='utf-8', errors='replace'`
- Parse each line as JSON; skip malformed lines with warning
- Extract text from `message.content` (handle string or list-of-dicts with `type="text"`)
- Detect JSONL version from metadata fields for format compatibility
- Skip `toolUseResult` messages (not user text)
- Extract session_id from filename (UUID before `.jsonl`)

**Pre-filter** (mark `is_boilerplate=1`):

Strip system messages that are not user corrections. Check if text starts with any of:
- `[Spawned by agent` -- agent spawn notifications
- `[Request interrupted` -- interrupt messages
- `<task-notification>` -- task notifications
- `You have been idle` -- idle reminders
- `[Message from agent` -- inter-agent messages
- `[Question from agent` -- agent questions
- `<system-reminder>` -- system reminders
- `This session is being continued` -- session continuations
- `[Redirected by` -- redirect notifications
- `Workflow '` -- workflow status messages

**Regex scoring** (runs on all non-boilerplate messages during extract):

After pre-filtering, run `tier1_score_message()` on each non-boilerplate user message. Store `regex_score` (0.0-1.0) and `regex_indicator` (best pattern label) in the `messages` table. This is ~10 lines of code, runs at ~24,000 msgs/sec, and catches keyword-driven corrections the LLM classifier may miss (9.2% recall, zero overlap with LLM per POC). The classifier agent receives these scores as supplemental context.

**3-message context window extraction:**

For each user message at index `i`:
- `context_before` = text of the assistant message at index `i-1` (what the agent did before the user spoke)
- `context_after` = text of the assistant message at index `i+1` (how the agent responded)
- Both nullable (first/last messages have no neighbor)

**Phase transition extraction:**

Scan all messages in a session for phase markers:
- Assistant messages containing `advance_phase` tool calls
- System messages containing `"Advanced to phase:"` strings
- User messages containing `/advance` commands
- Build timeline: `[(message_index, phase_id), ...]`
- Each message gets the phase from the most recent transition before it
- `phase_confidence = "inferred"` if from markers, `"snapshot"` if from chicsession, `"unknown"` if neither

**Output to stderr:**
```
Processing 2 chicsessions: ImplementFeatureX, BugFixY
  ImplementFeatureX: 3 agents, 5 JSONL files
    Skipped 2 files (unchanged)
    Extracted 47 new messages from 3 files (12 duplicates skipped)
    Pre-filtered 8 boilerplate messages
    Regex flagged 4 messages (score >= 0.3)
  BugFixY: 2 agents, 3 JSONL files
    Extracted 31 new messages from 3 files
    Pre-filtered 5 boilerplate messages
    Regex flagged 2 messages (score >= 0.3)
Database total: 547 messages, 312 classified, 41 corrections
```

### 5.4 `unclassified` -- Feed for Classifier Agent

Query: all non-boilerplate messages not yet in `classifications` table.

```sql
SELECT m.id, m.user_text, m.context_before, m.context_after,
       m.session_id, m.agent_name, m.phase_id,
       m.regex_score, m.regex_indicator
FROM messages m
WHERE m.is_boilerplate = 0
  AND m.id NOT IN (SELECT message_id FROM classifications)
ORDER BY m.id
```

Output: JSON array to stdout. The classifier agent reads this. Regex score and indicator are included as supplemental context for the classifier.

**Chunking:** `--chunk-size N` (default: 200) limits the JSON array to N items per output. If there are more unclassified messages than the chunk size, output includes a `"has_more": true` field. The auditor calls `unclassified` repeatedly until all messages are classified. This prevents context window overflow when passing large payloads to agents.

### 5.5 `corrections` -- Feed for Judge Agent

Query: all classified corrections with full context.

```sql
SELECT m.id, m.user_text, m.context_before, m.context_after,
       m.session_id, m.session_file, m.agent_name, m.workflow_id,
       m.phase_id, m.phase_confidence, m.turn_index,
       m.regex_score, m.regex_indicator,
       c.category, c.confidence
FROM messages m
JOIN classifications c ON m.id = c.message_id
WHERE c.is_correction = 1
ORDER BY m.phase_id, c.category, m.id
```

Output: JSON array to stdout. The judge agent reads ALL accumulated corrections.

Optional filters: `--phase`, `--category`, `--min-confidence`.

**Chunking:** Same `--chunk-size N` behavior as `unclassified`. For large accumulated datasets, the judge processes corrections in chunks.

### 5.6 `aggregate` -- Group Corrections into Patterns

Pure code (SQL + Python), no agent. Groups classified corrections into patterns the judge can reason about efficiently. This is the bridge between individual corrections and actionable suggestions.

```
python scripts/audit/audit.py aggregate [--min-count N]
```

`--min-count N` (default: 2) filters out patterns with fewer than N corrections. Patterns below threshold are still in the DB but excluded from the aggregate output.

**Aggregation logic:**

1. Group corrections by `(category, phase_id)`
2. Within each group, count total corrections, count distinct sessions, collect top 3 example messages (highest confidence first)
3. Include the 3-message context windows for top examples so the judge can see root causes

**Output:** JSON array to stdout, one object per pattern:

```json
[
  {
    "pattern_id": "factual_correction:implementation",
    "category": "factual_correction",
    "phase_id": "implementation",
    "correction_count": 7,
    "session_count": 3,
    "agent_names": ["implementor", "reviewer"],
    "top_examples": [
      {
        "message_id": 42,
        "user_text": "No, that's wrong -- use pathlib not os.path",
        "context_before": "I'll update the imports to use os.path...",
        "context_after": "You're right, switching to pathlib...",
        "confidence": "high",
        "session_id": "abc-123"
      },
      {
        "message_id": 67,
        "user_text": "I said to use pathlib, not string concatenation",
        "context_before": "Here's the updated path: root + '/src'...",
        "context_after": "Apologies, using Path() now...",
        "confidence": "high",
        "session_id": "def-456"
      }
    ],
    "all_message_ids": [42, 67, 89, 91, 103, 115, 128]
  },
  {
    "pattern_id": "frustration_escalation:testing",
    "category": "frustration_escalation",
    "phase_id": "testing",
    "correction_count": 4,
    "session_count": 2,
    "agent_names": ["implementor"],
    "top_examples": [...],
    "all_message_ids": [55, 78, 94, 112]
  }
]
```

**Why this matters:** The judge sees "7 corrections about factual errors in the implementation phase, across 3 sessions, mostly about path handling" instead of 7 individual messages. This produces better suggestions because the judge can identify recurring themes and proportional responses.

**SQL core:**

```sql
SELECT c.category, m.phase_id,
       COUNT(*) as correction_count,
       COUNT(DISTINCT m.session_id) as session_count,
       GROUP_CONCAT(DISTINCT m.agent_name) as agent_names
FROM classifications c
JOIN messages m ON c.message_id = m.id
WHERE c.is_correction = 1
GROUP BY c.category, m.phase_id
HAVING COUNT(*) >= :min_count
ORDER BY COUNT(*) DESC
```

Top examples are fetched per group with a secondary query ordered by confidence.

### 5.7 `store-classifications` -- Classifier Writes Back (Batch)

Reads a JSON array from stdin. Each element:
```json
{"message_id": 42, "is_correction": 1, "category": "factual_correction", "confidence": "high"}
```

Fields: `message_id` (required), `is_correction` (required, 0/1), `category` (required if is_correction=1), `confidence` (required if is_correction=1).

Batch INSERT into `classifications` table using `executemany`. Skips duplicates (already classified). Reports count to stderr: "Stored 47 classifications (3 duplicates skipped)."

**Usage:** The classifier agent writes all classifications to a temp file or pipes them:
```bash
echo '[{"message_id":42,"is_correction":1,"category":"factual_correction","confidence":"high"}, ...]' | python scripts/audit/audit.py store-classifications
```

### 5.8 `store-suggestions` -- Judge Writes Back (Batch)

Reads a JSON array from stdin. Each element contains suggestion fields:
```json
{
  "artifact_type": "phase-markdown",
  "file_path": "workflows/project-team/implementor/implementation.md",
  "suggestion_type": "modify",
  "current_content": "...",
  "proposed_content": "...",
  "rationale": "...",
  "evidence_count": 3,
  "priority": 2,
  "evidence_message_ids": [42, 67, 89]
}
```

Batch INSERT into `suggestions` table. Populates `suggestion_evidence` from `evidence_message_ids`. Returns JSON array of new suggestion IDs to stdout.

**Usage:**
```bash
echo '[{...}, {...}]' | python scripts/audit/audit.py store-suggestions
```

### 5.9 `update-suggestion` -- Update Verdict or Status

```
python scripts/audit/audit.py update-suggestion 7 --critic-verdict APPROVE --critic-reasoning "Well-evidenced"
python scripts/audit/audit.py update-suggestion 7 --apply-status applied
python scripts/audit/audit.py update-suggestion 7 --applied-at "2026-04-13T14:30:00"
```

UPDATE specific fields on an existing suggestion.

### 5.10 `check` -- Structured Advance Checks

Replaces fragile `status | grep` patterns in advance checks. Returns exit code 0 (pass) or 1 (fail) with a human-readable message to stderr.

```
python scripts/audit/audit.py check has-messages       # messages table is non-empty
python scripts/audit/audit.py check all-classified     # unclassified count = 0
python scripts/audit/audit.py check all-reviewed       # all suggestions have critic verdicts
python scripts/audit/audit.py check all-decided        # no suggestions with apply_status='pending'
python scripts/audit/audit.py check has-db             # .audit/corrections.db exists
```

Each check prints a one-line status message and exits 0/1:
```
$ python scripts/audit/audit.py check all-classified
PASS: 547 messages classified, 0 remaining
$ echo $?
0
```

### 5.11 `reset` -- Clear for Re-iteration

```
python scripts/audit/audit.py reset classifications    # DELETE FROM classifications
python scripts/audit/audit.py reset suggestions        # DELETE FROM suggestions + suggestion_evidence
```

Enables iterative refinement: re-run the classifier with different prompts, or re-run the judge after updating workflow definitions. Messages are preserved -- only derived data is cleared.

Requires `--confirm` flag to prevent accidental data loss.

### 5.12 `status` -- Database Dashboard

Queries and displays:
- Total messages / classified / unclassified / corrections
- Corrections by category (counts)
- Corrections by phase (counts)
- Corrections by agent (counts)
- Regex flags: messages with regex_score >= 0.3
- Suggestions by status (pending / applied / skipped)
- Suggestions by critic verdict (APPROVE / FLAG / REJECT / unreviewed)
- Last extraction timestamp
- Files processed count
- Chicsessions processed (names)

Output is structured key-value pairs (parseable by advance checks and readable by the auditor for context):
```
db_exists: true
messages: 547
classified: 312
unclassified: 235
corrections: 41
regex_flagged: 28
suggestions: 12
pending: 5
applied: 4
skipped: 3
unreviewed: 0
files_processed: 79
last_extract: 2026-04-13T14:30:00
chicsessions_processed: InitialSetup, RefactorModule
```

If the database does not exist, outputs `db_exists: false` and all counts as 0. The auditor uses this to provide context before asking what to audit (e.g., "This is your first audit" vs "I found 41 corrections from 2 previous audits").

---

## 6. Absorbed from mine_patterns.py

### 6.1 Kept (absorbed into scripts/audit/)

| Component | Original Location | Use in audit |
|-----------|-------------------|--------------|
| `parse_session()` | mine_patterns.py L145-283 | Core JSONL parser in `extract` command |
| `_extract_text()` | mine_patterns.py | Handles string or list-of-dicts content format |
| `_detect_version()` | mine_patterns.py | Version compatibility checking |
| `Message` dataclass | mine_patterns.py | Internal parsing, fields map to `messages` table columns |
| `ParseResult` / `ParseStats` | mine_patterns.py | Internal, not exposed |
| `discover_session_files()` | mine_patterns.py L317-346 | Used in picker for estimating unprocessed files |
| `KNOWN_VERSIONS` | mine_patterns.py | Format validation |
| `ALL_PATTERN_BANKS` (NEGATION, FRUSTRATION, ERROR, CORRECTION) | mine_patterns.py L356-424 | Active during extract -- regex scoring on all messages |
| `tier1_score_message()` | mine_patterns.py L450-527 | Active during extract -- stores regex_score + regex_indicator |

### 6.2 Dropped

| Component | Why |
|-----------|-----|
| Tier 2 semantic classification (transformers) | Replaced by LLM classifier (Haiku). No torch/transformers dependency. |
| Tier 3 HDBSCAN clustering | Judge agent spots patterns without clustering code. Defer to v2. |
| `.patterns_mining_state.json` incremental tracking | Replaced by `processed_files` table in SQLite. |
| `--validate` mode | Specific to PATTERNS.md maintenance. Not relevant to audit. |
| CLI (`build_parser()`, `main()`) | Replaced by audit.py CLI. |
| Pipeline orchestration (`run_pipeline()`) | Replaced by agent conversation. |
| Report output formatting | Auditor agent writes reports natively. |
| `DEFAULT_AGENT_ROLES` list | Agent roles come from chicsession, not hardcoded. |

### 6.3 Regex Scoring (Active in v1)

The 4 regex pattern banks and `tier1_score_message()` run during `extract` on every non-boilerplate message. Results are stored in `messages.regex_score` and `messages.regex_indicator`.

**Why active, not dormant:** POC validated that regex catches keyword-driven corrections the LLM misses (9.2% recall, zero overlap). It runs at ~24,000 msgs/sec -- effectively free. The 10 extra lines of code provide a complementary signal.

**How agents use it:** The `unclassified` output includes `regex_score` and `regex_indicator` for each message. The classifier agent sees these as supplemental context -- a message with `regex_score: 0.77` and `regex_indicator: "not what I"` is very likely a correction. The classifier makes the final call.

---

## 7. Workflow Phases

### 7.1 Phase Summary

| Phase | Role | What Happens |
|-------|------|-------------|
| `parse` | auditor | Ask user what to audit. Run `audit.py list-sessions` to check available sessions, then `extract` based on user's answer. Report results and cost estimate. |
| `analyze` | auditor + classifier | Spawn classifier agent. Classifier reads `unclassified` output (in chunks if needed), classifies each message, stores results via `store-classifications`. |
| `suggest` | auditor + judge + critic | Run `audit.py aggregate` to group corrections into patterns. Spawn judge with aggregated patterns. Judge generates suggestions, stores via `store-suggestions`. Spawn critic to validate. |
| `report` | auditor | Query DB for approved/flagged suggestions. Present to user conversationally. Record apply/skip decisions. |
| `apply` | auditor | Read approved suggestions from DB. Edit target files. Update apply_status to "applied". |

### 7.2 Phase Details

#### parse (auditor)

The auditor:
1. Runs `python scripts/audit/audit.py status` to check if a database exists and what's already been analyzed
2. Runs `python scripts/audit/audit.py list-sessions` to see all available chicsessions and their DB status
3. Presents context and asks the user what to audit. Examples:

   **First audit (no DB):**
   > "This is your first audit -- no previous data found. I can see 5 chicsessions available with ~320 messages total. What would you like to audit?
   > Examples: 'all sessions', 'just the new ones', 'the tutorial workflow', 'last 3 sessions', or a specific chicsession name."

   **Subsequent audit (existing DB):**
   > "I found 45 messages already classified from 2 previous audits (InitialSetup, RefactorModule), with 8 corrections detected. There are 3 new chicsessions with ~120 unanalyzed messages. What would you like to audit?
   > Examples: 'all sessions', 'just the new ones', 'ImplementFeatureX', or 'everything for a full re-audit'."

4. Matches the user's answer to chicsession names (e.g., "all sessions" -> `--all`, "the tutorial ones" -> `--sessions tutorial_setup,tutorial_extending`, "just the new ones" -> `--sessions` with unanalyzed names only)
5. Runs `python scripts/audit/audit.py extract --sessions <names>` (or `--all`)
6. Reports results: "Extracted 78 new messages from 3 sessions (24 skipped as duplicates, 13 pre-filtered as boilerplate, 2 files unchanged). Database now has 528 total messages."
7. Shows cost estimate: "78 new messages to classify. Estimated cost: ~$0.003 (Haiku). Proceed?"
8. Advance check: `audit.py check has-messages`

The `parse.md` instructions tell the auditor: "Run `audit.py status` and `audit.py list-sessions` first to understand what's available. Present context to the user, then ask what they want to audit with examples of natural language you understand. Use `extract --sessions` or `extract --all` based on the user's answer."

#### analyze (auditor + classifier)

The auditor:
1. Runs `python scripts/audit/audit.py unclassified --chunk-size 200` to get unclassified messages
2. If zero unclassified: report "All messages already classified" and advance
3. Spawns the classifier agent with the unclassified messages as input

The classifier (Haiku):
1. Receives unclassified messages (JSON array, chunked to fit context window)
2. For each message, determines: is this a correction? (yes/no)
3. If yes, assigns one of the 6 categories
4. Assigns confidence: "high" / "medium" / "low"
5. Uses the 3-message context (context_before, user_text, context_after) plus regex_score/regex_indicator as supplemental signals
6. Writes all classifications at once via stdin: `echo '<json_array>' | audit.py store-classifications`
7. Reports summary: "Classified N messages. Found M corrections."
8. If `has_more` was true, auditor runs `unclassified` again for next chunk

Advance check: `audit.py check all-classified`

#### suggest (auditor + judge + critic)

The auditor:
1. Runs `python scripts/audit/audit.py aggregate` to group corrections into patterns
2. If zero patterns: report "No correction patterns found" and advance
3. Spawns the judge agent with the aggregated patterns as input

The judge:
1. Receives aggregated patterns (JSON array with category, phase, counts, session counts, top examples with 3-message context)
2. Reads the actual workflow artifacts (phase markdown, rules, hints, checks) using Read tool
3. Uses category-to-fix mapping to determine fix types (see Section 8.2)
4. Generates machine-applicable suggestions -- one or more per pattern (see Section 8)
5. Uses `all_message_ids` from each pattern to populate `evidence_message_ids` in suggestions
6. Writes all suggestions at once via stdin: `echo '<json_array>' | audit.py store-suggestions`
7. Reports: "Generated N suggestions from M patterns."

**Why aggregate, not raw corrections:** The judge sees "7 corrections about factual errors in implementation, across 3 sessions" with top examples, rather than 7 individual messages. This produces better, more proportional suggestions because the judge reasons about patterns, not incidents.

The auditor then spawns the critic:

The critic:
1. Reads suggestions from DB (auditor provides them)
2. Validates each against 6 validation criteria (see Section 9)
3. Assigns verdict: APPROVE / FLAG / REJECT
4. Updates: `audit.py update-suggestion <id> --critic-verdict <V> --critic-reasoning "<R>"`
5. Reports: "Approved N, flagged M, rejected P."

Advance check: `audit.py check all-reviewed`

#### report (auditor)

The auditor:
1. Queries DB for suggestions with critic_verdict = APPROVE or FLAG
2. Presents each to the user conversationally:
   - Shows target file, rationale, proposed change, evidence count
   - Groups by artifact type (phase markdown > checks > rules > hints)
   - Asks: "Apply this suggestion? (yes/no)"
3. Records decisions: `audit.py update-suggestion <id> --apply-status applied|skipped`
4. Summarizes: "N approved, M skipped. Ready to apply?"

Advance check: `audit.py check all-decided` + manual-confirm

#### apply (auditor)

The auditor:
1. Queries DB for suggestions with apply_status = 'applied'
2. For each:
   - Reads target file with Read tool
   - For "modify": finds `current_content`, replaces with `proposed_content` using Edit tool
   - For "add": finds `insertion_point`, inserts `proposed_content` after it using Edit tool
   - Validates YAML if applicable (load with yaml.safe_load)
   - Updates DB: `audit.py update-suggestion <id> --applied-at <timestamp>`
3. Skips gracefully if target file missing or content not found (warns user)
4. Summarizes: "Applied N changes. Please review the diffs."

Advance check: manual-confirm ("Changes applied. Verify and confirm?")

---

## 8. Classification Taxonomy

### 8.1 Six Categories

| # | Category | Description | Suggested Fix Types |
|---|----------|-------------|-------------------|
| 1 | `factual_correction` | User corrects factual errors in agent output | Phase markdown, rules (warn/deny) |
| 2 | `approach_redirect` | User redirects the agent's approach/strategy | Phase markdown, rules (warn/deny) |
| 3 | `intent_clarification` | User clarifies their original intent | Phase markdown |
| 4 | `scope_adjustment` | User adjusts scope or level of detail | Phase markdown |
| 5 | `style_preference` | User requests style or format changes | Hints (user-facing ONLY) |
| 6 | `frustration_escalation` | User expresses frustration or escalates | Rules (deny), advance checks |

### 8.2 Category-to-Fix Mapping (Used by Judge)

| Category | Phase Markdown | Rules | Advance Checks | Hints |
|----------|:-:|:-:|:-:|:-:|
| factual_correction | Yes | warn/deny | -- | -- |
| approach_redirect | Yes | warn/deny | -- | -- |
| intent_clarification | Yes | -- | -- | -- |
| scope_adjustment | Yes | -- | -- | -- |
| style_preference | -- | -- | -- | Yes (user-only) |
| frustration_escalation | -- | deny | Yes | -- |

**Output priority:** Phase markdown (highest) > advance checks > rules > hints (lowest).

### 8.3 Minimum Evidence Thresholds

| Artifact Type | Minimum Corrections | Rationale |
|--------------|-------------------|-----------|
| Phase markdown | 2+ | Most impactful, lower bar |
| Hints | 2+ | Lightweight, lower bar |
| Advance checks | 3+ | Structural change, higher bar |
| Rules | 3+ | Enforcement impact, higher bar |

---

## 9. Critic Validation

### 9.1 Six Validation Criteria

| # | Criterion | Question |
|---|-----------|----------|
| 1 | **Specificity** | Can this be turned into a concrete rule/check/hint? Reject vague advice. |
| 2 | **Actionability** | Can this actually be implemented as a workflow artifact? |
| 3 | **Evidence grounding** | Do the cited corrections actually demonstrate this problem? Check the 3-message context. |
| 4 | **Proportionality** | Is N corrections enough to justify this change? (thresholds from 8.3) |
| 5 | **Conflict detection** | Would this conflict with existing workflow rules or create contradictions? |
| 6 | **Feasibility** | Can the agent actually follow this? No catch-22 patterns. |

### 9.2 Three Verdicts

| Verdict | Meaning | Action |
|---------|---------|--------|
| **APPROVE** | Passes all criteria | Present to user |
| **FLAG** | Has merit but needs revision | Critic provides revised version; revised version presented to user |
| **REJECT** | Vague, unsupported, or harmful | Drop with logged reason |

### 9.3 Context-Aware Validation

The critic uses the 3-message context to assess:
- If `context_after` shows agent fixed the issue immediately: lower priority
- If `context_after` shows agent repeated the same mistake: higher priority, more urgent
- If `context_before` shows agent was following conflicting existing rules: needs conflict check

---

## 10. suggest.md Content Requirements

The `judge/suggest.md` file is the judge agent's instruction set. The judge receives **aggregated patterns** from `audit.py aggregate`, not raw individual corrections. It must include:

1. **Input format** -- explain the aggregate pattern schema: `pattern_id`, `category`, `phase_id`, `correction_count`, `session_count`, `agent_names`, `top_examples` (with 3-message context), `all_message_ids`. The judge reasons about patterns, not individual messages.

2. **Output schema** -- exact JSON structure for `store-suggestions` input. Field names, types, examples. Emphasize `insertion_point` and `current_content` for machine application. Include `evidence_message_ids` (from pattern's `all_message_ids`) to link suggestions to supporting corrections.

3. **Worked example** -- at least one complete example:
   - Input: an aggregate pattern with `category: "factual_correction"`, `phase_id: "implementation"`, `correction_count: 7`, `session_count: 3`, and top examples showing users correcting agents about path handling
   - Output: complete suggestion JSON with file_path, current_content, proposed_content, evidence_count, evidence_message_ids
   - Demonstrate machine-applicability (the auditor can use Read + Edit to apply it)

4. **Tone instructions** -- suggestions become content other LLMs read. Imperative voice matching existing phase markdown (e.g., "Always read error output before retrying" not "Consider reading error output").

5. **Anti-patterns:**
   - Rules that block their own prerequisites (catch-22)
   - Overly broad rules firing on legitimate operations
   - Hints duplicating existing hints
   - Phase markdown changes for nonexistent phases

6. **Artifact access** -- instructions to Read target files before proposing changes.

7. **YAML reference** -- valid values for:
   - `trigger`: `PreToolUse/Bash`, `PreToolUse/Write`, etc.
   - `enforcement`: `deny` (block), `warn` (recommendation)
   - `lifecycle`: `show-once`, `show-every-session`, `show-until-resolved`, `cooldown-period`
   - `check type`: `file-exists-check`, `file-content-check`, `command-output-check`, `manual-confirm`

8. **3-message context usage** -- the top examples in each aggregate pattern include context_before, user_text, and context_after. Analyze the agent's mistake (context_before), the user's correction (user_text), and whether the agent fixed it (context_after).

---

## 11. Workflow Manifest

```yaml
workflow_id: audit
main_role: auditor

roles:
  - id: classifier
    description: "Scans messages, detects and categorizes corrections (Haiku)"
  - id: judge
    description: "Analyzes corrections, reads workflow definitions, generates suggestions"
  - id: critic
    description: "Validates suggestions against 6 criteria: specificity, actionability, evidence, proportionality, conflicts, feasibility"
  - id: auditor
    description: "Orchestrates workflow, presents to user, applies approved edits"

phases:
  - id: parse
    role: auditor
    file: parse
    hints:
      - message: "Phase 1/5: Ask the user what to audit, then extract messages into the corrections database."
        lifecycle: show-once
    advance_checks:
      - type: command-output-check
        command: "python scripts/audit/audit.py check has-messages"
        expected: "PASS"
        on_failure:
          message: "Run audit.py extract first."
          severity: warning

  - id: analyze
    role: auditor
    file: analyze
    hints:
      - message: "Phase 2/5: Spawn classifier agent to classify unprocessed messages."
        lifecycle: show-once
    advance_checks:
      - type: command-output-check
        command: "python scripts/audit/audit.py check all-classified"
        expected: "PASS"
        on_failure:
          message: "Classify all messages before advancing."
          severity: warning

  - id: suggest
    role: auditor
    file: suggest
    hints:
      - message: "Phase 3/5: Run audit.py aggregate, then spawn judge with patterns, then critic to validate."
        lifecycle: show-once
    advance_checks:
      - type: command-output-check
        command: "python scripts/audit/audit.py check all-reviewed"
        expected: "PASS"
        on_failure:
          message: "All suggestions must have critic verdicts before advancing."
          severity: warning

  - id: report
    role: auditor
    file: report
    hints:
      - message: "Phase 4/5: Present suggestions to user. Ask apply or skip for each."
        lifecycle: show-once
    advance_checks:
      - type: command-output-check
        command: "python scripts/audit/audit.py check all-decided"
        expected: "PASS"
        on_failure:
          message: "Review all suggestions before advancing."
          severity: warning
      - type: manual-confirm
        prompt: "All suggestions reviewed. Ready to apply approved changes?"

  - id: apply
    role: auditor
    file: apply
    hints:
      - message: "Phase 5/5: Apply approved suggestions by editing target files."
        lifecycle: show-once
    advance_checks:
      - type: manual-confirm
        prompt: "Changes applied. Verify and confirm?"

rules:
  - id: no_direct_edit_workflows
    trigger: PreToolUse/Write
    enforcement: warn
    detect:
      pattern: "workflows/"
    message: "Only the auditor in the apply phase should edit workflow files."
    phases: [parse, analyze, suggest, report]

  - id: no_direct_edit_rules
    trigger: PreToolUse/Write
    enforcement: warn
    detect:
      pattern: "global/"
    message: "Only the auditor in the apply phase should edit global files."
    phases: [parse, analyze, suggest, report]
```

---

## 12. Cross-Platform Requirements

- `encoding='utf-8', errors='replace'` on ALL file reads (JSONL, chicsession JSON, SQLite text)
- `pathlib.Path` everywhere. Never string-concatenate with `/`. Use `.as_posix()` for regex/string matching.
- ASCII only. No emoji, em-dash, or box-drawing characters.
- `python` not `python3` in all commands.
- Forward slashes in all `file_path` values stored in suggestions.
- `os.replace()` not `Path.rename()` for atomic operations (rename fails on Windows if target exists).
- SQLite: open with `PRAGMA journal_mode=WAL`. If WAL fails (Windows network drives), fall back to `PRAGMA journal_mode=DELETE` with logged warning.

---

## 13. File Inventory

### New files to create

| File | Purpose |
|------|---------|
| `scripts/audit/__init__.py` | Empty, enables imports |
| `scripts/audit/audit.py` | CLI entry point, JSONL extraction, regex scoring, pre-filter |
| `scripts/audit/db.py` | SQLite schema, connection management, batch queries (split from audit.py if needed) |
| `workflows/audit/audit.yaml` | Workflow manifest |
| `workflows/audit/classifier/identity.md` | Classifier role definition |
| `workflows/audit/classifier/analyze.md` | Classification phase instructions |
| `workflows/audit/judge/identity.md` | Judge role definition |
| `workflows/audit/judge/suggest.md` | Suggestion generation guidance |
| `workflows/audit/critic/identity.md` | Critic role definition |
| `workflows/audit/critic/suggest.md` | Validation criteria + verdicts |
| `workflows/audit/auditor/identity.md` | Auditor role + invocation UX + cold-start |
| `workflows/audit/auditor/parse.md` | Extract phase instructions |
| `workflows/audit/auditor/report.md` | Interactive review instructions |
| `workflows/audit/auditor/apply.md` | File editing instructions |

### Files to delete

| File | Reason |
|------|--------|
| `scripts/mine_patterns.py` | Replaced entirely by scripts/audit/ |
| `.patterns_mining_state.json` | Replaced by SQLite processed_files table |

### Existing files to modify

| File | Change |
|------|--------|
| `copier.yml` | Include `scripts/audit/` and `workflows/audit/` in template. Remove mine_patterns.py references. |
| `template/scripts/audit/` | Mirror of root `scripts/audit/` |
| `template/workflows/audit/` | Mirror of root `workflows/audit/` |

### Test files

| File | Purpose |
|------|---------|
| `tests/test_audit.py` | Unit tests: extract, dedup, pre-filter, regex scoring, incremental skip, batch store, check commands, reset, chicsession integration |
| `tests/test_audit_integration.py` | Integration: full pipeline with fixture JSONL + mock classifier |
| `tests/fixtures/audit/session_with_corrections.jsonl` | JSONL with known corrections |
| `tests/fixtures/audit/session_clean.jsonl` | JSONL with no corrections |
| `tests/fixtures/audit/session_multi_phase.jsonl` | JSONL with phase transition markers |
| `tests/fixtures/audit/chicsession_full.json` | Chicsession with workflow_state and multiple agents |

---

## 14. Implementation Order

1. **SQLite layer** -- schema creation, WAL mode with Windows fallback, batch insert/query functions. If splitting: this becomes `db.py`.
2. **audit.py extract** -- JSONL parsing (absorbed from mine_patterns.py), pre-filter, regex scoring, dedup, incremental skip, chicsession integration via ChicsessionManager
3. **audit.py picker** -- chicsession discovery, new-vs-audited classification, JSON output
4. **audit.py query commands** -- unclassified, corrections (with chunking)
5. **audit.py batch store** -- store-classifications, store-suggestions (stdin JSON arrays)
6. **audit.py utilities** -- check, reset, status, update-suggestion
7. **Tests** -- test_audit.py with fixture files
8. **Workflow manifest** -- audit.yaml
9. **Auditor markdown** -- identity.md (picker UX, cold-start, cost warning), parse.md
10. **Classifier markdown** -- identity.md, analyze.md
11. **Judge markdown** -- identity.md, suggest.md (examples, schema, anti-patterns, YAML reference)
12. **Critic markdown** -- identity.md, suggest.md (6 validation criteria, 3 verdicts)
13. **Auditor report + apply** -- report.md, apply.md
14. **Delete mine_patterns.py** -- verify no imports, remove
15. **Template integration** -- mirror into template/, update copier.yml

---

## 15. Risks

| Risk | Mitigation |
|------|------------|
| LLM classifier cost | Haiku ~$0.005/session. Cost warning shown before analyze phase. User confirms. |
| LLM generates invalid suggestion JSON | Critic catches. Apply phase skips gracefully on bad data. |
| LLM hallucinated file paths | Apply phase verifies with Read tool before editing. |
| Chicsession JSONL resolution fails | Warn and skip. Extract reports skipped entries with counts. |
| SQLite WAL mode fails on Windows | Fallback to DELETE journal mode with logged warning. |
| Large JSON payloads overflow agent context | Chunking via --chunk-size on unclassified/corrections commands. Default 200 items. |
| Database grows large | Corrections are sparse (~5-10% of messages). 1000 sessions = ~50K messages = ~10MB. Not a concern. |
| Phase mapping inaccuracy | phase_confidence field lets judge weight evidence appropriately. |
| mine_patterns.py dependents | Verify no imports before deleting. grep codebase. |
| Batch stdin parsing fails | Validate JSON before processing. Report line-level errors. |
