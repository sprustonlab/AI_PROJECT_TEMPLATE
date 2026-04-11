# Phase 3: SSH Multiplexing

## Goal
Set up `~/.ssh/sockets/` for SSH connection pooling. This dramatically speeds up repeated SSH commands.

## Steps

1. **Skip if local scheduler** — no SSH needed
2. **Check directory:**
   ```
   ls -ld ~/.ssh/sockets 2>/dev/null
   ```
3. **If missing or wrong permissions:**
   - Create: `mkdir -p ~/.ssh/sockets`
   - Set permissions: `chmod 700 ~/.ssh/sockets`
4. **Verify:** directory exists with `drwx------` permissions

## This phase IS auto-fixable
You can create the directory and set permissions directly.

## Output to carry forward
Report: `{status: working|dir_missing|dir_wrong_perms|skipped, can_auto_fix: true}`
