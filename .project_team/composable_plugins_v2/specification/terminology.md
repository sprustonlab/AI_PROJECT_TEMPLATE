# Terminology — Composable Plugins v2

> **Canonical home for all project-level term definitions.**
> Other documents should reference this file, not redefine terms.
> Maintained by: TerminologyGuardian
>
> **Relationship to v1:** This file extends `composable_plugins/specification/terminology.md`. All v1 terms (Plugin, Feature, Module, Seam, Composable, Axis, Onboarding, Manifest, Guardrail, Hook, Component, System) remain canonical with the same definitions. This file adds terms introduced or refined in v2.

---

## New Terms in v2

### MCP Tool

A **Python file that exposes callable functions to Claude Code via the MCP (Model Context Protocol) interface.** Each MCP tool file lives in the `mcp_tools/` directory and is discovered at runtime by claudechic.

- Discovery contract: the file must define a `get_tools(**kwargs) -> list[tool_function]` function.
- kwargs provide optional wiring: `caller_name`, `send_notification`, `find_agent`.
- File presence = enabled. File deletion = disabled.

> **Not to be confused with:** *MCP server* (the process that hosts MCP tools; claudechic is the MCP server). An MCP tool is a single capability exposed through the server. Also not to be confused with *command* (a CLI executable in `commands/`; MCP tools are invoked by Claude Code, not by the user's shell).

---

### MCP Tools Seam (Seam #6)

The **sixth seam** added to AI_PROJECT_TEMPLATE, following the same "directory convention IS the plugin system" principle as the original five seams.

| Property | Value |
|----------|-------|
| **Directory** | `mcp_tools/` at project root |
| **Discovery** | claudechic's `mcp.py` scans for `.py` files with `get_tools()` at startup |
| **What you drop in** | A Python file implementing `get_tools(**kwargs) -> list[tool_function]` |

Passes the swap test: drop a `.py` file to add a tool, delete it to remove — no other file changes needed.

> **Canonical reference:** Seam #6 analysis (to be written in `specification/seam_mcp_tools.md`).

---

### Seam Contract

The **formal interface agreement** that defines what a file must expose to participate in a seam. Each seam has exactly one contract.

For the MCP tools seam: `get_tools(**kwargs) -> list[tool_function]`.

> This term was implicit in v1 (each seam section described its "Contract"). v2 promotes it to an explicit term because seam #6 introduces the first *function-level* contract (vs. v1's file-presence contracts).

---

### Standard Mode

The **default claudechic installation mode** where claudechic is a git URL dependency in `pixi.toml`:

```toml
claudechic = { git = "https://github.com/boazmohar/claudechic", branch = "main" }
```

Updates arrive via `pixi update`. The user does not have a local editable copy.

> **Contrast with:** *Developer mode*. These are the only two installation modes.

---

### Developer Mode

The **claudechic installation mode for contributors** who need to edit claudechic source. Claudechic is cloned locally into `submodules/claudechic/` as an editable install.

Switching between standard mode and developer mode is a one-line change in `pixi.toml`.

> **Not to be confused with:** any general "development" workflow. Developer mode refers exclusively to the claudechic installation strategy.

---

### Bootstrap

The **minimal set of steps to go from zero to a working project.** In v2, bootstrap requires exactly one dependency (pixi) and two commands:

1. Install pixi (platform-specific one-liner).
2. `pixi exec --spec copier copier copy <template-url> <project-name>`.

> **Not to be confused with:** *onboarding* (the interactive questionnaire that configures plugin choices). Bootstrap gets you to the point where onboarding can run. Bootstrap = prerequisites + project creation. Onboarding = configuration choices.

---

### Ephemeral Environment

A **temporary, disposable environment** created by `pixi exec --spec <pkg>` that exists only for the duration of a single command. Used in v2 bootstrap so Copier is never permanently installed.

> **Contrast with:** *named environment* (a persistent `[feature.<name>]` in `pixi.toml`, installed to `.pixi/envs/<name>/`).

---

### Cluster MCP

The **MCP tool providing LSF cluster job management**, shipped as `mcp_tools/cluster.py`. Provides tools: `cluster_jobs`, `cluster_status`, `cluster_submit`, `cluster_kill`, `cluster_logs`, `cluster_watch`.

- Toggled via Copier question (`use_cluster: bool`).
- Configuration in `.claudechic.yaml` (SSH target, poll interval, etc.).
- File presence = enabled.

> **Not to be confused with:** a general "cluster" concept. Cluster MCP is a specific MCP tool file. Future backends (SLURM, PBS, Kubernetes) would be separate MCP tool files, not extensions of Cluster MCP.

---

### Git URL Dependency

A **pixi/pip dependency specified by git repository URL** rather than a package registry (PyPI, conda-forge). In v2, claudechic uses this pattern:

```toml
claudechic = { git = "https://github.com/boazmohar/claudechic", branch = "main" }
```

> **Not to be confused with:** *git submodule* (a vendored copy of a repo tracked by git). A git URL dependency is resolved by the package manager at install time; a git submodule is a directory in the repo.

---

## Refined v1 Terms

### Seam (updated)

v1 defined five seams. v2 adds a sixth:

| # | Seam | Directory | Discovery |
|---|------|-----------|-----------|
| 1 | Environments | `pixi.toml` features | `activate` calls `pixi info` |
| 2 | Commands | `commands/` + `pixi.toml` tasks | `activate` adds to PATH |
| 3 | Skills | `.claude/commands/` | Claude Code auto-discovers |
| 4 | Agent Roles | `AI_agents/**/*.md` | Coordinator reads |
| 5 | Guardrail Rules | `.claude/guardrails/rules.yaml` (+ `rules.d/`) | `generate_hooks.py` reads |
| **6** | **MCP Tools** | **`mcp_tools/`** | **claudechic `mcp.py` scans** |

> The canonical definition of "seam" (interface where two independent systems meet, passes the swap test) is unchanged from v1.

---

### Hook (updated)

v1 defined two hook types. v2 does not add a third, but note: MCP tool discovery is **not** a hook — it is a seam. Do not call `get_tools()` a "hook."

1. **Guardrail hooks** — generated scripts intercepting Claude Code tool calls.
2. **Lifecycle hooks** — scripts at workflow points (e.g., `setup_ao_mode.sh`).

> `get_tools()` is a **seam contract**, not a hook. A hook intercepts an existing flow; a seam contract defines an interface for discovery.

---

### Plugin (clarification for v2)

In v2, "plugin" still means a self-contained, independently enableable unit. However, note:

- **claudechic itself is NOT a plugin** — it is infrastructure (the MCP server, the base). Calling claudechic a "plugin" is incorrect.
- **An MCP tool file IS a plugin** — it is independently enableable, passes the swap test, and lives in a seam directory.
- **Cluster MCP is a plugin** — `mcp_tools/cluster.py` is an independently enableable unit.

---

## Synonym Watch List (v2 additions)

| Observed variant | Canonical term | When to use the variant |
|-----------------|---------------|------------------------|
| "MCP server" (for a tool file) | **MCP tool** | Only when referring to the claudechic process hosting the tools |
| "git dependency" | **git URL dependency** | Never — always include "URL" to distinguish from git submodule |
| "dev mode" | **developer mode** | Acceptable shorthand in casual context, but "developer mode" in docs |
| "standard install" | **standard mode** | Never — use "standard mode" for consistency with "developer mode" |
| "cluster tools" | **Cluster MCP** | Never — "Cluster MCP" is the canonical name for the `mcp_tools/cluster.py` plugin |
| "tool file" | **MCP tool** | Acceptable when context is unambiguous, but prefer "MCP tool" |
| "seam 6" / "sixth seam" | **MCP Tools seam** | Acceptable as shorthand when the six-seam table is in context |

---

## Terminology Hygiene Rules

All v1 rules remain in force. v2 adds:

| Rule | Rationale |
|------|-----------|
| **MCP tool ≠ MCP server** | A tool is a capability; the server hosts capabilities. claudechic is the server. `cluster.py` is a tool. |
| **Standard mode ≠ Developer mode** | These are the only two installation modes. Do not invent others ("production mode," "user mode"). |
| **Bootstrap ≠ Onboarding** | Bootstrap = get prerequisites + create project. Onboarding = configure choices. Sequential, not synonymous. |
| **Git URL dependency ≠ Git submodule** | URL dep = package manager resolves at install time. Submodule = directory tracked by git. Developer mode uses a submodule; standard mode uses a git URL dependency. |
| **Seam contract ≠ Hook** | A seam contract defines an interface for discovery. A hook intercepts an existing flow. `get_tools()` is a contract, not a hook. |

---

*Last updated: 2026-03-30 by TerminologyGuardian*
