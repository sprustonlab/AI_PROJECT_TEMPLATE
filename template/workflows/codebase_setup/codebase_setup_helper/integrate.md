# Integrate Phase

Place the codebase into the project's `repos/` directory.

## Steps

1. **Explain the two integration methods:**
   - **Symlink** (recommended) -- creates a symbolic link from `repos/<name>` to the original location. Saves disk space, and changes in the original are reflected immediately. Best when the codebase is on the same filesystem.
   - **Copy** -- copies the codebase into `repos/<name>`. Works everywhere, including across filesystems and network mounts. Changes must be synced manually.

2. **Let the user choose.** Default to symlink unless the user prefers copy or the codebase is on a different filesystem.

3. **Create `repos/` if it doesn't exist.** Run `mkdir -p repos/`.

4. **Perform the integration:**
   - Symlink: `ln -s /absolute/path/to/codebase repos/<name>`
   - Copy: `cp -r /absolute/path/to/codebase repos/<name>`

5. **Validate the result.** Confirm that `repos/<name>` exists and contains the expected files. For symlinks, verify the link target is valid with `readlink -f repos/<name>`.

6. **Report success.** Show the user what's now in `repos/` and remind them that `repos/<name>` is automatically added to `PYTHONPATH` by the project's activate script.

To advance: `repos/<name>/` exists and contains the codebase files.
