# Existing Infrastructure Audit: What EXISTS vs What's MISSING

**Requested by:** Coordinator
**Date:** 2026-04-04
**Tier of best source found:** T1 (Primary source code — the codebase itself)

## Query

Audit existing codebase infrastructure for: hints system, guardrails system, agent roles, and state/progress tracking. Map what exists vs what's missing for the tutorial system's infrastructure layer. Identify seams between existing systems.

---

## 1. Hints System

### What EXISTS

**Location:** `hints/` (7 files: `__init__.py`, `_types.py`, `_state.py`, `_engine.py`, `hints.py`, `__main__.py`)

**Architecture — 5-axis composable pipeline:**
- **TriggerCondition** protocol: `check(state: ProjectState) -> bool` — pure function, frozen dataclass
- **HintLifecycle** protocol: `should_show(hint_id, state_store) -> bool` + `record_shown()` — 4 implementations: `ShowOnce`, `ShowUntilResolved`, `ShowEverySession`, `CooldownPeriod`
- **HintSpec** dataclass: binds `id`, `trigger`, `message` (static or `Callable[[ProjectState], str]`), `severity`, `priority`, `lifecycle`
- **HintRecord** dataclass: resolved hint ready for presentation (`id`, `message`, `severity`, `priority`)
- **Pipeline** (`_engine.py`): Activation → Trigger → Lifecycle → Sort → Budget → Resolve → Schedule → Persist

**State management:**
- `ProjectState` (frozen): `root`, `copier`, `session_count` + query methods (`path_exists`, `dir_is_empty`, `file_contains`, `count_files_matching`)
- `HintStateStore`: reads/writes `.claude/hints_state.json`, atomic write, graceful degradation
- `ActivationConfig`: global on/off + per-hint disable, persisted in same state file

**Built-in triggers (6 + 3 combinators):**
- `GitNotInitialized`, `GuardrailsOnlyDefault`, `ProjectTeamNeverUsed`, `PatternMinerUnderutilized`, `McpToolsEmpty`, `ClusterConfiguredUnused`
- Combinators: `AllOf`, `AnyOf`, `Not`
- Dynamic: `LearnCommand` (rotating command lessons)

**CLI:** `/hints status|off|on|dismiss|reset|help`

**Public API:** `async evaluate(send_notification, project_root, session_count=None, **kwargs)` — called by ClaudeChic at startup and periodically (every 2 hours).

**Discovery:** Convention-based — ClaudeChic checks if `Path.cwd() / "hints"` exists, imports `evaluate()`.

### What's MISSING for Tutorials

| Gap | Description | Severity |
|-----|-------------|----------|
| **No mode awareness** | Hints pipeline has no concept of "current mode" (normal vs tutorial). All 7 built-in hints fire regardless of context. During a tutorial, generic hints ("Try /ao_project_team") would be noise. | High |
| **No step-scoped hint registration** | Hints are registered globally via `get_hints()`. No mechanism to add/remove hints per tutorial step. Tutorial steps need to inject step-specific hints into the pipeline dynamically. | High |
| **No hint-source tagging** | `HintSpec` has no field to indicate origin (built-in vs tutorial-injected). Needed for filtering: "show only tutorial hints during tutorial mode." | Medium |
| **ProjectState lacks tutorial context** | `ProjectState` has `root`, `copier`, `session_count` but no `active_tutorial`, `current_step`, or `tutorial_state`. Tutorial triggers need this context. | Medium |
| **Budget is hardcoded** | Startup budget=2, periodic budget=1, baked into `_engine.py`. Tutorial mode may need different budgets (e.g., 1 hint per step, immediately). | Low |
| **Timing is hardcoded** | Startup delay=2s, periodic interval=2h. Tutorial hints need immediate delivery, not delayed toasts. | Low |

### Seam Quality: GOOD

The hints system was designed with clean protocols. Adding tutorial support requires:
1. Adding a `source` or `scope` tag to `HintSpec` (non-breaking)
2. Extending `ProjectState` with optional tutorial context (non-breaking — frozen dataclass, add fields with defaults)
3. Making the hint registry dynamic (currently static `get_hints()` → needs a registration mechanism)
4. Adding mode-aware filtering in the pipeline (new filter stage before Trigger evaluation)

**None of these require breaking existing interfaces.** The seam discipline holds.

---

## 2. Guardrails System

### What EXISTS

**Location:** `.claude/guardrails/` (12+ files)

**Architecture — Declarative rules with code generation:**
- **rules.yaml**: Declarative rule catalog. Per-rule fields: `id`, `name`, `trigger`, `enforcement` (log/warn/deny/inject), `detect` (type: regex_match/regex_miss/always/spawn_type_defined + pattern + flags + field), `allow`/`block` (role lists), `message`, `enabled`
- **generate_hooks.py** (2,155 lines): Reads `rules.yaml` → generates Python hook scripts → updates `.claude/settings.json`
- **role_guard.py** (348 lines): Runtime library for role-based permission checking. `check_role(allow, block, enforce, message) -> (code, msg)`. Team mode detection via session markers.
- **hooks/** (auto-generated): `bash_guard.py`, `write_guard.py` — Claude Code PreToolUse hooks

**5 active rules:**
- R01: pytest-output-block (deny, Bash)
- R02: pip-install-block (deny, Bash)
- R03: conda-install-block (deny, Bash)
- R04: subagent-push-block (deny, Bash, block=[Subagent])
- R05: subagent-guardrail-config-block (deny, Write/Edit, block=[Subagent])

**Enforcement pipeline:**
```
Tool invocation → Claude Code PreToolUse hook → Generated hook script
→ Pattern match → Role check → Priority dispatch (deny > warn > inject > log)
→ Exit 0 (allow) or Exit 2 (block) → hits.jsonl logging
```

**Role system:**
- 3 reserved groups: `Agent`, `TeamAgent`, `Subagent`
- 17 named roles from `AI_agents/project_team/*.md`
- Environment variables: `CLAUDE_AGENT_NAME`, `CLAUDE_AGENT_ROLE`, `AGENT_SESSION_PID`

**Team mode:** `setup_ao_mode.sh` / `teardown_ao_mode.sh` — session marker files in `sessions/`

**Ack mechanism:** Two flows — Bash prefix (`# ack:R01`) for warn rules, Write/Edit TTL tokens for file operations.

**Contributed rules:** `rules.d/` directory (empty, ready for extensions).

### What's MISSING for Tutorials

| Gap | Description | Severity |
|-----|-------------|----------|
| **No mode-scoped rules** | Rules have `allow`/`block` for roles but no `scope` for modes (tutorial, normal). Tutorial guardrails should only fire during tutorial mode. | High |
| **No step-scoped rules** | No mechanism to activate rules only for specific tutorial steps. The composability spec calls for `guardrails: list[str]` per step with `scope: { tutorial_id, step_ids }`. | High |
| **No "checkpoint" enforcement** | Current enforcements are preventive (deny/warn/inject/log). Tutorials need a **verification** enforcement — "run this check and report pass/fail" — which is a fundamentally different direction (checking state, not blocking actions). | Critical |
| **No dynamic rule activation** | Rules are baked into generated hooks at generation time. Tutorial rules would need runtime activation/deactivation without regenerating hooks. | Medium |
| **rules.d/ is empty but ready** | The `rules.d/` extension point exists but has no tutorial rules yet. Tutorial-specific rules could live here. | Low (infrastructure exists) |
| **generate_hooks.py doesn't support conditional rules** | All rules in generated hooks are always evaluated. No runtime `if mode == "tutorial"` branching in generated code. | Medium |

### Seam Quality: MIXED

**Good seam:** `rules.d/` extension point — tutorial rules can be separate YAML files merged at generation time.

**Good seam:** Role system — tutorial runner could be a named role with specific allow/block entries.

**Bad seam:** Verification vs prevention. The entire guardrails system is designed to **prevent actions** (exit 2 = block tool). Tutorial verification needs to **check state and report results** (exit 0 with structured output). These are fundamentally different operations. Forcing verification into the guardrails hook model would be an architectural misfit.

**Recommendation:** Tutorial verification should be a **separate system** that reuses patterns from guardrails (shell script exit codes, role awareness) but has its own protocol (`check() -> VerificationResult`). The guardrails system handles **safety during tutorials** (preventing dangerous commands); the verification system handles **checkpoint confirmation**. These are orthogonal concerns and should remain separate.

---

## 3. Agent Roles Infrastructure

### What EXISTS

**Location:** `AI_agents/project_team/` (17 role files)

**Role categories:**
- **Leadership (5):** Coordinator, Composability, Skeptic, TerminologyGuardian, UserAlignment
- **Implementation (3):** Implementer, TestEngineer, UIDesigner
- **Advisory (9):** Researcher, SyncCoordinator, MemoryLayout, BinaryPortability, ProjectIntegrator, LabNotebook, GitSetup, ProjectTypes, README

**Role file format:** Markdown with standard sections: Title, Role, Core Principle, Vocabulary, Interaction Table, Communication Guidelines, Rules, Authority, Output Format.

**Coordination state:** `.ao_project_team/<project>/` with `STATUS.md`, `userprompt.md`, `specification/`

**Phase workflow:** 9 phases (Vision → Setup → Specification → Review → Implementation → Testing → Review → Deployment → Iteration)

**Communication:** `ask_agent` (request with guaranteed response), `tell_agent` (fire-and-forget), `spawn_agent`, `close_agent`, `list_agents`

**Spawning contract:**
```python
spawn_agent(name="<Instance>", type="<RoleType>", path="<Path>", prompt="<Task>", requires_answer=true)
```

### What's MISSING for Tutorials

| Gap | Description | Severity |
|-----|-------------|----------|
| **No "TutorialRunner" role** | No agent role for tutorial execution. The composability spec calls for a single tutorial-runner agent handling all standard tutorials. | Medium |
| **No tutorial-specific communication patterns** | Current agent communication is project-team-oriented. Tutorial mode needs: agent ↔ user dialogue patterns, not agent ↔ agent coordination. | Medium |
| **No mode-switching mechanism** | No way to transition from "project team mode" to "tutorial mode" and back. The `/ao_project_team` skill activates team mode; there's no `/tutorial` skill yet. | High |
| **Role file format works as-is** | The markdown role file convention is directly reusable for a TutorialRunner role. No format changes needed. | N/A (exists) |
| **Spawn contract works as-is** | `spawn_agent(type="TutorialRunner")` would work today if the role file existed. | N/A (exists) |

### Seam Quality: GOOD

The agent infrastructure is role-agnostic. Adding a TutorialRunner role requires:
1. Creating `AI_agents/project_team/TUTORIAL_RUNNER.md` (or `AI_agents/tutorials/TUTORIAL_RUNNER.md`)
2. Optionally adding tutorial-specific guardrail rules with `allow: [TutorialRunner]`

No changes to claudechic, spawn contract, or communication primitives needed.

---

## 4. State & Progress Tracking

### What EXISTS

**Hint state:** `HintStateStore` + `ActivationConfig` → `.claude/hints_state.json`
- Schema: `{ version, activation: { enabled, disabled_hints }, lifecycle: { <hint_id>: { times_shown, last_shown_ts, dismissed, taught_commands } } }`
- Atomic writes (temp + rename)
- Graceful degradation (missing/corrupt → fresh defaults)
- Version-aware (future versions → reset)

**Project state:** `ProjectState` (frozen dataclass) — read-only snapshot of project filesystem state
- `path_exists()`, `dir_is_empty()`, `file_contains()`, `count_files_matching()`

**Copier answers:** `CopierAnswers` — parses `.copier-answers.yml` for feature flags

**Pattern mining state:** `.patterns_mining_state.json` — tracks processed sessions, corrections found

**Session management (ClaudeChic):**
- `sessions.count_sessions()` — count session files in `~/.claude/projects/`
- `Checkpoint` dataclass — conversation rewind points
- `compact_session()` — context window optimization

**Project team state:** `.ao_project_team/<project>/STATUS.md` — phase tracking, agent status, milestones

### What's MISSING for Tutorials

| Gap | Description | Severity |
|-----|-------------|----------|
| **No TutorialStateStore** | No persistence class for tutorial progress. Need: which tutorial, current step, verification evidence per step, completion timestamps, total progress. | Critical |
| **No tutorial state file** | Need a `.claude/tutorial_state.json` (or per-tutorial state file) following the same patterns as `hints_state.json`. | Critical |
| **ProjectState lacks tutorial fields** | No `active_tutorial_id`, `current_step_id`, `tutorial_mode: bool` fields. Tutorial triggers and hints need this context. | High |
| **No cross-session tutorial persistence** | `HintStateStore` pattern handles cross-session state well. Tutorial state needs the same: user closes terminal mid-tutorial → resumes next session at same step. | High |
| **Verification evidence storage** | No existing pattern for storing "proof that step X was completed" (command output, timestamps). `HintStateStore` tracks display counts but not evidence. | Medium |

### Seam Quality: EXCELLENT

The state management patterns are the most reusable part of the codebase:
1. **Atomic write pattern** from `HintStateStore.save()` — copy directly
2. **Graceful degradation** (missing/corrupt → defaults) — copy directly
3. **Version field** for forward compatibility — copy directly
4. **Frozen dataclass for read-only context** (`ProjectState`) — extend with tutorial fields
5. **JSON file in `.claude/`** as persistence location — consistent convention

A `TutorialStateStore` would be structurally identical to `HintStateStore` with different fields.

---

## Cross-System Seam Map

### Existing Seams (Working)

| Seam | System A | System B | Interface | Quality |
|------|----------|----------|-----------|---------|
| **Hints ↔ ClaudeChic** | `hints/__init__.py` | ClaudeChic app | `evaluate(send_notification, project_root, session_count)` | Clean — convention-based discovery |
| **Guardrails ↔ Claude Code** | `hooks/*.py` | Claude Code harness | PreToolUse hook (JSON stdin → exit code) | Clean — standard hook protocol |
| **Guardrails ↔ Role System** | `role_guard.py` | `AI_agents/project_team/` | `CLAUDE_AGENT_ROLE` env var + role file existence | Clean — env var convention |
| **State ↔ Filesystem** | `HintStateStore` | `.claude/hints_state.json` | Atomic JSON read/write | Clean — battle-tested pattern |
| **Copier ↔ Features** | `CopierAnswers` | `.copier-answers.yml` | YAML parsing with graceful fallback | Clean |
| **Team Mode ↔ Sessions** | `setup_ao_mode.sh` | `sessions/ao_<PID>` | Marker file existence | Clean |

### Seams Needed for Tutorials

| Seam | System A | System B | Proposed Interface | Complexity |
|------|----------|----------|-------------------|------------|
| **Tutorial Engine ↔ ClaudeChic** | `tutorials/_engine.py` | ClaudeChic app | Same discovery pattern as hints: `from tutorials import run` | Low — copy existing pattern |
| **Tutorial ↔ Hints** | Tutorial step | Hints pipeline | Step registers `HintSpec` entries with `scope="tutorial"` tag; pipeline filters by mode | Medium — needs mode-aware filtering |
| **Tutorial ↔ Guardrails (Safety)** | Tutorial step | `rules.d/tutorial_*.yaml` | Tutorial-specific deny/warn rules scoped to tutorial mode | Medium — needs mode-scoped rules |
| **Tutorial ↔ Verification** | Tutorial step | `_verification.py` | `Verification.check(context) -> VerificationResult` protocol | Low — new but clean protocol |
| **Tutorial State ↔ Filesystem** | `TutorialStateStore` | `.claude/tutorial_state.json` | Copy `HintStateStore` pattern exactly | Low — pattern exists |
| **Tutorial ↔ ProjectState** | Tutorial engine | `ProjectState` | Add optional `tutorial_context` field to `ProjectState` | Low — non-breaking extension |

---

## Infrastructure Readiness Scorecard

| Component | Exists | Reusable As-Is | Needs Extension | Needs New Build | Notes |
|-----------|--------|---------------|-----------------|-----------------|-------|
| **Hint pipeline** | Yes | Partially | Mode-aware filtering, dynamic registration | — | Core pipeline reusable; needs scope layer |
| **Hint types** | Yes | Yes | Add `scope` field to HintSpec | — | Non-breaking addition |
| **Hint state** | Yes | Pattern reusable | — | TutorialStateStore (same pattern) | Copy-paste-adapt |
| **ProjectState** | Yes | Yes | Add tutorial context fields | — | Frozen dataclass, add defaults |
| **Guardrails rules** | Yes | Yes (for safety) | Mode-scoped rules | — | `rules.d/` ready for tutorial rules |
| **Guardrails hooks** | Yes | Yes (for safety) | — | — | Prevention works as-is for tutorial safety |
| **Guardrails as verification** | No | — | — | **Separate verification system** | Different concern; don't force into hook model |
| **Role files** | Yes | Yes | — | TutorialRunner.md role file | Add one file |
| **Agent spawning** | Yes | Yes | — | — | `spawn_agent(type="TutorialRunner")` works today |
| **Agent communication** | Yes | Partially | — | User-facing dialogue patterns | ask/tell is agent-to-agent; tutorial is agent-to-user |
| **Activation/mode** | Partial | `ActivationConfig` pattern | — | Mode registry (normal/tutorial/team) | Need global mode concept |
| **Content loading** | No | — | — | **Tutorial YAML manifest + MD loader** | New module |
| **Verification protocol** | No | — | — | **Verification types + runner** | New module (critical) |
| **Progression engine** | No | — | — | **Step sequencing + gating** | New module |
| **Tutorial CLI** | No | — | — | `/tutorial` skill + commands | New skill (follows `/hints` pattern) |

---

## Summary: What to Build vs What to Reuse

### Reuse Directly (zero changes)
1. Agent spawn contract (`spawn_agent(type="TutorialRunner")`)
2. Role file format (create `TUTORIAL_RUNNER.md`)
3. Guardrails for safety during tutorials (existing rules protect against `pip install`, etc.)
4. `rules.d/` extension point for tutorial-specific safety rules
5. Atomic write persistence pattern from `HintStateStore`
6. Convention-based discovery from ClaudeChic (`tutorials/` folder)

### Extend (non-breaking changes to existing code)
1. `HintSpec` — add optional `scope` field (default `None` = always active)
2. `ProjectState` — add optional `tutorial_context` field (default `None`)
3. Hints pipeline — add mode-aware filter stage (before trigger evaluation)
4. Guardrails `rules.yaml` schema — add optional `mode_scope` field to rules

### Build New
1. **`tutorials/_types.py`** — `TutorialStep`, `Verification` protocol, `VerificationResult`
2. **`tutorials/_verification.py`** — Built-in verification implementations (`CommandOutputCheck`, `FileExistsCheck`, `ConfigValueCheck`, `CompoundCheck`, `ManualConfirm`)
3. **`tutorials/_state.py`** — `TutorialStateStore` (modeled on `HintStateStore`)
4. **`tutorials/_engine.py`** — Tutorial execution pipeline (load → present → verify → progress)
5. **`tutorials/content/`** — YAML manifests + markdown step files per tutorial
6. **`/tutorial` skill** — Entry point for tutorial mode (modeled on `/hints` and `/ao_project_team`)
7. **Mode registry** — Global concept of "current mode" accessible to hints, guardrails, and tutorials

### Critical Architectural Decision

**Verification is NOT guardrails.** The guardrails system prevents actions (PreToolUse → exit 2 = block). Tutorial verification checks state (run command → inspect output → report pass/fail). These are fundamentally different:

| | Guardrails (Safety) | Verification (Checkpoint) |
|---|---|---|
| **When** | Before tool execution | After user completes a step |
| **Direction** | Preventive (block bad actions) | Confirmatory (prove good state) |
| **Output** | Allow/block (exit code) | Pass/fail + evidence |
| **Side effects** | None (pure filter) | Runs commands to check state |
| **Scope** | Active during tutorial (safety) | Defines tutorial progression |

Both systems should exist during tutorials — guardrails for safety, verification for progression — but they are orthogonal concerns connected only by the tutorial step (which lists both `guardrails: [R10, R11]` and `verification: CommandOutputCheck(...)`).
