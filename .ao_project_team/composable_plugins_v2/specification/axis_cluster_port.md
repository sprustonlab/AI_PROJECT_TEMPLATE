# Axis Deep-Dive: Cluster MCP Port

Scoping the refactor of `claudechic/cluster.py` into a standalone `mcp_tools/cluster.py`.

---

## 1. Import Analysis

### Standard Library (keep as-is)
```python
import asyncio
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable
```
No issues. All are stdlib. No changes needed.

### Third-Party Imports

| Import | Package | conda-forge? | Notes |
|--------|---------|-------------|-------|
| `from claude_agent_sdk import tool` | `claude-agent-sdk` | Unknown (pip) | **Required** by the MCP tool protocol. The `@tool` decorator defines tool name, description, and arg schema. This is the MCP registration mechanism. |

**Verdict:** `claude_agent_sdk` is a hard dependency for any MCP tool. It's not a claudechic dependency — it's an MCP protocol dependency. The ported file will still need it. It should be available in the project's pixi env (it already is, since claudechic depends on it).

### Claudechic Internal Imports (MUST be decoupled)

#### 1. `from claudechic.config import CONFIG`

**What it uses:**
- `CONFIG.get("cluster", {})` — reads the `cluster:` section from `~/.claude/.claudechic.yaml`
- Accessed via `_cluster_config()` helper, which returns a dict

**What config values are read:**
| Key | Env Var Override | Default | Used By |
|-----|-----------------|---------|---------|
| `cluster.ssh_target` | `LSF_SSH_TARGET` | `submit.int.janelia.org` | `_get_ssh_target()` |
| `cluster.lsf_profile` | `LSF_PROFILE` | `/misc/lsf/conf/profile.lsf` | `_get_lsf_profile()` |
| `cluster.conda_envs_dirs` | `CONDA_ENVS_DIRS` | `""` | `_get_conda_envs_dirs()` |
| `cluster.watch_poll_interval` | — | `30` | `_get_watch_poll_interval()` |

**Decoupling strategy:** Replace `CONFIG` import with a standalone YAML reader. The ported file reads `~/.claude/.claudechic.yaml` directly using `yaml.safe_load()`. This is ~5 lines of code and removes the claudechic dependency entirely. The env var overrides already work independently.

```python
# Replacement: inline config reader
def _load_config() -> dict:
    """Read cluster config from ~/.claude/.claudechic.yaml."""
    config_path = Path.home() / ".claude" / ".claudechic.yaml"
    if config_path.exists():
        import yaml
        with open(config_path) as f:
            return (yaml.safe_load(f) or {}).get("cluster", {})
    return {}
```

**Note:** This adds `pyyaml` as a dependency. It's already in conda-forge and already required by any project using claudechic. If we want zero YAML dependency, config could be passed purely via env vars or kwargs — but YAML is the cleaner path.

#### 2. `from claudechic.tasks import create_safe_task`

**What it uses:**
- `create_safe_task(coro, name=...)` — creates an asyncio task with exception logging

**Where it's called:**
- `_make_cluster_watch()` → calls `create_safe_task(_run_watch(...), name=f"watch-job-{job_id}")` to start the background polling task

**What `create_safe_task` actually does** (full source, 15 lines):
```python
def create_safe_task(coro, name=None):
    task_name = name or "unnamed"
    async def wrapper():
        try:
            return await coro
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception(f"Task '{task_name}' failed")
            return None
    return asyncio.create_task(wrapper(), name=name)
```

**Decoupling strategy:** Inline this function directly into the ported `cluster.py`. It's 15 lines, uses only stdlib, and has no claudechic-specific logic. This is the cleanest option — no external dependency, no kwargs complexity.

---

## 2. Tool Inventory

### Tool 1: `cluster_jobs`
- **Signature:** `async def cluster_jobs(args: dict) -> dict` (no required args)
- **What it does:** Lists all running/pending LSF jobs for the current user via `bjobs -w`
- **External deps:** `bjobs` (via SSH or local), bash shell
- **Complexity:** Low — parse tabular output

### Tool 2: `cluster_status`
- **Signature:** `async def cluster_status(args: dict) -> dict` — requires `job_id: str`
- **What it does:** Gets detailed status for one job via `bjobs -l`, parses verbose output (wrapped lines, resource usage, paths)
- **External deps:** `bjobs -l` (via SSH or local), bash shell
- **Complexity:** Medium — complex regex parsing of LSF's wrapped output format

### Tool 3: `cluster_submit`
- **Signature:** `async def cluster_submit(args: dict) -> dict` — requires `queue`, `cpus`, `walltime`, `command`; optional `job_name`, `gpus`, `stdout_path`, `stderr_path`
- **What it does:** Builds and runs `bsub` command with smart defaults (PYTHONUNBUFFERED injection, conda run --no-capture-output, auto-cd to cwd, auto-mkdir for log dirs, CONDA_ENVS_DIRS injection)
- **External deps:** `bsub` (via SSH or local), bash shell, NFS-shared filesystem
- **Complexity:** High — many command transformations, environment variable injection

### Tool 4: `cluster_kill`
- **Signature:** `async def cluster_kill(args: dict) -> dict` — requires `job_id: str`
- **What it does:** Kills a job via `bkill`
- **External deps:** `bkill` (via SSH or local)
- **Complexity:** Low

### Tool 5: `cluster_logs`
- **Signature:** `async def cluster_logs(args: dict) -> dict` — requires `job_id: str`; optional `tail: int`
- **What it does:** Extracts log file paths from `bjobs -l`, reads files locally via NFS, returns last N lines
- **External deps:** `bjobs -l` (via SSH or local), NFS-shared filesystem for log access
- **Complexity:** Medium — path resolution, `$HOME` expansion, CWD-relative paths

### Tool 6: `cluster_watch` (factory: `_make_cluster_watch`)
- **Signature:** Factory takes `caller_name`, `send_notification`, `find_agent`. Produced tool requires `job_id: str`; optional `condition: str`
- **What it does:** Starts background polling task that checks job status every N seconds, sends notification to calling agent when job reaches terminal state (DONE/EXIT)
- **External deps:** `bjobs -l` (via SSH or local), asyncio event loop
- **Complexity:** High — async background task, agent notification wiring, resource usage reporting
- **Special:** This is the only tool that needs kwargs wiring (`send_notification`, `find_agent`). The other 5 are fully self-contained.

---

## 3. `get_tools(**kwargs)` Adaptation

The ported file needs to expose a single entry point:

```python
def get_tools(**kwargs) -> list:
    """Return cluster MCP tools for registration.

    kwargs (all optional):
        caller_name: str          — identity of the calling agent
        send_notification: fn     — callback to send notifications to agents
        find_agent: fn            — callback to look up agents by name
    """
    tools = [
        cluster_jobs,
        cluster_status,
        cluster_submit,
        cluster_kill,
        cluster_logs,
    ]

    # cluster_watch needs notification wiring — only include if wiring provided
    caller_name = kwargs.get("caller_name")
    send_notification = kwargs.get("send_notification")
    find_agent = kwargs.get("find_agent")

    tools.append(
        _make_cluster_watch(
            caller_name=caller_name,
            send_notification=send_notification,
            find_agent=find_agent,
        )
    )

    return tools
```

**Key design decisions:**
1. `cluster_watch` is **always included** but returns an error at runtime if notification wiring is absent (current behavior — lines 750-753). This is correct: the tool exists, but gracefully reports "Watch not available" if `send_notification` or `find_agent` are None.
2. The 5 non-watch tools need **zero kwargs**. They're standalone.
3. The factory pattern (`_make_cluster_watch`) is already exactly what the `get_tools()` pattern needs — no refactoring required, just wrapping.

---

## 4. Configuration

### What cluster.py needs

| Setting | Type | Default | Source Priority |
|---------|------|---------|----------------|
| `ssh_target` | str | `submit.int.janelia.org` | env `LSF_SSH_TARGET` > yaml > default |
| `lsf_profile` | str | `/misc/lsf/conf/profile.lsf` | env `LSF_PROFILE` > yaml > default |
| `conda_envs_dirs` | str | `""` | env `CONDA_ENVS_DIRS` > yaml > default |
| `watch_poll_interval` | int | `30` | yaml > default |

### Proposed `.claudechic.yaml` schema

```yaml
# ~/.claude/.claudechic.yaml
cluster:
  ssh_target: submit.int.janelia.org    # SSH login node for LSF commands
  lsf_profile: /misc/lsf/conf/profile.lsf  # LSF profile to source on SSH
  conda_envs_dirs: ""                   # CONDA_ENVS_DIRS for conda run jobs
  watch_poll_interval: 30               # Seconds between poll attempts for cluster_watch
```

**This schema is unchanged from current behavior.** The config section already exists in the current codebase. The only change is HOW the ported file reads it — direct YAML read instead of `from claudechic.config import CONFIG`.

### How the tool reads config

**Recommended approach: direct file read (not kwargs).**

Rationale:
- Config is a file on disk. Reading it directly is simpler than threading it through kwargs.
- Env var overrides already work without any framework.
- The config path (`~/.claude/.claudechic.yaml`) is a project convention, not a claudechic internal.
- If we passed config via kwargs, the discovery code in `mcp.py` would need to know about cluster-specific config keys — that's a seam violation.

The tool reads its own config. The discovery mechanism just calls `get_tools(**kwargs)` and passes through the standard wiring kwargs.

---

## 5. Copier Integration

### Copier question

```yaml
use_cluster:
  type: bool
  default: false
  help: "Enable LSF cluster job management tools? (Requires SSH access to an LSF login node)"
```

### File mapping

| File | When `use_cluster=true` | When `use_cluster=false` |
|------|------------------------|-------------------------|
| `mcp_tools/cluster.py` | Included | Not generated |

**File presence = enabled.** No manifest, no config toggle. The discovery code in claudechic's `mcp.py` simply walks `mcp_tools/` — if `cluster.py` is there, its tools are registered. If not, they're not. This is the filesystem convention law in action.

### Additional files needed

| File | Purpose | Copier behavior |
|------|---------|----------------|
| `mcp_tools/cluster.py` | The tool itself | Conditional on `use_cluster` |
| `mcp_tools/__init__.py` | **NOT needed** — discovery uses `importlib` or direct file loading, not package imports | N/A |

**No config template needed.** The `.claudechic.yaml` `cluster:` section is optional — all values have sensible defaults. Users who need to customize SSH target can add the section manually. A comment in `cluster.py`'s docstring documents the available settings.

**No documentation file needed.** The tool docstrings (visible to Claude via MCP) ARE the documentation. Each `@tool` decorator includes a description string. The module docstring documents config.

---

## 6. Seam Cleanliness Verification

### After the port, does cluster.py import ANYTHING from claudechic?

**Goal: NO. Achieved: YES.**

| Current import | Replacement | Claudechic dependency? |
|---------------|-------------|----------------------|
| `from claudechic.config import CONFIG` | Inline `_load_config()` reading `~/.claude/.claudechic.yaml` | **NO** |
| `from claudechic.tasks import create_safe_task` | Inline `_create_safe_task()` (15 lines, stdlib only) | **NO** |
| `from claude_agent_sdk import tool` | Keep as-is (this is MCP protocol, not claudechic) | **NO** |

**Post-port import list:**
```python
# Standard library
import asyncio, logging, os, re, shutil, subprocess
from pathlib import Path
from typing import Any, Callable

# Third-party (MCP protocol)
from claude_agent_sdk import tool

# Config reading (optional — only if .claudechic.yaml exists)
import yaml  # pyyaml, conda-forge
```

**Zero claudechic imports.** Clean seam.

### Can cluster.py be tested standalone with mock SSH?

**YES.** The SSH execution is isolated in `_run_lsf()`. Testing approaches:

1. **Mock `_run_lsf()`** — replace with canned stdout/stderr/rc tuples. Tests all parsing logic without SSH.
2. **Mock `subprocess.run()`** — lower-level mock, tests SSH command construction.
3. **Mock `shutil.which("bsub")`** — control local-vs-SSH path selection.

The async tools can be tested with `asyncio.run()` or pytest-asyncio. No claudechic runtime needed.

### Can cluster.py be copied to a non-claudechic project and still work?

**YES, with one caveat:**

- **Works if:** The project has `claude_agent_sdk` installed (for `@tool` decorator) and `pyyaml` (for config reading). Both are standard packages.
- **Config:** The tool looks for `~/.claude/.claudechic.yaml` which is a user-level config, not project-specific. It works fine even if the file doesn't exist (all defaults apply). Env vars (`LSF_SSH_TARGET`, etc.) work regardless.
- **Discovery:** The tool exposes `get_tools(**kwargs)`. Any MCP host that calls this function gets the tools. The host doesn't need to be claudechic.

**The only conceptual coupling is the config file path** (`~/.claude/.claudechic.yaml`). This is a convention shared between claudechic and the template, not an import dependency. If a non-claudechic MCP host wants cluster tools, the user just sets env vars instead of YAML.

---

## 7. Refactoring Diff Summary

### Changes to `cluster.py` (from claudechic/cluster.py to mcp_tools/cluster.py)

| Section | Change | Lines affected |
|---------|--------|---------------|
| Module docstring | Update to reflect standalone nature | ~5 lines |
| Imports | Remove `claudechic.config`, `claudechic.tasks`; add `yaml` | 2 lines removed, 1 added |
| `_cluster_config()` | Replace `CONFIG.get("cluster", {})` with inline YAML reader | ~8 lines new |
| `create_safe_task` | Inline as `_create_safe_task()` | ~15 lines new |
| `_make_cluster_watch` | Use `_create_safe_task` instead of imported `create_safe_task` | 1 line changed |
| `get_tools()` | New function at bottom of file | ~20 lines new |
| Everything else | **UNCHANGED** — all tool functions, parsers, SSH layer, response helpers | ~700 lines untouched |

**Estimated diff: ~50 lines changed/added out of ~780 total.** The port is minimal because the module was already well-isolated internally.

---

## 8. Dependency Summary for Ported File

| Dependency | Type | conda-forge? | Why needed |
|-----------|------|-------------|------------|
| `claude_agent_sdk` | pip | Via claudechic/pip | `@tool` decorator for MCP registration |
| `pyyaml` | pip/conda | Yes | Read `.claudechic.yaml` config |
| SSH client | system | Yes (openssh) | Remote LSF command execution |
| LSF CLI (`bsub`, `bjobs`, `bkill`) | system (remote) | N/A | Available on cluster login nodes |

---

## 9. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| `claude_agent_sdk` API changes | Low | SDK is controlled by Anthropic, `@tool` is a stable interface |
| Config file path convention drift | Low | Env vars provide independent override path |
| `_create_safe_task` diverges from claudechic version | Very low | The function is trivial (15 lines) and unlikely to change |
| `pyyaml` not available | Very low | It's in conda-forge and already a transitive dependency |

---

## 10. Conclusion

The cluster.py port is **clean and minimal**. The module was already architecturally isolated — only 2 claudechic imports, both trivially replaceable. The port requires:

1. **Inline** `_create_safe_task()` (15 lines, stdlib-only)
2. **Inline** `_load_config()` (8 lines, reads YAML directly)
3. **Add** `get_tools(**kwargs)` entry point (~20 lines)
4. **Remove** 2 claudechic import lines

Total effort: ~50 lines of changes. Zero risk of behavioral regression. The resulting file is fully standalone, testable in isolation, and portable to any project with `claude_agent_sdk` available.
