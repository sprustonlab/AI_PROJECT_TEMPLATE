# Analytics Implementation

## Files

- `analytics.py` - `capture(event, **properties)` async function, direct HTTP to PostHog
- `config.py` - `~/.claude/claudechic.yaml` management (user ID, opt-out flag)

## Adding New Events

1. Call `capture("event_name", prop1=value1, prop2=value2)` from app.py
2. Use `self.run_worker(capture(...))` for fire-and-forget from sync context
3. For shutdown events, use `await capture(...)` to ensure delivery

## Current Events

### App Lifecycle
- `app_installed` - first launch only, includes `claudechic_version`, `os`
- `app_started` - every launch, includes `claudechic_version`, `term_width`, `term_height`, `term_program`, `os`, `has_uv`, `has_conda`, `is_git_repo`, `resumed`
- `app_closed` - shutdown, includes `duration_seconds`, `term_width`, `term_height`

### Agent Lifecycle
- `agent_created` - new agent, includes `same_directory`, `model`
- `agent_closed` - agent closes, includes `message_count`, `duration_seconds`, `same_directory`

### User Actions
All include `agent_id` to link events to specific Claude sessions.

- `message_sent` - when user sends a message to Claude
- `command_used` - when user runs a slash command, includes `command` name
- `model_changed` - when user switches models, includes `from_model`, `to_model`
- `worktree_action` - when user runs worktree commands, includes `action` (create/finish/cleanup/discard)

### MCP Tools (Claude-initiated)
All include `agent_id`.

- `mcp_tool_used` - when Claude calls an MCP tool, includes `tool` (spawn_agent/spawn_worktree/ask_agent/tell_agent)

### Errors
- `error_occurred` - on errors, includes `error_type`, `context`, `status_code`, `agent_id`
  - `context`: where the error occurred (`initial_connect`, `response`, `connection_lost`, `reconnect_failed`)
  - `error_subtype`: for `CLIConnectionError`, a safe categorization (`cwd_not_found`, `not_ready`, `process_terminated`, `not_connected`, `start_failed`, `cli_not_found`, `unknown`)

## Design Decisions

- **No PostHog SDK** - direct HTTP keeps dependencies minimal
- **Context only on app_started** - other events are minimal (just `$session_id` + event-specific props)
- **Opt-out not opt-in** - check `get_analytics_enabled()` before sending
- **Silent failures** - analytics must never crash or slow the app

## Querying PostHog

The `POSTHOG_API_KEY` environment variable contains a personal API key for querying.

### HogQL (Recommended for Aggregations)

PostHog supports HogQL, a SQL-like query language. Much cleaner for aggregations:

```python
import os, httpx

key = os.environ['POSTHOG_API_KEY']

r = httpx.post(
    'https://us.i.posthog.com/api/projects/@current/query/',
    headers={'Authorization': f'Bearer {key}'},
    json={
        'query': {
            'kind': 'HogQLQuery',
            'query': 'SELECT event, count() as cnt FROM events GROUP BY event ORDER BY cnt DESC'
        }
    },
    timeout=30
)
for row in r.json()['results']:
    print(f'{row[0]}: {row[1]}')
```

Common HogQL queries:
```sql
-- Event counts
SELECT event, count() as cnt FROM events GROUP BY event ORDER BY cnt DESC

-- Unique users
SELECT count(DISTINCT distinct_id) as users FROM events

-- Terminal breakdown
SELECT properties.term_program as terminal, count() as cnt
FROM events WHERE event = 'app_started'
GROUP BY terminal ORDER BY cnt DESC

-- Commands used
SELECT properties.command as cmd, count() as cnt
FROM events WHERE event = 'command_used'
GROUP BY cmd ORDER BY cnt DESC

-- Events in last 24h
SELECT event, count() FROM events
WHERE timestamp > now() - INTERVAL 1 DAY
GROUP BY event

-- Session durations
SELECT avg(properties.duration_seconds) as avg_duration,
       max(properties.duration_seconds) as max_duration
FROM events WHERE event = 'app_closed'
```

### Events API (For Raw Event Data)

Use the events API when you need individual events, not aggregations:

```python
import os, httpx

key = os.environ['POSTHOG_API_KEY']

r = httpx.get(
    'https://us.i.posthog.com/api/projects/@current/events/',
    params={'limit': 100, 'event': 'app_started'},
    headers={'Authorization': f'Bearer {key}'},
    timeout=30
)
events = r.json().get('results', [])

for e in events:
    print(e['properties'].get('term_program'))
```

Filter by time range:
```python
from datetime import datetime, timedelta, timezone
after = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
params = {'limit': 100, 'after': after}
```

**Pagination warning:** The API can return duplicates. Always dedupe by event ID:
```python
seen_ids = set()
all_events = []
url = 'https://us.i.posthog.com/api/projects/@current/events/'
params = {'limit': 100}

while url:
    r = httpx.get(url, params=params, headers={'Authorization': f'Bearer {key}'}, timeout=30)
    data = r.json()
    for e in data.get('results', []):
        if e['id'] not in seen_ids:
            seen_ids.add(e['id'])
            all_events.append(e)
    url = data.get('next')
    params = {}  # next URL has params embedded
```

### Key Fields (Events API)
- `e['event']` - event name
- `e['distinct_id']` - user ID (UUID)
- `e['timestamp']` - ISO timestamp
- `e['properties']` - event-specific data plus `$session_id`
- `e['id']` - unique PostHog event ID (use for deduplication)

## Dashboard

A Marimo dashboard for visualizing analytics data lives at `dashboard.py`:

```bash
POSTHOG_API_KEY=... uv run marimo run dashboard.py
```

Charts included:
- New installs by engagement level (message count bins)
- Versions in use per day
- Daily active users
- DAU by terminal and OS
- Messages per user percentiles (p10/p50/p90)
- Recent active users table (last 6 hours)
- Errors table (last 24 hours)

## Testing

Add debug logging temporarily:
```python
# In analytics.py before the try block
import json
with open("/tmp/posthog_debug.log", "a") as f:
    f.write(json.dumps(payload, indent=2) + "\n---\n")
```

Then restart app via remote: `curl -s -X POST localhost:9999/exit`
