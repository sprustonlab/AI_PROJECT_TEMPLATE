# Cluster Setup Workflow

A guided workflow for configuring cluster MCP tools. Detects your environment, proposes path mappings, validates connectivity, and writes config.

## Phases

### Phase 0: Diagnose (`phase="diagnose"`)

Run phases 1-5 in sequence. Completely read-only — safe entry point for both initial setup and troubleshooting.

**How to invoke:** When any cluster tool returns `setup_needed`, or when the user asks to set up cluster tools, start here.

### Phase 1: SSH Target (`phase="detect"`)

1. Check if a local scheduler is available (`which bsub` or `which sbatch`)
   - If found: skip SSH setup, note `local_scheduler: true`
2. Check existing `ssh_target` in the tool's YAML config
3. If set, test DNS reachability: `ssh -o BatchMode=yes -o ConnectTimeout=5 <target> echo ok`
4. Detect OS via `platform.system()` (affects path mapping defaults)
5. If no target configured, ask the user for their cluster login node hostname

**Output:** `{status: "configured" | "missing" | "unreachable" | "skipped", ssh_target, local_scheduler, os_platform}`

### Phase 2: Passwordless SSH (`phase="ssh_auth"`)

1. Skip if no `ssh_target` needed (local scheduler found)
2. Test: `ssh -o BatchMode=yes -o ConnectTimeout=5 <target> echo ok`
3. If auth fails, provide step-by-step instructions:
   - `ssh-keygen -t ed25519` (if no key exists)
   - `ssh-copy-id <target>`
   - Test again
4. This phase is NOT auto-fixable — the user must run the commands

**Output:** `{status: "working" | "auth_failed" | "timeout" | "skipped"}`

### Phase 3: SSH Multiplexing (`phase="ssh_mux"`)

1. Skip if no `ssh_target` needed
2. Check if `~/.ssh/sockets/` exists with correct permissions (mode 0700)
3. If missing or wrong permissions: auto-fix by creating the directory
4. This phase IS auto-fixable

**Output:** `{status: "working" | "dir_missing" | "dir_wrong_perms" | "skipped", can_auto_fix: true}`

### Phase 4: Scheduler Detection (`phase="scheduler"`)

1. Check locally: `which bsub` (LSF), `which sbatch` (SLURM)
2. Check remotely via SSH: `ssh <target> 'which bsub sbatch'`
3. Test basic command: `bjobs 2>&1` or `squeue 2>&1`
4. Report which scheduler was found

**Output:** `{status: "detected" | "not_found" | "both_found", scheduler: "lsf" | "slurm" | null}`

### Phase 5: Paths (`phase="paths"`)

Bundles path_map, remote_cwd, and log_access detection:

1. **Mount scan:** Parse `/proc/mounts` (Linux), `mount` (macOS), `net use` (Windows) for NFS/SMB/CIFS mounts
2. **Remote home:** `ssh <target> 'echo $HOME'`
3. **CWD check:** `ssh <target> "test -d <translated_cwd>"`
4. **Path map proposal:** Compare local mounts with remote filesystem paths
5. **remote_cwd proposal:** If CWD doesn't exist on cluster after translation, propose remote home
6. **log_access proposal:** Mounts found -> `auto`. No mounts -> `ssh`. Local scheduler -> `local`

**Output:** `{status, mounts_detected, proposed_path_map, proposed_remote_cwd, proposed_log_access}`

### Phase 6: Validation (`phase="validate"`)

Validates the assembled config WITHOUT writing it:

| Check | How | Fix Phase |
|-------|-----|-----------|
| SSH connectivity | `ssh <target> echo ok` | `detect` or `ssh_auth` |
| Scheduler command | `bjobs 2>&1` or `squeue` | `scheduler` |
| Path round-trip | local -> cluster -> local must match | `paths` |
| File visibility | Create test file, read via proposed log_access | `paths` |
| Cleanup | Remove test file (best-effort) | -- |

If **passed**: may proceed to apply.
If **failed**: each check includes `fix_phase` — loop back, fix, re-validate.

**Output:** `{status: "passed" | "failed", checks: {...}, failed_checks: [...]}`

### Phase 7: Apply (`phase="apply"`)

1. **Preview** (`dry_run=true`, default): Show diff of proposed changes. Always allowed.
2. **Apply** (`dry_run=false`): Write to YAML config. **Rejects if validation has not passed.**

Config merge: existing keys preserved, new keys added/updated. Single atomic write.

**Output:** `{status: "preview" | "written" | "rejected"}`

## Important Notes

- Phases 1-6 are **read-only** — they probe and detect but never modify config files
- Phase 7 is the **only** phase that writes, and only after validation passes
- The `diagnose` meta-phase runs 1-5 in sequence — use it as the default entry point
- All detection uses existing MCP tools and SSH commands — no separate helper module needed
- State (detected values, proposals, validation results) lives in the conversation context
