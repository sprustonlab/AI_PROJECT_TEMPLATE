# Architect Review: Audit Workflow Simplification

**Date:** 2026-04-13
**Reviewer:** Fresh architect (no project history)
**Input:** SPECIFICATION.md (v5.1), STATUS.md (30 decisions), POC FINDINGS.md, user's new direction

---

## 1. Verdict: What's ESSENTIAL vs BAGGAGE

### ESSENTIAL (keep)

| Element | Why |
|---------|-----|
| LLM classifier (Haiku) as primary detector | POC-validated. 24.1% recall at $0.005/session. This works. |
| Pre-filter (strip system boilerplate) | POC lesson: without this, flag rates explode (70%+). ~15 lines of code. |
| 4-role workflow (classifier, judge, critic, auditor) | Sound division of labor. These are agent roles, not Python modules. |
| 3-message context window (before/correction/after) | Gives judge and critic root-cause context. Critical for suggestion quality. |
| Category taxonomy (6 categories) | Helps judge map corrections to fix types. Lightweight -- classifier does this. |
| Phase mapping (hybrid: JSONL markers > chicsession > None) | Needed for scoped suggestions. But implementation is ~20 lines, not a module. |
| Machine-applicable suggestions (file_path, current_content, proposed_content) | The whole point -- agent applies edits. |
| `.audit/` output directory | End-user appropriate. |

### BAGGAGE (cut)

| Element | Why it's baggage |
|---------|-----------------|
| **8 Python modules** (types.py, parsing.py, prefilter.py, clustering.py, analysis.py, suggestions.py, report.py, session_lib.py) | Massively over-engineered. The Python code does ONE thing: extract messages from JSONL. Everything else is agent conversation. |
| **3 frozen dataclasses** (ParsedInteraction, CorrectionSignal, AuditSuggestion) | Over-specified. The database schema IS the data model. No need for frozen dataclasses when you're writing to SQLite/JSON. |
| **BERTopic clustering** | Adds a heavy dependency (transformers, torch) for marginal value. The LLM judge can spot patterns in 20 corrections without clustering. Cut from v1. |
| **Regex as parallel detector** | 9.2% recall, zero overlap with LLM. Marginal. The incremental design means we process fewer messages per run anyway. Not worth the complexity. |
| **validate_suggestions() programmatic validator** | Over-engineering. The critic agent validates suggestions. If YAML is broken, the apply phase will fail gracefully. |
| **Findings budget (top 20)** | Artifact of processing everything at once. Incremental design means smaller batches. |
| **Configurable label taxonomy (general vs coding)** | Premature abstraction. Ship general, add coding later if needed. |
| **Dated output files with glob advance checks** | Overcomplicated. A persistent database replaces per-run output files. |
| **report.py markdown formatter** | The auditor agent writes markdown. It doesn't need a Python formatter. |
| **session_lib.py extraction from mine_patterns.py** | Coupling concern that disappears when the Python file is simple and standalone. |
| **Template mirroring (root + template/)** | Ship concern, not architecture concern. Defer to copier.yml. |

### VERDICT

The spec treats Python as the orchestrator and agents as helpers. The user wants the INVERSE: agents are the orchestrator, Python is a helper. The spec has 8 modules because it puts pipeline logic in code. The new design puts pipeline logic in agent conversation and uses Python only for what agents can't do: read JSONL binary format and query a database.

---

## 2. Proposed Architecture

### Core Principle: Python extracts, agents think, database persists

```
  JSONL files (binary, agent can't read)
       |
       v
  [audit.py] -- ONE Python file
       |  - Discovers JSONL files
       |  - Reads messages
       |  - Tracks what's already processed (database)
       |  - Extracts NEW messages only
       |  - Pre-filters system boilerplate
       |  - Writes new messages to database
       |  - Presents messages to classifier agent
       |  - Stores classifications in database
       |  - Queries database for agent phases
       |
       v
  [SQLite database] -- .audit/corrections.db
       |  - All messages ever seen (with hash for dedup)
       |  - Classification results
       |  - Suggestions + verdicts
       |  - Grows over time, never reprocessed
       |
       v
  [Agent roles work from database]
       - Classifier: reads unclassified messages, classifies
       - Judge: reads all classified corrections, generates suggestions
       - Critic: validates suggestions
       - Auditor: presents to user, applies approved edits
```

### 2.1 The Database: `.audit/corrections.db` (SQLite)

SQLite because: single file, zero dependencies (stdlib), SQL queries for analysis, atomic writes, works on all platforms.

```sql
-- Every user message we've ever seen
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    message_hash TEXT UNIQUE,        -- SHA256 of (session_id + turn_index + text) for dedup
    session_id TEXT,
    session_file TEXT,               -- path to source JSONL
    turn_index INTEGER,
    user_text TEXT,
    context_before TEXT,             -- agent message before
    context_after TEXT,              -- agent message after
    phase_id TEXT,                   -- inferred phase (nullable)
    phase_confidence TEXT,           -- "inferred" | "snapshot" | "unknown"
    agent_name TEXT,
    workflow_id TEXT,
    is_boilerplate INTEGER DEFAULT 0,  -- pre-filter flag
    created_at TEXT,                 -- when we first saw this message
    UNIQUE(session_id, turn_index)
);

-- Classification results (only for non-boilerplate messages)
CREATE TABLE classifications (
    id INTEGER PRIMARY KEY,
    message_id INTEGER REFERENCES messages(id),
    is_correction INTEGER,           -- 1 = yes, 0 = no
    category TEXT,                   -- 6-category taxonomy (nullable if not correction)
    confidence TEXT,                 -- "high" | "medium" | "low"
    detection_source TEXT,           -- "llm"
    classified_at TEXT,
    UNIQUE(message_id)
);

-- Suggestions generated by judge, validated by critic
CREATE TABLE suggestions (
    id INTEGER PRIMARY KEY,
    artifact_type TEXT,              -- "phase-markdown" | "advance-check" | "rule" | "hint"
    file_path TEXT,
    suggestion_type TEXT,            -- "add" | "modify"
    current_content TEXT,
    proposed_content TEXT,
    insertion_point TEXT,
    rationale TEXT,
    evidence_count INTEGER,
    priority INTEGER,                -- 1=critical, 4=low
    critic_verdict TEXT,             -- "APPROVE" | "FLAG" | "REJECT"
    critic_reasoning TEXT,
    apply_status TEXT DEFAULT 'pending',  -- "pending" | "applied" | "skipped"
    created_at TEXT,
    applied_at TEXT
);

-- Link table: which corrections support which suggestion
CREATE TABLE suggestion_evidence (
    suggestion_id INTEGER REFERENCES suggestions(id),
    message_id INTEGER REFERENCES messages(id),
    PRIMARY KEY (suggestion_id, message_id)
);

-- Track which JSONL files we've fully processed
CREATE TABLE processed_files (
    file_path TEXT PRIMARY KEY,
    file_size INTEGER,               -- for detecting appended content
    file_mtime TEXT,                  -- for detecting changes
    messages_extracted INTEGER,
    processed_at TEXT
);
```

**Why this schema:**
- `message_hash` + `UNIQUE(session_id, turn_index)` = never reprocess a message
- `processed_files` with size/mtime = skip unchanged files instantly
- `classifications` separate from `messages` = can re-classify without re-extracting
- `suggestions` + `suggestion_evidence` = full audit trail
- Everything is append-only in normal operation

### 2.2 The Python File: `scripts/audit/audit.py`

One file. ~200-300 lines. Does exactly 4 things:

```python
"""Audit pipeline: extract JSONL messages into a persistent database.

Usage (called by auditor agent during workflow phases):
    python scripts/audit/audit.py extract          # Extract new messages from JSONL
    python scripts/audit/audit.py status           # Show database stats
    python scripts/audit/audit.py unclassified     # Dump unclassified messages (for classifier agent)
    python scripts/audit/audit.py corrections      # Dump all corrections (for judge agent)
    python scripts/audit/audit.py store-classification <msg_id> <is_correction> <category> <confidence>
    python scripts/audit/audit.py store-suggestion <json>
"""
```

**What each command does:**

1. **`extract`** -- The incremental core
   - Scan `~/.claude/projects/` for JSONL files
   - Check `processed_files` table: skip files with same size+mtime
   - For new/changed files: parse messages, compute hashes, INSERT OR IGNORE
   - Pre-filter boilerplate (mark `is_boilerplate=1`)
   - Extract 3-message context windows
   - Attempt phase mapping from JSONL transition markers
   - Report: "Found 3 new sessions, extracted 47 new messages (12 already in DB)"

2. **`unclassified`** -- Feed for classifier agent
   - `SELECT * FROM messages WHERE is_boilerplate=0 AND id NOT IN (SELECT message_id FROM classifications)`
   - Output as JSON array the classifier agent can read

3. **`corrections`** -- Feed for judge agent
   - `SELECT m.*, c.category, c.confidence FROM messages m JOIN classifications c ON m.id = c.message_id WHERE c.is_correction = 1`
   - Output as JSON array with context windows

4. **`store-classification`** / **`store-suggestion`** -- Agent writes back
   - Simple INSERT into the database
   - Agent calls these after making decisions

5. **`status`** -- Dashboard
   - Total messages, classified, corrections, suggestions by status
   - Per-phase and per-category breakdowns

**Dependencies:** `sqlite3` (stdlib), `json` (stdlib), `pathlib` (stdlib), `hashlib` (stdlib). That's it. No torch, no transformers, no BERTopic.

### 2.3 Incremental Processing Flow

**First run (cold start):**
```
extract: 0 files processed -> scans all -> extracts 500 messages
unclassified: 500 messages -> classifier agent processes all
corrections: 47 found -> judge generates suggestions
critic validates -> auditor presents -> user approves -> agent applies
```

**Second run (3 new sessions):**
```
extract: 76 files processed, 3 new -> extracts 38 new messages only
unclassified: 38 messages -> classifier agent processes only new ones
corrections: 5 new + 47 existing = 52 total -> judge sees FULL picture
  (judge may generate new suggestions OR notice existing ones cover it)
critic validates new suggestions only
auditor presents new suggestions
```

**Key insight:** The judge always sees ALL corrections (accumulated), not just new ones. This means suggestions improve over time as evidence accumulates. A pattern that appeared once in run 1 might hit the 3-signal threshold in run 3.

### 2.4 Agent Interaction with Database

The agents don't call Python functions -- they run CLI commands via Bash tool:

```
# Classifier agent (analyze phase):
$ python scripts/audit/audit.py unclassified
[{"id": 42, "user_text": "No that's wrong, use pathlib", "context_before": "...", ...}, ...]

# Classifier classifies each message, then stores:
$ python scripts/audit/audit.py store-classification 42 1 "factual_correction" "high"

# Judge agent (suggest phase):
$ python scripts/audit/audit.py corrections
[{"id": 42, "user_text": "...", "category": "factual_correction", "phase_id": "implementation", ...}, ...]

# Judge generates suggestion, stores:
$ python scripts/audit/audit.py store-suggestion '{"artifact_type": "phase-markdown", ...}'
```

This is the "conversational not code-heavy" design: agents read JSON, think, write back. The Python file is a thin database layer.

### 2.5 Workflow Phases (Simplified)

5 phases remain but they're lighter:

| Phase | What happens |
|-------|-------------|
| **parse** | Auditor runs `audit.py extract`. Reports new message count. |
| **analyze** | Auditor spawns classifier agent. Classifier reads `unclassified`, classifies each, stores results. |
| **suggest** | Auditor spawns judge agent. Judge reads `corrections` (ALL accumulated), generates suggestions. Auditor spawns critic. Critic validates. Results stored in DB. |
| **report** | Auditor queries DB for pending suggestions, presents to user conversationally. Marks apply/skip. |
| **apply** | Auditor reads approved suggestions from DB, edits target files. |

### 2.6 What the Workflow Markdown Files Do

The workflow markdown files (identity.md, phase .md files) contain ALL the intelligence. They tell agents:
- How to interpret the JSON output from `audit.py`
- The 6-category taxonomy
- The category-to-fix mapping
- How to generate machine-applicable suggestions
- The critic's 6 validation checks
- How to present suggestions to the user

This is where the spec's "suggest.md content requirements" (worked examples, anti-patterns, schema, YAML reference) still live. That content was always meant for agent markdown, and it stays there.

---

## 3. What We Cut and Why

| Cut | Lines of Python saved | Why safe to cut |
|-----|----------------------|-----------------|
| types.py (3 frozen dataclasses) | ~60 | SQLite schema IS the type system |
| parsing.py (JSONL + chicsession adapters) | ~150 | Merged into audit.py extract command (~50 lines) |
| prefilter.py | ~40 | 15-line function inside audit.py |
| clustering.py (BERTopic) | ~80 + heavy deps | Judge spots patterns without clustering. Defer to v2. |
| analysis.py (pipeline orchestrator) | ~120 | Agent conversation replaces orchestration code |
| suggestions.py (validation + serialization) | ~100 | Critic agent validates. DB stores. No serialization layer needed. |
| report.py (markdown formatter) | ~80 | Auditor agent writes markdown natively |
| session_lib.py extraction | refactor | audit.py is standalone. mine_patterns.py unchanged. |
| Regex parallel detector | ~30 | 9.2% recall. Not worth the complexity in v1. |
| validate_suggestions() | ~50 | Critic agent + apply-phase graceful failure |
| Dated output files | schema | Database replaces per-run files |
| Configurable label taxonomy | ~20 | Ship general only |

**Total: ~8 files + heavy deps -> 1 file + stdlib only**

---

## 4. What We Preserve From the Spec

These spec decisions are STILL VALID and carry forward:

1. **Decision 28:** LLM classifier (Haiku) is primary. GLiClass rejected.
2. **Decision 29:** 4-role workflow (classifier, judge, critic, auditor).
3. **Decision 30:** Critic with 3-message context, 6 checks, 3 verdicts.
4. **Decision 25:** Pre-filter system boilerplate.
5. **Decision 14:** Apply phase where auditor edits files.
6. **Decision 15:** Machine-applicable suggestions with file_path, current_content, proposed_content.
7. **Decision 10:** Output to `.audit/`.
8. **Decision 20:** Category-to-workflow-fix mapping.
9. **Spec Section 5.4.1:** suggest.md content requirements (examples, anti-patterns, schema, YAML reference).
10. **Spec Section 5.4.2:** Critic validation criteria (specificity, actionability, evidence, proportionality, conflicts, feasibility).

---

## 5. Open Questions for User

1. **SQLite vs alternatives?** SQLite is my recommendation (zero deps, SQL queries, atomic writes, cross-platform). Alternatives: JSON append-only (simpler but no queries), Parquet (overkill for this data size). I'd go SQLite.

2. **Chicsession integration in v1?** The spec has elaborate chicsession join logic. For simplicity, v1 could just scan JSONL files directly. Chicsession context (agent name, workflow state) adds value but also complexity. Recommend: v1 = JSONL only, v2 = add chicsession enrichment.

3. **mine_patterns.py coupling?** The spec wanted to extract session_lib.py to share code. With the simplified design, audit.py is standalone and doesn't share code with mine_patterns.py. They can evolve independently. Is that acceptable?

4. **Batch vs interactive classification?** Current design: classifier processes all unclassified messages in one batch. Alternative: classifier could work interactively (agent reads messages one at a time). Batch is more efficient for Haiku. Recommend batch.

---

## 6. Proposed File Inventory (Simplified)

### New files

| File | Purpose | Lines (est.) |
|------|---------|-------------|
| `scripts/audit/audit.py` | The ONE Python file. Extract, store, query. | ~250 |
| `scripts/audit/__init__.py` | Empty, enables imports | 0 |
| `workflows/audit/audit.yaml` | Workflow manifest (simplified, same 4 roles, 5 phases) | ~60 |
| `workflows/audit/classifier/identity.md` | Classifier role definition | ~30 |
| `workflows/audit/classifier/analyze.md` | How to classify messages from `audit.py unclassified` | ~50 |
| `workflows/audit/judge/identity.md` | Judge role definition | ~30 |
| `workflows/audit/judge/suggest.md` | Full suggestion guidance (examples, schema, anti-patterns) | ~100 |
| `workflows/audit/critic/identity.md` | Critic role definition | ~20 |
| `workflows/audit/critic/suggest.md` | 6 validation checks, 3 verdicts | ~60 |
| `workflows/audit/auditor/identity.md` | Auditor role + cold-start + invocation UX | ~40 |
| `workflows/audit/auditor/parse.md` | Run `audit.py extract` | ~20 |
| `workflows/audit/auditor/report.md` | Present suggestions conversationally | ~30 |
| `workflows/audit/auditor/apply.md` | Edit files for approved suggestions | ~30 |

### Test files

| File | Purpose |
|------|---------|
| `tests/test_audit.py` | Test extract, dedup, pre-filter, status, incremental processing |
| `tests/fixtures/audit/` | Fixture JSONL files (reuse from spec) |

**Total: 1 Python file + 12 markdown files + 1 test file**
vs. spec's 8 Python files + 12 markdown files + 8 test files + heavy dependencies

---

## 7. Implementation Order (Simplified)

1. **audit.py core** -- SQLite schema, extract command, pre-filter, dedup
2. **audit.py CLI** -- unclassified, corrections, store-classification, store-suggestion, status
3. **Workflow manifest** -- audit.yaml with 4 roles, 5 phases
4. **Auditor markdown** -- identity.md (invocation UX, cold-start), parse.md
5. **Classifier markdown** -- identity.md, analyze.md
6. **Judge markdown** -- identity.md, suggest.md (this is the big one -- examples, schema, anti-patterns)
7. **Critic markdown** -- identity.md, suggest.md
8. **Auditor report + apply** -- report.md, apply.md
9. **Tests** -- test_audit.py + fixtures
10. **Template integration** -- copier.yml, template mirroring
