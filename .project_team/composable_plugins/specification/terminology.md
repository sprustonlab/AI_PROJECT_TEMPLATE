# Terminology — Composable Plugins Project

> **Canonical home for all project-level term definitions.**
> Other documents should reference this file, not redefine terms.
> Maintained by: TerminologyGuardian

---

## Core Terms

### Plugin

A **self-contained, independently enableable unit of functionality** within AI_PROJECT_TEMPLATE. A plugin:

- Can be added or removed without breaking other plugins.
- Declares its own dependencies and configuration.
- Communicates with other plugins only through defined **seams**.
- Is the unit of choice during **onboarding** — users select which plugins they want.

**Examples:** Python env management, Claudechic, Project Team, Guardrails, Pattern Miner.

> **Not to be confused with:** *feature* (a user-visible capability; a plugin *delivers* one or more features) or *module* (a code-organization unit; a plugin *contains* one or more modules).

---

### Feature

A **user-visible capability** — something a user can do or benefit from. Features are described in terms of value to the user, not in terms of implementation.

- A plugin delivers one or more features.
- A feature lives inside exactly one plugin (no cross-plugin features).
- During onboarding, features are how we *describe* what a plugin provides; the plugin is what actually gets installed.

**Example:** "Reproducible Python environments" is a feature delivered by the *Python env management* plugin.

> **Key distinction:** Feature = *what the user gets*. Plugin = *what gets installed*. A plugin is a deployable unit; a feature is a value proposition.

---

### Module

A **code-organization unit** — a Python module, directory, or file that groups related implementation. Modules are an *internal* concern of a plugin.

- Each plugin contains one or more modules.
- Module boundaries enforce separation *within* a plugin (e.g., no circular imports between modules handling different axes).
- Modules are not user-facing; users never "install a module."

**Do not confuse with:**
- **Plugin** — the installable unit (contains modules).
- **Git submodule** — an external repository vendored via `git submodule` (e.g., `submodules/claudechic`). Always write "git submodule" or "submodule" (never bare "module") when referring to this.

---

### Seam

The **interface where two independent systems (or plugins) meet**, designed so that data crosses the boundary but assumptions and implementation details do not.

A clean seam passes the **swap test**: you can replace one side without changing anything on the other side.

**What crosses a clean seam:** data, well-defined interfaces/protocols, agreed-upon formats.
**What must NOT cross:** implementation details, assumptions about the other side, type-specific branching logic.

**Signs of a dirty seam:**
- `if isinstance(x, SpecificType):` on the wrong side of the boundary.
- Imports reaching across plugin boundaries.
- Changing one plugin forces changes in another.

> **Relationship to "module boundary":** A module boundary is an *internal* seam within a plugin. A seam (unqualified) refers to the *external* interface between plugins or between a plugin and the template core.

**Canonical reference:** `AI_agents/project_team/COMPOSABILITY.md` §Seam (lines 87–151).

---

### Composable / Composability

- **Composable** (adjective): A system where choices along independent dimensions (axes) can be freely mixed and matched without interference.
- **Composability** (noun): The architectural property that enables true composition — not forced bundling.

A composable plugin system means: any valid subset of plugins can be enabled together, and each plugin works correctly regardless of which others are present.

**Canonical reference:** `AI_agents/project_team/COMPOSABILITY.md`.

---

### Axis (plural: Axes)

An **independent dimension of variation** in the system. Each axis represents a choice that is orthogonal to other axes — changing one does not constrain the others.

**Example:** In a data system: Format (Arrow / Parquet / CSV) × Backend (mmap / sqlite / S3) × Caching (on / off). Each is an axis.

**In this project:** Each plugin roughly corresponds to an axis of the template's functionality, though some plugins may share an axis (this is a design smell worth investigating).

---

### Onboarding

The **interactive first-run experience** where a new user configures their repository by selecting which plugins to enable and optionally pointing to an existing codebase to wrap.

May be web-based, Claude-conversation-based, or both. Onboarding is the *process*; the result is a configured repository with the chosen plugins installed.

---

### Manifest

A **declarative file that describes a plugin's metadata**: name, version, dependencies on other plugins, files it provides, configuration schema, and seam contracts it implements or requires.

> **Status:** Not yet used in the codebase. Introduced here as the canonical term for plugin metadata declarations. The exact format (JSON, YAML, TOML) is a design decision for the architecture phase.

---

## Supporting Terms

### Guardrail

The **permission system** that enforces role × action rules via hooks. "Guardrail" refers to the *system as a whole* (rules + generation + enforcement + hooks).

- **Guard** (`role_guard.py`): The runtime module that checks permissions.
- **Guardrail hook**: A generated shell script that intercepts a tool call and invokes the guard.
- **Rule** (`rules.yaml`): A declarative permission entry (role + action + enforcement level).

> Use "guardrail system" or "guardrails" for the whole subsystem. Use "guard" only when referring to `role_guard.py` specifically. Use "hook" only for the interception mechanism.

---

### Hook

An **interception point in an execution flow** where custom logic runs. In this project, hooks have two distinct meanings:

1. **Guardrail hooks** — generated shell scripts that intercept Claude Code tool calls (bash, write, read, spawn_agent) before execution. Defined via `generate_hooks.py`, enforced by `role_guard.py`.
2. **Lifecycle hooks** — scripts that run at specific points in a workflow (e.g., `setup_ao_mode.sh`, `teardown_ao_mode.sh`).

> Always qualify which kind of hook you mean. Bare "hook" is ambiguous.

---

### Component

A **general-purpose label** for a major part of the system. The README currently names three main components: claudechic, project-team, and Python environment management.

> **Deprecation recommendation:** As the plugin architecture matures, prefer "plugin" over "component" for any unit that can be independently enabled. Reserve "component" only for non-plugin infrastructure (e.g., the plugin loader itself, the onboarding system).

---

### System

An **informal collective noun** for an integrated whole (e.g., "guardrail system," "plugin system"). Not a precise architectural term.

> Avoid bare "system" without qualification. Always say *which* system.

---

## Terminology Hygiene Rules

| Rule | Rationale |
|------|-----------|
| **One name, one meaning** | No synonyms (don't alternate "plugin" / "component" / "feature" for the same thing). No overloading (don't use "module" for both Python modules and git submodules). |
| **One canonical home** | Every term is defined here. Other documents reference this file. |
| **Qualify ambiguous terms** | "hook" → "guardrail hook" or "lifecycle hook." "module" → "Python module" or "git submodule." "seam" → "plugin seam" or "internal module boundary." |
| **Feature ≠ Plugin ≠ Module** | Feature = user value. Plugin = installable unit. Module = code organization. These are three different levels of abstraction. |
| **Newcomer test** | If a newcomer reading a document encounters a term not defined or linked, that's a bug. |

---

## Synonym Watch List

These terms have been observed drifting toward synonymy. The canonical term is on the right.

| Observed variant | Canonical term | When to use the variant |
|-----------------|---------------|------------------------|
| "component" | **plugin** | Only for non-plugin infrastructure |
| "feature" (as installable unit) | **plugin** | Only when describing user-facing value |
| "module" (as installable unit) | **plugin** | Only for code-organization units *within* a plugin |
| "system" (unqualified) | *(always qualify)* | Never use bare "system" |
| "boundary" | **seam** | "module boundary" for internal; "seam" for plugin-level |

---

*Last updated: 2026-03-29 by TerminologyGuardian*
