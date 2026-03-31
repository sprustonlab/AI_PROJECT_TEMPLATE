# Skeptic Spec Review — SPECIFICATION.md v2

> **Reviewer:** Skeptic
> **Date:** 2026-03-30
> **Phase:** Specification review (comparing spec against original skeptic_review.md findings)
> **Verdict:** **PASS.** All 5 risks addressed. One minor gap remains. No over-engineering detected.

---

## Risk-by-Risk Assessment

### Risk 1: MCP `get_tools()` Contract Under-Specified — **RESOLVED**

**Original finding:** Return type, kwargs signatures, error handling undefined. "~20 lines" optimistic.

**What the spec delivers:**
- **Return type:** `list[SdkMcpTool]` — concrete, references `claude_agent_sdk`'s `@tool` decorator (§3 "Tool function shape")
- **kwargs protocol:** Closed set, each kwarg has explicit type and "Default if absent" column (§3 "kwargs protocol"). `caller_name: str | None`, `send_notification: Callable | None`, `find_agent: Callable | None`
- **Error handling:** "The Iron Rule" table (§3) specifies behavior for 5 failure conditions — ImportError, SyntaxError, missing `get_tools()`, exception in `get_tools()`, missing directory. All logged, all skipped, never crash.
- **Line count:** Updated to "~30 lines" with actual discovery code shown inline. The code is 30 lines. Honest.
- **Degradation Law:** "get_tools() MUST NOT raise when called with fewer kwargs than expected" — this was my specific concern about kwargs evolution.
- **Isolation Law:** "A tool file MUST be testable by importing directly without claudechic installed" — this enforces the seam boundary I demanded.
- **Factory pattern for wired tools:** Concrete example of closure-based kwargs consumption.

**Assessment:** This is thorough. The discovery code is shown inline — an implementer can copy-paste it. The kwargs are typed with explicit signatures. The compositional laws prevent drift. My HIGH severity finding is fully addressed.

**One minor note:** The `send_notification` signature is shown as `(agent, message, *, caller_name) -> None` in the kwargs table. But `_send_prompt_fire_and_forget` in the current `mcp.py` has additional keyword args (`expect_reply`, `is_spawn`). The spec should clarify: does the kwargs protocol expose the full signature or a simplified one? This is an implementation detail, not a spec gap — the cluster port only needs the basic signature. Mentioning for the implementer's awareness.

---

### Risk 2: Git URL Update Semantics Ambiguous — **RESOLVED**

**Original finding:** Does pixi.lock pin SHA? Does pixi-pack work? Offline HPC?

**What the spec delivers:**
- **Lock pinning:** "pixi.lock pins exact commit SHA — byte-for-byte reproducible" (§1 Key behaviors table). Explicit.
- **pixi install behavior:** "Respects lock file — does NOT pull new commits." This answers my reproducibility concern directly.
- **pixi-pack:** "NOT supported for git URL deps — developer mode is the offline workaround" (§1 Key behaviors table). Honest — they don't claim it works, they provide the workaround.
- **Version pinning options:** §1 shows three options (branch tracking, tag pinning, commit pinning). This gives users control over the reproducibility/freshness tradeoff.
- **Network:** "Required for initial install and updates" — transparent about the constraint.

**Assessment:** Every question I asked is answered with a one-line entry in the Key behaviors table. The pixi-pack gap is addressed honestly (developer mode as workaround, not hand-waving). The version pinning options give users explicit control.

**Remaining question (not a blocker):** The "pixi.lock pins exact commit SHA" claim — has this been empirically verified, or is it documented pixi behavior? If unverified, it should be the first thing tested in implementation. The entire reproducibility story depends on it.

---

### Risk 3: Developer Mode "One Line" Misleading — **RESOLVED**

**Original finding:** Actually 3-5 steps, not one line.

**What the spec delivers:**
- **Switching workflow** (§2): Documented as explicit numbered steps — Standard→Developer is 3 steps, Developer→Standard is 2 steps. No "one line" claim.
- **Swap test:** Correctly identifies what changes (1 line in pixi.toml + pixi.lock regeneration) vs. the full workflow.
- **Risks table:** "Developer mode switching not 'one line'" listed at Low severity with "Documented as 2-3 step workflow."

**Assessment:** The spec is honest. The userprompt said "one line" — the spec corrects this to the real workflow. This is exactly what I asked for.

---

### Risk 4: Cluster MCP Port — Tight Coupling to Claudechic — **RESOLVED**

**Original finding:** Port requires refactoring, not just copying. `claudechic.config` and `claudechic.tasks` imports need removal.

**What the spec delivers:**
- **Port scope:** "This is a port + decouple, not a copy" (§5). Honest framing.
- **Line-by-line change table:** Shows exactly what's removed (2 claudechic imports) and what replaces them (`_load_config()` at +8 lines, `_create_safe_task()` at +15 lines, `get_tools()` at +20 lines).
- **Config replacement:** Inline `_load_config()` reads YAML directly — no claudechic dependency. Falls back through two paths (cwd, home). Handles missing pyyaml.
- **Task replacement:** Inline `_create_safe_task()` is a 7-line asyncio wrapper with exception logging.
- **Post-port verification:** "Zero claudechic imports. Only dependencies: `claude_agent_sdk` + `pyyaml`. Testable in isolation with mock SSH."
- **Seam cleanliness rules:** Explicit table — `claudechic.*` imports are **NO**.

**Assessment:** The spec shows the actual replacement code. An implementer knows exactly what to write. The "~50 lines changed out of ~780" estimate is credible given the change table. My concern about under-scoping is fully addressed.

---

### Risk 5: Bootstrap `pixi exec --spec copier` Untested — **RESOLVED**

**Original finding:** Version pinning, PyPI vs conda-forge, first-run performance, git availability.

**What the spec delivers:**
- **Version pinning:** "Copier version should be pinned: `--spec 'copier>=9,<10'`" (§4 Implementation notes).
- **conda-forge:** "creates a temporary env with the `copier` package from conda-forge" — explicitly states the source.
- **Git dependency:** "Git must be available on the system (Copier needs it to clone the template)" — transparent about the prerequisite.
- **First-run:** "First-run downloads copier + dependencies — document expected wait time" — acknowledges the issue, defers to documentation.
- **Risks table:** "pixi exec --spec copier version drift" listed at Medium severity with pinning mitigation.
- **Integration tests:** "pixi exec --spec copier copier copy end-to-end on clean machine" — in the testing strategy.

**Assessment:** All my concerns are either addressed in the spec or explicitly listed in the testing strategy. The version pinning is concrete. The git prerequisite is documented rather than assumed. The first-run performance is acknowledged as something to document.

---

## Over-Engineering Check

Is anything in this spec unnecessary or premature?

**No.**

- The MCP seam is the only new system. It's ~30 lines of discovery code. It follows the same "directory = plugin system" pattern as the other 5 seams.
- The cluster port is a user requirement with concrete scope.
- The git URL dependency is a simplification (removes submodule machinery).
- The bootstrap is a documentation change with a Copier update.
- Developer mode is a Copier question + 1 conditional line.

The spec explicitly limits scope: "NOT changed: All 5 v1 seam directories, activate script, guardrail hooks, agent roles, pattern miner." This is the right discipline.

**The `_helpers.py` convention** (§3 "Seam cleanliness rules") is the only thing that could be premature — shared response helpers before there are multiple tools to share them. But it's a 10-line file, not a framework, and it prevents copy-paste duplication between cluster.py and future tools. Acceptable.

---

## One Gap (Not a Blocker)

**The `SdkMcpTool` type reference.** The spec uses `list[SdkMcpTool]` as the return type of `get_tools()`, but `SdkMcpTool` isn't a real type from `claude_agent_sdk`. Looking at the current `mcp.py`, the `@tool` decorator returns an async function. The actual type is something like `Callable[[dict], Awaitable[dict]]` or whatever `claude_agent_sdk.tool` wraps it in.

The spec should either:
- Use the actual type from `claude_agent_sdk` (if one exists), or
- Say `list` with a comment: "each element is a `@tool`-decorated async function"

This won't block implementation — the discovery code uses `list` (untyped) anyway — but a contributor reading "SdkMcpTool" will grep for it and find nothing.

---

## Summary

| Original Risk | Severity | Status | How Addressed |
|---------------|----------|--------|---------------|
| MCP `get_tools()` contract | HIGH | **Resolved** | Full contract with types, error table, compositional laws, inline code |
| Git URL semantics | MEDIUM | **Resolved** | Key behaviors table, explicit lock/pixi-pack/network answers |
| Developer mode "one line" | LOW-MEDIUM | **Resolved** | Documented as 2-3 step workflow |
| Cluster MCP coupling | MEDIUM | **Resolved** | Port + decouple scoped with line-by-line change table |
| Bootstrap `pixi exec` | MEDIUM | **Resolved** | Version pinning, git prereq, first-run acknowledged, e2e test planned |

**Verdict: PASS.** The spec addresses every risk from the vision review. The scope is right — 5 concrete changes, no frameworks, no speculation. Ready for implementation.
