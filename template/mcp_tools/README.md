# MCP Tools

Drop-in tool plugins for claudechic. Any `.py` file in this directory (except underscore-prefixed helpers) is automatically discovered and registered by claudechic's MCP server.

## How It Works

Each tool file implements a `get_tools(**kwargs)` function that returns a list of MCP tools:

```python
def get_tools(caller_name=None, send_notification=None, find_agent=None, **kwargs):
    # Return a list of tool objects
    return [my_tool_1, my_tool_2]
```

Discovery happens at startup -- claudechic walks `mcp_tools/*.py`, imports each module, and calls `get_tools()`. Files that start with `_` are skipped (they're helpers, not entry points).

### Per-Tool Config

Each tool can have a sibling YAML config file with the same name:

```
mcp_tools/
|---- lsf.py          # LSF backend
|---- slurm.py        # SLURM backend
|---- cluster.yaml    # Cluster config (backend, SSH target, etc.)
|---- _cluster.py     # Shared helper (underscore = not discovered)
|---- README.md
```

Load config in your tool with:

```python
from mcp_tools._cluster import _load_config
config = _load_config(Path(__file__))  # Reads cluster.yaml
```

## Cluster Backends

The template includes HPC cluster job management with two backends:

### LSF (`lsf.py`)

For IBM LSF clusters (bsub/bjobs). Provides tools for:
- **cluster_jobs** -- list running/pending jobs
- **cluster_submit** -- submit batch jobs via bsub
- **cluster_job_details** -- detailed job info
- **cluster_kill** -- kill jobs
- **cluster_logs** -- read job output/error logs
- **cluster_watch** -- poll a job until completion

### SLURM (`slurm.py`)

For SLURM clusters (sbatch/squeue). Same tool names, same interface, different backend commands.

### Shared Infrastructure (`_cluster.py`)

Both backends share common infrastructure via the underscore-prefixed `_cluster.py` helper:
- **SSH layer** -- run commands on remote login nodes
- **Log reading** -- tail job output files
- **Watch mechanism** -- poll job status with configurable intervals
- **Config reader** -- load per-tool YAML config
- **Response helpers** -- format tool responses consistently

### Configuration

Both backends share a single config file (`cluster.yaml`) with:

```yaml
backend: ""              # lsf | slurm -- detected by cluster-setup workflow
ssh_target: ""           # Login node (empty = local scheduler)
lsf_profile: ""          # LSF-specific (e.g., /misc/lsf/conf/profile.lsf)
watch_poll_interval: 30
remote_cwd: ""
path_map: []
log_access: auto
```

The SSH target and backend are configured by the cluster-setup workflow.

### SSH Setup

If your cluster scheduler runs on a remote login node (not the machine where claudechic runs), you need passwordless SSH:

```bash
# 1. Generate a key (if you don't have one)
ssh-keygen -t ed25519

# 2. Copy it to the login node
ssh-copy-id login1.example.com

# 3. Test it works without a password prompt
ssh login1.example.com hostname
```

For hosts behind a jump/bastion server, add to `~/.ssh/config`:

```
Host login1.example.com
    ProxyJump bastion.example.com
    User your_username
```

The cluster tools use `ssh <target> <command>` under the hood -- any SSH config that makes `ssh login1.example.com bjobs` work interactively will also work from claudechic.

## Adding a New Tool

1. Create `mcp_tools/my_tool.py` with a `get_tools(**kwargs)` function
2. Optionally create `mcp_tools/my_tool.yaml` for configuration
3. Restart claudechic -- your tool is automatically discovered

The kwargs passed to `get_tools()` include:
- `caller_name` -- name of the calling agent
- `send_notification` -- function to send notifications to the TUI
- `find_agent` -- function to look up other agents

### Iron Rule

Discovery never crashes. If your tool file has an import error or `get_tools()` raises, it's logged and skipped -- other tools still load.
