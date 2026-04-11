# Remote Phase

Configure a git remote so the repository can be pushed to a hosting service.

## Steps

1. **Check for existing remote:**
   ```bash
   git remote get-url origin 2>/dev/null
   ```
   - If this succeeds, a remote is already configured. Show the URL and advance.
   - If no remote exists, proceed to step 2.

2. **Detect GitHub CLI availability:**
   ```bash
   gh auth status 2>/dev/null
   ```
   - If `gh` is available and authenticated, offer **Option A**.
   - If `gh` is not available or not authenticated, offer **Option B**.

3. **Option A -- Create repo with `gh`:**
   - Ask the user for a repo name (default: current directory name).
   - Ask whether the repo should be private (default: yes).
   - Run:
     ```bash
     gh repo create <name> --private --source=. --remote=origin
     ```
   - Verify with `git remote get-url origin`.

4. **Option B -- Manual remote add:**
   - Ask the user for the remote URL (SSH or HTTPS).
   - Run:
     ```bash
     git remote add origin <url>
     ```
   - Verify with `git remote get-url origin`.

## Notes

- If the user wants a public repo, use `--public` instead of `--private`.
- If `gh repo create` fails due to auth issues, fall back to Option B.
- Don't push yet -- that's the next phase.
