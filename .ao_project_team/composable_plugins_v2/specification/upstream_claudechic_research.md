# Research Report: Upstream Claudechic (abast) — Recent Additions

**Requested by:** Coordinator
**Date:** 2026-03-30
**Tier of best source found:** T1 (direct git repository analysis)

## Query

What has `abast/claudechic` (upstream) added recently that's NOT in the `boazmohar/claudechic` fork? Should any upstream features be incorporated into v2?

---

## Summary

**Upstream (abast/main) has 20 commits NOT in boazmohar/main.** These include several major features, important bug fixes, and infrastructure improvements. Conversely, **boazmohar/main has 18 commits NOT in upstream**, mostly cluster MCP tools and message metadata features.

The two branches have **diverged significantly** — they share a common ancestor around `e72a5e8` (Default agent model to opus) but have taken different paths since.

---

## Upstream-Only Commits (20 commits, newest first)

### 🔴 Critical Features (should sync)

#### 1. Soft-Close Agents with `/agent reopen` (b43c109)
- **Author:** Arco Bast, 2026-03-28
- **Files:** agent_manager.py (+81), app.py (+43), commands.py (+24), formatting.py (+28), mcp.py (+7)
- **What it does:** Closed agents are preserved in topology with `"closed": true` instead of being deleted. New `closed_agents` dict in AgentManager, `find_closed_by_name()`, `reopen()` method. New `/agent reopen <name>` command. spawn_agent blocks name collision with closed agents.
- **Why it matters for v2:** This is a significant UX improvement for multi-agent workflows. The MCP seam (#6) should be aware of this — our `mcp_tools/` plugins may interact with agent lifecycle.
- **Relevance:** HIGH

#### 2. Requires-Answer Nudge System (15af6db)
- **Author:** Arco Bast, 2026-03-28
- **Files:** agent.py (+11), app.py (+78), mcp.py (+44)
- **What it does:** `spawn_agent` gains optional `requires_answer` boolean. If true, the spawned agent is tracked as owing a reply. If idle 15s without `tell_agent`, it's nudged (up to 3 times). Safety: caller-gone detection, nudge cap, ask_agent doesn't clear obligation.
- **Why it matters for v2:** This directly affects our project team workflow. Currently agents can "forget" to report back. This is the fix. Also changes `spawn_agent`'s MCP schema from positional `{str, str, str, str, str}` to a proper JSON Schema object — **breaking change** for any code that calls spawn_agent.
- **Relevance:** CRITICAL — the spawn_agent schema change alone requires a sync

#### 3. Multi-Agent Topology Persistence for `--resume` (fd0e678)
- **Author:** Arco Bast, 2026-03-26
- **Files:** agent_manager.py (+22), app.py (+153), sessions.py (+75)
- **What it does:** Saves agent topology as `{session_id}.topology.json` sidecar file. On `--resume`, subagents are reconnected with their history. Atomic writes (write-to-temp + rename).
- **Why it matters for v2:** Essential for long-running scientific workflows. If a user's claudechic session crashes, they can resume with all agents intact. Our project team workflow (5+ agents) especially benefits.
- **Relevance:** HIGH

#### 4. Improved MCP close_agent (13f6a7b)
- **Author:** Arco Bast, 2026-03-26
- **Files:** app.py (+14), mcp.py (+75/-34)
- **What it does:** `close_agent` is now a factory (`_make_close_agent`) that binds `caller_name`, preventing self-close. `_close_worktree_agent` made async. Extracts `_close_agent_core()` from `_do_close_agent()` for direct await (avoids race conditions).
- **Why it matters for v2:** Fixes real race conditions in multi-agent close. Direct impact on our multi-agent project team.
- **Relevance:** HIGH

### 🟡 Important Bug Fixes (should sync)

#### 5. Fix ExitPlanMode GUI Freeze (a4307c7)
- **Author:** Arco Bast, 2026-03-28
- **Files:** app.py, mcp.py
- **What:** Fixes deadlock where `await agent.set_permission_mode()` inside SDK permission callback causes freeze. Also saves/restores pre-plan permission mode.
- **Relevance:** HIGH — affects daily UX

#### 6. Fix Model Switch Losing Conversation Context (73b2104)
- **Author:** Arco Bast, 2026-03-27
- **What:** `_set_agent_model` now preserves session_id through disconnect/reconnect.
- **Relevance:** MEDIUM

#### 7. Fix Model Selector Short Aliases (8f17ec3)
- **Author:** Arco Bast, 2026-03-28
- **What:** Adds `_model_matches()` for alias-to-full-name matching (e.g., "opus" matches "claude-opus-4-6").
- **Relevance:** MEDIUM

#### 8. Fix ExitPlanMode Race (24e2af5)
- **Author:** Arco Bast
- **What:** Desyncs permission mode from SDK. Defense-in-depth fix.
- **Relevance:** MEDIUM

#### 9. Fix diff viewer for paths containing 'b/' (6a93fd8)
- **Source:** PR #55
- **Relevance:** LOW-MEDIUM

#### 10. Recover from CLIJSONDecodeError (3a16e6c)
- **What:** Feeds JSON decode errors back to agent instead of crashing.
- **Relevance:** MEDIUM

### 🟢 Enhancements (nice to have)

#### 11. Diagnostics Modal (8ec39d6)
- **Files:** New `widgets/modals/diagnostics.py` (+196 lines)
- **What:** Clickable footer opens modal showing session JSONL path + compaction summary. Useful for debugging.
- **Relevance:** LOW-MEDIUM (nice for debugging)

#### 12. High-CPU Episode Detection (1684df4)
- **Files:** sampling.py (+160), widgets/modals/profile.py (+167), tests/test_sampling.py (+180)
- **What:** Detects high-CPU episodes with automatic diagnostics. Event loop lag monitoring.
- **Relevance:** LOW-MEDIUM (performance debugging)

#### 13. Ctrl+C Copy Selection (1a91efa)
- **What:** Ctrl+C copies text selection when selected, quits when nothing selected.
- **Relevance:** LOW (UX polish)

#### 14. Symlink .claude/ into Worktrees (61f6e21)
- **Author:** Matthew Rocklin
- **What:** Hooks, skills, and local settings are shared with worktrees via symlink.
- **Relevance:** MEDIUM — affects worktree UX

#### 15. Tell Calling Agent to Wait (28f929a)
- **What:** After spawning reviewer, tells caller to wait.
- **Relevance:** LOW

### 🔵 Infrastructure

#### 16. Bump claude-agent-sdk to >=0.1.40 (2bb33aa)
- **What:** Fixes rate_limit_event crash, enables Opus 4.6 support.
- **Relevance:** HIGH — needed for current SDK version

#### 17. Rewrite yolo flag tests + config module tests (70881af)
- **Files:** tests/test_config.py (+306), tests/test_yolo_flag.py (refactored)
- **Relevance:** MEDIUM

#### 18. Fix compaction summary format (55847f9)
- **Relevance:** LOW

#### 19. Fix pyright excluding .venv (bc7b36c)
- **Relevance:** LOW

#### 20. Fix CSS recalc perf (adb08b2)
- **Note:** boazmohar also has this commit (7dd6c01) — cherry-picked independently.
- **Relevance:** Already in fork

---

## Upstream-Only Feature Branches

### `upstream/credit-limits` (20+ commits ahead of upstream/main)
Contains significant features NOT yet in upstream/main:
- **PyPI release workflow** — publishing infrastructure
- **Responsive layout** — sidebar overlay, hamburger button for narrow screens
- **Collapsed tool headers with micro-summaries**
- **Truncation indicators for long tool results**
- **Skill tool display improvements**
- **`--version` flag + uv tool install fix**
- **`/welcome` command**
- **Agent decoupled from UI widgets** (architectural refactor)
- **Enums for tool names, agent status, permissions** (code quality)

This branch appears to be the next major release candidate. It's a substantial refactor.

### `upstream/fix-underscore-path-lookup`
Contains the session lookup fix for paths with underscores. Already cherry-picked to upstream/main.

---

## Boazmohar-Only Commits (18 commits, not in upstream)

For context, here's what the fork has that upstream doesn't:

| Feature | Commits |
|---------|---------|
| **Cluster MCP tools** (cluster_submit, cluster_logs, SSH multiplexing, etc.) | 7 commits |
| **Message metadata** (timestamps, model, token usage, cost display) | 5 commits |
| **Guardrail env vars** (CLAUDE_AGENT_NAME, CLAUDECHIC_APP_PID, CLAUDE_AGENT_ROLE) | 2 commits |
| **spawn_agent type param + model inheritance** | 2 commits |
| **Textual TextArea patch** | 1 commit |
| **Fix interrupt timeout crash** | 1 commit |

**Important conflict:** Upstream REMOVED `MessageMetadata` dataclass and timestamp/model fields from `ChatItem` and session loading. The boazmohar fork added these same fields. This will be a **merge conflict**.

**Important conflict:** Upstream removed `agent_type` parameter from `AgentManager.create()` and `_create_sdk_options()`. The boazmohar fork added it (for guardrail env vars). This will be a **merge conflict**.

**Important conflict:** Upstream changed `spawn_agent` schema from positional `{str, str, str, str, str}` to JSON Schema object (adding `requires_answer`). The boazmohar fork also modified spawn_agent (adding `type` and `model`). **Conflicting changes to the same function.**

---

## Recommendation

### Priority 1: Sync Critical Features (before v2 spec is finalized)

These upstream features should be merged into the boazmohar fork:

1. **Requires-answer nudge system** — directly improves our project team workflow reliability
2. **Soft-close with `/agent reopen`** — major UX improvement for multi-agent
3. **Multi-agent topology persistence** — essential for session resume
4. **Improved close_agent (factory pattern, self-close prevention)** — fixes real race conditions
5. **SDK bump to >=0.1.40** — needed for current Opus 4.6

### Priority 2: Merge Bug Fixes

6. **ExitPlanMode freeze fix** — daily UX impact
7. **Model switch context loss fix** — important for model switching
8. **CLIJSONDecodeError recovery** — resilience
9. **Worktree .claude/ symlink** — affects worktree users

### Priority 3: Watch the `credit-limits` Branch

The `upstream/credit-limits` branch contains a significant refactor (agent decoupled from UI, enums, responsive layout). This may change the architecture enough to affect v2 decisions. Worth monitoring but NOT blocking on.

### Merge Strategy

The divergence is significant enough that a simple `git merge upstream/main` will produce conflicts. Recommended approach:

1. **Create a sync branch** on the boazmohar fork
2. **Merge upstream/main** into it
3. **Resolve conflicts manually**, especially:
   - MessageMetadata: keep boazmohar's metadata feature but reconcile with upstream's session loading changes
   - spawn_agent: merge both `requires_answer` (upstream) and `model`/`type` (boazmohar) into the JSON Schema
   - agent_type/guardrail env vars: boazmohar needs these; upstream removed them. Keep boazmohar's version
4. **Test thoroughly** — both branches have test changes

### v2 Spec Implications

1. **MCP seam (#6)** should be designed knowing that `spawn_agent` now uses JSON Schema (not positional args) and has `requires_answer`
2. **mcp_tools/ discovery** should account for `_make_close_agent` factory pattern — tools may need `caller_name` binding
3. **Cluster MCP** (boazmohar-only) is not affected by any upstream changes
4. **The claudechic git URL dependency** in `pixi.toml` should point to the boazmohar fork AFTER the sync is complete

---

## ⚠️ Domain Validation Required

The `requires_answer` nudge system involves timing-dependent async behavior (15s idle detection, up to 3 nudges). This needs careful testing in the actual multi-agent project team workflow to verify:
- Nudge timing doesn't interfere with long-running agent tasks
- Caller-gone detection works correctly when agents are closed during team workflows
- The 15s/3-nudge defaults are appropriate for scientific project workflows (may need tuning)

---

## Sources

- Direct `git log`, `git diff`, `git show` analysis of local clone at `/groups/spruston/home/moharb/DECODE-PRISM/Repos/claudechic/`
- Upstream remote: `https://github.com/abast/claudechic.git`
- Fork remote: `https://github.com/boazmohar/claudechic.git`
- Both repos are private; analysis performed via local clone with both remotes configured

## Not Recommended

| Action | Why |
|--------|-----|
| Merging `upstream/credit-limits` now | Too large, still in development, would complicate v2 timeline |
| Ignoring upstream entirely | Missing critical fixes (SDK bump, race conditions, plan mode freeze) |
| Rebasing boazmohar onto upstream | Too destructive — boazmohar has published branches. Merge is safer |
