# Bootstrapping Bridge Specification

## 1. Problem Statement

The AI_PROJECT_TEMPLATE has a two-phase onboarding that currently has a seam between the phases:

1. **Copier** (generation time) asks intent questions (`use_cluster?`, `init_git?`, `use_existing_codebase?`), generates config stubs, and exits.
2. **Runtime workflows** (after activation) re-detect everything from scratch, ignoring what Copier already collected.

The user experiences this as redundant questioning, disconnected setup steps, and no unified view of what's configured vs. what still needs attention. Six specific seams exist today:

| Seam | Copier Side | Runtime Side | Gap |
|------|------------|--------------|-----|
| Cluster | Asks intent only (`use_cluster`); generates both MCP backends | cluster_setup workflow handles SSH target, scheduler detection, config | Copier generates files; workflow configures them |
| Git | Runs `git init` + initial commit | `/git_setup` skill exists but is disconnected | No trigger for remote setup |
| Codebase | Asks path + link mode, integrates at generation | No workflow for late addition | One-shot, non-interactive |
| Claudechic mode | standard vs developer choice | No transition path | Mode locked at generation |
| Quick-start presets | Conditional file generation | Workflows may assume features exist | No runtime awareness of what was included |
| MCP tools | Conditionally generated | No way to add tools later | One-shot only |

## 2. Solution: Welcome Screen

### Mental Model

Onboarding is a **welcome screen** — a UI panel that appears at session start, shows a checklist of setup items with live status, and lets the user choose which one to work on.

```
Session starts
  -> claudechic reads .copier-answers.yml (CopierAnswers, already exists)
  -> checks real state: SSH works? git remote exists? codebase integrated?
  -> builds checklist of setup items with status
  -> if any incomplete: renders welcome screen
  -> user picks one -> that facet workflow activates, welcome screen closes
  -> OR user closes/skips -> screen goes away, reappears next session
  -> OR user clicks "Don't show again" -> permanent dismiss
  -> next session: welcome screen reappears with updated status
  -> when everything is configured: welcome screen doesn't appear
```

No `/onboard` command. No onboarding workflow. No MCP tool. No workflow queue. A visual checklist that the user interacts with directly.

### Key Design Decisions

1. **`.copier-answers.yml` is the only bridge.** The `CopierAnswers` class already exists in claudechic core. Copier records intent (bool flags); facet workflows handle details interactively.

2. **Copier asks intent, workflows handle details.** A consistent pattern across all three facets: Copier asks a single bool (`use_cluster`, `init_git`, `use_existing_codebase`) and generates files. Workflows handle interactive configuration (SSH targets, scheduler detection, remote URLs, codebase paths, link modes). This reduces Copier questions from 15 to 12.

3. **Onboarding is a welcome screen, not a workflow.** It renders once at session start, shows status, and lets the user pick. No persistent onboarding state beyond a dismiss marker.

4. **User chooses which facet to work on.** The welcome screen presents all incomplete facets. The user selects one. No forced ordering, no auto-start. Full agency.

5. **One facet per session.** After the user selects a facet workflow and completes it, the session ends naturally. The next session's welcome screen shows updated status with the completed facet checked off. This keeps context windows fresh and avoids marathon setup sessions.

6. **Facet workflows are standalone.** `cluster-setup` (PR #18), `git-setup` (new), and `codebase-setup` (new) are independent workflows. They don't know about onboarding. They can be run at any time via their own slash commands.

7. **Workflows always re-verify.** Copier answers are hints, not truth. The welcome screen probes actual state (SSH connectivity, git remote existence). Facet workflows re-validate everything.

8. **Three-option dismiss model.** The welcome screen offers: select a facet (run it), close/skip (reappears next session), "Don't show again" (permanent dismiss, never shown again).

9. **Facet map is hardcoded.** The welcome screen logic hardcodes which CopierAnswers keys map to which facet workflows (~15 lines). No config file, no manifest discovery.

## 3. Terminology

| Term | Definition |
|------|-----------|
| **Onboarding** | The welcome screen that detects incomplete setup and lets the user pick a facet workflow |
| **Welcome screen** | The UI panel/overlay rendered at session start showing setup status |
| **Facet** | One independent setup concern (cluster, git, codebase) |
| **Facet workflow** | A standalone workflow handling one facet (e.g., `cluster-setup`, `git-setup`, `codebase-setup`) |
| **CopierAnswers** | The class that reads `.copier-answers.yml` |
| **Dismiss marker** | Flag indicating the user chose "Don't show again" |

## 4. Architecture

### 4.1 Component Overview

```
.copier-answers.yml              <-- bridge (Copier writes, claudechic reads)
claudechic core:
  welcome screen widget           <-- reads CopierAnswers, checks state, renders checklist
  dismiss marker                   <-- field in hints_state.json
workflows/cluster_setup/          <-- facet workflow (PR #18, minor updates)
  cluster_setup.yaml
  cluster_setup_helper/
    identity.md, detect.md, ...
workflows/git_setup/              <-- facet workflow (new)
  git_setup.yaml
  git_setup_helper/
    identity.md, init.md, remote.md, push.md, hooks.md
workflows/codebase_setup/         <-- facet workflow (new)
  codebase_setup.yaml
  codebase_setup_helper/
    identity.md, locate.md, integrate.md, environment.md, verify.md
```

### 4.2 Welcome Screen (claudechic core)

Renders automatically when a new claudechic session begins and setup is incomplete.

**Logic:**

```python
async def _check_onboarding(self) -> None:
    """Session-start onboarding check. Reads CopierAnswers, probes real
    state, and renders welcome screen if setup is incomplete."""

    # 1. Bail out early
    if self._onboarding_dismissed():
        return
    answers = CopierAnswers.load()  # returns None if no .copier-answers.yml
    if answers is None:
        return

    # 2. Build checklist of facet statuses
    facets: list[FacetStatus] = []  # (workflow_id, label, configured: bool, detail: str)

    if answers.get("use_cluster"):
        configured = self._cluster_configured()
        detail = self._cluster_detail() if configured else "not configured"
        facets.append(FacetStatus("cluster-setup", "Cluster access", configured, detail))

    git_configured = self._git_remote_configured()
    detail = self._git_detail() if git_configured else "no remote set"
    facets.append(FacetStatus("git-setup", "Git remote", git_configured, detail))

    if answers.get("use_existing_codebase"):
        configured = self._codebase_configured()
        detail = "integrated" if configured else "not integrated"
        facets.append(FacetStatus("codebase-setup", "Codebase integration", configured, detail))

    # 3. If everything is configured, don't show
    if all(f.configured for f in facets):
        return

    # 4. Render welcome screen
    choice = await self._show_welcome_screen(facets)
    #   workflow_id     -> activate that workflow
    #   "skip"          -> do nothing, show again next session
    #   "dont_show"     -> write dismiss marker, never show again

    if choice == "dont_show":
        self._write_dismiss_marker()
    elif choice == "skip":
        pass  # welcome screen closes, normal session continues
    else:
        await self._activate_workflow(choice)  # choice is a workflow_id
```

**Welcome screen rendering:**

```
┌─────────────────────────────────────────────┐
│  Welcome to your project! Setup status:     │
│                                             │
│  ○ Cluster access    — not configured       │
│  ✔ Git remote        — origin → github/foo  │
│  ○ Codebase integration — not integrated    │
│                                             │
│  Select an unconfigured item to set it up,  │
│  or press [Skip] to start working.          │
│                                             │
│  [Skip]  [Don't show again]                 │
└─────────────────────────────────────────────┘
```

- Configured items show ✔ with detail (e.g., "LSF on login.hpc.edu", "origin → github.com/user/repo").
- Unconfigured items show ○ and are selectable (clickable or keyboard-navigable).
- Selecting an unconfigured item activates that facet workflow and closes the welcome screen.
- [Skip] closes the screen for this session. It reappears next session.
- [Don't show again] writes the dismiss marker. Screen never appears again.

**Health checks (called by the welcome screen logic):**

| Facet | Check | "Configured" means |
|-------|-------|-------------------|
| cluster | `_cluster_configured()` | `mcp_tools/cluster.yaml` has non-empty `backend` AND non-empty `ssh_target` AND `ssh -o BatchMode=yes <target> echo ok` succeeds. OR local scheduler detected (`which bsub` or `which sbatch`). |
| git | `_git_remote_configured()` | `.git/` exists AND `git remote get-url origin` succeeds |
| codebase | `_codebase_configured()` | At least one non-hidden directory exists in `repos/` |

**The checks run synchronously at session start.** SSH check has a 5-second timeout. If it times out, the facet is marked as needing setup. Git and codebase checks are local and instant.

### 4.3 Workflow Activation from Welcome Screen

When the user selects a facet, the welcome screen calls `_activate_workflow(workflow_id)`. This is the existing workflow activation mechanism, with one small change:

**Bypass chicsession naming prompt.** When activated from the welcome screen, the workflow uses its workflow ID as the chicsession name automatically (e.g., "cluster-setup"). No interactive naming prompt.

This requires a minor refactor to `_activate_workflow()` — add an optional `auto_name: str | None` parameter that, when provided, skips the naming prompt and uses the given name directly.

### 4.4 Dismiss Marker

When the user chooses "Don't show again", a dismiss marker is written as a field in `hints_state.json`: `{"onboarding_dismissed": true}`. This reuses existing infrastructure and is already managed atomically.

**Dismiss is permanent.** No auto-reset. If the user dismisses and later runs `copier update`, they run facet workflows manually via slash commands.

## 5. Facet Specifications

### 5.1 Cluster Facet

**Copier side:** Copier asks only `use_cluster` (bool). The `cluster_scheduler` (enum) and `cluster_ssh_target` (str) questions are removed from `copier.yml`. When `use_cluster == true`, Copier includes all cluster files: `_cluster.py`, `lsf.py`, `slurm.py`, and `mcp_tools/cluster.yaml`. Both backends ship; the workflow configures the appropriate one.

**Single config file: `mcp_tools/cluster.yaml`** replaces the per-scheduler `lsf.yaml` + `slurm.yaml`:
```yaml
# mcp_tools/cluster.yaml -- single config, backend field selects scheduler
backend: ""              # lsf | slurm -- detected by cluster-setup workflow
ssh_target: ""           # filled by workflow
lsf_profile: ""          # LSF-specific (e.g., /misc/lsf/conf/profile.lsf)
watch_poll_interval: 30
remote_cwd: ""
path_map: []
log_access: auto
```

**Copier `_exclude` changes:** The existing per-scheduler conditionals are replaced with a single `use_cluster` gate:
```yaml
# Before: per-scheduler exclusion (4 separate conditionals)
- "{% if not use_cluster or cluster_scheduler != 'lsf' %}mcp_tools/lsf.py{% endif %}"
# After: all cluster files gated on use_cluster only
- "{% if not use_cluster %}mcp_tools/_cluster.py{% endif %}"
- "{% if not use_cluster %}mcp_tools/lsf.py{% endif %}"
- "{% if not use_cluster %}mcp_tools/slurm.py{% endif %}"
- "{% if not use_cluster %}mcp_tools/cluster.yaml{% endif %}"
```

**Recommendation:** Consider merging `lsf.py` and `slurm.py` into a single `cluster.py` that dispatches based on the `backend` field in `cluster.yaml`. This is an implementation detail -- either approach works.

**Facet workflow:** `cluster-setup` (PR #18, with updates to detect and apply phases). Seven phases:
1. detect -- ask user for SSH target, test reachability
2. ssh_auth -- verify passwordless SSH
3. ssh_mux -- set up connection pooling
4. scheduler -- detect which scheduler is available (LSF or SLURM), write `backend` field
5. paths -- configure path mappings and remote_cwd
6. validate -- end-to-end validation with real job
7. apply -- write final config to `mcp_tools/cluster.yaml`

**No pre-population:** Copier does not write `ssh_target` or `backend` into `cluster.yaml`. The workflow starts fresh. Copier generates files, workflow configures them.

**Welcome screen check:** `use_cluster == true` in CopierAnswers AND `cluster.yaml` has empty `backend` or empty `ssh_target` or SSH fails AND no local scheduler detected -> show as unconfigured.

**Independent usage:** `/cluster-setup` works at any time, outside of onboarding.

### 5.2 Git Facet

**Copier side:** `init_git == true` triggers `git init && git add -A && git commit -m "Initial project"` in `_tasks`. No remote setup.

**Facet workflow:** `git-setup` (new standalone workflow). Never skipped by onboarding -- git is always relevant.

```yaml
# workflows/git_setup/git_setup.yaml
workflow_id: git-setup
main_role: git_setup_helper

phases:
  - id: init
    file: init
    hints:
      - message: "Checking git initialization status..."
        lifecycle: show-once
    advance_checks:
      - type: command-output-check
        command: "git rev-parse --git-dir 2>/dev/null || echo no_git"
        pattern: "\\.git"
      - type: manual-confirm
        prompt: "Git repository initialized?"

  - id: remote
    file: remote
    hints:
      - message: "Configuring git remote. Will offer to create a GitHub repo if needed."
        lifecycle: show-once
    advance_checks:
      - type: command-output-check
        command: "git remote get-url origin 2>/dev/null || echo no_remote"
        pattern: "^(?!no_remote)"
      - type: manual-confirm
        prompt: "Git remote configured?"

  - id: push
    file: push
    advance_checks:
      - type: manual-confirm
        prompt: "Initial commit pushed to remote?"

  - id: hooks
    file: hooks
    advance_checks:
      - type: manual-confirm
        prompt: "Repository settings configured (or skipped)?"
```

**Phase details:**

| Phase | What It Does | Auto-Fixable? |
|-------|-------------|---------------|
| **init** | Check `git rev-parse --git-dir`. If no repo, offer `git init && git add -A && git commit`. | Yes |
| **remote** | Check `git remote get-url origin`. If none, detect `gh` CLI, offer `gh repo create --private`. Fall back to `git remote add`. | Partially (needs user auth) |
| **push** | If remote exists but no upstream, run `git push -u origin main`. Handle branch naming. | Yes |
| **hooks** | Optional: offer branch protection via `gh api`, configure `.githooks/`, set up pre-commit. User can skip. | Yes |

**Welcome screen check:** Always checks git state. No remote -> show as unconfigured.

**Independent usage:** `/git-setup` works at any time, outside of onboarding.

### 5.3 Codebase Facet

**Copier side:** Copier asks only `use_existing_codebase` (bool). No path, no link mode. Copier does NOT run `integrate_codebase.py` as a `_task`. The `existing_codebase` (str path) and `codebase_link_mode` (enum) questions are removed from `copier.yml`. The `_tasks` entry for codebase integration is removed. Copier just records the intent; the workflow does the work.

**Facet workflow:** `codebase-setup` (new standalone workflow).

```yaml
# workflows/codebase_setup/codebase_setup.yaml
workflow_id: codebase-setup
main_role: codebase_setup_helper

phases:
  - id: locate
    file: locate
    hints:
      - message: "Locating the existing codebase to integrate..."
        lifecycle: show-once
    advance_checks:
      - type: manual-confirm
        prompt: "Codebase path confirmed and validated?"

  - id: integrate
    file: integrate
    hints:
      - message: "Integrating codebase into repos/ directory..."
        lifecycle: show-once
    advance_checks:
      - type: command-output-check
        command: "ls -d repos/*/ 2>/dev/null | head -1"
        pattern: "repos/"
      - type: manual-confirm
        prompt: "Codebase integrated into repos/?"

  - id: environment
    file: environment
    hints:
      - message: "Scanning codebase for dependencies and configuring environment..."
        lifecycle: show-once
    advance_checks:
      - type: manual-confirm
        prompt: "Environment configured and dependencies resolved?"

  - id: verify
    file: verify
    advance_checks:
      - type: manual-confirm
        prompt: "Imports work and codebase is functional?"
```

**Phase details:**

| Phase | What It Does | Auto-Fixable? |
|-------|-------------|---------------|
| **locate** | Ask user for codebase path. Validate it exists. Check if it's a git repo, a Python package, or a plain directory. Identify the top-level module name. | No (needs user input) |
| **integrate** | Determine integration method: symlink (saves disk, changes reflect immediately) vs copy (works everywhere). Place in `repos/`. Validate the link/copy succeeded. | Yes |
| **environment** | Scan codebase for `requirements.txt`, `setup.py`, `pyproject.toml`, `environment.yml`. Propose a pixi feature/environment with the discovered dependencies. Add `repos/<name>` to PYTHONPATH (activate script already handles this). | Partially |
| **verify** | Test that `import <module>` works from the project root. If existing tests are found (`tests/`, `pytest.ini`), offer to run them. Report any import errors or missing dependencies. | Yes |

**Welcome screen check:** `use_existing_codebase == true` in CopierAnswers AND no directory in `repos/` -> show as unconfigured.

**Independent usage:** `/codebase-setup` works at any time, outside of onboarding.

## 6. Late Addition

When a user wants to add a facet that was skipped at generation time:

1. Run `copier update` and change answers (e.g., `use_cluster: false` -> `true`, or `use_existing_codebase: false` -> `true`)
2. Copier generates the previously-excluded files and updates `.copier-answers.yml`
3. On next session, the welcome screen detects the new intent vs. unconfigured state
4. If not dismissed: welcome screen shows the new facet as unconfigured alongside any others
5. If dismissed: user runs the facet workflow manually (e.g., `/cluster-setup`, `/codebase-setup`)

`copier update` handles file generation. Facet workflows handle configuration. The welcome screen handles detection for users who haven't dismissed it.

## 7. Re-Entry

### Within a session (chicsession handles it)

User quits mid-cluster-setup. On resume:
- Chicsession restores `cluster-setup` at whatever phase they were on
- User continues from where they left off

### Across sessions (welcome screen handles it)

User completes cluster-setup, quits. Next session:
- Welcome screen runs: cluster SSH works (✔), git remote missing (○)
- Welcome screen shows updated checklist with cluster checked off
- User selects git-setup to continue onboarding

### Fully configured project

Welcome screen finds everything configured. No screen shown. Invisible.

## 8. Technical Constraints

### Existing Infrastructure

| Component | Location | How We Use It |
|-----------|----------|---------------|
| `CopierAnswers` class | claudechic core | Read `.copier-answers.yml` |
| `_check_config_readiness()` | `mcp_tools/_cluster.py` | Pattern for cluster health check |
| `WorkflowEngine` | claudechic core | Phase management for facet workflows |
| `hints_state.json` | claudechic core | Store dismiss marker |
| Chicsession persistence | claudechic core | Resume interrupted workflows |

### Required Core Changes

| Change | File | Description | Lines |
|--------|------|-------------|-------|
| Welcome screen widget | `widgets/` | Checklist UI with status, selection, skip, dismiss | ~50-80 |
| Health check functions | `app.py` or `onboarding.py` | `_cluster_configured()`, `_git_remote_configured()`, `_codebase_configured()` | ~30 |
| `_activate_workflow` refactor | `app.py` | Add `auto_name` parameter to bypass chicsession naming prompt | ~15 |
| Dismiss marker | `app.py` | Write/read `onboarding_dismissed` in `hints_state.json` | ~5 |
| Session-start hook | `app.py` | Call `_check_onboarding()` after manifest loading, before first input | ~5 |
| **Total** | | | **~100-130** |

## 9. Implementation Plan

### Phase A: Copier Simplification

1. Update `copier.yml`: remove `cluster_scheduler` and `cluster_ssh_target` questions
2. Update `copier.yml`: replace `existing_codebase` (str path) + `codebase_link_mode` (enum) with `use_existing_codebase` (bool). Remove the `integrate_codebase.py` `_task`.
3. Update `_exclude` in `copier.yml`: replace per-scheduler conditionals with single `use_cluster` gate
4. Replace `lsf.yaml.jinja` + `slurm.yaml.jinja` with single `cluster.yaml.jinja` (empty `backend` and `ssh_target`)

**Delivers:** Consistent intent-only Copier pattern across all facets. Questions reduced from 15 to 12. Template ready for the new workflows.

### Phase B: Welcome Screen + Health Checks

1. Implement health check functions: `_cluster_configured()`, `_git_remote_configured()`, `_codebase_configured()`
2. Build welcome screen widget (checklist UI with status indicators, selection, skip, dismiss)
3. Add permanent dismiss marker to `hints_state.json`
4. Refactor `_activate_workflow()` to accept optional `auto_name` parameter
5. Wire into session startup (call after manifest loading, before first user input)

**Delivers:** Welcome screen appears at session start showing setup status. User selects a facet to work on, skips, or permanently dismisses.

### Phase C: `git-setup` Facet Workflow

1. Create `workflows/git_setup/git_setup.yaml` with 4 phases (init, remote, push, hooks)
2. Create `workflows/git_setup/git_setup_helper/` role files
3. Test standalone (`/git-setup`) and welcome-screen-activated paths

**Delivers:** Git remote setup as a guided workflow, accessible from welcome screen.

### Phase D: `codebase-setup` Facet Workflow

1. Create `workflows/codebase_setup/codebase_setup.yaml` with 4 phases (locate, integrate, environment, verify)
2. Create `workflows/codebase_setup/codebase_setup_helper/` role files
3. Test standalone (`/codebase-setup`) and welcome-screen-activated paths

**Delivers:** Codebase integration as an interactive guided workflow. Replaces the non-interactive Copier `_task`.
