# Skeptic Review — Composable Plugins v2 Vision

> **Reviewer:** Skeptic
> **Date:** 2026-03-30
> **Phase:** Specification — Challenge assumptions, identify risks and failure modes
> **Verdict:** Vision is **sound but has 5 risks** that need explicit mitigation before implementation. The scope is right — the problems are in under-specified interfaces and untested assumptions.

---

## 1. The Vision Is Directionally Correct

The v2 additions are well-motivated:
- **Git URL dependency** removes committed code — less repo bloat, clearer ownership
- **MCP tools seam** follows the same "directory = plugin system" pattern that works for the other 5 seams
- **Bootstrap simplification** reduces from 2 dependencies (pip + copier) to 1 (pixi) — genuine improvement
- **Cluster MCP inclusion** is a user requirement, not speculative

None of these are framework-building. All are concrete, user-facing changes. Good.

---

## 2. Risk 1: MCP Tools Seam — The `get_tools()` Contract Is Under-Specified

**Severity: HIGH — this is the architecturally novel part and needs precision.**

The userprompt says:
> Seam contract: `get_tools(**kwargs) -> list[tool_function]`
> kwargs provide optional wiring: `caller_name`, `send_notification`, `find_agent`

### What's Missing

**2a. What IS a `tool_function`?**

Looking at claudechic's current `mcp.py`, tools are created with `@tool` from `claude_agent_sdk`. The `create_chic_server()` function collects them and passes to `create_sdk_mcp_server()`. A tool function is a specific thing — an `async def` decorated with `@tool(name, description, schema)`.

The v2 proposal says claudechic discovers `mcp_tools/*.py` files and calls `get_tools()`. But the discovered tools need to be registered into the MCP server. This means:
1. The discovery code in `mcp.py` must import from external files at startup
2. The returned tools must be compatible with `create_sdk_mcp_server()`
3. Error handling for malformed tool files must not crash claudechic

**The ~20 lines claim is optimistic.** Discovery + import + error handling + registration is more like 40-60 lines, and the edge cases (import errors, missing `get_tools`, wrong return type) need handling or claudechic crashes on startup.

**2b. The `kwargs` wiring creates implicit coupling.**

The contract says `get_tools(**kwargs)` receives `caller_name`, `send_notification`, `find_agent`. But:
- `send_notification` — what's the signature? What does it notify? The UI? The agent?
- `find_agent` — this is `_find_agent_by_name` from `mcp.py`, which depends on the global `_app` reference. Exposing this means tool plugins can interact with claudechic internals.
- What happens when kwargs evolve? A tool written for v2.0 kwargs breaks when v2.1 changes them.

**This is essential complexity** — the user asked for it, so we solve it, not avoid it. But we need:
1. An explicit type definition for tool functions (or at least document: "must be `@tool`-decorated async functions from `claude_agent_sdk`")
2. Explicit signatures for each kwarg callback
3. A versioning strategy or stability promise for kwargs

### Failure Mode

A user writes `mcp_tools/my_tool.py` with `get_tools()`, claudechic updates, kwargs change, tool breaks silently at import time. User sees "tool not available" with no indication why.

**Recommendation:** Define the contract precisely. Make kwargs opt-in (tool declares what it needs, discovery provides only those). Log clearly when a tool file fails to load.

---

## 3. Risk 2: Git URL Dependency — Update Semantics Are Ambiguous

**Severity: MEDIUM — affects day-to-day developer experience.**

The userprompt says:
```toml
[pypi-dependencies]
claudechic = { git = "https://github.com/boazmohar/claudechic", branch = "main" }
```

And: "Users get updates via `pixi update`."

### What's Actually True

Currently `pixi.toml` has:
```toml
claudechic = { path = "submodules/claudechic", editable = true }
```

Switching to a git URL means:
1. **No more editable install** in standard mode — changes to claudechic require `pixi update` to take effect
2. **`pixi update` pulls latest main** — no pinning. If someone pushes a breaking change to `boazmohar/claudechic` main, every `pixi update` pulls it into every project
3. **Lock file behavior unclear** — does `pixi.lock` pin the git commit? If yes, updates are explicit (good). If no, installs are non-deterministic (bad).

### Questions That Need Answers

- Does `pixi.lock` record the exact git commit SHA for a git URL pypi-dependency? (This is critical for reproducibility.)
- What happens during `pixi install` if the network is down and the git URL isn't cached? (HPC nodes often lack internet.)
- Can `pixi-pack` bundle a git URL dependency for offline use?

### Failure Mode

Researcher A creates a project Monday. Researcher B creates one Friday. A breaking change to claudechic main lands Wednesday. A has the old version (locked), B has the new version. Neither knows they're running different code. Standard "works on my machine" debugging nightmare.

**Recommendation:** Spec must clarify: (a) whether pixi.lock pins git commits (verify empirically), (b) whether pixi-pack works with git URL deps (verify empirically), (c) whether to pin to a tag/release rather than branch for standard mode.

---

## 4. Risk 3: Developer Mode Switching — "One Line" Is Misleading

**Severity: LOW-MEDIUM — affects developer experience, not correctness.**

The userprompt says:
> Switching is one line in `pixi.toml`.

Switching from git URL to editable local:
```toml
# From:
claudechic = { git = "https://github.com/boazmohar/claudechic", branch = "main" }
# To:
claudechic = { path = "submodules/claudechic", editable = true }
```

But this also requires:
1. Cloning the repo into `submodules/claudechic/` (if not already there)
2. Running `pixi install` to resolve the new dependency
3. Possibly dealing with version conflicts if the local clone is at a different commit than what pixi.lock had

And switching back requires:
1. Ensuring local changes are committed/stashed (or they're lost from the dep perspective)
2. Editing pixi.toml back
3. Running `pixi install` again

**This is 3-5 steps, not "one line."** Calling it "one line" sets wrong expectations.

**Recommendation:** Be honest about the switching workflow. Document it as a 4-step process. Consider a `commands/dev-mode` script that automates the switch. But don't over-engineer — a documented process is fine for a developer audience.

---

## 5. Risk 4: Cluster MCP Port — Tight Coupling to Claudechic Internals

**Severity: MEDIUM — this determines whether the MCP seam is actually a seam.**

Looking at the cluster.py source (775 lines), it imports:
```python
from claude_agent_sdk import tool
from claudechic.config import CONFIG
from claudechic.tasks import create_safe_task
```

And the `cluster_watch` tool uses `_send_prompt_fire_and_forget` from `mcp.py` to notify agents when jobs complete.

If we're porting this to `mcp_tools/cluster.py` (the new seam), it:
1. **Cannot import from `claudechic`** — the whole point of the seam is independence from claudechic internals
2. **Needs `send_notification` via kwargs** — this is why kwargs exist, but the function must provide equivalent functionality to `_send_prompt_fire_and_forget`
3. **Needs `CONFIG` access** — for SSH target, poll interval. Where does configuration live for seam-based tools?

### The Real Question

Is `mcp_tools/cluster.py` truly a seam plugin, or is it "claudechic code that lives in a different directory"?

If cluster.py needs:
- claudechic's config system
- claudechic's task runner
- claudechic's agent notification system
- claudechic's `@tool` decorator

Then it's not independent — it's an extension module with a different import path. That's fine! But call it what it is. Don't claim seam independence if the tool can't function without claudechic's specific wiring.

### The Swap Test

A true seam plugin should work if you swap claudechic for a different MCP host. Can `cluster.py` work with a non-claudechic MCP server? Only if:
- `@tool` decorator is from `claude_agent_sdk` (not claudechic) — ✓ this is fine
- Config comes from env vars or a standalone config file — ✓ cluster.py already reads env vars as primary
- Notification comes through kwargs interface — ✓ if kwargs contract is well-defined

So the seam CAN work, but the port requires refactoring cluster.py to remove `claudechic.config` and `claudechic.tasks` imports. The userprompt says "port," but the scope is actually "port + refactor to remove claudechic coupling." That's more work than a straight port.

**Recommendation:** Explicitly scope the port as: (a) extract cluster logic from claudechic imports, (b) use env vars for config (already partially done), (c) receive agent notification capability via kwargs. Estimate accordingly — this is not a copy-paste port.

---

## 6. Risk 5: Bootstrap — `pixi exec --spec copier` Is Untested for This Use Case

**Severity: MEDIUM — this is the user's first experience.**

The userprompt says:
```bash
pixi exec --spec copier copier copy https://github.com/sprustonlab/AI_PROJECT_TEMPLATE my-project
```

### Assumptions to Verify

1. **Does `pixi exec --spec copier` work?** — `pixi exec` runs a command in an ephemeral environment. But `--spec copier` means "create an env with the `copier` package." Where does it come from — conda-forge or PyPI? Copier is a Python package (PyPI). Does `pixi exec --spec` support PyPI packages, or only conda-forge?

2. **Copier's git template fetching** — Copier needs git to clone the template. Does the ephemeral `pixi exec` env include git? On a fresh machine, git might not be available inside pixi's ephemeral env.

3. **Copier version pinning** — `--spec copier` without a version gets latest. Copier 9.x → 10.x could break the template's `copier.yml`. Should this be `--spec copier==9.*`?

4. **Performance** — `pixi exec` creates an ephemeral env every time. On first run, it downloads copier + dependencies. How long does this take? If it's 30+ seconds on a fresh machine, the "2 commands" simplicity claim is undermined by a poor first-run experience.

### Failure Mode

User follows the 2-command bootstrap. `pixi exec --spec copier` fails because copier isn't on conda-forge (it IS on conda-forge, but version may lag). Or it works but pulls copier 10.x which changed its YAML schema. User gets a cryptic error on their first interaction with the template.

**Recommendation:** Test `pixi exec --spec copier copier copy <git-url> <dir>` end-to-end on a clean machine (or clean pixi cache). Pin copier version. Document expected first-run time.

---

## 7. What's NOT a Risk (Confirming Sound Decisions)

### 7a. Directory conventions as plugin system
Still correct. v2 adds one seam (MCP tools) using the same pattern. No framework creep.

### 7b. Copier for onboarding
Still correct. Copier handles the `use_cluster` toggle naturally — it's just another conditional file.

### 7c. Pixi as sole backend
v1 already validated this. v2 doesn't change the env management story. Good.

### 7d. Scope
5 changes, all concrete, all user-requested. No speculative features. The v1 skeptic reviews eliminated the framework tendencies — v2 doesn't reintroduce them.

---

## 8. Summary Table

| Risk | Severity | Core Issue | Recommendation |
|------|----------|-----------|----------------|
| MCP `get_tools()` contract under-specified | **High** | Return type, kwargs signatures, error handling undefined | Define precise contract with types, opt-in kwargs, error logging |
| Git URL update semantics | **Medium** | Lock pinning, offline behavior, reproducibility unclear | Verify pixi.lock pins commits, test pixi-pack with git deps, consider tag pinning |
| Developer mode "one line" claim | **Low-Medium** | Actually 3-5 steps | Document honest workflow, consider helper script |
| Cluster MCP tight coupling | **Medium** | Port requires refactoring, not just copying | Scope as port + decouple, estimate accordingly |
| Bootstrap `pixi exec` untested | **Medium** | Version pinning, PyPI vs conda-forge, first-run perf | End-to-end test on clean machine, pin copier version |

---

## 9. The Four Questions

1. **Does this fully solve what the user asked for?** — YES. Git URL dep, MCP seam, cluster port, bootstrap simplification, developer mode — all present, all motivated.

2. **Is this complete?** — NOT YET. The MCP tools contract needs precision. The git URL lock behavior needs verification. The cluster port scope needs honest estimation.

3. **Is complexity obscuring correctness?** — NO. The vision is simple. The risks are in under-specification, not over-engineering.

4. **Is simplicity masking incompleteness?** — PARTIALLY. "One line to switch," "~20 lines of discovery," and "2-command bootstrap" are all simpler than the real implementation. The vision is right, but the effort estimates need honest recalibration.

---

## Bottom Line

The vision is correct. All 5 additions follow the established pattern (directory conventions, no frameworks, Copier assembly). The risks are all in the **implementation details** that the vision hand-waves:

1. **Define the MCP tools contract precisely** — this is the only new architectural concept in v2
2. **Verify git URL + pixi behaviors empirically** — lock pinning, offline, pixi-pack
3. **Scope the cluster port honestly** — it's a refactor, not a copy

Fix these three, and v2 is ready to spec and build.
