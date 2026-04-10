# Specification Appendix: cluster_path_mapping

Supporting material for [SPECIFICATION.md](SPECIFICATION.md) — decision log, risk detail, migration notes, implementation reference, conversation examples, and deployment notes.

---

## Appendix A: Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| A1 | `local`/`cluster` naming (not `remote`) | "Remote" is overloaded — SSH target is also "remote". `cluster` is unambiguous. Config keys, code methods (`PathMapper.to_cluster()`, `PathMapper.to_local()`), and class names (`PathMapper`, not `PathTranslator` or `PathResolver`) all use this convention. |
| A2 | Longest-prefix-first sorting | Prevents user from needing to manually order rules. Most specific rule always wins. |
| A3 | `remote_cwd` separate from `path_map` | Different semantics: `remote_cwd` is "where to run", `path_map` is "how to translate". A user may want `remote_cwd` without any path_map rules. |
| A4 | Passthrough on no match | Zero-surprise default. If a path doesn't match any rule, it's used as-is. Existing behavior preserved. |
| A5 | `shlex.quote()` for all paths in scheduler flags | Defense-in-depth. Fixes existing unquoted `os.getcwd()` bug in LSF submit. |
| A6 | Native scheduler flags (`-cwd`, `--chdir`) over `cd` injection | CWD is a job-level property, not part of the command string. Native flags keep the command clean, avoid nested shell escaping, make CWD visible in scheduler metadata (`bjobs -l` shows correct `Execution CWD`), and decompose cleanly: `_resolve_cwd()` computes the path (shared), each backend passes it via its own flag (per-backend). |
| A7 | Parameterized tests grouped by concept | Each test function tests ONE concept, parameterized across environments (SMB, Windows, WSL, SSH-only, direct cluster). ~13 functions x ~5-8 parameter sets = ~80 test cases in one file. Shared named constants (`SMB_MAC`, `WINDOWS_DRIVE`, etc.) for readability. Coverage matrix shows which inputs cover which scenarios. |
| A8 | `LogReader` strategy pattern (not PathMapper extension) | Log transport (local vs SSH) is orthogonal to path translation. PathMapper handles namespace; LogReader handles transport. Mixing them violates single-responsibility. |
| A9 | `log_access` explicit config key (not inferred) | User explicitly chose explicit config over auto-inference. Predictable behavior; user knows which transport is in use. `auto` default still provides zero-config convenience. |
| A10 | `_resolve_log_path()` returns `str` not `Path` | Cluster paths may not be valid on the local filesystem (e.g., no mount). Returning `Path` implies local validity. `str` is honest about the namespace. |
| A11 | `auto` as default `log_access` (not `local`) | `auto` is strictly superior: tries local first (fast, works for mount users), falls back to SSH. Zero behavioral change for existing users. |
| A12 | Skip `mkdir` when `log_access: ssh` | No shared filesystem means local `mkdir` is meaningless. The scheduler creates output directories on cluster nodes. |
| A13 | Single `cluster_setup` tool with `phase` parameter (not two tools) | One tool is simpler to discover and document. The `phase` parameter gives fine-grained control; `answers` dict lets the model pass context forward; `dry_run` flag on `apply` provides the read/write split where it matters. |
| A14 | `diagnose` meta-phase as safe entry point | Runs all detection probes (1–5) in one call without modifying anything. Also useful for troubleshooting. Iterates `STAGES` list, so new phases are automatically included. |
| A15 | Two-layer design: pure primitives + probe wrappers | Primitives (`_check_ssh_reachability`, `_scan_mounts`) are pure functions — independently testable without `_SetupState`. Probes wrap primitives with state management, skip conditions, and error handling. Clean separation of "what to detect" from "how to orchestrate." |
| A16 | `STAGES` list for extensibility | Declarative stage registry. New phases added by appending to list + adding to `PHASE_MAP`. `_diagnose()` iterates automatically. Skip conditions are declarative strings evaluated against state. |
| A17 | Validation tests in-memory config, not written config | Catches bad configs before they corrupt existing working config. Each failed check returns a `fix_phase` so the model knows where to loop back. |
| A18 | Apply phase rejects if `validation_passed != true` | Hard gate: `dry_run=false` refuses to write unless validation has passed. `dry_run=true` (preview) is always allowed. |
| A19 | Model-driven onboarding conversation | The model orchestrates the 7-phase pipeline, not a hard-coded wizard. Allows adaptive flow: skip phases, ask clarifying questions, handle errors conversationally. |
| A20 | Onboarding code in `_cluster_setup.py` (separate from `_cluster.py`) | Onboarding probes are ~400 LOC with different concerns from runtime infrastructure. Separate file keeps `_cluster.py` focused on `PathMapper`/`LogReader`/`_run_ssh`. Still underscore-prefixed (not auto-discovered). One-directional imports from `_cluster.py`. |
| A21 | `_SetupState` accumulates across phases | State object held by the tool closure tracks `ssh_target`, `scheduler`, `proposed_config`, `validation_passed`, and per-phase results. Later phases read state from earlier ones. |
| A22 | SSH auth probe is advisory only (`can_auto_fix: false`) | `ssh-copy-id` requires the user's password — cannot be automated in a non-interactive MCP context. |
| A23 | Combined "paths" phase (not 3 separate phases) | `path_map`, `remote_cwd`, and `log_access` are interdependent. One phase avoids redundant SSH calls and lets the model present a coherent proposal. |
| A24 | Config writes are batched and atomic | All changes collected in `state.proposed_config`, written in one `yaml.safe_dump()` call. Merge preserves existing keys not in the update. |
| A25 | Error hints in tool responses | When tools fail with path or connection errors, the error response includes a `hint` field suggesting `cluster_setup phase='diagnose'`. Creates a self-healing loop: failure → hint → diagnose → fix → retry. |
| A26 | Proactive onboarding (not reactive) | Every cluster tool call includes `_check_config_readiness()`. For `needs_setup`: model automatically runs diagnose. For `incomplete`: model asks user. For `ready`: no prompt. First-time users onboarded immediately, not after a confusing error. |
| A27 | Three-state readiness (not boolean) | `needs_setup` vs `incomplete` vs `ready` distinguishes "no config at all" from "partial config" from "all good". Binary would either over-prompt or under-prompt. |
| A28 | Readiness check is O(1) | `_check_config_readiness()` only reads config dict + `shutil.which()`. No SSH, no filesystem probes. Safe to run on every tool call. |
| A29 | `setup_needed` field in responses (not separate tool) | The readiness signal is embedded in normal tool responses. The model discovers the need for setup naturally during its first tool call. |
| A30 | Tool descriptions instruct proactive behavior | `cluster_setup`'s description says "IMPORTANT: check if the response includes setup_needed." Explicit model guidance, not implicit. |
| A31 | Two sorted rule lists in PathMapper | `_rules_by_local` (sorted by local prefix length desc) for `to_cluster()`, `_rules_by_cluster` (sorted by cluster prefix length desc) for `to_local()`. A single list sorted by one side's prefix length could mismatch when the other side has overlapping prefixes of different lengths. |
| A32 | Split `_normalize_path()` into local/cluster variants | `_normalize_local_path()` expands `~`, env vars, converts backslashes. `_normalize_cluster_path()` only strips trailing slashes. Expanding `$HOME` on cluster paths would use local `$HOME`, which is wrong. |
| A33 | `startswith("/")` instead of `os.path.isabs()` for cluster paths | `os.path.isabs("/groups/lab/out.log")` returns `False` on Windows. Cluster paths are always POSIX, so `startswith("/")` is correct and cross-platform. |
| A34 | All returned paths use forward slashes (even on Windows) | Windows APIs accept forward slashes natively. Avoids platform-conditional de-normalization logic. Simpler and consistent. |
| A35 | Lazy PathMapper/LogReader creation (not at `get_tools()` time) | Creating at `get_tools()` time makes objects stale after `cluster_setup apply` updates config. Lazy creation in each tool handler ensures fresh config is always used. |
| A36 | `_create_log_reader()` accepts explicit `profile` parameter | Removed `config.get("lsf_profile")` from the factory. Each backend passes its own profile key, making the factory scheduler-agnostic. |
| A37 | `log_reader` is required in `_read_logs()` (no default) | Removed `log_reader or LocalLogReader(path_mapper)` default. Backends always create and pass a log reader explicitly. Eliminates hidden coupling and makes the dependency explicit. |

---

## Appendix B: Risk Detail & Known Limitations

### Case Sensitivity (Risk 6.6)

Windows and macOS filesystems are case-insensitive; Linux (cluster) is case-sensitive. All path matching in `PathMapper` is case-sensitive, matching cluster semantics. A future `case_insensitive: true` flag per rule can be added if demand warrants. Do not implement prematurely — it adds complexity to prefix matching and normalization.

### `/bin/bash` Hardcoded in `_run_ssh()` (Risk 6.7)

`subprocess.run(..., executable="/bin/bash")` in `_cluster.py` line 107 will fail on Windows where `/bin/bash` does not exist. Proposed future fix: use `shutil.which("bash")` with fallback, or allow `shell_executable` in config. Out of scope for this project but noted for completeness.

### Path Traversal Defense-in-Depth (Risk 6.3)

After translation, validate that the result still starts with one of the expected prefixes from `path_map`. Log a warning (do not hard-fail) if a translated path escapes all known prefixes. The primary trust boundary is the YAML config file which the user controls.

### SSH Log Reading Performance (Risk 6.10)

Mitigated by existing SSH connection multiplexing (`ControlMaster=auto`, `ControlPersist=600`). All SSH calls share a single TCP connection. `tail -n` runs remote-side, so only requested lines are transferred. `AutoLogReader` tries local first (O(1) for mount users). 30-second timeout prevents hangs.

---

## Appendix C: Migration Notes

### LSF CWD: Before/After

**Before** (current `lsf.py` line 247-248 — `cd` injected into command string, unquoted):
```python
if not re.match(r"^\s*cd\s+", full_command):
    full_command = f"cd {os.getcwd()} && {full_command}"
```

**After** (native scheduler flag, command untouched):
```python
cwd = _resolve_cwd(config, path_mapper)
parts += ["-cwd", shlex.quote(cwd)]
# Remove the cd injection and re.match guard entirely.
```

This also fixes an **existing bug** where `os.getcwd()` was injected unquoted — paths with spaces, dollar signs, or backticks could break or exploit the shell command.

### SLURM CWD: New Feature

CWD handling is currently **missing entirely** in `slurm.py`. This project adds it:
```python
cwd = _resolve_cwd(config, path_mapper)
parts += [f"--chdir={shlex.quote(cwd)}"]
```

### `_resolve_log_path()` Return Type Change

Previously returned `Path` and performed path translation. Now returns `str` (cluster path) and delegates translation to `LogReader`. This is a breaking change to the internal API but not to any external interface.

---

## Appendix D: Onboarding Implementation Reference

### `_cluster_setup.py` Code Architecture

All onboarding logic lives in `_cluster_setup.py` — a separate underscore-prefixed helper (not auto-discovered by MCP). The `cluster_setup` tool is registered by each backend in its `get_tools()`.

```python
# In _cluster_setup.py — new file:

from __future__ import annotations
import platform
import shutil
from pathlib import Path
from typing import Any, Callable

from mcp_tools._cluster import _run_ssh, _ssh_control_path, _load_config

# ---------------------------------------------------------------------------
# Stage registry (extensible — add new stages here)
# ---------------------------------------------------------------------------

STAGES: list[dict[str, Any]] = [
    {"name": "detect",    "fn": "_probe_detect",    "skip_if": "local_scheduler"},
    {"name": "ssh_auth",  "fn": "_probe_ssh_auth",  "skip_if": "no_ssh_target"},
    {"name": "ssh_mux",   "fn": "_probe_ssh_mux",   "skip_if": "no_ssh_target"},
    {"name": "scheduler", "fn": "_probe_scheduler",  "skip_if": None},
    {"name": "paths",     "fn": "_probe_paths",      "skip_if": None},
]
# validate and apply are NOT in STAGES — they have special semantics

# ---------------------------------------------------------------------------
# State accumulator (per-session, held by the tool closure)
# ---------------------------------------------------------------------------

class _SetupState:
    """Accumulated state across phases. Holds probe results + assembled config."""
    def __init__(self, config: dict | None = None):
        self.initial_config: dict = config or {}
        self.ssh_target: str = ""
        self.local_scheduler: bool = False
        self.os_platform: str = platform.system().lower()
        self.scheduler: str | None = None
        self.proposed_config: dict = {}
        self.validation_passed: bool = False
        self.phase_results: dict[str, dict] = {}

    def should_skip(self, skip_condition: str | None) -> bool:
        """Evaluate a skip condition against current state."""
        if skip_condition is None:
            return False
        if skip_condition == "local_scheduler":
            return self.local_scheduler
        if skip_condition == "no_ssh_target":
            return not self.ssh_target
        return False

# ---------------------------------------------------------------------------
# Detection primitives (pure functions — independently testable)
# ---------------------------------------------------------------------------

def _check_ssh_reachability(ssh_target: str, timeout: int = 5) -> dict:
    """Pure: test if an SSH target is reachable. Returns {reachable, error}."""
    ...

def _check_ssh_auth(ssh_target: str, timeout: int = 10) -> dict:
    """Pure: test passwordless SSH via BatchMode=yes. Returns {status, stderr}."""
    ...

def _check_socket_dir(socket_dir: Path) -> dict:
    """Pure: check if socket dir exists with correct permissions. Returns {exists, mode}."""
    ...

def _detect_scheduler_local() -> dict:
    """Pure: check for bsub/sbatch in local PATH. Returns {found, scheduler}."""
    ...

def _detect_scheduler_ssh(ssh_target: str, timeout: int = 10) -> dict:
    """Pure: check for bsub/sbatch via SSH. Returns {found, scheduler}."""
    ...

def _scan_mounts(os_platform: str) -> list[dict]:
    """Pure: parse OS mount table. Returns list of {mount_point, remote, fs_type}."""
    ...

def _detect_remote_home(ssh_target: str) -> str | None:
    """Pure: get cluster-side $HOME via SSH. Returns path or None."""
    ...

# ---------------------------------------------------------------------------
# Probe functions (wrap primitives, read/write _SetupState)
# ---------------------------------------------------------------------------

def _probe_detect(state: _SetupState, answers: dict) -> dict: ...
def _probe_ssh_auth(state: _SetupState, answers: dict) -> dict: ...
def _probe_ssh_mux(state: _SetupState, answers: dict) -> dict: ...
def _probe_scheduler(state: _SetupState, answers: dict) -> dict: ...
def _probe_paths(state: _SetupState, answers: dict) -> dict: ...
def _probe_validate(state: _SetupState, answers: dict) -> dict: ...
def _do_apply(state: _SetupState, answers: dict, dry_run: bool, tool_file: Path) -> dict: ...

# ---------------------------------------------------------------------------
# Diagnose — safe entry point
# ---------------------------------------------------------------------------

def _diagnose(state: _SetupState, answers: dict) -> dict:
    """Run all STAGES in order, respecting skip conditions."""
    results = {}
    ready, action_needed, skipped = [], [], []
    for stage in STAGES:
        name = stage["name"]
        if state.should_skip(stage["skip_if"]):
            results[name] = {"status": "skipped"}
            skipped.append(name)
            continue
        fn = PHASE_MAP[name]
        result = fn(state, answers)
        results[name] = result
        state.phase_results[name] = result
        if result.get("status") in ("working", "configured", "detected", "proposals_ready"):
            ready.append(name)
        else:
            action_needed.append(name)
    return {
        "phases": results,
        "summary": {"ready_phases": ready, "action_needed": action_needed, "skipped": skipped},
    }

# ---------------------------------------------------------------------------
# Phase dispatcher
# ---------------------------------------------------------------------------

PHASE_MAP: dict[str, Callable] = {
    "detect": _probe_detect,
    "ssh_auth": _probe_ssh_auth,
    "ssh_mux": _probe_ssh_mux,
    "scheduler": _probe_scheduler,
    "paths": _probe_paths,
    "validate": _probe_validate,
    # "diagnose" and "apply" handled separately in the tool function
}

# ---------------------------------------------------------------------------
# Config writer
# ---------------------------------------------------------------------------

def _preview_config_changes(tool_file: Path, updates: dict) -> dict:
    """Return diff of what would change without writing."""
    existing = _load_config(tool_file)
    merged = {**existing, **updates}
    added = {k: v for k, v in updates.items() if k not in existing}
    changed = {k: {"old": existing[k], "new": v} for k, v in updates.items()
               if k in existing and existing[k] != v}
    return {"added": added, "changed": changed, "merged": merged}

def _apply_config_changes(tool_file: Path, updates: dict) -> dict:
    """Merge updates into existing YAML. Atomic write.
    Preserves unrelated keys. Returns the final merged config."""
    config_path = tool_file.with_suffix(".yaml")
    existing = _load_config(tool_file)
    merged = {**existing, **updates}
    with open(config_path, "w") as f:
        yaml.safe_dump(merged, f, default_flow_style=False, sort_keys=False)
    return {"written": True, "path": str(config_path), "config": merged}
```

### `_check_config_readiness()` Full Implementation

```python
def _check_config_readiness(config: dict) -> dict:
    """Lightweight config-readiness check. No SSH calls, no side effects.

    Returns:
        {"state": "needs_setup" | "incomplete" | "ready",
         "message": str | None,
         "action": str | None}   # Directive: AUTO_RUN or ASK
    """
    ssh_target = config.get("ssh_target", "")
    has_local = bool(shutil.which("bsub") or shutil.which("sbatch"))
    has_path_map = bool(config.get("path_map"))

    if not ssh_target and not has_local:
        return {
            "state": "needs_setup",
            "message": (
                "Cluster tools are not yet configured. No ssh_target is set "
                "and no scheduler is available locally."
            ),
            "action": "AUTO_RUN cluster_setup phase='diagnose'",
        }

    if ssh_target and not has_path_map:
        return {
            "state": "incomplete",
            "message": (
                "Cluster connection is configured (ssh_target set) but path "
                "mapping is not. Paths may not translate correctly between "
                "your local machine and the cluster."
            ),
            "action": "ASK user if they want to run cluster_setup phase='diagnose'",
        }

    return {"state": "ready", "message": None, "action": None}
```

### Defensive Design Pattern

Every probe follows this pattern — never raises, always returns structured result, always has timeout:

```python
def _probe_ssh_auth(state: _SetupState, answers: dict) -> dict:
    """Test passwordless SSH. Always returns a result, never raises."""
    ssh_target = state.ssh_target
    if not ssh_target:
        return {"status": "skipped", "reason": "no ssh_target configured"}
    try:
        result = _check_ssh_auth(ssh_target, timeout=10)
        if result["status"] == "ok":
            return {"status": "working", "can_auto_fix": False}
        elif result["status"] == "auth_failed":
            return {
                "status": "auth_failed",
                "can_auto_fix": False,
                "instructions": [
                    "ssh-keygen -t ed25519",
                    f"ssh-copy-id {ssh_target}",
                    f"ssh {ssh_target} hostname",
                ],
            }
        else:
            return {"status": "error", "detail": result.get("stderr", ""), "can_auto_fix": False}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "can_auto_fix": False}
    except Exception as e:
        return {"status": "error", "detail": str(e), "can_auto_fix": False}
```

Key principles:
- **Never raises** — always returns a structured result
- **Always has a timeout** — no probe blocks indefinitely (≤10s per SSH call)
- **Catches all exceptions** — one broken probe doesn't crash the pipeline
- **Reports `can_auto_fix`** — model knows what it can offer vs. what needs user action
- **Delegates to pure primitives** — try/except in probe; primitive is clean and testable

---

## Appendix E: Conversation Examples

### Scenario A: Proactive first-use (`needs_setup`)

```
User: "Submit my training script to the cluster"

Model: [calls cluster_submit command="python train.py" ...]

Response: {"type": "text", "text": "Error: Cluster tools are not yet configured...",
           "setup_needed": "needs_setup",
           "action": "AUTO_RUN cluster_setup phase='diagnose'"}

Model: "I see your cluster tools aren't set up yet. Let me run a quick
  diagnosis to get you connected."

Model: [calls cluster_setup phase="diagnose"]

Model: "Here's what I found:
  ✗ SSH target: not configured
  — SSH auth: skipped (no target yet)
  — Scheduler: not found locally
  — Path config: skipped

  What's the hostname of your cluster login node?"

User: "login1.janelia.org"

Model: [calls cluster_setup phase="detect" answers={"ssh_target": "login1.janelia.org"}]

... (continues through ssh_auth, ssh_mux, scheduler, paths, validate, apply)

Model: "All set! Now let me submit that training script..."
       [calls cluster_submit command="python train.py" ...]

Model: "Job 12345 submitted to LSF."
```

### Scenario B: Proactive incomplete config (`incomplete`)

```
User: "Submit my analysis to the cluster"

Model: [calls cluster_submit command="python analyze.py" ...]

Response: {"type": "text", "text": "Job 67890 submitted successfully.",
           "setup_needed": "incomplete",
           "action": "ASK user..."}

Model: "Job submitted! I also notice path mapping isn't configured yet.
  This means paths won't translate between your Mac and the cluster.

  Want me to run cluster_setup to auto-detect your environment?"

User: "Yes please"

Model: [calls cluster_setup phase="diagnose"]
... (auto-detects SMB mount, proposes path_map, validates, applies)
```

### Scenario C: Explicit request (config already complete)

```
User: "I need to set up cluster access"

Model: [calls cluster_setup phase="diagnose"]

Model: "Your cluster is fully configured:
  ✓ SSH target: login1.janelia.org (reachable)
  ✓ SSH auth: working
  ✓ SSH mux: socket directory ready
  ✓ Scheduler: LSF detected
  ✓ Path mapping: /Volumes/groups → /groups
  ✓ log_access: auto

  Everything looks good — no changes needed!"
```

### Scenario D: Validation failure loop

```
Model: [calls cluster_setup phase="validate"]

Model: "✗ Validation failed:
  - Path round-trip: FAILED (fix_phase: paths)
    /Volumes/groups/test → /groups/test → /Volumes/groups//test (double slash)

  Let me fix the path config..."

Model: [calls cluster_setup phase="paths" answers={"path_map": [...]}]
Model: [calls cluster_setup phase="validate"]
Model: "✓ All checks passed now."
```

---

## Appendix F: Deployment Notes

### Copier Interaction

| Phase | What happens |
|-------|-------------|
| **`copier copy`** (generation) | User answers `use_cluster`, `cluster_scheduler`, `cluster_ssh_target`. Jinja template renders initial YAML with `ssh_target` filled in, new keys (`path_map`, `remote_cwd`, `log_access`) as commented defaults. |
| **First run** (proactive onboarding) | User's first cluster tool call returns `setup_needed: "needs_setup"` or `"incomplete"`. Model proactively runs `cluster_setup phase="diagnose"` (automatic for `needs_setup`, asks permission for `incomplete`). Probes detect environment, user confirms, `apply` writes config. |
| **`copier update`** (template update) | YAML files use copier's conflict resolution (user keeps their version). The generated YAML is owned by the user after first `apply`. |
