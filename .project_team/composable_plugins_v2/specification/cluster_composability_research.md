# Research Report: Cluster MCP Composability — LSF + SLURM

**Requested by:** Coordinator
**Date:** 2026-03-30
**Tier of best source found:** T1 (direct source code analysis of cluster.py; official SLURM, dask-jobqueue, Nextflow, Snakemake docs)

## Query

How do we make the cluster MCP tools composable across scheduler backends (LSF, SLURM), and what architecture options exist?

---

## 1. Source Code Analysis: Current cluster.py

The file is **776 lines** at `/groups/spruston/home/moharb/DECODE-PRISM/Repos/claudechic/claudechic/cluster.py`.

### Structural Breakdown

| Section | Lines | LSF-Specific? | Description |
|---------|-------|---------------|-------------|
| **Config helpers** | 52–79 (~28 lines) | 🟡 Partially | `_get_ssh_target()`, `_get_lsf_profile()`, `_get_conda_envs_dirs()`, `_get_watch_poll_interval()`. SSH target and conda dirs are generic; `_get_lsf_profile()` is LSF-only |
| **SSH/exec layer** | 87–141 (~55 lines) | 🟡 Partially | `_lsf_available()` checks for `bsub`; `_run_lsf()` wraps SSH+profile sourcing. The SSH multiplexing logic is 100% reusable. The LSF profile sourcing is not |
| **bjobs parsers** | 149–271 (~123 lines) | 🔴 Fully LSF | `_parse_bjobs_wide()`, `_collapse_lsf_lines()`, `_parse_bjobs_detail()`. These parse LSF-specific output formats with regex |
| **Core operations** | 279–406 (~128 lines) | 🔴 Mostly LSF | `_list_jobs()`, `_get_job_status()`, `_submit_job()`, `_kill_job()`. Job submission builds `bsub` command with LSF flags. Contains generic logic mixed in: conda-run injection, log dir creation, CWD injection |
| **Log reading** | 408–483 (~76 lines) | 🟢 Generic | `_resolve_log_path()`, `_read_tail()`, `_get_job_logs()`. Resolves paths from bjobs output (which is LSF-specific) but the file reading is generic |
| **Watch mechanism** | 491–575 (~85 lines) | 🟡 Partially | `_watch_lsf_exit()` polls via `_get_job_status()`. `_run_watch()` dispatches conditions and notifies agents — 90% generic |
| **MCP response helpers** | 583–600 (~18 lines) | 🟢 Generic | `_text_response()`, `_json_response()`, `_error_response()` |
| **MCP tool definitions** | 608–776 (~168 lines) | 🟡 Partially | Tool names say "LSF" in descriptions but the tool structure (args, async dispatch, error handling) is generic |

### Summary Count

| Category | Lines | Percentage |
|----------|-------|-----------|
| **Fully generic / reusable** | ~280 | 36% |
| **Partially generic** (needs minor changes) | ~250 | 32% |
| **Fully LSF-specific** (parsers, command builders) | ~246 | 32% |

**Key insight: ~68% of the code is reusable or needs only minor changes.** The LSF-specific parts are concentrated in two areas: **output parsing** and **command building**.

---

## 2. LSF → SLURM Command Mapping

### Direct Command Equivalents

| Operation | LSF | SLURM | Notes |
|-----------|-----|-------|-------|
| List jobs | `bjobs -w` | `squeue -u $USER --format="%i %u %T %P %B %R %j %V"` | SLURM has `--format` for custom output |
| Job detail | `bjobs -l <id>` | `scontrol show job <id>` | Very different output format |
| Job history | (bjobs for recent) | `sacct -j <id> --format=...` | SLURM separates current vs historical |
| Submit | `bsub -q Q -n N -W T cmd` | `sbatch --partition=P --ntasks=N --time=T script.sh` | SLURM prefers script files over inline commands |
| Kill | `bkill <id>` | `scancel <id>` | Direct equivalent |
| Check availability | `which bsub` | `which sbatch` | Same pattern |

### Flag Mapping

| LSF Flag | SLURM Equivalent |
|----------|-----------------|
| `-q queue` | `--partition=partition` or `-p` |
| `-n cpus` | `--ntasks=N` or `--cpus-per-task=N` |
| `-W walltime` (HH:MM format) | `--time=HH:MM:SS` or `--time=minutes` |
| `-J job_name` | `--job-name=name` or `-J` |
| `-o stdout_path` | `--output=path` or `-o` |
| `-e stderr_path` | `--error=path` or `-e` |
| `-gpu 'num=N:mode=exclusive_process'` | `--gres=gpu:N` or `--gpus=N` |

### Key Differences

1. **Submission model:** LSF takes inline commands (`bsub 'cmd'`); SLURM prefers batch scripts (`sbatch script.sh`). But SLURM also supports `sbatch --wrap="cmd"` for inline commands — this is our bridge.

2. **Output parsing:** LSF's `bjobs -l` uses a unique continuation-line format (26-space indent) that requires `_collapse_lsf_lines()`. SLURM's `scontrol show job` uses `Key=Value` pairs (much easier to parse). SLURM's `squeue` supports `--format` for machine-parseable output.

3. **Profile sourcing:** LSF requires `source /misc/lsf/conf/profile.lsf`. SLURM typically needs no profile (just `module load slurm` or it's already in PATH on login nodes).

4. **Terminal statuses:** LSF: DONE, EXIT. SLURM: COMPLETED, FAILED, CANCELLED, TIMEOUT, OUT_OF_MEMORY, NODE_FAIL.

5. **GPU syntax:** Very different between LSF and SLURM.

---

## 3. Architecture Options

### Option A: Two Separate Files (Fully Independent)

```
mcp_tools/
├── cluster_lsf.py       # Full LSF implementation (~400 lines)
├── cluster_slurm.py     # Full SLURM implementation (~400 lines)
```

Each file is standalone. Copier includes one or the other based on `use_cluster_lsf` / `use_cluster_slurm` questions.

| Criterion | Assessment |
|-----------|-----------|
| **Composability** | ✅ Perfect. File presence = enabled. Delete file = disabled. |
| **Swap test** | ✅ Either file can exist independently |
| **Code duplication** | 🔴 ~280 lines duplicated (SSH layer, response helpers, watch mechanism, conda injection, log reading) |
| **Maintenance** | 🔴 Bug fix in shared logic must be applied twice |
| **Copier integration** | ✅ Simple: conditional `{% if use_cluster_lsf %}` / `{% if use_cluster_slurm %}` |
| **User experience** | ✅ User sees only one file, no confusion about "base" classes |

### Option B: One File with Backend Abstraction

```
mcp_tools/
├── cluster.py            # Backend auto-detection + all code (~600 lines)
```

Single file with an internal `ClusterBackend` ABC and `LSFBackend`/`SLURMBackend` classes. Auto-detects which is available (check for `bsub` vs `sbatch`).

| Criterion | Assessment |
|-----------|-----------|
| **Composability** | ⚠️ One file, but which backend is active depends on runtime detection, not file presence |
| **Swap test** | ⚠️ Can't remove a backend without editing the file |
| **Code duplication** | 🟢 None |
| **Maintenance** | 🟢 Single file to maintain |
| **Copier integration** | ⚠️ Copier just includes or excludes the whole file — can't partially include |
| **User experience** | ⚠️ User sees 600 lines with code for a scheduler they don't use |

### Option C: Shared Base + Backend Modules

```
mcp_tools/
├── _cluster_base.py      # SSH layer, response helpers, watch, log reading (~300 lines)
├── cluster_lsf.py        # LSF backend: parsers, command builders, MCP tools (~280 lines)
├── cluster_slurm.py      # SLURM backend: parsers, command builders, MCP tools (~280 lines)
```

Base module provides reusable infrastructure. Backend files import from base and implement scheduler-specific logic. `get_tools()` is only in the backend files.

| Criterion | Assessment |
|-----------|-----------|
| **Composability** | ✅ File presence = enabled. Backend file has `get_tools()` |
| **Swap test** | ✅ Delete `cluster_lsf.py`, keep `cluster_slurm.py` — works |
| **Code duplication** | 🟢 None |
| **Maintenance** | 🟢 Shared logic in one place |
| **Copier integration** | 🟡 Need to handle `_cluster_base.py` — include if ANY cluster backend is selected |
| **User experience** | 🟡 User sees a `_cluster_base.py` they shouldn't edit + their backend file |
| **Follows prior art** | ✅ This is exactly how dask-jobqueue works (core.py + slurm.py + lsf.py) |

### Option D: Config-Driven Single Backend File (Recommended)

```
mcp_tools/
├── cluster.py            # One file, scheduler selected by config (~500 lines)
```

Single `cluster.py` with a `Backend` protocol/ABC. Backend selection via `.claudechic.yaml`:
```yaml
cluster:
  scheduler: lsf          # or "slurm"
  ssh_target: submit.int.janelia.org
  lsf_profile: /misc/lsf/conf/profile.lsf   # LSF-only
  # slurm has no profile equivalent
```

Backend classes are internal to the file. The `get_tools()` function returns the same tool names (`cluster_jobs`, `cluster_submit`, etc.) regardless of backend — the descriptions adapt.

| Criterion | Assessment |
|-----------|-----------|
| **Composability** | ✅ File presence = cluster enabled. Config selects backend. |
| **Swap test** | ✅ Delete `cluster.py` = no cluster. Change config `scheduler: slurm` = swap backend |
| **Code duplication** | 🟢 None |
| **Maintenance** | 🟢 Single file |
| **Copier integration** | ✅ Simple: `use_cluster` bool + `cluster_scheduler` choice (lsf/slurm) → generates config |
| **User experience** | ✅ One file. Config clearly shows which scheduler. Tool names are generic. |
| **Follows prior art** | ✅ Matches Nextflow executor pattern (config selects backend) |

---

## 4. Recommended Architecture: Option D (Config-Driven)

### Why Option D over Option C

- **One fewer file** — the `_cluster_base.py` in Option C is an implementation artifact users shouldn't need to know about
- **Stable tool names** — `cluster_jobs`, `cluster_submit`, `cluster_kill`, `cluster_logs`, `cluster_watch` work regardless of backend. LLM agents don't need to know which scheduler is active
- **Config-driven** aligns with `.claudechic.yaml` as the single config point
- **Copier can set the default** based on a simple question: "Which cluster scheduler? [lsf/slurm/none]"

### Proposed Internal Structure

```python
"""Cluster MCP tools — multi-scheduler support.

Supports LSF (bsub/bjobs/bkill) and SLURM (sbatch/squeue/scancel).
Scheduler backend selected via .claudechic.yaml: cluster.scheduler = "lsf" | "slurm"
"""

# --- Protocol / ABC ---
class ClusterBackend(Protocol):
    """Interface that each scheduler backend must implement."""
    name: str
    def is_available(self) -> bool: ...
    def run_command(self, cmd: str, timeout: int = 60) -> tuple[str, str, int]: ...
    def list_jobs(self) -> list[dict[str, Any]]: ...
    def get_job_status(self, job_id: str) -> dict[str, Any]: ...
    def submit_job(self, queue: str, cpus: int, walltime: str, command: str,
                   job_name: str = "", gpus: int = 0,
                   stdout_path: str = "", stderr_path: str = "") -> dict[str, Any]: ...
    def kill_job(self, job_id: str) -> dict[str, Any]: ...
    def terminal_statuses(self) -> frozenset[str]: ...

# --- Shared Infrastructure (~200 lines) ---
# SSH execution layer (reused by both backends)
# Log file reading (_resolve_log_path, _read_tail, _get_job_logs)
# Conda-run injection, CWD injection, PYTHONUNBUFFERED
# Watch mechanism (_run_watch, condition dispatch)
# MCP response helpers

# --- LSF Backend (~150 lines) ---
class LSFBackend:
    # _parse_bjobs_wide, _collapse_lsf_lines, _parse_bjobs_detail
    # _build_bsub_command
    # terminal_statuses = {"DONE", "EXIT"}

# --- SLURM Backend (~150 lines) ---
class SLURMBackend:
    # _parse_squeue, _parse_scontrol_show_job
    # _build_sbatch_command (using --wrap for inline commands)
    # terminal_statuses = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY"}

# --- Backend Selection ---
def _get_backend() -> ClusterBackend:
    scheduler = _cluster_config().get("scheduler", "lsf")
    if scheduler == "slurm": return SLURMBackend()
    return LSFBackend()  # default

# --- MCP Tool Definitions (~120 lines) ---
# cluster_jobs, cluster_status, cluster_submit, cluster_kill, cluster_logs, cluster_watch
# All use _get_backend() internally — tool names and signatures are scheduler-agnostic
```

### Estimated Line Counts

| Component | Lines |
|-----------|-------|
| Shared infrastructure (SSH, logs, watch, conda helpers) | ~200 |
| LSF backend (parsers + command builder) | ~150 |
| SLURM backend (parsers + command builder) | ~150 |
| MCP tool definitions | ~120 |
| Config/boilerplate | ~30 |
| **Total** | **~650** |

Current `cluster.py` is 776 lines. The refactored version is slightly shorter because shared code is deduplicated and the protocol enforces consistency.

---

## 5. Can a Site Have Both LSF AND SLURM?

**Extremely rare but not impossible.** Some sites migrate from one to the other and run both during transition. However:

- A user's project typically targets ONE cluster scheduler
- The config-driven approach (Option D) handles this: change `cluster.scheduler` in config
- If a site truly needs both simultaneously, they could maintain two config profiles — but this is an edge case not worth optimizing for now

---

## 6. Copier Integration

### Copier Questions

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

### Generated Config

Copier generates `.claudechic.yaml` with:
```yaml
cluster:
  scheduler: {{ cluster_scheduler }}
  ssh_target: {{ cluster_ssh_target }}
  {% if cluster_scheduler == 'lsf' %}
  lsf_profile: /misc/lsf/conf/profile.lsf
  {% endif %}
```

### File Inclusion

```
{% if use_cluster %}
mcp_tools/cluster.py   →  included
{% endif %}
```

**One file, one Copier condition.** Clean.

### Development vs User Experience

The question of "how do we develop both backends but only ship one" is solved naturally:

- **In the AI_PROJECT_TEMPLATE repo:** `mcp_tools/cluster.py` contains ALL backends (LSF + SLURM). Tests cover both. This is the development artifact.
- **In the user's generated project:** `mcp_tools/cluster.py` is copied as-is (it contains both backends), but `.claudechic.yaml` specifies which one is active. The "unused" backend code is ~150 lines of dead code — acceptable. It doesn't affect behavior and might be useful if the user switches clusters.
- **Alternative (if dead code is unacceptable):** Copier could use Jinja to strip the unused backend class during generation. But this adds template complexity for minimal gain.

**Recommendation:** Ship both backends in the file. Config selects the active one. Dead code is acceptable — this is exactly what Nextflow and dask-jobqueue do (they ship all backends).

---

## 7. Testing Strategy

### Testing SLURM Without a Real Cluster

#### Option T1: Docker-based SLURM Cluster (T5 — giovtorres/slurm-docker-cluster)
- **URL:** https://github.com/giovtorres/slurm-docker-cluster
- **Stars:** 500+, actively maintained
- **License:** MIT ✅
- **Tests:** Yes, includes test suite ✅
- **What it provides:** Full SLURM cluster (slurmctld, slurmdbd, compute nodes) via docker-compose
- **Usage:** `docker-compose up -d` → submit real jobs with `sbatch`
- **CI feasibility:** ✅ Works in GitHub Actions (no GPU tests though)
- **Drawback:** Heavy — multiple containers, MySQL, takes ~30s to start

#### Option T2: Mock Shell Scripts (Lightweight)
Create fake `sbatch`, `squeue`, `scancel` scripts that:
- Accept the same flags
- Return realistic output in the expected format
- Simulate job state transitions

```bash
#!/bin/bash
# tests/mocks/sbatch
echo "Submitted batch job 12345"
```

```bash
#!/bin/bash
# tests/mocks/squeue
echo "JOBID USER STATE PARTITION NODELIST NAME SUBMIT_TIME"
echo "12345 testuser RUNNING gpu node01 test_job 2026-03-30T10:00:00"
```

| Criterion | Assessment |
|-----------|-----------|
| **Setup complexity** | 🟢 ~10 small shell scripts |
| **CI feasibility** | ✅ No containers needed, runs anywhere |
| **Realism** | 🟡 Doesn't test actual submission, but tests ALL parsing and command building |
| **Maintenance** | 🟢 Low — mock outputs rarely change |

**This is how dask-jobqueue tests:** They mock the scheduler commands and test the parsing/formatting logic. Real cluster tests are run separately on actual HPC.

#### Option T3: Python-Level Mocking
Patch `subprocess.run` to return known outputs. Test parsers directly with captured real output.

```python
def test_parse_squeue_output():
    sample = "12345 user1 RUNNING gpu node01 myjob 2026-03-30T10:00:00\n"
    jobs = _parse_squeue(sample)
    assert jobs[0]["job_id"] == "12345"
    assert jobs[0]["status"] == "RUNNING"
```

| Criterion | Assessment |
|-----------|-----------|
| **Realism** | ✅ Uses captured real output |
| **CI feasibility** | ✅ Pure Python, no external deps |
| **Coverage** | ✅ Tests parsing, command building, error handling |

### Testing LSF

- **No Docker equivalent** — LSF is proprietary (IBM). No public Docker image exists.
- **Mock approach:** Same as SLURM T2/T3 — mock `bsub`/`bjobs` output
- **Current state:** The boazmohar fork has `tests/test_cluster.py` (1128 lines!). This likely uses mocked output.
- **Real testing:** Only on actual LSF clusters (like Janelia's)

### Recommended Test Strategy

1. **Unit tests (CI):** Python-level mocking (T3) — test all parsers with captured real output from both LSF and SLURM. Test command builders. Test SSH command construction.
2. **Integration tests (optional CI):** Mock shell scripts (T2) — test the full `_run_lsf()` / `_run_slurm()` path with fake binaries on PATH.
3. **Acceptance tests (manual):** Run on actual clusters before release. Not in CI.
4. **Docker SLURM (stretch goal):** If we want to test actual `sbatch` submission in CI, use giovtorres/slurm-docker-cluster. Probably overkill for now.

---

## 8. How Other Multi-Scheduler Tools Handle This

### Nextflow (T3 — nextflow-io official)
- **Pattern:** `AbstractGridExecutor` base class → `SlurmExecutor`, `LsfExecutor`, `PbsExecutor` subclasses
- **Selection:** Config-driven: `process.executor = 'slurm'` in `nextflow.config`
- **Code split:** Each executor overrides `getHeaders()`, `getSubmitCommandLine()`, `parseJobId()`, `killTaskCommand()`
- **Shared code:** Queue monitoring, polling, retry logic, job tracking in base class
- **Key insight:** User code is completely scheduler-agnostic. Only config changes.

### Dask-jobqueue (T3 — dask official)
- **Pattern:** `Job` base class (core.py) → `SLURMJob`, `LSFJob`, `PBSJob` subclasses
- **Selection:** User instantiates `SLURMCluster()` or `LSFCluster()` directly
- **Code split:** `core.py` is ~800 lines. Each backend is ~100-200 lines. Backend overrides: `submit_command`, `cancel_command`, `__init__` (for header building)
- **Key insight:** The base class does ~80% of the work. Backends only override command building and output parsing.

### Snakemake (T3 — snakemake official)
- **Pattern (v8+):** Executor plugins — separate pip-installable packages (`snakemake-executor-plugin-slurm`)
- **Selection:** Config or CLI: `--executor slurm`
- **Key insight:** Full plugin architecture — each executor is its own package. Overkill for our use case.

### DRMAA (T1 — Open Grid Forum standard)
- **Pattern:** Standard C API with language bindings. `drmaa_run_job()`, `drmaa_job_status()`, etc.
- **Selection:** Runtime — DRMAA library is provided by the scheduler vendor
- **Key insight:** The "correct" academic solution but adds a C dependency. Too heavy for MCP tools.

### Pattern Summary

| Tool | Selection Method | Backend Size | Shared Size |
|------|-----------------|-------------|------------|
| Nextflow | Config string | ~200 lines each | ~500 lines base |
| Dask-jobqueue | Class instantiation | ~100-200 lines each | ~800 lines base |
| Snakemake v8 | Plugin packages | Separate packages | Framework |
| **Our approach** | Config string | ~150 lines each | ~200 lines shared |

Our approach is closest to **Nextflow's model** — config-driven, shared infrastructure, small backend overrides. The difference is we're a single file (appropriate for our scale) rather than a class hierarchy across files.

---

## 9. SLURM-Specific Considerations

### Output Formats (Parsing Differences)

**`squeue` (list jobs):**
```
JOBID PARTITION     NAME     USER ST       TIME  NODES NODELIST(REASON)
12345 gpu         train  jsmith  R    2:30:15      1 gpu-node01
```
- Supports `--format` and `--Format` for custom output
- Recommended: `squeue --format="%i|%u|%T|%P|%B|%R|%j|%V" -h` (pipe-delimited, no header) — much easier to parse than space-delimited

**`scontrol show job` (job detail):**
```
JobId=12345 JobName=train
   UserId=jsmith(1001) GroupId=lab(1001)
   Priority=100 Nice=0 Account=default QOS=normal
   JobState=RUNNING Reason=None Dependency=(null)
   Requeue=1 Restarts=0 BatchFlag=1 Resubmit=0
   ...
```
- Key=Value format — straightforward to parse with regex or split
- Much simpler than LSF's continuation-line format

**`sacct` (historical job data):**
```
JobID    JobName  Partition  Account  AllocCPUS  State      ExitCode
------   ------   ---------  -------  ---------  -------    --------
12345    train    gpu        default  4          COMPLETED  0:0
```
- Supports `--format` for custom fields
- Useful for completed jobs (which `scontrol show job` may not retain)

### Config Differences

| LSF | SLURM | Notes |
|-----|-------|-------|
| `source /misc/lsf/conf/profile.lsf` | No profile needed (usually) | SLURM is typically in PATH on login nodes. May need `module load slurm` |
| `LSF_SSH_TARGET` | Same concept — SSH to login node | Identical SSH layer |
| `CONDA_ENVS_DIRS` | Same | Conda is scheduler-agnostic |
| N/A | `SLURM_CONF` | Rarely needed by users |

### SLURM-Specific Features Not in LSF

1. **Job arrays:** `sbatch --array=1-100` — first-class feature, very popular in science
2. **`--wrap`:** `sbatch --wrap="python train.py"` — inline command without script file (our bridge)
3. **`--gres`:** Generic resource allocation (`--gres=gpu:v100:2`)
4. **Sacct for history:** Richer job history than LSF
5. **`--dependency`:** Job dependencies (`--dependency=afterok:12345`)
6. **`--mail-type`:** Email notifications

For v1 of SLURM support, we only need the basics (submit/list/status/kill/logs/watch). Job arrays and dependencies can come later.

---

## 10. Final Recommendation

### Architecture: Option D (Config-Driven Single File)

- **One file:** `mcp_tools/cluster.py` (~650 lines)
- **Backend protocol:** `ClusterBackend` with `list_jobs()`, `get_job_status()`, `submit_job()`, `kill_job()`, `terminal_statuses()`
- **Config-driven:** `.claudechic.yaml` → `cluster.scheduler: lsf|slurm`
- **Copier integration:** Single `use_cluster` bool + `cluster_scheduler` choice
- **Both backends ship in the file** — config selects active one
- **Tool names are scheduler-agnostic:** `cluster_jobs`, `cluster_submit`, etc.

### Implementation Priority

1. **Refactor current LSF code** into the backend protocol pattern (~2 hours)
2. **Implement SLURM backend** — mostly command building + output parsing (~3 hours)
3. **Test with mock scripts** for both backends in CI (~1 hour)
4. **Test on real SLURM cluster** when available

### Effort Estimate

| Task | Lines | Effort |
|------|-------|--------|
| Shared infrastructure (extract from current) | ~200 | Low — mostly moving existing code |
| ClusterBackend protocol | ~20 | Trivial |
| LSF backend (extract from current) | ~150 | Low — restructuring existing code |
| SLURM backend (new) | ~150 | Medium — new parsers and command builder |
| MCP tools (adapt from current) | ~120 | Low — change internal calls to use backend |
| Tests (both backends) | ~300 | Medium — mock scripts + parser tests |
| **Total new code** | **~150 lines** (SLURM backend) | The rest is restructured existing code |

**Bottom line: SLURM support is ~150 lines of genuinely new code** (parsers + command builder). The refactoring to make the architecture composable is the larger effort but doesn't add functionality — it restructures what exists.

---

## Sources

- Direct analysis of `/groups/spruston/home/moharb/DECODE-PRISM/Repos/claudechic/claudechic/cluster.py` (776 lines) — T1
- [LSF to SLURM Quick Reference — ETH Zurich](https://scicomp.ethz.ch/wiki/LSF_to_Slurm_quick_reference) — T1, official HPC center docs
- [SLURM rosetta stone (official)](https://slurm.schedmd.com/rosetta.pdf) — T1, SchedMD official
- [dask-jobqueue architecture](https://github.com/dask/dask-jobqueue) — T3, dask official org. MIT license ✅, Tests ✅
- [Nextflow executors](https://www.nextflow.io/docs/latest/executor.html) — T1, Nextflow official docs
- [Snakemake executor plugins](https://snakemake.github.io/snakemake-plugin-catalog/plugins/executor/slurm.html) — T1, Snakemake official
- [giovtorres/slurm-docker-cluster](https://github.com/giovtorres/slurm-docker-cluster) — T5, MIT license ✅, Tests ✅, actively maintained
- [Pitt CRC Slurm-Test-Environment](https://github.com/pitt-crc/Slurm-Test-Environment) — T5, Dockerized SLURM testing
- [Dask-jobqueue development guidelines](https://jobqueue.dask.org/en/latest/develop.html) — T1, shows their testing approach (mock + real cluster)
- [SLURM sacct docs](https://slurm.schedmd.com/sacct.html) — T1, SchedMD official
- [Useful SLURM commands — CU Boulder](https://curc.readthedocs.io/en/latest/running-jobs/slurm-commands.html) — T1, university HPC docs

## Not Recommended (and why)

| Approach | Why Rejected |
|----------|-------------|
| **Option A (two separate files)** | 280 lines of duplicated code; bug fixes must be applied twice |
| **Option C (base + modules)** | Extra `_cluster_base.py` file is an implementation artifact users shouldn't see |
| **DRMAA** | C library dependency; overkill for MCP tools that just shell out to schedulers |
| **Snakemake-style plugin packages** | Way overkill — we have 2 backends, not a plugin ecosystem |
| **Full Docker SLURM in CI** | Heavy setup for unit tests; save for integration testing only |
