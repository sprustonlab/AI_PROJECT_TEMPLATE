# Terminology Report: Sub-agent Phase Injection (Issue #37)

> Produced by Terminology Guardian. Canonical reference for all naming
> decisions in this issue. Other issue documents should reference, not
> duplicate, these definitions.

---

## 1. Glossary of Canonical Terms

### Agent Hierarchy

| Canonical Term | Definition | DO NOT USE |
|---|---|---|
| **coordinator** | The main agent whose role matches `main_role` in the workflow manifest. Receives `phase_context.md` via the filesystem. | "main agent" (ambiguous with AgentManager's first agent), "parent agent" |
| **sub-agent** | Any agent spawned by the coordinator (or by another sub-agent) via `spawn_agent`. Has its own chat view and SDK client. Hyphenated. | "child agent", "spawned agent" (too generic), "subagent" (no hyphen) |
| **role** | The identity of an agent, derived from its agent folder name (e.g. `coordinator`, `implementer`, `skeptic`). Set via the `type` parameter of `spawn_agent`. | "role type" (redundant), "agent type" (overloaded -- `type` is the spawn parameter name) |

**Note on "spawned agent":** The codebase uses "spawned agent" in test comments (`test_yolo_flag.py`) and `is_spawn=True` as an internal flag. These are acceptable as *descriptions* ("the agent that was spawned") but not as a *term*. The term is **sub-agent**.

**Note on "subagent" vs "sub-agent":** Claude Code's SDK uses `subagent_type` (no hyphen) for the Task tool's built-in sub-agents. claudechic's multi-agent system is different -- these are full agents, not Task sub-agents. Use **sub-agent** (hyphenated) for claudechic agents to distinguish from SDK's `subagent` concept. The codebase already uses "sub-agent" in `corrections_report.json` (`session_type: "sub-agent"`) and STATUS.md.

---

### Prompt Assembly

| Canonical Term | Definition | Code Location | DO NOT USE |
|---|---|---|---|
| **identity file** | `identity.md` in an agent folder. Cross-phase content, always loaded. | `agent_folders.py:61` | "identity prompt", "role prompt" |
| **phase file** | `{phase}.md` in an agent folder (e.g. `specification.md`). Phase-specific instructions. Loaded only during that phase. | `agent_folders.py:67-73` | "phase markdown" (ambiguous), "phase instructions" (too vague), "phase prompt" (confusing with assembled result) |
| **agent prompt** | The assembled result: identity file + phase file, concatenated with `---` separator. This is what the agent actually receives. | `agent_folders.py:48-77` (`_assemble_agent_prompt`) | "role prompt", "system prompt" (overloaded), "full prompt" |
| **phase context** | The `phase_context.md` file written to `.claude/` for the coordinator only. Contains the agent prompt for the `main_role`. Read by Claude Code as part of the system prompt. | `app.py:1708-1736` (`_write_phase_context`) | "phase context file" (redundant -- "phase context" already implies the file) |

**Critical distinction:** `phase_context.md` is the *coordinator's* delivery mechanism (filesystem). Sub-agents receive their agent prompt via `spawn_agent`'s prompt parameter (in-band). These are the same *content* but different *delivery paths*.

---

### Content Delivery Mechanisms

| Canonical Term | Definition | Used For | Code Location |
|---|---|---|---|
| **filesystem injection** | Writing `phase_context.md` to `.claude/` so Claude Code reads it as system prompt context. | Coordinator only. | `app.py:1708` (`_write_phase_context`) |
| **spawn-time injection** | Prepending the agent prompt to the spawn prompt before sending to a new sub-agent. | Sub-agents at creation. | `mcp.py:268-289` (in `spawn_agent`) |
| **in-band delivery** | Sending content via `tell_agent` / `ask_agent` / `interrupt_agent` as a chat message. | Ad-hoc updates to running agents. | `mcp.py:118-156` (`_send_prompt_fire_and_forget`) |
| **PostCompact re-injection** | A hook that re-assembles and re-injects the agent prompt after `/compact` discards context. | Any agent with a registered PostCompact hook. | `agent_folders.py:105-146` |

**DO NOT USE:** "auto-injection" (ambiguous -- which mechanism?), "manual delivery" (vague), "push-based" vs "pull-based" (the spec's "pull-based" description is inaccurate -- spawn-time injection is push-based).

---

### Spawn Concepts

| Canonical Term | Definition | DO NOT USE |
|---|---|---|
| **spawn prompt** | The `prompt` parameter passed to `spawn_agent`. This is the coordinator's task instructions for the sub-agent. | "initial prompt" (acceptable in comments but not as a term), "coordinator prompt" |
| **full prompt** | Internal variable name (`full_prompt` in `mcp.py:269`). The spawn prompt with agent prompt prepended. Not a user-facing term. | -- |

---

### Communication Patterns

| Canonical Term | Definition | Code Pattern |
|---|---|---|
| **fire-and-forget** | Sending a message without blocking the caller. The internal `_send_prompt_fire_and_forget` function. Used by `tell_agent`, `ask_agent`, and spawn-time injection. | `mcp.py:118-156` |
| **ask (expect reply)** | `ask_agent` -- sends a question, recipient is nudged if idle without responding. | `mcp.py:346-378` |
| **tell (no reply)** | `tell_agent` -- sends a message, no reply expected. | `mcp.py:381-409` |

**Note:** "fire-and-forget" describes the *implementation* (non-blocking async task), not the *semantics*. `ask_agent` is fire-and-forget at the implementation level but semantically expects a reply. Do not conflate implementation pattern with communication semantics.

---

## 2. Synonyms Found

| Variants Found | Where | Recommendation |
|---|---|---|
| "phase context" / "phase prompt" / "phase instructions" / "phase markdown" | STATUS.md, mcp.py comments, workflows-system.md, audit specs | **agent prompt** for the assembled content. **phase file** for `{phase}.md`. **phase context** only for `phase_context.md`. |
| "sub-agent" / "child agent" / "spawned agent" / "subagent" | STATUS.md, test files, docs, corrections_report.json | **sub-agent** (hyphenated) everywhere. |
| "role prompt" / "coordinator prompt" / "spawn prompt" | Not heavily used yet but at risk | **spawn prompt** for the `prompt` param. **agent prompt** for identity + phase. Never "role prompt". |
| "folder prompt" / "agent folder prompt" | `mcp.py:276` (`folder_prompt` variable) | **agent prompt**. The variable `folder_prompt` in code is acceptable as a local name but should not leak into documentation. |

---

## 3. Overloaded Terms

### "phase context"
- **Meaning 1:** The `.claude/phase_context.md` file (coordinator only).
- **Meaning 2:** The general concept of "context about the current phase" (used loosely in comments).
- **Recommendation:** Reserve "phase context" exclusively for the `phase_context.md` file/mechanism. Use "agent prompt" for the assembled content, "phase file" for the source markdown.

### "prompt"
- **Meaning 1:** The `prompt` parameter of `spawn_agent` (task instructions from coordinator).
- **Meaning 2:** The assembled agent prompt (identity + phase file).
- **Meaning 3:** The full prompt (agent prompt + spawn prompt concatenated).
- **Recommendation:** Always qualify: "spawn prompt", "agent prompt", or "full prompt". Never bare "prompt" in documentation.

### "inject" / "injection"
- **Meaning 1:** Writing `phase_context.md` (filesystem injection).
- **Meaning 2:** Prepending agent prompt at spawn time (spawn-time injection).
- **Meaning 3:** `Injection` dataclass in guardrails (YAML `injections:` section).
- **Recommendation:** Always qualify with mechanism: "filesystem injection", "spawn-time injection", "PostCompact re-injection". The guardrails `Injection` is a separate concept entirely.

---

## 4. Orphan Definitions

| Term Used | Where | Definition Status |
|---|---|---|
| `main_role` | `project_team.yaml:2`, `mcp.py:843` | Defined implicitly. **Add:** "The role name of the coordinator agent, declared in the workflow manifest." |
| `agent_type` | `spawn_agent` parameter | Used as synonym for "role" in code. **Clarify:** `type` parameter maps to the agent's role (folder name). |
| `full_prompt` | `mcp.py:269` | Local variable, no documentation. Acceptable as code-only. |
| `folder_prompt` | `mcp.py:276` | Local variable, no documentation. Acceptable as code-only. |

---

## 5. Canonical Home Violations

| Term | Duplicated In | Canonical Home | Action |
|---|---|---|---|
| Agent prompt assembly | `workflows-system.md:48`, `agent_folders.py` docstring, `terminology.md:170-171` | `terminology.md:170` (existing workflow guidance spec) | Other files should say "See terminology.md" or keep to one sentence. |
| PostCompact hook | `workflows-system.md:48`, `agent_folders.py:105`, `terminology.md:186` | `agent_folders.py` (code is canonical) + `terminology.md:186` (definition) | OK -- code is source of truth, terminology.md is definition home. |

---

## 6. Newcomer Blockers

### In STATUS.md (issue #37)
- **"phase_context.md is assembled for the coordinator only"** -- A newcomer won't know what `phase_context.md` is or why it matters. Add: "the file at `.claude/phase_context.md` that delivers phase instructions via the system prompt."
- **"Sub-agents receive coordinator-authored prompts, not their role phase files"** -- Conflates two problems. Clarify: sub-agents receive the coordinator's *spawn prompt* (task instructions) but not their own *agent prompt* (identity file + phase file).
- **"No automated mechanism to inject context to running sub-agents on phase transition"** -- Which kind of injection? Clarify: no mechanism to deliver updated phase files to already-running sub-agents when `advance_phase` is called.

### In mcp.py
- **Line 276:** `folder_prompt` variable name -- if a newcomer reads this, "folder prompt" is not defined anywhere. The variable assembles the agent prompt from the agent folder. Acceptable as internal code but should not appear in docs or comments to users.

---

## 7. The Core Issue #37 in Canonical Terms

Restated with consistent terminology:

1. **At spawn time:** The coordinator sends sub-agents a **spawn prompt** (task instructions). `spawn_agent` correctly prepends the sub-agent's **agent prompt** (identity file + phase file) via **spawn-time injection** (`mcp.py:268-289`). This works.

2. **At phase transition:** When `advance_phase` runs, the coordinator's **phase context** (`phase_context.md`) is updated via **filesystem injection**. But there is no mechanism to deliver updated **phase files** to already-running sub-agents. They keep operating under stale phase instructions.

3. **After compaction:** The **PostCompact re-injection** hook exists and works for agents that have one registered. But sub-agents may not have this hook if they were spawned without a `type` parameter.

---

## 8. Terms That Are Fine As-Is

These terms are used consistently and do not need changes:

- **workflow**, **manifest**, **phase**, **advance checks** -- well-defined in existing `terminology.md`
- **`ask_agent`**, **`tell_agent`**, **`spawn_agent`** -- tool names, not ambiguous
- **agent folder** -- defined in `terminology.md:158`, used consistently
- **rule**, **hint**, **check** -- distinct mechanisms, well-documented
