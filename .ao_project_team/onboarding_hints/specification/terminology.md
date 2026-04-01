# Terminology Glossary: Hints System

> **Canonical home** for all terms used in this feature.
> Other documents must reference this file, not redefine terms.

---

## Core System Terms

### Hint
A short, contextual message surfaced to the user via a toast notification.
- **Use:** "hint" (noun), "surface a hint" (verb)
- **Do NOT use:** "tip", "suggestion", "advisory", "nudge", "message" (too generic)
- **Example:** *"No git repo detected -- spawn a Git agent to set one up"*

### Trigger
A boolean condition evaluated at a defined point (e.g., app startup, session start) that determines whether a hint should be shown.
- **Use:** "trigger" (noun), "trigger fires" (verb)
- **Do NOT use:** "check", "condition", "detector", "probe"
- **A trigger returns** `True` (fire the hint) or `False` (suppress it).

### Hint Registry
The declarative data structure (YAML or Python dict) that maps triggers to hints. Each entry is a **hint definition**.
- **Use:** "hint registry"
- **Do NOT use:** "hint config", "hint database", "hint store", "message registry"

### Hint Definition
A single entry in the hint registry. Contains: trigger, message text, category, and metadata.
- **Use:** "hint definition"
- **Do NOT use:** "hint rule", "hint record", "hint entry"

### Hints System
The toggleable system that owns the entire hint pipeline. Lives in the `hints/` folder in the generated project. Users can enable/disable it via `/hints off` and `/hints on`.
- **Canonical name:** "hints system" (or just "hints" in casual usage)
- **State file:** `.claude/hints_state.json` (activation + lifecycle sections)
- **Slash command:** `/hints` (unified entry point for browse, on/off, status, reset)
- **Folder:** `hints/` (top-level, alongside `mcp_tools/`)
- **Copier question:** `use_hints` (default `true`)
- **Do NOT use:** "onboarding", "onboarding skill", "hint skill", "discovery skill", "onboarding system"
- **Note:** The system was originally named "onboarding" but renamed because hints are not just for new users — they surface throughout the project lifecycle (e.g., Pattern Miner hint after 10+ sessions).

---

## Notification Terms

### Toast Notification
The transient UI element rendered by Textual's `self.notify()` method. Appears briefly, then auto-dismisses.
- **Use:** "toast notification" or just "toast" in casual context
- **Do NOT use:** "popup", "alert", "banner", "flash message"
- **Implementation:** `self.notify(message, severity=..., timeout=...)`
- **Severity levels:** `"information"` (default for hints), `"warning"`, `"error"`

### Session
One continuous run of ClaudeChic (from app launch to exit). Hint frequency is scoped per session.
- **Use:** "session"
- **Budget:** 1-2 toasts per session (not more).

---

## Feature Names (What Hints Surface)

These are the existing features that hints make discoverable. Use ONLY these canonical names.

| Canonical Name | Do NOT Use | What It Is |
|---|---|---|
| **Git agent** | "git setup agent", "Git spawner" | The agent spawned to initialise a git repository |
| **Guardrails** | "rules", "guards", "safety checks" | The `.claude/guardrails/` system (rules.yaml + hooks) |
| **Project Team** | "multi-agent team", "AI team", "agent team" | The `/ao_project_team` multi-agent workflow system |
| **Pattern Miner** | "pattern mining", "correction miner", "mine_patterns" | The `scripts/mine_patterns.py` 3-tier detection pipeline |
| **MCP tools** | "custom tools", "tool plugins" | User-defined tools dropped into `mcp_tools/` directory |
| **Cluster backend** | "HPC", "SLURM tools", "LSF tools" | The cluster integration via `mcp_tools/slurm.py` or `lsf.py` |

### Naming Notes

- **Pattern Miner** vs `mine_patterns.py`: "Pattern Miner" is the user-facing feature name. `mine_patterns.py` is the script filename. Hints should say "Pattern Miner", not reference the script.
- **ClaudeChic** vs "Claude Chic": The package is `claudechic` (no space). The display title is `"Claude Chic"` (with space). In hint text aimed at users, use "Claude Chic" (display form).
- **MCP tools**: Always lowercase "tools". The prefix `mcp__chic__` is an implementation detail; never expose it in hints.

---

## Lifecycle / Evaluation Terms

### Trigger Point
The moment when triggers are evaluated. Defined trigger points:
- **`app_start`** -- when ClaudeChic launches
- **`session_start`** -- when a new conversation session begins
- (extensible: future trigger points can be added)
- **Do NOT use:** "hook point", "check point", "event"
- **Note:** Do not confuse with guardrails "hooks" (generated Python files in `.claude/guardrails/hooks/`). Those are a separate system.

### Dismissal
When a user has seen a hint and it should not repeat.
- **Use:** "dismissed"
- **Do NOT use:** "acknowledged", "seen", "consumed", "completed"

### Hint State
Persistent record of which hints have been dismissed, stored per-project. Lives in `.claude/hints_state.json`.
- **Use:** "hint state"
- **Do NOT use:** "hint history", "hint log", "hint cache"

### Command Lesson
A special hint category (priority 4) that teaches one slash command per session. Rotates through commands the user hasn't tried.
- **Use:** "command lesson" (concept), `CommandLesson` (type name), `COMMAND_LESSONS` (registry constant)
- **Do NOT use:** "command tip", "command hint", "command discovery hint"
- **Priority:** Always 4 (lowest tier — never displaces state-triggered hints)
- **Lifecycle:** Single rotating `learn-command` hint with `taught_commands` tracking in state
- **Format:** "Try /command — [when you'd use it]" (explain the *moment*, not the mechanics)

### Priority Tiers
Static priority levels assigned to each hint definition (lower = higher priority):
| Tier | Category | Example |
|------|----------|---------|
| 1 | **Blocking setup** — project can't function well | Git repo missing |
| 2 | **High-value discovery** — high impact, low discoverability | Guardrails, Project Team |
| 3 | **Enhancement** — nice-to-know, not urgent | Custom tools, Pattern Miner, Cluster |
| 4 | **Command lesson** — teach a slash command | `/resume`, `/diff`, `/shell` |

---

## Terminology Review

### Synonyms Resolved
- "tip" / "suggestion" / "nudge" / "hint" --> **"hint"** everywhere
- "check" / "condition" / "trigger" --> **"trigger"** everywhere
- "plugin" / "skill" --> **"skill"** for this feature (a skill lives inside a plugin)
- "notification" / "toast" / "popup" --> **"toast notification"** (or "toast")

### Overloaded Terms Disambiguated
- **"hook"**: In guardrails = generated Python enforcement script. In the hints system = NOT used. Use **"trigger"** instead.
- **"message"**: In ClaudeChic internals = Textual Message subclass (e.g., `SystemNotification`). In the hints system = NOT used for hint text. Use **"hint"** for the content, **"toast"** for the UI element.
- **"onboarding"**: Retired name for this system. Do NOT use. The system is called "hints" because it's not limited to new-user onboarding — hints surface throughout the project lifecycle.
- **"discovery"**: Could mean "feature discovery" (user learning) or "skill/tool discovery" (runtime scanning). In this feature, use **"feature discovery"** explicitly when referring to the user-facing goal. Use **"skill discovery"** or **"tool discovery"** for runtime scanning (existing `discover_skills()`, `discover_mcp_tools()` functions).

### Newcomer Blockers Addressed
- "MCP" is jargon. Hints referencing MCP tools should say *"custom tools in `mcp_tools/`"*, not mention MCP by name.
- "Pattern Miner" should briefly explain what it does on first mention: *"Run the Pattern Miner to find recurring corrections in your sessions"*.
- `/ao_project_team` should be introduced as: *"Try `/ao_project_team` to launch a multi-agent team for complex tasks"*.
