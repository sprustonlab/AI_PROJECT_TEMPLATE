# Guardrails

Role-based access control for Claude Code tool calls.

## Quick Start

1. Edit `rules.yaml` to define permission rules
2. Run `python3 .claude/guardrails/generate_hooks.py` to regenerate hooks
3. Hooks are auto-discovered by Claude Code via `.claude/settings.json`

## Files

| File | Purpose |
|------|---------|
| `rules.yaml` | Source of truth for permission rules |
| `rules.d/` | Directory for contributed rule sets |
| `generate_hooks.py` | Generates guardrail hook scripts from rules |
| `role_guard.py` | Runtime role-based permission checking |
| `hooks/` | Generated guardrail hook scripts (do not edit directly) |

## Adding Rules

Add a rule to `rules.d/<name>.yaml`:

```yaml
rules:
  - id: PROJ01
    name: deny-dangerous-ops
    trigger: PreToolUse/Bash
    enforcement: deny
    detect:
      type: regex_match
      pattern: 'dangerous_command'
    message: "[PROJ01] Explanation for the user"
```

Then regenerate: `python3 .claude/guardrails/generate_hooks.py`
