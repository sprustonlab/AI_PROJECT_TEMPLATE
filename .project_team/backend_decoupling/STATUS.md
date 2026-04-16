# Project: backend_decoupling
# Phase: setup
# Status: initializing

## Vision (Approved)

| | |
|---|---|
| **Goal** | Explore and design approaches to decouple the claudechic workflow engine from the Claude Code API, enabling it to run on alternative AI backends. |
| **Value** | Extends the audience beyond Claude Code users, making the workflow/phase system available to the broader AI-assisted development community. |
| **Domain Terms** | **claudechic** — the workflow/phase orchestration system; **backend** — the AI agent runtime (currently Claude Code); **MCP tools** — the interface layer for agent spawning, phase management, etc. |
| **Success looks like** | A clear understanding of coupling points, a set of viable decoupling strategies ranked by effort/impact, and a prototype or architecture plan for at least one alternative backend. |
| **Failure looks like** | A vague report with no actionable paths forward, or a design that breaks existing Claude Code functionality without a clear migration story. |

## Team
- [ ] Leadership agents (not yet spawned)
- [ ] Researcher (key role — requested by user)

## Notes
- User emphasized Researcher agent will be important
- Focus on identifying coupling points between claudechic and Claude Code
- Explore alternative AI coding assistants and direct LLM APIs
