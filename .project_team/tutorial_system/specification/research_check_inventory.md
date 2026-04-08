# Research: Real Check Use Cases — Inventory of Actual Failure Modes

**Author:** Researcher
**Date:** 2026-04-04
**Requested by:** Coordinator
**Tier of best source found:** T1 (codebase, copier.yml, activate script, test suite, rules.yaml)

---

## Method

I traced the full user journey: `copier copy` → `source activate` → first Claude session. At each step, I identified what can fail, what the user sees, and whether a Check could catch it. I also audited every existing hint trigger and every guardrail rule for assumed-but-unchecked prerequisites.

---

## The Real Failure Modes

### Tier A: Things That Actually Break (Blocking Failures)

#### A1. `pixi` not installed, guardrails tell user to use pixi

**How it happens:** User clones a generated project on a new machine (or HPC node). They haven't installed pixi. They start a Claude session. Claude tries to run pytest → R01 fires and says "Use: pixi run pytest -n 8 -v > .test_runs/...". Claude tries pip install → R02 fires and says "Use: pixi add --pypi <package>". User is stuck: guardrails forbid pip/conda, but pixi doesn't exist.

**What a check catches:**
```python
CommandOutputCheck("pixi --version", r"pixi \d+")
# Message: "pixi is not installed — run: curl -fsSL https://pixi.sh/install.sh | bash"
```

**Already a hint?** No. No existing hint checks for pixi. The `activate` script bootstraps pixi (line 50-65), but users who don't source activate first hit this wall.

**Verdict: REAL. This is the #1 failure mode.** Every guardrail rule (R01, R02, R03) assumes pixi exists.

---

#### A2. `pixi install` never run — no environment, no dependencies

**How it happens:** User has pixi but hasn't run `pixi install`. No pytest, no pyyaml, no claudechic in PATH. Every `pixi run` command fails with "environment not found."

**What a check catches:**
```python
FileExistsCheck(".pixi/envs/default")
# Message: "Pixi environment not installed — run: pixi install"
```

**Already a hint?** No. The `activate` script handles this (line 69-82), but again, users who skip activate hit it.

**Verdict: REAL.** This is the second step in the bootstrap chain. Fails silently — user sees cryptic pixi errors.

---

#### A3. `.test_runs/` directory doesn't exist in generated projects

**How it happens:** R01 tells Claude to redirect pytest output to `.test_runs/$(date ...).txt`. But `.test_runs/` is NOT created by the copier template — I confirmed it doesn't exist in `template/`. It only exists in the dev repo because tests created it. In a freshly generated project, the redirect fails with "No such file or directory."

**What a check catches:**
```python
FileExistsCheck(".test_runs")
# Message: "Create .test_runs/ directory for test output — run: mkdir -p .test_runs"
```

**Already a hint?** No. This is a template bug that a check would surface immediately.

**Verdict: REAL.** This is a bug. The template should either create `.test_runs/` or R01's message should include `mkdir -p`.

---

#### A4. `git` not initialized — copier post-task may have failed

**How it happens:** User set `init_git: true` in copier, but git init failed (git not installed, or permissions). Or they set `init_git: false`. Guardrail R04 assumes git exists (`git push`). The `activate` script's git hooks setup (line 107-109) silently skips.

**What a check catches:**
```python
FileExistsCheck(".git")
# Message: "No git repo — run: git init && git add -A && git commit -m 'Initial commit'"
```

**Already a hint?** YES — `GitNotInitialized` trigger already exists in `hints/hints.py` (line 36). It fires as a `ShowUntilResolved` hint with priority 1.

**Verdict: ALREADY COVERED.** This is the model for how checks-as-hints should work. The existing `GitNotInitialized` IS a FileExistsCheck wearing a different hat.

---

#### A5. `generate_hooks.py` failed during copier post-generation

**How it happens:** Copier runs `python3 .claude/guardrails/generate_hooks.py` as a post-task (copier.yml line 129). This requires PyYAML. If PyYAML isn't available (no pixi env yet, system Python doesn't have it), the task fails silently. Result: no hook scripts in `hooks/`, guardrails are dead.

**What a check catches:**
```python
FileExistsCheck(".claude/guardrails/hooks/bash_guard.py")
# Message: "Guardrail hooks not generated — run: python3 .claude/guardrails/generate_hooks.py"
```

**Already a hint?** Partially — `GuardrailsOnlyDefault` checks if rules.yaml has more than R01, but it does NOT check if hooks were actually generated. A project could have 5 rules in rules.yaml but no hook scripts.

**Verdict: REAL.** This is a chicken-and-egg problem: copier runs generate_hooks.py before pixi env exists. The activate script has a staleness check (line 40-47) but only compares timestamps, not existence.

---

#### A6. Guardrail hooks exist but `settings.json` doesn't reference them

**How it happens:** `generate_hooks.py` creates hook scripts AND writes `.claude/settings.json` with hook registrations. If `settings.json` gets deleted, corrupted, or overwritten by Claude Code, hooks exist but are never called. Guardrails silently stop working.

**What a check catches:**
```python
# Check that settings.json exists AND contains hook references
FileExistsCheck(".claude/settings.json")
# Plus a content check:
# settings.json contains "bash_guard.py"
```

**Already a hint?** No.

**Verdict: REAL.** This is a subtle failure — everything looks fine but guardrails are dead.

---

### Tier B: Things That Cause Confusion (Non-Blocking but Costly)

#### B1. Submodule not initialized (developer mode)

**How it happens:** User chose `claudechic_mode: developer` during copier. `git clone` of claudechic submodule may have failed (private repo, no auth). `pixi.toml` references `submodules/claudechic` as editable install. `pixi install` fails with "path not found."

**What a check catches:**
```python
# Only check if pixi.toml references submodules/claudechic as a path dependency
FileExistsCheck("submodules/claudechic/pyproject.toml")
# Message: "claudechic submodule not initialized — run: git submodule update --init --recursive"
```

**Already a hint?** No, but `activate` script handles this (line 111-137).

**Verdict: REAL for developer mode users.** The activate script tries to fix it, but if auth fails, the user sees a warning and nothing more.

---

#### B2. Environment drift — pip packages outside pixi

**How it happens:** User (or Claude via a missed guardrail) runs `pip install foo` directly. Package works now but isn't in pixi.toml. Next `pixi install` doesn't include it. Collaborator clones repo, package is missing.

**What a check catches:**
```python
CommandOutputCheck(
    "pixi run python -c \"import subprocess,json,sys; pip=json.loads(subprocess.run([sys.executable,'-m','pip','list','--format=json'],capture_output=True,text=True).stdout); pixi=json.loads(subprocess.run(['pixi','list','--json'],capture_output=True,text=True).stdout); drift=[p['name'] for p in pip if p['name'].lower() not in {x['name'].lower() for x in pixi}]; print(len(drift))\"",
    r"^0$"
)
```

**Already a check?** YES — `test_env_drift.py` does exactly this as a test. But it only runs when someone runs the test suite. A hint would catch it proactively.

**Verdict: REAL but too complex for a CommandOutputCheck.** Better as a dedicated trigger class (`EnvironmentDriftDetected`) that reuses the logic from `test_env_drift.py`. This is a case where a Python trigger is better than a YAML check.

---

#### B3. Copier answers file missing or corrupt

**How it happens:** User deletes `.copier-answers.yml`, or edits it and introduces a YAML syntax error. Feature flags become unknown. `CopierAnswers.load()` returns all-defaults (graceful), but this means features the user disabled might re-enable, or features they enabled might not get hints.

**What a check catches:**
```python
FileExistsCheck(".copier-answers.yml")
# Message: "Copier answers file missing — template feature flags may be incorrect"
```

**Already a hint?** No. `CopierAnswers.load()` silently falls back to defaults (line 42-53 of `_state.py`).

**Verdict: MARGINAL.** Graceful degradation is correct behavior. But a warning hint would help users understand why features appear/disappear.

---

### Tier C: Tutorial-Specific Checks

These only matter inside a tutorial workflow, not as standalone hints.

#### C1. pytest installed and runnable (First Pytest tutorial)

```python
CommandOutputCheck("pixi run pytest --version", r"pytest \d+")
```

**Verdict: REAL for tutorials, redundant with A2 for general use.** If pixi env is installed, pytest is there (it's a base dependency).

#### C2. Test file created (First Pytest tutorial gate)

```python
FileExistsCheck("tests/test_example.py")
```

**Verdict: REAL as a tutorial gate check.** Not useful as a standalone hint.

---

## What Existing Hints Already Check (and What They Miss)

| Existing Hint | What It Checks | What It Misses |
|---|---|---|
| `GitNotInitialized` | `.git` exists | git executable exists; git user.email configured |
| `GuardrailsOnlyDefault` | rules.yaml has >1 rule OR rules.d/ has files | Hook scripts actually generated; settings.json references them |
| `ProjectTeamNeverUsed` | `.ao_project_team` exists | N/A — discovery hint, not a health check |
| `PatternMinerUnderutilized` | session_count ≥ 10 AND no state file | N/A — feature hint |
| `McpToolsEmpty` | mcp_tools/*.py count = 0 | N/A — feature hint |
| `ClusterConfiguredUnused` | cluster_jobs/ and logs/cluster don't exist | Cluster SSH target reachable; scheduler available |

**Pattern:** Existing hints check for feature discovery ("you haven't tried X"). None of them check for environment health ("X is broken"). The Check primitive fills a gap the hint system wasn't designed for — but can absorb trivially.

---

## The Real Check Inventory (v1 Recommendation)

Based on actual failure modes, here are the checks worth building. Ordered by user impact:

### Must-have (blocks basic usage)

| ID | Check | Type | Trigger When | Message |
|---|---|---|---|---|
| `pixi-installed` | `pixi --version` outputs version | CommandOutputCheck | Missing pixi | "pixi not installed — run: curl -fsSL https://pixi.sh/install.sh \| bash" |
| `pixi-env-ready` | `.pixi/envs/default` exists | FileExistsCheck | Missing env | "Pixi environment not installed — run: pixi install" |
| `test-runs-dir` | `.test_runs` exists | FileExistsCheck | Missing dir | "Create .test_runs/ for test output — run: mkdir -p .test_runs" |
| `hooks-generated` | `.claude/guardrails/hooks/bash_guard.py` exists | FileExistsCheck | Missing hooks | "Guardrail hooks missing — run: python3 .claude/guardrails/generate_hooks.py" |

### Should-have (prevents confusion)

| ID | Check | Type | Trigger When | Message |
|---|---|---|---|---|
| `settings-json-valid` | `.claude/settings.json` exists and contains "hooks" | File content check | Missing/broken settings | "Claude Code settings missing hook config — run: python3 .claude/guardrails/generate_hooks.py" |
| `git-user-configured` | `git config user.email` returns something | CommandOutputCheck | No git identity | "git user.email not set — run: git config --global user.email 'you@example.com'" |
| `submodule-init` | `submodules/claudechic/pyproject.toml` exists (only if developer mode) | FileExistsCheck | Submodule missing | "claudechic submodule not initialized — run: git submodule update --init --recursive" |

### Nice-to-have (catches drift)

| ID | Check | Type | Trigger When | Message |
|---|---|---|---|---|
| `hooks-fresh` | rules.yaml not newer than settings.json | Timestamp comparison | Stale hooks | "Guardrail rules changed — run: python3 .claude/guardrails/generate_hooks.py" |

---

## Which Checks Work as Hints vs. Which Need /check-setup

| Check | As Hint? | As /check-setup? | Why |
|---|---|---|---|
| `pixi-installed` | **YES** — priority 1, ShowUntilResolved | Also yes | Blocks everything; must surface proactively |
| `pixi-env-ready` | **YES** — priority 1, ShowUntilResolved | Also yes | Same reason |
| `test-runs-dir` | **YES** — priority 2, ShowUntilResolved | Also yes | Blocks R01 compliance |
| `hooks-generated` | **YES** — priority 1, ShowUntilResolved | Also yes | Silent guardrail death |
| `settings-json-valid` | **YES** — priority 2, ShowUntilResolved | Also yes | Silent guardrail death |
| `git-user-configured` | **YES** — priority 2, ShowOnce | Also yes | One-time setup |
| `submodule-init` | Conditional — only in dev mode | Also yes | Needs CopierAnswers check |
| `hooks-fresh` | **YES** — priority 3, ShowUntilResolved | Also yes | activate script also checks |

**Every real check works as a hint.** The hint pipeline is the better primary surface — proactive, not reactive. `/check-setup` survives as a batch diagnostic ("show me everything at once").

---

## Recommendations for the Spec

### 1. The Check primitive earns its keep

These are real failures hitting real users. The Check primitive is justified — not by hypothetical SSH tutorials, but by the template's own bootstrap chain:

```
pixi installed? → pixi env ready? → hooks generated? → settings.json valid? → .test_runs/ exists?
```

Each step depends on the previous. A failing early step cascades silently.

### 2. FileExistsCheck handles 5 of 8 checks

Most real checks are "does this file/directory exist?" — exactly what `FileExistsCheck` does, and exactly what existing triggers already do via `ProjectState.path_exists()`. The `CheckTrigger` adapter from the previous research applies directly.

### 3. CommandOutputCheck handles 2 of 8 checks

Only `pixi --version` and `git config user.email` need command execution. Both are fast (<500ms). The contract relaxation is minimal.

### 4. Fix the `.test_runs/` bug now

The template should create `.test_runs/.gitkeep` so it exists in generated projects. This is a bug, not a check use case. The check catches it for existing projects that were generated before the fix.

### 5. Drop the SSH example from the spec

"SSH key exists" is a contrived example that doesn't match this template's actual user journey. Replace spec examples with these real checks. The pixi bootstrap chain is a much better motivating example.

### 6. `EnvironmentDriftDetected` should be a Python trigger, not a YAML check

The env drift detection from `test_env_drift.py` is too complex for CommandOutputCheck but valuable as a trigger. Build it as a proper `TriggerCondition` class like the existing ones — not as a Check.
