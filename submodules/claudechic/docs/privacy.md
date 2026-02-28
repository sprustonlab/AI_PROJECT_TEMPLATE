# Privacy

Claude Chic collects anonymous usage analytics to help us improve the product during early development.

## What We Track

We use [PostHog](https://posthog.com) to collect:

- **Session events**: app start, app close, session duration
- **Feature usage**: commands used, agents created/closed, model changes, worktree actions
- **Environment context**: OS, terminal program, terminal size, claudechic version
- **Error types** (not content): helps us identify and fix bugs

## What We Don't Track

- **Your conversations** - all message content goes directly to Anthropic
- **File contents** - we never see what you're working on
- **Personal information** - analytics IDs are random UUIDs

## Transparency

Claude Chic is open source. You can inspect exactly what we track here:

[`claudechic/analytics.py`](https://github.com/mrocklin/claudechic/blob/main/claudechic/analytics.py)

## Opt Out

### Via command

```
/analytics opt-out
```

### Via config file

Edit `~/.claude/.claudechic.yaml`:

```yaml
analytics:
  enabled: false
```

You can opt back in anytime with `/analytics opt-in` or by setting `enabled: true`.
