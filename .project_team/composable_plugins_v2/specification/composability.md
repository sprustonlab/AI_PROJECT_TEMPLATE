# Composability Analysis: AI_PROJECT_TEMPLATE v2

## Domain Understanding

AI_PROJECT_TEMPLATE is a project scaffolding system for AI/scientific computing projects. v1 established 5 filesystem-convention seams (envs, commands, skills, agent roles, guardrail rules), replaced SLC with pixi, and used Copier for onboarding. v2 evolves this by:

1. **Externalizing claudechic** — from committed submodule to git URL dependency (with developer-mode escape hatch)
2. **Adding seam #6: MCP Tools** — `mcp_tools/` directory for drop-in MCP tool modules
3. **Simplifying bootstrap** — pixi-only bootstrap via `pixi exec --spec copier`
4. **Shipping cluster MCP** — LSF job management as the first MCP tool plugin

The core compositional insight from v1 remains correct: **directory conventions ARE the plugin system**. v2 extends this principle cleanly — `mcp_tools/` follows exactly the same "drop a file, it's discovered" pattern as the other 5 seams.

---

## v1 Composability Recap and What Changed

### v1 Axes (6 identified)

| Axis | v1 Status | v2 Status |
|------|-----------|-----------|
| Env Backend | Pixi locked in (correct — one backend done well) | **Unchanged** — pixi remains sole backend |
| Agent Runtime | claudechic as committed submodule | **Evolved** — git URL dep + developer mode |
| Permission System | Guardrails (optional add-on) | **Unchanged** |
| Team Workflow | Project team (optional add-on) | **Unchanged** |
| Session Intelligence | Pattern miner (optional add-on) | **Unchanged** |
| Bootstrap Method | Copier + pip | **Simplified** — pixi exec ephemeral copier |

### v1 Dirty Seams — Resolution Status

| Dirty Seam | v1 Problem | v2 Resolution |
|------------|------------|---------------|
| activate monolith | Hard-coded all systems | **Still present** — activate is still the seam registry, but v1 spec already cleaned it (seam-aware sections, no SLC coupling) |
| guardrails ↔ claudechic env vars | `CLAUDECHIC_APP_PID` naming | **Not explicitly addressed in v2 scope** — but lower priority since claudechic IS the assumed runtime |
| claudechic ↔ env management | `require_env` coupling | **Resolved** — pixi `pypi-dependencies` git URL replaces submodule + require_env pattern |
| pattern miner ↔ role vocabulary | Hard-coded role names | **Not addressed in v2 scope** |

---

## v2 Axes of Composition

v2 doesn't add new fundamental axes — it refines existing ones and adds a new seam within the existing structure. Here are the axes relevant to v2's changes:

### Axis 1: Claudechic Distribution Mode
**What:** How claudechic code arrives in the project.
- Values: `git-url` (standard) | `editable-local` (developer mode)
- Why independent: The distribution method should not affect any other seam. Whether claudechic comes from a git URL or a local clone, all other systems (guardrails, skills, MCP tools, project team) work identically.
- Compositional law: Both modes produce the same installed Python package. The seam is `import claudechic` — downstream code doesn't know or care how it was installed.

**Clean seam test:**
- Switch from git-url to editable-local: change one line in `pixi.toml`. No other file changes. **PASS.**
- Switch back: change the same line. **PASS.**
- This is a genuinely orthogonal axis — it's a packaging concern, not a runtime concern.

### Axis 2: MCP Tool Composition (NEW — Seam #6)
**What:** Which MCP tools are available to claudechic at runtime.
- Values: Any combination of `mcp_tools/*.py` files (cluster, future-slurm, future-kubernetes, user-custom, etc.)
- Why independent: Each MCP tool is a self-contained Python file. Adding/removing one doesn't affect others or any other seam.
- Compositional law: `get_tools(**kwargs) -> list[tool_function]`

**This is the most compositionally interesting v2 addition.** Let me analyze it in detail:

#### The MCP Tools Seam Contract

```python
# Each mcp_tools/<name>.py exposes:
def get_tools(**kwargs) -> list[callable]:
    """Return tool functions for MCP registration.

    kwargs may include:
      caller_name: str       # agent identity
      send_notification: fn  # notification callback
      find_agent: fn         # agent lookup
    """
```

**Algebraic composition analysis:**
- The law is `get_tools(**kwargs) -> list[tool_function]`
- Each tool file follows this law independently
- Discovery is by filesystem convention (`mcp_tools/*.py`)
- Claudechic's `mcp.py` (~20 lines) walks the directory, calls `get_tools()` on each, flattens the results
- **No tool knows about other tools.** No tool imports from other tools. The seam is clean.

**Crystal test (5 random points):**

| cluster.py | custom_tool.py | another_tool.py | Works? |
|------------|---------------|-----------------|--------|
| present | absent | absent | YES — cluster tools available |
| absent | present | absent | YES — custom tools available |
| present | present | present | YES — all tools available |
| absent | absent | absent | YES — no MCP tools, claudechic still works |
| present | absent | present | YES — subset composition |

**5/5 pass. The crystal is complete.** This is because the axis is purely additive — file presence = enabled, file absence = disabled. No combinations can conflict because each tool registers independent functions.

**Potential hole:** The `kwargs` wiring. If a tool requires `send_notification` but it's not provided, the tool must handle that gracefully (default to no-op or raise clear error). The contract should specify: **all kwargs are optional, tools must have sensible defaults when kwargs are absent.**

#### MCP Tools vs. Guardrails Interaction

**Cross-seam question:** Do MCP tools respect guardrail rules?

MCP tools register as Claude Code tools. Guardrails hook into Claude Code's hook protocol. Therefore guardrails can gate MCP tool invocations the same way they gate any other tool. **The seams don't need to know about each other** — Claude Code is the composition substrate that connects them. This is clean.

### Axis 3: Cluster Backend (Sub-axis of MCP Tools)
**What:** Which cluster scheduler the cluster MCP tool targets.
- Values: `lsf` (shipped) | `slurm` (future) | `pbs` (future) | `kubernetes` (future)
- Why independent: The cluster MCP tool's external interface (submit, status, kill, logs, watch) is scheduler-agnostic. The scheduler backend is an implementation detail.

**Design consideration:** Currently `cluster.py` likely has LSF-specific code throughout. For v2, this is fine — LSF is the only backend. But the specification should note that if SLURM/PBS are added later, the cluster tool itself needs an internal axis (scheduler backend) with its own clean seam. This is a **future decomposition**, not a v2 requirement.

### Axis 4: Bootstrap Chain
**What:** The sequence of tools that gets a user from zero to working project.
- Values (simplified to one path in v2): `pixi install -> pixi exec copier -> source activate`
- Why this matters: v2 collapses the bootstrap to a single dependency (pixi). This eliminates the v1 axis of "how do you get copier?" (pip? pipx? conda?).

**Composability win:** By making pixi the sole entry point, the bootstrap is no longer an axis at all — it's a constant. This is the right move. Fewer axes = simpler crystal = fewer holes.

### Axis 5: Copier Feature Selection
**What:** Which add-ons are selected during `copier copy`.
- Values per add-on: `enabled` | `disabled`
- Add-ons: guardrails, project-team, pattern-miner, cluster-mcp
- Why independent: Each add-on is a set of files dropped into the right seam directories. Copier's `_skip_if_exists` and conditional file inclusion handle this.

**Crystal test (4 binary axes = 16 combinations):**

| guardrails | project-team | pattern-miner | cluster-mcp | Works? |
|-----------|-------------|--------------|-------------|--------|
| on | on | on | on | YES — full template |
| off | off | off | off | YES — bare project |
| on | off | on | off | YES — guardrails + mining, no team |
| off | on | off | on | YES — team + cluster, no guardrails |
| on | on | off | on | YES — team + guardrails + cluster |

**All combinations should work** because:
1. Each add-on lives in its own seam directory
2. No add-on imports from another add-on
3. Copier drops files without creating cross-add-on dependencies

**Potential hole: project-team + cluster-mcp interaction.** If team agents use cluster MCP tools, there's a soft runtime dependency (agents reference tools that may not exist). This is acceptable — agents gracefully discover available tools at runtime. But the agent role files should not hard-code cluster tool names.

---

## Compositional Laws for v2

### Law 1: The Filesystem Convention Law (unchanged from v1)
**Statement:** Each seam is a directory convention. File presence = enabled. File absence = disabled. No manifest, no registry, no runtime dispatch beyond directory scanning.

| Seam | Directory | Discovery |
|------|-----------|-----------|
| Environments | `pixi.toml` features | `pixi info` / feature parsing |
| Commands | `commands/` | `activate` adds to PATH |
| Skills | `.claude/commands/` | Claude Code auto-discovers |
| Agent Roles | `AI_agents/**/*.md` | Coordinator reads at runtime |
| Guardrail Rules | `.claude/guardrails/rules.yaml` + `rules.d/` | `generate_hooks.py` reads |
| **MCP Tools** | **`mcp_tools/`** | **claudechic `mcp.py` walks directory** |

**Why this is algebraic:** You don't ask "does cluster.py work with guardrails?" You ask "does cluster.py live in `mcp_tools/`?" YES. "Does `mcp.py` scan `mcp_tools/`?" YES. Therefore composition is guaranteed by the law.

### Law 2: The Package Identity Law (new for v2)
**Statement:** Claudechic is a Python package. How it's installed (git URL vs editable local) is invisible to all consumers. The seam is `import claudechic`.

**Why this matters:** This law ensures the distribution mode axis is truly orthogonal. No code anywhere should check "is claudechic installed from git or local?" — they just import it.

### Law 3: The MCP Tool Protocol Law (new for v2)
**Statement:** Every file in `mcp_tools/` exposes `get_tools(**kwargs) -> list[callable]`. All kwargs are optional with sensible defaults. Tools are self-contained — no cross-tool imports.

---

## Seam Analysis: Where v2 Changes Touch Existing Seams

### New Seam: Claudechic Discovery Code ↔ mcp_tools/

**Seam location:** claudechic's `mcp.py` (~20 lines) ↔ `mcp_tools/*.py` files

**What crosses the seam:**
- `mcp.py` reads: file paths, calls `get_tools(**kwargs)`
- Tool files receive: kwargs dict, return: list of callables

**What should NOT cross:**
- `mcp.py` should not inspect tool internals
- Tools should not import from claudechic internals (only use provided kwargs)
- Tools should not assume they're the only tool loaded

**Swap test:**
- Remove `cluster.py` from `mcp_tools/`: Does `mcp.py` still work? **YES** (fewer tools, no error)
- Add `custom.py` to `mcp_tools/`: Does `mcp.py` discover it? **YES** (directory scan)
- Replace `cluster.py` with SLURM version: Does anything else change? **NO**
- **CLEAN SEAM.**

### Modified Seam: pixi.toml ↔ Claudechic Installation

**v1:** `submodules/claudechic/` + editable install in pixi feature
**v2:** `git = "https://github.com/boazmohar/claudechic"` in `[pypi-dependencies]`

**Swap test:**
- Change git URL to editable local path: One line change in `pixi.toml`. Nothing else changes. **CLEAN.**
- The activate script no longer needs submodule auto-init for standard mode. Developer mode still uses submodules.

**Potential issue:** The activate script (Section 5: Submodule Auto-Init) checks for claudechic in `.gitmodules`. In standard mode (git URL), there's no submodule, so this section is skipped. In developer mode, the submodule exists. **The activate script should handle both gracefully** — and it already does, since the check is `if [[ -f ".gitmodules" ]] && grep claudechic`.

### Unchanged Seams: All 5 Original Seams

The 5 original seams are unaffected by v2 changes. This is the composability payoff — adding seam #6 and changing the distribution model requires zero changes to the other seams.

---

## Potential Issues and Holes

### Issue 1: kwargs Coupling in MCP Tool Protocol
**Risk:** Medium
**Description:** The `kwargs` passed to `get_tools()` (`caller_name`, `send_notification`, `find_agent`) create a soft dependency on claudechic's internal API. If claudechic changes its notification or agent-finding interface, all MCP tools using those kwargs break.

**Recommendation:** Define the kwargs signatures as a stable protocol, documented separately from claudechic internals. These are the "environment variables" of the MCP seam — they should be versioned and stable.

### Issue 2: cluster.py Configuration Location
**Risk:** Low
**Description:** Cluster configuration (SSH target, poll interval) goes in `.claudechic.yaml`. This means cluster MCP tool configuration is coupled to claudechic's config file, not to a tool-specific config.

**Recommendation:** Acceptable for v2. The cluster tool IS a claudechic tool — it makes sense for its config to live there. If non-claudechic MCP hosts emerge in the future, config could move to `mcp_tools/cluster.yaml` alongside the Python file. But premature abstraction here would add complexity for no current benefit.

### Issue 3: Copier Template + MCP Tools Interaction
**Risk:** Low
**Description:** The `use_cluster` Copier question controls whether `mcp_tools/cluster.py` exists. Post-creation, the user can add/remove MCP tools manually. There's a potential mismatch: Copier "thinks" cluster is disabled, but the user added it back manually.

**Assessment:** This is a non-issue. Copier only runs at creation time (and `copier update` for template evolution). The filesystem convention is the runtime truth, not Copier's answers. `_skip_if_exists` ensures Copier won't delete user-added files on update. **The filesystem law holds.**

### Issue 4: Developer Mode Switching Friction
**Risk:** Low
**Description:** Switching from standard to developer mode requires: (1) clone claudechic repo into `submodules/`, (2) change one line in `pixi.toml`, (3) `pixi install`. Switching back: (1) change line back, (2) `pixi install`, (3) optionally delete clone.

**Assessment:** This is 2-3 manual steps. Acceptable for a developer-mode escape hatch — developers who need this are comfortable with these operations. A helper command (`commands/dev-mode-claudechic`) could automate this, but it's not a composability issue.

---

## Crystal Summary

### v2 Crystal Dimensions

| Axis | Values | Truly Independent? |
|------|--------|-------------------|
| Claudechic Distribution | git-url, editable-local | YES — one line in pixi.toml |
| MCP Tools | any subset of mcp_tools/*.py | YES — additive, no conflicts |
| Cluster Backend (sub-axis) | lsf (v2), slurm/pbs/k8s (future) | YES (internal to cluster tool) |
| Copier Add-on Selection | 2^4 = 16 combinations | YES — independent file sets |
| Bootstrap | pixi-only (constant in v2) | N/A — not an axis anymore |

**Crystal size:** 2 (distribution) x 2^N (MCP tools, where N = number of available tools) x 16 (add-on combos) = highly combinatorial, but **algebraically guaranteed** by the filesystem convention law. No need to test every combination.

### v2 Crystal Hole Rate

**Predicted: ~0% for v2-scope changes.** The design is clean because:
1. The MCP tools seam follows the established filesystem convention pattern
2. The distribution mode axis is a pure packaging concern with no runtime leakage
3. The bootstrap simplification removes an axis rather than adding complexity
4. Copier add-on selection is purely file-presence-based

**Inherited from v1 (not v2 scope but still present):**
- Guardrails ↔ claudechic env var coupling (`CLAUDECHIC_APP_PID`)
- Pattern miner ↔ project team role vocabulary coupling

---

## Recommendations for Specification

1. **Document the MCP Tool Protocol explicitly** — `get_tools(**kwargs)` contract, kwargs stability guarantees, error handling expectations (graceful degradation when kwargs absent)

2. **Document the distribution mode switch** — the exact pixi.toml line change, so users understand this is a single-point-of-change axis

3. **Keep cluster.py LSF-specific for v2** — don't prematurely abstract a scheduler backend axis. Note it as a future decomposition point

4. **Ensure activate script handles both distribution modes** — submodule auto-init only when `.gitmodules` references claudechic (already the case)

5. **Add the MCP tools seam to the activate script's status display** — Section 6 should show discovered MCP tools alongside the other 5 seams, maintaining the "activate is the seam registry" principle

---

## Summary for Coordinator

**v2 composability is strong.** The changes are compositionally clean because they follow the established patterns:

- **MCP Tools seam (#6)** is the cleanest new seam — filesystem convention, self-contained files, `get_tools()` protocol. It's algebraically composable: any tool that follows the protocol composes with any configuration.

- **Claudechic distribution mode** is a genuinely orthogonal axis — one pixi.toml line change, zero runtime leakage. Standard vs developer mode is a packaging concern, not a compositional one.

- **Bootstrap simplification** removes an axis (how to get copier) rather than adding one. Fewer axes = simpler crystal = fewer holes.

- **No new dirty seams introduced.** The only concern is the kwargs protocol in MCP tools, which should be explicitly documented as a stable interface.

- **Inherited v1 issues remain** (guardrails ↔ claudechic env var coupling, pattern miner ↔ role vocabulary), but these are out of v2 scope and lower priority.

**Recommended deep-dive:** The MCP Tool Protocol is the only area warranting detailed specification work — define kwargs, error handling, and the discovery mechanism precisely.
