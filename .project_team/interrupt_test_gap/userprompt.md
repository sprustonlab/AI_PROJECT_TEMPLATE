# User Prompt

Investigate why interrupt_agent tests pass while the feature is broken in the TUI (issue #32). Two observed failures:
1. interrupt_agent does not stop a busy agent -- agent ignores interrupt and continues
2. interrupt_agent on a busy agent produces "invalid state transition" error

The original implementation was signed off with 724 passing tests and 0 regressions. This is a testing gap investigation.
