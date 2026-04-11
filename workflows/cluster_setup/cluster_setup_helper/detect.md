# Phase 1: SSH Target Detection & Passwordless Auth

## Goal
Determine how the user connects to the cluster, verify reachability, and confirm passwordless SSH works.

## Steps

1. **Check for local scheduler:**
   - Run `which bsub` (LSF) and `which sbatch` (SLURM)
   - If found locally: note `local_scheduler: true`, SSH setup can be skipped

2. **Check SSH config for known hosts:**
   - Read `~/.ssh/config` for Host entries that may match cluster login nodes
   - Look for patterns like `Host *cluster*`, `Host *hpc*`, or lab-specific hostnames
   - If a likely match is found, propose it as the ssh_target

3. **Check existing config:**
   - Read `mcp_tools/cluster.yaml` for `ssh_target`
   - If set, test reachability with passwordless SSH:
     ```
     ssh -o BatchMode=yes -o ConnectTimeout=5 <target> echo ok
     ```
   - If this succeeds, passwordless SSH is confirmed — no separate auth phase needed

4. **Detect OS:**
   - `uname -s` — affects path mapping defaults (Darwin = macOS, Linux, etc.)

5. **If no target configured:**
   - Ask the user for their cluster login node hostname
   - Once provided, test with the BatchMode command above

6. **If SSH auth fails, guide the user:**
   - Check for existing key: `ls ~/.ssh/id_ed25519 ~/.ssh/id_rsa 2>/dev/null`
   - If no key: instruct `ssh-keygen -t ed25519`
   - Copy key: `ssh-copy-id <target>`
   - Re-test after user completes the steps
   - **Important:** This is NOT auto-fixable. The user must run SSH key commands themselves (they may need to enter a password).

## Output to carry forward
Report: `{status: configured|missing|unreachable|auth_failed|skipped, ssh_target, local_scheduler, os_platform, passwordless_ssh: true|false}`

## Before advancing
**Write `ssh_target` to `mcp_tools/cluster.yaml`** — the advance check requires it. Use Edit to set the confirmed hostname before calling `advance_phase`.

**Important: Do NOT quote the value.** Write `ssh_target: submit.int.janelia.org` not `ssh_target: "submit.int.janelia.org"`. The advance checks use `awk '/^ssh_target:/{print $2}'` to extract the value, and quotes would be included literally, causing SSH to fail with "hostname contains invalid characters".

## When done
Summarize findings and call `advance_phase` when the target is confirmed reachable with passwordless SSH.
