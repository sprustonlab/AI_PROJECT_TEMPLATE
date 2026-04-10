# Terminology — Stress Test & Tutorials Project

> **Canonical home** for all domain terms used in this project.
> Other documents MUST reference this file, not redefine terms.

---

## Core Infrastructure

### AI_PROJECT_TEMPLATE
The top-level repository that houses all infrastructure: the Copier template, claudechic submodule, agent definitions, workflows, hints, guardrails, and commands. This is the **source of truth**; the Copier template scaffolds copies of it.

### claudechic
The CLI/TUI wrapper and MCP tool infrastructure that powers Claude Code integration. Lives in the `claudechic/` directory (as a submodule or installed dependency). Provides the `chic` MCP tools (`spawn_agent`, `tell_agent`, `ask_agent`, `advance_phase`, etc.) that agents use to communicate and coordinate.
- **Do NOT call it:** "chic", "the wrapper", "the MCP server" (ambiguous)
- **Canonical name:** `claudechic`

### Copier template
The scaffolding system defined by `copier.yml` + the `template/` directory. Running `copier copy` generates a new project from this template. Users answer prompts (project name, which features to enable) and get a ready-to-use project.
- **Do NOT call it:** "the template" (ambiguous — could mean any template file), "scaffold"
- **Canonical name:** "Copier template" (when referring to the system) or "`template/` directory" (when referring to the files)

---

## Agent System

### Project Team
The multi-agent workflow system defined by agent role files in `AI_agents/project_team/`. A structured team of specialized agents that collaborate on projects through phase-gated workflows.
- **Do NOT call it:** "the agents", "agent team", "multi-agent system" (too generic)
- **Canonical name:** "Project Team"

### Agent Role
A markdown file in `AI_agents/project_team/` (e.g., `COORDINATOR.md`, `IMPLEMENTER.md`) that defines a single agent's responsibilities, communication rules, and behavioral constraints.
- **Do NOT call it:** "agent file", "role file", "persona"
- **Canonical name:** "agent role" (the concept) or "agent role file" (the `.md` file)

### Coordinator
The lead agent in the Project Team workflow. Delegates work to other agents, never writes code directly. Defined in `COORDINATOR.md`.

### Implementer
Agent responsible for writing and modifying code. Receives tasks from Coordinator. Defined in `IMPLEMENTER.md`.

### Skeptic
Agent responsible for critical review — finding flaws, risks, and gaps. Defined in `SKEPTIC.md`.

### Composability (agent)
Agent responsible for architecture — ensuring the system remains modular and extensible. Defined in `COMPOSABILITY.md`.

### Terminology Guardian
Agent (assistant to Composability) responsible for naming consistency and documentation clarity. Defined in `TERMINOLOGY_GUARDIAN.md`. *(That's me.)*

### User Alignment
Agent responsible for ensuring deliverables match what the user actually wants. Defined in `USER_ALIGNMENT.md`.

---

## Workflow System

### Workflow
A phase-gated process defined by a YAML file in `workflows/`. Specifies an ordered sequence of phases, rules, hints, and the main agent role. Example: `workflows/project_team/project_team.yaml`.
- **Do NOT call it:** "pipeline", "process", "flow"
- **Canonical name:** "workflow"

### Phase
A named stage within a workflow (e.g., `vision`, `setup`, `leadership`, `specification`, `implementation`, `testing`, `signoff`). Phases advance sequentially. Each phase may have advance checks and hints.
- **Do NOT call it:** "step", "stage", "state"
- **Canonical name:** "phase"

### Advance Check
A gate condition that must be satisfied before a workflow can move from one phase to the next. Defined in the workflow YAML under `advance_checks`. Types include `manual-confirm` (requires user approval).
- **Do NOT call it:** "gate", "checkpoint" (reserved — see below), "approval"
- **Canonical name:** "advance check"

### Phase File
A markdown file in `workflows/<workflow_name>/<role>/` that contains the instructions for what an agent should do during a specific phase.

---

## Guardrails System

### Guardrails
The permission and safety system that controls what Claude Code tool calls are allowed. Rules are defined in YAML; hooks are auto-generated. Operates at three enforcement levels.
- **Do NOT call it:** "permissions", "safety system", "access control"
- **Canonical name:** "guardrails"

### Rule (guardrail)
A single guardrail entry in `rules.yaml` (global) or in a workflow YAML's `rules:` section. Each rule has: `id`, `trigger`, `enforcement`, `detect` (pattern), and `message`.
- **Do NOT call it:** "policy", "permission", "hook" (hooks are generated FROM rules)
- **Canonical name:** "rule"

### Enforcement Level
How a rule responds when triggered:
- **`deny`** — blocks the action entirely
- **`warn`** — allows but shows a warning; agent must acknowledge
- **`log`** — silently logs for audit trail

### Hook (generated)
A Claude Code hook (in `.claude/settings.json`) auto-generated from guardrail rules by `generate_hooks.py`. Hooks are the *mechanism*; rules are the *policy*.
- **Do NOT confuse with:** "rule" (the source definition)
- **Canonical name:** "hook" or "generated hook"

### rules.yaml
The YAML file where guardrail rules are defined. Exists at two levels:
- **Global:** `global/rules.yaml` — applies to all workflows
- **Workflow-level:** embedded in workflow YAML under `rules:` — applies only during that workflow

---

## Hints System

### Hints
The onboarding hint engine that shows contextual toast notifications to help users discover features. Code lives in `hints/`; configuration in `global/hints.yaml` and per-workflow YAML.
- **Do NOT call it:** "tips", "notifications", "messages" (too generic)
- **Canonical name:** "hints"

### Hint Lifecycle
How often a hint is shown:
- **`show-once`** — shown one time, then never again
- **`show-every-session`** — shown at the start of each session

---

## Commands & Skills

### Command (slash command)
A Claude Code slash command defined as a markdown file in `commands/`. Invoked by the user as `/<command-name>`. Example: `/mine-patterns`.
- **Do NOT call it:** "skill" (different mechanism), "action"
- **Canonical name:** "command" or "slash command"

---

## Project Structure Directories

| Directory | Contains |
|-----------|----------|
| `AI_agents/project_team/` | Agent role files (`.md`) |
| `claudechic/` | claudechic submodule/dependency |
| `commands/` | Slash command definitions |
| `global/` | Global configuration (`rules.yaml`, `hints.yaml`) |
| `hints/` | Hint engine Python code |
| `template/` | Copier template source files (`.jinja` suffixed) |
| `workflows/` | Workflow definitions and phase files |
| `.ao_project_team/` | Runtime state for active Project Team sessions |
| `repos/` | User's integrated codebases |
| `scripts/` | Utility scripts (e.g., `integrate_codebase.py`) |
| `envs/` | Environment/dependency configurations |
| `submodules/` | Git submodules (claudechic in developer mode) |

---

## MCP Tools (claudechic-provided)

These are the inter-agent communication primitives provided by claudechic:

| Tool | Purpose |
|------|---------|
| `spawn_agent` | Create a new agent instance |
| `ask_agent` | Send a message and wait for a response (guaranteed reply) |
| `tell_agent` | Fire-and-forget message (no response expected) |
| `advance_phase` | Move the workflow to the next phase |
| `get_phase` | Query the current workflow phase |
| `spawn_worktree` | Create an isolated git worktree for an agent |

---

## Deliverable-Specific Terms

### Stress Test
Systematic exercise of all AI_PROJECT_TEMPLATE components to surface bugs, stale references, and design flaws. NOT a performance/load test.
- **Scope:** Copier template generation, guardrail generation, workflow execution, hint display, command invocation, agent communication

### Getting Started Guide
A reference document in `docs/` aimed at both humans and agents. Explains how to use the AI_PROJECT_TEMPLATE system from scratch.
- **Do NOT call it:** "README" (that's a different file), "manual", "documentation" (too broad)
- **Canonical name:** "Getting Started Guide"

### Tutorial Workflow
A runnable workflow (defined in `workflows/tutorial/`) that guides a user step-by-step. Two will be created:
1. **"Extending the System"** — teaches how to add new rules, checkpoints, agent roles, and YAML configuration
2. **"Toy Project with Agent Team"** — walks through a complete multi-agent project from start to finish

- **Do NOT call it:** "tutorial" alone (ambiguous — could mean the guide), "lesson", "walkthrough"
- **Canonical name:** "tutorial workflow"

---

## Potential Terminology Conflicts (Flagged)

### "checkpoint" vs "advance check"
The user prompt mentions "Add a new checkpoint." The workflow YAML uses `advance_checks`. These likely refer to the same concept.
→ **Recommendation:** Use **"advance check"** consistently (matches the YAML key). If "checkpoint" is kept for user-facing simplicity, define it explicitly as a synonym.

### "rule" (guardrail) vs "rule" (workflow)
Rules appear in both `global/rules.yaml` (guardrails) and inside workflow YAML `rules:` sections. They are the same mechanism but scoped differently.
→ **Recommendation:** Always qualify: "global rule" vs "workflow rule" when context is ambiguous.

### "template" (Copier) vs "template" (Jinja file)
"Template" could mean the Copier template system OR an individual `.jinja` file inside `template/`.
→ **Recommendation:** Use "Copier template" for the system, "template file" or "Jinja template" for individual files.
