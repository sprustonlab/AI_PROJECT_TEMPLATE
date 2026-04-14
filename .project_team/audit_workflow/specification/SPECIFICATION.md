# Audit Workflow -- Specification

---

## 1. Overview

The audit workflow lives in the template source repo (root level) for template developers AND ships in generated projects for end users. Both audiences use it to improve how they interact with Claude agents. It parses JSONL session files and chicsession snapshots, uses a classifier agent (Haiku) to detect corrections, a judge agent to analyze them against workflow definitions and generate suggestions, and an auditor agent to orchestrate user review and apply approved edits. Four specialized roles collaborate: classifier, judge, critic, and auditor.

**Pipeline:** LLM classifier (Haiku) detects corrections. Regex runs in parallel as a free bonus. BERTopic discovers emergent correction clusters. A judge agent analyzes corrections against workflow definitions and generates machine-applicable suggestions. A critic agent validates suggestion quality. The auditor agent presents suggestions to the user and applies approved edits.

**Audience:** Template developers (this repo) AND end users of generated projects.
**Workflow ID:** `audit`
**Roles:** `classifier`, `judge`, `critic`, `auditor` (orchestrator)
**Location:** `workflows/audit/` (root repo) + `template/workflows/audit/` (ships in generated projects)

### Invocation UX

The user activates the workflow with `/audit`. The auditor presents an interactive options menu:

```
What would you like to audit?

1. Current session        -- audit the active chicsession
2. Saved chicsession      -- pick from saved chicsessions
3. All local conversations -- scan all JSONL files in ~/.claude/projects/
```

| Mode | Selection | Behavior |
|------|-----------|----------|
| **Current session** | `1` | Audits the active chicsession -- uses stored session_ids + workflow_state |
| **Saved chicsession** | `2` | Shows a picker (like `chicsession restore`) listing `.chicsessions/*.json` -- user selects one |
| **All local conversations** | `3` | Auto-discovers and scans all JSONL files in `~/.claude/projects/` (no chicsession context) |

Default highlight is option 1 ("current session") because it's the most natural use case ("audit what just happened") and chicsessions already carry the workflow context needed for phase-scoped analysis.

**Note:** "All local conversations" mode loses agent/workflow context -- all suggestions will be global (unscoped). Users should prefer chicsession modes for higher-quality, phase-scoped suggestions.

### Cold-Start UX

For new projects with zero session history, `/audit` produces a friendly message: "No sessions found. Run some workflows first, then come back to audit." The `identity.md` handles this check before entering the parse phase.

### Post-Report UX (Interactive Review + Apply Phase)

The report phase is **interactive and conversational**. The auditor agent presents each suggestion (or logical group) to the user and asks whether to apply or skip. The user never edits the report file -- the agent records all decisions.

**Flow:**
1. Auditor agent generates `AUDIT_REPORT_{datetime}.md` with all suggestions (initially unmarked)
2. Agent presents suggestions to the user one by one (or grouped by type/phase), explaining each
3. For each suggestion, the agent asks: "Apply this suggestion? (yes/no)"
4. Agent writes the user's decision (`[APPLY]` or `[SKIP]`) into `AUDIT_REPORT_{datetime}.md`
5. After all suggestions are reviewed, user confirms the marked-up report looks correct
6. Workflow advances to the `apply` phase -- agent edits target files for all `[APPLY]` suggestions
7. User validates the applied changes (review diffs, run tests, etc.)

### Phases

| Phase | Purpose | Advance Checks |
|-------|---------|----------------|
| `parse` | Discover and parse JSONL sessions + chicsessions into unified timeline | Agent verifies `parsed_timeline_{datetime}.json` exists |
| `analyze` | Pre-filter, LLM classifier detects+categorizes corrections, optional regex, BERTopic clustering | Agent verifies `findings_{datetime}.json` exists |
| `suggest` | Judge generates suggestions, critic validates (APPROVE/FLAG/REJECT) | Agent verifies `suggestions_{datetime}.json` + `critic_review_{datetime}.json` exist |
| `report` | Assemble report, interactively review suggestions with user | Agent verifies `AUDIT_REPORT_{datetime}.md` exists + `manual-confirm` |
| `apply` | Apply user-approved suggestions by directly editing target files | `manual-confirm`: "Apply approved suggestions?" |

### Output Priority

1. **Phase markdown changes** (HIGHEST) -- most impactful, user's primary ask
2. **Advance checks** (HIGH) -- prevent premature phase transitions
3. **Rules** (MEDIUM) -- prevent recurring tool misuse. Two enforcement levels: `warn` (recommendation) and `deny` (block).
4. **Hints** (LOWER) -- user-facing advisory reminders ONLY (hints are NOT agent behavior controls)

### Dated Output Files

All audit output files include a datetime stamp so that audit runs are preserved as historical records. Multiple audits can coexist in `.audit/` without overwriting each other.

**Datetime format:** `{YYYY-MM-DD_HHmm}` (e.g., `2026-04-13_1430`). Uses 24-hour time to support multiple runs per day.

**Output files per run:**
| File | Phase |
|------|-------|
| `.audit/parsed_timeline_{datetime}.json` | parse |
| `.audit/findings_{datetime}.json` | analyze |
| `.audit/suggestions_{datetime}.json` | suggest (judge) |
| `.audit/critic_review_{datetime}.json` | suggest (critic) |
| `.audit/AUDIT_REPORT_{datetime}.md` | report |
| `.audit/apply_log_{datetime}.json` | apply |

**Convention:** The auditor agent determines the datetime stamp at the START of the parse phase and uses the SAME stamp for all output files in that audit run. Phase markdown instructions tell the agent to establish and propagate this stamp.

**Advance checks:** Since filenames are dynamic, advance checks use `command-output-check` with glob patterns (e.g., `ls .audit/parsed_timeline_*.json`) rather than `file-exists-check` with static paths. The agent also verifies the correct dated file exists before advancing.

---

## 2. Architecture

### 2.1 Module Structure

```
scripts/
  audit/
    __init__.py                -- Public API
    session_lib.py             -- Shared JSONL parser, session discovery, regex scorer
                                  (extracted from mine_patterns.py; regex used by BOTH audit pipeline and mine_patterns)
    types.py                   -- All frozen dataclasses (audit-specific)
    parsing.py                 -- JSONL + chicsession -> ParsedInteraction adapters
    prefilter.py               -- System boilerplate stripping (agent spawns, interrupts, reminders)
    clustering.py              -- BERTopic clustering on flagged items
    analysis.py                -- Orchestrates pre-filter -> classifier + optional regex -> BERTopic
    suggestions.py             -- AuditSuggestion validation + serialization
    report.py                  -- Markdown report formatter

workflows/audit/
  audit.yaml                   -- Workflow manifest (multi-role)
  classifier/
    identity.md                -- Classifier role: scan messages, detect corrections
    analyze.md                 -- Analyze phase instructions for classifier
  judge/
    identity.md                -- Judge role: analyze corrections, generate suggestions
    suggest.md                 -- Suggest phase LLM guidance (examples, anti-patterns, schema)
  critic/
    identity.md                -- Critic role: validate suggestions (specificity, actionability, evidence, proportionality, conflicts, feasibility)
    suggest.md                 -- Critic phase instructions (runs after judge in suggest phase)
  auditor/
    identity.md                -- Auditor role: orchestrate, present to user, apply edits
    parse.md                   -- Parse phase instructions
    report.md                  -- Report phase instructions
    apply.md                   -- Apply phase instructions (edit target files)
```

Module responsibilities map to the pipeline:
- **Parse:** `session_lib.py` + `parsing.py` -- JSONL/chicsession -> `ParsedInteraction`
- **Detect:** `prefilter.py` + `analysis.py` + `clustering.py` -- LLM classifier (Haiku) + optional regex -> `CorrectionSignal`
- **Suggest:** `suggestions.py` -- judge agent generates `AuditSuggestion`, critic agent validates (APPROVE/FLAG/REJECT), code serializes
- **Report+Apply:** `report.py` -- auditor presents to user, applies approved edits

**Note:** `session_lib.py` lives INSIDE `scripts/audit/` (not as a sibling) so the entire `scripts/audit/` directory works as one clean unit. `scripts/mine_patterns.py` does NOT ship in the template -- it imports from `scripts.audit.session_lib` in this repo only.

**Dual-location layout:**
- Root repo: `scripts/audit/` + `workflows/audit/` (used by template developers directly)
- Template: `template/scripts/audit/` + `template/workflows/audit/` (mirrored for generated projects)
- Does NOT ship: `scripts/mine_patterns.py`, test fixtures, dev scripts
- Requires: `scripts/__init__.py` (empty) for import chain in both locations

### 2.2 Data Flow (Multi-Agent Pipeline)

```
JSONL sessions ──> [session_lib] ──> ParseResult/Message ──┐
                                                            ├──> [parsing.py] ──> ParsedInteraction[]
Chicsession JSON ──> [chicsessions.py] ──> Chicsession ────┘          |
                                                                       v
                                                              [prefilter.py] ──> clean user messages
                                                              Strip system boilerplate (agent spawns,
                                                              interrupts, reminders, notifications)
                                                                       |
                                                                       v (clean messages)
                                                              ┌────────┴────────┐
                                                              |                 |    PARALLEL (optional)
                                                    [CLASSIFIER AGENT]   [session_lib regex]
                                                    LLM (Haiku) scans    keyword patterns
                                                    all messages,         threshold 0.3
                                                    flags + categorizes   (free, supplemental)
                                                    (primary detector)    |
                                                              |                 |
                                                              └────────┬────────┘
                                                                       v
                                                              [analysis.py] UNION
                                                                       |
                                                                       v (all flagged items)
                                                              [clustering.py]
                                                              BERTopic clusters
                                                              (emergent themes)
                                                                       |
                                                                       v
                                                              [analysis.py] ──> CorrectionSignal[]
                                                                       |
                                                                       v
Workflow manifests ──> [ManifestLoader] ──> LoadResult ──┐   [JUDGE AGENT / LLM]
Phase markdown files ────────────────────────────────────┤   Reviews signals + categories + clusters,
Global rules/hints ──────────────────────────────────────┘   reads workflow definitions,
                                                              identifies gaps, generates suggestions
                                                                       |
                                                                       v
                                                              [CRITIC AGENT / LLM]
                                                              Validates each suggestion:
                                                              specificity, actionability,
                                                              evidence, proportionality,
                                                              conflicts, feasibility
                                                              Verdict: APPROVE / FLAG / REJECT
                                                                       |
                                                                       v
                                                              [report.py] ──> AUDIT_REPORT_{datetime}.md
                                                                       |
                                                              [AUDITOR AGENT / LLM]
                                                              Presents suggestions to user,
                                                              asks apply/skip for each,
                                                              writes decisions to report
                                                                       |
                                                                       v
                                                              [AUDITOR AGENT / LLM]
                                                              Reads approved suggestions,
                                                              edits target MD + YAML files
                                                                       |
                                                                       v
                                                              Applied file edits + apply_log_{datetime}.json
```

**The critical distinction:** Parse and pre-filter are deterministic code. Detection is LLM-driven (classifier agent using Haiku). Suggestion generation is LLM-driven (judge agent). Suggestion validation is LLM-driven (critic agent). The auditor agent orchestrates the user-facing workflow.

### 2.3 Shared Module Extraction (scripts/audit/session_lib.py)

Extract shared code from `mine_patterns.py` into `scripts/audit/session_lib.py` before building audit on top. Nested inside `audit/` so the entire package ships as one unit in the template.

**What moves to session_lib.py:**
- `Message` dataclass
- `ParseResult` dataclass
- `ParseStats` dataclass
- `_extract_text()` function
- `_detect_version()` function
- `parse_session()` function
- `tier1_score_message()` function (used by BOTH audit pipeline and mine_patterns.py)
- `ALL_PATTERN_BANKS` (NEGATION, FRUSTRATION, ERROR, CORRECTION patterns -- used by both)
- `discover_session_files()` function
- `DEFAULT_AGENT_ROLES` list -- but made CONFIGURABLE (not hardcoded to this repo's roles)

The regex-based `tier1_score_message()` and `ALL_PATTERN_BANKS` are used by `mine_patterns.py` and optionally by the audit pipeline as a free parallel signal alongside the LLM classifier.

**What stays in mine_patterns.py (repo-only, does NOT ship):**
- CLI (`build_parser()`, `main()`)
- Pipeline orchestration (`run_pipeline()`, `run_validate()`)
- Tier-2 and tier-3 logic (semantic + clustering)
- State file tracking
- Report output formatting

**Import chain:** `scripts/__init__.py` (empty) enables `from scripts.audit.session_lib import ...`. mine_patterns.py imports from `scripts.audit.session_lib` in this repo.

### 2.4 Phase-to-Correction Mapping Strategy

Chicsessions are snapshots (final state), not timelines. JSONL doesn't record phase transitions explicitly. Phase mapping uses a hybrid strategy:

1. **Primary: Scan JSONL for phase-transition markers.** Look for:
   - `advance_phase` tool calls in assistant messages
   - Phase announcement strings in system messages (e.g., "Advanced to phase: project-team:implementation")
   - `/advance` command strings in user messages
   - Build a timeline: `[(message_index, phase_id), ...]`
   - Each correction gets the phase from the most recent transition marker before it

2. **Fallback: Chicsession final state.** If no transition markers found in JSONL (e.g., single-phase session, or session without workflow), use `workflow_state.current_phase` from chicsession as best-guess for all messages.

3. **Last resort: None.** If neither source provides phase context, `phase_id = None` and suggestions are unscoped (global).

**Fragility mitigation:** Phase mapping is best-effort. The analyzer marks each correction's phase confidence: `phase_confidence: "inferred" | "snapshot" | "unknown"`. The LLM-as-judge only generates phase-scoped suggestions from `"inferred"` confidence; `"snapshot"` and `"unknown"` produce global suggestions.

---

## 3. Terminology

### New Terms (6)

| Term | Definition |
|------|------------|
| **ParsedInteraction** | Parsed session from JSONL or chicsession. Input to the detect stage. |
| **CorrectionSignal** | Detected user correction. Detected by LLM classifier (Haiku, primary) with optional regex parallel signal. Collapses synonyms: correction/redirection/fix/override. |
| **AuditSuggestion** | LLM-generated recommendation to modify one workflow artifact. Machine-applicable with exact file paths and content. Output of the suggest stage. |
| **AuditReport** | The structured Markdown output combining signals and suggestions. Final deliverable. |

### Existing Terms Reused (14)

`Message`, `ParseResult`, `ParseStats` (session_lib.py), `Chicsession`, `ChicsessionEntry` (chicsessions.py), `Phase`, `CheckDecl`, `CheckResult` (claudechic checks), `HintDecl`, `HintSpec`, `HintRecord` (claudechic hints), `Rule`, `Manifest`.

### Collision Rules

- **NEVER** use bare "pattern" for behavioral observations -- "pattern" means regex banks (session_lib/mine_patterns). Use `CorrectionSignal`.
- **NEVER** use "check" for audit analysis -- "check" means async verification protocol. Audit "analyzes."
- **NEVER** use "AuditResult" -- `ParseResult` + `CheckResult` already exist. Use `AuditReport`.
- **NEVER** use bare "session" -- always "JSONL session" or "chicsession."
- **NEVER** use bare "score" for severity -- detection confidence owns "score." Use `priority` (1-4) for severity ranking.
- **NEVER** say "suggestions.py generates suggestions" -- `suggestions.py` provides validation and serialization. The judge agent generates suggestion content.
- **NEVER** say regex is the "primary" detector -- the LLM classifier (Haiku) is primary. Regex is an optional free parallel signal.

---

## 4. Data Models

3 dataclasses in `scripts/audit/types.py`. That's it.

```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedInteraction:
    """Input: parsed session from JSONL or chicsession source."""
    source_path: Path
    source_type: str                   # "jsonl" | "chicsession"
    session_id: str | None
    workflow_id: str | None
    phase_id: str | None               # From chicsession snapshot (best-guess)
    agent_name: str | None
    messages: list                     # list[Message] from session_lib
    session_date: str
    phase_transitions: list            # list[tuple[int, str]] -- (msg_index, phase_id)


@dataclass(frozen=True)
class CorrectionSignal:
    """Middle: detected user correction. Output of the detect stage.
    Includes 3-message context window for judge and critic analysis."""
    context_before: str | None         # Agent message BEFORE (what agent did wrong)
    user_text: str                     # The user correction itself
    context_after: str | None          # Agent message AFTER (how agent responded)
    detection_source: str              # "llm" | "regex" | "both"
    llm_confidence: str                # "high" | "medium" | "low" (from classifier agent)
    category: str | None               # 6-category classification (from classifier agent)
    cluster_id: int | None             # BERTopic cluster ID
    cluster_label: str | None          # BERTopic topic label
    session_id: str | None
    agent_name: str | None
    workflow_id: str | None
    phase_id: str | None               # Inferred from phase_transitions
    phase_confidence: str              # "inferred" | "snapshot" | "unknown"
    turn_index: int                    # Position in conversation


@dataclass(frozen=True)
class AuditSuggestion:
    """Output: LLM-generated suggestion. Machine-applicable."""
    artifact_type: str                 # "phase-markdown" | "advance-check" | "rule" | "hint"
    file_path: str                     # Relative path to target file
    suggestion_type: str               # "add" | "modify"
    current_content: str | None        # Text to replace (None if new addition)
    proposed_content: str              # Replacement text or YAML
    insertion_point: str | None        # For "add": marker after which to insert
    rationale: str                     # Why this change helps
    evidence_count: int                # How many signals support this
    priority: int                      # 1=critical, 2=high, 3=medium, 4=low
    apply_status: str                  # "pending" | "apply" | "skip"
```

**Collections:** Use plain `list[CorrectionSignal]`, `list[AuditSuggestion]`, and a `stats: dict` for aggregates. No wrapper dataclasses.

### 4.1 LLM Output Validation (in scripts/audit/suggestions.py)

LLM output is validated programmatically AFTER the auditor writes `suggestions_{datetime}.json`. Do not trust the LLM to self-validate.

```python
def validate_suggestions(
    suggestions: list[AuditSuggestion],
    project_root: Path,
) -> tuple[list[AuditSuggestion], list[str]]:
    """Validate LLM-generated suggestions. Returns cleaned list + warnings.

    Checks:
    1. All YAML snippets parse with yaml.safe_load()
    2. All file_path values exist on disk
    3. All enum values are valid (trigger, lifecycle, enforcement)
    4. All suggested rule IDs are bare (no colons)

    Invalid suggestions are SKIPPED with a warning, not retried.
    Warnings are included in the final report.
    """
    ...
```

**Failure mode:** Skip invalid suggestions with warning in report (e.g., "1 suggestion omitted: invalid YAML"). Never retry. Never block.

---

## 5. Module Specifications

### 5.1 session_lib.py (extracted from mine_patterns.py)

**Purpose:** Shared JSONL parsing, session discovery, and regex scoring library. Used by mine_patterns.py and optionally by the audit pipeline as a free parallel signal alongside the LLM classifier.

**Exports:**
- `Message`, `ParseResult`, `ParseStats` -- frozen dataclasses
- `parse_session(path, agent_roles) -> ParseResult` -- JSONL parser
- `tier1_score_message(text, ...) -> tuple[float, str | None]` -- regex scorer (used by mine_patterns.py, optionally by audit pipeline)
- `discover_session_files(project_dirs) -> list[Path]` -- session file discovery
- `ALL_PATTERN_BANKS` -- pattern bank data (NEGATION, FRUSTRATION, ERROR, CORRECTION)
- `DEFAULT_AGENT_ROLES` -- agent role list
- `KNOWN_VERSIONS` -- version set

Regex is an optional free parallel signal in the audit pipeline. The LLM classifier (Haiku) is the primary detector.

**Cross-platform:**
- `encoding='utf-8', errors='replace'` on all file reads
- `pathlib.Path` throughout
- No non-ASCII characters (do NOT propagate em-dash from mine_patterns.py line 304)

### 5.2 audit/parsing.py

**Purpose:** Adapt JSONL sessions and chicsession snapshots into `ParsedInteraction` objects.

**Key behaviors:**

1. **Chicsession-aware parsing:**
   - Load chicsession JSON via `ChicsessionManager`
   - For each `ChicsessionEntry`: resolve `session_id` to JSONL file path
   - Path resolution: scan `~/.claude/projects/` for `{session_id}.jsonl` and `agent-{session_id}.jsonl`
   - Annotate each `ParsedInteraction` with `agent_name`, `workflow_id`, `phase_id` from chicsession

2. **Phase transition extraction:**
   - Scan JSONL messages for phase-transition markers:
     - Assistant messages containing `advance_phase` tool calls
     - System messages containing "Advanced to phase:" strings
     - User messages containing `/advance` commands
   - Build `phase_transitions: list[tuple[int, str]]` -- ordered (message_index, phase_id) pairs
   - If no markers found: use chicsession `workflow_state.current_phase` as fallback

3. **Session ID join:**
   - Chicsession `session_id` -> JSONL filename is the join key
   - Handle stale references gracefully: skip with warning if JSONL file not found
   - Handle resumed sessions: if session_id not found, try glob for recent JSONL files in the same project dir

4. **All local conversations mode:**
   - User selected option 3 from the interactive menu
   - Auto-discover JSONL files: scan `~/.claude/projects/` recursively for `*.jsonl` and `agent-*.jsonl`
   - Use `session_lib.discover_session_files()` for discovery
   - No agent_name or workflow context available -- all fields None

**Output:** `list[ParsedInteraction]`

### 5.3a audit/prefilter.py (System Boilerplate Stripping)

**Purpose:** Remove system boilerplate messages before detection. These are not user corrections and would pollute results.

**Stripped patterns:**
- Agent spawn messages: `[Spawned by agent`
- Interrupt messages: `[Request interrupted`
- Task notifications: `<task-notification>`
- Idle reminders: `You have been idle`
- Agent messages: `[Message from agent`, `[Question from agent`
- System reminders: `<system-reminder>`

**Exports:**
- `prefilter(messages: list[Message]) -> list[Message]` -- returns clean user messages only

### 5.3b Classifier Agent (LLM -- Haiku)

**Purpose:** A SEPARATE agent role (`classifier`) that scans ALL pre-filtered user messages and flags corrections with category. This is NOT the auditor -- it's a specialized detection agent spawned during the analyze phase.

**Model:** Claude Haiku (fast, low-cost).

**What the classifier does:**
1. Receives all pre-filtered messages as input (full session context for sessions under 30 turns; windowed context for longer sessions)
2. For each user message, determines: is this a correction? (yes/no)
3. If yes, assigns a category from the 6-category taxonomy
4. Returns confidence level: "high" / "medium" / "low"
5. Extracts 3-message context window for each flagged correction:
   - `context_before`: the agent message immediately before (what the agent did that triggered the correction)
   - `user_text`: the correction itself
   - `context_after`: the agent message immediately after (how the agent responded to the correction)
6. Output: list of flagged messages with category + confidence + 3-message context window

**6-category taxonomy (classifier assigns one per flagged message):**

Two configurable label sets (general is default):

**General (default):**

| # | Category | Description |
|---|----------|-------------|
| 1 | Factual Correction | User corrects factual errors in agent output |
| 2 | Approach Redirect | User redirects the agent's approach/strategy |
| 3 | Intent Clarification | User clarifies their original intent |
| 4 | Scope/Detail Adjustment | User adjusts scope or level of detail |
| 5 | Style/Format Preference | User requests style or format changes |
| 6 | Frustration/Escalation | User expresses frustration or escalates |

**Coding-specific (alternative):**

| # | Category | Description |
|---|----------|-------------|
| 1 | Wrong File | Agent edited the wrong file |
| 2 | Wrong Implementation | Agent implemented incorrectly |
| 3 | Wrong Approach | Agent took the wrong approach entirely |
| 4 | Misunderstood Task | Agent misunderstood what was asked |
| 5 | Too Much/Too Little | Agent did too much or too little |
| 6 | Process Complaint | User complains about process/workflow |

**Category-to-workflow-fix mapping (used by judge agent):**

| Category | Suggested Fix Types |
|----------|-------------------|
| Factual Correction | Phase markdown, rules (warn or deny) |
| Approach Redirect | Phase markdown, rules (warn or deny) |
| Intent Clarification | Phase markdown |
| Scope/Detail Adjustment | Phase markdown |
| Style/Format Preference | Hints (user-facing ONLY) |
| Frustration/Escalation | Rules (deny), advance checks |

### 5.3c audit/clustering.py (BERTopic Clustering)

**Purpose:** Discover emergent correction themes using BERTopic on flagged items (from classifier + optional regex union).

**Key behaviors:**
1. Takes all flagged item texts (from union) as input
2. Runs BERTopic to discover natural clusters (no predefined number)
3. Generates topic labels and representative documents per cluster
4. Output: cluster assignments + topic labels + representatives

**Exports:**
- `cluster_corrections(texts: list[str]) -> ClusterResult`

### 5.3d audit/analysis.py (Pipeline Orchestrator)

**Purpose:** Orchestrate the full detection pipeline: pre-filter -> classifier agent + optional regex -> BERTopic clustering.

**Pipeline:**

1. **Pre-filter -- strip system boilerplate:**
   - Run `prefilter.prefilter()` on all messages
   - Removes agent spawns, interrupts, system reminders, task notifications
   - Output: clean user messages only

2. **LLM classifier (primary detector):**
   - Spawn the `classifier` agent with all clean messages (full session if <30 turns; windowed for longer)
   - Classifier (Haiku) scans each user message, flags corrections with category + confidence
   - For each flagged correction, extracts 3-message context window:
     - `context_before`: agent message immediately before the correction
     - `user_text`: the correction itself
     - `context_after`: agent message immediately after the correction
   - Output: list of flagged messages with category + llm_confidence + 3-message context

3. **Regex (optional parallel signal):**
   - Run `session_lib.tier1_score_message()` on all clean user messages
   - Uses existing pattern banks (NEGATION, FRUSTRATION, ERROR, CORRECTION). Threshold 0.3.
   - Free supplemental signal -- catches keyword-driven corrections the LLM might miss

4. **Union -- merge flagged sets:**
   - Take the union of LLM-flagged and regex-flagged messages
   - Mark each with `detection_source`: "llm", "regex", or "both"
   - LLM-flagged items already have category from classifier; regex-only items get category=None (judge assigns later)

5. **BERTopic clustering on ALL flagged items:**
   - `clustering.cluster_corrections()` discovers emergent themes
   - Output: cluster assignments + topic labels + representatives

6. **Merge into CorrectionSignal objects:**
   - Build `CorrectionSignal` with `context_before`, `user_text`, `context_after`, `detection_source`, `category`, `cluster_id`, `llm_confidence`
   - For regex-only flags: extract `context_before`/`context_after` from the message list (agent messages adjacent to the flagged user message)
   - Assign `phase_id` from `phase_transitions` timeline (most recent transition before this message)
   - Set `phase_confidence`: "inferred" if from transition markers, "snapshot" if from chicsession, "unknown" otherwise

7. **Frequency threshold:**
   - Track signal counts per (category, phase_id, agent_name) triple
   - Only signals that appear 3+ times across sessions qualify as patterns (configurable)

8. **Statistics:**
   - Per-phase: signal count, user turns, signal rate, category distribution
   - Per-agent: signal count, user turns, signal rate
   - Per-category: signal count, top clusters
   - Per-detection-source: llm-only count, regex-only count, both count
   - Overall: sessions analyzed, total signals, overall rate, flag rate

**Output:** `list[CorrectionSignal]` + statistics dict

### 5.4 Suggestion Generation (Judge Agent)

**Purpose:** A SEPARATE agent role (`judge`) that analyzes flagged corrections, reads workflow definitions, identifies gaps, and generates machine-applicable suggestions. This is NOT the auditor -- it's a specialized analysis agent spawned during the suggest phase.

**How it works:**

The `suggest` phase instructs the judge agent to:

1. **Read the correction signals** (from `findings_{datetime}.json` produced by the analyze phase), which include:
   - Category assignments per signal
   - BERTopic cluster IDs and labels
   - Cluster representatives (most characteristic examples)
2. **Read the actual workflow artifacts:**
   - Phase markdown files
   - Existing rules, hints, advance checks in manifests
   - Global rules and hints
3. **Use category-to-fix mapping** to determine what type of fix each correction needs:
   - Factual Correction / Approach Redirect -> Phase markdown, rules (warn or deny)
   - Intent Clarification / Scope-Detail Adjustment -> Phase markdown
   - Style/Format Preference -> Hints (user-facing ONLY -- hints are NOT agent behavior controls)
   - Frustration/Escalation -> Rules (deny), advance checks
4. **Understand the content** via cluster representatives -- not just "a correction happened in phase X" but "the user had to repeatedly tell the agent to read error output before retrying tests in the implementation phase"
4. **Generate suggestions** that are:
   - Grounded in evidence (specific correction signals with quotes)
   - Targeted to specific files (exact paths)
   - Machine-applicable (exact `current_content` for replacements, exact `insertion_point` for additions)
   - Valid content (valid markdown for phase files, valid YAML for rules/hints/checks)
   - Prioritized (phase markdown > checks > rules > hints)
   - Directly applicable by the auditor agent in the apply phase (no manual copy-paste needed)

**The `scripts/audit/suggestions.py` module provides:**
- AuditSuggestion dataclass
- YAML validation (ensure generated YAML is parseable)
- Serialization to/from `suggestions_{datetime}.json`
- But NOT the actual suggestion content -- that comes from the judge agent

**Phase markdown instructions (`judge/suggest.md`) guide the LLM to:**
- Group findings by phase and artifact type
- Read current phase markdown and identify what's missing
- Draft specific text additions/modifications
- Draft valid YAML snippets for checks/rules/hints
- Apply minimum evidence thresholds:
  - Phase markdown: 2+ signals required
  - Advance checks: 3+ signals required
  - Rules: 3+ signals required
  - Hints: 2+ signals required
- Validate all YAML output before writing

**Findings budget:** Sort findings by severity, cap at top 20 findings passed to the suggest phase. Report notes "X additional lower-severity findings omitted" if any are dropped. This prevents context window exhaustion.

**Output:** `suggestions_{datetime}.json` containing `list[AuditSuggestion]` (validated by `validate_suggestions()` in the report phase)

### 5.4.1 suggest.md Content Requirements

The `judge/suggest.md` phase markdown is critical -- it IS the judge agent's instructions. Must include:

1. **Output schema** -- exact JSON structure for `suggestions_{datetime}.json` so the LLM produces valid, deserializable output. Include the `AuditSuggestion` field names, types, and examples. Emphasize `insertion_point` and `current_content` fields that enable machine application.

2. **Worked example** -- at least one full example showing:
   - Input: "3 correction signals in implementation phase where users corrected agents for retrying tests without reading errors"
   - Output: complete `AuditSuggestion` with `file_path` pointing to the implementation phase markdown, exact `current_content` (text to replace) or `insertion_point` (marker after which to insert), proposed text addition, evidence count
   - Must demonstrate that the suggestion is machine-applicable (the auditor agent can use Read + Edit tools to apply it later in the apply phase)

3. **Tone/voice instructions** -- suggestions become content that other LLMs read. Write in imperative voice matching existing phase markdown conventions (e.g., "Always read error output before retrying" not "The agent should consider reading error output").

4. **Anti-patterns** -- what NOT to suggest:
   - Rules that block their own prerequisites (catch-22 pattern from CLAUDE.md)
   - Overly broad rules that fire on legitimate operations
   - Hints that duplicate existing hints (read existing hints first)
   - Phase markdown changes for phases that don't exist in the target workflow

5. **How to access artifacts** -- explicit instructions to use Read tool on target `file_path` to read current content before proposing changes.

6. **YAML reference** -- enumerate valid values for:
   - `trigger`: `PreToolUse/Bash`, `PreToolUse/Write`, etc.
   - `enforcement`: `deny` (block), `warn` (recommendation) -- NO `log` level
   - `lifecycle`: `show-once`, `show-every-session`, `show-until-resolved`, `cooldown-period`
   - `check type`: `file-exists-check`, `file-content-check`, `command-output-check`, `manual-confirm`

7. **Dual-update note** -- extending suggestion types requires updating BOTH `suggestions.py` (new dataclass field) AND `judge/suggest.md` (new LLM instructions).

8. **3-message context** -- the judge receives `context_before`, `user_text`, and `context_after` for each correction. Instructions should tell the judge to analyze the agent's mistake (context_before), the user's correction, AND whether the agent fixed it (context_after). If the agent repeated the mistake after correction, the suggestion is more urgent.

### 5.4.2 Critic Agent (Suggestion Validation)

**Purpose:** A SEPARATE agent role (`critic`) that validates each suggestion from the judge before it reaches the user. Runs in the suggest phase AFTER the judge. Single-pass validation, not multi-round debate.

**Why a separate critic:**
- Self-critique is unreliable -- models rate their own output too leniently
- A quality gate catches hallucinated rules, disproportionate suggestions, and false positives

**What the critic checks (6 validation criteria):**

| # | Check | Question |
|---|-------|----------|
| 1 | **Specificity** | Can this be turned into a concrete rule/check/hint? Reject vague advice. |
| 2 | **Actionability** | Can this actually be implemented as a workflow artifact? |
| 3 | **Evidence grounding** | Do the cited corrections actually demonstrate this problem? Check the 3-message context windows. |
| 4 | **Proportionality** | Is N corrections enough to justify this change? (threshold: 3+ for rules/checks, 2+ for markdown/hints) |
| 5 | **Conflict detection** | Would this suggestion conflict with existing workflow rules or create contradictions? |
| 6 | **Feasibility** | Can the agent actually follow this rule? Guards against the catch-22 pattern ("DON'T write guardrail rules that block their own prerequisites"). |

**3-message context for critic validation:**

The critic receives the full `CorrectionSignal` for each suggestion's supporting evidence, including:
- `context_before`: what the agent did wrong (root cause analysis)
- `user_text`: the correction itself (what the user actually said)
- `context_after`: how the agent responded (did it fix the issue or repeat the mistake?)

This context lets the critic judge whether the suggestion actually addresses the root cause. Examples:
- If `context_after` shows the agent immediately fixed the issue -> suggestion may be lower priority
- If `context_after` shows the agent repeated the same mistake -> suggestion is high priority
- If `context_before` shows the agent was following existing rules that conflict -> suggestion needs conflict check

**Three verdicts:**

| Verdict | Meaning | Action |
|---------|---------|--------|
| **APPROVE** | Suggestion is specific, actionable, evidence-backed, proportionate, no conflicts | Pass to report |
| **FLAG** | Suggestion has merit but needs revision | Critic provides `revised_suggestion`; revised version passes to report |
| **REJECT** | Suggestion is vague, unsupported, disproportionate, or based on false positive | Drop from report with logged reason |

**Critic output per suggestion:**
```json
{
  "suggestion_id": "<id>",
  "verdict": "APPROVE | FLAG | REJECT",
  "concerns": ["<list of specific concerns, empty if approved>"],
  "revised_suggestion": "<improved version if FLAG, null otherwise>",
  "reasoning": "<1-2 sentence explanation>"
}
```

**Pipeline integration:**
1. Judge generates `list[AuditSuggestion]` -> written to `suggestions_{datetime}.json`
2. Critic reads `suggestions_{datetime}.json` + supporting `CorrectionSignal` evidence (with 3-message context)
3. Critic validates each suggestion -> writes `critic_review_{datetime}.json`
4. `validate_suggestions()` runs on APPROVED + FLAG'd (revised) suggestions
5. Final validated suggestions pass to report phase

**Output file:** `.audit/critic_review_{datetime}.json`

### 5.5 audit/report.py

**Purpose:** Assemble structured Markdown report with machine-applicable suggestions. The report is generated with suggestions initially unmarked. During the interactive review, the auditor agent presents each suggestion to the user, asks for approval, and writes `[APPLY]` or `[SKIP]` markers into the report based on the user's decisions.

**Output format:**

```markdown
# Audit Report -- {date}

## Summary
- Sessions analyzed: N
- Total user turns: N
- Correction signals detected: N (rate: X%)
- Audit findings: N
- Suggestions generated: N

## Correction Signals by Phase
| Phase | Signals | User Turns | Rate | Phase Confidence |
|-------|---------|------------|------|-----------------|
| ...   | ...     | ...        | ...  | ...             |

## Correction Signals by Agent
| Agent | Signals | User Turns | Rate |
|-------|---------|------------|------|
| ...   | ...     | ...        | ...  |

## Audit Findings
### Finding 1: {description}
- **Gap type:** {phase-gap | missing-check | weak-rule | missing-hint}
- **Severity:** {critical | high | medium | low}
- **Affected phase:** {phase_id} (confidence: {inferred | snapshot | unknown})
- **Affected agent:** {agent_name}
- **Related definitions:** {existing IDs}
- **Evidence (top 3):**
  - "{user_text}" (turn {N}, session {id})
  - ...

---

## Suggestions

### Phase Markdown Changes ({count})

#### Suggestion 1 `[PENDING]` (priority: {N}, evidence: {count} signals across {count} sessions)
- **Target:** `{file_path}`
- **Type:** {add | modify | strengthen}
- **Rationale:** {why}
- **Current text:**
```
{current_content or "(none -- new addition)"}
```
- **Suggested text:**
```
{proposed_content}
```

### Advance Check Suggestions ({count})

#### Suggestion 1 `[PENDING]` (priority: {N}, evidence: {count} signals)
- **Target:** workflow `{workflow_id}`, phase `{phase_id}`
- **Rationale:** {why}
- **YAML:**
```yaml
{proposed_content}
```

### Rule Suggestions ({count})

#### Suggestion 1 `[PENDING]` (priority: {N}, evidence: {count} signals)
- **Scope:** {global | workflow_id}
- **Rationale:** {why}
- **YAML:**
```yaml
{proposed_content}
```

### Hint Suggestions ({count})

#### Suggestion 1 `[PENDING]` (priority: {N}, evidence: {count} signals)
- **Scope:** {global | workflow_id}, phase: {phase_id | all}
- **Rationale:** {why}
- **YAML:**
```yaml
{proposed_content}
```

<!-- Markers are initially [PENDING]. During interactive review, the auditor agent
     replaces each with [APPLY] or [SKIP] based on the user's conversational response. -->
```

### 5.6 Report Phase Interactive Review (LLM-Driven)

**Purpose:** After generating the report, the auditor agent interactively walks the user through each suggestion and records their apply/skip decisions. The user never edits the report file directly.

**How it works (still in report phase):**

1. **Generate `AUDIT_REPORT_{datetime}.md`** with all suggestions marked `[PENDING]`
2. **Present suggestions to the user** -- one by one or grouped by type/phase:
   - Show the suggestion summary, target file, rationale, and proposed change
   - Ask: "Apply this suggestion? (yes/no)"
   - Optionally group related suggestions (e.g., "These 3 suggestions all target the implementation phase -- apply all?")
3. **Write decisions into the report** -- replace `[PENDING]` with `[APPLY]` or `[SKIP]` for each suggestion based on user response
4. **Present summary** -- "N suggestions approved, M skipped. Ready to apply?"
5. **User confirms** the marked-up report is correct before advancing

### 5.7 Apply Phase (LLM-Driven -- the auditor agent edits files)

**Purpose:** The auditor agent directly edits target MD and YAML files to apply user-approved suggestions.

**How it works:**

The `apply` phase instructs the auditor agent to:

1. **Read `AUDIT_REPORT_{datetime}.md`** and identify all `[APPLY]` suggestions (skip `[SKIP]` ones)
2. **For each `[APPLY]` suggestion**, apply the edit:
   - **Phase markdown (add):** Read the target file, find the `insertion_point`, insert `proposed_content` after it
   - **Phase markdown (modify/strengthen):** Read the target file, find `current_content`, replace with `proposed_content`
   - **Advance checks / rules / hints (YAML):** Read the target YAML file, parse it, insert or modify the relevant section, write back valid YAML
3. **Log each applied edit** to `.audit/apply_log_{datetime}.json`:
   - Suggestion ID, target file, edit type, success/failure, error message if any
4. **Skip gracefully** if a target file doesn't exist or `current_content` can't be found (log warning, continue)
5. **Never retry failed edits** -- log the failure and move on
6. **Present summary to user** -- "Applied N suggestions, skipped M, failed F. Please review the changes."

**Phase markdown (`auditor/apply.md`) guides the LLM to:**
- Use Read tool to verify file contents before editing
- Use Edit tool (not Write) for modifications to preserve surrounding content
- Validate YAML after editing (load with yaml.safe_load to verify)
- Report a summary of applied vs skipped vs failed suggestions

**Output:** Applied file edits + `.audit/apply_log_{datetime}.json`

**Guardrail note:** The `no_direct_edit_workflows` and `no_direct_edit_rules` rules explicitly EXCLUDE the apply phase. The auditor agent is ALLOWED to edit workflow files and global files during the apply phase only.

---

## 6. Workflow Manifest

```yaml
workflow_id: audit
main_role: auditor

roles:
  - id: classifier
    description: "Scans messages, detects and categorizes corrections (Haiku)"
  - id: judge
    description: "Analyzes corrections, reads workflow definitions, generates suggestions"
  - id: critic
    description: "Validates suggestions: specificity, actionability, evidence, proportionality, conflicts, feasibility"
  - id: auditor
    description: "Orchestrates workflow, presents to user, applies approved edits"

phases:
  - id: parse
    role: auditor
    file: parse
    hints:
      - message: "Phase 1/5: Parse JSONL sessions and chicsessions into a unified timeline."
        lifecycle: show-once
      - message: "Choose a mode: current session, saved chicsession (picker), or all local conversations."
        lifecycle: show-once
      - message: "Use datetime stamp for output files: parsed_timeline_{YYYY-MM-DD_HHmm}.json"
        lifecycle: show-once
    advance_checks:
      - type: command-output-check
        command: "ls .audit/parsed_timeline_*.json 2>/dev/null | tail -1"
        expected: ".audit/parsed_timeline_"
        on_failure:
          message: "Run the parser to generate parsed_timeline_{datetime}.json"
          severity: warning

  - id: analyze
    role: auditor
    file: analyze
    hints:
      - message: "Phase 2/5: Pre-filter, spawn classifier agent (Haiku) to detect corrections, optional regex, BERTopic clustering."
        lifecycle: show-once
    advance_checks:
      - type: command-output-check
        command: "ls .audit/findings_*.json 2>/dev/null | tail -1"
        expected: ".audit/findings_"
        on_failure:
          message: "Run the analyzer to generate findings_{datetime}.json"
          severity: warning

  - id: suggest
    role: auditor
    file: suggest
    hints:
      - message: "Phase 3/5: Spawn judge agent to generate suggestions, then critic agent to validate them."
        lifecycle: show-once
      - message: "Suggestions require minimum evidence thresholds: 2+ for markdown/hints, 3+ for checks/rules."
        lifecycle: show-once
    advance_checks:
      - type: command-output-check
        command: "ls .audit/suggestions_*.json 2>/dev/null | tail -1"
        expected: ".audit/suggestions_"
        on_failure:
          message: "Run the judge to generate suggestions_{datetime}.json"
          severity: warning
      - type: command-output-check
        command: "ls .audit/critic_review_*.json 2>/dev/null | tail -1"
        expected: ".audit/critic_review_"
        on_failure:
          message: "Run the critic to validate suggestions"
          severity: warning

  - id: report
    role: auditor
    file: report
    hints:
      - message: "Phase 4/5: Present suggestions interactively. Ask the user to approve or skip each one."
        lifecycle: show-once
      - message: "Write [APPLY]/[SKIP] decisions into AUDIT_REPORT_{datetime}.md based on user responses."
        lifecycle: show-once
    advance_checks:
      - type: command-output-check
        command: "ls .audit/AUDIT_REPORT_*.md 2>/dev/null | tail -1"
        expected: ".audit/AUDIT_REPORT_"
        on_failure:
          message: "Generate the final report first"
          severity: warning
      - type: manual-confirm
        prompt: "All suggestions reviewed. Ready to apply approved changes?"

  - id: apply
    role: auditor
    file: apply
    hints:
      - message: "Phase 5/5: Applying approved suggestions. Edit target files directly for all [APPLY] items."
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
    message: "Only the auditor in the apply phase should edit workflow files. Other roles suggest changes only."
    phases: [parse, analyze, suggest, report]

  - id: no_direct_edit_rules
    trigger: PreToolUse/Write
    enforcement: warn
    detect:
      pattern: "global/"
    message: "Only the auditor in the apply phase should edit global files. Other roles suggest changes only."
    phases: [parse, analyze, suggest, report]
```

---

## 7. Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| LLM generates invalid YAML | High | `validate_suggestions()` runs post-write. Invalid suggestions skipped with warning in report. Never retry. |
| LLM hallucinated file paths | High | `validate_suggestions()` checks all `file_path` values exist on disk. |
| LLM exceeds context window | Medium | Findings budget: top 20 findings by severity passed to suggest phase. Report notes omissions. |
| LLM classifier cost | Low | Haiku is low-cost. Budget cap configurable per audit run. |
| Classifier agent spawn overhead | Medium | Spawn classifier as sub-agent during analyze phase. Keep message batching efficient. |
| BERTopic empty clusters | Low | Handle gracefully: if <5 flagged items, skip clustering (too few for meaningful topics). |
| Phase-to-correction mapping | High | Hybrid strategy: scan JSONL for transition markers (primary), chicsession final state (fallback), None (last resort). Mark `phase_confidence` on each signal. |
| mine_patterns.py coupling | High | Extract `session_lib.py` into `scripts/audit/`. mine_patterns.py imports from it. Regex shared by both audit and mine_patterns. |
| Import chain in generated projects | Medium | `scripts/__init__.py` (empty) enables package imports. `session_lib.py` nested inside `audit/`. |
| Hardcoded agent roles | Medium | `DEFAULT_AGENT_ROLES` in session_lib.py is configurable, not hardcoded to template repo roles. |
| JSONL format instability | Medium | Reuse session_lib version-aware parsing. Log warnings for unknown versions. |
| Stale session ID references | Medium | Graceful skip with warning if JSONL file not found for a chicsession entry. |
| Cold-start (zero sessions) | Low | `identity.md` detects zero sessions, shows friendly "run workflows first" message. |
| Cross-platform (Windows) | Medium | pathlib everywhere. `encoding='utf-8', errors='replace'`. `.as_posix()` for string matching. ASCII-only. Suggestion file_path uses forward slashes. |
| Duplicate suggestions | Medium | LLM reads existing definitions before suggesting. Skips where adequate definitions exist. |
| Chicsession adapter join complexity | Medium | Isolate join logic in parsing.py. Do not let it leak into analysis layer. |
| Non-deterministic LLM testing | Medium | Golden-path integration tests with pre-canned suggestions JSON. Post-hoc suggestion linter. QA checklist for suggest.md. |

---

## 8. Testing Strategy

### Unit tests (fast, default markers)

1. **session_lib tests (test_session_lib.py):**
   - Verify extraction doesn't break mine_patterns.py functionality
   - Parse fixture JSONL -> verify Message/ParseResult fields
   - Score known correction messages -> verify score ranges
   - Discover session files in fixture directory

2. **Parser tests (test_audit_parser.py):**
   - Parse fixture JSONL -> verify ParsedInteraction fields
   - Parse fixture chicsession JSON -> verify agent roster, workflow state
   - Join chicsession entries to JSONL files -> verify correlation
   - Extract phase transitions from JSONL -> verify timeline
   - Handle missing JSONL for chicsession entry -> graceful skip
   - Handle chicsession without workflow_state -> phase_id=None

3. **Pre-filter tests (test_audit_prefilter.py):**
   - Strip agent spawn messages -> not in output
   - Strip system reminders -> not in output
   - Strip interrupt/notification messages -> not in output
   - Preserve genuine user messages -> in output
   - Handle empty input -> empty results

4. **Clustering tests (test_audit_clustering.py):**
   - BERTopic on fixture correction texts -> verify cluster assignments
   - Handle <5 inputs -> graceful skip (too few for clustering)
   - Verify cluster representatives are from input texts

5. **Analysis tests (test_audit_analyzer.py):**
   - Full pipeline: pre-filter -> classifier + optional regex -> union -> BERTopic -> CorrectionSignal
   - Verify CorrectionSignal has detection_source, category, cluster_id, llm_confidence
   - Verify LLM-flagged and regex-flagged items are unioned correctly
   - Map corrections to phases via transition timeline -> verify phase_id + confidence
   - Compute per-phase/per-agent/per-category/per-source stats -> verify arithmetic
   - Handle sessions with zero correction signals -> empty results

6. **Suggestion tests (test_audit_suggestions.py):**
   - Validate AuditSuggestion with valid file_path, artifact_type, YAML content
   - YAML snippets are valid YAML (parse them with yaml.safe_load)
   - Suggested file paths reference real workflow structure
   - Priority ordering matches output type priority

7. **Report tests (test_audit_reporter.py):**
   - Fixture findings + suggestions -> verify Markdown structure
   - Snapshot tests for format stability
   - Empty findings -> "no findings" report (no crash)
   - Sections ordered: phase markdown > advance checks > rules > hints

### Integration tests (marker: integration)

8. **End-to-end (test_audit_integration.py):**
   - Parse fixture sessions -> analyze -> suggest -> report
   - Verify report contains expected sections
   - Verify suggested YAML is parseable by ManifestLoader
   - Verify suggestion file_path values are valid

### Test fixtures (tests/fixtures/audit/)

- `session_with_corrections.jsonl` -- JSONL with known correction signals
- `session_clean.jsonl` -- JSONL with no corrections
- `session_multi_phase.jsonl` -- JSONL with phase transition markers
- `session_corrupted.jsonl` -- JSONL with malformed lines
- `chicsession_full.json` -- Chicsession with workflow_state and multiple agents
- `chicsession_no_workflow.json` -- Chicsession without workflow_state
- `sample_workflow.yaml` -- Minimal workflow manifest for cross-reference testing
- `sample_phase.md` -- Minimal phase markdown for gap detection testing

---

## 9. File Inventory

### New files to create

**Root repo files (used by template developers, AND mirrored into template for end users):**

| File | Purpose |
|------|---------|
| `scripts/__init__.py` | Empty, enables package imports |
| `scripts/audit/__init__.py` | Public API |
| `scripts/audit/session_lib.py` | Shared JSONL parsing, session discovery, regex scoring (used by audit pipeline AND mine_patterns) |
| `scripts/audit/types.py` | All frozen dataclasses |
| `scripts/audit/parsing.py` | JSONL + chicsession adapters |
| `scripts/audit/prefilter.py` | System boilerplate stripping (agent spawns, interrupts, reminders) |
| `scripts/audit/clustering.py` | BERTopic clustering on flagged items |
| `scripts/audit/analysis.py` | Pipeline orchestrator (pre-filter -> classifier + optional regex -> BERTopic) |
| `scripts/audit/suggestions.py` | AuditSuggestion validation (`validate_suggestions()`), serialization |
| `scripts/audit/report.py` | Markdown report formatter |
| `workflows/audit/audit.yaml` | Workflow manifest (multi-role) |
| `workflows/audit/classifier/identity.md` | Classifier role: scan messages, detect corrections |
| `workflows/audit/classifier/analyze.md` | Classifier analyze phase instructions |
| `workflows/audit/judge/identity.md` | Judge role: analyze corrections, generate suggestions |
| `workflows/audit/judge/suggest.md` | Suggest phase LLM guidance (examples, schema, anti-patterns) |
| `workflows/audit/critic/identity.md` | Critic role: validate suggestions (6 checks, 3 verdicts) |
| `workflows/audit/critic/suggest.md` | Critic phase instructions (runs after judge in suggest phase) |
| `workflows/audit/auditor/identity.md` | Auditor role: orchestrate, present to user, apply edits (includes cold-start handling) |
| `workflows/audit/auditor/parse.md` | Parse phase instructions |
| `workflows/audit/auditor/report.md` | Report phase instructions |
| `workflows/audit/auditor/apply.md` | Apply phase instructions (edit target files for approved suggestions) |

**Repo-only (NOT mirrored into template):**

| File | Purpose |
|------|---------|
| `tests/test_session_lib.py` | session_lib extraction tests |
| `tests/test_audit_parser.py` | Parser tests |
| `tests/test_audit_prefilter.py` | System boilerplate stripping tests |
| `tests/test_audit_clustering.py` | BERTopic clustering tests |
| `tests/test_audit_analyzer.py` | Full pipeline orchestration tests (classifier + optional regex) |
| `tests/test_audit_suggestions.py` | Suggestion + validation tests |
| `tests/test_audit_reporter.py` | Report tests |
| `tests/test_audit_integration.py` | End-to-end integration test |
| `tests/fixtures/audit/` | Fixture files (8 files listed above) |

### Existing files to modify

| File | Change |
|------|--------|
| `scripts/mine_patterns.py` | Import from `scripts.audit.session_lib` instead of defining shared functions locally |
| `copier.yml` | Include `scripts/audit/` and `workflows/audit/` in template output. Exclude `scripts/mine_patterns.py`, test fixtures. |
| `template/scripts/__init__.py` | Create empty file for package imports in generated projects |
| `template/scripts/audit/` | Mirror of root `scripts/audit/` for generated projects (Copier copies root -> template) |
| `template/workflows/audit/` | Mirror of root `workflows/audit/` for generated projects (Copier copies root -> template) |

---

## 10. Implementation Order

1. **Phase 1: Shared extraction** -- `session_lib.py` + `test_session_lib.py`. Verify mine_patterns.py still works after extraction. Regex stays in session_lib for mine_patterns.py.
2. **Phase 2: Types + Parser** -- `audit/types.py` + `audit/parsing.py` + `test_audit_parser.py` + fixture files
3. **Phase 3: Pre-filter** -- `audit/prefilter.py` + `test_audit_prefilter.py`. System boilerplate stripping.
4. **Phase 4: Clustering** -- `audit/clustering.py` + `test_audit_clustering.py`. BERTopic on flagged items.
5. **Phase 5: Analysis orchestration** -- `audit/analysis.py` + `test_audit_analyzer.py`. Wires pre-filter -> classifier agent (Haiku) + optional regex -> BERTopic.
6. **Phase 6: Suggestions utilities** -- `audit/suggestions.py` (validation, serialization) + `test_audit_suggestions.py`
7. **Phase 7: Report** -- `audit/report.py` + `test_audit_reporter.py`
8. **Phase 8: Workflow + Role Markdown** -- `workflows/audit/` manifest + ALL role directories (classifier, judge, critic, auditor). The `judge/suggest.md` guides suggestion generation. The `critic/suggest.md` guides suggestion validation (6 checks, 3 verdicts). The `auditor/apply.md` guides file edits.
9. **Phase 9: Integration** -- `test_audit_integration.py` + end-to-end verification
10. **Phase 10: Template integration** -- Mirror root `scripts/audit/` and `workflows/audit/` under `template/` and verify with `test_copier_generation.py`. Root files are the source of truth; template mirrors them for generated projects.

---

## 11. Deferred to APPENDIX.md (NOT in v1)

The following tools and features are explicitly deferred from the v1 audit workflow. They may be explored in future iterations and are documented in a separate APPENDIX.md:

- **Spotlight** -- interactive data exploration
- **Marimo** -- reactive notebook for audit results
- **DeepEval** -- LLM evaluation framework
- **Cleanlab** -- data quality / label noise detection
- **Active learning** -- human-in-the-loop label refinement
- **Timeline visualization** -- visual correction timeline
- **Drift detection** -- monitoring correction rates over time
- **GLiClass NLI** -- not used in v1. See APPENDIX.md for evaluation data.
