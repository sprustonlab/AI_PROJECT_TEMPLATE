# Session Compaction

Claude Code sessions accumulate context over time as tool calls build up. The `/compactish` command lets you reclaim context by removing old, large tool uses from your session.

## Quick Start

```
/compactish        # Compact and reconnect
/compactish -n     # Preview what would be removed (dry run)
/compactish -a     # Aggressive mode (lower thresholds)
```

## How It Works

The command removes entire tool_use/tool_result pairs that are **both old AND large**:

- **Small results** (<1KB) are kept regardless of age
- **Small inputs** (<2KB) are kept regardless of age
- **Recent items** (last 5 per tool type) are kept regardless of size

This preserves your recent work and small utility calls while removing large file reads and outputs from earlier in the session.

## Flags

| Flag | Description |
|------|-------------|
| `-n`, `--dry` | Preview mode - shows what would be removed without making changes |
| `-a`, `--aggressive` | Lower size thresholds (500B results, 1KB inputs) |
| `--no-reconnect` | Don't reconnect after compaction |

## Output

After compaction, a summary table shows the before/after breakdown:

```
## Session Compacted

| Category | Before | After |
|----------|-------:|------:|
| Tool Results | 72,630 (61%) | 16,843 (37%) |
| Tool Inputs | 35,242 (29%) | 18,186 (40%) |
| Assistant Text | 6,376 (5%) | 6,376 (14%) |
| User Text | 3,770 (3%) | 3,770 (8%) |
| **Total** | **118,018** | **45,175** |
```

## Reconnection

By default, `/compactish` reconnects the agent after compaction so Claude immediately sees the reduced context. The session file is modified in-place, so a reconnect is needed to reload it.

A backup is created at `session.jsonl.bak` before modification.

## When to Use

- When you're hitting context limits
- After a long session with many file reads
- Before starting a new phase of work where old context isn't needed

## Comparison to Built-in Compaction

Claude Code has two built-in compaction mechanisms:

### Microcompaction

Triggers automatically at ~80% context usage. Keeps the last ~10 tool results and truncates older ones. This is **runtime-only** - the session file on disk is unchanged, so resuming the session later reloads the full history.

### Autocompaction (`/compact`)

Creates a summary of the conversation using Claude, then prepends it to the session. The original messages remain in the file but Claude reads from the summary forward. This preserves searchable history but doesn't reduce file size.

### How `/compactish` Differs

| Feature | Microcompact | /compact | /compactish |
|---------|--------------|----------|-------------|
| Trigger | ~80% context | Manual | Manual |
| Strategy | Truncate content | Summarize | Remove entirely |
| Persistence | Runtime only | Adds to file | Modifies file |
| File size | Unchanged | Grows | Shrinks |
| Reversible | Yes (reload) | Yes (messages remain) | Backup only |

The `/compactish` approach is more aggressive - it permanently removes tool uses from the session file. This is useful when you want a clean slate without losing your session identity.

---

## Internals: Session File Structure

!!! info "For the Curious"
    This section explains how Claude Code stores sessions and how `/compactish` manipulates them.

### File Location

Sessions are stored as JSONL files in `~/.claude/projects/`:

```
~/.claude/projects/-Users-username-myproject/
├── a1b2c3d4-e5f6-7890-abcd-ef1234567890.jsonl
├── agent-abc123.jsonl  # Sub-agent sessions
└── *.jsonl.bak         # Backups from compaction
```

The project path uses dashes instead of slashes (e.g., `/Users/foo/bar` → `-Users-foo-bar`).

### Message Types

Each line in the JSONL file is a message with a `type` field:

```json
{"type": "user", "message": {"role": "user", "content": [...]}, "uuid": "..."}
{"type": "assistant", "message": {"role": "assistant", "content": [...]}, "uuid": "..."}
{"type": "system", "message": {"content": "..."}}
{"type": "summary", "isCompactSummary": true, "leafUuid": "..."}
```

### Tool Use Structure

Tool calls are stored as content blocks within messages:

**Tool Use** (in assistant messages):
```json
{
  "type": "assistant",
  "message": {
    "content": [
      {"type": "text", "text": "Let me read that file..."},
      {"type": "tool_use", "id": "toolu_abc123", "name": "Read", "input": {"file_path": "/foo/bar.py"}}
    ]
  }
}
```

**Tool Result** (in user messages):
```json
{
  "type": "user",
  "message": {
    "content": [
      {"type": "tool_result", "tool_use_id": "toolu_abc123", "content": "file contents here..."}
    ]
  },
  "toolUseResult": "file contents here..."  // Duplicate for rendering
}
```

Note: The `toolUseResult` field duplicates the content - this means ~60% of session file size is redundant data.

### What `/compactish` Does

1. **Loads** all messages from the session JSONL
2. **Identifies** old, large tool_use inputs and tool_result outputs
3. **Shrinks** inputs to a minimal placeholder: `{"_compacted": true}`
4. **Shrinks** outputs to tool-specific minimal strings (e.g., "No matches found" for Grep)
5. **Preserves** all message envelopes to maintain the UUID chain
6. **Writes** the compacted messages back to the file
7. **Reconnects** the agent so Claude loads the new file

!!! info "Tool-Specific Output Formats"
    Claude Code's renderer expects specific output formats for each tool. We replace large outputs with minimal strings that won't crash the renderer:

    - **Grep**: "No matches found" (avoids the `filenames.map()` crash)
    - **Read**: "[file content compacted]"
    - **Bash**: "[output compacted]"
    - Other tools: "[compacted]"

### Token Estimation

We estimate tokens at ~4 characters per token. This is rough but sufficient for comparing before/after sizes. The breakdown categories are:

- **Tool Results**: Content returned from tool calls (usually the largest)
- **Tool Inputs**: Arguments passed to tools (file paths, commands, etc.)
- **Assistant Text**: Claude's prose responses
- **User Text**: Your messages

### Inspecting Sessions

Useful commands for exploring session files:

```bash
# Find your project's sessions directory
ls ~/.claude/projects/

# Check session file sizes
wc -c ~/.claude/projects/-path-to-project/*.jsonl

# See last API usage stats
tail -1 session.jsonl | python3 -c "
import json, sys
d = json.load(sys.stdin)
u = d.get('message', {}).get('usage', {})
print(f'input={u.get(\"input_tokens\", 0):,}')
print(f'cache_read={u.get(\"cache_read_input_tokens\", 0):,}')
"
```
