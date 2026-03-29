# Composable Role-Based Agent Guardrails

A YAML-driven framework for enforcing safety rules on Claude Code agents via PreToolUse hooks.

## Quick Start

1. **Create your rules** — copy and edit the example:
   ```bash
   cp .claude/guardrails/rules.yaml.example .claude/guardrails/rules.yaml
   # Edit rules.yaml with your project-specific rules
   ```

2. **Generate hooks** — this creates shell/Python hooks and wires them into `.claude/settings.json`:
   ```bash
   python3 .claude/guardrails/generate_hooks.py
   ```

3. **Done.** Claude Code will now enforce your rules on every tool call.

## Files

| File | Purpose |
|------|---------|
| `generate_hooks.py` | Reads `rules.yaml`, generates shell hooks in `hooks/`, updates `.claude/settings.json` |
| `role_guard.py` | Runtime role checking + ack-token mechanism for Write/Edit warns |
| `rules.yaml.example` | 23 synthetic test rules exercising every framework mechanism |
| `test_framework.py` | 58 integration tests (real subprocesses, no mocks) |
| `rules.yaml` | **Your project rules** (you create this) |

## Rule Anatomy

```yaml
catalog_version: "1.0"
ack_ttl_seconds: 120

rules:
  - id: R01                          # Unique ID
    name: no-git-stash               # Human-readable name
    trigger: PreToolUse/Bash         # When to check (Bash, Write, Edit, Glob, Read, MCP)
    enforcement: deny                # deny | warn | log
    detect:
      type: regex_match              # regex_match | regex_miss
      pattern: '\bgit\s+stash\b'    # What to look for
    message: "Use branches instead of git stash."
```

## Detection Types

- **`regex_match`** — fires when pattern matches (block dangerous commands)
- **`regex_miss`** — fires when pattern does NOT match (enforce required tokens)

## Enforcement Levels

- **`deny`** — hard block, cannot be bypassed
- **`warn`** — exit code 2, user can acknowledge with `# ack:RULE_ID` prefix
- **`log`** — silent logging to `hits.jsonl`, no block

## Role-Based Rules

Rules can target specific agent roles in multi-agent (team mode) setups:

```yaml
- id: R11
  name: coordinator-no-execute
  trigger: PreToolUse/Bash
  enforcement: deny
  scope: coordinator            # Only applies to Coordinator role
  detect:
    type: regex_match
    pattern: '\b(python3?|pytest|prism-)\b'
  message: "Coordinator must delegate execution to sub-agents."
```

Scope options:
- `universal` (default) — applies to all agents
- `coordinator` — only the Coordinator agent
- `subagent` — only sub-agents (Implementer, Researcher, etc.)
- `team_any` — any agent in team mode (Coordinator + sub-agents)
- Custom role name — only agents spawned with that `type`

## Advanced Features

### Exclude Patterns
Skip the rule when a secondary pattern matches:
```yaml
exclude_if_matches: '\bsafe_command\b'
```

### Context Stripping
By default, content inside `python -c "..."` and heredocs is excluded from pattern matching, preventing false positives.

### Ack Token Flow (Write/Edit warns)
When a write rule fires as `warn`, the agent can acknowledge via:
```bash
python3 .claude/guardrails/role_guard.py ack RULE_ID path/to/file
```
This creates a time-limited token (default 120s). The next write attempt to that path will pass.

### Field Extraction (MCP triggers)
For MCP tool triggers, extract a specific field from the JSON input:
```yaml
trigger: mcp__tool__name
detect:
  type: regex_match
  field: color           # Extract this field from tool args
  pattern: '^red$'
```

### Multi-Pattern
Match any of several patterns:
```yaml
detect:
  type: regex_match
  patterns:
    - '\balpha_bad\b'
    - '\bbeta_bad\b'
```

## Testing

```bash
# Run all 58 framework tests
pytest .claude/guardrails/test_framework.py -v

# Tests use rules.yaml.example (synthetic rules), no project rules.yaml needed
```

## Runtime Artifacts

These are generated at runtime and excluded via `.gitignore`:
- `acks/` — time-limited ack tokens
- `sessions/` — team-mode session markers
- `hits.jsonl` — audit log of all rule matches

## Requirements

- Python 3.9+
- PyYAML (`pip install pyyaml`)
- claudechic with guardrail env var support (`CLAUDE_AGENT_NAME`, `CLAUDECHIC_APP_PID`, `CLAUDE_AGENT_ROLE`)
