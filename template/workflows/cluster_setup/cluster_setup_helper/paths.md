# Phase 5: Path Mapping

## Goal
Configure bidirectional path mappings between local and cluster filesystems, and propose `remote_cwd` and `log_access` settings.

## Steps

### 1. Mount scan
Detect network mounts that bridge local and cluster filesystems:
- **macOS:** `mount | grep -iE 'nfs|smb|cifs|smbfs'`
- **Linux:** `cat /proc/mounts | grep -iE 'nfs|cifs'`
- **Windows/WSL:** `net use` or `mount | grep drvfs`

### 2. Remote home
```
ssh <target> 'echo $HOME'
```

### 3. CWD check
Test if the current local working directory (translated) exists on the cluster:
```
ssh <target> "test -d <translated_cwd> && echo exists"
```

### 4. Propose path_map
Compare local mounts with remote filesystem paths. Example:
```yaml
path_map:
  - local: /Volumes/groups/spruston
    cluster: /groups/spruston
```

If NO mounts are detected, propose `remote_cwd` as the fallback (e.g., the user's remote home or a project directory on the cluster).

### 5. Propose remote_cwd
If the local CWD doesn't map to a cluster path:
- Propose remote home: `/groups/spruston/home/<user>`
- Or ask user for their project directory on the cluster

### 6. Propose log_access
- Mounts found -> `auto` (try local first, fall back to SSH)
- No mounts -> `ssh` (always read logs via SSH)
- Local scheduler -> `local`

### 7. Code sync strategy (when project is NOT under a mount)

If the project's local working directory is NOT under any detected network mount, the cluster cannot see the code. **Symlinks cannot work across this boundary** — they resolve on the machine where they're followed.

Detect this case and present the user with options:

1. **Work from the mount** (recommended if mount exists) — clone/move the repo under the mounted path so both local and cluster see the same files automatically.
   ```
   cd /Volumes/<mount_point>
   git clone <repo_url> <project_name>
   ```

2. **rsync on demand** — push code to the cluster before submitting jobs:
   ```
   rsync -avz --exclude '.git' --exclude '.pixi' --exclude '__pycache__' \
     <local_project>/ <ssh_target>:<remote_home>/<project_name>/
   ```

3. **Git clone on cluster** — maintain a separate clone on the cluster and pull before runs:
   ```
   ssh <target> 'cd ~/<project_name> && git pull'
   ```

**Important:** Clearly explain to the user that their project code will NOT be visible to cluster jobs unless they take one of these steps. Set `remote_cwd` to wherever the code will land on the cluster.

## Output to carry forward
Report: `{status, mounts_detected, proposed_path_map, proposed_remote_cwd, proposed_log_access, code_sync_strategy}`

Present the proposed config to the user for approval before advancing.
