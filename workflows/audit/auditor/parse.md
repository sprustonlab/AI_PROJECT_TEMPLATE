# Parse Phase

Goal: Ask the user what to audit, then extract messages into the corrections database.

---

## Steps

1. Run `python scripts/audit/audit.py status` to check if a database exists and
   what has already been analyzed.
2. Run `python scripts/audit/audit.py list-sessions` to see all available
   chicsessions and their database status.
3. Present context to the user (see identity.md for first-audit vs subsequent
   wording). Ask what they want to audit with examples of natural language you
   understand.
4. Match the user's answer to chicsession names:
   - "all sessions" -> `extract --all`
   - "just the new ones" -> `extract --sessions` with names where `in_db: false`
   - "the tutorial workflow" -> `extract --sessions` with matching names
   - "this session", "current", "the one I'm in" -> use the active chicsession
     name (the workspace chicsession the audit workflow is running in). Detect
     this from the chicsession context and offer it as the default.
   - Specific names -> `extract --sessions NAME1,NAME2`

   When presenting options, mention the active chicsession by name as a
   convenient default: "You're currently in 'FeatureX'. Audit this session,
   or something else?"
5. Run `python scripts/audit/audit.py extract --sessions <names>` (or `--all`).
6. Report results to the user:
   > "Extracted N new messages from M sessions (P skipped as duplicates,
   > Q pre-filtered as boilerplate). Database now has T total messages."
7. Show cost estimate for the next phase:
   > "N new messages to classify. Estimated cost: ~$X (Haiku). Proceed?"

---

## Cold Start

If `list-sessions` returns an empty array and `status` shows `db_exists: false`
or `messages: 0`:
> "No sessions found. Run some workflows first, then come back to audit."

Do not proceed further.

---

## Advance Check

The phase advance check runs: `audit.py check has-messages`
This passes when the messages table is non-empty.
