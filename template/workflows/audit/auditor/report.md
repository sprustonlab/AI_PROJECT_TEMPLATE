# Report Phase

Goal: Present suggestions to the user and record their decisions.

---

## Steps

1. Query the database for suggestions with `critic_verdict` of APPROVE or FLAG.
   Run `python scripts/audit/audit.py corrections` if needed for context.
2. Present each suggestion to the user conversationally, grouped by artifact
   type in this order:
   - Phase markdown changes (highest impact)
   - Advance check additions
   - Rule additions/modifications
   - Hint additions (lowest impact)
3. For each suggestion, show:
   - Target file path
   - Rationale (why this change is needed)
   - Proposed change (what will be added or modified)
   - Evidence count (how many corrections support this)
   - Critic verdict and reasoning
   - For FLAG verdicts: show the critic's revised version alongside the original
4. Ask the user for each suggestion: "Apply this suggestion? (yes/no)"
5. Record decisions:
   ```
   python scripts/audit/audit.py update-suggestion <id> --apply-status applied
   python scripts/audit/audit.py update-suggestion <id> --apply-status skipped
   ```
6. After all suggestions are reviewed, summarize:
   > "N approved for application, M skipped. Ready to apply?"

---

## Presentation Style

- Be concise. Show the essential information, not every database field.
- For "modify" suggestions: show a before/after diff of the relevant section.
- For "add" suggestions: show where the content will be inserted and what it
  looks like.
- Group related suggestions (e.g., multiple changes to the same file).
- If a suggestion was FLAGged by the critic, explain the concern and present
  the revised version.

---

## Advance Check

Two checks must pass:
1. `audit.py check all-decided` -- every suggestion has an apply_status
2. Manual confirm -- "All suggestions reviewed. Ready to apply approved changes?"
