# claudechic_ui_upgrade — STATUS

## Phase: Complete
## Working Directory: /Users/moharb/Documents/Repos/AI_PROJECT_TEMPLATE
## Target: submodules/claudechic/

## Work Items

| # | Item | Owner | Status |
|---|------|-------|--------|
| 1 | Bottom bar computer_info button | AI agent | DONE |
| 2 | Issue #9 — restore workflow/phase display | AI agent | DONE |
| 3 | Issue #4 — agent sidebar overflow | AI agent | DONE |
| 4 | ChicsessionLabel action buttons | AI agent | DONE |
| 5 | FilesSection /diff button + MD preview | AI agent | DONE |
| 6 | Agent switcher + hints (team-sourced ideas) | AI agent | DONE |

## Extra Work Completed

| Item | Description |
|------|-------------|
| FilesSection visibility fix | `#agent-scroll` and `#files-scroll` had default Textual `height: 1fr`, causing AgentSection to fill the entire sidebar and push FilesSection off-screen (y=43 on a 40-line terminal). Fixed with `height: auto` on both scroll containers. |
| Files header row | Title ("Files") and /diff button now share one `Horizontal` row instead of stacking vertically. `FILES_OVERHEAD` updated from 5 to 4 in `_layout_sidebar_contents`. |
| chicsession_overhead fix | `_layout_sidebar_contents` used hardcoded `CHICSESSION_OVERHEAD = 3` but ChicsessionLabel is 5 lines when a workflow is active. Made dynamic: `3 + (2 if self._workflow_engine else 0)`. |
| FilesSection VerticalScroll | Added `VerticalScroll(id="files-scroll")` to FilesSection so file items scroll rather than overflow. |
| Rich bracket escaping | `\[Preview]` / `\[Diff]` labels in PreviewToggle use raw strings to prevent Rich from consuming `[Preview]` as an unknown markup tag (renders as empty string). |
| get_file_stats cwd wiring | `_async_refresh_files` passes `agent.cwd` (= `Path.cwd()` at launch) to `get_file_stats`. Confirmed returns 6 files from parent repo. |

## Key Files Modified

- `claudechic/widgets/layout/sidebar.py` — FilesSection (VerticalScroll, header row, CSS), AgentSection (height:auto), FilesSection CSS visibility
- `claudechic/app.py` — `_async_refresh_files`, `_position_right_sidebar`, `_layout_sidebar_contents` (dynamic chicsession_overhead, FILES_OVERHEAD=4)
- `claudechic/widgets/content/markdown_preview.py` — PreviewToggle bracket escaping, MarkdownPreviewModal
- `claudechic/screens/chat.py` — sidebar compose order (ChicsessionLabel, AgentSection, PlanSection, FilesSection, TodoPanel, ReviewPanel, ProcessPanel)
- `tests/test_widgets.py` — three new FilesSection tests

## Tests Added

| Test | What it catches |
|------|-----------------|
| `test_files_section_scrolls_with_many_files` | FilesSection must contain `VerticalScroll#files-scroll`; 20 items all queryable |
| `test_files_section_visible_with_workflow_active` | At H=29 with workflow active + 4 agents + 5 files, agents must compact (overhead=5 not 3) |
| `test_files_section_renders_with_files` | FilesSection `y < 40` in sidebar-like layout — catches the `height:1fr` regression that pushed FilesSection off-screen |

## Git State
- Parent repo: develop branch, uncommitted changes
- Submodule (claudechic): develop branch, uncommitted changes

## Key Files (original)
- Footer: `claudechic/widgets/layout/footer.py`
- Sidebar: `claudechic/widgets/layout/sidebar.py`
- Indicators: `claudechic/widgets/layout/indicators.py`
- Chicsession screen: `claudechic/screens/chicsession.py`
- Chicsession manager: `claudechic/chicsessions.py`
- Diff system: `claudechic/features/diff/`, `claudechic/screens/diff.py`
- Diagnostics modal: `claudechic/widgets/modals/diagnostics.py`
- Styles: `claudechic/styles.tcss`
- Main app: `claudechic/app.py`
