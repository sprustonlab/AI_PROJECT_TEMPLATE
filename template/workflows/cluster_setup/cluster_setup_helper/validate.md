# Phase 6: Validation

## Goal
Validate the assembled configuration end-to-end WITHOUT writing it. A real cluster job must submit, complete, and have its log readable before you can advance.

## Automated Advance Checks

This phase has 3 automated checks that must all pass before the manual confirmation:

### Check 1: Job Submission
Auto-detects the scheduler and submits a test job (`echo cluster_setup_ok`) to the `short` queue/partition.
- **LSF:** `bsub -J cluster_setup_validate -q short ...` — passes when output matches `Job <ID>`
- **SLURM:** `sbatch --job-name=cluster_setup_validate --partition=short ...` — passes when output matches `Submitted batch job ID`
- **Neither found:** fails with `NO_SCHEDULER_FOUND`
- **Fix phase:** `detect` (SSH target), `ssh_auth` (connectivity), `scheduler` (queue access)

### Check 2: Job Completion
Waits 15 seconds, then queries job status using the detected scheduler.
- **LSF:** `bjobs -noheader -J cluster_setup_validate` — passes on `DONE` or `RUN`
- **SLURM:** `sacct --name=cluster_setup_validate --format=State` — passes on `COMPLETED` or `RUNNING`
- **Fix phase:** `scheduler` (cluster health, queue config)

### Check 3: Log Readable
Reads the job's stdout log from the cluster and checks for expected output.
- **Passes when:** log contains `cluster_setup_ok` (same for both schedulers)
- **Fix phase:** `paths` (log_access setting, path_map)

## What To Do

1. **Let the advance checks run.** Call `advance_phase` — the engine will execute all 3 checks automatically.
2. **If a check fails:** report which check failed and its `on_failure` message. Guide the user back to the appropriate fix phase.
3. **If all 3 pass:** the manual confirmation prompt will appear. Summarize results for the user.

## Additional Manual Checks (run before advancing)

These are not gated by advance checks but should be verified:

| Check | How | Fix Phase |
|-------|-----|-----------|
| SSH connectivity | `ssh <target> echo ok` | `detect` or `ssh_auth` |
| Path round-trip | local -> cluster -> local must match | `paths` |

### Path round-trip test
For each proposed `path_map` entry, verify:
```
local_path -> apply path_map -> cluster_path -> reverse path_map -> local_path
```
The result must match the original. If no path_map entries exist, verify `remote_cwd` is a valid directory on the cluster.

## Cleanup
After validation, remove test artifacts:
```
ssh <target> 'rm -f /tmp/cluster_setup_validate_*.log'
```

## Output
Report: `{status: passed|failed, checks: {submit: pass|fail, completion: pass|fail, log: pass|fail}, failed_checks: [...]}`
