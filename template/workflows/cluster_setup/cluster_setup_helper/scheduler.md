# Phase 3: Scheduler Detection

## Goal
Detect which job scheduler (LSF or SLURM) is available on the cluster.

## Steps

1. **Check locally:**
   - `which bsub` (LSF)
   - `which sbatch` (SLURM)

2. **Check remotely via SSH:**
   ```
   ssh <target> 'which bsub 2>/dev/null; which sbatch 2>/dev/null'
   ```

3. **Test basic command:**
   - LSF: `ssh <target> 'source /misc/lsf/conf/profile.lsf 2>/dev/null; bjobs 2>&1'`
   - SLURM: `ssh <target> 'squeue 2>&1'`

4. **If both found:** ask user which to configure

5. **Verify lsf_profile** (if LSF):
   - Check that `lsf_profile` in cluster.yaml points to a valid file on the cluster
   - `ssh <target> 'test -f /misc/lsf/conf/profile.lsf && echo exists'`

## Before advancing
**Write `backend` and `lsf_profile` to `mcp_tools/cluster.yaml`** before calling `advance_phase`. The next phases rely on these values. Example for LSF:
```yaml
backend: lsf
lsf_profile: /misc/lsf/conf/profile.lsf
```
Do NOT quote the values — awk is used to extract them in advance checks.

## Output to carry forward
Report: `{status: detected|not_found|both_found, scheduler: lsf|slurm|null, lsf_profile_path}`
