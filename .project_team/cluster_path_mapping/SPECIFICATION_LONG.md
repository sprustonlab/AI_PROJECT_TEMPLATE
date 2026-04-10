# Specification: cluster_path_mapping

**Status:** Draft v10-long
**Date:** 2026-04-09
**Authors:** Composability, Terminology, UserAlignment, Skeptic (synthesized)

---

## 1. Overview

The cluster MCP tools assume local and cluster filesystem paths are identical and that log files are locally accessible. Both assumptions break for users on SMB mounts, WSL, Windows mapped drives, or SSH-only environments. This project adds:

- **`PathMapper`** — bidirectional local↔cluster path translation (shared class in `_cluster.py`)
- **`LogReader`** — strategy pattern for transport-aware log reading (local mount, SSH, or auto-fallback)
- **`cluster_setup`** — claudechic workflow that detects environment, proposes config, validates, and writes
- **Config keys** — `path_map`, `remote_cwd`, `log_access` added to both `lsf.yaml` and `slurm.yaml`

Empty config = passthrough (paths used as-is). Scheduler-agnostic (LSF + SLURM share all infrastructure). TDD with ~13 parameterized test functions (~80 actual test cases).

---

## 2. Terminology

| Term | Definition |
|------|-----------|
| **local path** | A filesystem path as seen by the MCP client process (Claude Code). May be a POSIX path, a Windows path, or a UNC/SMB path depending on the user's OS and mount configuration. |
| **cluster path** | A filesystem path as seen by the cluster compute nodes and login nodes. Always POSIX. This is the path used inside SSH commands and scheduler directives. |
| **remote_cwd** | A config-level setting specifying the default working directory (as a cluster path) for submitted jobs. Overrides the auto-translated `os.getcwd()`. Independent from `path_map`. |
| **execution_cwd** | A per-job property returned by the scheduler (e.g., LSF's `Execution CWD`, SLURM's `WorkDir`). This is a cluster path describing where a specific job actually ran. Not user-configurable. |
| **path_map** | An ordered list of `{local, cluster}` prefix pairs in the YAML config. Defines bidirectional translation rules. First match wins (after longest-prefix sorting). |
| **path translation** | The act of converting a path from one filesystem to another using `path_map` rules. Performed by `PathMapper.to_cluster()` (local -> cluster) and `PathMapper.to_local()` (cluster -> local). |
| **path normalization** | Pre-processing a path before translation: resolving `~`, expanding `$HOME`/env vars (local side only), converting backslashes to forward slashes (local side only), and stripping trailing slashes. Performed by `_normalize_local_path()` / `_normalize_cluster_path()`. |
| **log_access** | A config key controlling how log files are read: `auto` (try local then SSH), `local` (local/mount only), or `ssh` (always via SSH). |
| **log transport** | The mechanism used to read log file contents — either local filesystem access or SSH-based remote reading. Orthogonal to path translation. |
| **claudechic workflow** | A markdown-defined workflow (`.claude/workflows/`) that the model executes conversationally, advancing through phases via structured checks. State lives in the conversation context. |

---

## 3. Architecture

### 3.1 PathMapper Class (in `_cluster.py`)

A single shared class consumed by both LSF and SLURM backends:

```python
class PathMapper:
    """Bidirectional path translation between local and cluster filesystems.

    Maintains two sorted rule lists — one sorted by local prefix length
    (for to_cluster lookups) and one by cluster prefix length (for to_local
    lookups). An empty rule list means all paths pass through unchanged.

    All returned paths use forward slashes, even on Windows. Windows APIs
    accept forward slashes natively.
    """

    def __init__(self, path_map: list[dict[str, str]] | None = None):
        rules = []
        for entry in (path_map or []):
            local = _normalize_local_path(entry["local"])
            cluster = _normalize_cluster_path(entry["cluster"])
            rules.append((local, cluster))
        # Two sorted views — each direction matches against the correct prefix
        self._rules_by_local: list[tuple[str, str]] = sorted(
            rules, key=lambda r: len(r[0]), reverse=True,
        )
        self._rules_by_cluster: list[tuple[str, str]] = sorted(
            rules, key=lambda r: len(r[1]), reverse=True,
        )

    def to_cluster(self, local_path: str) -> str:
        """Translate a local path to a cluster path."""
        normalized = _normalize_local_path(local_path)
        for local_prefix, cluster_prefix in self._rules_by_local:
            # Boundary-safe matching: prefix must align on "/" or be exact.
            # Bare startswith() would cause "/mnt/cluster" to match
            # "/mnt/cluster-backup" — a silent, dangerous false match.
            if normalized == local_prefix or normalized.startswith(local_prefix + "/"):
                return cluster_prefix + normalized[len(local_prefix):]
        return local_path  # passthrough

    def to_local(self, cluster_path: str) -> str:
        """Translate a cluster path to a local path.

        Returns forward-slash paths on all platforms. Windows APIs accept
        forward slashes natively.
        """
        normalized = _normalize_cluster_path(cluster_path)
        for local_prefix, cluster_prefix in self._rules_by_cluster:
            # Boundary-safe matching — see to_cluster() comment.
            if normalized == cluster_prefix or normalized.startswith(cluster_prefix + "/"):
                return local_prefix + normalized[len(cluster_prefix):]
        return cluster_path  # passthrough
```

### 3.2 Path Normalization Helpers

Two separate normalizers — local paths get full expansion, cluster paths only get minimal cleanup (no env var or tilde expansion, since those would use local values):

```python
def _normalize_local_path(p: str) -> str:
    """Normalize a LOCAL path for prefix matching.

    - Expand ~ and environment variables (safe: uses local env)
    - Convert backslashes to forward slashes
    - Strip trailing slashes (except bare "/")
    """
    expanded = os.path.expandvars(os.path.expanduser(p))
    forward = expanded.replace("\\", "/")
    return forward.rstrip("/") if forward != "/" else forward


def _normalize_cluster_path(p: str) -> str:
    """Normalize a CLUSTER path for prefix matching.

    - Strip trailing slashes (except bare "/")
    - NO env var expansion (local $HOME != cluster $HOME)
    - NO tilde expansion (local ~ != cluster ~)
    - NO backslash conversion (cluster paths are always POSIX)
    """
    return p.rstrip("/") if p != "/" else p
```

### 3.3 Shared CWD Resolution Helper

```python
def _resolve_cwd(config: dict, path_mapper: PathMapper) -> str:
    """Determine the effective cluster CWD for job submission.

    Returns a cluster path string. Each backend passes the resolved CWD
    to the scheduler via its native flag (bsub -cwd, sbatch --chdir).

    Priority: config["remote_cwd"] > path_mapper.to_cluster(os.getcwd()) > os.getcwd()
    """
    remote_cwd = config.get("remote_cwd")
    if remote_cwd:
        return remote_cwd
    return path_mapper.to_cluster(os.getcwd())
```

Each backend uses its scheduler's native CWD flag:

```python
# LSF (lsf.py):
cwd = _resolve_cwd(config, path_mapper)
parts += ["-cwd", shlex.quote(cwd)]

# SLURM (slurm.py):
cwd = _resolve_cwd(config, path_mapper)
parts += [f"--chdir={shlex.quote(cwd)}"]
```

### 3.4 Updated `_resolve_log_path()`

Resolves relative paths against `execution_cwd` on the **cluster filesystem only**. Does NOT perform path translation — that responsibility belongs to the `LogReader` (Section 3.6).

```python
def _resolve_log_path(
    log_path: str,
    execution_cwd: str | None,
) -> str:
    """Resolve a log file path on the cluster filesystem.

    1. If absolute (starts with "/"), return as-is.
       Uses startswith("/") instead of os.path.isabs() because cluster
       paths are always POSIX, and os.path.isabs() fails on Windows
       for POSIX paths like "/groups/lab/out.log".
    2. If relative, prepend execution_cwd.

    Returns a cluster path (string, not Path -- since it may not be
    valid on the local filesystem).
    """
    if log_path.startswith("/"):
        return log_path
    if execution_cwd:
        return f"{execution_cwd}/{log_path}"
    return log_path
```

### 3.5 PathMapper Factory

```python
def _create_path_mapper(config: dict) -> PathMapper:
    """Create a PathMapper from the config's path_map key."""
    return PathMapper(config.get("path_map"))
```

### 3.6 LogReader Strategy Pattern (in `_cluster.py`)

A strategy pattern that separates **how** log files are read (transport) from **where** they are (filesystem).

```python
import shlex
from typing import Protocol


class LogReader(Protocol):
    """Strategy for reading log file contents."""

    def read_tail(self, cluster_path: str, tail: int) -> str | None:
        """Read last `tail` lines of a log file (0 = full file).

        Args:
            cluster_path: The log file path on the cluster filesystem.
            tail: Number of lines from the end (0 = all).

        Returns:
            File contents as a string, or None if unavailable.
        """
        ...


class LocalLogReader:
    """Read logs from local/mounted filesystem.

    Translates cluster paths to local paths via PathMapper before reading.
    """

    def __init__(self, path_mapper: PathMapper | None = None):
        self._path_mapper = path_mapper

    def read_tail(self, cluster_path: str, tail: int) -> str | None:
        local_path = cluster_path
        if self._path_mapper:
            local_path = self._path_mapper.to_local(cluster_path)
        return _read_tail(Path(local_path), tail)


class SSHLogReader:
    """Read logs via SSH when no shared filesystem is available.

    Uses the cluster path directly — no translation needed since the
    SSH command runs on the cluster.
    """

    def __init__(self, ssh_target: str, profile: str | None = None):
        self._ssh_target = ssh_target
        self._profile = profile

    def read_tail(self, cluster_path: str, tail: int) -> str | None:
        if not self._ssh_target:
            return None
        safe_path = shlex.quote(cluster_path)
        if tail > 0:
            cmd = f"tail -n {tail} {safe_path}"
        else:
            cmd = f"cat {safe_path}"
        stdout, stderr, rc = _run_ssh(
            cmd, self._ssh_target, profile=self._profile, timeout=30,
        )
        if rc != 0:
            log.debug(
                "SSH log read failed (rc=%d) for %s: %s",
                rc, cluster_path, stderr.strip(),
            )
            return None
        return stdout


class AutoLogReader:
    """Try local filesystem first, fall back to SSH.

    This is the default strategy (`log_access: auto`).
    """

    def __init__(self, local: LocalLogReader, ssh: SSHLogReader):
        self._local = local
        self._ssh = ssh

    def read_tail(self, cluster_path: str, tail: int) -> str | None:
        content = self._local.read_tail(cluster_path, tail)
        if content is not None:
            return content
        log.debug(
            "Local log read failed for %s, falling back to SSH", cluster_path,
        )
        return self._ssh.read_tail(cluster_path, tail)
```

### 3.7 LogReader Factory

```python
def _create_log_reader(
    config: dict,
    path_mapper: PathMapper | None = None,
    profile: str | None = None,
) -> LogReader:
    """Create the appropriate LogReader based on config['log_access'].

    Args:
        config: The tool config dict.
        path_mapper: For local path translation.
        profile: Scheduler profile script (e.g., LSF profile path).
            Each backend passes its own profile key explicitly.

    Modes:
        "auto"  -- try local first, fall back to SSH (default)
        "local" -- local filesystem only (NFS/SMB mount required)
        "ssh"   -- always read via SSH (no shared filesystem)
    """
    mode = config.get("log_access", "auto")
    ssh_target = config.get("ssh_target", "")

    local = LocalLogReader(path_mapper)
    ssh = SSHLogReader(ssh_target, profile)

    if mode == "local":
        return local
    elif mode == "ssh":
        return ssh
    else:  # "auto"
        return AutoLogReader(local, ssh)
```

### 3.8 Updated `_read_logs()`

```python
def _read_logs(
    job_id: str,
    get_job_status_fn,
    tail: int = 100,
    log_reader: LogReader,
    path_mapper: PathMapper | None = None,
) -> dict[str, Any]:
    """Read stdout/stderr log files for a cluster job.

    Args:
        job_id: The cluster job ID.
        get_job_status_fn: Function to get job details (returns dict).
        tail: Number of lines from the end (0 = full log).
        log_reader: Strategy for reading log contents (required).
        path_mapper: For translating display paths in the response.
    """
    detail = get_job_status_fn(job_id)
    stdout_log_path = detail.get("stdout_path")   # cluster path
    stderr_log_path = detail.get("stderr_path")    # cluster path
    execution_cwd = detail.get("execution_cwd")    # cluster path

    result: dict[str, Any] = {
        "job_id": job_id,
        "stdout": "",
        "stderr": "",
        "log_paths": {"stdout": stdout_log_path, "stderr": stderr_log_path},
        "found": False,
    }

    for stream in ("stdout", "stderr"):
        raw_path = detail.get(f"{stream}_path")
        if not raw_path:
            continue
        # Resolve relative paths (stays on cluster filesystem)
        resolved = _resolve_log_path(raw_path, execution_cwd)
        # Reader handles transport (local+translation, SSH, or auto)
        content = log_reader.read_tail(resolved, tail)
        if content is not None:
            result[stream] = content
            result["found"] = True
            # Return local path to the model if we have a mapper
            display_path = (
                path_mapper.to_local(resolved) if path_mapper else resolved
            )
            result["log_paths"][stream] = display_path

    return result
```

---

## 4. Config Schema

### 4.1 Additions to `lsf.yaml.jinja`

```yaml
# SSH login node for LSF commands (leave empty if LSF is available locally)
ssh_target: {{ cluster_ssh_target }}
# Path to LSF profile script sourced before each command
lsf_profile: /misc/lsf/conf/profile.lsf
# Seconds between polls when watching a job for completion
watch_poll_interval: 30

# Working directory (cluster path) for submitted jobs.
# Overrides the auto-translated os.getcwd().
# Leave empty to auto-translate the client's current directory via path_map.
remote_cwd: ""

# Bidirectional path mapping rules (ordered, longest-prefix match wins).
# "local"   = path as seen by the MCP client (e.g., SMB mount, WSL path)
# "cluster" = path as seen by the cluster login/compute nodes
# Leave empty if local and cluster paths are identical (default: passthrough).
path_map: []
  # - local: /mnt/janelia
  #   cluster: /groups/spruston
  # - local: //smb-server/spruston
  #   cluster: /groups/spruston

# How to read job log files:
#   "auto"  — try local filesystem first, fall back to SSH (default, recommended)
#   "local" — local filesystem only (requires NFS/SMB mount)
#   "ssh"   — always read via SSH (for users with no shared filesystem)
log_access: auto
```

### 4.2 Additions to `slurm.yaml.jinja`

```yaml
# SSH login node for SLURM commands (leave empty if SLURM is available locally)
ssh_target: {{ cluster_ssh_target }}
# Seconds between polls when watching a job for completion
watch_poll_interval: 30

# Working directory (cluster path) for submitted jobs.
# Overrides the auto-translated os.getcwd().
# Leave empty to auto-translate the client's current directory via path_map.
remote_cwd: ""

# Bidirectional path mapping rules (ordered, longest-prefix match wins).
# "local"   = path as seen by the MCP client (e.g., SMB mount, WSL path)
# "cluster" = path as seen by the cluster login/compute nodes
# Leave empty if local and cluster paths are identical (default: passthrough).
path_map: []
  # - local: /mnt/janelia
  #   cluster: /groups/spruston
  # - local: //smb-server/spruston
  #   cluster: /groups/spruston

# How to read job log files:
#   "auto"  — try local filesystem first, fall back to SSH (default, recommended)
#   "local" — local filesystem only (requires NFS/SMB mount)
#   "ssh"   — always read via SSH (for users with no shared filesystem)
log_access: auto
```

### 4.3 New Config Keys

The table below lists the **new** config keys introduced by this project. Existing keys (`ssh_target`, `lsf_profile`, `watch_poll_interval`) are also read by the new code but are not new — they are already documented in their respective YAML templates.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `remote_cwd` | `str` | `""` | Cluster path used as CWD for submitted jobs. Empty = auto-translate via path_map. |
| `path_map` | `list[{local: str, cluster: str}]` | `[]` | Ordered prefix-replacement rules. Empty = passthrough. |
| `log_access` | `str` | `"auto"` | How to read log files: `auto`, `local`, or `ssh`. |

YAML template comments (shown above) serve as inline documentation for users configuring their environment.

---

## 5. Integration Points

### 5.1 `_submit_job()` CWD via Native Scheduler Flags — Both Backends

Both backends use `_resolve_cwd()` from `_cluster.py` to compute the cluster path, then pass it via the scheduler's own flag. The user's command string is never modified.

**LSF (`lsf.py`):**
```python
cwd = _resolve_cwd(config, path_mapper)
parts += ["-cwd", shlex.quote(cwd)]
```

**SLURM (`slurm.py`):**
```python
cwd = _resolve_cwd(config, path_mapper)
parts += [f"--chdir={shlex.quote(cwd)}"]
```

### 5.2 `_submit_job()` stdout/stderr Path Translation

When the user provides `stdout_path` or `stderr_path` as local paths, translate to cluster paths for the scheduler:

```python
if stdout_path:
    stdout_path = path_mapper.to_cluster(stdout_path)
if stderr_path:
    stderr_path = path_mapper.to_cluster(stderr_path)
```

Local `mkdir` for log directories uses the **local** path (before translation). When `log_access` is `ssh` (no shared filesystem), skip local `mkdir` — the scheduler creates directories on the cluster side:

```python
log_access = config.get("log_access", "auto")
for lp in [stdout_path, stderr_path]:
    if lp and log_access != "ssh":
        local_dir = Path(path_mapper.to_local(lp)).parent
        local_dir.mkdir(parents=True, exist_ok=True)
```

### 5.3 `_resolve_log_path()` — Cluster-Filesystem Resolution Only

`_resolve_log_path()` resolves relative log paths against `execution_cwd`, staying entirely on the **cluster filesystem**. Returns `str` (not `Path`). Uses `startswith("/")` for absolute-path detection (not `os.path.isabs()`, which fails on Windows for POSIX paths). Path translation for local reading is handled by `LocalLogReader.read_tail()`. SSH reading uses the cluster path directly.

```python
# In _read_logs():
resolved = _resolve_log_path(raw_path, execution_cwd)  # cluster path string
content = reader.read_tail(resolved, tail)              # reader handles transport
```

### 5.4 Status Response Path Display

Paths returned by `_parse_bjobs_detail()` (LSF) and `_parse_scontrol_job()` (SLURM) are cluster paths. Translate to local paths in status responses:

```python
for key in ("stdout_path", "stderr_path", "execution_cwd"):
    if detail.get(key):
        detail[key] = path_mapper.to_local(detail[key])
```

### 5.5 `_read_logs()` — LogReader Wiring

Both backends create `PathMapper` and `LogReader` **lazily inside each tool handler** (not at `get_tools()` time). This ensures that config changes made by `cluster_setup apply` are picked up immediately — every tool call reads fresh config.

```python
# In each tool handler (e.g., cluster_logs, cluster_submit):
config = _get_config()
path_mapper = _create_path_mapper(config)
log_reader = _create_log_reader(config, path_mapper, profile=config.get("lsf_profile"))

# In the cluster_logs tool handler:
result = await asyncio.to_thread(
    _read_logs, job_id,
    lambda jid: _get_job_status(jid, config),
    tail,
    log_reader=log_reader,
    path_mapper=path_mapper,
)
```

> **Note:** `_create_log_reader()` accepts `profile` as an explicit parameter. Each backend passes its own profile key (e.g., `config.get("lsf_profile")` for LSF, `None` for SLURM).

### 5.6 Call-Site Wiring Summary

| Location | Direction | Function Used |
|----------|-----------|---------------|
| `_submit_job()` CWD | local -> cluster | `_resolve_cwd()` (uses `to_cluster`); passed via `-cwd` / `--chdir` flag |
| `_submit_job()` log paths | local -> cluster | `path_mapper.to_cluster()` |
| `_submit_job()` mkdir | cluster -> local | `path_mapper.to_local()` (skipped when `log_access: ssh`) |
| `LocalLogReader.read_tail()` | cluster -> local | `path_mapper.to_local()` (for local `open()`) |
| `SSHLogReader.read_tail()` | none | Uses cluster path directly |
| `AutoLogReader.read_tail()` | cluster -> local (local attempt) | Delegates to `LocalLogReader` then `SSHLogReader` |
| `_read_logs()` display paths | cluster -> local | `path_mapper.to_local()` (for model response) |
| Status response display | cluster -> local | `path_mapper.to_local()` |

---

## 6. Risk Mitigations

| # | Risk | Mitigation |
|---|------|------------|
| 6.1 | Shell injection via paths (spaces, quotes, backticks, `$(...)`) | `shlex.quote()` on all paths in scheduler flags and SSH commands. |
| 6.2 | Shell injection via SSH log reading | `SSHLogReader.read_tail()` uses `shlex.quote()` on cluster path before embedding in SSH command. |
| 6.3 | Path traversal via malicious `path_map` | Intentionally omitted — trust boundary is user-controlled YAML config. |
| 6.4 | Overlapping mapping rules | `PathMapper.__init__()` maintains two sorted lists (by local prefix length and by cluster prefix length). Longest prefix always wins in each direction. User's YAML order is tiebreaker for equal lengths. |
| 6.5 | Trailing slash mismatch | `_normalize_local_path()` / `_normalize_cluster_path()` strip trailing slashes before storing and matching. |
| 6.6 | Case sensitivity (Windows/macOS vs Linux) | Known limitation. All matching is case-sensitive (Linux semantics). Future `case_insensitive` flag per rule if needed. |
| 6.7 | `/bin/bash` hardcoded in `_run_ssh()` | Known limitation on Windows. Future fix: `shutil.which("bash")` with fallback. Out of scope. |
| 6.8 | Config defaults for existing users | Existing configs without new keys work unchanged (passthrough defaults). All fields default to safe values (`""`, `[]`, `"auto"`). Empty `PathMapper` = passthrough. `AutoLogReader` tries local first. No guarantee that the new key schema will be preserved across future versions. |
| 6.9 | Malformed `path_map` entries | `PathMapper.__init__()` validates `local` and `cluster` keys as non-empty strings. `log_access` validated to `auto`/`local`/`ssh`. `ValueError` at config load time. |
| 6.10 | SSH log reading performance | Mitigated by existing SSH connection multiplexing (`ControlMaster`). `tail -n` runs remote-side. `AutoLogReader` tries local first (O(1) for mount users). 30s timeout prevents hangs. |
| 6.11 | Silent SSH fallback debugging | `AutoLogReader` and `SSHLogReader` log at `DEBUG` level on fallback/failure. |
| 6.12 | Env var expansion on cluster paths | `_normalize_cluster_path()` does NOT expand `$HOME` or `~`. A user writing `cluster: "$HOME/data"` keeps the literal string. Only `_normalize_local_path()` expands env vars (using local env, which is correct for local paths). |
| 6.13 | `os.path.isabs()` fails on Windows for POSIX paths | `_resolve_log_path()` uses `startswith("/")` instead of `os.path.isabs()`. Cluster paths are always POSIX. |

---

## 7. Model Awareness

### 7.1 Updated Tool Descriptions

**`cluster_submit`:**
```
"Submit a job to the {LSF|SLURM} cluster. Paths in log path arguments "
"(stdout_path, stderr_path) are automatically translated between local "
"and cluster filesystems if path_map is configured. Working directory "
"defaults to the translated current directory (or remote_cwd if set). "
"NOTE: Paths inside your command string are NOT automatically translated "
"-- use relative paths or cluster-side absolute paths in the command. "
"IMPORTANT: If the response contains setup_needed='needs_setup', STOP "
"and automatically run cluster_setup phase='diagnose' before retrying. "
"If 'incomplete', ask the user if they want to run cluster_setup first."
```

**`cluster_logs`:**
```
"Read stdout/stderr log files for a cluster job. Log paths are "
"automatically translated from cluster paths to local paths via path_map. "
"Logs can be read from mounted filesystems or via SSH depending on "
"log_access config (default: auto -- tries local first, falls back to SSH). "
"IMPORTANT: If the response contains setup_needed, handle it the same "
"as cluster_submit (auto-run setup for 'needs_setup', ask for 'incomplete')."
```

**`cluster_status`:**
```
"Get detailed status for a cluster job. Paths in the response "
"(stdout_path, stderr_path, execution_cwd) are translated to local paths."
```

**`cluster_setup` workflow triggering (in all cluster tool descriptions):**
```
"IMPORTANT: If the response contains setup_needed='needs_setup', STOP "
"and invoke the cluster_setup workflow to guide the user through "
"configuration. If 'incomplete', ask the user if they want to run the "
"cluster_setup workflow first."
```

The `setup_needed` field value includes the workflow name explicitly (e.g., `"run cluster_setup workflow"`), so the model knows which workflow to invoke. Tool descriptions instruct the model to check for this field in every response.

### 7.2 Error Hints in Tool Responses

When runtime tools fail in ways suggesting misconfiguration, the error response includes a setup hint directing the model to the `cluster_setup` workflow. This creates a self-healing loop: failure -> hint -> workflow -> fix -> retry.

```python
def _error_with_hint(message: str, hint_type: str = "path") -> dict:
    """Return an error response with a cluster_setup workflow hint."""
    hints = {
        "path": "Path may not be configured correctly. Run the cluster_setup workflow.",
        "connection": "Cluster connection failed. Run the cluster_setup workflow.",
        "first_use": "Cluster tools are not yet configured. Run the cluster_setup workflow.",
    }
    return _error_response(message, hint=hints.get(hint_type, hints["path"]))
```

| Tool | Error Condition | Hint Type |
|------|----------------|-----------|
| `cluster_submit` | CWD path doesn't exist on cluster | `path` |
| `cluster_submit` | SSH connection fails (rc=255) | `connection` |
| `cluster_submit` | No `ssh_target` and no local scheduler | `first_use` |
| `cluster_logs` | Log file not found (local or SSH) | `path` |
| `cluster_logs` | SSH fails while reading logs | `connection` |
| `cluster_status` | Job status command fails | `connection` |

Updated `_error_response()`:

```python
def _error_response(message: str, hint: str | None = None) -> dict:
    result = {"type": "text", "text": f"Error: {message}"}
    if hint:
        result["text"] += f"\n\nHint: {hint}"
    return result
```

### 7.3 Proactive Onboarding Detection

Every cluster tool call starts with `_check_config_readiness()` — an O(1) check (config dict lookups + `shutil.which()`, no SSH) that returns a three-state readiness signal embedded in the tool response as a `setup_needed` field:

| State | Condition | Response Behavior | Model Action |
|-------|-----------|-------------------|--------------|
| `needs_setup` | No `ssh_target` AND no local scheduler | **Blocks** — does not attempt operation. Returns `setup_needed: "run cluster_setup workflow"` | **Automatically** invoke the `cluster_setup` workflow. Do not ask. |
| `incomplete` | Has `ssh_target` but no `path_map` | **Proceeds** — operation runs, response includes warning. Returns `setup_needed: "run cluster_setup workflow"` | **Ask** user if they want to run the `cluster_setup` workflow. Proceed if declined. |
| `ready` | Config sufficient | Normal response, no extra fields | Proceed normally. |

---

## 8. Onboarding Workflow

### 8.1 Overview

A **claudechic workflow** (`.claude/workflows/cluster_setup.md`) — NOT an MCP tool. The model executes detection and validation by calling existing MCP tools (`_run_ssh`, filesystem reads) and shell commands directly. No separate `_cluster_setup.py` helper module is needed.

**State:** Workflow state (SSH target, detected scheduler, proposed config, validation results, etc.) lives in the model's conversation context, not a Python state object. Each phase's structured results are carried forward in the conversation as the model advances through the pipeline.

### 8.2 Workflow Structure

The workflow markdown defines 7 phases with advancement checks. The model interprets probe results, explains them in plain language, and asks the user to confirm before writing. Config is validated before writing — the model refuses to apply if validation has not passed.

- **Phases 1-6 are read-only** — probe, detect, propose, but never modify config files
- **Phase 7 (`apply`)** is the only phase that writes. Requires all validation checks to have passed. The model previews the diff first and writes only on user confirmation.
- **`diagnose`** — meta-phase that runs phases 1-5 in sequence. Safe, read-only entry point.
- The model asks clarifying questions and passes user overrides (e.g., SSH target hostname) into each phase's detection logic

### 8.3 Onboarding Phases

#### Phase 0: Diagnose (`phase="diagnose"`)

Runs phases 1-5 in sequence, returns combined results. Completely read-only. Recommended entry point for both initial setup and troubleshooting.

Output: `{phases: {detect: {...}, ssh_auth: {...}, ...}, summary: {ready_phases: [...], action_needed: [...], skipped: [...]}}`

#### Phase 1: SSH Target (`phase="detect"`)

| Aspect | Detail |
|--------|--------|
| **Probe** | Check `ssh_target` in YAML. If set, test DNS/reachability. Detect OS via `platform.system()`. |
| **Skip if** | Local scheduler found (`shutil.which("bsub")` or `shutil.which("sbatch")`). Returns `{status: "skipped", local_scheduler: true}`. |
| **`answers`** | `{"ssh_target": "login1.example.com"}` |
| **Output** | `{status: "configured" | "missing" | "unreachable" | "skipped", ssh_target, local_scheduler, os_platform}` |

#### Phase 2: Passwordless SSH (`phase="ssh_auth"`)

| Aspect | Detail |
|--------|--------|
| **Probe** | `ssh -o BatchMode=yes -o ConnectTimeout=5 <target> echo ok` |
| **Auto-fixable?** | **No.** Returns step-by-step instructions (`ssh-keygen`, `ssh-copy-id`, test command). |
| **Skip if** | No `ssh_target` in state. |
| **Output** | `{status: "working" | "auth_failed" | "timeout" | "skipped", instructions, can_auto_fix: false}` |

#### Phase 3: SSH Multiplexing (`phase="ssh_mux"`)

| Aspect | Detail |
|--------|--------|
| **Probe** | Check `~/.ssh/sockets/` exists with mode `0o700`. |
| **Auto-fixable?** | **Yes.** `os.makedirs("~/.ssh/sockets", mode=0o700, exist_ok=True)`. |
| **Skip if** | No `ssh_target` in state. |
| **Output** | `{status: "working" | "dir_missing" | "dir_wrong_perms" | "skipped", can_auto_fix: true}` |

#### Phase 4: Scheduler Detection (`phase="scheduler"`)

| Aspect | Detail |
|--------|--------|
| **Probe** | Local: `shutil.which("bsub")`, `shutil.which("sbatch")`. Remote: `ssh <target> 'which bsub sbatch'`. Also tests basic command (`bjobs`/`squeue`). |
| **Skip if** | Never — always runs. |
| **Output** | `{status: "detected" | "not_found" | "both_found" | "detected_but_broken", scheduler: "lsf" | "slurm" | null, detection_method}` |

#### Phase 5: Paths — Combined (`phase="paths"`)

Bundles `path_map`, `remote_cwd`, and `log_access` (they depend on each other).

| Sub-step | Probe |
|----------|-------|
| Mount scan | Parse `/proc/mounts` (Linux), `mount` (macOS), `net use` (Windows). Filter NFS/SMB/CIFS. |
| Remote home | `ssh <target> 'echo $HOME'` |
| CWD check | `ssh <target> "test -d <translated_cwd>"` |
| Path map proposal | Compare local mounts with `ssh <target> df -h`. Match overlapping paths. |
| remote_cwd proposal | If CWD doesn't exist on cluster after translation, propose `remote_cwd` = remote home. |
| log_access proposal | Mounts found -> `auto`. No mounts -> `ssh`. Local scheduler -> `local`. |

**`answers` overrides:** `{"path_map": [...], "remote_cwd": "...", "log_access": "ssh"}`

**Output:** `{status, mounts_detected, cluster_home, proposed_path_map, proposed_remote_cwd, proposed_log_access, confidence}`

#### Phase 6: Validation (`phase="validate"`)

Validates the **assembled in-memory config** (not yet written). This is the gate before `apply`.

| Check | How | `fix_phase` on failure |
|-------|-----|------------------------|
| SSH connectivity | `ssh <target> echo ok` | `detect` or `ssh_auth` |
| Scheduler command | `bjobs 2>&1` or `squeue` via SSH | `scheduler` |
| Path round-trip | local -> cluster -> local must match | `paths` |
| File visibility | Create test file on cluster, read via proposed `log_access` | `paths` |
| Cleanup | Remove test file (best-effort, non-fatal) | -- |

If **passed**: the model records that validation passed in the conversation context and may proceed to apply.
If **failed**: each failed check includes `fix_phase` — the model loops back to that phase, then re-validates.

**Output:** `{status: "passed" | "failed", validation_passed, checks: {...}, failed_checks: [...], assembled_config}`

#### Phase 7: Preview + Write Config (`phase="apply"`)

1. **Preview** (`dry_run=true`, default): Shows diff of proposed changes. Does NOT require `validation_passed`.
2. **Apply** (`dry_run=false`): Writes to YAML. **Rejects if `validation_passed != true`** — returns `{status: "rejected", reason: "..."}`.

Config merge: `{**existing, **updates}` — updates win, existing unmentioned keys preserved. Single atomic `yaml.safe_dump()` call.

---

## 9. TDD Test Plan

All tests live in **one file**: `tests/test_cluster_path_mapping.py`. Each test is a single function testing ONE concept, parameterized to cover multiple environments. Mock `os.getcwd()`, `subprocess.run`, and filesystem access where needed.

**Total: 13 test functions x ~5-8 parameter sets each = ~80 actual test cases, but only 13 functions to review.**

### 9.1 Shared Environment Constants

Named variables defined at the top of the test file. Reused across tests for consistency and readability:

```python
# --- Reusable environment definitions ---
SMB_MAC = {"local": "/Volumes/groups", "cluster": "/groups"}
WINDOWS_DRIVE = {"local": "Z:\\groups", "cluster": "/groups"}
WSL_MOUNT = {"local": "/mnt/cluster/groups", "cluster": "/groups"}
UNC_PATH = {"local": "//smb-server/groups", "cluster": "/groups"}
DIRECT_CLUSTER = {}  # no mapping needed
MULTI_MOUNT = [
    {"local": "/mnt/projects", "cluster": "/groups/projects"},
    {"local": "/mnt/scratch", "cluster": "/scratch"},
]
OVERLAP_RULES = [
    {"local": "/mnt/cluster", "cluster": "/"},
    {"local": "/mnt/cluster/groups", "cluster": "/groups"},
]
```

### 9.2 Test Functions

#### Test 1: `test_path_translates_local_to_cluster`

```python
def test_path_translates_local_to_cluster(...):
    """Local-to-cluster translation via PathMapper.to_cluster()."""
```

**Parameterized inputs:**

| Input | Path | Expected | Why |
|-------|------|----------|-----|
| `SMB_MAC` | `/Volumes/groups/lab/script.sh` | `/groups/lab/script.sh` | Mac SMB mount prefix replacement |
| `WINDOWS_DRIVE` | `Z:\groups\lab\run.py` | `/groups/lab/run.py` | Backslashes normalized to forward slashes |
| `WSL_MOUNT` | `/mnt/cluster/groups/spruston/project` | `/groups/spruston/project` | WSL mount prefix replacement |
| `UNC_PATH` | `//smb-server/groups/lab/data` | `/groups/lab/data` | UNC path prefix replacement |
| `SMB_MAC` | `/tmp/scratch/data` | `/tmp/scratch/data` | No matching rule -> passthrough |
| `OVERLAP_RULES` | `/mnt/cluster/groups/spruston/file.py` | `/groups/spruston/file.py` | Longest local prefix wins |
| Single rule | `/mnt/clusterX/foo` | `/mnt/clusterX/foo` | Similar prefix does NOT false-match |
| Trailing `/` | `/Volumes/groups/lab/data` | `/groups/lab/data` | Trailing slash in config still works |

**Assertion:** `mapper.to_cluster(input_path) == expected`

#### Test 2: `test_path_translates_cluster_to_local`

```python
def test_path_translates_cluster_to_local(...):
    """Cluster-to-local translation via PathMapper.to_local()."""
```

**Parameterized inputs:**

| Input | Path | Expected | Why |
|-------|------|----------|-----|
| `SMB_MAC` | `/groups/lab/logs/out.log` | `/Volumes/groups/lab/logs/out.log` | Reverse of Test 1 |
| `WINDOWS_DRIVE` | `/groups/lab/out.log` | `Z:/groups/lab/out.log` | Forward slashes returned (A34) |
| `WSL_MOUNT` | `/groups/spruston/logs/out.log` | `/mnt/cluster/groups/spruston/logs/out.log` | WSL reverse |
| `SMB_MAC` | `/tmp/scratch/data` | `/tmp/scratch/data` | No match -> passthrough |
| `[]` | `/groups/lab/out.log` | `/groups/lab/out.log` | Empty rules -> passthrough |
| `None` | `/groups/lab/out.log` | `/groups/lab/out.log` | None rules -> passthrough |
| `OVERLAP_RULES` | `/groups/spruston/deep/file.py` | `/mnt/cluster/groups/spruston/deep/file.py` | Longest cluster prefix wins |

**Assertion:** `mapper.to_local(input_path) == expected`

#### Test 3: `test_cwd_resolves_correctly`

```python
def test_cwd_resolves_correctly(..., monkeypatch):
    """_resolve_cwd() priority: remote_cwd > translated CWD > raw os.getcwd()."""
```

**Parameterized inputs:**

| remote_cwd | local CWD (mocked) | Rule | Expected | Why |
|------------|---------------------|------|----------|-----|
| `/groups/lab/project` | `/Volumes/groups/lab/project` | `SMB_MAC` | `/groups/lab/project` | remote_cwd wins over translation |
| `""` | `/Volumes/groups/lab/project` | `SMB_MAC` | `/groups/lab/project` | Translates local CWD via path_map |
| `""` | `/home/user/project` | `DIRECT_CLUSTER` | `/home/user/project` | No config -> passthrough |
| `""` | `/groups/lab/project` | `DIRECT_CLUSTER` | `/groups/lab/project` | Direct cluster -> verbatim |
| `""` | `Z:\groups\lab\project` | `WINDOWS_DRIVE` | `/groups/lab/project` | Windows CWD normalized |
| (has `cd` in command) | any | any | (CWD flag still set) | Command already has cd -> flag still added |

**Assertion:** `_resolve_cwd(config, mapper) == expected`

#### Test 4: `test_log_reading_works`

```python
def test_log_reading_works(...):
    """LogReader strategy selects correct transport and handles failures gracefully."""
```

**Parameterized inputs:**

| log_access | mount_works | ssh_works | Expected Source | Why |
|------------|-------------|-----------|-----------------|-----|
| `"local"` | True | -- | local | Local mount read succeeds |
| `"ssh"` | -- | True | ssh | SSH read |
| `"auto"` | True | True | local | Auto: local succeeds, SSH not attempted |
| `"auto"` | False | True | ssh | Auto: local fails, SSH fallback |
| `"auto"` | False | False | None | Auto: both fail -> `found: false` |
| `"ssh"` | -- | False | None | SSH failure -> graceful None |

**Assertion:** Correct reader invoked; content or None returned; no crash on failure.

#### Test 5: `test_submit_uses_correct_paths`

```python
def test_submit_uses_correct_paths(..., monkeypatch):
    """Submit builds correct CWD flag per scheduler x environment combination."""
```

**Parameterized inputs:**

| Scheduler | Rule | CWD | remote_cwd | Expected Flag |
|-----------|------|-----|------------|---------------|
| LSF | `SMB_MAC` | `/Volumes/groups/lab/project` | `""` | `-cwd '/groups/lab/project'` |
| LSF | `DIRECT_CLUSTER` | -- | `/groups/lab/project` | `-cwd '/groups/lab/project'` |
| SLURM | `SMB_MAC` | `/Volumes/groups/lab/project` | `""` | `--chdir='/groups/lab/project'` |
| SLURM | `WINDOWS_DRIVE` | `Z:\groups\lab\project` | `""` | `--chdir='/groups/lab/project'` |
| SLURM | `DIRECT_CLUSTER` | `/groups/lab/project` | `""` | `--chdir='/groups/lab/project'` |
| LSF | `DIRECT_CLUSTER` | `/groups/lab/project` | `""` | `-cwd '/groups/lab/project'` |

**Assertion:** Mock SSH; verify bsub/sbatch command string includes expected flag; user's command string is unmodified.

#### Test 6: `test_status_returns_local_paths`

```python
def test_status_returns_local_paths(...):
    """Status response paths are translated to local filesystem for model display."""
```

**Parameterized inputs:**

| Rules | Cluster Paths | Expected Local Paths | Why |
|-------|---------------|----------------------|-----|
| `[SMB_MAC]` | stdout: `/groups/lab/out.log`, cwd: `/groups/lab/project` | stdout: `/Volumes/groups/...`, cwd: `/Volumes/groups/...` | Mac SMB |
| `[]` | stdout: `/groups/lab/out.log` | stdout: `/groups/lab/out.log` | SSH-only passthrough |
| `[WINDOWS_DRIVE]` | stdout: `/groups/lab/out.log` | stdout: `Z:/groups/lab/out.log` | Windows forward slashes |
| `MULTI_MOUNT` | stdout on `/groups/projects/...`, stderr on `/scratch/...` | Each maps to correct mount | Multi-mount routing |

**Assertion:** `mapper.to_local(cluster_val) == expected_local[key]`

#### Test 7: `test_config_loads_correctly`

```python
def test_config_loads_correctly(...):
    """Config parsing succeeds with valid input or fails with clear errors."""
```

**Parameterized inputs:**

| Config | Expected | Why |
|--------|----------|-----|
| Full valid (path_map + log_access + remote_cwd) | OK | Happy path |
| `{}` | OK | Empty config -> safe defaults |
| `{"ssh_target": "..."}` (no path_map key) | OK | Missing key defaults to empty |
| path_map entry missing `local` | `ValueError` | Clear error mentioning "local" |
| path_map entry missing `cluster` | `ValueError` | Clear error mentioning "cluster" |
| `local: ""` | `ValueError` | Empty prefix would match everything |
| `cluster: ""` | `ValueError` | Empty prefix would match everything |
| `log_access: "ftp"` | `ValueError` | Lists valid options |
| `path_map: "/mnt:/groups"` (string) | `TypeError` | Wrong type, clear message |

**Assertion:** `_create_path_mapper(config)` succeeds or `pytest.raises(expected_error)`.

#### Test 8: `test_shell_injection_prevented`

```python
def test_shell_injection_prevented(...):
    """shlex.quote() neutralizes all shell metacharacters in paths."""
```

**Parameterized inputs:** paths containing spaces, `$HOME`, backticks, single quotes, `$(whoami)`.

**Assertion:** `shlex.quote(path)` produces a safe string; SSHLogReader embeds quoted path in SSH command.

#### Test 9: `test_defaults_passthrough`

```python
def test_defaults_passthrough(..., monkeypatch):
    """Configs without new keys use safe defaults — all paths pass through unchanged."""
```

**Parameterized inputs:**

| Config | Why |
|--------|-----|
| `{"ssh_target": "login1.org"}` | No new keys at all |
| `{"ssh_target": "login1.org", "path_map": []}` | Explicit empty path_map |
| `{"ssh_target": "login1.org"}` | No log_access -> defaults to auto |
| `{}` | Completely empty config |

**Assertions:** `to_cluster()` and `to_local()` pass through unchanged; `_resolve_cwd()` returns `os.getcwd()` as-is.

#### Test 10: `test_model_sees_correct_descriptions`

```python
def test_model_sees_correct_descriptions(...):
    """Tool descriptions inform the model about path mapping, log transport, and setup."""
```

**Parameterized inputs:**

| Tool | Must Contain | Why |
|------|-------------|-----|
| `cluster_submit` | `"path_map"` | Model knows paths are translated |
| `cluster_submit` | `"remote_cwd"` | Model knows about remote CWD override |
| `cluster_submit` | `"setup_needed"` | Model knows to check for setup |
| `cluster_submit` | `"NOT automatically translated"` | Model warned about command-string paths |
| `cluster_logs` | `"log_access"` | Model knows about log transport config |
| `cluster_logs` | `"SSH"` | Model knows about SSH fallback |
| `cluster_status` | `"local paths"` | Model knows response paths are local |
| `cluster_setup` | `"diagnose"` | Model knows the entry point phase |

**Assertion:** `must_contain.lower() in tool.description.lower()`

#### Test 11: `test_onboarding_detect_phase`

```python
def test_onboarding_detect_phase(...):
    """Detect phase identifies SSH target and OS environment correctly."""
```

**Parameterized inputs:**

| OS | ssh_target | Local Scheduler | Expected Status | Why |
|----|------------|-----------------|-----------------|-----|
| macOS | `"login1.org"` | No | `"configured"` | Target set and reachable |
| Windows | `""` | No | `"missing"` | No target configured |
| Linux | `"bad-host.org"` | No | `"unreachable"` | DNS/connection fails |
| Linux | `""` | Yes | `"skipped"` | Local scheduler found, SSH not needed |
| macOS | `""` (answer override) | No | `"configured"` | Model provides target via answers dict |

**Assertion:** `result["status"] == expected_status`

#### Test 12: `test_onboarding_validate_phase`

```python
def test_onboarding_validate_phase(...):
    """Validation gates apply and points to the correct fix_phase on failure."""
```

**Parameterized inputs:**

| SSH | Scheduler | Path Round-trip | File Visibility | Expected Status | fix_phase |
|-----|-----------|-----------------|-----------------|-----------------|-----------|
| Pass | Pass | Pass | Pass | `"passed"` | -- |
| Fail | Pass | Pass | Pass | `"failed"` | `"detect"` |
| Pass | Pass | Fail | Pass | `"failed"` | `"paths"` |
| Pass | Fail | Pass | Pass | `"failed"` | `"scheduler"` |
| Pass | Pass | Pass | Fail | `"failed"` | `"paths"` |

**Assertion:** `result["status"] == expected`; failed checks include correct `fix_phase`.

#### Test 13: `test_onboarding_apply_phase`

```python
def test_onboarding_apply_phase(..., tmp_path):
    """Apply writes only after validation; dry_run previews safely without writing."""
```

**Parameterized inputs:**

| dry_run | validation_passed | Expected Status | Why |
|---------|-------------------|-----------------|-----|
| True | False | `"preview"` | Dry run always allowed |
| True | True | `"preview"` | Dry run with validation |
| False | True | `"written"` | Apply succeeds after validation |
| False | False | `"rejected"` | Apply blocked without validation |

**Assertions:** Status matches; `"written"` -> YAML file exists on disk; `"rejected"` -> no file written.

### 9.3 Scenario Coverage Matrix

| User Environment | Test 1 (L->C) | Test 2 (C->L) | Test 3 (CWD) | Test 4 (Logs) | Test 5 (Submit) | Test 6 (Status) | Test 7 (Config) | Test 8 (Inject) | Test 9 (Defaults) |
|---|---|---|---|---|---|---|---|---|---|
| **Mac + SMB** | yes | yes | yes | local_mount | lsf, slurm | yes | full_valid | all | -- |
| **Windows** | yes | yes (fwd slash) | yes | -- | slurm | yes (fwd slash) | -- | all | -- |
| **WSL** | yes | yes | -- | -- | -- | -- | -- | all | -- |
| **UNC/SMB** | yes | -- | -- | -- | -- | -- | -- | -- | -- |
| **SSH-only** | -- | -- | remote_cwd | ssh, fallback | lsf | passthrough | -- | all | -- |
| **Direct cluster** | passthrough | passthrough | passthrough | -- | lsf, slurm | -- | empty | -- | all |
| **Multi-mount** | overlap | overlap | -- | -- | -- | multi_mount | -- | -- | -- |
| **Misconfiguration** | -- | -- | -- | -- | -- | -- | all error cases | -- | -- |
| **Onboarding** | -- | -- | -- | -- | -- | -- | -- | -- | -- |

Onboarding tests (11-13) cover: macOS/Windows/WSL/on-cluster detect, validation pass/fail with fix phases, apply gate with dry_run.

### 9.4 Test File Summary

| File | Tests | Parameter Sets | Actual Cases |
|------|-------|----------------|--------------|
| `tests/test_cluster_path_mapping.py` | 13 functions | ~5-8 each | ~80 total |

---

## 10. Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `mcp_tools/_cluster.py` | **Modify** | Add `PathMapper` class (with two sorted rule lists), `_normalize_local_path()`, `_normalize_cluster_path()`, `_resolve_cwd()`, `_create_path_mapper()`. Add `LogReader` protocol, `LocalLogReader`, `SSHLogReader`, `AutoLogReader` classes, `_create_log_reader()` factory (accepts explicit `profile` parameter). Update `_resolve_log_path()` to return `str`, use `startswith("/")` instead of `os.path.isabs()`, remove env var expansion. Update `_read_logs()` to require `LogReader` parameter (no default). Add `_error_with_hint()`, `_check_config_readiness()`. Update `_error_response()` to accept optional `hint` parameter and `setup_needed` field. Add `import shlex, shutil`. |
| `.claude/workflows/cluster_setup.md` | **New** | Claudechic workflow definition — pure prompt orchestration with 7 phases, advancement checks, and inline detection/validation logic. Model calls existing tools + SSH directly. No separate Python helper module. |
| `mcp_tools/lsf.py` | **Modify** | Import `_create_path_mapper`, `_resolve_cwd`, `_create_log_reader`. Create `PathMapper` and `LogReader` lazily in each tool handler (not at `get_tools()` time). Remove `cd` injection from command string; add `-cwd` flag via `_resolve_cwd()`. Translate `stdout_path`/`stderr_path` in `_submit_job()`. Conditionally `mkdir` based on `log_access`. Pass `LogReader` and `PathMapper` to `_read_logs()`. Translate status response paths. Update `@tool()` descriptions (include `setup_needed` workflow trigger). Pass `config.get("lsf_profile")` to `_create_log_reader()`. |
| `mcp_tools/slurm.py` | **Modify** | Same as `lsf.py` but with `--chdir` flag instead of `-cwd`. Additionally: **add CWD handling** in `_submit_job()` (currently absent entirely). Pass `profile=None` to `_create_log_reader()`. |
| `mcp_tools/lsf.yaml.jinja` | **Modify** | Add `remote_cwd`, `path_map`, and `log_access` config keys with comments. |
| `mcp_tools/slurm.yaml.jinja` | **Modify** | Add `remote_cwd`, `path_map`, and `log_access` config keys with comments. |
| `tests/test_cluster_path_mapping.py` | **New** | All 13 parameterized test functions (~80 test cases): path translation both directions, CWD resolution, log reading, submit integration, status display, config loading, shell injection, default passthrough, model descriptions, onboarding detect/validate/apply. Shared named environment constants (`SMB_MAC`, `WINDOWS_DRIVE`, `WSL_MOUNT`, etc.) at the top for reuse. |

### Dependency Changes

- **New stdlib imports:** `shlex`, `shutil` (in `_cluster.py`) — no new third-party dependencies.
- `typing.Protocol` used for `LogReader` — available in Python 3.8+ via `typing` or `typing_extensions`.

See [SPECIFICATION_APPENDIX.md](SPECIFICATION_APPENDIX.md) for decision log, risk detail, migration notes, implementation reference, conversation examples, and deployment notes.
