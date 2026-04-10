# Current Guardrails System vs. Specification Audit

**Author:** Researcher
**Date:** 2026-04-05
**Purpose:** Ensure the Workflow Guidance System spec preserves all existing guardrails functionality.

---

## Overview of the Two Systems

### Current System ("file-based guardrails")

Located at `.claude/guardrails/`. A **code-generation** architecture:
- `rules.yaml` is the single source of truth
- `generate_hooks.py` reads rules.yaml and generates self-contained Python hook scripts in `hooks/`
- Generated scripts are registered in `.claude/settings.json` as Claude Code hooks
- `role_guard.py` is a runtime library imported by generated hooks for role checks and ack tokens
- Hooks run as **separate Python processes** spawned by Claude Code (stdin JSON → stdout/stderr → exit code)
- This is the Claude Code native hook system (file-based hooks)

### claudechic SDK Hooks ("closure-based guardrails")

Located at `submodules/claudechic/claudechic/guardrails/`. A **closure-based** architecture:
- `rules.py` has `Rule` dataclass + matching functions
- `app.py._guardrail_hooks()` creates SDK hook closures that run in-process
- Closures load `rules.yaml` fresh every call and evaluate in-memory
- This is the claudechic SDK hook system (in-process callbacks)

### The Spec's Approach

The spec builds on the **closure-based** approach (SDK hooks in claudechic). It replaces the single-file loader with a multi-manifest unified loader reading from `workflows/`.

---

## PART 1: Features in the CURRENT System MISSING from the Spec

These are features that exist in the file-based guardrails today that the spec does not describe or account for.

### 1.1 The Entire Code-Generation Pipeline

**Current:** `generate_hooks.py` is a ~2150-line code generator that:
- Reads `rules.yaml` and generates self-contained Python scripts (`bash_guard.py`, `write_guard.py`, `read_guard.py`, `glob_guard.py`, `mcp__chic__spawn_agent_guard.py`, `post_compact_injector.py`)
- Registers them in `.claude/settings.json` as Claude Code hooks
- Has `--check` mode (drift detection) and `--matrix` mode (role × action matrix)
- Supports `rules.d/*.yaml` for contributed rule sets with ID collision detection

**Spec:** Does not mention generate_hooks.py at all. The spec replaces file-based hooks with SDK hook closures. **This is intentional** — the spec's approach is architecturally different. But the migration path is unspecified.

**Risk:** Users who have customized `.claude/guardrails/rules.yaml` need a migration story.

### 1.2 The `inject` Enforcement Level (Tool Input Modification)

**Current:** `inject` is a full enforcement level (pcode=4) in the generated hooks. It modifies tool input before the tool executes. `generate_hooks.py` generates inject handling code. `role_guard.py` returns pcode=4 for inject. The `ENFORCEMENT_RANK` includes it.

**Spec:** §2 says: "`inject` is a separate tool-input modification mechanism, not an enforcement level." §8 says: "Parsed in the same rules YAML but behavior is orthogonal to enforcement. Handled separately in the hook pipeline — does not go through the deny/warn/log code path."

**Assessment:** The spec acknowledges inject exists but deliberately excludes it from the enforcement hierarchy. The closure-based hook in the spec's §8 code has no inject handling. The spec says "for backward compatibility" but provides no implementation. **This is a gap** — inject rules won't work with the new system unless code is added.

### 1.3 The Bash Ack Mechanism (`# ack:<RULE_ID>` comment prefix)

**Current:** For Bash `warn` rules, the agent can re-run the command with `# ack:<RULE_ID>` as a prefix. The generated `bash_guard.py` has:
```python
_ack_match = re.match(r'^#\s*ack:(\S+)', command)
_acked_rule = _ack_match.group(1) if _ack_match else None
```
Warn-level matches where `_rid == _acked_rule` are filtered out of `_warn_msgs`.

**Spec:** §8 mentions this: "Bash commands use `# ack:<RULE_ID>` comment prefix on retry" and says `warn` uses "the existing ack mechanism." But the closure-based hook code in §8 does NOT implement ack checking. It just does:
```python
elif rule.enforcement == "warn":
    return {"decision": "block", "reason": rule.message}
```
No ack detection, no ack filtering.

**Risk:** HIGH. Warn rules will become permanent blocks with no bypass. The spec says to use the existing mechanism but the closure code doesn't implement it.

### 1.4 The Write/Edit Ack Token Flow

**Current:** For Write/Edit `warn` rules, the agent runs:
```bash
python3 .claude/guardrails/role_guard.py ack <RULE_ID> <FILE_PATH>
```
This writes a per-agent JSON token to `acks/ack_<AGENT>_<RULE>.json` with a TTL. The generated `write_guard.py` checks tokens via `_rg.check_write_ack(rule_id, file_path, _ACK_TTL_SECONDS)`.

**Spec:** Same as 1.3 — mentions "Write/Edit uses `role_guard.py ack <RULE_ID> <FILE_PATH>` to create an ack token" but the closure code doesn't implement token checking.

**Risk:** HIGH. Same as 1.3 — Write/Edit warn rules lose their bypass mechanism.

### 1.5 The `ack_ttl_seconds` Top-Level Config

**Current:** `rules.yaml` has a top-level `ack_ttl_seconds: 60` field. This is baked into generated hooks at generation time.

**Spec:** Not mentioned in the manifest format or the loader.

### 1.6 Multi-Match Enforcement Priority (deny > warn > inject > log)

**Current:** Generated hooks collect ALL matching rules into `_matched_rules`, then dispatch:
1. If any deny → exit 2 (block)
2. Else if any warn (not acked) → exit 2 (block)
3. Else if any inject → apply transform, proceed
4. Else log-only → exit 0

Multiple rules can match simultaneously. The highest-priority enforcement wins.

**Spec:** The closure code uses early-return on first match:
```python
for rule in result.rules:
    ...
    if rule.enforcement == "deny":
        return {"decision": "block", "reason": rule.message}
    elif rule.enforcement == "warn":
        return {"decision": "block", "reason": rule.message}
```

**Risk:** MEDIUM. If a deny and a warn both match, current system shows both messages and exits with deny. New system returns on whichever rule appears first in the list. Different behavior.

### 1.7 `detect.type` Enumeration

**Current:** Four detect types:
- `regex_match` (or `regex`) — fire when pattern matches
- `regex_miss` — fire when pattern does NOT match
- `always` — fires on every trigger match (requires role gate)
- `spawn_type_defined` — fires when agent type has no matching `.md` file in `AI_agents/`

**Spec:** The `Rule` dataclass has `detect_pattern` and `exclude_pattern`. No `detect.type` field. No `regex_miss`, no `always`, no `spawn_type_defined`.

**Risk:** HIGH. Existing rules using `regex_miss`, `always`, and `spawn_type_defined` detect types will break.

### 1.8 `exclude_contexts` (Strip Python Inline/Heredoc)

**Current:** Rules can specify `detect.exclude_contexts: ['python_dash_c', 'python_heredoc']` to strip Python code blocks before pattern matching. Generated hooks include a `strip_contexts()` function.

**Spec:** Not mentioned.

### 1.9 `detect.flags` (Regex Flags)

**Current:** Rules can specify `detect.flags: [IGNORECASE, DOTALL, MULTILINE]`. Generated hooks apply these as Python `re` flags.

**Spec:** Not mentioned. The `Rule` dataclass uses `re.compile(pattern)` with no flags support.

### 1.10 `detect.field` for Arbitrary Tool Input Fields

**Current:** Supports `field:` for any tool input field. MCP triggers REQUIRE `field:` since they have no default.

**Spec:** The `Rule` dataclass has `detect_field: str = "command"` — supports this. OK.

### 1.11 `detect.conditions` (Glob Guard Special Conditions)

**Current:** Glob guard supports `detect.conditions.path_is_root` — a special condition that fires when the glob path is empty, ".", or CWD.

**Spec:** Not mentioned.

### 1.12 `detect.target` for Read/Write Guards

**Current:** Read guard uses `detect.target` to specify what variable to match against (`file_path` by default). Glob guard uses `detect.target` similarly (`pattern` by default).

**Spec:** Not mentioned explicitly, but `detect_field` may cover this.

### 1.13 Session Markers and Team Mode Activation

**Current:** Team mode is activated by session markers at `.claude/guardrails/sessions/ao_<PID>`:
- `setup_ao_mode.sh` writes the marker (records coordinator name)
- `teardown_ao_mode.sh` deletes it
- `get_my_role()` reads the marker to determine if team mode is active
- Coordinator is identified via marker's `coordinator` field
- `_role_matches()` handles group roles: `Agent`, `TeamAgent`, `Subagent`

**Spec:** Uses `block_roles`/`allow_roles` with no mention of session markers, team mode, `get_my_role()`, role groups, or the `Agent/TeamAgent/Subagent` group hierarchy.

**Risk:** HIGH. The entire team-mode activation mechanism (session markers, role groups, solo vs team mode distinction) is not described in the spec. The closure just receives `agent_role` directly.

### 1.14 `hits.jsonl` Logging

**Current:** Every rule match is logged to `.claude/guardrails/hits.jsonl` with fields: `ts`, `rule_id`, `enforcement`, `tool`, `agent`, `target`. Separate `log_hit()` function in generated hooks includes `session_id`, `session_name` (derived from JSONL).

**Spec:** Not mentioned. The closure code has no hit logging.

**Risk:** MEDIUM. Loss of observability. The hardening path (`log` → `warn` → `deny`) depends on hits.jsonl data.

### 1.15 `catalog_version` Field

**Current:** `rules.yaml` has a top-level `catalog_version: "1"` field. Used in generated hook headers and the matrix output.

**Spec:** Not mentioned.

### 1.16 `source` Field on Rules

**Current:** Rules can have a `source:` field (e.g., "User rule — full suite output must be saved"). Informational only.

**Spec:** Not in the `Rule` dataclass.

### 1.17 `name` Field on Rules

**Current:** Rules have both `id` and `name` fields. `id` is for matching (R01, R02), `name` is human-readable (pytest-output-block, pip-install-block).

**Spec:** The `Rule` dataclass has `name: str`. OK — this is preserved.

### 1.18 `enabled` Field on Rules

**Current:** Rules can have `enabled: false` to disable without removing. `group_rules_by_trigger()` skips disabled rules.

**Spec:** Not in the `Rule` dataclass.

### 1.19 Message Files (`messages/*.md`)

**Current:** Messages can be file references (e.g., `message: messages/R21.md` or `message: .claude/guardrails/messages/R22.md`). `get_message_text()` resolves these.

**Spec:** Messages are inline strings only.

### 1.20 Pattern Lists (Multiple Patterns per Rule)

**Current:** `detect.pattern` can be a list of patterns. Generated hooks use `any([re.search(p1), re.search(p2), ...])`.

**Spec:** The `Rule` dataclass has `detect_pattern: re.Pattern[str] | None` — a single compiled pattern, not a list.

### 1.21 PostCompact Injector (SessionStart/compact Trigger)

**Current:** `generate_hooks.py` has `generate_post_compact_injector()` for `SessionStart/compact` triggers. It emits inject-type rules that print content to stdout after compaction.

**Spec:** Has a PostCompact hook but it's for re-injecting phase context, not for general inject rules. The spec's PostCompact is about agent folder content, not arbitrary inject rules.

### 1.22 `rules.d/` Contributed Rule Sets

**Current:** `generate_all()` merges rules from `rules.d/*.yaml` with collision detection.

**Spec:** Not mentioned.

### 1.23 MCP Trigger Hook Generation

**Current:** Any trigger starting with `mcp__` gets its own generated hook script. The system dynamically creates hooks for arbitrary MCP tools.

**Spec:** The closure-based system handles all triggers in a single PreToolUse hook. MCP triggers would need to be in the tool_name matching — but the spec only shows `PreToolUse/<ToolName>` format.

### 1.24 `settings.json` Auto-Update

**Current:** `generate_all()` calls `update_settings_json()` to register all generated hooks in `.claude/settings.json`.

**Spec:** SDK hooks don't need settings.json registration (they're registered programmatically via `ClaudeAgentOptions.hooks`).

### 1.25 `GUARDRAILS_DIR` Environment Variable Override

**Current:** All framework files respect `GUARDRAILS_DIR` env var for locating the guardrails directory.

**Spec:** Not mentioned. Uses `workflows/` relative to project root.

---

## PART 2: Features CHANGED Between Current System and Spec

### 2.1 Rule Discovery Path

**Current:** Single file: `.claude/guardrails/rules.yaml`
**Spec:** Multi-file: `workflows/global.yaml` + `workflows/*/workflow_name.yaml`

### 2.2 Rule Evaluation Architecture

**Current:** Generated Python scripts run as separate processes (subprocess per tool call)
**Spec:** In-process SDK hook closures (no subprocess overhead)

**Implication:** ~30ms per-hook latency (subprocess) → sub-millisecond (in-process). Major performance improvement.

### 2.3 Enforcement Levels

**Current:** Four levels: `deny`, `warn`, `log`, `inject`
**Spec:** Three levels: `deny`, `warn`, `log`. `inject` is "separate mechanism, not an enforcement level."

### 2.4 `user_confirm` Enforcement

**Current:** `user_confirm` exists in the claudechic SDK hook (`app.py._guardrail_hooks()`) but NOT in the file-based system. The current file-based system has no `user_confirm`.
**Spec:** Mentions `user_confirm` in the closure code (§8 line 1367) but the terminology section says three levels: deny, warn, log. Inconsistent.

### 2.5 `deny` Override Mechanism

**Current file-based:** `deny` = hard block, no override, no ack.
**Current claudechic:** `deny` → `{"decision": "block"}`, no override.
**Spec:** `deny` → agent can use `request_override` MCP tool → user approves → suppressed for session.

**This is a NEW mechanism** — deny rules become overridable by users.

### 2.6 Role Scoping Field Names

**Current file-based:** `allow:` and `block:` (YAML keys)
**Current claudechic:** `block_roles` and `allow_roles` (Rule dataclass fields), parsed from YAML `block`/`allow`
**Spec:** Uses `block_roles` and `allow_roles` in the Rule dataclass.

### 2.7 Role Matching Semantics

**Current:** Complex hierarchy: `Agent` (all agents), `TeamAgent` (team mode only), `Subagent` (sub-agents in team), named roles (exact match on `CLAUDE_AGENT_ROLE`). Solo mode skips team-scoped rules. Coordinator identified via session marker.
**Spec:** Simple: `block_roles` list → skip if role not in list. `allow_roles` list → skip if role in list. No group roles, no team mode, no session markers.

### 2.8 Phase State Location

**Current claudechic:** `.claude/guardrails/phase_state.json`
**Spec:** In-memory engine state, persisted via chicsession (§2 says "Held in-memory by the engine, persisted via `Chicsession.workflow_state`").

### 2.9 Namespace Prefixing

**Current:** No namespacing. Rule IDs are bare (R01, R02, etc.).
**Spec:** Auto-prefixed: `_global:pip_block`, `project-team:close_agent`.

---

## PART 3: Features NEW in the Spec (Not in Current System)

### 3.1 Unified Manifest Loader with ManifestSection[T] Protocol
### 3.2 Workflow Engine (Phase Transitions, Advance Checks, State)
### 3.3 Check Protocol (4 Built-in Types: CommandOutput, FileExists, FileContent, ManualConfirm)
### 3.4 CheckFailed → Hints Adapter
### 3.5 Agent Folders (identity.md + phase files, prompt assembly)
### 3.6 PostCompact Hook for Phase Context Re-injection
### 3.7 `request_override` MCP Tool for Deny Rule Overrides
### 3.8 `get_phase` MCP Tool for Phase Queries
### 3.9 Startup Validation (Duplicate IDs, Phase References, Regex Validation)
### 3.10 `when` Clause for Conditional Checks (Copier-Answer Gating)
### 3.11 Namespace Convention and Qualified Phase IDs
### 3.12 `workflows/` Directory Structure
### 3.13 Phase-Scoped Hints
### 3.14 Setup Checks in `global.yaml`
### 3.15 Chicsession-Based State Persistence

---

## PART 4: Critical Gaps Summary

### Must Address Before Implementation

| # | Gap | Severity | Recommendation |
|---|-----|----------|----------------|
| 1 | **Ack mechanism missing from closure code** (Bash `# ack:` prefix + Write/Edit token flow) | CRITICAL | Add ack detection to the closure. The spec says to use existing ack but doesn't implement it. |
| 2 | **`detect.type` enumeration not supported** (`regex_miss`, `always`, `spawn_type_defined`) | HIGH | Extend Rule dataclass and match_rule() for these types. |
| 3 | **Multi-match priority missing** (deny > warn > inject > log across all matching rules) | HIGH | Change from early-return to collect-all-then-dispatch. |
| 4 | **`inject` enforcement not implemented** in closure | HIGH | Add inject handling or document explicit deprecation. |
| 5 | **Team mode / session markers / role groups not mentioned** | HIGH | Either migrate to closure-native approach or document co-existence. |
| 6 | **hits.jsonl logging absent** from closure | MEDIUM | Add hit logging to closure. Essential for hardening path. |
| 7 | **Pattern lists not supported** (single pattern vs list) | MEDIUM | Support `list[re.Pattern]` in Rule. |
| 8 | **Regex flags not supported** | MEDIUM | Add flags field to Rule. |
| 9 | **`exclude_contexts` (strip Python code) not supported** | LOW | Add or document removal. Only used by specific Bash rules. |
| 10 | **`ack_ttl_seconds` not in manifest format** | MEDIUM | Add to manifest schema. |

### Co-Existence Question

The spec does not state whether the file-based system (`.claude/guardrails/`) is **replaced** or **co-exists** with the new closure-based system. Today, BOTH run:
- Claude Code loads file-based hooks from `settings.json` → subprocess
- claudechic creates SDK hook closures → in-process

If both continue to run, rules fire twice. If file-based is removed, all the features in Part 1 are lost unless migrated.

**Recommendation:** The spec should explicitly state the migration plan:
1. Phase 1: New closure system reads from `workflows/`, old file-based reads from `.claude/guardrails/`
2. Phase 2: Migrate rules to `workflows/` format
3. Phase 3: Remove file-based hooks from `settings.json`

Or: Document that the file-based system continues to operate alongside the closure-based system, with the understanding that `workflows/` rules are evaluated by closures and `.claude/guardrails/rules.yaml` rules continue to be evaluated by generated hooks.
