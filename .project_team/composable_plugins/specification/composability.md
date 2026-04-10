# Composability Analysis: AI_PROJECT_TEMPLATE Plugin System

## Domain Understanding

AI_PROJECT_TEMPLATE is a project scaffolding framework that bundles 5 systems for AI/scientific computing projects: environment management (conda/Miniforge bootstrap), claudechic (TUI for Claude Code), a multi-agent project team workflow, a guardrails permission system, and a pattern miner (to be ported). The goal is to decompose these into independently selectable plugins with an interactive onboarding flow.

---

## Seam Analysis: Where the 5 Systems Touch

### System 1: Environment Management (SLC)
**Files:** `activate`, `install_env.py`, `lock_env.py`, `install_SLC.py`, `commands/require_env`, `envs/*.yml`, `envs/*.lock`

**What it provides:**
- Miniforge/conda bootstrap (`install_SLC.py` -> `envs/SLCenv/`)
- Per-environment install/lock lifecycle (`install_env.py`, `lock_env.py`)
- Environment activation with PATH, PYTHONPATH, CONDA_ENVS_PATH setup (`activate`)
- Auto-install-and-activate helper (`commands/require_env`)
- Environment variables: `PROJECT_ROOT`, `SLC_BASE`, `SLC_PYTHON`, `SLC_VERSION`

**What other systems assume about it:**
- `commands/claudechic` hard-sources `commands/require_env claudechic` — assumes SLC is the env manager
- `activate` script scans `envs/*.yml` for status display — tight coupling to `envs/` directory layout
- `install_env.py` checks `SLC_BASE` and `SLC_PYTHON` env vars — all env tools couple to these
- `commands/require_env` validates `PROJECT_ROOT == REPO_ROOT` and `SLC_BASE == SLC_DIR` — assumes single-root project

**Contracts it exposes:**
- Directory convention: `envs/<name>.yml` (spec), `envs/<name>.<platform>.lock` (lockfile), `envs/<name>/` (installed)
- Env vars: `PROJECT_ROOT`, `SLC_BASE`, `SLC_PYTHON`
- CLI: `python install_env.py <name>`, `python lock_env.py <name>`
- Shell helper: `source commands/require_env <name>` (auto-installs + activates)

---

### System 2: Claudechic
**Files:** `commands/claudechic`, `submodules/claudechic/`, `envs/claudechic.yml`

**What it provides:**
- TUI wrapper for Claude Code
- Agent spawning with `CLAUDE_AGENT_NAME`, `CLAUDE_AGENT_ROLE`, `CLAUDECHIC_APP_PID` env vars
- Session management (PID-scoped)

**What other systems assume about it:**
- Guardrails' `role_guard.py` reads `CLAUDE_AGENT_NAME`, `CLAUDE_AGENT_ROLE`, `CLAUDECHIC_APP_PID` — hard dependency on claudechic's env var protocol
- Project team's skill entry (`ao_project_team.md`) is loaded by Claude Code / claudechic — assumes claudechic's skill discovery mechanism
- `activate` script checks for claudechic submodule specifically (line 141-142) — hard-coded submodule name

**What it assumes about others:**
- `commands/claudechic` sources `require_env claudechic` — hard dependency on SLC env management
- Expects `submodules/claudechic/pyproject.toml` at a fixed path
- The `claudechic.yml` spec uses `-e ../submodules/claudechic` — relative path coupling to repo layout

**Contracts it exposes:**
- Env vars: `CLAUDE_AGENT_NAME`, `CLAUDE_AGENT_ROLE`, `CLAUDECHIC_APP_PID`
- Skill files in `.claude/commands/*.md`
- Agent spawning protocol (spawn_agent, tell_agent, etc.)

---

### System 3: Project Team
**Files:** `AI_agents/project_team/*.md`, `.claude/commands/ao_project_team.md`

**What it provides:**
- Multi-agent workflow with role-based delegation (Coordinator, Implementer, Skeptic, Composability, etc.)
- Phased project lifecycle (Vision -> Setup -> Leadership -> Implementation)
- Working directory + state tracking (`.ao_project_team/<project>/STATUS.md`)

**What other systems assume about it:**
- Nothing directly — project team is the most self-contained system

**What it assumes about others:**
- `ao_project_team.md` says "Read and follow: AI_agents/project_team/COORDINATOR.md" — assumes fixed path
- Coordinator spawns agents using claudechic's agent protocol — hard dependency on claudechic
- Agent role files reference concepts that may need guardrails — soft dependency
- No explicit dependency on env management (agents work at the Claude Code level)

**Contracts it exposes:**
- Skill entry point: `.claude/commands/ao_project_team.md`
- Role definitions: `AI_agents/project_team/<ROLE>.md`
- State convention: `.ao_project_team/<project_name>/`

---

### System 4: Guardrails
**Files:** `.claude/guardrails/generate_hooks.py`, `.claude/guardrails/role_guard.py`, `.claude/guardrails/rules.yaml.example`, `.claude/guardrails/hooks/` (generated)

**What it provides:**
- Role-based permission system (allow/block lists per tool trigger)
- Code-generated hook scripts from `rules.yaml` (single source of truth)
- Enforcement levels: deny, warn (with ack flow), log, inject
- Role groups: Agent, TeamAgent, Subagent, Coordinator, named roles
- Session marker system for team mode detection

**What other systems assume about it:**
- Nothing directly imports guardrails — it hooks into Claude Code's hook protocol transparently

**What it assumes about others:**
- **Hard dependency on claudechic env vars:** `role_guard.py` reads `CLAUDE_AGENT_NAME`, `CLAUDE_AGENT_ROLE`, `CLAUDECHIC_APP_PID` (lines 98-101, 195)
- **Hard dependency on claudechic session model:** Session markers at `.claude/guardrails/sessions/ao_<CLAUDECHIC_APP_PID>` — PID-scoped to claudechic
- `generate_hooks.py` assumes PyYAML available (or fails) — soft env dependency
- Session markers are written by `setup_ao_mode.sh` (claudechic lifecycle) and read by `role_guard.py` — shared filesystem protocol
- `GUARDRAILS_DIR` env var defaults to `.claude/guardrails` — assumes repo-relative location

**Contracts it exposes:**
- `rules.yaml` schema (rules list with id, trigger, enforcement, detect, allow/block)
- Generated hook scripts in `hooks/` directory
- Session marker protocol: JSON file at `sessions/ao_<PID>`
- Ack token protocol: JSON file at `acks/ack_<agent>_<rule>.json`
- CLI: `python3 role_guard.py ack <RULE_ID> <FILE_PATH>`

---

### System 5: Pattern Miner (to be ported from DECODE-PRISM)
**Files:** Reference: `DECODE-PRISM/scripts/mine_patterns.py`

**What it provides:**
- 3-tier JSONL session scanner (regex -> semantic -> clustering)
- Extracts user corrections from Claude conversation history
- Outputs to JSON report + state tracking file

**What other systems assume about it:**
- Nothing yet (not ported)

**What it assumes about others:**
- Hard-coded `PROJECT_DIRS` list (line 54-58) — project-specific paths
- Hard-coded `CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"` — assumes Claude's session storage location
- `STATE_FILE` is relative to script location — assumes fixed directory structure
- `_detect_agent_type()` has hard-coded agent role names (Coordinator, Implementer, Skeptic, etc.) — couples to project team's role vocabulary
- No dependency on SLC env management (uses stdlib for Tier 1, optional ML libraries for Tiers 2-3)
- No dependency on claudechic at runtime (reads session files after the fact)

**Contracts it exposes (will expose):**
- CLI: `python mine_patterns.py [--scan-all] [--semantic] [--cluster]`
- Output: JSON correction report
- State: `.patterns_mining_state.json`

---

## Seam Map: Dependency Graph

```
                    ┌────────────────┐
                    │  activate       │  (bootstrap entry point)
                    │  (bash script)  │
                    └───────┬────────┘
                            │ sources/sets env vars
                            ▼
    ┌──────────────────────────────────────────────┐
    │           ENV MANAGEMENT (SLC)                 │
    │  install_SLC.py, install_env.py, lock_env.py  │
    │  require_env, envs/*.yml                       │
    │                                                │
    │  Exports: PROJECT_ROOT, SLC_BASE, SLC_PYTHON  │
    │  Convention: envs/<name>.yml → envs/<name>/    │
    └──────────┬───────────────────────┬─────────────┘
               │                       │
               │ require_env claudechic│
               ▼                       │
    ┌────────────────────┐             │
    │    CLAUDECHIC       │             │
    │  commands/claudechic│             │
    │  submodules/...     │             │
    │                     │             │
    │  Exports:           │             │
    │  CLAUDE_AGENT_NAME  │             │
    │  CLAUDE_AGENT_ROLE  │             │
    │  CLAUDECHIC_APP_PID │             │
    └──┬──────────┬───────┘             │
       │          │                     │
       │          │ env vars read by    │
       │          ▼                     │
       │  ┌──────────────────┐         │
       │  │   GUARDRAILS      │         │
       │  │  role_guard.py    │         │
       │  │  generate_hooks.py│         │
       │  │  rules.yaml       │         │
       │  │                   │         │
       │  │  Reads:           │         │
       │  │  CLAUDE_AGENT_*   │         │
       │  │  CLAUDECHIC_APP_PID│        │
       │  └──────────────────┘         │
       │                               │
       │ skill + agent spawn protocol  │
       ▼                               │
    ┌────────────────────┐             │
    │   PROJECT TEAM      │             │
    │  AI_agents/         │             │
    │  project_team/*.md  │             │
    │  .claude/commands/  │             │
    │  ao_project_team.md │             │
    └────────────────────┘             │
                                       │
    ┌────────────────────┐             │
    │   PATTERN MINER     │  (no deps) │
    │  mine_patterns.py   │─ ─ ─ ─ ─ ─┘
    │  (standalone)       │  (optional ML envs)
    │  Reads: ~/.claude/  │
    │  projects/ JSONL    │
    └────────────────────┘
```

**Key observation:** The dependency flow is mostly linear:
`activate → SLC → claudechic → guardrails` and `claudechic → project team`. Pattern miner is truly standalone.

---

## Dirty Seams Found

### Seam 1: Claudechic ↔ Env Management (DIRTY)
**Coupling:** `commands/claudechic` hard-sources `require_env claudechic` — it assumes SLC is the only way to manage environments.

**Evidence:**
- Line 24: `source "$PROJECT_ROOT/commands/require_env" claudechic || exit 1`
- `claudechic.yml` uses `-e ../submodules/claudechic` (relative path to repo layout)

**Swap test failure:** If someone wanted to use `pip install claudechic` directly (no conda), the launch script breaks. The env management choice leaks into the claudechic launch path.

### Seam 2: Guardrails ↔ Claudechic (DIRTY)
**Coupling:** `role_guard.py` directly reads 3 claudechic-specific env vars. The session marker path is PID-scoped to claudechic.

**Evidence:**
- `role_guard.py` lines 98-101: reads `CLAUDE_AGENT_NAME`, `CLAUDECHIC_APP_PID`
- Session marker: `sessions/ao_<CLAUDECHIC_APP_PID>` — name literally contains "claudechic"
- If guardrails were used without claudechic (e.g., raw Claude Code), `get_my_role()` returns None for everything

**Swap test failure:** If someone used Claude Code directly (without claudechic TUI), guardrails cannot distinguish agents. The role system becomes inert.

### Seam 3: Project Team ↔ Claudechic (MODERATE)
**Coupling:** The skill entry point (`ao_project_team.md`) depends on claudechic's skill discovery. Agent spawning uses claudechic's `spawn_agent` protocol.

**Assessment:** This is more of a necessary coupling — the project team IS a claudechic workflow. But it means the team roles can't be used outside claudechic.

### Seam 4: Pattern Miner ↔ Project Team Vocabulary (DIRTY)
**Coupling:** `mine_patterns.py` `_detect_agent_type()` has hard-coded role names: Coordinator, Implementer, TestEngineer, Skeptic, etc.

**Evidence:** Lines 249-258 — regex patterns with literal role names

**Swap test failure:** If project team roles change or a project uses different role names, the pattern miner doesn't detect them.

### Seam 5: Activate Script ↔ Everything (DIRTY)
**Coupling:** The `activate` script is monolithic — it bundles SLC bootstrap, submodule init (hard-codes "claudechic"), command discovery, skill discovery, and env listing into one script.

**Evidence:**
- Line 141: `if grep -q "claudechic" "$BASEDIR/.gitmodules"` — hard-coded submodule name
- Lines 113-121: hard-codes `commands/` directory for PATH
- Lines 233-251: hard-codes `.claude/commands/` for skill display

**This is the worst seam:** The activate script is where ALL systems converge and it has no plugin awareness. Adding/removing a system requires editing activate.

---

## Identified Composability Axes

### Axis 1: Environment Backend
**What:** How Python environments are managed.
- Values: `slc-conda` (current) | `pip-venv` | `uv` | `nix` | `none` (user manages own env)
- Why independent: You should be able to use guardrails with pip-managed envs, or claudechic without conda.
- Current coupling: Hard-coded in `activate`, `require_env`, `install_env.py`

### Axis 2: Agent Runtime
**What:** What provides agent identity, spawning, and session management.
- Values: `claudechic` (current) | `raw-claude-code` | `claude-api` | `custom-tui`
- Why independent: Guardrails and project team define roles/permissions — the runtime that creates agents should be swappable.
- Current coupling: Guardrails hard-reads `CLAUDECHIC_APP_PID`; project team uses claudechic spawn protocol

### Axis 3: Permission System
**What:** Whether and how tool-use permissions are enforced.
- Values: `guardrails` (current) | `none` | `custom-hooks`
- Why independent: A project should work without guardrails. Adding guardrails shouldn't require claudechic.
- Current coupling: Guardrails inert without claudechic env vars, but otherwise fairly independent

### Axis 4: Team Workflow
**What:** Whether multi-agent collaboration is available and what roles exist.
- Values: `project-team` (current) | `experiment-team` | `custom-team` | `none` (solo mode)
- Why independent: Users should be able to use env management + guardrails without the team system.
- Current coupling: Loosely coupled via `.claude/commands/` skill convention

### Axis 5: Session Intelligence
**What:** Whether and how historical sessions are mined for patterns.
- Values: `pattern-miner` (current) | `none` | `custom-analyzer`
- Why independent: Pattern mining is a post-hoc analysis — doesn't affect runtime at all.
- Current coupling: Nearly zero (standalone script), but has hard-coded role vocabulary

### Axis 6: Bootstrap Method
**What:** How the project is initialized and activated.
- Values: `activate-script` (current) | `cli-tool` | `onboarding-wizard` | `docker`
- Why independent: The bootstrap method should be a thin shell around whatever plugins are selected.
- Current coupling: `activate` script is monolithic, bundles all setup logic

---

## Compositional Law (Proposed)

### The Manifest Law

All plugins interact through a **plugin manifest** — a declarative file (`plugins.yaml` or similar) that declares:

```yaml
plugins:
  env-management:
    backend: slc-conda
    config: { ... }
  agent-runtime:
    backend: claudechic
    config: { ... }
  guardrails:
    enabled: true
    config: { rules_path: .claude/guardrails/rules.yaml }
  team-workflow:
    backend: project-team
    roles_dir: AI_agents/project_team/
  pattern-miner:
    enabled: true
```

**The law:** Each plugin:
1. **Declares** its capabilities and requirements in a standard schema
2. **Reads** its own config from the manifest (never reads another plugin's config)
3. **Exposes** a standard interface: `install()`, `activate()`, `check()`, `remove()`
4. **Communicates** with other plugins only through well-defined env vars or a shared event bus — never by importing/sourcing each other directly

**Seam protocol (bytes equivalent):** Instead of bytes, the common currency is **environment variables** and **filesystem conventions**:
- Plugin A sets `AGENT_NAME` (not `CLAUDE_AGENT_NAME` or `CLAUDECHIC_...`)
- Plugin B reads `AGENT_NAME` if it exists, operates without it if not
- Both agree on the env var name, neither knows the other's implementation

---

## Crystal Holes (Predicted)

| Axis 1 (Env) | Axis 2 (Runtime) | Axis 3 (Perms) | Works? | Issue |
|---|---|---|---|---|
| slc-conda | claudechic | guardrails | YES | Current state |
| pip-venv | claudechic | guardrails | NO | `require_env` fails without SLC |
| slc-conda | raw-claude-code | guardrails | NO | `role_guard.py` needs CLAUDECHIC_APP_PID |
| none | raw-claude-code | none | NO | `activate` script breaks without SLC |
| pip-venv | raw-claude-code | none | SHOULD WORK | Minimal combo, but activate blocks it |
| slc-conda | claudechic | none | YES | Guardrails just absent |

**6 random crystal points, 3 fail = 50% hole rate.** The crystal has significant gaps.

---

## Potential Issues

1. **Activate script is the anti-plugin:** It's the convergence point of all systems with no dispatch mechanism. Must be decomposed first.
2. **Claudechic env vars are baked into guardrails:** The `CLAUDECHIC_APP_PID` naming literally encodes the runtime choice. Needs abstraction to `AGENT_SESSION_PID` or similar.
3. **Pattern miner's hard-coded role names:** Violates open/closed principle — adding a new team role requires editing the miner.
4. **No plugin discovery mechanism exists yet:** There's no registry, no manifest, no lifecycle hooks.
5. **The "SLC_BASE required" check in install_env.py (line 100-103):** This makes env management self-referential — you need SLC activated to install SLC envs. Bootstrapping problem for alternative env backends.

---

## Recommended Deep-Dive Axes

1. **Bootstrap/Activate decomposition** — highest priority, it's the convergence bottleneck
2. **Agent identity abstraction** — needed to decouple guardrails from claudechic
3. **Plugin manifest schema** — needed to define the compositional law concretely
4. **Env backend protocol** — needed to support pip-venv/uv alternatives

---

## Summary for Coordinator

The 5 systems have a mostly linear dependency chain: `activate → env-mgmt → claudechic → guardrails`, with project-team as a claudechic plugin and pattern-miner as standalone. The primary dirty seams are:

1. **activate script** — monolithic, hard-codes all systems, no plugin dispatch
2. **guardrails ↔ claudechic** — env var names literally encode "claudechic", session markers PID-scoped to claudechic
3. **claudechic ↔ env management** — launch script hard-couples to SLC's require_env
4. **pattern miner ↔ project team** — hard-coded role vocabulary

The 6 identified axes (env backend, agent runtime, permission system, team workflow, session intelligence, bootstrap method) define the crystal. Current hole rate is ~50% for random axis combinations — significant work needed to clean seams and enable true composability.

**Critical path:** Decompose the activate script into a plugin-aware dispatcher FIRST. Then abstract the agent identity env vars. Then define the plugin manifest schema. Everything else follows.
