# User Prompt — claudechic UI Upgrade

Upgrade claudechic's look and usability:

1. **Bottom bar `computer_info` button** — clickable label (like session_info) showing hostname, OS, SDK version. Opens a ComputerInfoModal. Team should suggest additional items.

2. **Issue #9 — Session restore workflow/phase display** — ChicsessionLabel doesn't populate workflow_text/phase_text on load from .chicsessions/*.json. Data is in workflow_state, just needs wiring.

3. **Issue #4 — Agent sidebar overflow** — Compact mode triggers too late with 11+ agents. Lower threshold and/or add scrolling.

4. **ChicsessionLabel always-visible action buttons** — Add /workflow, /chicsession restore buttons so new users discover them without knowing slash commands. UIDesigner should propose layout.

5. **FilesSection /diff button + Markdown preview** — Clickable /diff trigger in FilesSection header. Rendered Markdown display for .md files (spec files).

6. **Team-sourced ideas** — Leadership agents propose additional enhancements.
