# User Prompt -- audit_workflow

## Original Request

GitHub Issue #29: feat: add audit workflow for reviewing agent-human interaction quality

## User Refinements

- Output must include actionable suggestions for changes to:
  - Workflow phase markdown files
  - Advance checks
  - Rules (guardrails)
  - Hints
- Parsing must be updated to understand:
  - Chicsessions (`.chicsessions/{name}.json` -- multi-agent snapshots with workflow state)
  - Session JSONL (user messages, assistant responses, tool uses, compaction summaries)
- Cross-reference against current workflow manifests to scope suggestions to the right phase/workflow

## Source Issue

https://github.com/sprustonlab/AI_PROJECT_TEMPLATE/issues/29
