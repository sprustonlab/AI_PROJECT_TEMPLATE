# User Request — Composable Plugins v2

## Context

v1 (branch `composable-onboarding`) implemented:
- Pixi-based env management (replacing SLC)
- 5 codified seams (envs, commands, skills, agent roles, guardrail rules)
- Pure Python guardrail hooks (cross-platform)
- Copier-based onboarding
- Pattern miner port
- rules.d/ for contributed guardrail rule sets
- Windows first-class support
- CI for 3 platforms (Linux, macOS, Windows)

## What v2 Adds

### 1. Claudechic as a git URL dependency (not committed code)

Claudechic should be installed via git URL in `pixi.toml`:
```toml
[pypi-dependencies]
claudechic = { git = "https://github.com/boazmohar/claudechic", branch = "main" }
```

This replaces the committed code in `submodules/claudechic/`. Users get updates via `pixi update`. No PyPI publishing needed — it's a fork we control.

### 2. Developer mode for claudechic hackers

Onboarding asks how the user wants claudechic:
- **Standard mode:** git URL dependency, updates automatically
- **Developer mode:** clones repo locally into `submodules/claudechic/`, editable install, user hacks freely

Switching is one line in `pixi.toml`. The onboarding explains the tradeoff.

### 3. MCP Tools seam (#6)

New seam: `mcp_tools/` directory at project root. Claudechic discovers Python files with `get_tools()` at startup. ~20 lines of discovery code in claudechic's `mcp.py`.

This enables:
- **Cluster MCP (LSF):** shipped as `mcp_tools/cluster.py`, toggled via Copier question
- **Future backends (SLURM, PBS, Kubernetes):** drop a `.py` file
- **User custom MCP tools:** same pattern as all other seams
- **New core-ish tools** (e.g., `tell_agent_wait`): shipped via `mcp_tools/` independently of claudechic version

Seam contract: `get_tools(**kwargs) -> list[tool_function]`
kwargs provide optional wiring: `caller_name`, `send_notification`, `find_agent`

### 4. Bootstrap simplification

Replace `pip install copier` with pixi-only bootstrap:
```bash
# Install pixi (one-time)
curl -fsSL https://pixi.sh/install.sh | bash  # Linux/macOS
iwr -useb https://pixi.sh/install.ps1 | iex   # Windows

# Create project (copier runs in ephemeral env)
pixi exec --spec copier copier copy https://github.com/sprustonlab/AI_PROJECT_TEMPLATE my-project
```

Two commands. One dependency (pixi). Copier is never permanently installed.

### 5. Cluster MCP inclusion

Port `cluster.py` from `/groups/spruston/home/moharb/DECODE-PRISM/Repos/claudechic/claudechic/cluster.py` into `mcp_tools/cluster.py`. Provides: cluster_jobs, cluster_status, cluster_submit, cluster_kill, cluster_logs, cluster_watch.

Copier question:
```yaml
use_cluster:
  type: bool
  default: false
  help: "Enable LSF cluster job management?"
```

File presence = enabled. Delete = disabled. Config in `.claudechic.yaml` for SSH target, poll interval, etc.

## Key Design Decisions from v1 Analysis

- Directory conventions ARE the plugin system (no framework)
- Copier assembles files at creation time, no runtime dispatch
- `copier update` handles template evolution (3-way merge)
- `_skip_if_exists` for user-owned files Copier shouldn't touch
- Pixi is the sole env backend (conda-forge covers Python, R, C, etc.)
- Pure Python hooks for cross-platform guardrails
- Seams pass the swap test — add/remove/replace without touching other seams

## Reference Material

- v1 spec: `.ao_project_team/composable_plugins/specification/SPECIFICATION.md`
- Seam analyses: `.ao_project_team/composable_plugins/specification/seam_*.md`
- Cluster MCP source: `/groups/spruston/home/moharb/DECODE-PRISM/Repos/claudechic/claudechic/cluster.py`
- MCP tool registration analysis: Composability2's seam #6 analysis
- Bootstrap analysis: Skeptic2's `pixi exec` recommendation
- claudechic distribution analysis: Composability2 + Skeptic2 convergence on git URL + developer mode
