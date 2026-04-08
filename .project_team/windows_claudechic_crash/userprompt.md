# User Prompt -- Windows Claudechic Crash Investigation

## Problem

Claudechic (the Textual TUI for Claude Code) crashes on Windows with a clean exit (no error log, no crash file). The TUI disappears and the user gets their PowerShell prompt back. This happens:

1. After completing a tutorial workflow (graduation phase finishes, agent goes idle, then TUI exits)
2. Sometimes with `StackOverflowException` during `activate.ps1` (likely `pixi shell-hook` related)
3. With `CLIConnectionError: Cannot write to terminated process (exit code: 0)` when queued messages are drained after the Claude Code subprocess exits

## Evidence

### Known working version
The `abast/mesotools` repo on `arco_develop` branch has claudechic at commit `c5d5966` ("revert to stable version") which works on Windows. This is essentially `abast/claudechic upstream/main` -- the base version without sprustonlab additions.

### Known crashing version
`sprustonlab/claudechic main` (commit `99f91c4`) which includes ~1100 lines of changes over the stable version in `agent.py` (~595 lines diff) and `app.py` (~567 lines diff).

### What was added between stable and crashing
Files added:
- `chicsession_cmd.py`, `chicsessions.py`, `screens/chicsession.py` (chicsession feature)
- `cluster.py` (cluster tools)
- `widgets/modals/diagnostics.py`

Major changes in `agent.py`:
- `ResponseState` state machine replacing simple boolean flags (`_thinking`, `_interrupted`)
- `ResponseContext` dataclass grouping per-response state
- `_pending_messages` queue with drain logic
- `MessageMetadata` for timestamps/tokens/cost
- `_drain_stale_on_next_response` for interrupt recovery
- Plan mode support
- `_pending_reply_to` / nudge system

Major changes in `app.py`:
- Workflow guidance system (phase context, advance checks)
- Chicsession auto-save on agent create/close/init
- `_close_workflow_resources` cleanup
- Modified interrupt handling
- Diagnostics label
- Agent close refactored (`_close_agent_core` + `_do_close_agent`)

### Crash log (from `~/claudechic.log`)
The log shows normal operation up to the last response completing, then nothing -- no error logged. The TUI just exits. The `CLIConnectionError` crash was captured in a separate run:

```
claude_agent_sdk._errors.CLIConnectionError: Cannot write to terminated process (exit code: 0)
```

This happens when `_drain_next_message()` tries to send a queued message after the Claude Code CLI process has already exited cleanly.

### Partial fix already applied
A transport liveness check was added to `_drain_next_message()` (commit `99f91c4`) but the clean-exit-after-tutorial issue persists.

## Task

1. **Bisect the cause**: Determine which specific change(s) between the stable version and our version cause the Windows crash. The stable version is available via:
   ```
   git --git-dir=/tmp/mesotools-bare show c5d5966:submodules/claudechic/claudechic/agent.py
   git --git-dir=/tmp/mesotools-bare show c5d5966:submodules/claudechic/claudechic/app.py
   ```
   Our version is at `submodules/claudechic/claudechic/agent.py` and `app.py`.

2. **Fix the crash**: Make the sprustonlab features (workflow guidance, chicsessions, response state machine) work on Windows without crashing.

3. **Add Windows CI**: Add a Windows test to the claudechic test suite that catches this class of crash (clean exit, transport death, StackOverflow).

## Key files
- `submodules/claudechic/claudechic/agent.py` -- Agent class, response processing, message queue
- `submodules/claudechic/claudechic/app.py` -- Main TUI app, event handlers, reconnect logic
- `submodules/claudechic/claudechic/__main__.py` -- Entry point, crash handling
- `submodules/claudechic/claudechic/errors.py` -- Logging setup

## Reproduction
On Windows PowerShell:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
iwr -useb https://sprustonlab.github.io/AI_PROJECT_TEMPLATE/install.ps1 -OutFile install.ps1
.\install.ps1
# Create project, run tutorial workflow, observe crash after graduation phase
```

## Constraints
- Fix must not break Linux/macOS
- All sprustonlab features (workflows, chicsessions, response state) should be preserved
- The claudechic submodule lives at `submodules/claudechic/` with remote `origin` = `sprustonlab/claudechic` and `upstream` = `abast/claudechic`
