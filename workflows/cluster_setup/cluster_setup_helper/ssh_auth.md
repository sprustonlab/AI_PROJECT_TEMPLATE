# Phase 2: Passwordless SSH

## Goal
Ensure SSH to the cluster works without password prompts (BatchMode).

## Steps

1. **Skip if local scheduler** — no SSH needed
2. **Test BatchMode:**
   ```
   ssh -o BatchMode=yes -o ConnectTimeout=5 <target> echo ok
   ```
3. **If auth fails, guide the user:**
   - Check for existing key: `ls ~/.ssh/id_ed25519 ~/.ssh/id_rsa 2>/dev/null`
   - If no key: instruct `ssh-keygen -t ed25519`
   - Copy key: `ssh-copy-id <target>`
   - Re-test after user completes the steps

## Important
This phase is NOT auto-fixable. The user must run SSH key commands themselves (they may need to enter a password).

## Output to carry forward
Report: `{status: working|auth_failed|timeout|skipped}`
