# Specification: cluster_path_mapping

**Status:** Draft v10 — FRESH START
**Date:** 2026-04-09

**Previous versions:** See `SPECIFICATION_v9_archive.md` and `SPECIFICATION_APPENDIX.md` for full history, decision log, and prior code samples.

---

## Scope

This spec defines WHAT we are building and WHY. Implementation details (code, exact function signatures) are for the implementer. Test details (exact parameterization) are for the test engineer.

---

## 1. Problem

The cluster MCP tools assume:
1. Local and cluster filesystem paths are identical
2. Log files are locally accessible via the same path
3. The user's CWD exists on the cluster

These assumptions break for users on SMB mounts, Windows, WSL, or SSH-only environments.

## 2. Terminology

| Term | Definition |
|------|-----------|
| **local path** | Filesystem path as seen by the MCP client (Claude Code). May be POSIX, Windows, UNC/SMB. |
| **cluster path** | Filesystem path as seen by cluster login/compute nodes. Always POSIX. |
| **execution_cwd** | Per-job cluster path where the job actually ran (from scheduler metadata). Not user-configurable. |
| **claudechic workflow** | A markdown-defined workflow (`.claude/workflows/`) that the model executes conversationally, advancing through phases via structured checks. State lives in the conversation context. |

## 3. Solution — Three Components

### 3.1 PathMapper — Bidirectional Path Translation

A shared class in `_cluster.py` that translates paths between local and cluster filesystems using prefix-replacement rules from config.

**Behavior:**
- `to_cluster(local_path)` → cluster path (longest local prefix match wins)
- `to_local(cluster_path)` → local path (longest cluster prefix match wins)
- Empty rules = passthrough (paths used as-is)
- **Pre-processing (before matching):** Local paths get `~` expansion, env var expansion, backslash→`/` conversion. Cluster paths get trailing-slash stripping only (no env var expansion — local `$HOME` != cluster `$HOME`).
- All returned paths use forward slashes (Windows APIs accept them)
- **Prefix boundary rule:** A prefix matches only if `path == prefix` or `path.startswith(prefix + "/")`. Bare `startswith()` is NOT sufficient — it would cause `/mnt/cluster` to falsely match `/mnt/cluster-backup`. (Note: the v9 archive code uses bare `startswith()` — implementers must NOT copy that pattern.)

### 3.2 LogReader — Strategy Pattern for Log Access

A strategy pattern in `_cluster.py` that separates HOW logs are read from WHERE they are.

**Three strategies:**
- `LocalLogReader` — reads from mounted filesystem, uses PathMapper to translate cluster→local
- `SSHLogReader` — reads via SSH (`tail -n` / `cat`), uses cluster path directly
- `AutoLogReader` — tries local first, falls back to SSH

**Configured by:** `log_access` config key (`auto` | `local` | `ssh`)

### 3.3 cluster_setup — Onboarding Workflow

A **claudechic workflow** (not an MCP tool) that guides new users through cluster configuration. The workflow is pure prompt orchestration — the model executes detection and validation by calling existing MCP tools (`_run_ssh`, filesystem reads) and shell commands directly. No separate `_cluster_setup.py` helper module is needed.

**State:** Workflow state (SSH target, detected scheduler, proposed config, etc.) lives in the model's conversation context, not a Python state object. Each phase's structured results are carried forward in the conversation.

**Phases:**
1. **detect** — Identify SSH target, detect OS, check for local scheduler
2. **ssh_auth** — Verify passwordless SSH works; provide instructions if not
3. **ssh_mux** — Check/create SSH multiplexing socket directory
4. **scheduler** — Detect LSF or SLURM (local or remote)
5. **paths** — Scan mounts, propose `path_map`, `remote_cwd`, `log_access`
6. **validate** — Test assembled config (SSH, scheduler cmd, path round-trip, file visibility)
7. **apply** — Preview diff, write config on user confirmation

**Phase advancement checks:** Each phase returns structured results. The workflow advances only when the check for that phase passes (e.g., SSH auth confirmed working, scheduler detected, paths validated). Failed checks loop back with guidance.

**Proactive triggering:** `_check_config_readiness()` (see §5) returns a `setup_needed` field in tool error/warning responses. The field value includes the workflow name (e.g., `"run cluster_setup workflow"`), and tool descriptions instruct the model to invoke the workflow when this field is present.

## 4. Config Schema

### New keys (added to both `lsf.yaml.jinja` and `slurm.yaml.jinja`):

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `remote_cwd` | `str` | `""` | Cluster-side CWD for jobs. Empty = auto-translate `os.getcwd()` via path_map. |
| `path_map` | `list[{local, cluster}]` | `[]` | Ordered prefix-replacement rules. Empty = passthrough. |
| `log_access` | `str` | `"auto"` | How to read log files: `auto`, `local`, or `ssh`. |

Empty config = passthrough (paths used as-is). Existing configs without the new keys work unchanged (passthrough defaults). No guarantee that the new key schema will be preserved across future versions.

## 5. Integration Points

### 5.1 Job Submission CWD
- Use `_resolve_cwd()`: returns `remote_cwd` if set, else `path_mapper.to_cluster(os.getcwd())`
- Pass via scheduler's native flag: `bsub -cwd` (LSF), `sbatch --chdir` (SLURM)
- Do NOT inject `cd` into the command string (existing `cd {os.getcwd()}` injection is removed)

### 5.2 Log Path Handling
- Relative log paths resolved against `execution_cwd` on the cluster filesystem
- Use `startswith("/")` for absolute detection (not `os.path.isabs()` — fails on Windows for POSIX paths)
- LogReader handles transport; PathMapper handles filesystem translation

### 5.3 Status Response Paths
- Translate cluster paths to local paths in status responses (`stdout_path`, `stderr_path`, `execution_cwd`)

### 5.4 Submit Log Paths
- Translate user-provided `stdout_path`/`stderr_path` from local→cluster for scheduler
- Skip local `mkdir` when `log_access: ssh` (no shared filesystem)

### 5.5 Lazy Construction
- PathMapper and LogReader created inside each tool handler call (not at `get_tools()` time) so config changes are picked up immediately

## 6. Model Awareness

- Tool descriptions mention `path_map`, `remote_cwd`, `log_access`, and `setup_needed`
- Tool descriptions warn that paths inside the user's command string are NOT auto-translated
- Tool descriptions instruct the model: "if the response contains `setup_needed`, invoke the `cluster_setup` workflow"
- Error responses include `setup_needed` field with explicit workflow name
- Proactive detection: `_check_config_readiness()` returns `needs_setup` | `incomplete` | `ready`. This check is O(1) — config dict reads and `shutil.which()` only; no SSH, no filesystem probes. Safe to run on every tool call.

## 7. Risks

| Risk | Mitigation |
|------|------------|
| Shell injection via paths | `shlex.quote()` on all paths in scheduler flags and SSH commands |
| Prefix boundary false match | `/`-boundary checking in prefix matching |
| Case sensitivity (Win/Mac vs Linux) | Known limitation — all matching is case-sensitive. Document. |
| Env var expansion on cluster paths | Separate normalizers: local gets full expansion, cluster gets none |
| `os.path.isabs()` on Windows | Use `startswith("/")` for cluster paths |
| Config hot-reload after setup | Lazy construction per tool call |
| Path traversal via malicious `path_map` | Intentionally omitted — trust boundary is user-controlled YAML config |

## 8. Test Plan — Behavioral Acceptance Criteria

Tests verify behavior, not implementation. One test file: `tests/test_cluster_path_mapping.py`.

**What to test (the implementer/test engineer decides HOW):**

1. **Path translation** — local→cluster and cluster→local for: SMB Mac, Windows drive, WSL, UNC, passthrough, overlapping rules, prefix boundary safety
2. **CWD resolution** — priority order (remote_cwd > translated CWD > raw CWD), Windows normalization
3. **Log reading** — correct strategy selected per `log_access`, graceful fallback in auto mode, graceful failure
4. **Submit integration** — correct CWD flag per scheduler, paths translated, command string untouched
5. **Status paths** — cluster→local translation in responses
6. **Config validation** — valid configs load, invalid configs fail with clear errors
7. **Shell injection** — metacharacters in paths are neutralized
8. **Model descriptions** — tool descriptions contain key terms
9. **Onboarding phases** — detect identifies environment, validate gates apply, apply writes only after validation

**Environment constants** for parameterization: `SMB_MAC`, `WINDOWS_DRIVE`, `WSL_MOUNT`, `UNC_PATH`, `DIRECT_CLUSTER`, `MULTI_MOUNT`, `OVERLAP_RULES` — defined as named dicts at top of test file.

## 9. Files Changed

| File | Change |
|------|--------|
| `mcp_tools/_cluster.py` | Add PathMapper, normalizers, _resolve_cwd, LogReader protocol + 3 implementations, factories, error hints, readiness check |
| `mcp_tools/lsf.py` | Use PathMapper/LogReader, replace `cd` injection with `-cwd` flag, translate paths, lazy construction, update tool descriptions |
| `mcp_tools/slurm.py` | Same as lsf.py but `--chdir` flag, add CWD handling (currently missing) |
| `mcp_tools/lsf.yaml.jinja` | Add `remote_cwd`, `path_map`, `log_access` keys |
| `mcp_tools/slurm.yaml.jinja` | Add `remote_cwd`, `path_map`, `log_access` keys |
| `.claude/workflows/cluster_setup.md` | New workflow definition — pure prompt orchestration with phases, advancement checks, and inline detection/validation logic (no separate Python helper module) |
| `tests/test_cluster_path_mapping.py` | New test file with parameterized behavioral tests |

No new third-party dependencies (stdlib only: `shlex`, `shutil`, `platform`).
