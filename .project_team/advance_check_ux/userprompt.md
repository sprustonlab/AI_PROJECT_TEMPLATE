# User Prompt

GitHub Issue #21: Advance check UX: show context and auto-focus agent

## Problem
The advance check confirmation prompt in the TUI has two UX issues:

1. **No context shown with the prompt** - When a manual-confirm advance check fires, the user sees the question but cannot see which workflow phase they're in or why they're being asked.

2. **No auto-focus when confirmation is needed** - If the user is viewing a different agent's tab, they have no indication another agent is waiting for confirmation.

## Expected Behavior
1. Show phase name/hint alongside the confirmation prompt (e.g., "Phase X/N: <phase hint>")
2. Auto-switch to agent's view if user is idle, or show a tab badge/notification

## Context
Found during cluster-setup workflow with 6 phases and frequent agent switching.
