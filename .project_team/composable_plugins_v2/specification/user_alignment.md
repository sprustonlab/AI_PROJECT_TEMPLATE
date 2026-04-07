# User Alignment Check — Composable Plugins v2

> **Agent:** UserAlignment
> **Date:** 2026-03-30
> **Input:** `userprompt.md` (source of truth), v1 `SPECIFICATION.md` (background)

---

## Original Request Summary

The user requests 5 incremental additions to the existing v1 system:

1. **Claudechic as git URL dependency** — replace committed code in `submodules/claudechic/` with a `pixi.toml` git URL dependency. Users get updates via `pixi update`.
2. **Developer mode for claudechic** — onboarding offers two modes: standard (git URL, auto-updates) vs developer (local clone, editable install). Switching is one line in `pixi.toml`.
3. **MCP Tools seam (#6)** — new `mcp_tools/` directory convention. Python files with `get_tools()` discovered at startup. ~20 lines of discovery code. Contract: `get_tools(**kwargs) -> list[tool_function]`.
4. **Bootstrap simplification** — replace `pip install copier` with `pixi exec --spec copier copier copy ...`. Two commands, one dependency (pixi).
5. **Cluster MCP inclusion** — port `cluster.py` into `mcp_tools/cluster.py`, toggled via Copier bool question. File presence = enabled.

---

## Alignment Status: ✅ ALIGNED (with clarifications needed)

The user prompt is clear, concrete, and well-scoped. Each of the 5 items has explicit implementation details, code snippets, and design rationale. The v2 request explicitly builds on v1 conventions (directory-is-the-plugin-system, Copier assembles, pixi manages envs). No fundamental misalignment detected.

---

## Clarifications Needed

### ❓ C1: MCP kwargs contract — open or closed set?

User said: `kwargs provide optional wiring: caller_name, send_notification, find_agent`

These three kwargs are listed as examples. Is this the **complete** set, or should the discovery code pass through **all** available context? This affects the contract surface area:
- **Closed set (only these 3):** simpler, easier to document, stable API
- **Open set (pass everything):** more flexible, but tools can depend on undocumented internals

**Recommend:** Treat as closed set for v2. Document these 3. Future kwargs require explicit addition.

### ❓ C2: Developer mode — what happens to existing `submodules/claudechic/` directory?

User said: Developer mode `clones repo locally into submodules/claudechic/, editable install, user hacks freely`

The v1 system already has code committed in `submodules/claudechic/`. The v2 standard mode removes this. Questions:
- In developer mode, does onboarding `git clone` fresh, or does it expect the user to clone manually?
- Is the `submodules/` directory gitignored in standard mode to prevent accidental commits?

**Recommend:** Onboarding should handle the clone automatically. Standard mode should gitignore `submodules/claudechic/`.

### ❓ C3: Cluster MCP config location

User said: `Config in .claudechic.yaml for SSH target, poll interval, etc.`

The v1 spec doesn't mention `.claudechic.yaml` as a configuration file. Is this a new file introduced in v2, or does it already exist in claudechic? If new, this is a 7th convention beyond the 6 seams — should it follow the seam pattern (directory convention) or is a single config file appropriate here?

**Recommend:** Clarify whether `.claudechic.yaml` already exists. If new, keep it simple — single file is fine for tool-specific config (not a seam).

### ❓ C4: `copier update` interaction with git URL dependency

User said: `copier update handles template evolution (3-way merge)` (from v1 design decisions, reaffirmed in v2)

When the template evolves the claudechic git URL (e.g., branch change, new repo), `copier update` would modify `pixi.toml`. But pixi.lock is generated — does `copier update` also need to regenerate the lockfile? Or is that left to the user to run `pixi install` after update?

**Recommend:** Document post-`copier update` workflow: user runs `pixi install` to sync lockfile.

---

## Scope Check

### ✅ No scope shrink detected
All 5 v1 seams are preserved. v2 adds seam #6 (MCP tools) without removing anything.

### ✅ No scope creep detected
All 5 items are explicitly requested with concrete implementation details. No gold-plating needed.

### ✅ Key v1 design decisions preserved
User explicitly reaffirms in "Key Design Decisions from v1 Analysis":
- Directory conventions ARE the plugin system (no framework)
- Copier assembles at creation time, no runtime dispatch
- Pixi is sole env backend
- Pure Python hooks for cross-platform

---

## Domain Term Check

### ✅ "Seam" — correctly used
User's usage of "seam" is consistent with v1: a filesystem convention boundary where components can be swapped independently. The new MCP Tools seam (#6) follows the same pattern (drop a file, it's discovered).

### ✅ "Developer mode" — clear meaning
User explicitly defines both modes with concrete behavior. No ambiguity.

### ✅ "Bootstrap" — clear meaning
User means the initial project creation workflow. Explicitly scoped to the two-command pixi flow.

---

## Wording Fidelity Check

| User's words | Potential spec drift to watch for | Risk |
|---|---|---|
| "~20 lines of discovery code" | Spec might over-engineer discovery into a framework | Medium |
| "Switching is one line in pixi.toml" | Spec might add a CLI command or wrapper script | Low |
| "File presence = enabled. Delete = disabled." | Spec might add an enable/disable config flag | Medium |
| "No PyPI publishing needed" | Spec might suggest publishing to PyPI "for convenience" | Low |
| "Two commands. One dependency (pixi)." | Spec might add prerequisites or intermediate steps | Medium |

---

## Recommendation (Phase 1)

The user prompt is exceptionally well-specified. Proceed to specification with these guidelines:

1. **Resolve C1–C4** during spec writing (defaults provided above are safe)
2. **Guard simplicity** — the user repeatedly emphasizes minimalism ("~20 lines", "one line", "two commands"). Any implementation that exceeds these targets needs justification.
3. **v2 is additive** — it adds to v1, doesn't restructure it. The spec should clearly delineate what's new vs inherited.
4. **Test the "file presence = enabled" contract** — this is a powerful, simple pattern. Ensure it's consistent across cluster MCP and any future MCP tools.

---

## Phase 2: Specification Review

> **Reviewed:** `specification/SPECIFICATION.md` (Draft, 2026-03-30)
> **Against:** `userprompt.md` (source of truth)

### Item-by-Item Alignment

#### ✅ Item 1: Claudechic as git URL dependency
- Spec Section 1 faithfully reproduces the exact `pixi.toml` snippet from userprompt.md
- Adds useful detail (lock pinning, version options) without changing the ask
- Correctly identifies what's removed (submodule, `.gitmodules`)
- **Verdict: Fully aligned**

#### ✅ Item 2: Developer mode for claudechic
- Copier question correctly implements the two-mode choice
- "Switching is one line in `pixi.toml`" — spec honestly acknowledges it's a 2-3 step *workflow* (clone + edit line + pixi install), but the actual `pixi.toml` diff IS one line. **This is fair.**
- Developer mode uses plain git clone (not git submodule) — good design choice, consistent with user intent
- `.gitignore` for `submodules/claudechic/` resolves clarification C2 ✅
- **Verdict: Fully aligned**

#### ⚠️ Item 3: MCP Tools seam (#6) — minor wording drift
- User said: "~20 lines of discovery code in claudechic's `mcp.py`"
- Spec says: "~30 lines in claudechic's `mcp.py`" (overview table) and provides ~30-line implementation
- The implementation is clean and minimal. The extra ~10 lines are logging, None-checks, and docstring — all justified. But the user's expectation was "~20 lines."
- **Recommendation:** Not a blocker. The implementation is honest and doesn't over-engineer. Accept as-is but note the delta.

- kwargs protocol: Spec adopts **closed set** per C1 recommendation ✅
- `get_tools(**kwargs) -> list[tool_function]` contract: Faithfully reproduced ✅
- Discovery rules (skip `_`-prefixed, skip non-.py, skip subdirs): Reasonable additions that follow the "directory conventions" philosophy ✅
- **Seam cleanliness rules** (no `claudechic.*` imports from mcp_tools): Good addition — enforces isolation without over-engineering
- **Verdict: Aligned with minor wording delta (acceptable)**

#### ✅ Item 4: Bootstrap simplification
- Exact same two commands from userprompt.md reproduced
- "Two commands. One dependency (pixi). Copier is never permanently installed." — verbatim alignment ✅
- Adds copier version pinning (`--spec "copier>=9,<10"`) — sensible, not scope creep
- Post-`copier update` workflow documented per C4 ✅
- **Verdict: Fully aligned**

#### ✅ Item 5: Cluster MCP inclusion
- Port from correct source path
- 6 tools match user list: cluster_jobs, cluster_status, cluster_submit, cluster_kill, cluster_logs, cluster_watch ✅
- Copier question matches user's YAML exactly ✅
- "File presence = enabled. Delete = disabled." — spec says "File presence = enabled. No manifest, no config toggle." ✅
- Config in `.claudechic.yaml` — spec provides concrete schema and resolves C3 (it's tool-specific config, not a new seam) ✅
- **Verdict: Fully aligned**

### Scope Check

#### ✅ No scope shrink
All 5 user items are present and complete. No features deferred or removed.

#### ✅ No meaningful scope creep
Additions beyond the user prompt:
- Version pinning options for git URL (Section 1) — helpful documentation, not new functionality
- Compositional laws (Sections 2, 3) — formalize swap-test thinking from v1, not new requirements
- Seam cleanliness rules (Section 3) — enforce the isolation the user already expects
- Testing strategy — necessary for implementation, not scope creep
- Response helpers in `_helpers.py` — minor convenience, appropriate

**None of these additions change what gets built.** They document conventions and testing.

### Wording Fidelity Check (from Phase 1 watchlist)

| User's words | Spec's words | Status |
|---|---|---|
| "~20 lines of discovery code" | "~30 lines" + actual code shown | ⚠️ Minor delta — justified by logging/safety |
| "Switching is one line in pixi.toml" | "Only `pixi.toml` (1 line) and `pixi.lock` (regenerated) change" | ✅ Faithful |
| "File presence = enabled. Delete = disabled." | "File presence = enabled. No manifest, no config toggle." | ✅ Same meaning |
| "No PyPI publishing needed" | Not mentioned (implicit) | ✅ No PyPI suggested |
| "Two commands. One dependency (pixi)." | Verbatim reproduced | ✅ Exact match |

### Simplicity Guardrail

The spec respects the user's minimalism emphasis throughout:
- No frameworks introduced
- No runtime dispatch
- No manifest files
- Discovery is a single function
- The "Files Changed by v2" table is small (6 template files + 1 claudechic file)
- Implementation order is 5 clear steps

### Overall Verdict

## ✅ ALIGNED

The specification faithfully represents all 5 user-requested items. One minor wording delta (~20 vs ~30 lines for discovery code) is justified and does not indicate over-engineering. All 4 Phase 1 clarifications (C1–C4) have been resolved with sensible defaults. No scope creep. No scope shrink. The spec is ready for implementation.
