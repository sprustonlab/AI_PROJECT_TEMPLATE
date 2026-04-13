# User Prompt

Add an `interrupt_agent` MCP tool for inter-agent interruption (GitHub Issue #10).

## Requirements (from issue)
1. Calls the existing `agent.interrupt()` method (SDK interrupt + SIGINT fallback)
2. Optionally accepts a follow-up message/prompt to queue after the interrupt
3. Returns confirmation that the interrupt was delivered
4. If `message` is provided, it's queued as the next prompt (agent resumes with new instructions)
5. If no `message`, agent simply stops and becomes idle

## Existing Infrastructure
- `agent.interrupt()` in `agent.py` -- handles SDK interrupt, SIGINT fallback, task cancellation
- `client.interrupt()` in the SDK -- non-blocking interrupt support
- Escape key handler in `app.py` already orchestrates this flow
- `tell_agent` and `close_agent` MCP tools already exist as patterns to follow
