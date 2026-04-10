# Check Inventory: Honest Assessment

**Author:** Composability
**Date:** 2026-04-04

---

## What already covers setup diagnostics

Before proposing new checks, here's what the template already does:

| Failure | Where it's caught | When |
|---|---|---|
| No GitHub access | `install.sh` runs `git ls-remote` | Install time only |
| No pixi | `activate` script bootstraps pixi via curl | Every session |
| Pixi env not installed | `activate` runs `pixi install` | Every session |
| No git repo | `GitNotInitialized` hint trigger | Session startup |
| Guardrails stale | `activate` timestamp comparison, auto-regenerates | Every session |
| Cluster configured but unused | `ClusterConfiguredUnused` hint | Session startup |
| No custom guardrail rules | `GuardrailsOnlyDefault` hint | Session startup |

**The installer and activate script handle the hard failures. The hints system handles the soft nudges. There's a genuine gap in between: things that break AFTER install, or that the installer doesn't check.**

---

## Real checks that test outcomes

### Check 1: GitHub authentication works

**What it tests:** Can this machine authenticate to GitHub right now?

**Why it matters:** The installer checks this, but SSH keys expire, tokens get revoked, and scientists move between machines. A working install can break silently. The first symptom is `pixi install` or `git push` failing with cryptic auth errors.

```yaml
type: command-output-check
command: "git ls-remote https://github.com/sprustonlab/claudechic.git HEAD 2>&1 | head -1"
pattern: "[0-9a-f]{40}"
```

- **Passes when:** `git ls-remote` returns a commit hash (any 40-char hex)
- **Fails when:** Auth failure, network down, repo deleted
- **Hint on failure:** `"GitHub authentication failed. Run: gh auth login  — or check your SSH keys with: ssh -T git@github.com"`
- **Lifecycle:** `ShowUntilResolved` — re-checks each session

### Check 2: Git identity configured

**What it tests:** Will commits have a real author?

**Why it matters:** Not checked anywhere in the template. Scientists on shared HPC nodes commit as `root@login-node.cluster.edu`. This creates unusable git history and breaks `git blame`. The template enforces guardrails on git operations (R04, R05) but never checks that git identity is sane.

```yaml
type: command-output-check
command: "git config user.email"
pattern: ".+@.+"
```

- **Passes when:** Email contains `@` (minimal sanity)
- **Fails when:** No email configured, or set to empty
- **Hint on failure:** `"Git email not configured. Run: git config --global user.email 'you@example.com'"`
- **Lifecycle:** `ShowUntilResolved`

### Check 3: Pixi environment is healthy

**What it tests:** Can Python actually import from the pixi environment?

**Why it matters:** `activate` checks that `pixi install` ran, but doesn't verify the result works. After a `pixi update`, broken solver resolutions, or NFS cache staleness on clusters, the environment can exist but be non-functional. Scientists see `ModuleNotFoundError` on first `pixi run pytest` and don't know why.

```yaml
type: command-output-check
command: "pixi run python -c \"import yaml; print('ok')\" 2>&1"
pattern: "ok"
```

- **Passes when:** Python can import PyYAML (a hard dependency — if this works, the env is functional)
- **Fails when:** Broken env, missing packages, corrupted .pixi/
- **Hint on failure:** `"Pixi environment is broken. Try: pixi install --force"`
- **Lifecycle:** `ShowUntilResolved`

### Check 4: Cluster SSH works (conditional — only if `use_cluster=true`)

**What it tests:** Can you actually reach the cluster login node?

**Why it matters:** The `ClusterConfiguredUnused` hint nudges users to try cluster features, but doesn't verify the prerequisite: SSH access. When SSH fails, the MCP cluster tools (`lsf.py`, `slurm.py`) use `subprocess.run()` which hangs or returns cryptic errors. Scientists report "the tool is frozen" — it's actually waiting for an SSH password prompt that never appears in the TUI.

```yaml
type: command-output-check
command: "ssh -o ConnectTimeout=5 -o BatchMode=yes ${CLUSTER_SSH_TARGET} hostname 2>&1"
pattern: "^[a-zA-Z]"
```

- **Passes when:** SSH returns a hostname (any string starting with a letter)
- **Fails when:** Auth failure, timeout, host unreachable, password required
- **Hint on failure:** `"Cannot SSH to cluster (${CLUSTER_SSH_TARGET}). Ensure passwordless SSH is configured: ssh-copy-id ${CLUSTER_SSH_TARGET}"`
- **Lifecycle:** `ShowUntilResolved`
- **Trigger guard:** Only evaluates when `copier.use_cluster` is true

### Check 5: Tests collect without errors

**What it tests:** Does `pytest --collect-only` succeed?

**Why it matters:** The testing phase gate runs `pixi run pytest`, but if tests have import errors, the agent gets a wall of traceback instead of a pass/fail signal. This check catches broken test files early — before the agent enters the testing phase. Scientists who add tests with wrong imports get stuck in a "tests fail but I don't know why" loop.

```yaml
type: command-output-check
command: "pixi run pytest --collect-only -q 2>&1 | tail -1"
pattern: "\\d+ tests? collected"
```

- **Passes when:** pytest can discover and import all test files
- **Fails when:** Import errors, syntax errors, missing fixtures
- **Hint on failure:** `"Tests have collection errors. Run: pixi run pytest --collect-only  to see which files are broken"`
- **Lifecycle:** `ShowOnce` — this is a nudge, not a persistent warning

---

## Checks I considered and rejected

### "SSH key exists" — WRONG

The original spec example (`FileExistsCheck("~/.ssh/id_ed25519")`) is wrong because:
- Keys can be `id_rsa`, `id_ecdsa`, `id_ed25519`, or custom names in `~/.ssh/config`
- GitHub CLI (`gh auth`) uses credential helpers, not SSH keys
- The OUTCOME is "can you authenticate to GitHub?" — Check 1 above

### "Pixi installed" — ALREADY HANDLED

`activate` script bootstraps pixi automatically. A check would be redundant.

### "Guardrails up to date" — ALREADY HANDLED

`activate` script auto-regenerates hooks when `rules.yaml` is newer than `settings.json`.

### "Git repo initialized" — ALREADY HANDLED

`GitNotInitialized` hint trigger already exists in `hints/hints.py`.

### "Conda/pip not used" — WRONG LAYER

This is a guardrail (R02, R03), not a check. Guardrails block the action in real-time. A startup check for "is conda installed?" would be meaningless — the issue is using it, not having it.

---

## Verdict: Does the CheckFailed adapter pattern justify itself?

**Yes, but barely for v1. The real payoff is v2.**

### v1 justification (honest)

- **3 checks are genuinely new coverage:** GitHub auth (#1), git identity (#2), pixi env health (#3). These catch real failures that nothing else in the template diagnoses.
- **1 check is high-value but conditional:** Cluster SSH (#4). Only applies if `use_cluster=true`. When it applies, it prevents the single worst UX failure in the template (frozen TUI from SSH timeout).
- **1 check is useful but not critical:** Test collection (#5). Nice-to-have for the testing phase gate.
- **The adapter itself is ~15 lines.** The HintSpec definitions are ~30 lines. Total: ~45 lines of new code for 3-5 real diagnostics. This is small enough to justify.

### What the pattern really enables (v2 and beyond)

- **Tutorial prerequisites:** Before starting a tutorial, run its required checks. "SSH tutorial requires Check 1 + Check 4. Pixi tutorial requires Check 3." Same Check objects, consumed by tutorial prerequisites AND hints.
- **Project health dashboard:** `/check-health` that runs all checks and shows a table. Same objects, third consumer.
- **User-defined checks:** Scientists add checks to `checks.yaml` for their domain (e.g., "can I reach the data server?", "is CUDA available?").

### Recommendation

Keep the feature. The 3-5 genuine checks justify the ~45 lines. But:

1. **Ship only Checks 1-3 in v1.** These have zero external dependencies (GitHub, git, pixi are universal for this template).
2. **Ship Check 4 in v1 only if `use_cluster=true` path is straightforward** — the `${CLUSTER_SSH_TARGET}` variable substitution needs the engine to read copier answers, which it already does via `ProjectState.copier`.
3. **Defer Check 5 to v2** — it's useful but not critical, and it adds pytest as a dependency of the check system itself.
4. **Kill `/check-setup` as a separate feature.** The CheckFailed → hints path IS the discovery mechanism. If someone wants an explicit diagnostic, they can run `/hints` to see all active warnings. Don't build a parallel reporting tool for 3 checks.

---

## Proposed v1 check inventory (final)

| # | Check | Command | Success pattern | Hint on failure | Priority |
|---|---|---|---|---|---|
| 1 | GitHub auth | `git ls-remote .../claudechic.git HEAD` | `[0-9a-f]{40}` | "GitHub auth failed. Run: gh auth login" | 1 (blocking) |
| 2 | Git identity | `git config user.email` | `.+@.+` | "Git email not configured" | 1 (blocking) |
| 3 | Pixi env health | `pixi run python -c "import yaml; print('ok')"` | `ok` | "Pixi environment broken. Try: pixi install --force" | 1 (blocking) |
| 4 | Cluster SSH | `ssh -o ConnectTimeout=5 -o BatchMode=yes ... hostname` | `^[a-zA-Z]` | "Cannot SSH to cluster" | 2 (high-value) |

Check 5 (test collection) deferred to v2.
`/check-setup` slash command cut — CheckFailed hints are sufficient.
