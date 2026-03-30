# Research Report: Windows Bootstrap & GitHub Pages Landing Page

**Requested by:** Coordinator
**Date:** 2026-03-30
**Tier of best source found:** T1 (official pixi, rustup, conda docs; MDN Web API docs)

## Query

How do we handle Windows users in the bootstrap story? Can a GitHub Pages landing page with OS detection solve the UX problem? What do scientists on Windows actually use?

---

## 1. How the Best Tools Handle This: Landing Page Patterns

### rustup.rs (T1 — official Rust project)

- **OS detection:** Yes. JavaScript detects platform, shows platform-specific instructions by default
- **Linux/macOS:** Shows `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
- **Windows:** Shows "Download rustup-init.exe" link with direct download for x86_64, i686, aarch64
- **Platform cycling:** Users can click or press 'n' to cycle through platforms (see all options)
- **Copy button:** Yes, on the code block
- **Key insight:** Windows gets a **downloadable .exe**, not a paste-able command. This is deliberate — `.exe` download is the most familiar pattern for Windows users

### pixi.sh / pixi.prefix.dev (T3 — prefix-dev official)

- **OS detection:** Uses **tabs** — "Linux & macOS" | "Windows" — user clicks to toggle
- **Linux/macOS:** `curl -fsSL https://pixi.sh/install.sh | sh`
- **Windows:** Two options:
  1. **MSI installer download** (clickable link to GitHub releases)
  2. **PowerShell command:** `powershell -ExecutionPolicy ByPass -c "irm -useb https://pixi.sh/install.ps1 | iex"`
- **Copy button:** Yes
- **Transparency:** Links to view both install scripts before running them
- **Key insight:** Pixi offers BOTH a downloadable MSI and a PowerShell command. Belt and suspenders.

### conda / miniconda (T1 — Anaconda official)

- **Windows:** Download `.exe` installer from anaconda.com/download → double-click → GUI wizard
- **No command-line option for initial install on Windows** — it's all GUI
- **This is what scientists know.** The miniconda `.exe` wizard is the most common onboarding experience in scientific Python on Windows
- **Key insight:** Scientists on Windows expect to **download and double-click something**

### Common Pattern Across All Three

| Tool | Linux/macOS | Windows |
|------|-------------|---------|
| rustup | `curl \| sh` | Download `.exe` |
| pixi | `curl \| sh` | MSI download OR PowerShell one-liner |
| conda | `bash Miniconda3-*.sh` | Download `.exe`, GUI wizard |

**The pattern is clear: on Windows, provide a downloadable artifact (not just a command to paste).**

---

## 2. GitHub Pages Landing Page Proposal

### Architecture

A simple static page at `sprustonlab.github.io/AI_PROJECT_TEMPLATE/` that:

1. Detects OS via JavaScript (`navigator.userAgentData` or `navigator.platform` fallback)
2. Shows the appropriate install method by default
3. Allows manual platform switching (tabs, like pixi does)

### OS Detection (T1 — MDN Web API docs)

```javascript
// Modern approach
function getOS() {
  // navigator.userAgentData (modern browsers)
  if (navigator.userAgentData?.platform) {
    const p = navigator.userAgentData.platform;
    if (p === 'Windows') return 'windows';
    if (p === 'macOS') return 'macos';
    if (p === 'Linux') return 'linux';
  }
  // Fallback to userAgent string
  const ua = navigator.userAgent;
  if (ua.includes('Win')) return 'windows';
  if (ua.includes('Mac')) return 'macos';
  if (ua.includes('Linux')) return 'linux';
  return 'unknown';
}
```

**Note:** `navigator.platform` is deprecated but still widely supported. `navigator.userAgentData` is the modern replacement. Using both as fallback is standard practice.

### Proposed Page Layout

```
┌─────────────────────────────────────────────┐
│  🔬 AI Project Template                     │
│  Scientific project scaffolding in seconds   │
│                                              │
│  [Linux/macOS]  [Windows]  ← tabs, auto-    │
│                               selected by OS │
│  ┌─────────────────────────────────────────┐ │
│  │ Linux/macOS:                            │ │
│  │                                         │ │
│  │ curl -fsSL https://sprustonlab.github   │ │
│  │ .io/AI_PROJECT_TEMPLATE/install.sh      │ │
│  │ | bash -s my-project          [Copy 📋] │ │
│  │                                         │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  ┌─────────────────────────────────────────┐ │
│  │ Windows:                                │ │
│  │                                         │ │
│  │ Option 1: [Download install.ps1] button │ │
│  │                                         │ │
│  │ Option 2: Copy this into PowerShell:    │ │
│  │ powershell -ExecutionPolicy ByPass -c   │ │
│  │ "irm -useb https://...install.ps1 |    │ │
│  │ iex"                          [Copy 📋] │ │
│  │                                         │ │
│  │ Option 3: Using WSL? Use the Linux      │ │
│  │ command above.                          │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  Already have pixi? → advanced instructions  │
│  Already have pipx? → advanced instructions  │
└─────────────────────────────────────────────┘
```

### Implementation

- **Hosting:** GitHub Pages (free, automatic from repo's `/docs` folder or `gh-pages` branch)
- **Complexity:** ~100 lines HTML + ~30 lines JavaScript. No framework needed
- **Maintenance:** Nearly zero — only changes when install URLs change
- **Bonus:** Can include a "What does this do?" expandable section for transparency

---

## 3. Windows-Specific Bootstrap Options Evaluated

### Option W1: PowerShell One-Liner (like pixi does)

```powershell
powershell -ExecutionPolicy ByPass -c "irm -useb https://sprustonlab.github.io/AI_PROJECT_TEMPLATE/install.ps1 | iex"
```

The script would:
1. Install pixi if not present (using pixi's own install.ps1)
2. Run `pixi exec --spec copier copier copy --trust ... my-project`

| Criterion | Assessment |
|-----------|-----------|
| **Familiarity** | ⚠️ Scientists rarely type PowerShell commands. They use GUIs, Anaconda Navigator, or conda from Anaconda Prompt |
| **Security** | ⚠️ `irm | iex` pattern is flagged by security tools — it's the PowerShell equivalent of `curl \| bash`. Windows Defender / corporate policies may block it |
| **ExecutionPolicy ByPass** | 🔴 Red flag for managed/enterprise Windows machines. IT departments may restrict this |
| **Realistic?** | Yes, but only for power users. This is how pixi itself does it, which validates the approach |

**Verdict:** Include as "Option 2" on the landing page. Power users will appreciate it.

### Option W2: Downloadable `.ps1` Script ("Download for Windows" Button)

A button on the GitHub Pages site that downloads `install.ps1`. User right-clicks → "Run with PowerShell" or opens PowerShell and runs `.\install.ps1 my-project`.

| Criterion | Assessment |
|-----------|-----------|
| **Familiarity** | ✅ Download + run is familiar to all Windows users |
| **Security** | ⚠️ Windows may warn about running downloaded scripts (SmartScreen). User needs to allow it. ExecutionPolicy may block `.ps1` files |
| **UX** | 🟡 Slightly clunky — download, find file, right-click. But still better than typing a long command |
| **Realistic?** | Yes, this is how most Windows tools distribute scripts |

**Verdict:** Include as "Option 1" on the landing page. Pair with clear instructions: "1. Download, 2. Right-click → Run with PowerShell, 3. Answer the questions"

### Option W3: Downloadable `.exe` Installer

A compiled binary that installs pixi and runs copier.

| Criterion | Assessment |
|-----------|-----------|
| **Familiarity** | ✅ This is how conda/miniconda works. Scientists know this |
| **Security** | ⚠️ SmartScreen warning for unsigned exe. Code signing costs ~$200-400/year |
| **Maintenance** | 🔴 High — need to compile, sign, and publish binary for each update |
| **Feasibility** | Possible (write in Rust/Go, or use PyInstaller), but massive overkill |

**Verdict:** ❌ Not recommended. The maintenance burden is extreme for what is a thin wrapper around pixi + copier. Only justified if we had thousands of users.

### Option W4: MSI Installer (like pixi offers)

Same as W3 but as an MSI package. Even more complex to build.

**Verdict:** ❌ Not recommended. Same reasoning as W3.

### Option W5: winget Package

```cmd
winget install sprustonlab.ai-project-template
```

| Criterion | Assessment |
|-----------|-----------|
| **Familiarity** | ⚠️ winget is growing but not yet universal in scientific computing |
| **Feasibility** | Requires: building a binary, creating a YAML manifest, submitting to microsoft/winget-pkgs repo, maintaining updates |
| **Maintenance** | 🔴 High — same as W3 plus winget-specific packaging |

**Verdict:** ❌ Not recommended. Requires us to build and maintain a Windows binary. Overkill.

### Option W6: Scoop/Chocolatey Package

Similar to winget. Requires maintaining a package manifest and a binary/script.

**Verdict:** ❌ Not recommended for same reasons.

### Option W7: "Just Use WSL"

Document: "On Windows, we recommend using WSL (Windows Subsystem for Linux). Then use the Linux instructions."

| Criterion | Assessment |
|-----------|-----------|
| **Familiarity** | ⚠️ WSL adoption is growing but many scientists don't have it set up |
| **HPC relevance** | ✅ If they SSH into HPC from Windows, they're using Linux anyway |
| **Maintenance** | 🟢 Zero — it's just documentation |

**Verdict:** ✅ Include as "Option 3" on the landing page for users who have or want WSL. Not a primary path.

### Option W8: Git Bash (ships with Git for Windows)

Git Bash includes `curl` and a bash shell. Our `install.sh` might just work in Git Bash.

| Criterion | Assessment |
|-----------|-----------|
| **Familiarity** | ✅ Many scientists have Git for Windows installed (it's a VS Code prerequisite) |
| **Feasibility** | ⚠️ Depends on whether pixi's install.sh works in Git Bash (MSYS2 environment). Needs testing |
| **Path handling** | ⚠️ Git Bash uses Unix-style paths; pixi installs to Windows-style paths. May cause issues |

**Verdict:** ⚠️ Worth testing. If it works, this is a great zero-effort Windows path. If not, don't force it.

---

## 4. What Do Scientists on Windows Actually Use?

### Terminal Environment

Based on field observation and community patterns:

| Environment | Prevalence Among Scientists | Notes |
|------------|---------------------------|-------|
| **Anaconda Prompt / cmd** | Very high | Default after conda install. Most lab tutorials use this |
| **PowerShell** | Medium | Windows default terminal since Win10. Many scientists don't know the difference from cmd |
| **VS Code integrated terminal** | Growing fast | Defaults to PowerShell. Many scientists use VS Code for Python |
| **Git Bash** | Low-medium | Comes with Git for Windows. More common in CS-adjacent researchers |
| **WSL** | Low but growing | Bioinformaticians and ML researchers adopt it. Neuroscientists less so |
| **CMD (plain)** | Declining | Still used by older workflow tutorials |

### How Conda Bootstraps on Windows

This is the gold standard for "how scientists install things on Windows":

1. Go to anaconda.com/download
2. Click "Download" (auto-detects Windows, shows `.exe`)
3. Double-click the downloaded `.exe`
4. Click through GUI wizard (Next → Agree → Next → Install)
5. Open "Anaconda Prompt" from Start Menu

**Five steps, mostly clicking.** No command typing. This is what our audience knows.

### Key Insight

> Scientists on Windows don't type install commands. They download things and click them. Our Windows path should prioritize a **downloadable script with clear instructions** over a paste-able PowerShell command.

---

## 5. Recommendation

### Landing Page + Dual-Path Strategy

**Build a GitHub Pages landing page at `sprustonlab.github.io/AI_PROJECT_TEMPLATE/`** with:

#### Linux/macOS (auto-detected, or clickable tab)
```bash
curl -fsSL https://sprustonlab.github.io/AI_PROJECT_TEMPLATE/install.sh | bash -s my-project
```
With a prominent "Copy" button.

#### Windows (auto-detected, or clickable tab)

**Primary (Option 1):** "Copy" button for the PowerShell one-liner:
```powershell
irm https://sprustonlab.github.io/AI_PROJECT_TEMPLATE/install.ps1 | iex
```
With instructions: "Open PowerShell and paste this command."

This is simpler than pixi's version — no need for `-ExecutionPolicy ByPass` wrapper if our script handles it internally. And `irm` is shorter than `Invoke-RestMethod`.

**Secondary (Option 2):** "Download install.ps1" button for users who prefer to inspect/save the file first.

**Tertiary (Option 3):** "Using WSL or Git Bash? Use the Linux command above."

### What `install.ps1` Does

```powershell
# 1. Check if pixi is installed
# 2. If not, run pixi's own install.ps1
# 3. Run: pixi exec --spec copier copier copy --trust <template-url> <project-name>
# 4. Optionally: cd into project, run pixi install
# 5. Print friendly next-steps message
```

~30-40 lines of PowerShell. Low maintenance.

### What NOT to Build

- ❌ `.exe` installer — extreme maintenance burden for a thin wrapper
- ❌ MSI package — same reasoning
- ❌ winget/scoop/chocolatey package — requires building a binary
- ❌ Web-based project generator — loses copier update, high maintenance
- ❌ `.bat` file — limited; would just call PowerShell anyway

### Implementation Priority

1. **`install.sh`** (Linux/macOS) — ~30 lines bash
2. **`install.ps1`** (Windows) — ~40 lines PowerShell
3. **Landing page** (`index.html`) — ~130 lines HTML/CSS/JS
4. Host all three in the repo's `/docs` folder → GitHub Pages auto-publishes

Total effort: ~200 lines of code. Very low maintenance. Follows the exact same pattern as pixi.sh and rustup.rs — two of the most successful installer landing pages in the developer ecosystem.

---

## Sources

- [pixi installation docs](https://pixi.prefix.dev/latest/) — T1, official prefix-dev docs (tabs UI, MSI + PowerShell for Windows)
- [rustup.rs](https://rustup.rs/) — T1, official Rust project (OS detection, .exe download for Windows)
- [conda Windows installation](https://docs.conda.io/projects/conda/en/stable/user-guide/install/windows.html) — T1, official conda docs (GUI .exe installer)
- [miniconda install guide](https://www.anaconda.com/docs/getting-started/miniconda/install) — T1, Anaconda official
- [MDN Navigator.platform](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/platform) — T1, MDN Web API docs
- [30secondsofcode OS detection](https://www.30secondsofcode.org/js/s/browser-os-detection/) — T6, well-known code snippet site
- [winget-pkgs repository](https://github.com/microsoft/winget-pkgs) — T3, Microsoft official
- [GitHub Pages docs](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages) — T1, GitHub official
- [VS Code terminal profiles](https://code.visualstudio.com/docs/terminal/profiles) — T1, VS Code official docs
- [TeachBooks: Git Bash + Conda + VS Code](https://teachbooks.io/manual/installation-and-setup/git_bash_conda_vs-code.html) — T6, educational resource showing how scientists combine tools on Windows

## Not Recommended (and why)

| Approach | Why Rejected |
|----------|-------------|
| **`.exe` installer** | Massive build/sign/release pipeline for a 5-line wrapper around pixi + copier |
| **MSI installer** | Same as .exe but even more complex packaging |
| **winget package** | Requires building a binary; winget not widespread in scientific computing |
| **Scoop/Chocolatey** | Same effort as winget; smaller audience |
| **Web form generator** | Loses copier update; high hosting burden; covered in previous research |
| **`.bat` file** | Limited scripting; would just shell out to PowerShell anyway |
