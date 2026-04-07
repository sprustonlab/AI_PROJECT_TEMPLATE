# Composable Plugins v2 — Specification

> **Status:** Draft — pending user approval
> **Date:** 2026-03-30
> **Builds on:** v1 specification (`.ao_project_team/composable_plugins/specification/SPECIFICATION.md`)

---

## Overview

| # | Change | Scope |
|---|--------|-------|
| 0 | Claudechic fork sync (prerequisite) | Merge 20 upstream commits into boazmohar fork, resolve 3 conflicts |
| 1 | Claudechic as git URL dependency | `pixi.toml` (1 line) |
| 2 | Developer mode for claudechic | Copier question + conditional `pixi.toml` line |
| 3 | MCP Tools seam (#6) | `mcp_tools/` directory + ~30 lines in claudechic's `mcp.py` |
| 4 | Landing page + install scripts | `docs/install.sh`, `docs/install.ps1`, `docs/index.html` (~200 lines) |
| 5 | Cluster MCP — LSF + SLURM | `mcp_tools/lsf.py` + `mcp_tools/slurm.py` + `mcp_tools/_cluster.py` + 3 Copier questions |

---

## 0. Claudechic Fork Sync (Prerequisite)

The boazmohar fork (`boazmohar/claudechic`, main at `ae4adff`) is 20 commits behind upstream (`abast/claudechic`). Sync before any v2 implementation.

### Commits to merge

**Features (Priority 1):**

| # | Commit | Feature | Impact |
|---|--------|---------|--------|
| 1 | `15af6db` | `requires_answer` nudge system | spawn_agent gains `requires_answer: bool`. **Breaking:** spawn_agent schema changes from positional to JSON Schema. |
| 2 | `b43c109` | Soft-close agents + `/agent reopen` | Closed agents preserved, reopenable with full history. |
| 3 | `fd0e678` | Multi-agent topology persistence | Saves topology as JSON sidecar. `--resume` restores subagents. |
| 4 | `13f6a7b` | Improved close_agent factory | `_make_close_agent` binds caller_name, prevents self-close, fixes race conditions. |
| 5 | `2bb33aa` | SDK bump to >=0.1.40 | Needed for Opus 4.6 + rate_limit_event crash fix. |

**Bug fixes (Priority 2):**

| # | Commit | Fix |
|---|--------|-----|
| 6 | `a4307c7` | ExitPlanMode freeze fix |
| 7 | `73b2104` | Model switch context loss fix |
| 8 | `3a16e6c` | CLIJSONDecodeError recovery |
| 9 | `61f6e21` | Worktree `.claude/` symlink |
| 10 | `8f17ec3` | Model selector short aliases |

### Merge conflicts (3 areas)

| Area | Upstream | Boazmohar | Resolution |
|------|----------|-----------|------------|
| **MessageMetadata** | Removed it | Added it | Keep boazmohar's metadata, reconcile with upstream's session loading |
| **spawn_agent schema** | Added `requires_answer` | Added `model`/`type` | Merge both into the JSON Schema object |
| **agent_type env vars** | Removed | Added | Keep boazmohar's version |

### Merge workflow

1. `git checkout -b sync-upstream-main`
2. `git remote add upstream https://github.com/abast/claudechic`
3. `git fetch upstream && git merge upstream/main`
4. Resolve 3 conflict areas (see table above)
5. Test: MCP tools, agent spawning, guardrails env vars
6. Merge sync branch to boazmohar/main
7. Scope: `upstream/main` only (not feature branches)

---

## 1. Claudechic as Git URL Dependency

### pixi.toml entry

```toml
[pypi-dependencies]
claudechic = { git = "https://github.com/boazmohar/claudechic", branch = "main" }
```

Pixi also supports `tag` and `rev` specifiers for stricter pinning if needed later.

### Key behaviors

| Property | Behavior |
|----------|----------|
| **Reproducibility** | `pixi.lock` pins exact commit SHA |
| **Updates** | `pixi update claudechic` re-resolves to latest branch HEAD |
| **`pixi install`** | Respects lock file — does not pull new commits |
| **pixi-pack** | Not supported for git URL deps — use developer mode (local path) for pixi-pack/offline HPC |
| **Network** | Required for initial install and updates |

---

## 2. Developer Mode

### Copier question

```yaml
claudechic_mode:
  type: str
  choices:
    standard: "Standard — installs from git, updates via pixi update (recommended)"
    developer: "Developer — clones locally for hacking on claudechic itself"
  default: "standard"
  help: |
    Standard mode: claudechic installed from git URL. You get updates with `pixi update`.
    Developer mode: claudechic cloned into submodules/claudechic/ for local editing.
    You can switch between modes later (see project docs).
```

### pixi.toml conditional (Jinja2 in Copier template)

```toml
[pypi-dependencies]
{% if claudechic_mode == "standard" %}
claudechic = { git = "https://github.com/boazmohar/claudechic", branch = "main" }
{% else %}
claudechic = { path = "submodules/claudechic", editable = true }
{% endif %}
```

### Copier post-generation hook

In `copier.yml`:

```yaml
_tasks:
  - "{% if claudechic_mode == 'developer' %}git clone https://github.com/boazmohar/claudechic submodules/claudechic{% endif %}"
```

### .gitignore entry (always present)

```
# Developer mode claudechic clone (not tracked by parent project)
submodules/claudechic/
```

This line is always in `.gitignore` regardless of mode. In standard mode it's harmless; in developer mode it prevents the clone from being tracked.

### Developer mode details

- `submodules/claudechic/` is a plain git clone, not a git submodule
- `editable = true` means changes take effect immediately without reinstalling

### Switching workflow

**Standard → Developer:**
1. `git clone https://github.com/boazmohar/claudechic submodules/claudechic`
2. Edit `pixi.toml`: change git URL line to `claudechic = { path = "submodules/claudechic", editable = true }`
3. `pixi install`

**Developer → Standard:**
1. Edit `pixi.toml`: change path line to `claudechic = { git = "https://github.com/boazmohar/claudechic", branch = "main" }`
2. `pixi install`

---

## 3. MCP Tools Seam (#6)

### Directory layout

```
project-root/
  mcp_tools/
    lsf.py               # get_tools(**kwargs) -> list — LSF cluster tools
    slurm.py              # get_tools(**kwargs) -> list — SLURM cluster tools
    _cluster.py           # shared cluster infrastructure (skipped by discovery)
    _helpers.py           # shared response helpers (skipped by discovery)
    my_custom_tool.py     # user-defined tools follow same contract
```

### Discovery rules

| Item | Action |
|------|--------|
| `*.py` (no underscore prefix) | Import, call `get_tools()` |
| `_`-prefixed files | Skip (private helpers, importable by tools) |
| `__pycache__/`, `__init__.py` | Skip |
| Non-`.py` files | Skip |
| Subdirectories | Skip (flat namespace only) |

### Discovery code in claudechic's `mcp.py` (~30 lines)

```python
import importlib.util
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

def discover_mcp_tools(mcp_tools_dir: Path, **kwargs) -> list:
    """Walk mcp_tools/, import each eligible .py, call get_tools()."""
    tools = []
    if not mcp_tools_dir.is_dir():
        return tools

    for py_file in sorted(mcp_tools_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        module_name = f"mcp_tools.{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                log.warning("mcp_tools: could not load spec for %s", py_file.name)
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            get_tools_fn = getattr(module, "get_tools", None)
            if get_tools_fn is None:
                log.debug("mcp_tools: %s has no get_tools(), skipping", py_file.name)
                continue

            file_tools = get_tools_fn(**kwargs)
            tools.extend(file_tools)
            log.info("mcp_tools: loaded %d tool(s) from %s", len(file_tools), py_file.name)

        except Exception:
            log.warning("mcp_tools: failed to load %s, skipping", py_file.name, exc_info=True)
            continue

    return tools
```

### Integration point in `mcp.py`

```python
def create_chic_server(caller_name: str | None = None):
    tools = [
        # ... core agent tools (spawn, ask, tell, etc.) ...
    ]

    # Discover mcp_tools/ plugins
    mcp_tools_dir = Path.cwd() / "mcp_tools"
    external_tools = discover_mcp_tools(
        mcp_tools_dir,
        caller_name=caller_name,
        send_notification=_send_prompt_fire_and_forget,
        find_agent=_find_agent_by_name,
    )
    tools.extend(external_tools)

    return create_sdk_mcp_server(name="chic", version="1.0.0", tools=tools)
```

### The `get_tools()` contract

```python
def get_tools(**kwargs) -> list:
    """Return MCP tool functions for registration.

    All kwargs are optional. Tools MUST have sensible defaults when any kwarg is absent.
    get_tools() itself MUST NOT raise — individual tools MAY return errors at runtime.
    """
```

### kwargs protocol (closed set for v2)

| kwarg | Type | Purpose | Default if absent |
|-------|------|---------|-------------------|
| `caller_name` | `str \| None` | Identity of calling agent | `None` |
| `send_notification` | `Callable \| None` | `(agent, message, *, caller_name) -> None` | `None` — tools degrade gracefully |
| `find_agent` | `Callable \| None` | `(name) -> (agent, error_msg \| None)` | `None` — tools degrade gracefully |

### Tool function shape

```python
from claude_agent_sdk import tool

@tool("tool_name", "Description shown to Claude", {"param": str})
async def tool_name(args: dict[str, Any]) -> dict[str, Any]:
    try:
        result = do_work(args["param"])
        return {"content": [{"type": "text", "text": result}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": str(e)}], "isError": True}
```

### Factory pattern for wired tools

Tools needing kwargs use closures:

```python
def get_tools(**kwargs) -> list:
    send_notification = kwargs.get("send_notification")
    tools = [simple_tool_a, simple_tool_b]
    tools.append(_make_wired_tool(send_notification))
    return tools

def _make_wired_tool(send_notification):
    @tool("wired_tool", "Does something with notifications", {"param": str})
    async def wired_tool(args: dict) -> dict:
        if send_notification is None:
            return {"content": [{"type": "text", "text": "Notifications not available"}], "isError": True}
        # ... use send_notification ...
    return wired_tool
```

### Error handling

Discovery must never crash. Every exception is caught, logged, and skipped.

| Condition | Behavior | Log Level |
|-----------|----------|-----------|
| `mcp_tools/` doesn't exist | Return empty list | (silent) |
| File has `get_tools()` | Call it, extend tool list | INFO |
| File has no `get_tools()` | Skip | DEBUG |
| File raises ImportError/SyntaxError | Skip, continue | WARNING (with traceback) |
| `get_tools()` raises exception | Skip, continue | WARNING (with traceback) |

### Seam cleanliness rules

| Import | Allowed? |
|--------|----------|
| `claude_agent_sdk` | YES |
| Python stdlib | YES |
| PyPI packages (declared in `pixi.toml`) | YES |
| `mcp_tools._helpers`, `mcp_tools._cluster` | YES — underscore-prefixed private helpers |
| `claudechic.*` | **NO** |
| Other `mcp_tools/*.py` (non-underscore) | **NO** — tools must be independent |

### Shared response helpers — `mcp_tools/_helpers.py`

```python
def _text_response(text, *, is_error=False):
    result = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result

def _error_response(text):
    return _text_response(text, is_error=True)
```

### Activate script — MCP tools status display

Add to Section 6 of `activate` (bash):

```bash
# --- Show MCP tools ---
if [[ -d "$BASEDIR/mcp_tools" ]]; then
    mcp_count=0
    for f in "$BASEDIR/mcp_tools"/*.py; do
        [[ -f "$f" ]] && [[ "$(basename "$f")" != _* ]] && ((mcp_count++))
    done
    if [[ $mcp_count -gt 0 ]]; then
        echo ""
        echo "🔌 MCP tools: $mcp_count plugin(s) in mcp_tools/"
    fi
fi
```

Add equivalent to `activate.ps1`:

```powershell
# Show MCP tools
if (Test-Path "$BASEDIR\mcp_tools") {
    $mcpCount = (Get-ChildItem "$BASEDIR\mcp_tools\*.py" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike "_*" }).Count
    if ($mcpCount -gt 0) {
        Write-Host ""
        Write-Host "🔌 MCP tools: $mcpCount plugin(s) in mcp_tools/"
    }
}
```

---

## 4. Landing Page + Install Scripts

Landing page at `sprustonlab.github.io/AI_PROJECT_TEMPLATE/` with OS-detecting tabs and copy buttons.

### User experience

**Linux/macOS:**
```bash
curl -fsSL https://sprustonlab.github.io/AI_PROJECT_TEMPLATE/install.sh | bash -s my-project
```

**Windows:**
```powershell
iwr -useb https://sprustonlab.github.io/AI_PROJECT_TEMPLATE/install.ps1 | iex
```

Plus a "Download install.ps1" button. The script prompts for project name and install location interactively.

### `docs/install.sh` (~30 lines bash)

```bash
#!/bin/bash
set -euo pipefail

PROJECT_NAME="${1:?Usage: curl ... | bash -s <project-name> [install-dir]}"
INSTALL_DIR="${2:-.}"  # default: current directory
TEMPLATE_URL="https://github.com/sprustonlab/AI_PROJECT_TEMPLATE"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AI_PROJECT_TEMPLATE — project setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Install pixi if not present
if ! command -v pixi &> /dev/null; then
    echo "Installing pixi..."
    curl -fsSL https://pixi.sh/install.sh | bash
    export PATH="$HOME/.pixi/bin:$PATH"
fi

# 2. Run copier in ephemeral pixi env (pinned version)
echo "Creating project '$PROJECT_NAME'..."
pixi exec --spec "copier>=9,<10" -- copier copy "$TEMPLATE_URL" "$INSTALL_DIR/$PROJECT_NAME"

# 3. Install environments
echo "Installing environments..."
cd "$INSTALL_DIR/$PROJECT_NAME"
pixi install

echo ""
echo "✔ Project '$PROJECT_NAME' is ready!"
echo "  cd $PROJECT_NAME && source activate"
```

### `docs/install.ps1` (~40 lines PowerShell)

```powershell
$ErrorActionPreference = "Stop"

$ProjectName = Read-Host "Enter project name"
if (-not $ProjectName) { Write-Error "Project name required"; exit 1 }
$InstallDir = Read-Host "Install location (default: current directory)"
if (-not $InstallDir) { $InstallDir = "." }
$TemplateUrl = "https://github.com/sprustonlab/AI_PROJECT_TEMPLATE"

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "  AI_PROJECT_TEMPLATE — project setup"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Install pixi if not present
if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    Write-Host "Installing pixi..."
    iwr -useb https://pixi.sh/install.ps1 | iex
    $env:PATH = "$HOME\.pixi\bin;$env:PATH"
}

# 2. Run copier in ephemeral pixi env (pinned version)
Write-Host "Creating project '$ProjectName'..."
pixi exec --spec "copier>=9,<10" -- copier copy $TemplateUrl "$InstallDir\$ProjectName"

# 3. Install environments
Write-Host "Installing environments..."
Push-Location "$InstallDir\$ProjectName"
pixi install
Pop-Location

Write-Host ""
Write-Host "✔ Project '$ProjectName' is ready!"
Write-Host "  cd $ProjectName; . .\activate.ps1"
```

### `docs/index.html` (~130 lines)

Static HTML page with:
- OS-detecting tabs (Linux/macOS vs Windows) via `navigator.platform`
- Copy button on each code block (clipboard API)
- "Download install.ps1" button for Windows users
- Fallback commands for users who already have pixi or pipx
- WSL note: "Using WSL? Use the Linux/macOS command."
- Clean, minimal styling (inline CSS, no framework)
- Links to the GitHub repo, docs, and issues

### Hosting

GitHub Pages from `/docs` folder. Enable in repo Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, folder: `/docs`.

URL: `https://sprustonlab.github.io/AI_PROJECT_TEMPLATE/`

### Implementation notes

- Copier version pinned: `--spec "copier>=9,<10"`
- Git must be available on the system (Copier needs it)
- Install scripts run `pixi install` after copier for fully working state
- `docs/`, `submodules/`, `tests/`, `.ao_project_team/` are template-repo only, excluded from generated projects via `_exclude` in copier.yml

---

## 5. Cluster MCP — LSF + SLURM

### Architecture: Seam-native separate files

Three files in `mcp_tools/`:

| File | Lines | Role |
|------|-------|------|
| `_cluster.py` | ~200 | Shared infrastructure (underscore prefix = skipped by discovery, importable by backends) |
| `lsf.py` | ~300 | LSF backend + `get_tools(**kwargs)` — discovered by MCP seam |
| `slurm.py` | ~300 | SLURM backend + `get_tools(**kwargs)` — discovered by MCP seam |

Source for LSF code: boazmohar fork's `claudechic/cluster.py`. Decouple 2 claudechic imports, split into shared + LSF-specific. Write SLURM backend from scratch.

File presence = enabled. Copier includes the selected scheduler's file. No runtime backend selection, no internal protocol/ABC framework.

### `mcp_tools/_cluster.py` — shared infrastructure (~200 lines)

Contains functions imported by both `lsf.py` and `slurm.py`:

| Function | Description |
|----------|-------------|
| `_load_config(tool_file: Path) -> dict` | YAML reader for sibling config file (e.g., `lsf.yaml` next to `lsf.py`) |
| `_create_safe_task(coro, *, name) -> Task` | asyncio.create_task with error logging |
| `_run_ssh(cmd, ssh_target, profile) -> str` | SSH command execution |
| `_read_logs(job_id, log_dir) -> str` | Job log file reader |
| `_run_watch(...)` | Background polling loop for job completion |
| `_text_response(text) -> dict` | MCP response helper |
| `_error_response(text) -> dict` | MCP error response helper |

Config reader:

```python
def _load_config(tool_file: Path) -> dict:
    """Read config from a YAML sibling of the given tool file.

    Example: _load_config(Path("mcp_tools/lsf.py"))
             reads mcp_tools/lsf.yaml
    """
    try:
        import yaml
    except ImportError:
        return {}
    config_path = tool_file.with_suffix(".yaml")
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}
```

Task helper:

```python
def _create_safe_task(coro, *, name=None):
    """asyncio.create_task with exception logging."""
    task = asyncio.create_task(coro, name=name)
    def _on_done(t):
        if not t.cancelled() and t.exception():
            log.error("Task %s failed: %s", t.get_name(), t.exception())
    task.add_done_callback(_on_done)
    return task
```

### `mcp_tools/lsf.py` — LSF backend (~300 lines)

Imports from `_cluster`. Provides `get_tools(**kwargs)` for LSF.

| Operation | Command | Parsing |
|-----------|---------|---------|
| List jobs | `bjobs -w` | Tabular, fixed-width columns |
| Job status | `bjobs -l <id>` | Verbose wrapped-line format with continuation lines |
| Submit | `bsub` with `-q`, `-n`, `-W`, `-R "rusage[mem=N]"`, `-gpu "num=N"` | `Job <id> is submitted` |
| Kill | `bkill <id>` | Confirmation text |
| Terminal statuses | `DONE`, `EXIT` | |
| Profile | Sources `lsf_profile` before commands | |

```python
from mcp_tools._cluster import _load_config, _run_ssh, _read_logs, _create_safe_task, _run_watch

def get_tools(**kwargs) -> list:
    caller_name = kwargs.get("caller_name")
    send_notification = kwargs.get("send_notification")
    find_agent = kwargs.get("find_agent")
    config = _load_config(Path(__file__))

    return [
        cluster_jobs, cluster_status, cluster_submit, cluster_kill, cluster_logs,
        _make_cluster_watch(config, caller_name, send_notification, find_agent),
    ]
```

### `mcp_tools/slurm.py` — SLURM backend (~300 lines)

Same structure as `lsf.py`, same `get_tools(**kwargs)` contract. Imports from `_cluster`.

| Operation | Command | Parsing |
|-----------|---------|---------|
| List jobs | `squeue -u $USER --format="%i\|%j\|%T\|%M\|%l\|%D\|%R"` | Pipe-delimited |
| Job status | `scontrol show job <id>` | `Key=Value` pairs |
| Submit | `sbatch` with `--partition`, `--ntasks`, `--time`, `--mem`, `--gres=gpu:N`, `--wrap` | `Submitted batch job <id>` |
| Kill | `scancel <id>` | Confirmation text |
| Terminal statuses | `COMPLETED`, `FAILED`, `CANCELLED`, `TIMEOUT`, `OUT_OF_MEMORY`, `NODE_FAIL` | |
| Profile | None needed | |

**LSF → SLURM flag mapping:**

| LSF flag | SLURM equivalent |
|----------|-----------------|
| `-q <queue>` | `--partition=<partition>` |
| `-n <cores>` | `--ntasks=<cores>` |
| `-W <HH:MM>` | `--time=<HH:MM:SS>` |
| `-R "rusage[mem=N]"` | `--mem=<N>M` |
| `-gpu "num=N"` | `--gres=gpu:<N>` |
| `-J <name>` | `--job-name=<name>` |
| `-o <file>` | `--output=<file>` |
| `-e <file>` | `--error=<file>` |

### Tools (6 per backend, identical names)

| Tool | Required kwargs | Notes |
|------|----------------|-------|
| `cluster_jobs` | None | List all user jobs |
| `cluster_status` | None | Detailed status for one job |
| `cluster_submit` | None | Submit a job |
| `cluster_kill` | None | Kill a job |
| `cluster_logs` | None | Read job log files |
| `cluster_watch` | `send_notification`, `find_agent` (graceful degradation) | Background polling, notifies on completion |

### Copier questions

```yaml
use_cluster:
  type: bool
  default: false
  help: "Enable cluster job management (submit, monitor, kill jobs)?"

cluster_scheduler:
  type: str
  default: lsf
  choices:
    lsf: "IBM LSF (bsub/bjobs)"
    slurm: "SLURM (sbatch/squeue)"
  when: "{{ use_cluster }}"
  help: "Which cluster scheduler does your HPC use?"

cluster_ssh_target:
  type: str
  default: ""
  when: "{{ use_cluster }}"
  help: "SSH login node (leave empty if scheduler is available locally)"
```

### Copier file inclusion (Jinja2)

In the Copier template directory, the cluster files use conditional inclusion:

```
mcp_tools/_cluster.py.jinja    →  included when use_cluster is true
mcp_tools/lsf.py.jinja         →  included when use_cluster and cluster_scheduler == "lsf"
mcp_tools/slurm.py.jinja       →  included when use_cluster and cluster_scheduler == "slurm"
```

In `copier.yml`:

```yaml
_skip_if_exists: []

_exclude:
  - docs/
  - .ao_project_team/
  - submodules/
  - tests/
  - "{% if not use_cluster %}mcp_tools/_cluster.py{% endif %}"
  - "{% if not use_cluster or cluster_scheduler != 'lsf' %}mcp_tools/lsf.py{% endif %}"
  - "{% if not use_cluster or cluster_scheduler != 'lsf' %}mcp_tools/lsf.yaml{% endif %}"
  - "{% if not use_cluster or cluster_scheduler != 'slurm' %}mcp_tools/slurm.py{% endif %}"
  - "{% if not use_cluster or cluster_scheduler != 'slurm' %}mcp_tools/slurm.yaml{% endif %}"
```

### Per-tool YAML config files

Each MCP tool carries its own YAML config as a sibling file. `_load_config(Path(__file__))` reads `<tool>.yaml` next to `<tool>.py`.

**`mcp_tools/lsf.yaml`** (Copier template, included when `use_cluster` and `cluster_scheduler == "lsf"`):

```yaml
ssh_target: {{ cluster_ssh_target }}
lsf_profile: /misc/lsf/conf/profile.lsf
watch_poll_interval: 30
```

**`mcp_tools/slurm.yaml`** (Copier template, included when `use_cluster` and `cluster_scheduler == "slurm"`):

```yaml
ssh_target: {{ cluster_ssh_target }}
watch_poll_interval: 30
```

### pyyaml dependency

Add to `pixi.toml` (conditional on cluster):

```toml
{% if use_cluster %}
[feature.claudechic.pypi-dependencies]
pyyaml = "*"
{% endif %}
```

Only included when `use_cluster` is true — nothing else currently requires pyyaml.

### Verification checklist

- Zero `claudechic.*` imports in `lsf.py`, `slurm.py`, `_cluster.py`
- Each backend testable in isolation: `from mcp_tools.lsf import get_tools; get_tools()`
- Only dependencies: `claude_agent_sdk` + `pyyaml`

---

## Seam Summary

| # | Seam | Directory | Discovery |
|---|------|-----------|-----------|
| 1 | Environments | `pixi.toml` features | `activate` → `pixi info` |
| 2 | Commands | `commands/` | `activate` → PATH |
| 3 | Skills | `.claude/commands/` | Claude Code auto-discovers |
| 4 | Agent Roles | `AI_agents/**/*.md` | Coordinator reads |
| 5 | Guardrail Rules | `.claude/guardrails/` | `generate_hooks.py` reads |
| **6** | **MCP Tools** | **`mcp_tools/`** | **claudechic `mcp.py` scans** |

---

## Files Changed

### In AI_PROJECT_TEMPLATE (Copier template)

| File | Change | Section |
|------|--------|---------|
| `pixi.toml` | Claudechic dependency line (conditional on `claudechic_mode`) | 1, 2 |
| `.gitignore` | Add `submodules/claudechic/` | 2 |
| `copier.yml` | Add questions: `claudechic_mode`, `use_cluster`, `cluster_scheduler`, `cluster_ssh_target`. Add `_exclude: [docs/, .ao_project_team/, submodules/, tests/, ...]` with conditional cluster file exclusions. | 2, 4, 5 |
| `mcp_tools/_helpers.py` | New — shared MCP response helpers | 3 |
| `mcp_tools/_cluster.py` | New — shared cluster infrastructure (conditional on `use_cluster`) | 5 |
| `mcp_tools/lsf.py` | New — LSF backend (conditional on `use_cluster` + `cluster_scheduler == lsf`) | 5 |
| `mcp_tools/slurm.py` | New — SLURM backend (conditional on `use_cluster` + `cluster_scheduler == slurm`) | 5 |
| `mcp_tools/lsf.yaml` | New — LSF config (conditional on `use_cluster` + `cluster_scheduler == lsf`) | 5 |
| `mcp_tools/slurm.yaml` | New — SLURM config (conditional on `use_cluster` + `cluster_scheduler == slurm`) | 5 |
| `activate` / `activate.ps1` | Add `mcp_tools/` status display in Section 6 | 3 |
| `submodules/claudechic/` | Keep in template repo for development. Remove `.gitmodules` entry. Excluded from generated projects via `_exclude`. | 1, 2 |
| `tests/` | New — template testing scripts. Excluded from generated projects via `_exclude`. | Testing |
| `docs/install.sh` | New — Linux/macOS bootstrap (~30 lines). Template-repo only. | 4 |
| `docs/install.ps1` | New — Windows bootstrap (~40 lines). Template-repo only. | 4 |
| `docs/index.html` | New — GitHub Pages landing page (~130 lines). Template-repo only. | 4 |

### In claudechic (boazmohar fork)

| File | Change | Section |
|------|--------|---------|
| `claudechic/mcp.py` | Add `discover_mcp_tools()` (~30 lines) + call in `create_chic_server()` | 3 |

Push-to-fork workflow:
1. Implement `discover_mcp_tools()` in `claudechic/mcp.py` (code in Section 3)
2. Test with a dummy `mcp_tools/` tool
3. Push to `boazmohar/claudechic` main
4. In AI_PROJECT_TEMPLATE: `pixi update claudechic` to pick up new SHA

---

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Fork sync merge conflicts | Medium | 3 conflict areas identified with explicit resolutions |
| MCP kwargs evolve and break tools | Medium | Closed set for v2, documented as stable protocol |
| pixi-pack incompatible with git URL deps | Low | Developer mode (local path) works with pixi-pack — validated in v1 |
| SLURM backend untested on real cluster | Medium | Mock tests with captured real output. Manual testing when cluster available. |
| `pixi exec --spec copier` version drift | Medium | Pin: `--spec "copier>=9,<10"` |
| spawn_agent schema breaking change | Low | Project team already uses named params |

---

## Terminology

| Term | Definition |
|------|-----------|
| **MCP Tool** | Python file in `mcp_tools/` with `get_tools()`. Not the MCP server (claudechic). |
| **Standard Mode** | Git URL dependency. Default. |
| **Developer Mode** | Local editable clone for claudechic development. |
| **Seam Contract** | `get_tools(**kwargs)` — function-level interface. |

---

## Implementation Order

0. **Claudechic fork sync** — merge 20 upstream commits, resolve 3 conflicts. Must complete before all other steps.
1. **Claudechic `mcp.py` discovery code** — implement `discover_mcp_tools()` on synced boazmohar/main, test, push.
2. **`mcp_tools/` cluster files** — write `_cluster.py` (shared), `lsf.py` (refactored from fork's `cluster.py`), `slurm.py` (new). Decouple 2 claudechic imports.
3. **Clean up submodule** — remove `.gitmodules` entry (no longer a git submodule). `submodules/claudechic/` stays in template repo for development, excluded from generated projects via `_exclude`.
4. **Template changes** — `pixi.toml` conditional, Copier questions, per-tool YAML configs (`lsf.yaml`, `slurm.yaml`), `.gitignore`, `_helpers.py`, activate script display.
5. **Landing page + install scripts** — `docs/install.sh`, `docs/install.ps1`, `docs/index.html`. Enable GitHub Pages on `/docs`.
6. **Testing** — discovery tests, cluster tool tests (both backends), swap tests, install script end-to-end.

---

## Testing Strategy

Tests live in `tests/` in the template repo. Excluded from generated projects via `_exclude`.

### Local tests (`tests/`)

Scripts for quick feedback during development. Run from the template repo.

**Copier generation tests:**
- `copier copy` into temp dir with standard mode → verify `pixi.toml` has git URL line
- `copier copy` into temp dir with developer mode → verify `pixi.toml` has editable path line, `submodules/claudechic/` cloned
- `copier copy` with `use_cluster=true, cluster_scheduler=lsf` → verify `mcp_tools/lsf.py` present, `slurm.py` absent
- `copier copy` with `use_cluster=true, cluster_scheduler=slurm` → verify `mcp_tools/slurm.py` present, `lsf.py` absent
- `copier copy` with `use_cluster=false` → verify no cluster files in `mcp_tools/`
- Verify `docs/`, `.ao_project_team/`, `submodules/`, `tests/` are NOT in generated project

**MCP discovery tests:**
- Empty `mcp_tools/` → empty list
- Missing `mcp_tools/` → empty list
- Underscore files skipped
- Files without `get_tools()` skipped
- Broken files skipped (others still load)
- kwargs passed through correctly
- Alphabetical load order

**Cluster tool tests:**
- `lsf.py`: `get_tools()` with no kwargs → 6 tools returned
- `slurm.py`: `get_tools()` with no kwargs → 6 tools returned
- `cluster_watch` without wiring → returns graceful error
- Tool responses are valid MCP format
- Mock `_run_ssh()` for command construction tests
- LSF: parse captured `bjobs -w`, `bjobs -l` output
- SLURM: parse captured `squeue --format`, `scontrol show job` output
- Each backend testable independently

**Environment tests:**
- Standard mode: `pixi install` resolves claudechic from git URL, `import claudechic` works
- Developer mode: `pixi install` with editable local path, `import claudechic` works
- Swap test: change 1 line in `pixi.toml`, `pixi install` — both modes work
- MCP tools load after `pixi install`: discovery finds cluster tools

### CI tests (GitHub Actions)

Same tests as local, run cross-platform on clean machines.

| Platform | Runner | Tests |
|----------|--------|-------|
| Linux x86_64 | `ubuntu-latest` | Full suite |
| macOS ARM64 | `macos-latest` | Full suite |
| Windows | `windows-latest` | Full suite (PowerShell install script, `activate.ps1`) |

CI workflow:
1. Checkout template repo
2. Install pixi
3. Run `copier copy` with each configuration (standard/developer, lsf/slurm/none)
4. Run `pixi install` in generated project
5. Verify claudechic imports
6. Verify MCP tools discovery
7. Run cluster tool unit tests (mocked SSH)

---

## Template Development Workflow

| Branch | Purpose | Audience |
|--------|---------|----------|
| `main` | Clean, user-facing. `copier copy` pulls from here. | End users |
| `develop` | Feature work. Specs and `.ao_project_team/` committed. | Contributors |
| Feature branches | Branch off `develop` for individual features. | Individual contributors |

`docs/`, `.ao_project_team/`, `submodules/`, and `tests/` are committed to git (project history and development infrastructure) but excluded from generated projects via Copier's `_exclude`.

Contribution workflow:
1. Fork or branch from `develop`
2. Commit specs to `.ao_project_team/<feature>/`
3. Implement template changes
4. PR to `develop`
5. Periodic clean merges from `develop` → `main`
