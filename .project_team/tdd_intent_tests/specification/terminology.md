# Terminology — TDD Intent Tests Initiative

> Canonical definitions for every domain term in this initiative.
> **Rule:** Use these names exactly. Do not introduce synonyms.

---

## Core Terms

### Intent-Based Test
**Definition:** An integration test that exercises a full end-to-end user workflow — scaffolding a project with copier into a temp directory, then running a real command through Claude Code — and asserts on the *observable outcome* (e.g., "guardrail blocks a forbidden action") rather than on internal implementation details.

**Contrast with:** Unit tests that mock dependencies and validate components in isolation. Unit tests can all pass while the system is broken end-to-end. Intent-based tests prove the system *works as a user would experience it*.

**Canonical home:** Test files under `tests/` that follow this pattern.

---

### Guardrail
**Definition:** The enforcement mechanism that restricts what actions an AI agent can perform based on its role. Comprises five parts:

| Component | File(s) | Purpose |
|-----------|---------|---------|
| Rules | `.claude/guardrails/rules.yaml` | Declarative role × action permission matrix |
| Generator | `.claude/guardrails/generate_hooks.py` | Reads rules, emits hook scripts |
| Hook scripts | `.claude/guardrails/hooks/` | Auto-generated Python interceptors that check permissions at runtime |
| Runtime library | `.claude/guardrails/role_guard.py` | Shared role-checking logic |
| **Registration** | `.claude/settings.json` | Hook entries that tell Claude Code to *invoke* the hook scripts |

**Do not say:** "guard", "rule system", "permission system" when you mean the full guardrail mechanism.

---

### Guardrail Wiring
**Definition:** The act of registering generated hook scripts in `.claude/settings.json` so that Claude Code actually invokes them. Without wiring, hook scripts exist on disk but are never called — guardrails are "unwired" and silently inactive.

**The core bug this initiative addresses:** Guardrails are fully generated but not wired. All unit tests pass, yet guardrails never fire in practice.

---

### Settings Merge
**Definition:** The strategy for updating `.claude/settings.json` to add guardrail hook registrations *without destroying* pre-existing user configuration (custom `mcpServers`, `permissions`, other hooks).

**Requirements:**
- Deep-merge nested objects (e.g., add to `hooks.PreToolUse[]` without replacing the array).
- Preserve all existing keys and values the user has set.
- Must be **idempotent** (see below).

**Do not say:** "settings update", "settings write", "config patch" — use **settings merge**.

---

### Idempotent Merge
**Definition:** A merge operation that produces the same result whether run once or many times. Concretely: if `generate_hooks.py` is run twice, `settings.json` must not contain duplicate hook entries. The merge checks for existing entries by a unique key before adding.

**Why it matters:** `copier update` can re-run post-generation tasks. The merge must be safe to repeat.

---

### TUI (Terminal User Interface)
**Definition:** In this project, refers specifically to **Claudechic** — a Textual-based terminal wrapper around Claude Code. The TUI:
1. Launches and manages Claude Code sessions.
2. Injects environment variables (`CLAUDE_AGENT_NAME`, `CLAUDE_AGENT_ROLE`, `CLAUDECHIC_APP_PID`) that guardrails depend on at runtime.

**Do not say:** "the terminal", "the wrapper", "the app" — use **TUI** or **Claudechic**.

---

### Copier
**Definition:** The project scaffolding tool (Python package `copier`) that generates a new project from this template. It reads `copier.yml`, prompts the user with questions, renders Jinja2 templates, and runs post-generation tasks (e.g., `generate_hooks.py`).

**Key behaviors relevant to this initiative:**
- `copier copy` — initial project generation.
- `copier update` — re-applies template changes to an existing project (triggers post-generation tasks again, hence the need for idempotent merge).
- Conditional file inclusion based on user answers (e.g., `cluster_scheduler` choice).

**Do not say:** "scaffolder", "template engine", "generator" — use **copier**.

---

### Red/Green TDD
**Definition:** The development workflow for this initiative:

1. **Red:** Write a test that *fails today*, proving a feature is broken or unwired (e.g., "assert guardrail blocks file deletion for read-only role" → fails because hooks aren't registered in settings.json).
2. **Green:** Write the minimum code fix to make the failing test pass (e.g., add settings merge logic to `generate_hooks.py`).

**Rule:** No code fix is written until a failing test proves the defect. The failing test is the *specification*.

---

### Hooks Registration
**Definition:** The process of adding hook entries to the `hooks` section of `.claude/settings.json`. Each entry maps a Claude Code lifecycle event (e.g., `PreToolUse`, `PostToolUse`) to a hook script path and matcher pattern.

**Contrast with:** Hook *generation* (creating the `.py` script files). Registration is the missing step — scripts are generated but not registered.

**Do not say:** "hook setup", "hook config", "hook installation" — use **hooks registration**.

---

### Hook Script
**Definition:** An auto-generated Python file in `.claude/guardrails/hooks/` that is invoked by Claude Code at a specific lifecycle event. It calls `role_guard.py` to check whether the current agent's role permits the requested action.

**Do not confuse with:** Hooks registration (the settings.json entries that *point to* hook scripts).

---

### Session Marker
**Definition:** A file at `.claude/guardrails/sessions/ao_<PID>` that indicates team mode is active for a given TUI session. Contains JSON with the coordinator's agent name (e.g., `{"coordinator": "Coordinator"}`). Created by `setup_ao_mode.sh`, removed by `teardown_ao_mode.sh`.

**Why it matters:** `role_guard.py` checks for a session marker to determine whether to enforce role-gated rules. Without a session marker, role_guard treats the session as solo mode and skips role-based enforcement.

**Do not say:** "marker file", "session file", "team flag" — use **session marker**.

---

## Secondary Terms

### settings.json
**Definition:** Claude Code's project-level configuration file at `.claude/settings.json`. Contains `mcpServers`, `permissions`, and `hooks` sections. This is the file that hooks registration targets.

**Do not say:** "config file", "claude config", "project settings" — use **settings.json**.

---

### rules.yaml
**Definition:** The declarative file at `.claude/guardrails/rules.yaml` that defines which roles can perform which actions. Source of truth for guardrail permissions. Read by `generate_hooks.py` to produce hook scripts.

---

### generate_hooks.py
**Definition:** The code generator at `.claude/guardrails/generate_hooks.py` that reads `rules.yaml` and emits hook scripts. Currently generates scripts but does **not** perform hooks registration in settings.json — this is the gap to fix.

---

## Terminology Smells to Watch

| Smell | Risk | Mitigation |
|-------|------|------------|
| "hooks" alone | Ambiguous — hook scripts? hooks registration? hook entries? | Always qualify: "hook scripts", "hooks registration", "hook entries in settings.json" |
| "settings" alone | Could mean settings.json, copier settings, or project config | Always say "settings.json" for the Claude Code config file |
| "merge" alone | Could mean git merge, dict merge, settings merge | Always say "settings merge" for the settings.json update strategy |
| "wiring" alone | Vague without context | Always say "guardrail wiring" |
| "test" alone | Unit test? Intent-based test? | Qualify: "intent-based test" vs "unit test" |
