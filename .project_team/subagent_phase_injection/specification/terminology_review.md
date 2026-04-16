# Terminology Review: SPEC.md (Issue #37)

> Reviewed by Terminology Guardian against `terminology_report.md` glossary.
> Spec file: `.project_team/subagent_phase_injection/SPEC.md`

---

## Overall Assessment

The spec explicitly references the terminology report and uses canonical terms
consistently throughout. Composability has done strong terminology work. I found
**3 issues to fix**, **4 minor suggestions**, and **2 codebase convention
concerns**. No blockers.

---

## Issues to Fix

### 1. "agent prompt injection" (line 85) -- Overloaded Term

**Quoted text (line 85):**
> `"...Set type= to a role folder name to enable agent prompt injection."`

**Problem:** "injection" is triple-overloaded per the glossary (filesystem
injection, spawn-time injection, guardrails `Injection` dataclass). The warning
message seen by the coordinator agent should not use bare "injection."

**Fix:** Replace with:
```
"...Set type= to a role folder name so this agent receives its role-specific
phase instructions at spawn and on phase transitions."
```

This avoids "injection" entirely in user-facing text and is clearer to the
coordinator about *what* it's missing.

---

### 2. "roles" YAML field (line 253) vs Codebase Convention

**Quoted text (line 253):**
```yaml
roles: [coordinator]
```

**Problem:** The existing `project_team.yaml` (line 57) already uses `roles:`
and this is consistent. However, the terminology report's glossary and the
existing `terminology.md` (line 76-78) document the field names as
`block_roles` and `allow_roles`. The existing codebase uses bare `roles:` as
shorthand for `block_roles:` (confirmed in `project_team.yaml` line 57).

**This is fine** -- `roles:` is the actual YAML field name in the existing
codebase. The `block_roles`/`allow_roles` distinction in `terminology.md` is
the *conceptual* documentation. No change needed, but note the discrepancy
for future terminology.md updates: the YAML field is `roles:` (equivalent to
`block_roles`), and `allow_roles:` is the inverse. This should be documented
in terminology.md.

**Action:** No change to SPEC.md. Flag for terminology.md update:
> "`roles:` in YAML is shorthand for `block_roles:`. The inverse is
> `allow_roles:`. Both restrict which agent roles a rule applies to."

---

### 3. "Role type" in agent_manager.py Docstring (line 140 of agent_manager.py)

**Quoted text (agent_manager.py line 140):**
> `agent_type: Role type (e.g. "Implementer") -- injected as CLAUDE_AGENT_ROLE`

**Problem:** The glossary says DO NOT USE "role type" (listed as redundant).
The canonical term is **role**. Also, the example `"Implementer"` uses
TitleCase, but all role folder names are lowercase (`implementer`, `skeptic`,
`coordinator`). This is a pre-existing issue but the spec should note it
for the implementer to fix alongside the `agent_type` storage change.

**Recommended fix for agent_manager.py docstring:**
```python
agent_type: Agent's role name (e.g. "implementer") -- matches the role
    folder under workflows/{workflow}/ and is set as CLAUDE_AGENT_ROLE env var.
```

---

## Minor Suggestions

### A. "typed sub-agents" (line 153 comment) -- Acceptable but Could Be Clearer

**Quoted text (line 153):**
```python
# Broadcast phase update to all typed sub-agents
```

**Assessment:** "typed" means "has `agent_type` set." This is clear in context
but could be misread as "statically typed" or "type-annotated." Consider:
```python
# Broadcast phase update to all sub-agents that have a role
```

This uses the canonical "role" term directly.

---

### B. "agent prompt" vs "phase instructions" -- Slight Inconsistency

The spec uses both:
- Line 178: `"Your updated phase instructions:\n\n"` (in broadcast message)
- Line 11: "agent prompt (assembled identity file + phase file)"

The broadcast message says "phase instructions" but what's delivered is the
full **agent prompt** (identity + phase file). For a sub-agent receiving this
mid-conversation, "phase instructions" is arguably more intuitive than "agent
prompt" (which sounds like a system prompt). **This is acceptable** -- the
broadcast message is a user-facing chat message, not a technical document.
The spec's terminology header correctly defines "agent prompt" for technical
use.

**No change needed.** Just noting the intentional distinction between
technical terminology (spec text) and agent-facing language (chat messages).

---

### C. "exclude_phases" (line 271) vs "exclude_phases" in Existing Rules

**Quoted text (line 271):**
```yaml
exclude_phases: [signoff]
```

**Existing usage (project_team.yaml line 65):**
```yaml
exclude_phases: [testing, documentation, signoff]
```

**Assessment:** Consistent. The field name `exclude_phases` matches the
existing codebase convention. Good.

---

### D. Comment in Code: "agent prompt" Variable Named `folder_prompt`

**Quoted text (line 168):**
```python
agent_prompt = assemble_phase_prompt(...)
```

**Assessment:** Excellent. The spec correctly uses `agent_prompt` as the
variable name (matching the glossary), unlike the existing `mcp.py` which
uses `folder_prompt` (line 276). The implementer should also rename the
existing `folder_prompt` in `spawn_agent` to `agent_prompt` for consistency.

**Recommendation for implementer:** When modifying `mcp.py`, also rename
`folder_prompt` (line 276) to `agent_prompt` in `spawn_agent`.

---

## Codebase Convention Verification

### Rule ID Naming

| Proposed Rule ID | Convention Check | Verdict |
|---|---|---|
| `spawn_agent_requires_type` | snake_case, descriptive, matches `no_direct_code_coordinator`, `no_push_before_testing`, `no_force_push` pattern | OK -- but existing IDs use `no_` prefix for prohibitions. This rule is a requirement, not a prohibition. `spawn_agent_requires_type` is appropriate for a "must do X" rule. |
| `no_close_leadership` | `no_` prefix + snake_case, matches existing `no_force_push`, `no_push_before_testing` | OK |

### YAML Field Names

| Field | Matches Existing? | Verdict |
|---|---|---|
| `trigger: PreToolUse/mcp__chic__spawn_agent` | Yes -- existing rules use `PreToolUse/Bash`, `PreToolUse/Write` | OK |
| `enforcement: warn` | Yes -- existing `warn_sudo` uses `warn` | OK |
| `detect.pattern` + `detect.field` | Yes -- existing rules use `detect.pattern` | OK |
| `roles: [coordinator]` | Yes -- line 57 of existing project_team.yaml | OK |
| `exclude_phases: [signoff]` | Yes -- line 65 of existing project_team.yaml | OK |

### Function/Method Names

| Proposed | Convention Check | Verdict |
|---|---|---|
| `Agent.agent_type` attribute | Matches `Agent.worktree` pattern (optional metadata stored on instance). Not a property, just an attribute. | OK |
| `_send_prompt_fire_and_forget` (reused) | Already exists in mcp.py | OK |
| `assemble_phase_prompt` (reused) | Already exists in agent_folders.py | OK |

### `__raw__` Pseudo-Field (line 56)

The spec proposes `field: __raw__` for JSON-serialized tool input matching.
**This does not exist in the current codebase.** The `detect.field` currently
only supports named fields from tool input (e.g., `command` for Bash). The
spec correctly identifies this as a problem and recommends the code-level
warning approach instead (lines 76-89). Good self-correction. If the guardrail
approach is pursued later, `__raw__` would need to be implemented in the
detect matching logic.

---

## Summary of Required Actions

| # | Severity | Location | Action |
|---|---|---|---|
| 1 | Fix | SPEC.md line 85 | Replace "agent prompt injection" with non-overloaded phrasing |
| 2 | Note | terminology.md | Document that YAML `roles:` = `block_roles` shorthand |
| 3 | Fix | SPEC.md / agent_manager.py | Change "Role type" to "role" in docstring; fix "Implementer" -> "implementer" |
| A | Suggestion | SPEC.md line 153 | "typed sub-agents" -> "sub-agents that have a role" |
| D | Suggestion | Implementation note | Rename existing `folder_prompt` -> `agent_prompt` in spawn_agent |

---

## Newcomer Simulation

Reading the spec as a newcomer who has NOT read the terminology report:

1. **Line 7-11 (terminology header):** Excellent. Defines key terms upfront with
   a reference to the full glossary. A newcomer knows exactly where to look.

2. **"spawn prompt" (line 10):** Defined in the header. Clear.

3. **"in-band delivery" (line 108):** Used without inline definition. The
   terminology report defines it, but a newcomer reading only the spec might
   not know this means "via chat message." Consider adding "(via chat message)"
   parenthetically on first use.

4. **"fire-and-forget" (line 108, 389):** Used as an implementation detail.
   Clear enough from context (non-blocking send), but the terminology report's
   warning about conflating implementation pattern with communication semantics
   is relevant here.

5. **"PostCompact re-injection" (line 228, 395):** A newcomer might not know
   what `/compact` is. The spec doesn't explain it, but this is appropriate --
   the spec is for the implementation team, not end users.

**Verdict:** Accessible to a contributor who reads the terminology header and
follows the glossary link. No blockers for the target audience.
