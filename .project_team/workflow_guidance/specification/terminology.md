# Terminology — Workflow Guidance System

> **Canonical home for all domain terms.** Other specification files reference this document; they do not duplicate definitions.

---

## Core Concepts

### Workflow
A named configuration — YAML manifest + markdown content in a directory under `workflows/` — that defines phases, rules, checks, and hints for a particular use case. Example: `project_team`. Each workflow has a `workflow_id` (kebab-case, e.g. `project-team`) used in namespacing.

### Manifest
A YAML file declaring rules, phases, checks, and hints. Two kinds:
- **Global manifest** (`workflows/global.yaml`) — always active, no phases.
- **Workflow manifest** (`workflows/<name>/<name>.yaml`) — scoped to one workflow.

The filename matches the directory name (folder name = identity).

### Manifest Loader
The unified system that reads all manifest files, discovers them by directory convention, and distributes each YAML section to a typed parser. Two operational modes:
- **Full load** — at startup and phase transitions. Parses all sections.
- **Rules-only load** — on every tool call. Parses only the `rules:` section for performance.

### ManifestSection Protocol
A typed parser interface (`ManifestSection[T]`) that each section kind implements. Three built-in parsers: rules, checks, hints. Adding a new section type means adding a parser — the loader itself does not change.

---

## The 2×2 Guidance Framing

All guidance maps onto two axes: **valence** (positive/negative) × **bypassability** (advisory/enforced).

| | Advisory (agent can bypass) | Enforced (agent cannot bypass) |
|---|---|---|
| **Positive** (do this) | Quadrant A: do's in markdown | Quadrant C: checkpoints |
| **Negative** (don't do this) | Quadrant B: don'ts + `warn`/`log` rules | Quadrant D: guardrails (`deny`/`user_confirm`) |

### Advisory
Guidance the agent may choose to bypass. Includes markdown instructions (Quadrant A), markdown don'ts, and rules with `warn` or `log` enforcement (Quadrant B).

### Enforced
Guidance the agent cannot bypass. Includes advance checks / checkpoints (Quadrant C) and rules with `deny` or `user_confirm` enforcement (Quadrant D).

### Bypassability
The boundary between advisory and enforced. The defining property: can the agent proceed without satisfying the guidance? `warn` and `log` are advisory (bypassable). `deny` and `user_confirm` are enforced (not bypassable).

---

## Rules

### Rule
A YAML-declared directive that fires when a tool call matches its trigger and detect pattern. Each rule has an `id`, `trigger`, `enforcement` level, optional `detect` pattern, and optional role/phase scoping. Rules are the mechanism for Quadrants B and D. A rule's enforcement level determines whether it's advisory (`warn`/`log`, Quadrant B) or enforced (`deny`/`user_confirm`, Quadrant D). The term "guardrail" is colloquial shorthand for enforced rules — all four enforcement levels are *rules*.

### Trigger
The SDK hook event that activates a rule. Format: `PreToolUse/<ToolName>` (e.g. `PreToolUse/Bash`). A bare `PreToolUse` matches all tools.

### Enforcement Level
How the system responds when a rule fires:

| Level | Who decides | Bypassable? | Quadrant |
|---|---|---|---|
| `deny` | System (automatic block) | No | D |
| `user_confirm` | User via TUI `SelectionPrompt` | No | D |
| `warn` | Agent acknowledges | Yes | B |
| `log` | Silent recording | N/A | B |

> **Constraint:** Do not use `warn` yet — it has an infinite-loop risk (agent retries after acknowledging).

### Detect Pattern
A regex in a rule's `detect` block, matched against a specified `field` of the tool input (default: `command`). If absent, the rule fires on every matching trigger.

### Exclude Pattern
A regex (`exclude_if_matches`) that, when matched, prevents the rule from firing — checked before the detect pattern.

### Role Scoping
Two fields that restrict which agent roles a rule applies to:
- **`block_roles`** — rule fires *only* for these roles.
- **`allow_roles`** — rule *never* fires for these roles.

### Phase Scoping
Two fields that restrict which phases a rule is active in:
- **`phase_block`** — rule fires only during these phases (qualified IDs).
- **`phase_allow`** — rule fires only when the current phase is in this list.

---

## Phases

### Phase
A named stage in a workflow's lifecycle (e.g. `vision`, `setup`, `specification`, `implementation`, `testing`, `signoff`). Phases are ordered. Each phase has an `id`, a `file` reference to a coordinator markdown file, optional `advance_checks`, and optional `hints`.

### Phase Transition
Moving from the current phase to the next. Gated by `advance_checks` — all must pass (AND semantics, short-circuit on first failure) before the transition proceeds.

### Phase State
Runtime tracking of which phase a workflow is currently in. Persisted in `state.json` within the workflow directory. Written atomically (temp file + rename). No mtime caching (NFS unreliability on HPC clusters).

### Qualified Phase ID
The namespaced form of a phase reference: `<workflow_id>:<phase_id>` (e.g. `project-team:testing`). Used in `phase_block` and `phase_allow` fields. The loader validates these against known phases at startup. Bare phase IDs are never used in scoping fields.

---

## Checks

### Check
A verification that tests system state and returns pass/fail with evidence. The **engine** runs checks — not the agent. The protocol is async.

### Check Types (built-in)

| Type | Canonical Name | Passes When |
|---|---|---|
| `CommandOutputCheck` | `command-output-check` | stdout of `command` matches `pattern` regex |
| `FileExistsCheck` | `file-exists-check` | File at `path` exists |
| `FileContentCheck` | `file-content-check` | Content of file at `path` matches `pattern` regex |
| `ManualConfirm` | `manual-confirm` | User answers affirmatively via `SelectionPrompt` in the TUI |

`ManualConfirm` is **system-level** — the engine prompts the user directly. The engine receives a confirmation callback at construction, not an app reference.

### Advance Checks
Checks declared under a phase's `advance_checks` key. Gate phase transitions. AND semantics with short-circuit on first failure.

### Setup Checks
Checks in `global.yaml` that verify environment prerequisites (e.g. GitHub auth, SSH access). Include `on_failure` with a message, severity, and lifecycle. Bridged to the hints pipeline via a `CheckFailed` adapter.

### `when` Clause
A condition on setup checks that gates whether the check runs, based on copier-answer values (e.g. `when: { copier: use_cluster }`).

### `on_failure`
A block on setup checks specifying what happens when the check fails:
- `message` — human-readable guidance.
- `severity` — `warning` (used for setup checks).
- `lifecycle` — controls display behavior (e.g. `show-until-resolved`).

---

## Hints

### Hint
Advisory content delivered to the agent or user. Declared in manifests under phase entries or globally. The engine converts hint declarations to `HintSpec` objects via `run_pipeline()`.

### HintSpec
The internal object representing a hint after manifest parsing. Consumed by the existing hints pipeline.

### Hint Lifecycle
Controls when and how a hint is displayed:
- **`show-once`** — displayed once, then suppressed.
- **`show-until-resolved`** — displayed repeatedly until the underlying condition passes.

> **Not in scope:** `ShowUntilPhaseComplete` lifecycle.

### CheckFailed Adapter
Bridges failing checks into the hints pipeline. When a setup check fails, it produces a hint via `on_failure`, surfaced through `run_pipeline()`.

---

## Agent Folders

### Agent Folder
A directory inside a workflow directory (e.g. `workflows/project_team/coordinator/`). The **folder name is the role type** — used in `block_roles`/`allow_roles` and captured in SDK hook closures at spawn time.

### Role Type
The identity of an agent, derived from its folder name (e.g. `coordinator`, `implementer`, `skeptic`). One name, used everywhere: folder name, rule scoping, hook closures.

### Identity File
`identity.md` inside an agent folder. Cross-phase content — always loaded regardless of current phase.

### Phase File
A markdown file in an agent folder named after a phase (e.g. `specification.md`). Loaded only during that phase. All phase files are pure advisory content.

### Agent Prompt
The assembled prompt for an agent: `identity.md` + current phase file. Content is pull-based — the agent reads `state.json` and loads its own files.

---

## SDK Hooks

### SDK Hook
A callback registered with the Claude Agent SDK that intercepts tool calls. claudechic is the required runtime — all rule-evaluation hooks are SDK hook closures.

### Hook Closure
A function created per-agent that captures the agent's role type at creation time. Used to evaluate rules with role scoping. Rules are loaded fresh on every tool call (no mtime caching).

### Hook Evaluation Pipeline
The sequence when a tool call arrives: match trigger → check role skip → check phase skip → match detect pattern → apply enforcement.

### `PostCompact` Hook
An SDK hook that fires after `/compact`. Re-injects phase context (identity + current phase file) so the agent doesn't lose its guidance after context compaction.

### `SelectionPrompt`
The existing TUI widget used for user confirmations. Used by `user_confirm` enforcement and `ManualConfirm` checks. The engine receives a confirmation callback — not a direct app reference.

---

## Namespacing

### Namespace
A prefix applied to bare IDs at load time: `_global:<id>` for global manifest items, `<workflow_id>:<id>` for workflow items. All IDs are namespaced at runtime. IDs in YAML are written bare — the loader prefixes automatically.

### Qualified ID
The runtime form: `namespace:name`. Examples: `_global:pip_block`, `project-team:close_agent`. Used for deduplication and cross-referencing.

---

## Content Delivery

### Pull-Based Delivery
The engine does **not** inject content mid-session. Instead, agents read `state.json` to discover the current phase, then load their own markdown files. The only exception is `/compact` recovery via the `PostCompact` hook.

---

## Failure Modes

### Fail Closed
If `workflows/` is unreadable, block everything. Applied at the directory level.

### Fail Open
If an individual manifest is malformed or contains a bad regex, skip that manifest and load the rest. Applied per-manifest.

### Startup Validation
Checks performed when manifests are first loaded: duplicate ID detection, invalid regex detection, unknown phase reference validation.

---

## Scope Boundaries

### In Scope
Unified manifest loader, workflow engine, check protocol (4 types), agent folders, `global.yaml` with setup checks, `/compact` recovery hook, phase-scoped rule evaluation.

### Explicitly Out of Scope
- **CompoundCheck** — OR semantics for checks.
- **Content focus guards** — phase-aware read guards.
- **Multi-workflow** — multiple workflows active simultaneously.
- **`ShowUntilPhaseComplete`** — hint lifecycle type.

---

## Existing Codebase Terms (Canonical Homes)

These terms already exist in claudechic. The spec extends but does not rename them:

| Term | Canonical Home | Meaning |
|---|---|---|
| `Rule` (dataclass) | `guardrails/rules.py` | A parsed rule (all enforcement levels) |
| `load_rules()` | `guardrails/rules.py` | Parse YAML into `Rule` objects |
| `SelectionPrompt` | `widgets/prompts.py` | TUI confirmation widget |
| `ChatApp` | `app.py` | Main application class |
| `Agent` | `agent.py` | SDK client wrapper |
| `AgentManager` | `agent_manager.py` | Multi-agent coordinator |
| `HookMatcher` | `claude_agent_sdk.types` | SDK type for hook event matching |

---

## Terminology Hygiene Notes

### Potential Confusion Points

1. **"Rule" vs "Check"** — Rules are reactive (fire on tool calls). Checks are proactive (engine evaluates state). They are distinct mechanisms despite both producing pass/fail outcomes.

2. **"Phase" vs "Stage"** — Use **phase** exclusively. Never "stage" or "step."

3. **"Manifest" vs "Config"** — Use **manifest** for the YAML files in `workflows/`. "Config" refers to `~/.claude/.claudechic.yaml` (user preferences).

4. **"Agent folder" vs "Role directory"** — Use **agent folder**. The folder name *is* the role type, but the container is called "agent folder."

5. **"Rule" vs "Guardrail"** — **Rule** is the precise mechanism term for all four enforcement levels (`deny`, `user_confirm`, `warn`, `log`). **Guardrail** is colloquial shorthand for the enforced subset (Quadrant D: `deny`/`user_confirm`). Use "rule" in definitions and code. Use "guardrail" only as a 2×2 quadrant label or in casual reference to enforced rules. The code module `guardrails/` is a legacy name for the rules infrastructure — acceptable as a module name, but the spec says "rules" when being precise. **Guidance** remains the umbrella term for all four quadrants.

6. **"Advisory" vs "Hint"** — **Advisory** is a classification (bypassable guidance). **Hint** is a specific mechanism (content delivered via `HintSpec`/`run_pipeline()`). Advisory markdown (Quadrant A) is not delivered as hints.

7. **"Engine" vs "Loader"** — The **loader** reads and parses manifests. The **engine** manages workflow state, phase transitions, check execution, and hint delivery. They are separate components.

8. **"Workflow" vs "Workflow manifest"** — A **workflow** is the full package (directory + manifest + agent folders + state). A **workflow manifest** is specifically the YAML file.

9. **"Identity" vs "Prompt"** — **Identity** is the cross-phase `identity.md` file. **Agent prompt** is the assembled result (identity + phase file).

10. **`block_roles` vs `phase_block`** — Both use "block" but scope differently. `block_roles` restricts by agent role. `phase_block` restricts by workflow phase. The naming is inherited from the existing codebase (`guardrails/rules.py`).
