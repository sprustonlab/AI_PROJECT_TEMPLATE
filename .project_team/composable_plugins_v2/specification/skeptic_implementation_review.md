# Skeptic Implementation Review — Phase 4

> **Reviewer:** Skeptic
> **Date:** 2026-03-30
> **Scope:** All implemented files from Impl-Claudechic and Impl-Template
> **Verdict:** **2 bugs, 3 risks, 2 minor issues.** One bug is critical (duplicate tool registration). Code quality is high overall.

---

## BUG 1 (CRITICAL): Duplicate Cluster Tool Registration in `mcp.py`

**File:** `submodules/claudechic/claudechic/mcp.py`, lines 640-661

```python
# LSF cluster tools (always registered; LSF availability checked at runtime)
from claudechic.cluster import (
    cluster_jobs, cluster_kill, cluster_logs,
    cluster_status, cluster_submit, _make_cluster_watch,
)
tools.extend([cluster_jobs, cluster_status, ...])
```

AND then at lines 663-671:

```python
# Discover mcp_tools/ plugins
mcp_tools_dir = Path.cwd() / "mcp_tools"
external_tools = discover_mcp_tools(mcp_tools_dir, ...)
tools.extend(external_tools)
```

**The problem:** If a user has `mcp_tools/lsf.py` (from the template) AND claudechic has its built-in `cluster.py`, the MCP server will register **two copies** of every cluster tool — `cluster_jobs` from `claudechic.cluster` AND `cluster_jobs` from `mcp_tools/lsf.py`. Both have the same tool name. Behavior is undefined — Claude may see duplicate tools, or one may shadow the other, or both may be called.

**This is the whole point of v2** — move cluster tools from claudechic into the MCP seam. The hardcoded `from claudechic.cluster import ...` block (lines 640-661) must be removed. The discovery mechanism replaces it.

**Fix:** Remove lines 640-661 entirely. Cluster tools are now discovered via `mcp_tools/lsf.py` or `mcp_tools/slurm.py` through the discovery mechanism.

---

## BUG 2 (MEDIUM): `_helpers.py` Duplicates `_cluster.py` Response Helpers

**Files:** `template/mcp_tools/_helpers.py` and `template/mcp_tools/_cluster.py`

`_helpers.py` defines `_text_response` and `_error_response`.
`_cluster.py` defines `_text_response`, `_json_response`, and `_error_response`.

Neither `lsf.py` nor `slurm.py` imports from `_helpers.py` — they import from `_cluster.py`. So `_helpers.py` is dead code that ships to users but is never used.

**Fix:** Either (a) remove `_helpers.py` since `_cluster.py` already has the helpers, or (b) have `_cluster.py` import from `_helpers.py` instead of defining its own. Option (a) is simpler — the helpers exist for future non-cluster MCP tools, but shipping dead code is worse than adding it when needed.

---

## RISK 1 (HIGH): `from mcp_tools._cluster import ...` May Fail at Discovery Time

**Files:** `template/mcp_tools/lsf.py` line 20, `slurm.py` line 19

```python
from mcp_tools._cluster import (
    _create_safe_task, _error_response, _json_response,
    _load_config, _read_logs, _run_ssh, _run_watch, _text_response,
)
```

The discovery code in `mcp.py` uses `importlib.util.spec_from_file_location(module_name, py_file)` to load each tool file. The tool file then tries `from mcp_tools._cluster import ...`.

**The question:** When `lsf.py` is loaded via `spec_from_file_location`, is `mcp_tools._cluster` on the import path? It depends on:
1. Whether the parent directory of `mcp_tools/` is in `sys.path`
2. Whether `mcp_tools/` has an `__init__.py` (it doesn't)

The discovery code does `sys.modules[module_name] = module` for discovered files, but `_cluster.py` is **never loaded by discovery** (underscore prefix = skipped). So `mcp_tools._cluster` is NOT in `sys.modules` when `lsf.py` tries to import it.

**Likely failure:** `lsf.py` loads → tries `from mcp_tools._cluster import ...` → `ModuleNotFoundError` → discovery catches it as `ImportError` → silently skips → **all cluster tools silently unavailable** with only a WARNING log.

**The Iron Rule (discovery never crashes) is upheld** — the exception is caught. But the user's cluster tools silently disappear, which is a bad failure mode.

**Fix options:**
1. **Pre-load `_cluster.py`** in discovery: before the main loop, find all `_`-prefixed `.py` files and load them into `sys.modules` so they're importable. (~5 lines added to discovery.)
2. **Use relative imports** in `lsf.py`: `from ._cluster import ...` — but this requires `mcp_tools/` to be a package with `__init__.py`.
3. **Add `mcp_tools/` parent to `sys.path`** in discovery: `sys.path.insert(0, str(mcp_tools_dir.parent))` before loading. Simple but pollutes sys.path.

Option 1 is cleanest — it follows the spec's intent (underscore files are "importable by tools") and doesn't change the public contract.

---

## RISK 2 (MEDIUM): `_run_ssh` Shell Injection via `cmd` Parameter

**File:** `template/mcp_tools/_cluster.py` lines 75-109

```python
def _run_ssh(cmd: str, ssh_target: str, ...) -> tuple[str, str, int]:
    escaped = cmd.replace('"', '\\"')
    full_cmd = f'ssh ... {ssh_target} "{prefix}{escaped}"'
    result = subprocess.run(full_cmd, shell=True, ...)
```

The `cmd` parameter flows from MCP tool inputs. For example, `cluster_submit` takes a user-provided `command` string and passes it through `_submit_job` → `_run_lsf` → `_run_ssh`. The escaping is only `replace('"', '\\"')` — this doesn't handle `$()`, backticks, `; rm -rf /`, or other shell metacharacters.

**This is an inherited risk from the original `claudechic/cluster.py`** — not new code. But now it's in the MCP seam where it's more visible.

**Mitigating factor:** The tool is invoked by Claude (an AI agent), not by untrusted users. Shell injection requires Claude to craft a malicious command, which is unlikely but not impossible in adversarial prompt scenarios.

**Recommendation:** Not a v2 blocker, but add a comment: `# SECURITY: cmd is passed to shell. In production, consider shlex.quote() for non-SSH paths.` Track as a known risk.

---

## RISK 3 (LOW): Config YAML Files Are Copier Templates But Not `.jinja` Suffixed

**Files:** `template/mcp_tools/lsf.yaml`, `template/mcp_tools/slurm.yaml`

```yaml
ssh_target: {{ cluster_ssh_target }}
```

These contain Jinja2 template variables (`{{ cluster_ssh_target }}`). For Copier to render them, they need to be treated as Jinja2 templates. Copier's default behavior is to render ALL files in the template directory through Jinja2, so this likely works. However:

1. If someone adds `_render_exclude` to `copier.yml` or changes Copier's rendering behavior, these files would ship with literal `{{ cluster_ssh_target }}` in them.
2. The `.py` files in `mcp_tools/` also don't have `.jinja` suffix but they don't contain template variables, so they're fine.

**Current status:** Probably works with default Copier settings. Just flagging the implicit dependency on Copier's "render everything" behavior.

---

## MINOR 1: Activate Script Still References Git Submodules

**File:** `template/activate.jinja` lines 105-124

```bash
if grep -q "claudechic" "$BASEDIR/.gitmodules"; then
    if [[ ! -f "$BASEDIR/submodules/claudechic/pyproject.toml" ]]; then
        _needs_init=true
    fi
```

In standard mode, there IS no `.gitmodules` file (claudechic is a git URL dep, not a submodule). The `grep -q` will fail silently and the block will be skipped — so this is **not a bug**. But it's dead code in standard mode. In developer mode, claudechic is a plain clone (not a submodule), so `.gitmodules` also won't mention it.

**This code path is now unreachable for v2 projects.** It could be cleaned up, but it's not harmful — the conditional guards prevent it from executing.

**Similarly:** `template/commands/claudechic` (line 18) still has `git submodule update --init submodules/claudechic`. This fallback also won't trigger in v2 because the submodule doesn't exist. Not harmful but stale.

---

## MINOR 2: `_exclude` Pattern for Empty `mcp_tools/` Directory

**File:** `copier.yml` lines 120-124

When `use_cluster` is false, all `.py` files in `mcp_tools/` are excluded. But `_helpers.py` is always excluded when `use_cluster` is false (line 120). What if `use_cluster` is false but the user wants to write custom MCP tools? They get an empty `mcp_tools/` directory with no `_helpers.py`.

Actually — looking more carefully, `_helpers.py` exclusion is tied to `use_cluster`, not to `mcp_tools/` in general:
```yaml
- "{% if not use_cluster %}mcp_tools/_cluster.py{% endif %}"
```

But `_helpers.py` is NOT in the exclude list at all — it's always included. That's correct. Only `_cluster.py` and the backend files are conditional. Good.

Wait — is there any exclusion for `_helpers.py`? Let me re-check... No, `_helpers.py` is not in any `_exclude` entry. So it's always present. That's fine — it's a small file useful for any future custom MCP tools.

**Revised assessment:** Not an issue. Withdraw this point.

---

## Fork Sync Assessment

**Commit log confirms:**
- `ffe01be` — "Merge upstream/main: sync 20 commits with 3 conflict resolutions" ✓
- `f5845a0` — "Add discover_mcp_tools() for plugin discovery from mcp_tools/" ✓

The merge is on top of the sync. Correct ordering. The 3 conflict areas (MessageMetadata, spawn_agent schema, agent_type env vars) should be verified by running claudechic's test suite, but structurally the git history looks right.

---

## Summary

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| BUG 1 | Duplicate cluster tools in mcp.py (hardcoded + discovered) | **CRITICAL** | Must fix — remove hardcoded import block |
| BUG 2 | `_helpers.py` is dead code | **Medium** | Fix — remove or use |
| RISK 1 | `from mcp_tools._cluster import` may fail (not in sys.modules) | **High** | Must fix — pre-load underscore helpers in discovery |
| RISK 2 | Shell injection in `_run_ssh` | **Medium** | Inherited risk — document, don't block |
| RISK 3 | YAML config files rely on implicit Jinja2 rendering | **Low** | Probably fine, just fragile |
| MINOR 1 | Stale submodule code in activate/commands | **Low** | Cleanup later — not harmful |
| MINOR 2 | (withdrawn) | — | — |

**Blockers before shipping:**
1. Remove hardcoded `from claudechic.cluster import ...` block from `mcp.py` (BUG 1)
2. Fix discovery to pre-load underscore-prefixed helpers so `from mcp_tools._cluster import` works (RISK 1)
3. Remove or integrate `_helpers.py` (BUG 2)
