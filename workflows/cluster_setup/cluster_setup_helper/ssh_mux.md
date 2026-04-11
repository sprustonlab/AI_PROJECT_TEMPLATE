# Phase 3: SSH Multiplexing

## Goal
Set up SSH connection pooling to speed up repeated SSH commands.

## Steps

1. **Skip if local scheduler** — no SSH needed

2. **Detect OS:**
   - Unix/macOS: use `ControlMaster` socket directory
   - Windows: use `ssh_config` connection sharing (OpenSSH for Windows)

### Unix / macOS

3. **Check socket directory:**
   ```bash
   ls -ld ~/.ssh/sockets 2>/dev/null
   ```
4. **If missing or wrong permissions:**
   - Create: `mkdir -p ~/.ssh/sockets`
   - Set permissions: `chmod 700 ~/.ssh/sockets`
5. **Verify:** directory exists with `drwx------` permissions

### Windows

3. **SSH multiplexing on Windows:**
   - Windows OpenSSH does **not** support `ControlMaster` / Unix sockets
   - Connection sharing is limited; skip socket directory setup
   - Ensure `~/.ssh/config` exists (create if needed):
     ```
     mkdir "%USERPROFILE%\.ssh" 2>nul
     ```
   - Add host entry for the cluster target if not already present:
     ```
     Host <alias>
       HostName <ssh_target>
       User <username>
       ServerAliveInterval 60
     ```
   - `ServerAliveInterval` keeps connections alive, which helps with repeated commands

## This phase IS auto-fixable
You can create directories and config entries directly.
Do NOT check Unix permissions (chmod/drwx) on Windows — they don't apply.

## Output to carry forward
Report: `{status: working|configured|skipped, can_auto_fix: true}`
