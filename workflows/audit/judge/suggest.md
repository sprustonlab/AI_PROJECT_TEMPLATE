# Suggest Phase

Goal: Generate machine-applicable suggestions from aggregated correction patterns.

---

## Input Format

You receive aggregated patterns from `audit.py aggregate`. Each pattern:

```json
{
  "pattern_id": "<category>:<phase_id>",
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
    }
  ],
  "all_message_ids": [42, 67, 89, 91, 103, 115, 128]
}
```

Key fields:
- `pattern_id` -- unique identifier for the pattern (category + phase)
- `correction_count` -- total corrections in this pattern
- `session_count` -- distinct sessions where this pattern appears
- `top_examples` -- up to 3 highest-confidence examples with 3-message context
- `all_message_ids` -- every correction ID supporting this pattern (use for evidence linking)

**phase_confidence warning:** Each correction has a `phase_confidence` field:
`"inferred"` (from JSONL transition markers), `"snapshot"` (from chicsession
state), or `"unknown"` (no phase context available). When generating
phase-scoped suggestions (changes to a specific phase's markdown file), only
count corrections with a known phase -- those with `phase_confidence` of
`"inferred"` or `"snapshot"`. Corrections with `phase_confidence: "unknown"`
have no reliable phase association and must NOT be used to justify phase-specific
changes. They may still count toward global suggestions (rules, hints) that are
not phase-scoped.

---

## Output Schema

Each suggestion is a JSON object for `audit.py store-suggestions`:

```json
{
  "artifact_type": "phase-markdown",
  "file_path": "workflows/project-team/implementor/implementation.md",
  "suggestion_type": "modify",
  "current_content": "## Steps\n\n1. Read the task description",
  "proposed_content": "## Steps\n\n1. Read the task description\n2. Always use pathlib.Path for file paths -- never os.path or string concatenation",
  "insertion_point": null,
  "rationale": "7 corrections across 3 sessions show users repeatedly correcting agents about path handling. Adding an explicit instruction prevents the recurring mistake.",
  "evidence_count": 7,
  "priority": 2,
  "evidence_message_ids": [42, 67, 89, 91, 103, 115, 128]
}
```

Field reference:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `artifact_type` | string | yes | `phase-markdown`, `advance-check`, `rule`, `hint` |
| `file_path` | string | yes | Relative path with forward slashes |
| `suggestion_type` | string | yes | `add` or `modify` |
| `current_content` | string | modify only | Exact text to find and replace |
| `proposed_content` | string | yes | Replacement text or new content |
| `insertion_point` | string | add only | Text marker after which to insert |
| `rationale` | string | yes | Why this change is needed, citing evidence |
| `evidence_count` | integer | yes | Number of corrections supporting this |
| `priority` | integer | yes | 1=critical, 2=high, 3=medium, 4=low |
| `evidence_message_ids` | array | yes | IDs from pattern's `all_message_ids` |

---

## Worked Example

**Input pattern:**

```json
{
  "pattern_id": "factual_correction:implementation",
  "category": "factual_correction",
  "phase_id": "implementation",
  "correction_count": 7,
  "session_count": 3,
  "agent_names": ["implementor"],
  "top_examples": [
    {
      "message_id": 42,
      "user_text": "No, that's wrong -- use pathlib not os.path",
      "context_before": "I'll update the imports to use os.path.join for the file paths...",
      "context_after": "You're right, switching to pathlib.Path...",
      "confidence": "high",
      "session_id": "abc-123"
    },
    {
      "message_id": 67,
      "user_text": "I said to use pathlib, not string concatenation",
      "context_before": "Here's the updated path: root + '/src/main.py'...",
      "context_after": "Apologies, using Path() now...",
      "confidence": "high",
      "session_id": "def-456"
    }
  ],
  "all_message_ids": [42, 67, 89, 91, 103, 115, 128]
}
```

**Analysis:**

1. Read context_before: agent used os.path and string concatenation for paths.
2. Read user_text: user corrected to pathlib in multiple sessions.
3. Read context_after: agent acknowledged and switched, confirming the correction.
4. Pattern: recurring factual correction about path handling, 7 times across 3 sessions.
5. Category `factual_correction` maps to phase-markdown and/or rules.

**Step: Read the target file.**

Before writing the suggestion, use the Read tool to examine the current content
of `workflows/project-team/implementor/implementation.md`. Find the section
where path handling guidance should go.

**Output suggestion:**

```json
{
  "artifact_type": "phase-markdown",
  "file_path": "workflows/project-team/implementor/implementation.md",
  "suggestion_type": "modify",
  "current_content": "## Code Standards\n\nFollow the project's coding conventions.",
  "proposed_content": "## Code Standards\n\nFollow the project's coding conventions.\n\nAlways use pathlib.Path for all file path operations. Never use os.path\nfunctions or string concatenation with '/'. Use .as_posix() when paths\nmust appear in regex or string matching contexts.",
  "insertion_point": null,
  "rationale": "7 corrections across 3 sessions show agents repeatedly using os.path or string concatenation for file paths. Users consistently redirect to pathlib. Adding an explicit instruction prevents this recurring mistake.",
  "evidence_count": 7,
  "priority": 2,
  "evidence_message_ids": [42, 67, 89, 91, 103, 115, 128]
}
```

This suggestion is machine-applicable: the auditor can find `current_content`
in the file and replace it with `proposed_content` using the Edit tool.

---

## Tone Instructions

Suggestions become content that other LLM agents read. Write in imperative
voice matching the style of existing phase markdown files:

- GOOD: "Always read error output before retrying a failed command."
- GOOD: "Use pathlib.Path for all file path operations."
- GOOD: "Never force-push to any branch."
- BAD: "Consider reading error output before retrying."
- BAD: "It might be helpful to use pathlib."
- BAD: "You should try to avoid force-pushing."

Be direct. Be specific. Match the tone of the file you are modifying.

---

## Anti-Patterns

Avoid these common mistakes:

1. **Catch-22 rules** -- Rules that block their own prerequisites. Example: a
   rule that blocks all Bash commands in a phase where the agent needs Bash to
   complete its work. Before proposing a rule, verify the agent can still do
   its job with the rule active.

2. **Overly broad rules** -- Rules that fire on legitimate operations. Example:
   a rule blocking all Write operations when only writes to a specific directory
   should be blocked. Use `detect.pattern` to scope rules narrowly.

3. **Duplicate hints** -- Hints that repeat what an existing hint already says.
   Read the current hints in the manifest before proposing new ones.

4. **Phantom file paths** -- Suggesting changes to files that do not exist.
   Always Read the target file before proposing a modification. If the file
   does not exist, either propose creating it (with `suggestion_type: "add"`)
   or target a different file.

5. **Vague phase-markdown additions** -- Adding content like "Be careful with
   paths" instead of specific instructions. Every addition must be concrete
   enough that an agent can follow it without interpretation.

---

## Artifact Access

Before generating any suggestion, you MUST Read the target file to:
- Verify it exists
- Find the exact `current_content` string for modify suggestions
- Find the right `insertion_point` for add suggestions
- Check that your proposed content does not duplicate existing content
- Match the tone and formatting of the existing file

Do not guess file contents. Do not assume file structure. Read first.

---

## YAML Reference

When generating rule, advance-check, or hint suggestions, use these valid values:

**Rule triggers:**
- `PreToolUse/Bash` -- before shell commands
- `PreToolUse/Write` -- before file writes
- `PreToolUse/Edit` -- before file edits
- `PreToolUse/Read` -- before file reads

**Rule enforcement:**
- `deny` -- block the action entirely
- `warn` -- show warning but allow

**Hint lifecycle:**
- `show-once` -- show one time only
- `show-every-session` -- show at the start of every session
- `show-until-resolved` -- show until a condition is met
- `cooldown-period` -- show periodically

**Advance check types:**
- `file-exists-check` -- verify a file exists
- `file-content-check` -- verify file contains expected content
- `command-output-check` -- run a command and check output
- `manual-confirm` -- ask user for confirmation

---

## 3-Message Context Usage

Each top example in a pattern includes:

- `context_before` -- what the agent said/did before the user's correction
- `user_text` -- the user's correction
- `context_after` -- how the agent responded

Use this context to:
1. Identify the root cause (what did the agent do wrong in context_before?)
2. Understand the correction (what does the user want in user_text?)
3. Assess severity (did the agent fix it in context_after, or repeat the mistake?)

If `context_after` shows the agent immediately fixed the issue: the suggestion
is still valid but lower priority (the mistake still happened, it just got
corrected quickly).

If `context_after` shows the agent repeated the same mistake: higher priority.
The agent did not learn from the correction within the session.

---

## Process

1. Read each aggregated pattern.
2. Check evidence thresholds (2+ for markdown/hints, 3+ for rules/checks).
3. Use the category-to-fix mapping to determine which artifact types apply.
4. Read the target files using the Read tool.
5. Generate one or more suggestions per pattern.
6. Write all suggestions as a JSON array. The auditor will store them:
   ```
   echo '<your_json_array>' | python scripts/audit/audit.py store-suggestions
   ```
7. Report: "Generated N suggestions from M patterns."
