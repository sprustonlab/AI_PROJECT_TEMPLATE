# Worktree Feature

Git worktree integration for isolated feature development. Enables working on multiple features simultaneously with separate working directories and Claude sessions.

## Concept

Git worktrees allow multiple checkouts of the same repository. This feature layers on:
1. **Worktree management** - Create/switch/cleanup worktrees via `/worktree` command
2. **Session isolation** - Each worktree maintains its own Claude session history
3. **Finish workflow** - Automated rebase, merge, and cleanup when feature is complete

## Commands

### `/worktree` (no args)
Opens modal to select existing worktrees or create new one. Keyboard navigation with number keys or arrows.

### `/worktree <name>`
Create or switch to worktree named `<name>`:
- If worktree exists: switches to it, resumes most recent session
- If new: creates `../<repo>-<name>/` directory with new branch `<name>`

### `/worktree finish`
Complete feature work and merge back:
1. Claude handles rebase onto base branch and merge
2. App handles cleanup (worktree removal, branch deletion)
3. Retries cleanup up to 3 times, asking Claude to fix issues

### `/worktree cleanup [branches...]`
Remove merged worktrees:
- No args: removes all safe worktrees (merged, no uncommitted changes)
- With args: removes specific branches
- Prompts for confirmation on dirty/unmerged branches

## Architecture

### Module: `worktree.py`

Pure functions for git operations. Stateless—detects current state from git, not memory.

```
worktree.py
├── WorktreeInfo           # Dataclass: path, branch, is_main
├── FinishInfo             # Dataclass: branch_name, base_branch, worktree_dir, main_dir
├── get_repo_name()        # Current repo name from git
├── list_worktrees()       # List all WorktreeInfo objects
├── get_main_worktree()    # Find main (non-feature) worktree
├── start_worktree(name)   # Create worktree + branch
├── get_finish_info(cwd)   # Get FinishInfo for current worktree
├── get_finish_prompt(info)       # Generate Claude prompt for rebase/merge
├── get_cleanup_fix_prompt(...)   # Generate Claude prompt for fixing cleanup
├── finish_cleanup(info)   # Remove worktree and branch
├── has_uncommitted_changes(path) # Check for dirty state
├── is_branch_merged(branch, into)# Check merge status
├── remove_worktree(wt, force)    # Remove worktree + branch
└── cleanup_worktrees(branches)   # Batch cleanup with safety checks
```

### Dataclasses

```python
@dataclass
class WorktreeInfo:
    path: Path      # Worktree directory
    branch: str     # Branch name
    is_main: bool   # True if this is the main worktree

@dataclass
class FinishInfo:
    branch_name: str    # Feature branch to merge
    base_branch: str    # Branch to merge into
    worktree_dir: Path  # Feature worktree path
    main_dir: Path      # Main worktree path
```

### Main worktree detection

A worktree is "main" if its `.git` is a directory (not a file). Linked worktrees have `.git` as a file pointing to `.git/worktrees/<name>` in the main repo. This is robust—works regardless of directory naming.

### App integration (`app.py`)

Key state:
```python
self.sdk_cwd: Path  # SDK's current working directory (changes on worktree switch)
self._pending_worktree_finish: FinishInfo | None  # Info for cleanup after merge
self._worktree_cleanup_attempts: int  # Retry counter (max 3)
```

Key methods:
```
_handle_worktree_command()    # Route /worktree subcommands
_switch_or_create_worktree()  # Create or switch to worktree
_show_worktree_modal()        # Display selection UI
_reconnect_sdk(new_cwd)       # Reconnect SDK in new directory
_attempt_worktree_cleanup()   # Calls finish_cleanup(), delegates failures to Claude
_handle_cleanup_failure()     # Calls get_cleanup_fix_prompt(), sends to Claude
```

The app delegates git operations and prompt generation to `worktree.py`, keeping app.py focused on UI orchestration.

### Session isolation

Each worktree has its own Claude session directory based on absolute path:
```
~/.claude/projects/-Users-me-project/          # Main worktree sessions
~/.claude/projects/-Users-me-project-feature/  # Feature worktree sessions
```

When switching worktrees:
1. `_reconnect_sdk()` creates new SDK client with new `cwd`
2. Looks up most recent session for that directory
3. Auto-resumes if session exists, else starts fresh

## Finish Workflow Detail

The finish workflow splits responsibility between Claude and the app:

**Claude handles:**
- Check for uncommitted changes (fail if any)
- Rebase feature branch onto base branch
- Resolve any conflicts
- Perform merge in main worktree directory

**App handles (after Claude completes):**
- `git worktree remove <path>`
- `git branch -d <branch>`
- Reconnect SDK to main worktree
- If cleanup fails, ask Claude to fix (up to 3 retries)

This split exists because cleanup can fail due to untracked files or other issues that Claude can diagnose and fix.

## UI Components

### WorktreePrompt

Modal widget for worktree selection. Extends `BasePrompt` with:
- List of existing worktrees (numbered)
- "Enter name..." option for creating new
- Returns `("switch", path)` or `("new", name)`

### Visual feedback

- `sub_title` shows `[worktree: <name>]` when in feature worktree
- Notifications for state changes
- Chat messages show `/worktree finish` commands

## Design Decisions

### Stateless detection
Originally tracked worktree state in memory. Changed to always query git because:
- Simpler mental model
- Handles external worktree changes
- No state sync bugs

### Claude handles rebase/merge
Initially app did rebase/merge via subprocess. Changed because:
- Conflict resolution needs intelligence
- Claude can explain what it's doing
- User can intervene if needed

### App handles cleanup
Cleanup is mechanical but can fail in ways Claude can fix:
- Untracked files in worktree
- Uncommitted changes
- Branch not fully merged

### Auto-resume on switch
When switching to existing worktree, automatically resumes most recent session. Preserves context from previous work in that branch.
