# Build the Workflow Guidance System

Write the architecture specification for the Workflow Guidance System — infrastructure in claudechic that lets workflows define phases, guardrail rules, checks, and hints via YAML manifests and markdown files. The project-team build is the first workflow.

## Vision

Extend claudechic to offer a unified guidance system — advisory and enforced, positive and negative — where any workflow is just YAML config + markdown content. Users write manifests and agent folders. Claudechic provides the engine, the loader, the checks, and the hooks. One combined system, one set of primitives, any workflow type.

## Why

- Guidance is currently scattered across multiple systems, formats, and locations. Rules, checks, and hints each have their own mechanism.
- Users shouldn't need to learn three separate systems. A single pattern — YAML manifests + markdown content in `workflows/` — makes guidance easy to author, understand, and maintain.
- The 2x2 framing (advisory/enforced x positive/negative) gives users a clear mental model for where any piece of guidance fits and how it behaves.

---

## The 2x2 Guidance Framing

All guidance fits a 2x2 of **Positive/Negative** x **Advisory/Enforced**:

|  | Advisory (agent can bypass) | Enforced (agent cannot bypass) |
|---|---|---|
| **Positive** (do this) | **A:** Do's in markdown — phase instructions, best practices | **C:** Checkpoints — engine verifies work is done |
| **Negative** (don't do this) | **B:** Don'ts in markdown + `warn`/`log` rules | **D:** Guardrails — `deny` and `user_confirm` rules block actions via SDK hooks |

The boundary is **bypassability**: `warn` and `log` are advisory (B) even though they use SDK hook infrastructure. Only `deny` and `user_confirm` are enforced (D). All four quadrants evolve across phases.

---

## Directory structure

Everything lives under `workflows/` at the project root:

```
workflows/
  global.yaml                        # Global manifest: rules, checks, hints (always active, no phases)
  project_team/
    project_team.yaml                # Manifest: rules, phases, checks, hints
    state.json                       # Runtime phase state
    coordinator/                     # Agent folder — folder name = role type
      identity.md                    # Cross-phase identity (always loaded)
      vision.md                      # Phase-specific (loaded during vision phase)
      setup.md
      specification.md
      implementation.md
      testing.md
      signoff.md
    composability/
      identity.md
      specification.md
    skeptic/
      identity.md
      specification.md
    implementer/
      identity.md
      implementation.md
      testing.md
```

Folder name = identity everywhere: manifest filename, state.json location, rule ID namespace.

---

## Agent folders

Each agent has a folder inside its workflow directory. The folder name IS the agent's role type — used in `block_roles`/`allow_roles` in rules and passed to SDK hook closures at spawn time.

Each folder contains `identity.md` (cross-phase, always loaded) and per-phase markdown files (loaded only during that phase). Agent prompt = identity + current phase file. All markdown is pure advisory content.

---

## Manifests

Rules, checks, and hints are YAML sections in manifest files. `global.yaml` has rules/checks/hints that are always active. Each workflow manifest has rules, phases, checks, and hints scoped to that workflow.

Example workflow manifest:

```yaml
# workflows/project_team/project_team.yaml
workflow_id: project-team

rules:
  - id: pip_block
    trigger: PreToolUse/Bash
    enforcement: deny
    detect: { pattern: '\bpip\s+install\b', field: command }
    message: "Use pixi, not pip."

  - id: pytest_output
    trigger: PreToolUse/Bash
    enforcement: deny
    phase_block: ["project-team:testing"]
    detect: { pattern: '(?:^|&&|\|\||;|\brun\s+)\s*pytest\b', field: command }
    message: "Redirect pytest output to .test_runs/"

  - id: close_agent
    trigger: PreToolUse/mcp__chic__close_agent
    enforcement: user_confirm
    phase_allow: ["project-team:specification"]
    block_roles: [implementer]
    message: "Close agent during specification — user approval required."

phases:
  - id: vision
    file: coordinator/vision.md
  - id: setup
    file: coordinator/setup.md
  - id: specification
    file: coordinator/specification.md
  - id: implementation
    file: coordinator/implementation.md
    advance_checks:
      - type: manual-confirm
        question: "Are all implementation tasks complete?"
    hints:
      - message: "Focus on writing code, not running the full test suite"
        lifecycle: show-once
  - id: testing
    file: coordinator/testing.md
    advance_checks:
      - type: command-output-check
        command: "pixi run pytest --tb=short 2>&1 | tail -1"
        pattern: "passed"
  - id: signoff
    file: coordinator/signoff.md
```

Example global manifest with setup checks:

```yaml
# workflows/global.yaml
rules:
  - id: pip_block
    trigger: PreToolUse/Bash
    enforcement: deny
    detect: { pattern: '\bpip\s+install\b', field: command }
    message: "Use pixi, not pip."

checks:
  - id: github_auth
    type: command-output-check
    command: "git ls-remote https://github.com/sprustonlab/claudechic.git HEAD 2>&1 | head -1"
    pattern: "[0-9a-f]{40}"
    on_failure:
      message: "GitHub authentication failed. Run: gh auth login"
      severity: warning
      lifecycle: show-until-resolved

  - id: cluster_ssh
    type: command-output-check
    when: { copier: use_cluster }
    command: "ssh -o ConnectTimeout=5 -o BatchMode=yes ${cluster_ssh_target} hostname 2>&1"
    pattern: "^[a-zA-Z]"
    on_failure:
      message: "Cannot SSH to cluster. Run: ssh-copy-id ${cluster_ssh_target}"
      severity: warning
      lifecycle: show-until-resolved
```

A unified loader reads all manifests and distributes each section to a typed parser (`ManifestSection[T]`). Three parsers: rules, checks, hints. Adding a new section type means adding a parser — the loader doesn't change. The loader has two modes: full load (startup, phase transitions) and rules-only load (every tool call).

---

## Namespace convention

Every ID is `namespace:name` at runtime. Global = `_global:pip_block`. Workflow = `project_team:close_agent`. IDs in YAML are bare — the loader prefixes automatically.

Phase references in `phase_block`/`phase_allow` use qualified IDs: `"project-team:testing"`. The loader validates these against known phases at startup.

---

## Checks

Checks verify system state and return pass/fail with evidence. The engine runs checks, not the agent. The protocol is async. Four built-in types:

| Type | Passes when |
|---|---|
| `CommandOutputCheck(command, pattern)` | stdout matches regex |
| `FileExistsCheck(path)` | File exists |
| `FileContentCheck(path, pattern)` | File content matches regex |
| `ManualConfirm(question)` | User answers affirmatively |

`ManualConfirm` is system-level — the engine prompts the user directly via `SelectionPrompt` in the TUI. The engine receives a confirmation callback at construction, not an app reference.

Checks are independent of phases — usable standalone. `advance_checks` in manifests have AND semantics with short-circuit on first failure. A `CheckFailed` adapter bridges checks to the existing hints pipeline, so failing setup checks fire as hints at startup.

Setup checks in `global.yaml` test outcomes (can you authenticate? is pixi healthy?) with `on_failure` hints that show until resolved. The `when` clause supports copier-answer conditions.

---

## SDK hooks and enforcement

claudechic is required. All guardrail hooks are SDK hook closures — one per agent with the role type captured at creation time. Rules are loaded fresh on every tool call (no mtime caching). Evaluation: match trigger → check role skip → check phase skip → match pattern → apply enforcement.

| Level | Who decides | Bypassable? | 2x2 quadrant |
|---|---|---|---|
| `deny` | System | No | D (enforced) |
| `user_confirm` | User via TUI | No | D (enforced) |
| `warn` | Agent acknowledges | Yes | B (advisory) |
| `log` | Silent | N/A | B (advisory) |

Don't use `warn` on any rules yet — it has an infinite-loop risk (agent retries after acknowledging).

Failure modes: `workflows/` unreadable → fail closed (block everything). Individual manifest malformed or bad regex → fail open (skip it, load the rest). Startup validation catches duplicate IDs, invalid regexes, unknown phase references.

---

## Hints and content delivery

Phase hints are declared under phase entries in manifests — scoping is structural. Global hints go in `global.yaml`. The engine converts hint declarations to `HintSpec` objects via the existing `run_pipeline()`.

Content delivery is pull-based. The engine does not inject content mid-session. The agent reads state.json and loads its current phase file. A `PostCompact` SDK hook re-injects phase context after `/compact`.

---

## Constraints

- All infrastructure code lives in claudechic. The template provides only YAML and markdown in `workflows/`.
- No env var overrides for state paths. Tests use a temp project root.
- `state.json` written atomically (temp file + rename). No mtime caching — NFS is unreliable on HPC clusters.
- Always use qualified phase IDs in `phase_block`/`phase_allow` (`"project-team:testing"`, not bare `"testing"`).

---

## What exists in the codebase

Build on these in `submodules/claudechic/claudechic/`:

- `guardrails/rules.py` — rule loading and matching
- `guardrails/hits.py` — hit logging
- `app.py` — hook closures and `SelectionPrompt` confirmation
- `hints/` — trigger conditions, hint lifecycle, pipeline, project state

---

## Scope

Build:
- Unified manifest loader with typed section parsers
- Workflow engine (phase transitions, gates, state persistence)
- Check protocol with 4 built-in types and hints adapter
- Agent folder structure and prompt assembly
- `workflows/global.yaml` with setup checks
- COORDINATOR.md content split into agent folder
- `/compact` recovery hook
- Phase-scoped guardrail evaluation

Don't build:
- CompoundCheck (OR semantics)
- Content focus guards (phase-aware read guards)
- Multi-workflow (multiple active simultaneously)
- `ShowUntilPhaseComplete` hint lifecycle

---

## Examples for the spec

Include: full `project_team.yaml` manifest, `global.yaml` with setup checks, phase transition walkthrough, phase-scoped rule evaluation, hook closure code, manifest discovery, phase reference validation.
