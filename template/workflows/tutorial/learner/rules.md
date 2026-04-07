# Rules Phase

In this phase you'll experience all three enforcement levels:
1. **deny** (`rm -rf /path`) — Blocks the command. User must approve via TUI.
2. **warn** (`sudo ...`) — Blocks the command. Agent acknowledges via `acknowledge_warning` MCP.
3. **log** (`git ...`) — Silent. Check `.claude/hits.jsonl` for the audit record.

To advance: create `tutorial_rules_done.txt` then call `advance_phase`.
