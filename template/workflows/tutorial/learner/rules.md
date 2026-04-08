# Rules Phase

The guidance system uses a 2x2 design to shape agent behavior:

|                    | Negative (prevent bad)      | Positive (encourage good)       |
|--------------------|-----------------------------|---------------------------------|
| **MD instructive** | CLAUDE.md says "never X"    | CLAUDE.md says "always do Y"    |
| **Python deterministic** | Rules block/warn/log on X | Injections modify tool input    |

MD instructions are soft -- the agent can ignore or forget them.
Rules and injections are deterministic -- they fire every time, no exceptions.

This phase focuses on the **negative deterministic** quadrant: rules that block or flag bad actions.

## Enforcement Levels

There are three enforcement levels, from strictest to silent:

1. **deny** -- Blocks the action completely. The user must approve it via the TUI.
   Try: ask the agent to run `rm -rf /tmp/test`

2. **warn** -- Blocks the action, but the agent can acknowledge and proceed via `acknowledge_warning` MCP.
   Try: ask the agent to run `sudo echo hi`

3. **log** -- Silent. The action proceeds, but a record is written to `.claude/hits.jsonl`.
   Try: ask the agent to run `git status`, then check the log file.

Rules are defined in YAML and can be scoped globally or to specific workflow phases.

To advance: create `tutorial_rules_done.txt` then call `advance_phase`.
