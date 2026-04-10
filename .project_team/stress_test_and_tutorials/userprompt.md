# User Request

Stress test the AI Project Template repo and its parts to find bugs and bad design choices that limit what we can accomplish. The Copier template has not been updated since infrastructure was moved to claudechic — it needs updating.

Produce four deliverables:

1. **Stress test + fixes** — find bugs, fix the stale Copier template, surface design flaws
2. **Getting Started Guide** (`docs/`) — reference for agents and humans on how to use this system
3. **Tutorial Workflow: "Extending the System"** — runnable workflow teaching how to add new things:
   - Add a new rule
   - Add a new checkpoint
   - Edit an MD agent file for the project team
   - Edit YAML configuration
   *(An existing tutorial covers how existing ones are used — this teaches how to create more)*
4. **Tutorial Workflow: "Toy Project with Agent Team"** — runnable workflow with a pre-selected vision/goal that walks the user through a full multi-agent project from start to finish

---

# Vision Summary

**Goal:** Stress test and fix the AI Project Template, then produce a getting-started guide and two runnable tutorial workflows — one for extending the system, one for running a full agent team project.

**Value:** The template is stale (claudechic move), and there's no guided path for users who want to customize or extend the system. These deliverables close both gaps.

**Domain Terms:**
- **Copier template** — the `template/` dir + `copier.yml` that scaffolds new projects
- **claudechic** — the CLI/TUI wrapper and MCP tool infrastructure
- **Project team** — the multi-agent workflow (Coordinator, Implementer, Skeptic, etc.)
- **Guardrails** — permission system (rules.yaml → generated hooks)
- **Hints** — onboarding hint engine (`hints/`)
- **Workflows / Phases** — the phase-gated workflow system in `workflows/`

**Success looks like:**
- Template (`copier copy`) produces a working project that matches current codebase reality
- A new user (human or agent) can follow the getting-started guide and be productive within one session
- Both tutorial workflows run end-to-end with no unexplained errors
- "Extending" tutorial leaves the user with real new rules/checkpoints they created
- "Toy Project" tutorial produces a complete mini-project built by the agent team

**Failure looks like:**
- Docs describe how things *used to work* instead of how they work now
- Tutorials break mid-way or assume knowledge the reader doesn't have
- Stress test is shallow — only tests the happy path
- Template stays out of sync with claudechic
