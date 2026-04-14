# Suggest Phase -- Critic Validation

Goal: Validate every suggestion from the judge against 6 quality criteria.

---

## Input

You receive suggestions from the database. Each suggestion has:

- `id` -- database ID
- `artifact_type` -- phase-markdown, advance-check, rule, or hint
- `file_path` -- target file (relative path)
- `suggestion_type` -- add or modify
- `current_content` -- text to replace (for modify)
- `proposed_content` -- new content
- `insertion_point` -- where to insert (for add)
- `rationale` -- why this change is needed
- `evidence_count` -- number of corrections supporting this
- `priority` -- 1=critical, 2=high, 3=medium, 4=low

---

## Validation Criteria

Apply each criterion in order. If any criterion fails, the overall verdict
depends on severity (see Verdict Rules below).

### 1. Specificity

Is the suggestion concrete enough to implement?

- PASS: "Always use pathlib.Path for file path operations."
- FAIL: "Be more careful with paths."
- FAIL: "Improve error handling."

Reject suggestions that are generic advice rather than specific instructions.

### 2. Actionability

Can the `proposed_content` actually be inserted into or replace content in the
target file?

- PASS: proposed_content is valid markdown/YAML for the target file type.
- FAIL: proposed_content references undefined variables or nonexistent phases.
- FAIL: proposed_content is a description of what to do, not actual content.

### 3. Evidence Grounding

Do the cited corrections actually demonstrate the problem the suggestion claims
to fix? Read the rationale and check that the evidence count and category match.

- PASS: rationale explains how the corrections led to this suggestion.
- FAIL: rationale is generic and does not reference the actual corrections.
- FAIL: evidence count is inflated (claims 7 corrections but the pattern only
  has 3 relevant ones).

### 4. Proportionality

Is the evidence sufficient for the artifact type?

| Artifact Type | Minimum Evidence |
|--------------|-----------------|
| Phase markdown | 2+ corrections |
| Hints | 2+ corrections |
| Advance checks | 3+ corrections |
| Rules | 3+ corrections |

- PASS: evidence_count meets or exceeds the threshold.
- FAIL: 1 correction producing a deny rule.

### 5. Conflict Detection

Would this suggestion conflict with existing workflow artifacts?

- Read the target file and any related manifest files.
- Check for contradictions with existing rules, hints, or phase instructions.
- Check for duplicates of existing content.

- PASS: no conflicts found.
- FAIL: suggestion adds a rule that contradicts an existing rule.
- FAIL: suggestion duplicates an existing hint.

### 6. Feasibility

Can the agent actually follow this instruction without being blocked?

- PASS: the instruction does not prevent the agent from doing its core work.
- FAIL: a deny rule blocks Bash in a phase where the agent needs Bash.
- FAIL: instructions require tools or capabilities the agent does not have.

---

## Verdict Rules

- All 6 pass -> **APPROVE**
- 1-2 minor issues (fixable) -> **FLAG** with revised proposed_content
- Any critical failure (vague, unsupported, contradictory, catch-22) -> **REJECT**

When FLAGging, provide a revised version of the suggestion that addresses the
issues. The revised version is what gets presented to the user alongside the
original.

---

## 3-Message Context Assessment

Use the correction context to validate evidence grounding:

- If `context_after` shows the agent immediately fixed the issue: the suggestion
  is still valid but consider lowering priority. The mistake happened but was
  self-corrected.
- If `context_after` shows the agent repeated the same mistake: the suggestion
  is higher priority. The agent did not learn within the session.
- If `context_before` shows the agent was following conflicting existing rules:
  flag for conflict detection. The fix may need to address the conflicting rule
  rather than add a new one.

---

## Process

1. Read each suggestion from the auditor.
2. Read the target file with the Read tool to check for conflicts and
   duplicates (criterion 5).
3. Apply all 6 criteria.
4. Assign verdict and reasoning.
5. Update the database:
   ```
   python scripts/audit/audit.py update-suggestion <id> --critic-verdict APPROVE --critic-reasoning "Passes all criteria. Well-evidenced with 7 corrections across 3 sessions."
   ```
   ```
   python scripts/audit/audit.py update-suggestion <id> --critic-verdict FLAG --critic-reasoning "Good evidence but proposed content is too broad. Revised to scope narrowly."
   ```
   ```
   python scripts/audit/audit.py update-suggestion <id> --critic-verdict REJECT --critic-reasoning "Only 1 correction. Below threshold for a deny rule."
   ```
6. Report summary: "Reviewed N suggestions. Approved A, flagged F, rejected R."
