# User Prompt

Investigate GitHub issue #37: Sub-agent phase markdown not injected -- coordinator
bypasses role phase files.

Sub-agents spawned during workflow phases don't receive their role-specific phase
instructions (identity.md + {phase}.md). The coordinator sends something, but not
the actual phase files. Additionally, there is no automated way to inject updated
context to sub-agents during phase transitions.

Also: prevent coordinator from closing agents when it shouldn't.

The team should investigate what's actually happening and propose fixes at whichever
layer makes sense (guardrails, claudechic, workflow, or hybrid).
