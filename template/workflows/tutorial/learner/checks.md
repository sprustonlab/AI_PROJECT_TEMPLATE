# Checks Phase

Welcome! In this first phase you'll learn about phase transitions.

Phase transitions are gated by advance_checks (AND semantics):
1. `file-exists-check` — `tutorial_checks_done.txt` must exist
2. `manual-confirm` — User must approve in TUI

Try calling `advance_phase` WITHOUT creating the file first — you'll see the check fail.
Then create the file and try again — the file check passes, then manual confirm prompts the user.

To advance: create file + approve manual confirm.
