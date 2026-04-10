# Skeptic Cleanup Review — SPECIFICATION.md Problems List

> **Reviewer:** Skeptic
> **Date:** 2026-03-30
> **Lens:** "Does this read like an operational spec an implementer agent can follow, or a research document?"
> **Verdict:** The spec has **significant scope drift and structural problems**. The core decisions are buried under options, research notes, and sections that weren't in the userprompt.

---

## Category 1: OPTIONS Listed Instead of DECISIONS

### P1. Version pinning options (§1, lines 54-63)

The spec shows three pinning options (branch tracking, tag, exact commit) without deciding which one the template uses. An implementer sees three choices and no decision.

**The decision should be:** "The template tracks `branch = "main"`. Users CAN pin to tag/rev by editing pixi.toml, but the default Copier output is branch tracking."

Remove the options block. State the decision. Add one sentence: "Users can pin to a tag or rev by editing the git specifier in pixi.toml."

### P2. Copier help text says "one line" (§2, line 81)

```yaml
help: |
    ...You can switch between modes later by changing one line in pixi.toml.
```

The spec itself documents switching as 2-3 steps (lines 100-107). The Copier help text contradicts the spec. The help text IS the spec — it's what ships to users.

**Fix:** Change help text to "You can switch between modes later (see project README for steps)."

---

## Category 2: Scope Creep — NOT in the Userprompt

### P3. SLURM backend (§5) — NOT requested, doubles the port scope

The userprompt says:
> Port `cluster.py` from `/groups/spruston/home/moharb/DECODE-PRISM/Repos/claudechic/claudechic/cluster.py` into `mcp_tools/cluster.py`. Provides: cluster_jobs, cluster_status, cluster_submit, cluster_kill, cluster_logs, cluster_watch.

This is an LSF port. The word "SLURM" does not appear in the userprompt. The spec adds:
- A `ClusterBackend` protocol (~30 lines)
- A `SLURMBackend` (~150 lines, NEW code)
- A `cluster_scheduler` Copier question
- An LSF→SLURM flag mapping table
- SLURM parsing code
- Docker SLURM testing strategy

This **doubles** the cluster work from "port ~50 lines" to "refactor into multi-scheduler architecture ~650 lines." The overview table still says "~50 lines changed" but the Files Changed table says "~650 lines." Those can't both be true.

**This is the single biggest problem in the spec.** The userprompt asked for an LSF port. The spec delivers a multi-scheduler framework. This is exactly the kind of speculative generality I'm supposed to catch.

**Recommendation:** Cut SLURM entirely. Port LSF only. The ClusterBackend protocol is unnecessary when there's one backend. If/when a SLURM user appears, the refactor from a single-backend file to a protocol-based file is straightforward — but do it when there's a user, not now.

### P4. GitHub Pages landing page (§4) — NOT requested

The userprompt says:
> Replace `pip install copier` with pixi-only bootstrap: `pixi exec --spec copier copier copy ...`

The spec delivers:
- `docs/install.sh` (~30 lines)
- `docs/install.ps1` (~40 lines)
- `docs/index.html` (~130 lines) with OS detection, clipboard API, tabs
- GitHub Pages hosting setup
- `_exclude` for `docs/` directory

The userprompt asked for "two commands, one dependency." The spec delivers a landing page with install scripts, a static website, and GitHub Pages configuration. That's ~200 lines of new deliverables not in the userprompt.

**Recommendation:** The bootstrap section should be: (a) update README getting-started to show `pixi exec --spec copier` command, (b) pin copier version in the command. That's it. The landing page is a nice-to-have for a future iteration.

### P5. Claudechic fork sync section (lines 804-855) — operational procedure, not spec

The "Pre-Implementation: Claudechic Fork Sync" section is 50 lines documenting a git merge workflow with specific commit SHAs, conflict areas, and merge steps. This is:
- A one-time operational task, not a specification
- Already stale by the time someone reads it (upstream will have new commits)
- Not part of v2's design — it's a prerequisite chore

**Recommendation:** Move to a separate `fork_sync_plan.md` or a GitHub issue. The spec should say: "Prerequisite: boazmohar fork must be synced with upstream before implementation begins. See [link]."

### P6. Template Development Workflow section (lines 900-949) — process documentation, not spec

The branching strategy (develop/main/feature), contribution workflow, and Copier `_exclude` rationale are template-level process decisions. They apply to ALL future template work, not specifically to v2.

**Recommendation:** Move to a top-level `CONTRIBUTING.md` or `DEVELOPMENT.md`. The spec should not contain general process documentation.

---

## Category 3: Overview Table vs Reality Mismatch

### P7. Overview table says "~50 lines changed" for cluster, spec body says ~650 lines

Overview table (line 20):
> `mcp_tools/cluster.py` port (~50 lines changed) + Copier question

Files Changed table (line 739):
> `mcp_tools/cluster.py` | New file (~650 lines, multi-scheduler: LSF + SLURM, conditional on `use_cluster`) | 5

Section 5 heading says "~650 lines." These are contradictory. Even without SLURM, the LSF port alone would be ~400+ lines (the original is 775 lines). "~50 lines changed" was from the earlier version that assumed a simple decouple — the spec grew but the overview wasn't updated.

### P8. Overview table says "Documentation change" for bootstrap, spec body has ~200 lines of new files

Overview table (line 19):
> Documentation change + `copier.yml` update

Spec body (§4): Three new files (install.sh, install.ps1, index.html), GitHub Pages setup, OS-detection JavaScript. This is not a "documentation change."

---

## Category 4: Stale / Outdated Content

### P9. `SdkMcpTool` type doesn't exist

Used in §3 (line 124, 211, 302) as the return type: `list[SdkMcpTool]`. This type doesn't exist in `claude_agent_sdk`. The actual return type is `list` of `@tool`-decorated async functions.

**Fix:** Use `list` (untyped) or describe as "list of `@tool`-decorated functions from `claude_agent_sdk`."

### P10. "Section 5 becomes no-op" reference (line 50)

> No `git submodule update --init` in activate script (Section 5 becomes no-op when no `.gitmodules`)

This refers to the activate script's internal section numbering, but the spec doesn't show the activate script. An implementer won't know what "Section 5" means.

**Fix:** Say "the `git submodule update --init` block in `activate` becomes a no-op" without the section reference.

---

## Category 5: Ambiguity / Confusion for Implementer

### P11. Two different `copier.yml` entries in Files Changed table

Line 738:
> `copier.yml` | Add `claudechic_mode`, `use_cluster`, `cluster_scheduler`, `cluster_ssh_target` questions | 2, 5

Line 745:
> `copier.yml` | Add `_exclude: [docs/, .ao_project_team/]` to exclude template-repo meta-tooling from generated projects | 4

Same file listed twice with different changes. Should be one row with combined changes.

### P12. Cluster `get_tools()` creates backend at import time

```python
def get_tools(**kwargs) -> list:
    config = _load_config()
    backend = _get_backend(config)
    tools = [_make_cluster_jobs(backend), ...]
    return tools
```

This reads config and selects backend every time `get_tools()` is called. But `get_tools()` is called once at startup by `discover_mcp_tools()`. What if config changes after startup? Is that expected? If not, state it: "Config is read once at claudechic startup. Changes require restart."

### P13. `activate` / `activate.ps1` change appears without spec section

Files Changed table (line 741):
> `activate` / `activate.ps1` | Add `mcp_tools/` status display in Section 6 | 3

But §3 (MCP Tools Seam) never mentions the activate script. There's no spec for what the status display looks like, what it counts, or how it discovers tools. An implementer sees "add status display" with no details.

**Fix:** Either add a subsection to §3 showing the activate script change, or remove this from the Files Changed table if it's not a v2 deliverable.

---

## Summary: What to Do

### Must fix (blocking for implementer clarity)
| # | Problem | Action |
|---|---------|--------|
| P3 | SLURM not in userprompt, doubles scope | **Cut SLURM. LSF-only port.** Remove ClusterBackend protocol, SLURMBackend, scheduler Copier question. |
| P4 | Landing page not in userprompt | **Cut landing page.** Bootstrap = update README with `pixi exec` command. |
| P7 | Overview "~50 lines" vs body "~650 lines" | **Fix overview table** after cutting SLURM. |
| P8 | Overview "documentation change" vs 200 lines | **Fix overview table** after cutting landing page. |
| P13 | Activate change unspecified | **Add details or remove from Files Changed.** |

### Should fix (clarity improvements)
| # | Problem | Action |
|---|---------|--------|
| P1 | Version pinning options, no decision | State the decision, mention alternatives in one line. |
| P2 | Copier help text says "one line" | Fix help text. |
| P5 | Fork sync in spec | Move to separate file. |
| P6 | Dev workflow in spec | Move to separate file. |
| P9 | `SdkMcpTool` phantom type | Replace with real type or `list`. |
| P11 | `copier.yml` listed twice | Merge into one row. |

### Minor (implementer can figure out)
| # | Problem | Action |
|---|---------|--------|
| P10 | "Section 5" reference | Remove internal reference. |
| P12 | Config read timing | Add one sentence. |
