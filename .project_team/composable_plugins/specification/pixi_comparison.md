# Feature-by-Feature Comparison: Pixi vs. SLC (install_env.py / lock_env.py)

**Requested by:** Coordinator (user question)
**Date:** 2026-03-29
**Author:** Researcher
**Tier of sources:** T1 (official pixi documentation), T3 (prefix.dev repo), code analysis of SLC scripts

---

## 1. Lockfiles

### SLC (Current System)

**Per-platform lockfiles** — one file per environment per platform:
```
envs/
├── claudechic.yml              # Spec (human-written, minimal constraints)
├── claudechic.osx-arm64.lock   # Lockfile for macOS Apple Silicon
├── claudechic.linux-64.lock    # Lockfile for Linux x86_64
```

**How it works:**
- `lock_env.py` runs `conda env export` on the currently active environment
- Captures the full resolved dependency tree with exact versions
- Adds a `_meta:` header with origin hash (SHA256 of spec file), platform, timestamp
- Stores pip package hashes for integrity verification
- Preserves editable (`-e`) install paths with relative path resolution
- Writes atomically (temp file + `os.replace()`)

**Staleness detection:**
- `install_env.py` compares `_meta:origin_hash` in lockfile against current spec SHA256
- If they differ → warns "Lockfile may be stale"

**Key property:** Each lockfile is completely self-contained. You can copy `claudechic.linux-64.lock` to an HPC node and install from it with nothing else needed.

### Pixi

**Single multi-platform lockfile** — one `pixi.lock` for ALL platforms:
```
project/
├── pixi.toml          # Spec (manifest)
└── pixi.lock          # Lockfile for ALL platforms in one file
```

**How it works:**
- `pixi lock` (or automatic on `pixi add`) resolves dependencies for **all platforms declared in `pixi.toml`** simultaneously
- The lockfile has two YAML sections:
  1. **`environments`** — lists channels and package references per platform (linux-64, osx-arm64, etc.)
  2. **`packages`** — deduplicated metadata for all packages across all platforms (SHA256, MD5, URL, deps, license, size)
- Packages appearing on multiple platforms are stored once with an `environments` field listing all applicable platforms
- Version number in lockfile ensures backward compatibility

**Staleness detection:**
- Pixi automatically checks if the lockfile satisfies the current manifest
- If manifest changed → re-solves and regenerates lockfile
- Can verify **without internet connection** (static satisfiability check)

### Comparison

| Feature | SLC | Pixi | Winner |
|---------|-----|------|--------|
| **File count** | N files (one per platform) | 1 file (all platforms) | **Pixi** — single file to commit, review, share |
| **Resolution** | Per-platform (must run `lock_env.py` on each target platform) | All-at-once (solves all platforms from any machine) | **Pixi** — generate linux-64 lockfile from macOS |
| **Format** | YAML (conda env export format + `_meta:` header) | YAML (custom pixi format with environments + packages sections) | Tie |
| **Integrity hashes** | SHA256 for pip packages, no conda package hashes | SHA256 + MD5 for all packages (conda and PyPI) | **Pixi** — more comprehensive |
| **Staleness detection** | Manual (`_meta:origin_hash` comparison) | Automatic (satisfiability check on every run) | **Pixi** — no stale lockfiles possible |
| **Self-contained** | Yes — lockfile IS the install manifest | Yes — lockfile contains all URLs and hashes | **Tie** |
| **Editable pip installs** | Preserved in lockfile with relative paths | Supported via `pyproject.toml` `[tool.pixi.pypi-dependencies]` | **SLC** — more explicit about editable handling |
| **Cross-platform generation** | Must run on target platform (or have access to it) | Can resolve all platforms from one machine | **Pixi** — huge win for cross-platform teams |

### Verdict: Lockfiles

**Pixi is strictly better for lockfile management.** The single multi-platform lockfile eliminates the need to run `lock_env.py` on each target platform separately. A developer on macOS can generate a lockfile that includes linux-64 resolution, which is exactly what you need when developing locally and deploying to HPC.

**One thing SLC does that pixi doesn't:** The `_meta:` header with human-readable "Original constraints (from spec)" comments. This is nice for documentation but pixi's automatic staleness detection makes it unnecessary for correctness.

---

## 2. Offline / Cached Installation

### SLC (Current System)

**Explicit two-phase download + install with cache directory:**
```python
# Phase 1: Download (online)
conda create --prefix <env> --download-only --yes <packages>
# Cache stored in: envs/<name>.<platform>.cache/conda/

# Phase 2: Install (offline)
conda create --prefix <env> --offline --yes <packages>
# Marker: envs/<name>.<platform>.cache/download_complete
```

**How it works:**
- `install_env.py` checks for `download_complete` marker file
- If exists → **offline mode** — uses cached packages only, no network
- If not → **online mode** — downloads first, then installs
- Pip packages also cached separately: `envs/<name>.<platform>.cache/pip/`
- Pip offline install: `pip install --no-index --find-links <cache_dir>`
- Platform-specific cache directories: `envs/<name>.<platform>.cache/` — designed for NFS sharing

**Key property:** The cache directory (`envs/<name>.<platform>.cache/`) can be pre-populated on a machine with internet access, then the entire `envs/` directory (or just the cache) can be copied to an air-gapped HPC node. The `download_complete` marker triggers offline mode automatically.

### Pixi

**Global shared cache with automatic deduplication:**
```
# Default cache locations:
# Linux: $XDG_CACHE_HOME/rattler or ~/.cache/rattler
# macOS: ~/Library/Caches/rattler
# Override: PIXI_CACHE_DIR=/path/to/cache
```

**How it works:**
- Pixi caches all downloaded packages in a global cache folder
- Cache is shared across ALL pixi workspaces and globally installed tools
- When installing, pixi checks cache first → downloads only what's missing
- Subsequent installs of same packages (even in different projects) are instant
- **No explicit offline mode** — pixi downloads what's needed, uses cache for what's available

**Air-gapped / offline considerations:**
- Pixi does NOT have an explicit `--download-only` + `--offline` workflow like SLC
- Pixi does NOT have a built-in way to pre-populate a cache for transfer to an air-gapped system
- **Workaround:** Set `PIXI_CACHE_DIR` on a networked machine, run `pixi install`, then copy the cache directory + lockfile to the air-gapped node. Set `PIXI_CACHE_DIR` on the target and run `pixi install` — it will find packages in the cache.
- **Community discussion** (GitHub #1354) shows this is a known gap — users have requested better offline/air-gapped support
- **Third-party tool:** `pixi-install-to-prefix` can install from a lockfile to an arbitrary directory, which could help with pre-built environment transfer

### Comparison

| Feature | SLC | Pixi | Winner |
|---------|-----|------|--------|
| **Explicit offline mode** | Yes — `download_complete` marker triggers it | No — implicit cache-based | **SLC** — purpose-built for HPC |
| **Pre-download for transfer** | Yes — `conda create --download-only` into named cache dir | No built-in mechanism | **SLC** — critical for air-gapped HPC |
| **Cache sharing across projects** | No — per-environment cache directories | Yes — global cache shared across all projects | **Pixi** — saves disk space |
| **Cache location control** | Per-env: `envs/<name>.<platform>.cache/` | Global: `PIXI_CACHE_DIR` env var | **SLC** — more predictable per-project |
| **NFS compatibility** | Designed for NFS (platform-specific cache paths) | Global cache on home directory (may be on NFS) | **Tie** — both work, but SLC is more intentional |
| **Can install without network** | Yes — if cache populated | Yes — if cache populated | **Tie** (but SLC makes this explicit) |

### Verdict: Offline / Cached Installation

**SLC is better for air-gapped HPC environments.** The explicit two-phase download+install with a named cache directory is purpose-built for the workflow of "download on a login node with internet, install on a compute node without internet." Pixi's global cache works but doesn't have the explicit pre-download or offline mode markers.

**This is the biggest gap in pixi for scientific HPC users.** If adopting pixi, we would need to either:
1. Keep a thin SLC wrapper that does `pixi install` on networked nodes and provides the cache-transfer workflow for air-gapped nodes
2. Contribute an offline-mode feature upstream to pixi
3. Use `pixi-install-to-prefix` to build environments on a networked machine and rsync the result

---

## 3. Workflow Equivalence

### SLC Workflow

```bash
# 1. Write spec (human)
vim envs/myenv.yml

# 2. Create environment from spec (first time, needs internet)
python install_env.py myenv
# → Creates envs/myenv/ conda env
# → Auto-generates envs/myenv.<platform>.lock

# 3. Lock environment (after changes)
conda activate envs/myenv
python lock_env.py myenv
# → Generates envs/myenv.<platform>.lock

# 4. Install from lockfile (subsequent installs, can be offline)
python install_env.py myenv
# → Detects lockfile, installs from it
# → Checks staleness against spec

# 5. Activate
source activate
# → Sets up PATH, PYTHONPATH, SLC_BASE
# → Sources envs/myenv activation
```

### Pixi Equivalent Workflow

```bash
# 1. Write spec (human)
pixi init                   # Creates pixi.toml
pixi add numpy scipy jax    # Adds dependencies
# → Auto-generates pixi.lock (all platforms)

# 2. Install from lockfile
pixi install
# → Creates .pixi/envs/default/ conda env
# → Deterministic from lockfile

# 3. Lock (automatic — no separate step)
# pixi.lock is auto-updated on every `pixi add`
# Manual: `pixi lock` to force re-solve

# 4. Activate
pixi shell                  # Enters subshell with env active
# OR
pixi run <command>          # Runs command in env
# OR
pixi shell-hook > activate.sh  # Generate activation script
source activate.sh              # For batch jobs / HPC
```

### Step-by-Step Mapping

| Step | SLC Command | Pixi Command | Notes |
|------|------------|-------------|-------|
| Create spec | Edit `envs/myenv.yml` | `pixi init` + `pixi add ...` | Pixi: `pixi.toml` is the spec |
| Generate lockfile | `python lock_env.py myenv` | Automatic (on `pixi add`) or `pixi lock` | Pixi eliminates a manual step |
| Install from lock | `python install_env.py myenv` | `pixi install` | Functionally identical |
| Check staleness | Automatic in `install_env.py` | Automatic in `pixi install` | Both handle this |
| Add a package | Edit `.yml` → `conda install` → `lock_env.py` | `pixi add <pkg>` (one command) | **Pixi: 1 command vs. 3** |
| Activate env | `source activate` | `pixi shell` or `source <(pixi shell-hook)` | Different mechanism, same result |
| Run in env | `conda activate envs/myenv && cmd` | `pixi run cmd` | Pixi: no explicit activation needed |
| Multiple envs | Multiple `.yml` files | `[feature]` sections in `pixi.toml` | Both support this |
| Cross-platform lock | Must run on each platform | Automatic from any platform | **Pixi: major win** |

### Verdict: Workflow

**Pixi is more streamlined.** Adding a package goes from 3 steps (edit spec → install → lock) to 1 step (`pixi add`). Cross-platform lockfile generation from a single machine is a major win. The `pixi run` pattern eliminates explicit environment activation.

---

## 4. Environment Isolation

### SLC (Current System)

**Prefix-based, inside project directory:**
```
envs/
├── claudechic/          # Full conda env for claudechic
│   ├── bin/
│   ├── lib/
│   └── ...
├── jupyter/             # Full conda env for jupyter
│   ├── bin/
│   ├── lib/
│   └── ...
├── claudechic.yml       # Spec
├── claudechic.osx-arm64.lock  # Lockfile
└── ...
```

- Each env is a full conda prefix at `envs/<name>/`
- Isolated from other envs (separate `bin/`, `lib/`, `site-packages/`)
- Read-only option: `--read-only` flag makes env immutable after install
- Location is predictable and controllable

### Pixi

**Project-local environments in `.pixi/envs/`:**
```
project/
├── .pixi/
│   └── envs/
│       ├── default/     # Default environment
│       ├── test/        # Named environment (if defined)
│       └── cuda/        # Another named environment
├── pixi.toml
└── pixi.lock
```

- Environments stored in `.pixi/envs/<name>/` inside the project directory
- **This location is not configurable** by design — pixi wants envs co-located with projects
- Each env is a full conda prefix (same as SLC)
- Global package cache at `~/.cache/rattler/` (configurable via `PIXI_CACHE_DIR`)
- Hard links from cache to env where possible (saves disk space)

**Alternative: Detached environments:**
- Configure `detached-environments = "/opt/pixi/envs"` in `~/.pixi/config.toml`
- Moves envs outside project directory
- **Not recommended by pixi** — creates disconnect between project and env, requires manual cleanup

**Alternative: `pixi-install-to-prefix`:**
- Third-party tool that installs from pixi lockfile to any directory
- `pixi-install-to-prefix /custom/path/myenv`
- Generates activation scripts
- Does not manage updates or removal

### Comparison

| Feature | SLC | Pixi | Winner |
|---------|-----|------|--------|
| **Env location** | `envs/<name>/` (project-local, configurable) | `.pixi/envs/<name>/` (project-local, NOT configurable) | **SLC** — more flexible |
| **Multiple envs** | Separate `.yml` specs | `[feature]` + `[environments]` in one `pixi.toml` | **Pixi** — more organized |
| **Env isolation** | Full conda prefix per env | Full conda prefix per env | **Tie** |
| **Read-only envs** | `--read-only` flag (chmod) | No built-in read-only mode | **SLC** — useful for shared envs |
| **Disk efficiency** | No dedup between envs | Hard links from global cache | **Pixi** — saves significant disk space |
| **Custom prefix** | `envs/<name>/` is the prefix | Third-party tool needed (`pixi-install-to-prefix`) | **SLC** — simpler |
| **Shared on NFS** | Works (envs in project dir on NFS) | Works (but `.pixi/` creates many small files on NFS) | **SLC** — more NFS-friendly by convention |

### Verdict: Environment Isolation

**Roughly equivalent, with trade-offs.** SLC gives more control over env location and offers read-only mode. Pixi saves disk space via cache hard-linking and has better multi-environment support. For HPC on NFS, SLC's convention of `envs/<name>/` is slightly more predictable than pixi's `.pixi/envs/`.

---

## 5. Features You'd Lose by Switching to Pixi

| SLC Feature | Pixi Equivalent | Lost? |
|-------------|----------------|-------|
| **Explicit offline mode** (`download_complete` marker) | No equivalent — cache-based only | **YES** — biggest gap |
| **Platform-specific cache dirs** (`envs/<name>.<platform>.cache/`) | Global cache (`~/.cache/rattler/`) | **YES** — less granular control |
| **Read-only environments** (`--read-only` flag) | No equivalent | **YES** — minor (can `chmod` manually) |
| **Staleness warnings** with origin hash | Automatic re-solve (better — never stale) | **NO** — pixi is better |
| **Editable pip installs** with relative path resolution | Supported via `pyproject.toml` PyPI deps | **NO** — different syntax, same capability |
| **Pip hash verification** in lockfile | SHA256 + MD5 for all packages | **NO** — pixi is more comprehensive |
| **`SLC_BASE` / `SLC_PYTHON` env vars** | Different env vars (`PIXI_HOME`, `CONDA_PREFIX`) | **PARTIAL** — activate script would need updating |
| **`require_env` command** (auto-install on first use) | `pixi run` auto-installs from lockfile | **NO** — pixi does this natively |
| **Atomic lockfile writes** | pixi handles internally | **NO** |
| **Claudechic-specific `SETUPTOOLS_SCM_PRETEND_VERSION`** | Can set in `pixi.toml` `[activation.env]` | **NO** — different syntax |

### Features You'd GAIN by Switching to Pixi

| Feature | Impact |
|---------|--------|
| **Cross-platform lockfile generation** | Generate linux-64 lockfile from macOS — no HPC access needed for locking |
| **Automatic lock on `pixi add`** | One command instead of three (edit → install → lock) |
| **Multi-environment in one manifest** | `[feature.cuda]`, `[feature.test]` sections — clean separation |
| **Built-in task runner** | `pixi run test`, `pixi run lint` — replaces parts of `commands/` |
| **PyPI + conda co-resolution** | Native handling of mixed conda/pip dependencies |
| **10x faster installs** | Written in Rust, parallel downloads |
| **Global cache deduplication** | Significant disk savings on shared systems |
| **`pixi shell-hook`** | Generate activation scripts for batch jobs (perfect for SLURM) |

---

## 6. Recommendation

### Hybrid Approach: Pixi as Primary, SLC Offline Wrapper as Fallback

**Don't do a full replacement. Layer pixi on top.**

```
┌─────────────────────────────────────────────────────────────┐
│  User's project                                              │
│                                                              │
│  pixi.toml       ← Human-written spec (replaces .yml)       │
│  pixi.lock       ← Auto-generated multi-platform lockfile    │
│                                                              │
│  .pixi/envs/     ← Pixi-managed environments (default)      │
│                                                              │
│  envs/           ← SLC compatibility layer (optional)        │
│    offline_cache/ ← Pre-downloaded packages for air-gap      │
│    install_from_pixi.py  ← Thin wrapper: pixi install OR    │
│                            offline fallback                   │
└─────────────────────────────────────────────────────────────┘
```

**Why hybrid:**
1. **Pixi for the 90% case:** Local dev, CI/CD, networked HPC nodes — pixi is strictly better
2. **SLC offline wrapper for the 10% case:** Air-gapped compute nodes where you need explicit download → transfer → install
3. **Migration path:** Existing `envs/*.yml` specs convert via `pixi init --import`
4. **No lock-in:** `pixi.lock` is the source of truth; the offline wrapper reads it

**Concrete implementation:**
- `pixi.toml` replaces `envs/*.yml` as the spec format
- `pixi.lock` replaces `envs/*.<platform>.lock` files
- `pixi install` replaces `python install_env.py` for networked environments
- `pixi shell-hook > activate.sh` replaces the env activation portion of `activate`
- A thin `offline_install.sh` script handles the air-gap case:
  1. On networked machine: `pixi install` (populates `~/.cache/rattler/`)
  2. `rsync ~/.cache/rattler/ <air-gap-node>:<cache-path>/`
  3. On air-gapped node: `PIXI_CACHE_DIR=<cache-path> pixi install`

### Decision Matrix for the User

| If your situation is... | Use... |
|------------------------|--------|
| Local development (macOS/Linux with internet) | `pixi add`, `pixi install`, `pixi shell` |
| CI/CD (GitHub Actions) | `pixi install` with pixi-action cache |
| HPC with internet on login nodes | `pixi install` on login, `pixi shell-hook` for SLURM jobs |
| HPC air-gapped compute nodes | Offline wrapper (pre-populate pixi cache, transfer, install) |
| Existing projects with `envs/*.yml` | `pixi init --import envs/<name>.yml` to migrate |

---

## Sources

- [Pixi Lockfile documentation](https://pixi.prefix.dev/latest/workspace/lockfile/)
- [Pixi Environment documentation](https://pixi.prefix.dev/latest/workspace/environment/)
- [Pixi Configuration reference](https://pixi.prefix.dev/latest/reference/pixi_configuration/)
- [pixi-install-to-prefix](https://github.com/pavelzw/pixi-install-to-prefix)
- [Pixi on HiPerGator HPC](https://docs.rc.ufl.edu/software/pixi/)
- [Pixi on Oregon State HPC](https://docs.hpc.oregonstate.edu/cqls/software/conda/pixi/)
- [Pixi cache discussion #1354](https://github.com/prefix-dev/pixi/discussions/1354)
- [Pixi detached environments #255](https://github.com/prefix-dev/pixi/issues/255)
- [Shipping conda envs to production with pixi](https://tech.quantco.com/blog/pixi-production)
- SLC source code: `install_env.py` and `lock_env.py` in AI_PROJECT_TEMPLATE
