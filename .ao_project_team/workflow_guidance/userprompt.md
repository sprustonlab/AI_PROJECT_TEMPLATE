# User Prompt — Workflow Guidance System

## Original Request
Write the architecture specification for the Workflow Guidance System. The user prompt is in `.ao_project_team/workflow_guidance/USER_PROMPT.md` — a detailed spec evolved from the tutorial_system project team session.

## Detailed Prompt
See: `/groups/spruston/home/moharb/AI_PROJECT_TEMPLATE/.ao_project_team/workflow_guidance/USER_PROMPT.md`

## Vision Summary (Approved)
**Goal:** Write the architecture specification for a Workflow Guidance System — infrastructure in claudechic that lets workflows define phases, guardrail rules, checks, and hints via YAML manifests and markdown files.

**Value:** Unifies currently scattered guidance (rules, checks, hints) into one system — YAML manifests + markdown content in `workflows/`. Users get a single pattern and a clear 2x2 mental model (advisory/enforced x positive/negative).

**Domain terms:** Manifests, phases, checks, hints, guardrails, SDK hooks, agent folders, ManifestSection protocol, 2x2 guidance framing, enforcement levels (deny/user_confirm/warn/log)

**Success looks like:** A complete architecture specification that a team can implement — covering the unified manifest loader, workflow engine, check protocol, agent folders, phase-scoped evaluation, and `/compact` recovery. The project-team workflow is the first workflow built on it.

**Failure looks like:** A spec that's too vague to implement, misses the interaction between subsystems (e.g., how checks bridge to hints, how phase transitions gate on checks), or fails to identify which existing claudechic code needs to change and how (refactors, new modules, modified interfaces).
