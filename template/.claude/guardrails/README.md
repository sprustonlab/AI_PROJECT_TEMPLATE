# Composable Role Guardrails

This directory implements a **declarative role × action permission system** for
claudechic multi-agent workflows. Guardrail hooks intercept tool calls before they
execute and enforce role-based access control.

Three env vars — distinct purposes:

- **`CLAUDE_AGENT_NAME`** (identity): instance name, set for every agent by claudechic.
  Used for routing, ack token filenames, Coordinator mapping via session marker.
- **`CLAUDE_AGENT_ROLE`** (type): role type set via `spawn_agent(type=…)`.
  Used for `allow:`/`block:` permission matching. Not set → permission checks inactive.
- **`CLAUDECHIC_APP_PID`** (session): PID of the claudechic app process, injected by
  claudechic. All agents in the same session share this value. Hooks use it
  to locate the session marker at `.claude/guardrails/sessions/ao_<CLAUDECHIC_APP_PID>`.

**`GUARDRAILS_DIR`** (optional override): all framework files read this env var to
locate the guardrails directory. Defaults to `.claude/guardrails` relative to the
working directory. Override to place guardrails outside the standard path:
```bash
export GUARDRAILS_DIR=/path/to/my/guardrails
```

---

## Role Reference

The primary reference for `rules.yaml` authors:

| Role Type | Syntax | Fires in solo mode | Fires in team mode | Notes |
|-----------|--------|--------------------|--------------------|-------|
| **`Agent`** (group) | `allow: [Agent]` or `block: [Agent]` | ✓ | ✓ | All agents with `CLAUDE_AGENT_NAME` set |
| **`TeamAgent`** (group) | `allow: [TeamAgent]` or `block: [TeamAgent]` | ✗ | ✓ | Coordinator + sub-agents |
| **`Subagent`** (group) | `allow: [Subagent]` or `block: [Subagent]` | ✗ | ✓ (not Coordinator) | Sub-agents only |
| **Named role** | `allow: [Implementer]` | ✗ (team-only) | ✓ (`CLAUDE_AGENT_ROLE` exact match) | e.g., `Coordinator`, `Implementer`, `Skeptic`; matched against `CLAUDE_AGENT_ROLE` only — no fallback to `CLAUDE_AGENT_NAME` |

`Agent`, `TeamAgent`, `Subagent` are **reserved** — cannot be used as agent spawn names or
`type` values.

**Filename ↔ type transform** (used by `type: spawn_type_defined` to validate `type` against role
definition files):

| Type string | Expected path in `workflows/project_team/` |
|-------------|----------------------------------------------|
| `Implementer` | `implementer/identity.md` |
| `TestEngineer` | `test_engineer/identity.md` |
| `ClusterOperations` | `cluster_operations/identity.md` |
| `Composability` | `composability/identity.md` |
| `Terminology` | `terminology/identity.md` |

Rule: two-pass insertion of `_` handles consecutive uppercase runs correctly (e.g. `UIDesigner` → `ui_designer`):
pass 1 inserts `_` before an uppercase that ends a run (`XYZ→XY_Z`); pass 2 inserts `_` before an uppercase
following a lowercase/digit (`aB→a_B`). Then lowercase the whole string.
`type: spawn_type_defined` checks `workflows/project_team/<lower_snake>/identity.md`.

---

## Team Skill Contract

Any skill that activates team mode must:
1. Call `setup_ao_mode.sh` during activation — writes the session marker, enables `check_role()` team-mode enforcement
2. Spawn agents with `spawn_agent(name=…, type=<RoleName>)` — sets `CLAUDE_AGENT_ROLE` for role matching
3. Call `teardown_ao_mode.sh` during wind-down — deletes the session marker

The session marker path: `.claude/guardrails/sessions/ao_<CLAUDECHIC_APP_PID>` (override with `GUARDRAILS_DIR`).

---

## Abilities

- **Role × action permissions** — declare what each agent may and may not do,
  via `allow:`/`block:` fields directly in `rules.yaml`; role groups (`Agent`,
  `TeamAgent`, `Subagent`) allow flexible scoping without per-agent listing
- **Universal rules** — regex-based rules in `rules.yaml` that apply to all agents
  regardless of role (e.g., R21 denies `rm -rf` on worktrees for everyone)
- **Spawn-time validation** — spawn rules in `rules.yaml` warn before an agent is created
  if its name is reserved, has an invalid character set, or doesn't correspond to a known role definition file (`type: spawn_type_defined`)
- **Per-rule enforcement levels** — four levels: `log` (record only), `warn` (advisory,
  suppressible via ack), `deny` (hard stop), `inject` (modify tool input)
- **Hardening path** — monitor `hits.jsonl` to observe agent access, then
  change `enforcement: warn` → `enforcement: deny` with confidence

---

## Limitations

**1. Team mode requires both `CLAUDECHIC_APP_PID` and a session marker.**
Role-based permission checks activate only when (a) claudechic injects `CLAUDECHIC_APP_PID`
into the agent environment and (b) the session marker exists at
`.claude/guardrails/sessions/ao_<CLAUDECHIC_APP_PID>`. The marker is written by
`setup_ao_mode.sh` when a team skill activates. If rules fire but team mode is
unexpectedly inactive, verify that `setup_ao_mode.sh` ran and that `CLAUDECHIC_APP_PID` is
present in the agent's environment.

**2. One team session per claudechic process.**
`setup_ao_mode.sh` errors if a session marker already exists for the current
`CLAUDECHIC_APP_PID`. To run concurrent team sessions, use separate claudechic instances
(separate terminal / separate PID → separate marker path). Attempting to activate team
mode twice in the same claudechic session is an error.

**3. Two ack paths — one for Bash triggers, one for Write/Edit triggers.**
Hooks exit 0 (allow) or 2 (reject) to Claude Code; both deny and warn exit 2. The
distinction is the message: warn messages include acknowledgment instructions; deny
messages do not.

- **Bash ack:** Re-run the command with `# ack:<RULE_ID>` as a comment prefix. The hook
  sees the prefix and exits 0.
- **Write/Edit ack (ack token flow):** Run `python3 .claude/guardrails/role_guard.py ack <RULE_ID> <FILE_PATH>` to write a per-agent ack token to
  `.claude/guardrails/acks/ack_<AGENT_NAME>_<RULE_ID>.json`
  (`{"rule_id": "…", "agent_name": "…", "file_path": "…", "ts": "<ISO8601>Z"}`),
  then retry the write. Per-agent files mean exactly one writer per file — no shared-file
  race conditions, no locking needed (NFS-safe). The hook reads, validates (rule_id +
  file_path + TTL ≤ `ack_ttl_seconds`, default 60 s). The token persists until TTL expires —
  multiple writes to the same path within the window are allowed without re-acking. The exact
  ack command is included in the warning message — the agent copies and runs it. Set `ack_ttl_seconds` at the top level of `rules.yaml` to adjust the window.
- **spawn_agent:** No ack mechanism — correct the `spawn_agent()` call and retry.

The internal codes in `role_guard.py` (1 = deny, 2 = warn) are intermediate signals
mapped by the hook dispatch layer, not the final exit codes sent to Claude Code.

**4. Hooks write messages to stderr, not stdout.**
Claude Code's hook protocol reads stdout for structured data. All diagnostic messages,
warnings, and error text must go to `sys.stderr` (Python) or `>&2` (shell). Text written
to stdout may be silently consumed by the protocol and never shown to the agent.

**5. Role names are case-sensitive.**
If a spawned agent uses `type="implementer"` but rules list `Implementer`, all
permission checks treat it as an unlisted role. Rule S05 (`spawn_type_defined`) warns at
spawn time (exit 2). Always match the case used in `rules.yaml` `allow:`/`block:` lists.

**6. Solo mode bypasses team-scoped permission checks.**
When `CLAUDE_AGENT_NAME` is unset, nothing fires. When the session marker is absent (solo
mode), `TeamAgent`, `Subagent`, and named-role rules are skipped. Only `Agent`-group rules
fire in solo mode (e.g., `block: [Agent]` hard-blocks everyone including solo agents).
Universal rules (R01–R21) always apply. A diagnostic warning is emitted to stderr only when
`CLAUDE_AGENT_NAME` is unset — the usual case of a missing session marker (solo work) is
normal and does not warn.

**7. PID reuse (extremely low probability).**
If claudechic crashes without `teardown_ao_mode.sh` running, and the OS reuses the exact
same PID for a new claudechic instance before `setup_ao_mode.sh` runs again, the stale
session marker from the crashed session could activate team mode for the new session.
This is extremely low probability in practice. If suspected, run `teardown_ao_mode.sh`
manually (or delete `.claude/guardrails/sessions/ao_<PID>`) before restarting. The
`setup_ao_mode.sh` stale-marker cleanup also removes markers for non-running PIDs
at startup.

---

## File Layout

```
.claude/guardrails/
├── generate_hooks.py          # Framework: generates hook scripts from rules.yaml
│                               # Run after any change to rules.yaml
├── role_guard.py              # Framework: get_my_role() + check_role() library (CLAUDE_AGENT_ROLE for role checks)
├── README.md                  # Framework: this file
├── rules.yaml                 # Project: all guardrail rules (universal + role-gated)
├── rules.yaml.example         # Framework: one rule per pattern type, rename to activate
├── hooks/                     # Generated: one hook per trigger (bash_guard.sh, write_guard.sh, read_guard.sh, mcp__chic__spawn_agent_guard.sh, …)
├── messages/                  # Project: hook message text (R21.md, R22.md, …)
├── acks/                      # Runtime: per-agent Write/Edit ack tokens (gitignored)
│   └── ack_<AGENT>_<RULE>.json  # TTL-scoped token; created by agent, expires after ack_ttl_seconds
├── sessions/                  # Runtime: session markers (gitignored)
│   └── ao_<PID>               # Written by setup_ao_mode.sh; presence activates team mode
└── hits.jsonl                 # Runtime: hook match log (gitignored)
```

Framework files (`generate_hooks.py`, `role_guard.py`, `README.md`,
`rules.yaml.example`) are owned by
`sprustonlab/AI_PROJECT_TEMPLATE`. Do not edit them per-project — changes will be
overwritten on the next template sync.

## How to Add a Rule

All rules — universal rules and role-gated rules — live in the single `rules.yaml`
file. See `rules.yaml.example` for one entry of each pattern type.

1. Add an entry to `rules.yaml` under `rules:`. Choose the right `detect.type`:
   - **`type: regex_match`** — fire when pattern matches. Optional `field:` for MCP/structured tool inputs. Add `allow:`/`block:` for role gating.
   - **`type: regex_miss`** — fire when pattern does NOT match. Same `field:` support. Add `allow:`/`block:` for role gating.
   - **`type: always`** — fires on every trigger match; add `allow:` or `block:` for role gating (required)
   - **`type: spawn_type_defined`** — fires when agent `type` has no `workflows/project_team/<lower_snake>/identity.md`. Only for `mcp__chic__spawn_agent`.
   - **No `allow:`/`block:`** — universal rule; applies to every agent regardless of role
   Use **either** `allow:` or `block:` — not both. `generate_hooks.py` exits with an error
   if both are present:
   ```
   ERROR: rule 'R22' has both allow: and block:. Use one list per rule.
   ```
2. Create a message file at `messages/<RuleID>.md` (or inline a short `message:` in the rule).
   **Deny messages must include an "Instead:" line** using this template:
   ```
   [GUARDRAIL DENY RXX] <one-sentence reason>
   <Why this rule exists.>
   Instead: <what the agent should do — delegate, use an alternative, or contact the Coordinator>
   ```
   **Warn messages** — write the message content (including any delegation guidance) in the
   `message:` field. The generator appends only the ack instructions:
   ```
   <your message content here>

   To acknowledge and proceed:
     python3 .claude/guardrails/role_guard.py ack RXX <path>
   Then retry within <ack_ttl_seconds> seconds.
   (If the retry still rejects, the ack token may have expired — re-run the ack command.)
   ```
3. Run `python3 .claude/guardrails/generate_hooks.py` to regenerate hook scripts
4. Verify: pipe a test command to `bash .claude/guardrails/hooks/bash_guard.sh` and check
   the exit code and message

Start new rules at `enforcement: log` or `enforcement: warn`. Monitor `hits.jsonl`. Harden to `enforcement: deny`
once you've confirmed no legitimate use by unlisted roles.

> **Solo mode note:** Rules with an `allow:` list of named roles (e.g., `allow: [Implementer]`)
> are skipped in solo mode — they fire only when team mode is active (session marker present).
> If you want enforcement only in team mode, an `allow:` list is correct. If you want a rule
> that also fires in solo mode, use `block: [Agent]` (fires everywhere) or `block: [TeamAgent]`
> (fires in team mode, skips solo).

---

## How to Add a Role

1. Add the role type string to `allow:` or `block:` lists in the relevant rules in
   `rules.yaml`. List the **type** (e.g., `Implementer`), not numbered instance names.
   All instances spawned with `type="Implementer"` match this single entry.
2. Create an agent definition directory at `workflows/project_team/<lower_snake>/identity.md`
   (CamelCase→lower_snake transform from the type name; required for `type: spawn_type_defined`
   path validation). Example: type `TestEngineer` → directory `test_engineer/identity.md`.
3. Run `python3 .claude/guardrails/generate_hooks.py` to regenerate hook scripts.
4. Spawn with `spawn_agent(name="<InstanceName>", type="<RoleName>")`.
   The `type` string must exactly match the entry in `rules.yaml` (case-sensitive).
   For single-instance roles, `name` and `type` can be the same:
   `spawn_agent(name="Composability", type="Composability")`.

---

## Validation — Hook Overhead Benchmark

Run `python3 tests/benchmark_hook_overhead.py` to measure hook latency on your system
before committing to production use. The script reports mean, p95, and p99 per condition
and fails (exit 1) if any mean exceeds 50 ms.

**Conditions tested:**

| # | Condition | What it measures |
|---|-----------|-----------------|
| 1 | No hooks active (manual baseline) | Reference cost — hooks disabled in settings.json manually |
| 2 | Hooks active, no rule match | Rules scan + pattern check + early exit 0 |
| 3 | Hooks active, rule match (rejected) | Full match + role check + exit 2 |
| 4 | Full ack round-trip | Condition 3 + `role_guard.py ack` CLI subprocess + retry + token valid + exit 0 |

**Reported metrics:** mean, p95, p99 latency per condition (conditions 2–4 automated).
**Threshold:** absolute mean ≤ 50 ms per condition. If exceeded, investigate optimizations
(compiled regex at module level, reduced hook coverage).

**Reference results** (Linux, NFS home directory, 2026-03-29):

| Condition | Mean | p95 | p99 | Status |
|-----------|------|-----|-----|--------|
| no_match | 31.3 ms | 34.5 ms | 39.1 ms | ✅ PASS |
| match_reject | 30.0 ms | 32.6 ms | 36.4 ms | ✅ PASS |
| ack_roundtrip | 71.2 ms | 78.9 ms | 89.7 ms | ⚠️ EXPECTED |

The ack roundtrip exceeds 50 ms because it is **two subprocess launches** (ack CLI + retry hook).
This cost is only incurred once per write-warn acknowledgment, not on every tool call.
The per-hook cost (~30 ms) is the number that matters for interactive latency.
