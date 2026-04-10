# Project: windows_claudechic_crash
# Phase: sign-off

## Vision (Approved)

**Goal:** Investigate and fix a crash in Claudechic (Textual TUI) that silently exits on Windows.

## CI Status: ALL GREEN
- ubuntu-latest: PASS
- macos-latest: PASS
- windows-latest: PASS
- 184 passed, 5 skipped, 0 failed

## Fixes Delivered

### P0: Windows signal handling (agent.py)
- `_sigint_fallback`: uses `process.terminate()` on Windows instead of `os.kill(pid, signal.SIGINT)`
- `_is_process_alive()`: uses `OpenProcess` + `GetExitCodeProcess` on Windows instead of `os.kill(pid, 0)`
- `_liveness_check`: uses `_is_process_alive()` instead of raw `os.kill`

### P1: Drain logic hardening (agent.py + app.py)
- `_drain_next_message()`: catches `CLIConnectionError`, re-queues message, triggers reconnection
- 19 `run_worker()` calls: added `exit_on_error=False` for non-critical background tasks

### P2: Error visibility (__main__.py)
- `SystemExit` re-raised (no longer swallowed)
- Windows stderr redirected to log file instead of devnull
- `sys.excepthook` + `threading.excepthook` installed for full crash capture

### Bonus: Template freshness + chicsession workflow state
- Synced em dash -> double dash across all workflow files
- Chicsession save preserves workflow engine state

## Tests: 17 new in test_windows_crash_fixes.py
- TestIsProcessAlive (5 tests)
- TestSigintFallback (4 tests)
- TestDrainNextMessageErrorHandling (4 tests)
- TestErrorHooksInstalled (4 tests)

## PR
- https://github.com/sprustonlab/AI_PROJECT_TEMPLATE/pull/12 (develop -> main)

## Remaining Follow-ups (non-blocking)
1. Nudge transport guard (_fire_nudge doesn't check transport liveness)
2. Reconnect loop max-retry counter (no backoff on repeated failures)
3. Duplicate on_complete race (interrupt vs finally block)
4. Manual Windows testing by user
