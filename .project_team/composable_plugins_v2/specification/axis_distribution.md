# Axis Deep-Dive: Claudechic Distribution Mode

> **Status:** Draft v1
> **Date:** 2026-03-30
> **Axis:** Claudechic Distribution Mode
> **Values:** `git-url` (standard) | `editable-local` (developer)
> **Seam:** `import claudechic` — downstream code is blind to installation method

---

## 1. Standard Mode (git URL)

### pixi.toml Entry

```toml
[pypi-dependencies]
claudechic = { git = "https://github.com/boazmohar/claudechic", branch = "main" }
```

### Reproducibility: pixi.lock Pins Exact SHA

**Yes — pixi.lock pins the full commit SHA, not just the branch name.** When pixi resolves a git URL dependency, it records the URL as `git+https://github.com/boazmohar/claudechic@<40-char-commit-sha>` in pixi.lock. This means:

- Two developers running `pixi install` from the same pixi.lock get the **exact same claudechic code** — byte-for-byte reproducibility.
- The branch name (`main`) is only used during resolution to find the current HEAD; the lock file records the concrete commit.
- This was verified against pixi's uv-based PyPI resolution engine. Historical bugs in this area (pixi issues #3367, #2865) have been fixed (PRs #3425, #4874).

### Update Workflow

```bash
# Pull latest claudechic from main branch
pixi update claudechic
# → pixi.lock updated with new SHA
# → next `pixi install` gets the new code

# Or update everything
pixi update
```

**Key distinction:** `pixi install` respects the existing lock file — it does NOT pull new commits. Only `pixi update` re-resolves and fetches the latest branch HEAD. This is the correct behavior: reproducibility by default, explicit opt-in to updates.

### pixi-pack Compatibility (Offline HPC)

**⚠️ pixi-pack does NOT support git URL pypi-dependencies.**

pixi-pack only handles wheel packages from PyPI registries and conda packages from conda-forge. Git URL dependencies require cloning + building from source, which pixi-pack cannot do.

**Impact:** For offline/air-gapped HPC deployment, the current v1 approach (committed submodule or editable local path) is still needed. The git URL mode requires network access during `pixi install`.

**Mitigation options (future, not v2 scope):**
1. Publish claudechic to a private PyPI registry (e.g., Artifactory, devpi) — pixi-pack can then pack it as a wheel.
2. Use pixi-pack with `--ignore-pypi-non-wheel` and handle claudechic installation separately in the activate script.
3. Pre-build a wheel and commit it to the template (ugly but functional).

**v2 recommendation:** Document that standard mode requires network access for initial `pixi install`. For air-gapped HPC, use developer mode (editable-local) with the claudechic code present locally. This is an acceptable tradeoff — the template already requires network for `pixi install` of conda packages unless pixi-pack is used.

### What's NOT Needed in Standard Mode

- **No `.gitmodules`** — pixi handles the git clone internally in its cache.
- **No `submodules/claudechic/` directory** — the code lives in pixi's internal cache (`.pixi/`).
- **No submodule auto-init** — activate script Section 5 is skipped (no `.gitmodules` to check).
- **No `git submodule update --init`** — pixi is the package manager, not git.

---

## 2. Developer Mode (Editable Local)

### pixi.toml Entry

```toml
[pypi-dependencies]
claudechic = { path = "submodules/claudechic", editable = true }
```

### Clone Location

`submodules/claudechic/` — consistent with v1 convention. This directory:
- Contains a full git clone of the claudechic repository
- Has its own `.git/` directory (it's an independent repo, not a git submodule)
- Must contain a `pyproject.toml` with a valid build system

### .gitmodules: NOT Required

Developer mode does **not** use git submodules. The `submodules/claudechic/` directory is:
- **Manually cloned** by the developer (`git clone https://github.com/boazmohar/claudechic submodules/claudechic`)
- **Listed in `.gitignore`** so the parent project doesn't track it
- **Not a git submodule** — no `.gitmodules` entry, no `git submodule` commands

This is simpler than v1's actual git submodule approach. The directory name `submodules/` is a v1 legacy convention — it's just a local clone location.

### Why Editable?

`editable = true` means changes to files in `submodules/claudechic/` take effect immediately without reinstalling. This is the whole point of developer mode — hack on claudechic, see changes in real-time.

---

## 3. Onboarding Flow (Copier)

### Question Wording

```yaml
claudechic_mode:
  type: str
  choices:
    standard: "Standard — installs from git, updates via pixi update (recommended)"
    developer: "Developer — clones locally for hacking on claudechic itself"
  default: "standard"
  help: |
    Standard mode: claudechic installed from git URL. You get updates with `pixi update`.
    Developer mode: claudechic cloned into submodules/claudechic/ for local editing.
    You can switch between modes later by changing one line in pixi.toml.
```

### Files That Differ Between Modes

| File | Standard Mode | Developer Mode |
|------|--------------|----------------|
| `pixi.toml` (one line) | `claudechic = { git = "https://github.com/boazmohar/claudechic", branch = "main" }` | `claudechic = { path = "submodules/claudechic", editable = true }` |
| `.gitignore` | No `submodules/` entry needed | `submodules/claudechic/` entry present |
| `submodules/claudechic/` | Does not exist | Created by Copier post-generation hook (`git clone`) |

**That's it.** Two files differ, and only one line in pixi.toml is the functional difference. The `.gitignore` entry is a safety measure, not a runtime concern.

### Default: Standard Mode

Standard mode is the default because:
- It's simpler (no local clone to manage)
- It's reproducible (pixi.lock pins exact SHA)
- It auto-updates with `pixi update`
- Most users consume claudechic, they don't develop it

### Copier Post-Generation Hook (Developer Mode Only)

When developer mode is selected, Copier's post-generation hook runs:

```python
# In copier.yml post_generate tasks
if claudechic_mode == "developer":
    subprocess.run(["git", "clone", "https://github.com/boazmohar/claudechic", "submodules/claudechic"])
```

---

## 4. Swap Test

### Standard → Developer

```bash
# 1. Clone claudechic locally
git clone https://github.com/boazmohar/claudechic submodules/claudechic

# 2. Change one line in pixi.toml
# FROM: claudechic = { git = "https://github.com/boazmohar/claudechic", branch = "main" }
# TO:   claudechic = { path = "submodules/claudechic", editable = true }

# 3. Reinstall
pixi install
```

**Files changed:** `pixi.toml` (one line), `pixi.lock` (re-resolved). **No other file changes.**

### Developer → Standard

```bash
# 1. Change one line in pixi.toml
# FROM: claudechic = { path = "submodules/claudechic", editable = true }
# TO:   claudechic = { git = "https://github.com/boazmohar/claudechic", branch = "main" }

# 2. Reinstall
pixi install

# 3. (Optional) Remove local clone
rm -rf submodules/claudechic
```

**Files changed:** `pixi.toml` (one line), `pixi.lock` (re-resolved). **No other file changes.**

### Does ANY Other File Change? **NO.**

| File/System | Changes on swap? | Why |
|-------------|-----------------|-----|
| `pixi.toml` | YES (one line) | The axis value lives here |
| `pixi.lock` | YES (re-resolved) | Lock file always regenerates on dependency change |
| `activate` script | NO | Doesn't know or care about distribution mode |
| `.claude/` anything | NO | Skills, hooks, settings are distribution-blind |
| `AI_agents/` anything | NO | Agent roles don't reference distribution mode |
| `commands/` anything | NO | Commands use `pixi run`, not direct claudechic paths |
| `mcp_tools/` anything | NO | MCP tools import claudechic, don't know how it's installed |
| `.claudechic.yaml` | NO | Runtime config, not installation config |

**The seam is clean. The swap test passes perfectly.**

---

## 5. Edge Cases

### 5.1 Private Repo Access

**Not an issue for v2.** `https://github.com/boazmohar/claudechic` is a public fork. HTTPS access works without SSH keys or tokens.

If the repo were ever made private:
- HTTPS URL would require a GitHub personal access token (configured via `git config` or environment variable)
- SSH URL (`git = "git@github.com:boazmohar/claudechic"`) would require SSH keys
- pixi delegates git operations to the system `git`, so standard git authentication works

### 5.2 Version Pinning Options

pixi supports three git reference specifiers:

```toml
# Track a branch (standard mode default)
claudechic = { git = "https://github.com/boazmohar/claudechic", branch = "main" }

# Pin to a release tag
claudechic = { git = "https://github.com/boazmohar/claudechic", tag = "v1.0" }

# Pin to exact commit (maximum reproducibility)
claudechic = { git = "https://github.com/boazmohar/claudechic", rev = "abc123def456..." }
```

**v2 recommendation:** Use `branch = "main"` as default. The pixi.lock already pins the exact SHA, so reproducibility is guaranteed. Tags can be used when the claudechic fork creates releases. The `rev` option is available for extreme pinning needs but is rarely practical.

### 5.3 Conflict: Both Git URL and Local Path

**Impossible.** TOML keys are unique within a table. Two `claudechic = ...` lines in `[pypi-dependencies]` would either:
- Override each other (last one wins) — unlikely to be what the user intended
- Cause a TOML parse error in strict mode

**The pixi feature system could theoretically enable both** (git URL in default, editable in a `dev` feature), but this adds unnecessary complexity. For v2, it's one or the other — swapped by editing the single line.

### 5.4 pixi-pack + Developer Mode

Developer mode (`path = "submodules/claudechic", editable = true`) also does NOT work with pixi-pack. Editable/local path dependencies are not packable. However, in developer mode the code is already local, so pixi-pack is less relevant — the user has the code on-disk.

### 5.5 Activate Script Compatibility

The activate script (Section 5: Submodule Auto-Init) currently checks:
```bash
if [[ -f ".gitmodules" ]] && grep -q claudechic .gitmodules; then
    git submodule update --init submodules/claudechic
fi
```

In v2:
- **Standard mode:** No `.gitmodules` file → Section 5 is a no-op. ✓
- **Developer mode:** No `.gitmodules` file (we don't use git submodules) → Section 5 is a no-op. ✓
- **v1 projects with actual submodules:** `.gitmodules` exists → Section 5 runs as before. Backward compatible. ✓

**No changes needed to the activate script for this axis.**

---

## 6. Compositional Law

**Law 2 (Package Identity Law):** Claudechic is a Python package. How it's installed (git URL vs editable local) is invisible to all consumers. The seam is `import claudechic`.

**What this means concretely:**
- No code anywhere checks `claudechic.__file__` to determine installation mode
- No code checks for the existence of `submodules/claudechic/`
- No conditional logic branches on distribution mode
- The activate script doesn't display distribution mode (it doesn't matter at runtime)

**Enforcement:** Any code that does `if os.path.exists("submodules/claudechic")` or inspects claudechic's package metadata to determine install source would violate this law and create a dirty seam.

---

## 7. Summary

| Property | Standard Mode (git-url) | Developer Mode (editable-local) |
|----------|------------------------|--------------------------------|
| pixi.toml line | `{ git = "...", branch = "main" }` | `{ path = "submodules/claudechic", editable = true }` |
| Code location | pixi internal cache (`.pixi/`) | `submodules/claudechic/` |
| Reproducibility | pixi.lock pins exact SHA | Developer manages their own git state |
| Updates | `pixi update claudechic` | `cd submodules/claudechic && git pull` |
| pixi-pack | ❌ Not supported | ❌ Not supported (but code is local) |
| Network required | Yes (initial install + updates) | No (code is local) |
| .gitmodules needed | No | No |
| Swap cost | One line in pixi.toml + `pixi install` | One line in pixi.toml + clone + `pixi install` |
| Target user | Most users (consume claudechic) | Claudechic developers (hack on it) |
| Default | **YES** | No |

**Axis orthogonality: CONFIRMED.** Swapping distribution mode changes exactly one line in pixi.toml and regenerates pixi.lock. No other file, system, seam, or behavior changes. This is a textbook orthogonal axis.
