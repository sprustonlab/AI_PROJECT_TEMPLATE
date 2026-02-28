# Remote Testing Guide

This document explains how to run live tests against claudechic using the remote control HTTP API.

## Setup

Start claudechic with the auto-restart wrapper:

```bash
./scripts/claudechic-remote 9999
```

This runs claudechic with `--remote-port 9999` and auto-restarts when the app exits.

Ask the user if they would like to do this so that they can follow along, but
offer to do it yourself too in case they don't want to.

## API Endpoints

All endpoints are on `http://localhost:9999`.

### GET /status
Get current app and agent state.

```bash
curl -s localhost:9999/status
```

Response:
```json
{
  "agents": [{"name": "...", "id": "...", "status": "idle", "cwd": "...", "active": true}],
  "active_agent": "agent-name"
}
```

### POST /send
Send a message to the active agent.

```bash
curl -s -X POST localhost:9999/send -H "Content-Type: application/json" -d '{"text": "Hello"}'
```

Response:
```json
{"status": "sent", "text": "Hello"}
```

### GET /wait_idle
Wait until the active agent finishes responding.

```bash
curl -s "localhost:9999/wait_idle?timeout=30"
```

Response:
```json
{"status": "idle"}
```

### GET /screen_text
Get the current screen content as plain text, preserving 2D layout.

```bash
curl -s localhost:9999/screen_text | python3 -c "import sys,json; print(json.load(sys.stdin)['text'])"
```

Query params:
- `compact` - If `false`, include blank lines. Default: `true` (removes blank lines to save tokens).

```bash
# Full layout with all blank lines
curl -s "localhost:9999/screen_text?compact=false"
```

Prefer this to getting a screenshot at first. It's easier to iterate with plain text and preserves column alignment (sidebar, main content, footer).

### GET /screenshot
Save a screenshot. Returns the file path.

```bash
# SVG (default)
curl -s "localhost:9999/screenshot?path=/tmp/shot.svg"

# PNG (uses macOS qlmanage for conversion)
curl -s "localhost:9999/screenshot?format=png&path=/tmp/shot.png"
```

Response:
```json
{"path": "/tmp/shot.png", "format": "png"}
```

To view the PNG:
```bash
# Use the Read tool on the PNG path
```

### POST /exit
Exit the app cleanly. The wrapper script will auto-restart it.

```bash
curl -s -X POST localhost:9999/exit
```

Response:
```json
{"status": "exiting"}
```

Wait ~2 seconds for restart, then verify:
```bash
sleep 2 && curl -s localhost:9999/status
```

Use this when you want to restart the application.  Don't restart the `./scripts/claudechic-remote 9999` server, just send an exit signal and wait a moment.

### POST /key
Simulate keyboard key presses.

```bash
# Press escape
curl -s -X POST localhost:9999/key -H "Content-Type: application/json" -d '{"keys": ["escape"]}'

# Navigate with arrow keys
curl -s -X POST localhost:9999/key -d '{"keys": ["down", "down", "enter"]}'

# Press Ctrl+C
curl -s -X POST localhost:9999/key -d '{"keys": ["ctrl+c"]}'
```

Response:
```json
{"status": "pressed", "keys": ["escape"]}
```

Supported keys:
- Single characters: `a`, `1`, etc.
- Named keys: `escape`, `enter`, `tab`, `space`, `backspace`, `delete`
- Arrow keys: `up`, `down`, `left`, `right`
- Function keys: `f1` through `f12`
- Modifiers: `ctrl+c`, `shift+tab`, `ctrl+n`
- Special: `wait:500` to pause 500ms between keys

## Common Test Patterns

### Send message and check response

```bash
# Send
curl -s -X POST localhost:9999/send -d '{"text": "What is 2+2?"}'

# Wait for completion
curl -s "localhost:9999/wait_idle?timeout=30"

# Get text output
curl -s localhost:9999/screen_text | python3 -c "import sys,json; print(json.load(sys.stdin)['text'])"
```

### Visual verification

```bash
# Take PNG screenshot
curl -s "localhost:9999/screenshot?format=png&path=/tmp/test.png"

# Then use Read tool on /tmp/test.png to view it
```

### Test slash commands

```bash
# Test /agent command
curl -s -X POST localhost:9999/send -d '{"text": "/agent"}'
curl -s localhost:9999/wait_idle
curl -s localhost:9999/screen_text
```

### Restart with fresh state

```bash
curl -s -X POST localhost:9999/exit
sleep 2
curl -s localhost:9999/status  # Verify new agent ID
```

## Spawning New Instances

On macOS, you can spawn new claudechic instances in separate Terminal windows using osascript:

```bash
# Spawn a new instance on port 9998 (use absolute path to script)
osascript -e "tell application \"Terminal\" to do script \"$(pwd)/scripts/claudechic-remote 9998\""

# Wait for startup, then verify
sleep 4 && curl -s localhost:9998/status
```

**Important**: Use the absolute path to the script. Running `uv run claudechic` directly will use whatever directory the terminal opens in (usually home), which may not have the latest code.

## Tips

1. **Always wait for idle** after sending messages before checking output
2. **Text extraction** includes UI elements (title, sidebar, footer) - filter as needed
3. **PNG screenshots** may have font rendering issues on some systems; SVG is always accurate
4. **Agent IDs change** on restart - use this to verify restart worked
5. **Timeout on wait_idle** defaults to 30s; increase for long operations
6. **Spawning instances**: Use absolute paths to avoid running stale code from wrong directories
