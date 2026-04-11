# Phase 7: Apply Configuration

## Goal
Write the validated configuration to `mcp_tools/cluster.yaml`.

## Steps

### 1. Preview (always do this first)
Show the user a diff of what will change:
- Current values vs proposed values
- Format as a clear before/after comparison

### 2. Apply (only after user approves preview)
Write the following fields to `mcp_tools/cluster.yaml`:
- `backend` — detected scheduler (`lsf` or `slurm`)
- `ssh_target` — confirmed login node
- `lsf_profile` — scheduler profile path (LSF only, leave empty for SLURM)
- `path_map` — approved bidirectional mappings
- `remote_cwd` — override working directory (if needed)
- `log_access` — log reading method

### Important
- **Merge, don't replace.** Preserve existing keys that aren't being updated.
- **Single atomic write.** Use the Edit tool to update specific fields.
- **Reject if validation hasn't passed.** Do not write config if phase 6 was skipped or failed.

### 3. Verify
After writing, read back `mcp_tools/cluster.yaml` and confirm the values are correct.

### 4. Test
Submit a quick test job via `cluster_submit` to confirm everything works end-to-end:
```
echo "cluster setup validation complete"
```
Verify the job runs in the correct working directory.

## Output
Report: `{status: preview|written|rejected}`

Run `/cluster_setup stop` to deactivate the workflow when done.
