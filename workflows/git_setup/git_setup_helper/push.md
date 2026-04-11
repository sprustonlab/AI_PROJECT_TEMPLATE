# Push Phase

Push the initial commit to the remote and set up upstream tracking.

## Steps

1. **Check if already pushed:**
   ```bash
   git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null
   ```
   - If this succeeds, upstream is already set. Report status and advance.
   - If no upstream exists, proceed to step 2.

2. **Determine the branch name:**
   ```bash
   git branch --show-current
   ```
   - The branch is typically `main`. If it's `master` or something else, use that name.

3. **Push with upstream tracking:**
   ```bash
   git push -u origin <branch>
   ```

4. **Verify:** Confirm the push succeeded by checking `git rev-parse --abbrev-ref --symbolic-full-name @{u}` again.

## Troubleshooting

- **Authentication failure:** If push fails with a permission error, help the user check their SSH key (`ssh -T git@github.com`) or HTTPS credentials.
- **Rejected push:** If the remote has existing content (e.g., GitHub created a README), suggest `git pull --rebase origin <branch>` first, then push again.
- **Branch name mismatch:** If the remote expects `main` but local is `master` (or vice versa), offer to rename with `git branch -M main`.
