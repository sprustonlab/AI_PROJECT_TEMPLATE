# Skeptic Review: SDK Hooks PoC

**Reviewer:** Skeptic
**Date:** 2026-04-05
**Scope:** PoC code review, migration risk analysis, hardening gaps

---

## 1. PoC Assessment: What's Proven

The PoC proves the core mechanism works: SDK in-process hooks evaluate `rules.yaml`, deny enforcement blocks commands, `user_confirm` shows a TUI prompt, and timing is acceptable (<5ms). This is a solid foundation. The architecture is fundamentally simpler than file hooks — fewer moving parts, no code generation, no shell subprocess communication.

**What's actually proven:**
- Rule loading from YAML → Rule dataclass
- Trigger matching (tool name extraction from `PreToolUse/Bash`)
- Pattern matching with detect + exclude
- Role-based filtering (`block_roles`, `allow_roles`)
- Deny enforcement returning `{"decision": "block"}`
- `user_confirm` via `SelectionPrompt`
- Timing under budget

**What's NOT proven (only stubbed or untested):**
- Phase-based filtering (`should_skip_for_phase` exists but no test exercises it with live hooks)
- `hits.jsonl` logging (mentioned in STATUS.md "What's Next" but not implemented)
- Multiple rules matching the same tool call (only first-match tested)
- Concurrent agents sharing the same `rules.yaml`
- Error recovery under real SDK conditions

---

## 2. Risks for Full Implementation

### RISK-1: YAML re-parse on every tool call (Medium)

`load_rules(rules_path)` is called on **every single PreToolUse event**. The comment says "Always fresh — supports live edits." This is a deliberate design choice for hot-reloading, and at 5 rules + <5ms it's fine. But it won't stay at 5 rules. With phase-scoped rules per tutorial, rule count could reach 20-50. YAML parsing scales linearly; regex compilation happens every time.

**Recommendation:** Cache with mtime check. Read `rules_path.stat().st_mtime`, only re-parse if changed. Regex patterns get compiled once and reused. This preserves hot-reload while eliminating redundant work. Simple, verifiable, no downside.

### RISK-2: First-match semantics are implicit (Medium)

The `evaluate` function iterates rules and returns on first match. This is fine for deny-only rules, but creates ordering sensitivity once you mix enforcement levels. If a `log` rule appears before a `deny` rule for the same pattern, the deny never fires — the log rule matches first and falls through (returns `{}`), and the loop continues... wait, actually the `log` case *does* continue the loop (no return). So the current code is: deny/user_confirm/warn return immediately, log falls through. This means:

- A `log` rule before a `deny` rule: both fire (log logged, deny blocks). Correct.
- A `warn` rule before a `deny` rule: warn blocks, deny never evaluated. The `warn` enforcement currently returns `{"decision": "block"}` — **same as deny**. Is this intentional? Warn-as-block seems wrong. If warn is advisory, it should not block.

**Finding:** `warn` enforcement currently acts as `deny` (line 698: `return {"decision": "block"}`). This needs clarification. Either warn should log+allow (advisory) or the 2×2 framing (advisory vs enforced) isn't reflected in the code.

### RISK-3: Fail-open on exceptions (Design decision, flag it)

Line 714: `return {}  # Fail-open for PoC debugging`. In production, fail-open means a broken `rules.yaml` or a bug in rule evaluation silently allows everything. This is reasonable for PoC but must be a conscious decision for production. The SPECIFICATION's 2×2 framing has enforced rules — those should arguably fail-closed (block on error) rather than silently allow.

**Recommendation:** Make failure mode configurable per-rule or globally. At minimum, log a visible warning (not just stderr) when the guardrail system errors so the user knows protection is down.

### RISK-4: `_cwd` access is fragile (Low)

Line 647: `Path(self._cwd if hasattr(self, "_cwd") else Path.cwd())`. Using `hasattr` to guard against missing attributes is a code smell that suggests `_cwd` isn't reliably set at hook creation time. If `_cwd` is `None` or unset, it falls back to `Path.cwd()` which may be wrong in worktree scenarios.

**Recommendation:** Pass `cwd` explicitly when constructing the closure, don't reach into `self` at evaluation time.

---

## 3. Underspecified Areas Needing Hardening

### 3A. Concurrent agents

The PoC creates a closure with `agent_role` captured at agent creation time. This is correct — each agent gets its own hook closure with its own role. But:

- All agents share the same `rules.yaml` file. No locking. Two agents loading simultaneously is fine (read-only). But if the Coordinator edits `rules.yaml` while a subagent is mid-evaluation, the subagent could read a partial file. YAML parsing of a partially-written file will raise an exception → fail-open (RISK-3).
- `phase_state.json` is shared state written by one agent, read by all. Same partial-read risk. JSON is more atomic than YAML (single write vs multi-line), but still not guaranteed on all filesystems.

**Recommendation:** For `phase_state.json`, use atomic write (write to temp file, rename). For `rules.yaml`, the mtime-cache from RISK-1 naturally reduces the window. Accept the remaining risk as low-probability.

### 3B. `user_confirm` prompt with multiple agents

When `user_confirm` fires, it calls `app._show_guardrail_confirm(rule)`, which mounts a `SelectionPrompt`. If two agents trigger `user_confirm` simultaneously, they'll both try to mount prompts. The existing permission flow likely has the same serialization mechanism (the `_show_prompt` context manager), so this may already be handled. But it needs verification.

### 3C. Rule validation at startup

STATUS.md lists "Add startup validation for rules.yaml" as a next step. This is essential. Currently, a malformed regex in `detect.pattern` will raise `re.error` at load time → caught by the try/except → fail-open. A typo in enforcement level (e.g., `enforcment: deny`) silently defaults to `deny` (line 98: `entry.get("enforcement", "deny")`). This is actually safe-by-default but masks user errors.

**Recommendation:** Validate at startup:
- All `id` fields are unique
- All `enforcement` values are in `{deny, warn, log, user_confirm}`
- All `detect.pattern` values compile as valid regex
- All `trigger` values match `PreToolUse/<ToolName>` format
- Warn on unknown fields (catches typos like `enforcment`)

### 3D. No hit logging

The PoC logs to stderr with `print()`. Production needs structured hit logging (`hits.jsonl`) for auditability. This is acknowledged in STATUS.md but worth emphasizing: without hit logging, there's no way to verify guardrails are actually firing in production.

### 3E. The `type` field in detect is parsed but ignored

`rules.yaml` has `type: regex_match` in detect blocks, but `rules.py` never checks this field. It only reads `pattern` and `field`. If future rule types are planned (e.g., `type: exact_match`, `type: glob`), the code doesn't distinguish. If `regex_match` is the only type, remove the field from the YAML to avoid confusion.

---

## 4. Deletion Plan Safety Analysis

The plan deletes ~2860 lines and replaces with ~210 lines. This is a 13:1 reduction. The ratio alone suggests the old system was over-engineered, which is a good sign for the new design.

### Safe to delete:

| File | Reason safe |
|------|-------------|
| `generate_hooks.py` (2155 lines) | Generates file hooks. SDK hooks replace this entirely. No other consumers. |
| `bash_guard.py` (173 lines) | Called by generated file hooks. SDK `evaluate()` replaces it. |
| `write_guard.py` (185 lines) | Called by generated file hooks. SDK `evaluate()` replaces it. |
| `role_guard.py` (~350 lines) | Role enforcement now in `should_skip_for_role()`. |

### Needs care:

| Item | Risk |
|------|------|
| **settings.json hook entries** | Must remove old file hook registrations. If any remain, Claude Code will try to call deleted scripts → errors on every tool use. Verify with a clean `settings.json` after deletion. |
| **Session marker system** | The old system used env vars (`CLAUDECHIC_APP_PID`) and marker files to track sessions. The new SDK hooks don't need session markers (role is captured in the closure). But `CLAUDECHIC_APP_PID` and `CLAUDE_AGENT_ROLE` env vars are still set in `_make_options()` (lines 777-782). Are these still needed? If only the old file hooks consumed them, they can be removed. If MCP or other systems read them, they must stay. |
| **`test_framework.py`** | Still exists in `.claude/guardrails/`. What is its relationship to the old system? If it tests file hooks, delete it. If it's independent, keep it. |

### Migration sequence matters:

The deletion must be atomic (single commit). If you delete `generate_hooks.py` but leave settings.json hook entries pointing to the old scripts, every tool call will error. If you remove settings.json entries but keep using file hooks somewhere, guardrails silently stop working.

**Recommended sequence:**
1. Merge PoC (SDK hooks active alongside old file hooks — both fire, SDK hooks are the real enforcement, old hooks are redundant but harmless)
2. Verify SDK hooks are enforcing correctly in real usage
3. Single commit: delete all old files + remove settings.json entries
4. Verify no regressions

---

## 5. Migration Risks

### 5A. Coverage gap during migration

The old system has `bash_guard.py` and `write_guard.py` with their own pattern matching logic. The new system uses `rules.yaml` patterns. Are the patterns identical? A subtle regex difference could mean a command that was blocked before now passes.

**Recommendation:** Before deleting old code, run both systems in parallel on the same inputs and diff the decisions. The PoC test file (`test_poc.py`) covers R01-R05 but doesn't compare against old system output.

### 5B. `warn` enforcement behavior change

As noted in RISK-2, `warn` currently acts as `deny` (blocks the tool call). If the old system's `warn` was truly advisory (logged but allowed), this is a behavioral regression. If the old system also blocked on warn, it's consistent. Verify before migration.

### 5C. Environment variable cleanup

`CLAUDE_AGENT_NAME`, `CLAUDECHIC_APP_PID`, `CLAUDE_AGENT_ROLE` are set in `_make_options()`. With SDK hooks, `agent_role` is captured in the closure — the env var `CLAUDE_AGENT_ROLE` is redundant for guardrail purposes. But removing it could break other consumers. Audit all references before removing.

### 5D. `rules.yaml` header comment is stale

Line 4-5 of `rules.yaml`: "To update enforcement: edit this file, then run: `python3 .claude/guardrails/generate_hooks.py`". After migration, this instruction points to a deleted file. Update the comment.

---

## 6. Simplification Opportunities

### 6A. Remove debug prints before merge

The PoC has 7 `print(..., file=sys.stderr)` calls. These are fine for PoC validation but should be replaced with proper logging (or removed) before merge. stderr prints in a TUI app can cause visual artifacts.

### 6B. The `evaluate` closure captures `app` by reference

Line 649: `app = self`. The closure captures `self` (the ChatApp instance). This is correct but means the hook holds a reference to the entire app. For the current design this is fine (the hook can't outlive the app). But if hooks are ever passed to external systems, this is a leak vector. Low risk, just noting.

### 6C. Import inside function

Lines 638-645 and 657-658: imports inside the function body. This was appropriate for PoC iteration speed. For production, move the `rules` imports to module level. Keep `sys` and `time` imports at module level too.

---

## Summary

| Area | Verdict |
|------|---------|
| Core mechanism (deny, user_confirm) | ✅ Proven, solid |
| `warn` enforcement | ⚠️ Acts as deny — clarify intent |
| Fail-open on error | ⚠️ Conscious decision needed |
| YAML re-parse per call | ⚠️ Fine now, cache before rule count grows |
| Phase filtering | ❌ Untested in live hooks |
| Hit logging | ❌ Not implemented |
| Concurrent agent safety | ⚠️ Mostly fine, needs atomic writes for phase_state |
| Deletion plan | ✅ Safe if done atomically with settings.json cleanup |
| Migration coverage gap | ⚠️ Verify regex parity with old guards before deleting |
| Startup validation | ❌ Not implemented (acknowledged in STATUS.md) |

**Bottom line:** The PoC validates the architecture. The remaining work is hardening, not redesign. The six items above (warn semantics, fail mode, caching, phase tests, hit logging, startup validation) are the gap between PoC and production. None are architecturally risky — they're all straightforward engineering tasks.

---

## 7. Re-review: SPECIFICATION.md Updated (2026-04-05)

After Composability updated the spec with the SDK hook architecture, re-reviewing my original concerns:

### ✅ RESOLVED: `warn` enforcement semantics (was RISK-2)

The spec now explicitly documents `warn` behavior in the enforcement levels table (§3.3):

| Level | Who decides | Agent can bypass? | SDK hook return |
|---|---|---|---|
| `warn` | Agent | Yes — agent acknowledges | `{"decision": "block", "reason": "..."}` (agent sees reason) |

This clarifies the intent: `warn` returns `block` **so the agent sees the reason**, but the agent "acknowledges and proceeds." The semantics are: the SDK delivers the block reason to the agent as context, and the agent can proceed on its next attempt. This is how Claude Code SDK hooks work — `block` with a reason is the mechanism for communicating information back to the agent. The agent is not truly blocked; it sees the reason and decides.

**Verdict:** Resolved. The code is correct. My original concern conflated "block" (the SDK return value) with "deny" (the enforcement policy). They're different — block is the delivery mechanism, deny is permanent rejection.

**One remaining question:** Does the SDK actually re-allow the tool on the agent's next attempt after a `warn` block? If the agent re-submits the same command, the same rule fires again and blocks again — creating an infinite loop. This needs either: (a) a per-session "acknowledged" set so warn rules fire once, or (b) documentation that warn rules should have narrow patterns that the agent can work around. The spec says "agent acknowledges" but doesn't specify the acknowledgment mechanism.

### ✅ RESOLVED: Fail-closed behavior (was RISK-3)

The spec now specifies a two-tier failure mode (§3.3 "Failure modes"):

- **Whole `rules.yaml` broken** (parse error): **fail-closed** — block all tool calls
- **Individual rule error** (bad regex, missing field): **fail-open** — skip broken rule, evaluate rest

This is the right design. It balances safety (broken file = all protection on) with graceful degradation (one bad rule doesn't kill everything). The PoC code still has `return {}` (fail-open) for all exceptions — the code needs updating to match the spec's two-tier model.

**Action needed:** The `evaluate()` function's try/except currently catches everything and returns `{}`. It needs to distinguish between YAML parse errors (fail-closed → `{"decision": "block"}`) and per-rule errors (fail-open → skip rule, continue loop).

### ✅ RESOLVED: No mtime caching — by design (was RISK-1)

The spec explicitly addresses this (§3.3 line 623): "**No mtime caching** — NFS mtime is unreliable on HPC clusters. At 2.4ms per parse, caching is unnecessary optimization."

This is a legitimate technical constraint I hadn't considered. On NFS (which this HPC environment uses), `stat().st_mtime` can be stale. Re-parsing every time is the correct choice for correctness on NFS. 2.4ms is budget.

**Verdict:** Resolved. My recommendation was wrong for this environment.

### ✅ RESOLVED: Deletion plan is atomic and sequenced (was §4/§5)

The spec's implementation order (§8.3) puts deletion in step 1 as part of PoC cleanup, with a clear GO/NO-GO gate: "if any rule doesn't evaluate correctly via SDK hooks, fix before proceeding." The risk table (§8.2) calls out "SDK hook regression when deleting file hooks" with mitigation: "Delete file hooks AFTER SDK hooks are fully wired for all agents; run full test suite."

**Verdict:** Resolved. The sequence is safe.

### ⚠️ PARTIALLY RESOLVED: `phase_state.json` atomic writes

The spec FAQ mentions `phase_state.json` atomic write (§10): "Temp-then-rename matches existing `HintStateStore` pattern." This is acknowledged but not yet in the code. The `read_phase_state()` function in `rules.py` will need a matching atomic writer wherever `phase_state.json` is written (likely in `WorkflowEngine`).

**Verdict:** Acknowledged in spec, needs implementation.

### ⚠️ NEW CONCERN: `warn` infinite loop risk

As noted above in the `warn` resolution — if `warn` returns `{"decision": "block"}` and the agent retries the same command, the same rule fires again. The spec says the agent "acknowledges and proceeds" but there's no mechanism for the agent to signal acknowledgment. This could create an infinite retry loop for warn-level rules.

**Possible solutions:**
1. **Don't use `warn` enforcement in v1.** No existing rules use it (R01-R05 are all `deny`). Defer the warn acknowledgment mechanism to when it's actually needed.
2. **Per-session acknowledged set.** After a warn fires once, record `(rule_id, tool_input_hash)` and skip on subsequent matches.
3. **Accept the loop.** The agent will eventually give up or change its approach. This is how Claude Code's built-in permission denials work — the agent adapts.

**Recommendation:** Option 1 (don't use `warn` in v1) is the simplest. No code needed, no risk. Add the mechanism in v2 when a real use case demands it.

### ⚠️ NEW CONCERN: `should_skip_for_phase` spec vs code mismatch

The spec's `should_skip_for_phase()` (§3.3 line 751-781) uses **qualified IDs** (`workflow_id:phase_id`), constructing them from `phase_state.get("workflow_id")` and `phase_state.get("phase_id")`. But the PoC code in `rules.py` (line 179) uses `phase_state.get("current_phase", "")` — a single unqualified field. The spec has evolved past the PoC code.

**Action needed:** When implementing step 4 (WorkflowEngine + phase state), update `rules.py`'s `should_skip_for_phase()` to match the spec's qualified ID format. This is straightforward but must not be forgotten.

### Summary of re-review

| Original concern | Status | Action needed? |
|---|---|---|
| `warn` acts as `deny` | ✅ Resolved — by design (SDK mechanism) | Defer `warn` usage to v2 (infinite loop risk) |
| Fail-open on error | ✅ Spec resolved (two-tier) | Update PoC code to match two-tier model |
| YAML re-parse per call | ✅ Resolved — NFS makes caching unreliable | None |
| Phase filtering untested | ⚠️ Still true | Test during step 4 implementation |
| No hit logging | ⚠️ Still true | Implement in step 1 (spec has `hits.py` ~30 lines) |
| Deletion plan safety | ✅ Resolved — sequenced with GO/NO-GO gate | None |
| `phase_state.json` atomic writes | ⚠️ Acknowledged, not implemented | Implement in step 4 |
| `warn` infinite loop | ⚠️ NEW | Don't use `warn` in v1 |
| `should_skip_for_phase` code vs spec | ⚠️ NEW | Update code in step 4 |

**Overall verdict:** The spec addresses my major concerns. Two new concerns surfaced (`warn` loop risk, phase code/spec drift) but both have simple mitigations. The architecture is sound. Proceed with implementation.
