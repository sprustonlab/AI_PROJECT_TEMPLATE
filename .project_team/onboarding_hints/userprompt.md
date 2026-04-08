# User Request

I want to have useful hints for users as they start interacting with ClaudeChic, one example is check if we are a git repo and advising to launch the Git agent if we are not — this will use the Textual's toast notification system. We need a way to have triggers and messages. I want to think about onboarding as a skill which you can turn off. I want to think about how users discover features like the pattern mining.

## Context
- This is for the **AI_PROJECT_TEMPLATE** repo (not claudechic itself)
- The template scaffolds projects with: guardrails, project team, pattern miner, MCP tools, cluster support
- ClaudeChic is the TUI used within generated projects
- Toast notifications via Textual's `self.notify()` system

## Vision Summary
**Goal:** Build a contextual onboarding & feature discovery system for AI_PROJECT_TEMPLATE projects that surfaces helpful hints via ClaudeChic's toast notifications.

**Value:** Bridge the gap between template installation and feature mastery.

**Key features to surface:**
| Feature | Example Trigger | Example Hint |
|---------|----------------|-------------|
| Git setup | No `.git` directory | "No git repo detected — spawn a Git agent to set one up" |
| Guardrails | Only default rule | "Your guardrails only have the default rule" |
| Project Team | Never used `/ao_project_team` | "Try `/ao_project_team` for multi-agent workflows" |
| Pattern Miner | 10+ sessions, miner never run | "Run the pattern miner to find recurring corrections" |
| MCP Tools | `mcp_tools/` is empty | "Drop Python files into `mcp_tools/` for custom tools" |
| Cluster | Configured but unused | "Your cluster backend is ready" |

**Success:** 1-2 toasts/session, declarative registry, toggleable skill, easy to extend.
