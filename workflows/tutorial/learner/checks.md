# Checks Phase

Welcome! In this first phase you'll learn about phase transitions.

Phase transitions are gated by advance_checks. All checks must pass (AND semantics) before you can move to the next phase.

There are four types of advance checks:
1. `file-exists-check` -- verifies a file exists at a given path
2. `file-content-check` -- verifies file content matches a regex pattern
3. `command-output-check` -- verifies a command's stdout matches a regex pattern
4. `manual-confirm` -- prompts the user to approve in the TUI

This phase uses two of them:
- `file-exists-check` for `tutorial_checks_done.txt`
- `manual-confirm` asking if you're ready to proceed

Try calling `advance_phase` WITHOUT creating the file first -- you'll see the check fail.
Then create the file and try again -- the file check passes, then manual confirm prompts the user.

To advance: create file + approve manual confirm.
