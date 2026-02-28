# Claude à la Mode Refactoring Plan

This plan addresses technical debt identified in a January 2026 codebase review. Each phase is self-contained and can be executed by a fresh agent.

## Current State

- **Total**: ~3,700 lines across 17 Python files
- **Problem**: `app.py` is 1,254 lines (34%) and handles too many concerns
- **Goal**: Better organization, improved debugging, consistent patterns

---

## Phase 1: Error Handling & Debugging Infrastructure

**Goal**: Make exceptions visible and debuggable instead of silently swallowed.

### Background

The codebase has many `try/except Exception: pass` blocks that swallow errors silently. This makes debugging difficult, especially in a TUI where stdout isn't visible.

### Tasks

1. **Create `claudechic/errors.py`** with:
   - `log_exception(e, context="")` - logs to file and optionally shows in UI
   - Exception types for recoverable vs fatal errors

2. **Add error display widget** in `widgets/chat.py`:
   - `ErrorMessage` widget with red styling
   - Method `app.show_error(message, exception=None)` that:
     - Logs full traceback to `claude-alamode.log`
     - Shows brief message in chat view (not just toast)

3. **Audit and fix exception handling**:
   - `app.py`: ~15 bare except blocks
   - `widgets/tools.py`: ~6 bare except blocks
   - `widgets/prompts.py`: ~2 bare except blocks
   - For each, either:
     - Log and display the error
     - Or add comment explaining why silence is intentional (shutdown edge cases)

4. **Update `styles.tcss`** with error message styling (red border, like user messages but red)

### Files to Modify
- Create: `claudechic/errors.py`
- Modify: `claudechic/app.py`, `claudechic/widgets/chat.py`, `claudechic/widgets/tools.py`, `claudechic/widgets/prompts.py`, `claudechic/styles.tcss`

### Verification
- Introduce a deliberate error and confirm it appears in chat and log file
- Run existing tests: `uv run pytest tests/ -v`

---

## Phase 2: Extract Worktree Functionality

**Goal**: Pull all worktree-related code into a cohesive module, preparing for potential plugin extraction.

### Background

Worktree functionality is split between:
- `worktree.py` (278 lines) - git operations, pure functions
- `app.py` (~150 lines) - command handling, UI integration

### Tasks

1. **Create `claudechic/features/worktree/` package**:
   ```
   features/worktree/
   ├── __init__.py      # Public API
   ├── git.py           # Current worktree.py content (git operations)
   ├── commands.py      # Command handlers extracted from app.py
   └── prompts.py       # WorktreePrompt moved from widgets/prompts.py
   ```

2. **Extract from `app.py`**:
   - `_handle_worktree_command()` → `features/worktree/commands.py`
   - `_switch_or_create_worktree()` → `features/worktree/commands.py`
   - `_handle_worktree_cleanup()` → `features/worktree/commands.py`
   - `_run_cleanup_prompt()` → `features/worktree/commands.py`
   - `_attempt_worktree_cleanup()` → `features/worktree/commands.py`
   - `_handle_cleanup_failure()` → `features/worktree/commands.py`
   - `_show_worktree_modal()` → `features/worktree/commands.py`
   - `_wait_for_worktree_selection()` → `features/worktree/commands.py`
   - Related state: `_pending_worktree_finish`, `_worktree_cleanup_attempts`, `MAX_CLEANUP_ATTEMPTS`

3. **Move `WorktreePrompt`** from `widgets/prompts.py` to `features/worktree/prompts.py`

4. **Create integration point** in app.py:
   ```python
   from claudechic.features.worktree import handle_worktree_command

   # In _handle_prompt:
   if prompt.strip().startswith("/worktree"):
       handle_worktree_command(self, prompt.strip())
       return
   ```

5. **Update imports** in `widgets/__init__.py` to re-export WorktreePrompt for backward compat

### Files to Create
- `claudechic/features/__init__.py`
- `claudechic/features/worktree/__init__.py`
- `claudechic/features/worktree/git.py`
- `claudechic/features/worktree/commands.py`
- `claudechic/features/worktree/prompts.py`

### Files to Modify
- `claudechic/app.py` (remove ~150 lines)
- `claudechic/widgets/prompts.py` (remove WorktreePrompt)
- `claudechic/widgets/__init__.py` (update exports)
- Delete: `claudechic/worktree.py` (moved to features/worktree/git.py)

### Verification
- Test `/worktree` command creates worktree
- Test `/worktree finish` flow
- Test `/worktree cleanup` flow
- Run existing tests

---

## Phase 3: Extract Agent Management

**Goal**: Pull agent-related code into its own module.

### Background

Agent management is in:
- `agent.py` (47 lines) - AgentSession dataclass
- `app.py` (~100 lines) - `/agent` command, agent switching, creation, closing
- `widgets/agents.py` (152 lines) - AgentSidebar, AgentItem

### Tasks

1. **Create `claudechic/features/agents/` package**:
   ```
   features/agents/
   ├── __init__.py      # Public API
   ├── session.py       # Current agent.py content
   ├── commands.py      # /agent command handlers from app.py
   └── widgets.py       # Move from widgets/agents.py
   ```

2. **Extract from `app.py`**:
   - `_handle_agent_command()` → `features/agents/commands.py`
   - `_create_new_agent()` → `features/agents/commands.py`
   - `_close_agent()` → `features/agents/commands.py`
   - `_do_close_agent()` → `features/agents/commands.py`
   - `_switch_to_agent()` → `features/agents/commands.py`
   - `action_switch_agent()` → `features/agents/commands.py`
   - `action_new_agent()` → `features/agents/commands.py`

3. **Remove proxy properties** from app.py (lines 129-191):
   - Delete `client`, `session_id`, `sdk_cwd`, `current_response`, `pending_tools`, `active_tasks`, `recent_tools`, `_chat_view` properties
   - Update all usages to access via `self._agent.X` directly

4. **Update imports** in `widgets/__init__.py`

### Files to Create
- `claudechic/features/agents/__init__.py`
- `claudechic/features/agents/session.py`
- `claudechic/features/agents/commands.py`
- `claudechic/features/agents/widgets.py`

### Files to Modify
- `claudechic/app.py` (remove ~150 lines + proxy properties)
- `claudechic/widgets/__init__.py`
- Delete: `claudechic/agent.py`, `claudechic/widgets/agents.py`

### Verification
- Test `/agent` lists agents
- Test `/agent foo` creates new agent
- Test `/agent close` closes agent
- Test Ctrl+1-9 switching
- Run existing tests

---

## Phase 4: Extract Simple Commands & Shell

**Goal**: Extract remaining simple commands from app.py.

### Background

Simple commands still in app.py:
- `/clear` - trivial
- `/resume` - session picker
- `/shell` - subprocess execution

### Tasks

1. **Create `claudechic/commands.py`** for simple commands:
   ```python
   def handle_clear(app) -> bool:
       """Handle /clear command. Returns True if handled."""

   def handle_resume(app, prompt: str) -> bool:
       """Handle /resume command. Returns True if handled."""

   def handle_shell(app, prompt: str) -> bool:
       """Handle /shell command. Returns True if handled."""
   ```

2. **Refactor `_handle_prompt()`** in app.py to use command dispatch:
   ```python
   def _handle_prompt(self, prompt: str) -> None:
       # Try built-in commands first
       if handle_clear(self, prompt):
           return
       if handle_resume(self, prompt):
           return
       if handle_shell(self, prompt):
           return
       if handle_worktree_command(self, prompt):
           return
       if handle_agent_command(self, prompt):
           return

       # Otherwise send to Claude...
   ```

3. **Move session picker methods**:
   - `_show_session_picker()` → `commands.py`
   - `_update_session_picker()` → `commands.py`
   - `_hide_session_picker()` → `commands.py`

### Files to Create
- `claudechic/commands.py`

### Files to Modify
- `claudechic/app.py` (remove ~80 lines)

### Verification
- Test `/clear` clears chat
- Test `/resume` shows picker
- Test `/shell ls` runs command
- Run existing tests

---

## Phase 5: Consolidate Spinner & Async Patterns

**Goal**: Remove duplication and use proper async primitives.

### Background

- Two spinner implementations: `ThinkingIndicator` and `ToolUseWidget`
- `threading.Event` used for async coordination instead of `asyncio.Event`

### Tasks

1. **Create `claudechic/widgets/spinner.py`**:
   ```python
   SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
   SPINNER_INTERVAL = 1/10

   class SpinnerMixin:
       """Mixin for widgets that need spinner animation."""
       def start_spinner(self, update_callback): ...
       def stop_spinner(self): ...
   ```

2. **Refactor `ThinkingIndicator`** to use SpinnerMixin

3. **Refactor `ToolUseWidget`** to use SpinnerMixin

4. **Replace `threading.Event` with `asyncio.Event`** in:
   - `claudechic/permissions.py`: `PermissionRequest`
   - `claudechic/widgets/prompts.py`: `BasePrompt`

   Change from:
   ```python
   async def wait(self) -> str:
       while not self._event.is_set():
           await anyio.sleep(0.05)
       return self._result
   ```
   To:
   ```python
   async def wait(self) -> str:
       await self._event.wait()
       return self._result
   ```

### Files to Create
- `claudechic/widgets/spinner.py`

### Files to Modify
- `claudechic/widgets/chat.py` (ThinkingIndicator)
- `claudechic/widgets/tools.py` (ToolUseWidget)
- `claudechic/permissions.py`
- `claudechic/widgets/prompts.py`
- `claudechic/widgets/__init__.py`

### Verification
- Spinner animates correctly in ThinkingIndicator
- Spinner animates correctly in ToolUseWidget
- Permission prompts still work
- Question prompts still work
- Run existing tests

---

## Phase 6: Consolidate Styles to CSS

**Goal**: Move all inline CSS to styles.tcss for consistency.

### Background

Some widgets define `DEFAULT_CSS` inline:
- `widgets/agents.py`: AgentItem, AgentSidebar
- `widgets/autocomplete.py`: TextAreaAutoComplete

### Tasks

1. **Extract `AgentItem.DEFAULT_CSS`** to `styles.tcss`
2. **Extract `AgentSidebar.DEFAULT_CSS`** to `styles.tcss`
3. **Extract `TextAreaAutoComplete.DEFAULT_CSS`** to `styles.tcss`
4. **Remove `DEFAULT_CSS` class attributes** from widgets
5. **Document styling policy** in CLAUDE.md: "All styles in styles.tcss"

### Files to Modify
- `claudechic/styles.tcss` (add ~60 lines)
- `claudechic/widgets/agents.py` (remove DEFAULT_CSS)
- `claudechic/widgets/autocomplete.py` (remove DEFAULT_CSS)
- `CLAUDE.md` (document policy)

### Verification
- Agent sidebar renders correctly
- Autocomplete dropdown renders correctly
- Run existing tests

---

## Phase 7: Constants & Configuration

**Goal**: Centralize constants for easier configuration.

### Background

Constants scattered across files:
- `formatting.py`: `MAX_CONTEXT_TOKENS`
- `app.py`: `AUTO_EDIT_TOOLS`, `COLLAPSE_BY_DEFAULT`, `RECENT_TOOLS_EXPANDED`, `SIDEBAR_MIN_WIDTH`, `MAX_CLEANUP_ATTEMPTS`, `LOCAL_COMMANDS`
- `widgets/tools.py`: `TaskWidget.RECENT_EXPANDED`

### Tasks

1. **Create `claudechic/config.py`**:
   ```python
   # Context
   MAX_CONTEXT_TOKENS = 200_000

   # Tool behavior
   AUTO_EDIT_TOOLS = {"Edit", "Write"}
   COLLAPSE_BY_DEFAULT = {"WebSearch", "WebFetch", "AskUserQuestion", "Read", "Glob", "Grep"}
   RECENT_TOOLS_EXPANDED = 2

   # UI
   SIDEBAR_MIN_WIDTH = 140

   # Truncation limits
   PREVIEW_MAX_LENGTH = 500
   DIFF_MAX_LENGTH = 300
   ```

2. **Update imports** in all files to use config.py

3. **Replace magic numbers** with named constants where appropriate

### Files to Create
- `claudechic/config.py`

### Files to Modify
- `claudechic/formatting.py`
- `claudechic/app.py`
- `claudechic/widgets/tools.py`
- `claudechic/features/worktree/commands.py` (if MAX_CLEANUP_ATTEMPTS moved)

### Verification
- App behaves identically
- Run existing tests

---

## Phase 8: Testing Infrastructure (Future)

**Goal**: Improve test coverage and make testing easier.

### Background

Current state:
- 2 tests total
- Testing Textual apps is challenging
- Need SDK running for E2E tests

### Tasks (exploratory)

1. **Research Textual testing patterns**:
   - Textual's `pilot` API capabilities
   - Mocking SDK responses
   - Snapshot testing for widgets

2. **Add unit tests for pure functions**:
   - `formatting.py` - easy to test
   - `sessions.py` - can test with fixture files
   - `features/worktree/git.py` - can mock subprocess

3. **Add widget tests** using Textual's test framework:
   - Mount widget in isolation
   - Verify rendering
   - Verify event handling

4. **Document testing strategy** in `tests/README.md`

### Files to Create
- `tests/README.md`
- `tests/test_formatting.py`
- `tests/test_sessions.py`
- `tests/test_widgets.py`

### Open Questions
- How to test SDK integration without real SDK?
- How to test permission flows?
- Worth investing in snapshot tests?

---

## Summary: Expected Outcome

After all phases, app.py should be ~400-500 lines (down from 1,254), with:

```
claudechic/
├── __init__.py
├── __main__.py
├── app.py              # ~400 lines - core app, event handlers
├── commands.py         # ~80 lines - /clear, /resume, /shell
├── config.py           # ~30 lines - constants
├── errors.py           # ~50 lines - error handling
├── formatting.py       # unchanged
├── messages.py         # unchanged
├── permissions.py      # minor changes (asyncio.Event)
├── sessions.py         # unchanged
├── styles.tcss         # +60 lines from extracted CSS
├── features/
│   ├── __init__.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── session.py
│   │   ├── commands.py
│   │   └── widgets.py
│   └── worktree/
│       ├── __init__.py
│       ├── git.py
│       ├── commands.py
│       └── prompts.py
└── widgets/
    ├── __init__.py
    ├── autocomplete.py
    ├── chat.py
    ├── header.py
    ├── prompts.py      # minus WorktreePrompt
    ├── spinner.py      # new - shared spinner
    ├── todo.py
    └── tools.py
```

---

## Execution Notes

- Each phase can be done in 1-2 sessions
- Run `uv run pytest tests/ -v` after each phase
- Manual testing recommended: start app, try relevant commands
- Commit after each phase with message like "refactor: extract worktree to features/"
