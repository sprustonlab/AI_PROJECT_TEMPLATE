# Apply Phase

Goal: Edit target files to apply approved suggestions.

---

## Steps

1. Query the database for suggestions with `apply_status = 'applied'`.
2. For each approved suggestion:
   a. Read the target file using the Read tool.
   b. If the file does not exist: warn the user and skip. Do NOT create new
      files without user confirmation.
   c. For "modify" suggestions:
      - Find `current_content` in the file.
      - If not found: warn the user that the content has changed since the
        suggestion was generated. Ask whether to skip or attempt a manual edit.
      - Replace with `proposed_content` using the Edit tool.
   d. For "add" suggestions:
      - Find `insertion_point` in the file.
      - Insert `proposed_content` after the insertion point using the Edit tool.
   e. If the target file is YAML (rules.yaml, hints.yaml, workflow manifests):
      validate the result parses cleanly. If validation fails, revert and warn.
   f. Update the database:
      ```
      python scripts/audit/audit.py update-suggestion <id> --applied-at "<ISO timestamp>"
      ```
3. After all suggestions are processed, summarize:
   > "Applied N changes to M files. Please review the diffs."
4. If any suggestions were skipped due to errors, list them with reasons.

---

## Safety

- Always Read the target file before editing. Never edit blind.
- Never force-write a file. Use the Edit tool for surgical changes.
- If a YAML file fails validation after editing, revert the change immediately.
- Do not edit files outside the repository root.
- Use forward slashes in all file paths.

---

## Advance Check

Manual confirm: "Changes applied. Verify and confirm?"
