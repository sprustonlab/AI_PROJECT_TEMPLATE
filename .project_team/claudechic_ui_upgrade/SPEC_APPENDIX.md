# SPEC APPENDIX: claudechic UI Upgrade

## Architecture Decision Rationale

### InfoModal Base Class
DiagnosticsModal and ComputerInfoModal share 90% structure. Extracting a base class
(`InfoModal`) with a frozen `InfoSection` dataclass keeps the seam clean: callers
provide data, InfoModal handles presentation. Future info modals become trivial.

DiagnosticsModal remains a subclass (it has data-resolution logic in __init__).
ComputerInfoModal can be a thin subclass or factory function.

### SidebarSection Header Actions
Rather than special-casing DiffButton in FilesSection, the pattern is generalized:
SidebarSection accepts optional `header_actions` list. Default is None, so existing
sections are unaffected. This is reusable for any section wanting header buttons.

### ChicsessionActions Descriptor Model
Actions use generic `(command_string, label)` pairs rather than hardcoded buttons.
This keeps ChicsessionLabel agnostic about what commands exist. New actions can be
added without modifying the widget.

### Message Seam Integrity
All widgets communicate via Textual Messages bubbling up to ChatApp. No widget
imports or calls methods on another widget. The one existing violation is
`ContextBar.on_click()` calling `self.app._handle_prompt("/context")` -- new widgets
should post Messages instead.

## Rejected Alternatives

### Merging DiagnosticsModal and ComputerInfoModal
Rejected: they serve different purposes (session diagnostics vs system info).
Merging would create a bloated modal.

### Inline Markdown preview in sidebar
Rejected: sidebar is 28 chars wide -- too narrow for readable Markdown.
Modal at 80% width is the correct UX.

### Adding computer_info as verbose text in footer
Rejected: footer is already ~80 chars. Verbose text would overflow on narrow
terminals. Short "sys" label + modal is the correct pattern.

### Ctrl+A for Agent Switcher keybinding
Rejected: conflicts with select-all in text input. Ctrl+G chosen instead.

### Adding emoji indicators for new elements
Rejected: CLAUDE.md mandates ASCII only for cross-platform safety.
Windows conhost.exe does not render emoji correctly.

## What NOT To Do

1. Do NOT merge footer labels -- each is independent, don't combine session_info + sys.
2. Do NOT use `os.uname()` -- not available on Windows. Use `platform` module.
3. Do NOT make sidebar buttons focusable -- `can_focus = False` prevents stealing
   focus from chat input.
4. Do NOT hardcode button labels in ChicsessionActions -- use the descriptor model.
5. Do NOT skip the 50KB size gate on MarkdownPreview -- large files will freeze the TUI.
6. Do NOT add scrolling to AgentSection without also updating `_layout_sidebar_contents()`
   height budget -- they must be coordinated.
7. Do NOT use bare "Session" for chicsession context -- always prefix with "Chicsession".

## Leadership Agent Reports Summary

### Composability
- 5 independent architectural axes identified (footer items, sidebar sections, modals,
  interactivity level, data sources)
- All items touch different zones -- no conflicts
- Recommended InfoModal base class, SidebarActionButton pattern, SectionAction header pattern
- Recommended order: 2 -> (1, 3, 5 parallel) -> 4 -> 6

### Terminology
- Naming conventions locked: XxxLabel (footer), XxxSection (sidebar), XxxModal (modals)
- Key conflict avoidance: "Chicsession" always one word, never bare "Session"
- DiffButton (not DiffLabel) -- it triggers navigation, not displays status

### Skeptic
- Footer already ~80 chars -- ComputerInfoLabel must be SHORT
- Sidebar only shows at >= 110 width -- discoverability paradox for new users
- Items 3 and 4 compete for sidebar vertical space
- Windows cross-platform concerns: no os.uname, use platform module
- Test at 80x24, 110x40, 160x50 terminal sizes

### UserAlignment
- Priority: bug fix (Item 2) first for trust, then discoverability (Item 4)
- Empty-state gap: new users with no sessions need guidance, not blank labels
- Action buttons should adapt based on workflow state
- Non-sidebar fallback needed (hints + Agent Switcher)
- Session Health dashboard and Agent Switcher proposed as enhancements
