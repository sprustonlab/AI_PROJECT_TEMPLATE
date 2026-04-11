# Init Phase

Check whether a git repository already exists. If not, initialize one.

## Steps

1. **Check for existing repo:**
   ```bash
   git rev-parse --git-dir 2>/dev/null
   ```
   - If this succeeds (prints `.git` or a path), a repo already exists. Report status and advance.
   - If this fails, no repo exists -- proceed to step 2.

2. **Initialize the repository:**
   - Explain to the user that you'll create a git repo, stage all files, and make an initial commit.
   - Run:
     ```bash
     git init
     git add -A
     git commit -m "Initial project"
     ```
   - Set the default branch to `main` if it isn't already:
     ```bash
     git branch -M main
     ```

3. **Verify:** Confirm the repo was created by checking `git rev-parse --git-dir` again.

## Notes

- If `git init` fails, check whether `git` is installed and on PATH.
- If there are no files to commit, create a minimal `.gitignore` so the initial commit isn't empty.
- Don't configure user.name/user.email here -- that's the user's global git config.
