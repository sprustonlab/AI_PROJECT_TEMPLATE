# Research: Phase Content Delivery & State Discovery Alignment

**Author:** Researcher
**Date:** 2026-04-04
**Requested by:** Coordinator
**Tier of best source found:** T1 (codebase itself — primary source)

---

## Question 1: How Does Phase Content Reach a Running Agent Mid-Session?

### What the Codebase Actually Does

I traced the entire agent communication pipeline. There are exactly **three content delivery mechanisms** in the system:

#### Mechanism A: spawn_agent (Initial Prompt)

When Coordinator spawns a sub-agent, it uses the `spawn_agent` MCP tool (`submodules/claudechic/claudechic/mcp.py` lines 155-234). The prompt is delivered asynchronously via `_send_prompt_fire_and_forget()`. This is **one-shot** — you set the initial prompt and the agent runs with it.

```python
spawn_agent(
    name="Composability",
    path="{working_dir}",
    prompt="You are Composability. Read your role file: {role_path}...",
    requires_answer=True
)
```

**Limitation:** Can only deliver content at spawn time. Cannot update a running agent's system prompt.

#### Mechanism B: tell_agent / ask_agent (Runtime Messages)

Located at `mcp.py` lines 282-346. These inject a message into another agent's conversation:

- `tell_agent(name, message)` — fire-and-forget status update
- `ask_agent(name, message)` — expects a response

The message appears in the agent's conversation as:
```
[Message from agent 'Sender']

<actual message content>
```

**Key insight:** This is a conversational message, not a system prompt injection. The agent sees it as a new turn in its conversation and can act on it.

#### Mechanism C: File-Based Pull (Agents Read Files Themselves)

This is the dominant pattern in the codebase. COORDINATOR.md instructs: **"EVERY TURN, BEFORE ANYTHING ELSE: Read STATUS.md"**. Agents actively fetch context by reading files from disk:

- `.ao_project_team/{project}/STATUS.md` — current phase and progress
- `.ao_project_team/{project}/userprompt.md` — original request
- `.ao_project_team/{project}/specification/*.md` — other agents' outputs

**This is pull-based for shared state, push-based for commands.**

#### What Does NOT Exist

- No system prompt injection via environment variables
- No mechanism to modify a running agent's role file
- No SessionStart hooks that inject content (the `post_compact_injector.py` trigger exists in `generate_hooks.py` line 54, but no rules use it — it's infrastructure without consumers)
- No hot-reload of agent instructions

---

### How the Coordinator Itself Is Launched

The Coordinator is **not spawned by spawn_agent**. It runs in the main session:

1. User runs `/ao_project_team`
2. `.claude/commands/ao_project_team.md` contains: `Read and follow: AI_agents/project_team/COORDINATOR.md`
3. Claude reads COORDINATOR.md and executes the workflow in its own session
4. Claude uses `spawn_agent` to create sub-agents

**The Coordinator IS the main session agent.** It can read any file at any time.

---

### Recommendation: Phase Content Delivery Mechanism

Given these constraints, there are three viable options. I recommend **Option C** (hybrid).

#### Option A: tell_agent Phase Content (Push)

```
Engine transitions Phase 4 → Phase 5
Engine calls: tell_agent("Coordinator", "Phase transition: read teams/project_team/phases/phase-05-testing.md")
Coordinator reads the file and follows its instructions
```

**Problem:** The Coordinator is the main session agent. You can't `tell_agent` to yourself. And the "engine" isn't a separate agent — it would need to be.

#### Option B: File-Based Pull (STATUS.md Pattern)

```
Engine writes phase_state.json with new phase_id
Coordinator's instructions say: "After each gate check, read phase_state.json and load the current phase file"
Coordinator reads phases/phase-05-testing.md itself
```

**This follows the existing pattern exactly.** COORDINATOR.md already tells the agent to read STATUS.md every turn. Adding "read phase_state.json and load the corresponding phase file from phases.yaml" is the same pattern.

**Advantage:** Zero new infrastructure. Works today.
**Disadvantage:** Relies on the agent following instructions (~80% reliable per spec's own estimate).

#### Option C: Hybrid — File Pull + Guardrail Nudge (Recommended)

```
1. phase_state.json is updated with new phase_id + phase file path
2. COORDINATOR.md (cross-phase) instructs: "At each phase transition, read phase_state.json
   and load the phase file listed there"
3. A SessionStart/compact hook (post_compact_injector) injects a reminder:
   "Current phase: {phase_id}. Instructions: {phase_file_path}"
```

**Why this is best:**

1. **Primary delivery (file pull):** Coordinator reads `phase_state.json` to discover the current phase file, then reads that file. Follows the STATUS.md pattern that already works.

2. **Compaction safety (hook injection):** After `/compact`, the conversation history is summarized and phase context may be lost. The `post_compact_injector.py` hook trigger already exists in `generate_hooks.py` (line 54: `"SessionStart/compact": "post_compact_injector.py"`). It has zero consumers today. Adding a rule that injects "Current phase: X, read file Y" after compaction is the intended use of this infrastructure.

3. **Guardrail reinforcement:** Phase-scoped guardrails (phase_block/phase_allow) already prevent wrong-phase actions. Even if the agent drifts, the guardrails catch it.

**Implementation cost:** ~30 lines:
- `phase_state.json` includes a `current_phase_file` field (the resolved path)
- Cross-phase COORDINATOR.md gets 3 lines: "Read phase_state.json, load the phase file"
- One `SessionStart/compact` rule in `rules.yaml` that injects phase context (~15 lines)

#### Option D: Spawn-Per-Phase (Rejected)

Spawn a new Coordinator agent for each phase with the phase file in its prompt. Rejected because:
- Loses conversation context between phases
- Wastes context window re-establishing state
- Doesn't match how the system works (Coordinator is the main session)

---

### The post_compact_injector — Existing Infrastructure Ready for Use

This is a key finding. `generate_hooks.py` line 54 defines:

```python
"SessionStart/compact": "post_compact_injector.py"
```

This means the code generator already knows how to emit a hook script for the `SessionStart/compact` trigger. No rules currently use this trigger, so no hook is generated. But the infrastructure is ready.

A `SessionStart/compact` rule would fire after every `/compact` command, injecting a system message. This is exactly what phase content delivery needs for compaction safety:

```yaml
# Proposed rule for rules.yaml
- id: R-PHASE-REMINDER
  name: phase-context-injector
  trigger: SessionStart/compact
  enforcement: inject
  detect:
    type: always
  message: "Current phase context — read phase_state.json for instructions"
  source: "Phase system — restore phase context after compaction"
```

---

## Question 2: State Discovery — One Consistent Pattern

### What Exists Today (Three Patterns)

| System | Discovery | Path | Set By |
|--------|-----------|------|--------|
| **Hints** | Constructor parameter (`project_root: Path`) | `project_root / ".claude/hints_state.json"` | claudechic passes `self._cwd` |
| **Guardrails** | Env var with default | `GUARDRAILS_DIR` (default: `.claude/guardrails`) | Default or external override |
| **Generated hooks** | Hardcoded script-relative | `SCRIPT_DIR / "rules.yaml"` | Fixed at generation time |

### Why They Differ

The patterns differ because the **consumers** differ:

1. **Hints** are evaluated by a Python module imported by claudechic. The caller (claudechic) knows `project_root` and passes it as a parameter. Clean dependency injection.

2. **Guardrails/hooks** are executed as **standalone scripts** by Claude Code's hook system. They don't receive `project_root` as a parameter — they're invoked by the Claude Code runtime with a JSON payload on stdin. They must discover their context from environment or filesystem.

3. **generate_hooks.py** runs at **development time**, not runtime. It knows where it lives (`__file__`) and resolves `rules.yaml` relative to itself. No discovery needed.

### The Right Pattern for phase_state.json

`phase_state.json` has **two consumers with different constraints:**

| Consumer | Runtime | Has project_root? | Needs env var? |
|----------|---------|-------------------|----------------|
| **Hints pipeline** (PhaseIs trigger) | Python import in claudechic | Yes — passed via `ProjectState.build()` | No |
| **Guardrail hooks** (phase_guard.py) | Standalone script, stdin JSON | No — must discover | Yes, or derive from CWD |

### Recommendation: Parameter-First, Env-Var-Override

```
Default path:    <project_root>/.ao_project_team/phase_state.json
Override:        PHASE_STATE_PATH environment variable
```

**For the hints pipeline (ProjectState):**

```python
# In hints/_state.py — ProjectState.build()
@classmethod
def build(cls, project_root: Path, **kwargs: Any) -> ProjectState:
    root = Path(project_root).resolve()
    copier = CopierAnswers.load(root)
    active_phase = _load_active_phase(root)  # NEW
    return cls(
        root=root,
        copier=copier,
        session_count=kwargs.get("session_count"),
        active_phase=active_phase,
    )

def _load_active_phase(root: Path) -> ActivePhase | None:
    """Load phase state. Follows HintStateStore pattern: missing/corrupt → None."""
    override = os.environ.get("PHASE_STATE_PATH")
    path = Path(override) if override else root / ".ao_project_team" / "phase_state.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ActivePhase(
            workflow_id=data["workflow_id"],
            phase_id=data["phase_id"],
            phase_entered_at=data.get("phase_entered_at", 0.0),
            completed_phases=frozenset(data.get("completed_phases", [])),
            last_check_result=None,  # Not loaded from file
        )
    except (json.JSONDecodeError, KeyError, OSError):
        return None  # Fail-open: no phase → triggers don't fire
```

**For guardrail hooks (phase_guard.py):**

```python
# In .claude/guardrails/phase_guard.py
def _get_phase_state_path() -> Path:
    """Resolve phase_state.json path.

    Priority: PHASE_STATE_PATH env var > CWD-relative default.
    Follows GUARDRAILS_DIR pattern for hooks.
    """
    override = os.environ.get("PHASE_STATE_PATH")
    if override:
        return Path(override)
    return Path(".ao_project_team/phase_state.json")
```

**Why `.ao_project_team/` and not `.claude/`:**

- `.claude/` is Claude Code's config directory (settings, commands, guardrails)
- `.ao_project_team/` is the project team's runtime state directory
- Phase state is runtime state (which phase is active), not configuration
- It sits alongside `STATUS.md` and other workflow state — where it belongs

**Why env var override for both consumers:**

- Hints pipeline: for unit tests that need a temp directory
- Guardrail hooks: for the same reason, plus CI environments
- Follows `GUARDRAILS_DIR` precedent (optional override, sensible default)

### Summary: The Unified Rule

> **State files live at a fixed path relative to `project_root`.** Python modules receive `project_root` as a parameter. Standalone scripts derive it from CWD. Both support an env var override for testing. The env var is optional — the default path is always valid.

| State File | Default Path (relative to project root) | Env Var Override | Consumer A (Python) | Consumer B (Hook) |
|------------|----------------------------------------|------------------|--------------------|--------------------|
| Hints state | `.claude/hints_state.json` | *(none today)* | `project_root` param | N/A |
| Phase state | `.ao_project_team/phase_state.json` | `PHASE_STATE_PATH` | `project_root` param | CWD-relative + env var |
| Guardrails config | `.claude/guardrails/rules.yaml` | N/A (generation-time) | N/A | `SCRIPT_DIR`-relative |
| Session markers | `.claude/guardrails/sessions/ao_<PID>` | `GUARDRAILS_DIR` | N/A | `GUARDRAILS_DIR` + env var |

---

## Summary

### Content Delivery: Use file-based pull + compaction hook

The Coordinator reads `phase_state.json` to discover the current phase file (same pattern as STATUS.md). A `SessionStart/compact` rule — using the existing but unused `post_compact_injector` infrastructure — restores phase context after compaction. Phase-scoped guardrails provide a safety net. Zero new delivery infrastructure needed.

### State Discovery: Parameter-first, env-var-override, fixed relative path

`phase_state.json` lives at `.ao_project_team/phase_state.json`. Python modules receive `project_root` as a parameter and resolve the path. Standalone hooks derive from CWD. Both accept `PHASE_STATE_PATH` env var for testing. This unifies the hints pattern (parameter-first) with the guardrails pattern (env var override).
