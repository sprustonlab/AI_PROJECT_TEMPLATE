# Research Report: Bootstrap/Installer Options for Scientific Project Templates

**Requested by:** Coordinator
**Date:** 2026-03-30
**Tier of best source found:** T1 (official documentation for pixi, copier, cookiecutter, scientific-python/cookie)

## Query

Evaluate bootstrap/installer approaches for the AI_PROJECT_TEMPLATE, targeting scientific computing audiences (neuroscientists, computational biologists, ML researchers) who may not be software engineers. The current proposal uses two commands (install pixi + pixi exec copier). The user wants to explore whether simpler alternatives exist.

---

## 1. Field Standards for Scientific Project Bootstrapping

### How existing template tools bootstrap

| Tool | Install Command | Create Command | Total Steps |
|------|---------------|----------------|-------------|
| **Cookiecutter Data Science v2** | `pipx install cookiecutter-data-science` | `ccds` | 2 (install + run) |
| **Copier** | `pipx install copier` or `uv tool install copier` | `copier copy gh:org/template project` | 2 |
| **Scientific-python/cookie** | `uv tool install --with copier-templates-extensions copier` | `copier copy gh:scientific-python/cookie pkg --trust` | 2 |
| **PyScaffold** | `pipx install pyscaffold` | `putup my_project` | 2 |
| **Cruft** | `uv tool install cruft` | `cruft create https://github.com/org/template` | 2 |
| **QuantCo pixi+copier** | (pixi already installed) | `pixi exec --spec copier --spec ruamel.yaml -- copier copy --trust https://github.com/quantco/... dest` | 1-2 |

**Key observation:** Every major scientific template follows the same pattern — install a tool, then run it. Two steps is the norm. The differentiator is what's assumed as prerequisites.

### What prerequisites each assumes

- **cookiecutter-data-science:** Python 3.9+ with pip/pipx already available
- **scientific-python/cookie:** Python 3.10+ with uv or pipx
- **PyScaffold:** Python with pip, conda, or pipx
- **QuantCo template:** pixi already installed
- **R ecosystem (usethis):** R + RStudio already installed; then `usethis::create_project("path")` — one function call from within the IDE

### How tools bootstrap *themselves*

| Tool | Self-install mechanism |
|------|----------------------|
| **pixi** | `curl -fsSL https://pixi.sh/install.sh \| bash` |
| **Homebrew** | `curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh \| bash` |
| **rustup** | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| **conda/miniconda** | Download installer script from website, `bash Miniconda3-latest-Linux-x86_64.sh` |
| **uv** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

The `curl | bash` pattern is well-established for developer tools. Scientists are familiar with it from conda/miniconda installs.

---

## 2. How Scientists Actually Set Up Projects

### Typical lab workflow (no template tool)

1. `mkdir my-project && cd my-project`
2. Copy files from a previous project or a lab "starter repo"
3. `conda create -n my-project python=3.10`
4. `conda activate my-project`
5. Start coding

This is **zero-tooling** but also zero-standardization. The main competitor for any template is "just copy the last project."

### HPC environments

- Tools available: `module load miniconda3` → `conda create`
- No admin rights, often no internet on compute nodes (login nodes may have internet)
- Users SSH in, work in `$HOME` or `/groups/` directories
- `pip install --user` works; `curl` usually works on login nodes
- pixi installs to `~/.pixi/` — no admin rights needed ✓
- Docker/containers increasingly available (Singularity/Apptainer) but not universal

### conda ecosystem approach

- `conda create -n env_name` — familiar to nearly all scientific Python users
- No project structure — just an environment
- Scientists mentally separate "environment" from "project structure"

### R ecosystem approach

- `usethis::create_project("my-project")` — run from R console or RStudio
- Single function call, no separate install (usethis comes with devtools, which most R users have)
- Beautiful UX: IDE-integrated, interactive, no command line needed

---

## 3. Option Evaluation

### Option A: Current Proposal (pixi install + pixi exec copier)

```bash
curl -fsSL https://pixi.sh/install.sh | bash   # one-time
pixi exec --spec copier copier copy https://github.com/sprustonlab/AI_PROJECT_TEMPLATE my-project
```

| Criterion | Assessment |
|-----------|-----------|
| **Commands from zero** | 2 (install pixi, then pixi exec copier) |
| **Prerequisites** | curl, bash (universal on Linux/macOS) |
| **Cross-platform** | ✅ Linux, macOS; Windows uses `iwr \| iex` variant |
| **HPC compatible** | ✅ No admin rights needed; pixi installs to `~/.pixi/` |
| **Familiarity to scientists** | ⚠️ pixi is newer; `pixi exec --spec` is obscure syntax |
| **Maintenance burden** | 🟢 Low — pixi and copier maintained by others |
| **Supports copier update** | ✅ Yes — `.copier-answers.yml` preserved |
| **Offline/air-gapped** | ❌ Requires internet for both pixi install and copier run |

**Strengths:** Clean dependency story (pixi is the only permanent install). Copier enables template updates. Already proven by QuantCo template.

**Weaknesses:** `pixi exec --spec copier copier copy` is confusing — "copier" appears twice. Scientists may not understand what `--spec` means.

---

### Option B: Single curl Installer Script

```bash
curl -fsSL https://raw.githubusercontent.com/sprustonlab/AI_PROJECT_TEMPLATE/main/install.sh | bash
```

The script would:
1. Check if pixi is installed; install if not
2. Run `pixi exec --spec copier copier copy ...`
3. Print friendly instructions

| Criterion | Assessment |
|-----------|-----------|
| **Commands from zero** | **1** (single curl command) |
| **Prerequisites** | curl, bash |
| **Cross-platform** | ✅ Linux, macOS; separate `.ps1` for Windows |
| **HPC compatible** | ✅ Same as Option A under the hood |
| **Familiarity** | ✅ Scientists see `curl \| bash` for conda, homebrew, rust |
| **Maintenance burden** | 🟡 Medium — we maintain the installer script |
| **Supports copier update** | ✅ Same as A under the hood |
| **Offline** | ❌ Requires internet |

**Strengths:** Absolute minimum user effort. Hides complexity. Can include friendly output, error handling, platform detection. Can be versioned.

**Weaknesses:** We maintain a bash script. Windows needs a separate PowerShell script. The interactive copier prompts still happen (which is fine — that's the project configuration step). Security-conscious users dislike `curl | bash` (though the entire scientific tool ecosystem uses it).

**Implementation sketch:**
```bash
#!/usr/bin/env bash
set -euo pipefail

echo "🔬 Setting up your scientific project..."

# Install pixi if not present
if ! command -v pixi &>/dev/null; then
    echo "Installing pixi package manager..."
    curl -fsSL https://pixi.sh/install.sh | bash
    export PATH="$HOME/.pixi/bin:$PATH"
fi

# Run copier via pixi
pixi exec --spec copier copier copy --trust \
    https://github.com/sprustonlab/AI_PROJECT_TEMPLATE "${1:-.}"

echo "✅ Project created! Next: cd into your project and run 'pixi install'"
```

---

### Option C: pip/pipx Install a Lightweight CLI Tool

```bash
pipx install ai-project-template   # or: pip install --user ai-project-template
ai-project-template create my-project
```

| Criterion | Assessment |
|-----------|-----------|
| **Commands from zero** | 2 (install CLI + run it) |
| **Prerequisites** | Python + pip/pipx (most scientists have this) |
| **Cross-platform** | ✅ Fully cross-platform via Python |
| **HPC compatible** | ✅ `pip install --user` works without admin |
| **Familiarity** | ✅ `pip install` is the most familiar command in scientific Python |
| **Maintenance burden** | 🔴 High — publish to PyPI, maintain a Python package, handle versioning |
| **Supports copier update** | ⚠️ Would need to bundle or depend on copier |
| **Offline** | ❌ Requires internet (unless pre-installed) |

**Strengths:** Scientists know `pip install`. A branded command (`ai-project-template create`) is memorable. This is what cookiecutter-data-science v2 does (`pipx install cookiecutter-data-science` → `ccds`).

**Weaknesses:** Now we maintain a PyPI package. The CLI is just a thin wrapper around copier. Adds a Python dependency before pixi takes over. Philosophical conflict: we're using pixi to escape pip, but bootstrapping via pip.

**Verdict:** Only worth it if the template becomes widely used. Overkill for a lab/org template.

---

### Option D: GitHub Template Repository ("Use this template" button)

Users click "Use this template" on GitHub, then clone their new repo.

| Criterion | Assessment |
|-----------|-----------|
| **Commands from zero** | 0 CLI commands (web UI) + `git clone` |
| **Prerequisites** | GitHub account, git |
| **Cross-platform** | ✅ Universal |
| **HPC compatible** | ✅ `git clone` works everywhere |
| **Familiarity** | ✅ GitHub is familiar to most scientists |
| **Maintenance burden** | 🟢 Very low — just mark repo as template |
| **Supports copier update** | ❌ **No** — no connection between template and generated project |
| **Offline** | ⚠️ Only `git clone` after creation |

**Strengths:** Zero tooling. Friendly web UI. Scientists already use GitHub.

**Critical weaknesses:**
- **No variable substitution** — GitHub templates copy files verbatim. No project name injection, no conditional files (e.g., cluster.py toggle), no personalization
- **No template updates** — the generated repo has no link to the template. `copier update` is impossible
- **No conditional content** — can't ask "do you want cluster support?" and include/exclude files
- **Unrelated git histories** — branches from template have no common ancestor with the template repo

**Verdict:** Fundamentally incompatible with our needs. We need variable substitution (project name, cluster toggle, claudechic mode) and template evolution via `copier update`. **Not recommended.**

---

### Option E: Web Form That Generates a Zip/Tarball

A web app (GitHub Pages or small server) with a form that generates a customized project download.

| Criterion | Assessment |
|-----------|-----------|
| **Commands from zero** | 0 CLI commands (web) + unzip + `pixi install` |
| **Prerequisites** | Web browser |
| **Cross-platform** | ✅ Universal |
| **HPC compatible** | ❌ HPC often lacks web browsers; would need to `wget` the zip |
| **Familiarity** | ✅ Web forms are universally familiar |
| **Maintenance burden** | 🔴 Very high — maintain a web app, hosting, server-side generation |
| **Supports copier update** | ❌ No connection to template after download |
| **Offline** | ❌ |

**Strengths:** Lowest possible barrier to entry. Nice for demos/workshops.

**Weaknesses:** Loses `copier update`. Significant hosting/maintenance burden. Doesn't work on HPC where you'd actually use it. The web form duplicates copier's interactive prompts.

**Verdict:** **Not recommended.** High effort, loses key features. Could be a supplementary option for workshops but not the primary path.

---

### Option F: VS Code Extension / Claude Code Slash Command

```
/create-project my-project
```

| Criterion | Assessment |
|-----------|-----------|
| **Commands from zero** | 1 (slash command) — but requires Claude Code already running |
| **Prerequisites** | Claude Code or VS Code with extension |
| **Cross-platform** | ✅ Wherever the IDE runs |
| **HPC compatible** | ⚠️ Requires IDE access (VS Code remote, Claude Code SSH) |
| **Familiarity** | ⚠️ Only users already in the Claude Code ecosystem |
| **Maintenance burden** | 🟡 Medium — maintain a skill/extension |
| **Supports copier update** | ✅ Skill can shell out to copier |
| **Offline** | ❌ |

**Strengths:** Zero-friction for users already in Claude Code. Could combine project creation + initial setup + first commit in one step.

**Weaknesses:** Only works within a specific tool. Not a general-purpose solution. Good as a *supplementary* path, not the *primary* path.

**Verdict:** Nice addition, but can't be the only option. Users need to create projects before they have Claude Code configured.

---

### Option G: `pixi exec` with a Wrapper Script in the Repo (Hybrid)

Ship a small `create-project.sh` in the repo root that pixi exec can run:

```bash
pixi exec --spec copier copier copy --trust https://github.com/sprustonlab/AI_PROJECT_TEMPLATE my-project
```

Or create a pixi task alias:
```bash
pixi global install copier
copier copy https://github.com/sprustonlab/AI_PROJECT_TEMPLATE my-project
```

| Criterion | Assessment |
|-----------|-----------|
| **Commands from zero** | 2 (install pixi + one command) |
| **Prerequisites** | pixi |
| **Maintenance** | 🟢 Low |

**Verdict:** Marginal improvement over Option A. Doesn't solve the core UX problem.

---

### Option H: `pipx run` (Zero-Install Copier)

```bash
pipx run copier copy https://github.com/sprustonlab/AI_PROJECT_TEMPLATE my-project
```

| Criterion | Assessment |
|-----------|-----------|
| **Commands from zero** | 1 (if pipx is available) |
| **Prerequisites** | Python + pipx |
| **Cross-platform** | ✅ |
| **HPC compatible** | ✅ Most HPC have Python; `pip install --user pipx` works |
| **Familiarity** | ✅ Python-based, familiar ecosystem |
| **Maintenance** | 🟢 Zero — uses copier directly |
| **Supports copier update** | ✅ |

**Strengths:** Uses the Python ecosystem scientists already have. `pipx run` means no permanent install. One command if pipx exists.

**Weaknesses:** Requires Python + pipx as prerequisite. On HPC, user might need `module load python` first. Doesn't install pixi (which is needed for the project itself).

**Verdict:** Good alternative path to document alongside Option A/B. Useful for users who already have Python but not pixi.

---

## 4. Comparative Summary

| Option | Steps | Prerequisites | copier update | HPC | Maintenance | Recommended? |
|--------|-------|--------------|---------------|-----|-------------|-------------|
| **A: pixi + pixi exec** | 2 | curl | ✅ | ✅ | 🟢 Low | ✅ Primary |
| **B: curl \| bash installer** | 1 | curl | ✅ | ✅ | 🟡 Med | ✅ **Best UX** |
| **C: pip/pipx CLI** | 2 | Python+pip | ✅ | ✅ | 🔴 High | ⚠️ Only if widely adopted |
| **D: GitHub template** | 1+clone | GitHub acct | ❌ | ✅ | 🟢 Low | ❌ Loses key features |
| **E: Web form** | 0+download | Browser | ❌ | ❌ | 🔴 Very high | ❌ |
| **F: Claude Code skill** | 1 | Claude Code | ✅ | ⚠️ | 🟡 Med | ⚠️ Supplementary only |
| **G: pixi wrapper** | 2 | pixi | ✅ | ✅ | 🟢 Low | ⚠️ Marginal gain |
| **H: pipx run copier** | 1-2 | Python+pipx | ✅ | ✅ | 🟢 Zero | ✅ Alt path |

---

## 5. Recommendation

### Primary path: Option B (curl installer) wrapping Option A

**Rationale:**
1. One command from zero to project — matches the UX bar of `curl | sh` tools scientists already use (conda, homebrew, rust)
2. Under the hood, it's still pixi + copier — no new tooling to maintain
3. The installer script is ~30 lines of bash — low maintenance
4. Pixi gets installed as a side effect, which the project needs anyway
5. Copier's interactive prompts provide the project customization experience
6. `.copier-answers.yml` is preserved for future `copier update`

**Document three paths in README (in order):**

```markdown
## Quick Start

### One-line install (recommended)
```bash
curl -fsSL https://sprustonlab.github.io/AI_PROJECT_TEMPLATE/install.sh | bash -s my-project
```

### Already have pixi?
```bash
pixi exec --spec copier copier copy --trust https://github.com/sprustonlab/AI_PROJECT_TEMPLATE my-project
```

### Already have Python + pipx?
```bash
pipx run copier copy --trust https://github.com/sprustonlab/AI_PROJECT_TEMPLATE my-project
```
```

### Why not the other options?

- **Option D (GitHub template):** Loses variable substitution and copier update — these are core features
- **Option E (Web form):** Massive maintenance burden, loses copier update, doesn't work on HPC
- **Option C (PyPI CLI):** Only worth it if template has 100+ users; overkill for a lab/org template
- **Option F (Claude Code):** Good supplementary path, but can't be primary — circular dependency (need project before Claude Code is configured)

### Implementation notes for Option B

1. Host `install.sh` at a stable URL (GitHub Pages or raw GitHub)
2. Script should: detect OS, install pixi if missing, run copier, print next steps
3. Windows: ship `install.ps1` alongside
4. Script should be idempotent (safe to run twice)
5. Consider: should the script also run `pixi install` in the new project? (Probably yes — gets user to a fully working state)

---

## Sources

- [Cookiecutter Data Science](https://cookiecutter-data-science.drivendata.org/) — T1, official docs
- [scientific-python/cookie](https://github.com/scientific-python/cookie) — T3, official scientific-python org
- [QuantCo copier-template-python-open-source](https://github.com/Quantco/copier-template-python-open-source) — T5, well-maintained, uses pixi+copier pattern
- [Copier documentation](https://copier.readthedocs.io/en/stable/) — T1, official docs
- [pixi documentation / GitHub](https://github.com/prefix-dev/pixi) — T3, official prefix-dev org
- [PyScaffold](https://github.com/pyscaffold/pyscaffold) — T5, well-maintained community project
- [usethis R package](https://usethis.r-lib.org/) — T1, official R-lib docs
- [GitHub template repositories docs](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template) — T1, GitHub official docs
- [rustup installation](https://rust-lang.github.io/rustup/installation/index.html) — T1, official Rust docs
- [From Cookiecutter to Copier](https://medium.com/@gema.correa/from-cookiecutter-to-copier-uv-and-just-the-new-python-project-stack-90fb4ba247a9) — T6, practitioner blog
- [HPC conda environments](https://rabernat.medium.com/custom-conda-environments-for-data-science-on-hpc-clusters-32d58c63aa95) — T6, HPC practitioner

---

## Not Recommended (and why)

| Source/Approach | Why Rejected |
|----------------|-------------|
| **GitHub template repos** | No variable substitution, no template updates, no conditional files — fundamentally incompatible with copier-based workflow |
| **Web form generator** | Massive maintenance burden, loses copier update, doesn't work on HPC — the place scientists most need it |
| **Yeoman (yo)** | Node.js dependency — wrong ecosystem for scientific Python |
| **cargo-generate** | Rust ecosystem only — irrelevant |
| **create-react-app pattern (npm create)** | Requires Node.js — wrong ecosystem. Also, CRA itself is deprecated. Pattern insight is useful though: `npx` = `pipx run` = `pixi exec` — ephemeral execution of a scaffolding tool |
