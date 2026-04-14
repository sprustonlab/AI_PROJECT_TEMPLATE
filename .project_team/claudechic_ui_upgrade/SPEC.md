# SPEC: claudechic UI Upgrade

## Implementation Order

| # | Item | Type | Est. Hours |
|---|------|------|------------|
| 1 | Issue #9 -- Workflow/phase display on restore | Bug fix | 1-2h |
| 2 | ChicsessionActions buttons + WorkflowPickerScreen | New feature | 4-6h |
| 3 | Issue #4 -- Agent sidebar overflow | Bug fix | 2-3h |
| 4 | ComputerInfoLabel + ComputerInfoModal | New feature | 3-4h |
| 5 | DiffButton + MarkdownPreview | New feature | 3-4h |
| 6 | Agent Switcher (Ctrl+G style) | Enhancement | 4-6h |

Items 1 and 3 are independent and can be parallelized.
Item 2 depends on Item 1 (needs workflow state wired correctly first).
Items 4 and 5 are independent of each other and of 1-3.

---

## Command Reality (verified)

| What user types | What it does |
|-----------------|-------------|
| `/<workflow-id>` (e.g. `/project_team`) | Activates a workflow |
| `/<workflow-id> stop` | Deactivates a workflow |
| `/workflow list` | Lists discovered workflows |
| `/workflow reload` | Rediscovers workflow manifests |
| `/chicsession save <name>` | First-time save (after this, auto-save kicks in) |
| `/chicsession restore` | Opens session picker |
| `/chicsession restore <name>` | Restores named session directly |
| `/diff` | Opens DiffScreen for uncommitted changes |

There is NO `/advance` command. Phase advancement is agent-driven via MCP tools.
Chicsession auto-saves on agent lifecycle events after initial manual save.

---

## Naming Conventions (from Terminology)

| Element | Class Name | ID |
|---------|------------|-----|
| Footer computer info button | `ComputerInfoLabel` | `#computer-info-label` |
| Computer info modal | `ComputerInfoModal` | -- |
| Info modal base class | `InfoModal` | -- |
| Sidebar action buttons container | `ChicsessionActions` | `#chicsession-actions` |
| Action button widget | `ActionButton` | `#workflows-btn`, `#restore-btn`, `#stop-btn` |
| Workflow picker screen | `WorkflowPickerScreen` | -- |
| Workflow picker item | `WorkflowItem` | -- |
| Files section diff trigger | `DiffButton` | `#diff-btn` |
| Markdown preview modal | `MarkdownPreviewModal` | -- |
| Agent switcher overlay | `AgentSwitcher` | `#agent-switcher` |
| Footer agent name button | `AgentLabel` | `#agent-label` |

Rules:
- Footer clickables -> `XxxLabel` (extends `ClickableLabel`)
- Sidebar containers -> `XxxSection` (extends `SidebarSection`)
- Modal overlays -> `XxxModal` (extends `ModalScreen` or `InfoModal`)
- Full-page pickers -> `XxxScreen` (extends `Screen`)
- IDs use kebab-case
- "Chicsession" is always one word, lowercase

---

## Item 1: Issue #9 -- Workflow/Phase Display on Restore

**Problem:** `_handle_restore()` calls `_update_sidebar_label(app, name)` with only the name. It then calls `_restore_workflow_from_session()` which restores the engine but never updates the sidebar label.

**Fix:** After `_restore_workflow_from_session()` in `chicsession_cmd.py` (~line 270), call `app._update_sidebar_workflow_info()` which already exists (app.py ~line 1749) and does the right thing.

**Edge cases:**
- No `workflow_state` in saved session -> leave workflow/phase empty (correct)
- `workflow_state` exists but phase is None -> show workflow, hide phase
- Stale workflow pointing to deleted workflow -> show name, log warning, don't crash

**Files:** `claudechic/features/chicsession/chicsession_cmd.py`, `claudechic/app.py`

---

## Item 2: ChicsessionActions Buttons + WorkflowPickerScreen

### 2A: ChicsessionActions

**Widget hierarchy:**
```
ChicsessionLabel #chicsession-label
  +-- Static .chicsession-title     ("Chicsession")
  +-- Static .chicsession-value     (session name or "none")
  +-- Static .chicsession-workflow  (workflow name)
  +-- Static .chicsession-phase     (phase name)
  +-- ChicsessionActions #chicsession-actions        <- NEW
        +-- ActionButton #workflows-btn or #stop-btn
        +-- ActionButton #restore-btn (idle only)
```

**Adaptive state machine:**

| Workflow State | Buttons | Action on Click |
|----------------|---------|-----------------|
| No workflow active | `[Workflows]` `[Restore]` | Opens WorkflowPickerScreen / Opens ChicsessionScreen |
| Workflow active | `[Stop]` | Triggers `/<active-wf-id> stop` |

**ActionButton design:**
- Extends `Static`, `can_focus = False` (CRITICAL: don't steal focus)
- Each button type posts its own Message:
  - `[Workflows]` -> `ChicsessionActions.WorkflowPickerRequested()`
  - `[Restore]` -> `ChicsessionActions.RestoreRequested()`
  - `[Stop]` -> `ChicsessionActions.StopRequested()`
- ChatApp handles each message separately (no generic command dispatch)

**State updates:** `ChicsessionActions.update_state(workflow_active: bool)` rebuilds buttons. Called by ChatApp on workflow activation, deactivation, and session restore.

**Layout mockups:**

No workflow:
```
Chicsession
  none
  [Workflows] [Restore]
```

Workflow active:
```
Chicsession
  my-session
  Workflow: project-team
  Phase: leadership
  [Stop]
```

**CSS:**
```css
ChicsessionActions { layout: horizontal; height: auto; padding: 0 1; }
ActionButton { height: 1; padding: 0 1; background: $panel; color: $text-muted; }
ActionButton:hover { background: $accent; color: white; }
```

**First-run hint** (direct `app.notify()` with `HintStateStore` persistence):

Trigger: On first mount of `ChicsessionLabel` when no chicsession is loaded
(`self._chicsession_name is None`) and sidebar is visible. This is the moment
a new user sees the empty "none" state and would benefit from guidance.

```python
# In ChatApp, after sidebar becomes visible and chicsession label is mounted:
if self._chicsession_name is None:
    store = HintStateStore(self._cwd)
    if store.get_times_shown("workflow-actions-tip") == 0:
        self.notify(
            "Tip: Click [Workflows] in the sidebar to start, or type /<workflow-name>",
            severity="information",
            timeout=8,
        )
        store.increment_shown("workflow-actions-tip")
        store.save()
```

Does NOT use `global/hints.yaml` — the hints YAML pipeline is project-state
based, not UI-event driven. Uses direct notify + `HintStateStore` for
cross-session persistence (shows once ever, not once per session).
Follows the precedent set by the existing Ctrl+N hint.

### 2B: WorkflowPickerScreen

**New file:** `claudechic/screens/workflow_picker.py`

**Widget hierarchy:**
```
WorkflowPickerScreen (extends Screen[str | None])
  +-- Vertical #workflow-picker-container
        +-- Static #workflow-picker-title  ("Select Workflow (N available)")
        +-- Input #workflow-search         ("Search workflows...")
        +-- ListView #workflow-list
              +-- WorkflowItem per workflow
                    +-- Label .workflow-name  (workflow_id)
                    +-- Label .workflow-meta  (role, phase count, status)
```

**Mockup:**
```
Select Workflow (4 available)
+------------------------------------------------------+
| Search workflows...                                  |
+------------------------------------------------------+

| project-team
| role: coordinator . 5 phases . available

| tutorial
| role: learner . 4 phases . available

| audit
| role: auditor . 3 phases . available
```

**Data sources:**
- workflow_id: key from `app._workflow_registry`
- main_role: from `app._load_result.workflows[wf_id].main_role`
- phase_count: count phases matching namespace
- is_active: `wf_id == app._workflow_engine.workflow_id`

**Interaction flow:**
1. User clicks [Workflows] -> ChatApp pushes WorkflowPickerScreen
2. User searches/navigates, selects a workflow
3. Screen dismisses with `workflow_id` string
4. ChatApp callback calls `_activate_workflow(workflow_id)` which handles chicsession naming etc.
5. If selected workflow is already active -> toast "Already active", dismiss with None
6. If different workflow is active -> toast "Stop current workflow first", dismiss with None

**Edge cases:**
- No workflows discovered -> empty state: "No workflows discovered. Add YAML files to workflows/"
- Search returns nothing -> clear list, show "0 matches"
- Already active workflow selected -> toast, no action
- Different workflow active -> toast with stop instructions, no action (don't auto-stop)

**Navigation:** Follows ChicsessionScreen pattern exactly (Up/Down arrows, Enter, Escape, real-time search filtering).

**Files:** `claudechic/screens/workflow_picker.py` (new), `claudechic/widgets/layout/sidebar.py`, `claudechic/app.py`, `claudechic/styles.tcss`

---

## Item 3: Issue #4 -- Agent Sidebar Overflow

**Two changes:**

A. **Lower compact threshold:** If `agent_count > 6`, force compact mode regardless of available space.

B. **Add scrolling:** Wrap AgentSection items in `VerticalScroll#agent-scroll`. Set `max_height` dynamically from `_layout_sidebar_contents()`.

**Height budget change:** Add ChicsessionLabel to `_layout_sidebar_contents()` as a fixed cost:
```
CHICSESSION_BASE = 3        (title + name + action buttons)
CHICSESSION_WORKFLOW = 2    (workflow + phase lines when active)
```

**Auto-scroll:** Active agent must scroll into view when switched.

**Mockup (11 agents, compact, scrollable):**
```
Agents (11)              ^
  o agent-1              |
  * agent-2              =
  * agent-3              |
  o agent-4              v
  o agent-5
  * agent-6
```

**CSS:**
```css
AgentSection #agent-scroll { height: auto; scrollbar-size: 1; }
```

**Edge cases:**
- 0 agents: section hidden (existing)
- Agent added while scrolled: mount and auto-scroll if active
- Agent removed: scroll adjusts naturally

**Files:** `claudechic/widgets/layout/sidebar.py`, `claudechic/app.py` (`_layout_sidebar_contents`), `claudechic/styles.tcss`

---

## Item 4: ComputerInfoLabel + ComputerInfoModal

**InfoModal base class** (new file: `claudechic/widgets/modals/base.py`):
- `InfoSection` frozen dataclass: `title`, `content`, `copyable=True`, `scrollable=False`
- `InfoModal(ModalScreen)`: takes `title: str` and `sections: list[InfoSection]`
- Renders: header + sections (each with optional copy button) + close footer
- ESC dismisses, copy buttons use pyperclip, close button dismisses
- Refactor `DiagnosticsModal` to subclass `InfoModal`

**ComputerInfoLabel** in footer:
- Displays "sys" (3 chars) -- placed after DiagnosticsLabel with a separator
- On click posts `ComputerInfoLabel.Requested()` message
- ChatApp gathers data synchronously, constructs `ComputerInfoModal`

**ComputerInfoModal sections:**

| Field | Source |
|-------|--------|
| Host | `platform.node()` |
| OS | `f"{platform.system()} {platform.release()} ({platform.machine()}")` |
| Python | `platform.python_version()` |
| SDK | `importlib.metadata.version("claude-code-sdk")` or `"unknown"` |
| claudechic | `importlib.metadata.version("claudechic")` or `"unknown"` |
| CWD | `self._cwd` |

**Footer mockup:**
```
opus . Auto-edit: off . session_info . sys          [====30%====] CPU 12% branch develop
```

**Modal mockup:**
```
+----------------------------------------------+
| System Info                                  |
|                                              |
|  Host:        MacBook-Pro.local              |
|  OS:          macOS 15.2 (arm64)             |
|  Python:      3.12.4                         |
|  SDK:         0.3.1                          |
|  claudechic:  0.9.0                          |
|  CWD:         /Users/me/project              |
|                                              |
|             [Copy]  [Close]                  |
+----------------------------------------------+
```

**CSS:** Modal centered, 40-60 cols wide, surface background, bordered, info rows at height 1.

**Files:** `claudechic/widgets/modals/base.py` (new), `claudechic/widgets/modals/diagnostics.py` (refactor), `claudechic/widgets/layout/footer.py`, `claudechic/app.py`, `claudechic/styles.tcss`

---

## Item 5: DiffButton + MarkdownPreview

### 5A: DiffButton in FilesSection Header

**SidebarSection modification:** Accept optional `header_actions` parameter. When provided, compose title in a `Horizontal` with action widgets alongside.

**DiffButton:** Extends `Static`, `can_focus = False`, renders "/diff", posts `DiffButton.DiffRequested()`. ChatApp handles via `self._handle_prompt("/diff")`.

**FilesSection header mockup:**
```
Files                /diff
  ...sidebar.py      +12 -3
```

**Files:** `claudechic/widgets/layout/sidebar.py`

### 5B: Markdown Preview Toggle in DiffScreen

The user wants to see spec files (.md) as rendered markdown when reviewing diffs.
This is NOT a standalone modal — it's wired INTO the existing DiffScreen diff viewer.

**Architecture:** Each `FileDiffPanel` for a `.md` file gets a `[Preview]` toggle
button in its `FileHeaderLabel` row. Clicking it swaps the hunk widgets for a
rendered `Markdown` widget showing the file's current content.

**Widget hierarchy change in FileDiffPanel (for .md files only):**
```
FileDiffPanel
  +-- Horizontal .file-header-row               <- NEW wrapper
  |     +-- FileHeaderLabel (existing)
  |     +-- PreviewToggle #preview-{safe_id}     <- NEW (only for .md files)
  +-- HunkWidget ...                             <- visible when preview OFF
  +-- HunkSeparator ...                          <- visible when preview OFF
  +-- VerticalScroll #md-preview-{safe_id}       <- visible when preview ON
        +-- Markdown #md-content-{safe_id}         (Textual built-in)
```

**PreviewToggle widget:**
```python
class PreviewToggle(Static):
    """Toggle button: switches between diff hunks and rendered markdown."""
    can_focus = False

    class Toggled(Message):
        def __init__(self, path: str, show_preview: bool) -> None:
            self.path = path
            self.show_preview = show_preview
            super().__init__()

    def __init__(self, path: str, **kwargs) -> None:
        super().__init__("[Preview]", **kwargs)
        self._path = path
        self._preview_active = False

    def on_click(self, event) -> None:
        event.stop()
        self._preview_active = not self._preview_active
        label = "[Diff]" if self._preview_active else "[Preview]"
        self.update(label)
        self.post_message(self.Toggled(self._path, self._preview_active))
```

**FileDiffPanel changes:**
- In `compose()`, detect if `self.change.path.endswith(".md")`.
- If .md: wrap header in `Horizontal`, add `PreviewToggle`, and mount a hidden
  `VerticalScroll` with `Markdown` widget after the hunks.
- Handle `PreviewToggle.Toggled`: toggle visibility of hunks vs markdown container.
- Markdown content loaded lazily on first toggle (read file from disk via `Path.read_text(encoding='utf-8')`).

**DiffSidebar enhancement:** `.md` files get a small "md" badge in their `DiffFileItem`:
```
M  ...SPEC.md (2)  md  ✎
```

**Mockup — DiffScreen with .md file, diff mode (default):**
```
+-------------------------------+--------------------------------------------+
| Changed Files                 |  .project_team/.../SPEC.md      [Preview]  |
|                               |                                            |
|   M ...SPEC.md (2)  md  e    |  @@ -250,8 +250,6 @@                       |
|   M ...footer.py (3)    e    |  - | MCP | Count from self._mcp_server |   |
|   M ...sidebar.py (1)   e    |  - | Agents | len(self.agent_mgr) |        |
|                               |                                            |
|                               |  @@ -273,10 +271,8 @@                     |
|                               |  -|  MCP:         1 server (chic)  |       |
|                               |  -|  Agents:      3 active         |       |
+-------------------------------+--------------------------------------------+
```

**Mockup — DiffScreen with .md file, preview mode (after clicking [Preview]):**
```
+-------------------------------+--------------------------------------------+
| Changed Files                 |  .project_team/.../SPEC.md         [Diff]  |
|                               |                                            |
|   M ...SPEC.md (2)  md  e    |  # SPEC: claudechic UI Upgrade             |
|   M ...footer.py (3)    e    |                                            |
|   M ...sidebar.py (1)   e    |  ## Implementation Order                   |
|                               |                                            |
|                               |  | # | Item        | Type    | Est. Hours ||
|                               |  |---|-------------|---------|------------|
|                               |  | 1 | Issue #9... | Bug fix | 1-2h      ||
|                               |  ...                                       |
+-------------------------------+--------------------------------------------+
```

**Interaction flow:**
1. User opens DiffScreen (via /diff or sidebar [/diff] button).
2. For .md files, `[Preview]` button appears in the file header row.
3. Click `[Preview]` -> hunks hide, rendered markdown appears, button label changes to `[Diff]`.
4. Click `[Diff]` -> markdown hides, hunks reappear, button label changes to `[Preview]`.
5. Navigation (j/k) skips over the file when in preview mode (hunks are hidden, not focusable).
6. Comments on hunks are preserved across toggles (HunkWidgets stay mounted, just hidden).

**Data source for preview content:**
- `Path(cwd / change.path).read_text(encoding='utf-8')` — reads CURRENT file content (post-edit).
- Loaded lazily on first `[Preview]` click, cached in `FileDiffPanel._md_content`.
- 50KB size gate: if file > 50KB, toast "File too large for preview" and don't toggle.

**CSS:**
```css
PreviewToggle { width: auto; height: 1; padding: 0 1; color: $text-muted; pointer: pointer; }
PreviewToggle:hover { color: $primary; background: $panel; }
FileDiffPanel .md-preview { height: auto; min-height: 10; padding: 0 1; }
FileDiffPanel .md-preview.hidden { display: none; }
```

**Edge cases:**
- File deleted between diff and preview click -> toast "File not found", stay in diff mode.
- UnicodeDecodeError -> toast "Cannot preview file", stay in diff mode.
- Empty .md file -> show "(empty file)" placeholder in preview area.
- Non-.md files -> no PreviewToggle, no change to existing behavior.
- Binary files -> no PreviewToggle (already handled as "no diff available").
- Hunk navigation: when preview is active for a file, j/k skip to next file's hunks.
- Comments: toggling to preview and back preserves all hunk comments (widgets stay mounted, just display:none).

**Also keep MarkdownPreviewModal for sidebar .md clicks:**
The standalone `MarkdownPreviewModal` is ALSO still useful for clicking `.md` files
in the chat sidebar (FilesSection) when NOT in DiffScreen. Keep it as a simpler
read-only viewer for that context.

**New file:** `claudechic/widgets/content/markdown_preview.py`
- `MarkdownPreviewModal(ModalScreen)` — for sidebar FileItem clicks on .md files
- `PreviewToggle(Static)` — for DiffScreen integration

**Files:** `claudechic/widgets/content/markdown_preview.py` (new), `claudechic/features/diff/widgets.py` (modify FileDiffPanel, FileHeaderLabel, DiffFileItem), `claudechic/app.py`, `claudechic/styles.tcss`

---

## Item 6: Agent Switcher (Ctrl+G style)

**Rationale:** Addresses the discoverability fallback concern -- sidebar buttons only show at >= 110 terminal width. The agent switcher works at ANY terminal size via keyboard.

### 6A: AgentSwitcher Modal

**Widget hierarchy:**
```
AgentSwitcher(ModalScreen)
  +-- Vertical #agent-switcher-container
        +-- Input #agent-search (placeholder: "search agents...")
        +-- ListView #agent-results
              +-- AgentSwitcherItem (per agent, shows name + status)
```

**Mockup:**
```
+-----------------------------------+
| > search agents...                |
|                                   |
|   * Coordinator        (busy)     |
| > o UIDesigner          (idle)    |
|   * Implementer        (busy)     |
+-----------------------------------+
```

**Keybinding:** Ctrl+G (avoids conflict with Ctrl+A select-all, Ctrl+P print).
- Fuzzy search by agent name
- Up/Down to navigate, Enter to switch, Escape to dismiss
- Shows status indicators (same as sidebar)

### 6B: AgentLabel in Footer

**Naming:** `AgentLabel` (extends `ClickableLabel`), ID `#agent-label`.

**What it displays:** The active agent's display name, truncated to 12 chars max.
- Single agent (default "main"): hidden (no label shown — avoids clutter for solo users).
- Multiple agents: shows active agent name, e.g. "Coordinator".
- No agents connected: hidden.

This is more useful than a generic "agents" label because it tells the user
WHICH agent they're talking to — critical context when running multi-agent sessions.

**Footer position:** Right side, between ProcessIndicator and ContextBar. This groups
it with other status indicators rather than the left-side settings cluster.

**Updated footer compose order:**
```
Horizontal #footer-content
  +-- ViModeLabel
  +-- ModelLabel
  +-- Static (sep)
  +-- PermissionModeLabel
  +-- Static (sep)
  +-- DiagnosticsLabel
  +-- Static (sep)
  +-- ComputerInfoLabel "sys"
  +-- Static #footer-spacer (1fr)
  +-- ProcessIndicator
  +-- AgentLabel #agent-label             <- NEW (hidden when single agent)
  +-- ContextBar
  +-- CPUBar
  +-- Static #branch-label
```

**Footer mockup — single agent (label hidden):**
```
 opus . Auto-edit: off . session_info . sys          [====30%====] CPU 12% develop
```

**Footer mockup — multiple agents, "Coordinator" active:**
```
 opus . Auto-edit: off . session_info . sys       Coordinator [==30%==] CPU 12% develop
```

**Footer mockup — 80-col terminal, multiple agents:**
```
 opus . Auto-edit: off . session_info . sys  Coordin.. [30%] CPU 12% develop
```
(Truncated to fit — the `1fr` spacer compresses, and the label truncates at 12 chars max.)

**Interaction:**
1. Click `AgentLabel` -> posts `AgentLabel.SwitcherRequested()` message.
2. ChatApp handles by pushing `AgentSwitcher` modal (same as Ctrl+G).
3. `can_focus = False` — does not steal focus from chat input.

**Reactive updates:** ChatApp calls `agent_label.update_agent(name, visible)` when:
- Agent is switched (`on_agent_switched`)
- Agent is created/closed (agent count changes)
- Set `visible=False` when `len(self.agent_mgr) <= 1`

**Widget design:**
```python
class AgentLabel(ClickableLabel):
    """Shows active agent name. Click to open Agent Switcher."""

    class SwitcherRequested(Message):
        """Emitted when user clicks to open agent switcher."""

    MAX_NAME_LEN = 12

    def on_click(self, event) -> None:
        self.post_message(self.SwitcherRequested())

    def update_agent(self, name: str, visible: bool) -> None:
        """Update displayed agent name and visibility."""
        if not visible:
            self.add_class("hidden")
            return
        self.remove_class("hidden")
        display = name[:self.MAX_NAME_LEN - 2] + ".." if len(name) > self.MAX_NAME_LEN else name
        self.update(display)
```

**CSS:**
```css
AgentLabel { width: auto; padding: 0 1; color: $text-muted; }
AgentLabel:hover { background: $panel; }
AgentLabel.hidden { display: none; }
```

### 6C: Discovery Hint

Uses direct `app.notify()` with `HintStateStore` for cross-session persistence.
Does NOT use `global/hints.yaml` — the hints YAML pipeline is project-state
based, not UI-event driven. Follows the precedent set by the existing Ctrl+N hint.

**When to show:** On the first time a second agent is created (agent count goes
from 1 to 2). This is the moment the feature becomes relevant. Showing at
startup would be noise for single-agent users.

**Trigger point:** In ChatApp's `on_agent_created()` handler:
```python
if len(self.agent_mgr.agents) == 2:
    store = HintStateStore(self._cwd)
    if store.get_times_shown("agent-switcher-tip") == 0:
        self.notify(
            "Tip: Press Ctrl+G to switch agents, or click the agent name in the bottom bar",
            severity="information",
            timeout=8,
        )
        store.increment_shown("agent-switcher-tip")
        store.save()
```

**Persistence:** `HintStateStore` writes to `.chicsessions/.hint_state.json`
(or equivalent project-local path). The `get_times_shown` / `increment_shown`
API ensures the hint shows once ever across all sessions, not once per session.

**Files:** `claudechic/widgets/modals/agent_switcher.py` (new), `claudechic/widgets/layout/footer.py` (add AgentLabel), `claudechic/app.py` (handlers, hint trigger), `claudechic/styles.tcss`

---

## New Files Summary

| File | Contents |
|------|----------|
| `claudechic/widgets/modals/base.py` | `InfoSection`, `InfoModal` base class |
| `claudechic/screens/workflow_picker.py` | `WorkflowPickerScreen`, `WorkflowItem` |
| `claudechic/widgets/content/markdown_preview.py` | `MarkdownPreviewModal` |
| `claudechic/widgets/modals/agent_switcher.py` | `AgentSwitcher`, `AgentSwitcherItem` |

## Modified Files Summary

| File | Changes |
|------|---------|
| `claudechic/features/chicsession/chicsession_cmd.py` | Item 1: add workflow info update after restore |
| `claudechic/widgets/layout/sidebar.py` | Items 2,3,5A: ChicsessionActions, ActionButton, AgentSection scroll, SidebarSection header_actions, DiffButton |
| `claudechic/widgets/layout/footer.py` | Item 4: add ComputerInfoLabel |
| `claudechic/widgets/modals/diagnostics.py` | Item 4: refactor to extend InfoModal |
| `claudechic/features/diff/widgets.py` | Item 5B: PreviewToggle in FileDiffPanel, md badge in DiffFileItem |
| `claudechic/app.py` | Items 1-6: message handlers, height budget, workflow picker callback |
| `claudechic/styles.tcss` | Items 2-6: new styles |
| `claudechic/screens/chat.py` | Item 2: mount ChicsessionActions |

---

## TDD Test Plan

9 tests (7 main + 2 edge cases). Tests are written BEFORE implementation.

### Testing Patterns

| Pattern | When to use | Mocking |
|---------|-------------|---------|
| **WidgetTestApp** | Isolated widget behavior | ZERO mocking. Mount widget in minimal Textual app. |
| **ChatApp + mock_sdk** | Full app integration flows | Uses existing `mock_sdk` fixture from conftest.py. |

### Approved Mocks (beyond mock_sdk)

Only 2 additional mocks were approved:
1. `app._workflow_registry` dict injection (Test 4 — workflow picker integration)
2. `FileChange` list injection (Tests 7-8 — diff preview)

### Tests

**Test 1: `test_restore_session_shows_workflow_and_phase`** (Item 1)
- Pattern: ChatApp + mock_sdk
- Setup: Write `.chicsessions/test.json` in tmp_path with `workflow_state: {"workflow_id": "tutorial", "current_phase": "tutorial:design"}`
- Action: Mount ChatApp at size=(120,40), submit `/chicsession restore test`
- Assert:
  - `chicsession_label.workflow_text == "tutorial"`
  - `chicsession_label.phase_text == "design"`
  - Both Static widgets have `display != none`

**Test 2: `test_restore_with_missing_workflow_state`** (Item 1 edge case)
- Pattern: ChatApp + mock_sdk
- Setup: Write `.chicsessions/test.json` WITHOUT `workflow_state` key
- Action: Mount ChatApp, submit `/chicsession restore test`
- Assert:
  - `chicsession_label.workflow_text == ""`
  - `chicsession_label.phase_text == ""`
  - No crash, no exception

**Test 3: `test_chicsession_buttons_adapt_to_workflow_state`** (Item 2)
- Pattern: WidgetTestApp (ZERO mocking)
- Setup: Mount ChicsessionLabel at size=(120,40)
- Action 1: Check initial state (no workflow)
- Assert 1:
  - `#workflows-btn` is present and visible
  - `#restore-btn` is present and visible
  - `#stop-btn` is NOT present
  - Click `#restore-btn` -> assert `ChicsessionActions.RestoreRequested` message is posted (U1)
- Action 2: Set `chicsession_label.workflow_text = "project-team"` (triggers state update)
- Assert 2:
  - `#stop-btn` is present and visible
  - `#workflows-btn` is NOT present
  - `#restore-btn` is NOT present
  - Click `#stop-btn` -> assert `ChicsessionActions.StopRequested` message is posted (U3)
- Action 3: Resize to 80x24 (narrow terminal, below SIDEBAR_MIN_WIDTH=110)
- Assert 3:
  - ChicsessionActions buttons are not visible (sidebar hidden at < 110 width) (U2)
  - Verifies graceful degradation for narrow terminals

**Test 4: `test_workflows_button_opens_picker_and_activates`** (Item 2)
- Pattern: ChatApp + mock_sdk
- Setup: Inject `app._workflow_registry = {"tutorial": Path("/tmp/workflows/tutorial")}` after mount. Pre-set `app._chicsession_name = "test"` to prevent `_activate_workflow` from prompting for a session name (C1). Size=(120,40).
- Action: Click `#workflows-btn`, wait for WorkflowPickerScreen, select "tutorial" item, press Enter
- Assert:
  - WorkflowPickerScreen was pushed (check screen stack)
  - Screen lists "tutorial" as a WorkflowItem
  - After selection and dismiss, `chicsession_label.workflow_text == "tutorial"`
- Height budget integration (C2):
  - Action: After picker flow completes, add 8 agents via `agent_section.add_agent()`
  - Assert: ChicsessionActions buttons/labels still visible (no `display: none`)
  - Assert: All AgentSection items are queryable and visible (no `display: none`)
  - Verifies height budget coordination between Items 2 and 3
- Approved mock: `app._workflow_registry` dict injection

**Test 5: `test_sidebar_handles_many_agents`** (Item 3)
- Pattern: WidgetTestApp (ZERO mocking)
- Setup: Mount AgentSection
- Action: Call `agent_section.add_agent(f"id-{i}", f"Agent-{i}")` for 12 agents
- Assert:
  - All AgentItems have the `compact` CSS class: `all(item.has_class("compact") for item in agent_section.query(AgentItem))` (S1: tests observable output, not private state)
  - `VerticalScroll` container exists as child (query `#agent-scroll`)
  - All 12 AgentItem widgets are queryable (`len(agent_section.query(AgentItem)) == 12`)
  - No items have `display: none`

**Test 6: `test_sys_label_click_opens_modal`** (Item 4)
- Pattern: WidgetTestApp with StatusFooter
- Setup: Mount StatusFooter
- Action: Click `#computer-info-label`
- Assert:
  - `ComputerInfoModal` is pushed onto screen stack
  - Modal contains Static widgets with non-empty text for: Host, OS, Python, CWD
  - SDK and claudechic values are either valid version strings or "unknown"
  - Pressing Escape dismisses the modal (screen stack returns to previous)

**Test 7: `test_diff_button_and_md_preview_toggle`** (Item 5)
- Pattern: WidgetTestApp for Part A; DiffScreen with injected FileChange for Part B
- Part A -- DiffButton:
  - Setup: Mount FilesSection with header_actions
  - Action: Click DiffButton
  - Assert: `DiffButton.DiffRequested` message is posted
- Part B -- Preview toggle:
  - Setup: Mount DiffScreen with FileChange list including one `.md` file change. Write a real `.md` file (< 50KB) to tmp_path.
  - Action: Select the `.md` file, click `[Preview]` toggle
  - Assert: Hunk widgets are hidden (`display: none`), Markdown widget is visible and contains rendered content
  - Action: Click `[Diff]` toggle
  - Assert: Hunk widgets visible again, Markdown widget hidden
  - Assert: For non-.md files, no PreviewToggle widget exists
- Approved mock: `FileChange` list injection for DiffScreen

**Test 8: `test_md_preview_rejects_large_files`** (Item 5 edge case)
- Pattern: Same as Test 7 Part B
- Setup: Write a `.md` file > 50KB to tmp_path. Inject FileChange pointing to it.
- Action: Select the .md file, click `[Preview]`
- Assert:
  - Toast notification appears with "too large" message
  - Hunk widgets remain visible (preview did NOT activate)
  - No Markdown widget mounted

**Test 9: `test_agent_switcher_hint_and_ctrl_g`** (Item 6)
- Pattern: ChatApp + mock_sdk
- Setup: Mount ChatApp at size=(120,40). Starts with 1 agent (default main).
- Step 1 -- Hint fires on 1->2:
  - Action: Create second agent
  - Assert: Toast notification fired with text containing "Ctrl+G"
  - Assert: `HintStateStore(app._cwd).get_times_shown("agent-switcher-tip") == 1`
  - Assert: `AgentLabel` in footer is visible, shows second agent's name (or main's name depending on which is active)
- Step 2 -- Hint does NOT repeat on 2->3:
  - Action: Create third agent
  - Assert: NO new toast with "Ctrl+G" text
  - Assert: `HintStateStore(app._cwd).get_times_shown("agent-switcher-tip") == 1` (unchanged)
- Step 3 -- Ctrl+G opens switcher:
  - Action: Press Ctrl+G
  - Assert: `AgentSwitcher` modal is on screen stack, lists 3 agents with names
- Step 4 -- Navigate and switch:
  - Action: Press Down arrow, press Enter (select second agent)
  - Assert: Modal dismissed
  - Assert: Active agent changed to the second agent
  - Assert: `AgentLabel` text updated to second agent's name
- Step 5 -- AgentLabel hides at 1 agent:
  - Action: Close 2 agents (back to 1)
  - Assert: `AgentLabel` is hidden
- Step 6 -- Cross-session persistence:
  - Action: Tear down the ChatApp instance
  - Action: Create a NEW ChatApp instance pointing at the SAME tmp_path (same `_cwd`, so same HintStateStore on disk)
  - Action: Mount at size=(120,40), create 2 agents (reach the 1->2 threshold again)
  - Assert: NO toast notification fires (HintStateStore already has times_shown == 1 from previous app session)
  - Assert: `HintStateStore(app._cwd).get_times_shown("agent-switcher-tip") == 1` (unchanged)
  - This verifies the hint fires once EVER, not once per app session
- No new mocks: HintStateStore uses `app._cwd` which points at tmp_path in test

### Test Summary

| Test | Item | Pattern | Mocks |
|------|------|---------|-------|
| 1 | Item 1 (restore wf display) | ChatApp + mock_sdk | mock_sdk only |
| 2 | Item 1 (missing wf state) | ChatApp + mock_sdk | mock_sdk only |
| 3 | Item 2 (button adaptation) | WidgetTestApp | NONE |
| 4 | Item 2 (picker flow) | ChatApp + mock_sdk | mock_sdk + registry injection |
| 5 | Item 3 (agent overflow) | WidgetTestApp | NONE |
| 6 | Item 4 (sys modal) | WidgetTestApp | NONE |
| 7 | Item 5 (diff + preview) | WidgetTestApp + DiffScreen | FileChange injection |
| 8 | Item 5 (large file gate) | DiffScreen | FileChange injection |
| 9 | Item 6 (hint + switcher) | ChatApp + mock_sdk | mock_sdk only |

---

## Cross-Cutting Constraints

1. **ASCII only** -- no new emoji/unicode beyond what exists (existing circle/branch symbols OK)
2. **`encoding='utf-8'`** on ALL file I/O
3. **`can_focus = False`** on all sidebar buttons and footer labels
4. **Message-based seams only** -- widgets post Messages, ChatApp handles
5. **pathlib.Path everywhere** -- no string concatenation with `/`
6. **Test at 80x24, 110x40, 160x50** terminal sizes
7. **Windows safe** -- use `platform` module not subprocess for system info, guard any process-related calls

---

## Risks and Mitigations (from Skeptic)

| Risk | Mitigation |
|------|------------|
| Footer overflow at 80 cols | "sys" is only 3 chars + separator = 5 cols added |
| Sidebar buttons invisible < 110 width | First-run hint toast + Agent Switcher (Item 6) |
| Compact threshold change breaks layout | Add ChicsessionLabel to height budget, test at multiple sizes |
| Markdown preview freezes on large files | 50KB size gate |
| Click handlers steal focus | `can_focus = False` on all new clickable widgets |
| Windows emoji rendering | ASCII only for new elements |
