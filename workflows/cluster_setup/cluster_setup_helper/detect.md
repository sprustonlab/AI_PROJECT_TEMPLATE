# Phase 1: SSH Target Detection

## Goal
Determine how the user connects to the cluster and verify reachability.

## Steps

1. **Check for local scheduler:**
   - Run `which bsub` (LSF) and `which sbatch` (SLURM)
   - If found locally: note `local_scheduler: true`, SSH setup can be skipped

2. **Check existing config:**
   - Read `mcp_tools/cluster.yaml` for `ssh_target`
   - If set, test DNS reachability: `ssh -o BatchMode=yes -o ConnectTimeout=5 <target> echo ok`

3. **Detect OS:**
   - `uname -s` — affects path mapping defaults (Darwin = macOS, Linux, etc.)

4. **If no target configured:**
   - Ask the user for their cluster login node hostname

## Output to carry forward
Report: `{status: configured|missing|unreachable|skipped, ssh_target, local_scheduler, os_platform}`

## When done
Summarize findings and call `advance_phase` when the target is confirmed reachable.
