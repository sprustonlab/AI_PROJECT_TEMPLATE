# Multi-Agent Project Team

A structured multi-agent workflow for building software projects with Claude Code. Launch it by running `/ao_project_team` in claudechic.

**See [COORDINATOR.md](COORDINATOR.md) for the full orchestration logic.**

## Workflow

### 1. Vision (1 agent)

You describe what you want to build. The agent clarifies your intent — spelling out what success and failure look like — and iterates with you until it's correct and complete. You're also asked where the project lives (new or existing directory).

The agent creates `.ao_project_team/{project_name}/` with:
- `userprompt.md` — your verbatim prompt + the approved vision
- `STATUS.md` — tracks workflow progress

**User checkpoint:** approve the vision before work proceeds.

### 2. Specification (4 leadership agents)

The Coordinator's prime directive is **"Delegate, don't do."** It spawns leadership agents that draft a specification together, saved under `.ao_project_team/{project_name}/specification/`.

**User checkpoint:** approve the specification before implementation begins.

**Tips:**
- The coordinator should spawn one Composability agent per identified axis. If it doesn't, say: *"Start a fresh review with new agents, this time make sure to start one composability agent per identified axis."*
- Repeat reviews until no major issues remain. You can also read the specs yourself.
- Request fresh reviews if you feel the current agents have tunnel vision.

### 3. Implementation (leadership + implementers)

Implementer agents write code directly in the project, guided by leadership agents.

**Tips:**
- One implementer per file works well.
- If only one implementer is spawned, say: *"Spawn a sufficient amount of claudechic implementer agents."*
- If leadership isn't actively guiding, say: *"Remember to inform the leadership agents that implementation has started and that it is their role to guide the implementers."*

### 4. Testing

Tests are written and run. Leadership does a final review and signs off.

**User checkpoint:** optionally request end-to-end tests. By default, agents write "smoke" tests with short runtimes. E2E tests run full real-world use cases but aren't always reliable — sometimes it's faster to run them yourself.

---

## Agent Roster

### Leadership

| Agent | File | Role |
|-------|------|------|
| **Coordinator** | `COORDINATOR.md` | Orchestrates the workflow. Delegates, doesn't implement. |
| **Composability** | `COMPOSABILITY.md` | Dissects problems into independent axes with defined seams. The most important leadership agent. |
| **Terminology Guardian** | `TERMINOLOGY_GUARDIAN.md` | Ensures consistent naming across components. |
| **Skeptic** | `SKEPTIC.md` | Checks for completeness and minimality. Correctness through simplicity. |
| **User Alignment** | `USER_ALIGNMENT.md` | Protects user intent. Has veto power — cannot remove user-requested features. |

### Implementation

| Agent | File | Role |
|-------|------|------|
| **Implementer** | `IMPLEMENTER.md` | Writes the code. Multiple instances spawned (one per file works well). |
| **Test Engineer** | `TEST_ENGINEER.md` | Writes tests and CI configuration. |
| **UI Designer** | `UI_DESIGNER.md` | Interface design (spawned when applicable). |

### Advisory (spawned when applicable)

| Agent | File | Role |
|-------|------|------|
| **Researcher** | `RESEARCHER.md` | Investigates technical questions, surveys approaches. |
| **Binary Portability** | `BINARY_PORTABILITY.md` | Cross-language/platform compatibility. |
| **Sync Coordinator** | `SYNC_COORDINATOR.md` | Concurrency correctness (only for concurrent systems). |
| **Memory Layout** | `MEMORY_LAYOUT.md` | Data structure and memory optimization. |
| **Lab Notebook** | `LAB_NOTEBOOK.md` | Documents experiments and decisions. |
| **Project Integrator** | `PROJECT_INTEGRATOR.md` | Integration with existing project infrastructure. |

---

## Key Rules

1. **Git Setup runs first** — always save `userprompt.md` before coding begins
2. **User Alignment has veto** — cannot remove user-requested features
3. **Skeptic ensures correctness** — complete, simple, verifiable; no shortcuts
4. **Composability drives architecture** — independent axes, defined seams, no hidden coupling
5. **Advisory agents are non-blocking** — spawned only when relevant, don't hold up the workflow
