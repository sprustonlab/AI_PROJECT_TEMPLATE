# Hooks Phase

Optional phase. Configure repository settings and hooks. The user can skip everything here.

**Tell the user upfront:** This phase is optional. They can skip any or all of these steps. Ask before proceeding with each one.

## Available Options

### 1. Branch Protection (requires `gh` CLI)

Offer to set up branch protection on `main`:
```bash
gh api repos/{owner}/{repo}/branches/main/protection \
  -X PUT \
  -f "required_pull_request_reviews[dismiss_stale_reviews]=true" \
  -f "required_pull_request_reviews[required_approving_review_count]=1" \
  -f "enforce_admins=false" \
  -f "restrictions=null" \
  -f "required_status_checks=null"
```
- Only offer this if `gh` is available and authenticated.
- Explain what branch protection does: prevents direct pushes to main, requires PR reviews.

### 2. Local Git Hooks (`.githooks/`)

Offer to set up a local hooks directory:
```bash
mkdir -p .githooks
git config core.hooksPath .githooks
```
- Offer a basic pre-commit hook that runs linting or tests if configured.
- Example pre-commit hook content:
  ```bash
  #!/bin/sh
  # Run checks before committing
  if command -v pixi >/dev/null 2>&1; then
      pixi run -e dev check 2>/dev/null || true
  fi
  ```

### 3. Pre-commit Framework

If the user wants more sophisticated hooks, offer to set up the `pre-commit` framework:
- Check if `.pre-commit-config.yaml` already exists.
- If not, offer a minimal config with common hooks (trailing whitespace, end-of-file fixer, YAML check).

## Completing This Phase

After offering all options (or if the user skips), confirm that repository settings are configured to the user's satisfaction. The user can always come back and run `/git-setup` again later.
