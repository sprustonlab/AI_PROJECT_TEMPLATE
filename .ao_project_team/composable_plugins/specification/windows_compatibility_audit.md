# Windows Compatibility Audit

> **Reviewer:** Composability
> **Date:** 2026-03-29
> **Scope:** All shell scripts in the template + claudechic, guardrail hooks, pixi Windows support

---

## 1. Complete Shell Script Inventory

### 1.1 Scripts Found

| # | File | Shebang | Purpose | Must modify parent shell? |
|---|------|---------|---------|--------------------------|
| 1 | `activate` | `#!/bin/bash` | Seam registry — sets PATH, PROJECT_ROOT, PYTHONPATH, displays status | **YES** — `source`d into parent shell |
| 2 | `commands/claudechic` | `#!/bin/bash` | Env-activating wrapper — launches claudechic | No — child process |
| 3 | `commands/jupyter` | `#!/bin/bash` | Env-activating wrapper — launches Jupyter Lab | No — child process |
| 4 | `commands/require_env` | `#!/bin/bash` | Auto-install + activate env (to be deleted in pixi migration) | YES (when sourced) / No (when executed) |
| 5 | `submodules/claudechic/scripts/claudechic-remote` | `#!/bin/bash` | Wrapper for remote-control mode with auto-restart | No — child process |
| 6 | `tests/ci/test_activate.sh` | `#!/bin/bash` | E2E test for activate | No — test runner |
| 7 | `tests/ci/test_claudechic.sh` | `#!/bin/bash` | E2E test for claudechic command | No — test runner |
| 8 | `tests/ci/test_skill_available.sh` | `#!/bin/bash` | E2E test for skill availability | No — test runner |

### 1.2 Generated Scripts (not yet on disk — created by `generate_hooks.py`)

| File | Format | Purpose |
|------|--------|---------|
| `.claude/guardrails/hooks/bash_guard.sh` | Bash wrapper + embedded Python | Intercepts Bash tool calls |
| `.claude/guardrails/hooks/read_guard.sh` | Bash wrapper + embedded Python | Intercepts Read tool calls |
| `.claude/guardrails/hooks/glob_guard.sh` | Bash wrapper + embedded Python | Intercepts Glob tool calls |
| `.claude/guardrails/hooks/write_guard.sh` | Bash wrapper + embedded Python | Intercepts Write/Edit tool calls |
| `.claude/guardrails/hooks/post_compact_injector.sh` | Bash wrapper + embedded Python | SessionStart/compact injector |
| `.claude/guardrails/hooks/mcp__*_guard.sh` | Bash wrapper + embedded Python | MCP-specific tool interceptors |

---

## 2. Pixi Windows Support Assessment

### 2.1 Pixi Core — Fully Cross-Platform

| Feature | Linux/macOS | Windows | Notes |
|---------|-------------|---------|-------|
| `pixi install` | ✅ | ✅ | Native Rust binary for all platforms |
| `pixi add <pkg>` | ✅ | ✅ | |
| `pixi run -e <name> <cmd>` | ✅ | ✅ | **This is our primary activation path** |
| `pixi shell -e <name>` | ✅ | ✅ | Spawns subshell (bash on Unix, cmd on Windows) |
| `pixi shell-hook -s powershell` | ✅ | ✅ | Outputs PowerShell activation commands |
| `pixi shell-hook -s bash` | ✅ | ✅ (Git Bash/WSL) | |
| `pixi shell-hook -s cmd` | N/A | ✅ | Windows-native cmd.exe |
| `pixi lock` | ✅ | ✅ | Multi-platform lockfile from any OS |
| `pixi-pack` | ✅ | ✅ | Cross-platform packing |
| Bootstrap install | `curl \| bash` | `iwr -useb pixi.sh/install.ps1 \| iex` | Different install scripts |

**Key insight:** `pixi run -e <name> <cmd>` is cross-platform by design. Since our command wrappers use this as the primary pattern, the env activation path works on Windows without modification — **if the wrappers themselves are cross-platform.**

### 2.2 Pixi Shell-Hook for `activate`

Pixi's `pixi shell-hook` outputs shell-specific activation code:

```bash
# Bash/Zsh:
eval "$(pixi shell-hook -s bash)"

# PowerShell:
pixi shell-hook -s powershell | Invoke-Expression

# cmd.exe:
pixi shell-hook -s cmd > activate_tmp.bat && activate_tmp.bat
```

This could replace much of our custom `activate` script's env setup logic.

---

## 3. Per-Script Windows Assessment

### 3.1 `activate` — NEEDS WINDOWS EQUIVALENT

**Why:** Must modify the parent shell (PATH, PROJECT_ROOT, PYTHONPATH). Cannot be replaced with a child process.

**Current bash-specific features:**
- `BASH_SOURCE[0]` for script location resolution
- `source` semantics (modifying caller's environment)
- `shopt -s nullglob` / `setopt NULL_GLOB` (bash/zsh compatibility)
- `chmod +x` for commands/ scripts (no-op on Windows)
- `grep -oP` for pixi.toml parsing (PCRE, not available in PowerShell natively)

**Options:**

| Option | Effort | Coverage | Recommended? |
|--------|--------|----------|-------------|
| **A. Write `activate.ps1`** | Medium | PowerShell on Windows | Yes — v1 |
| **B. Use `pixi shell-hook` to replace activate** | Low | All pixi-supported shells | Investigate — could eliminate custom scripts entirely |
| **C. Python `activate.py`** | Medium | All platforms with Python | No — chicken-and-egg (Python comes FROM pixi) |
| **D. Do nothing** | Zero | WSL/Git Bash users only | Acceptable if Windows is not a v1 target |

**Recommendation: Option B (investigate pixi shell-hook) with Option A as fallback.**

If `pixi shell-hook` can set PATH, PROJECT_ROOT, and PYTHONPATH, then `activate` reduces to:
1. Bootstrap pixi (platform-specific: `curl | bash` or `iwr | iex`)
2. Run `pixi install` if needed
3. `eval "$(pixi shell-hook)"` (or PowerShell equivalent)
4. Display status (could be a pixi task: `pixi run status`)

The status display could be a Python script (`scripts/show_status.py`) invoked by pixi — cross-platform by construction.

**Skeleton for `activate.ps1` (if Option A):**

```powershell
# activate.ps1 — PowerShell equivalent of activate
$ErrorActionPreference = "Stop"

# Section 1: Path Resolution
$BASEDIR = Split-Path -Parent $MyInvocation.MyCommand.Path

# Section 2: Pixi Bootstrap
if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    Write-Host "First-time setup: Installing pixi..."
    iwr -useb https://pixi.sh/install.ps1 | iex
}

# Section 3: Environment Install
if ((Test-Path "$BASEDIR\pixi.toml") -and -not (Test-Path "$BASEDIR\.pixi\envs")) {
    Write-Host "Installing environments from pixi.toml..."
    Push-Location $BASEDIR
    pixi install
    Pop-Location
}

# Section 4: Environment Setup
$env:PROJECT_ROOT = $BASEDIR

# Add repos/ to PYTHONPATH
if (Test-Path "$BASEDIR\repos") {
    Get-ChildItem "$BASEDIR\repos" -Directory | ForEach-Object {
        $env:PYTHONPATH = "$($_.FullName);$env:PYTHONPATH"
    }
}

# Add commands/ to PATH
$env:PATH = "$BASEDIR\commands;$env:PATH"

# Section 5: Status Display (delegate to cross-platform Python)
pixi run -e default python "$BASEDIR\scripts\show_status.py"
```

### 3.2 Command Wrappers (`commands/*`) — REPLACE WITH PIXI TASKS

**Current pattern (bash):**
```bash
#!/bin/bash
cd "$PROJECT_ROOT" || exit 1
pixi run -e claudechic claudechic "$@"
```

**Windows problem:** Bash scripts don't run on native Windows (no `#!/bin/bash`, no `$@`).

**Solution: Pixi tasks replace command wrappers entirely.**

In `pixi.toml`:
```toml
[feature.claudechic.tasks]
claudechic = "claudechic"

[feature.jupyter.tasks]
jupyter = "jupyter lab"

[feature.r-analysis.tasks]
r-analysis = "R"
```

Usage becomes:
```bash
pixi run -e claudechic claudechic    # Works on ALL platforms
pixi run -e jupyter jupyter lab      # Works on ALL platforms
```

**Impact:** The `commands/` directory pattern is Unix-specific (relies on PATH + executable scripts). On Windows, pixi tasks are the equivalent. The `commands/` seam still works for Unix users who want shell scripts on PATH, but the **canonical cross-platform invocation is `pixi run`**.

**Recommendation for v1:** Keep `commands/` for Unix. Document `pixi run -e <name> <task>` as the cross-platform equivalent. Add pixi tasks to `pixi.toml` for every command wrapper. Don't write `.bat` or `.ps1` wrappers for each command — that's what pixi tasks solve.

### 3.3 Guardrail Hook Scripts — MAJOR WINDOWS ISSUE

**The problem:** Claude Code hooks are configured as shell commands in `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "command",
        "command": ".claude/guardrails/hooks/bash_guard.sh"
      }]
    }]
  }
}
```

The generated hooks are bash scripts with embedded Python heredocs:

```bash
#!/usr/bin/env bash
INPUT=$(cat)
export HOOK_INPUT="${INPUT}"
python3 << 'PYEOF'
import json, os, re, sys
# ... rule matching logic ...
PYEOF
```

**On Windows:** `.sh` files don't execute natively. The `python3 << 'PYEOF'` heredoc syntax doesn't work in cmd.exe or PowerShell.

**Options:**

| Option | Effort | Recommendation |
|--------|--------|---------------|
| **A. Generate pure Python hooks** | Medium | **YES — best option** |
| **B. Generate both `.sh` and `.ps1` hooks** | Large | No — doubles maintenance |
| **C. Generate `.sh` + rely on Git Bash/WSL** | Zero | Acceptable short-term |

**Recommendation: Generate pure Python hook scripts.**

The bash wrapper is thin — it just reads stdin, sets env vars, and calls python3 with an inline script. Replace with:

```python
#!/usr/bin/env python3
"""bash_guard.py — AUTO-GENERATED by generate_hooks.py"""
import json, os, re, sys

data = json.loads(sys.stdin.read())
command = data.get('tool_input', {}).get('command', '')
# ... identical rule matching logic (already Python) ...
```

The change to `generate_hooks.py` is straightforward:
1. Change output filenames from `*_guard.sh` to `*_guard.py`
2. Remove the bash wrapper — emit the Python directly as the script
3. Add `#!/usr/bin/env python3` shebang (works on Unix, ignored on Windows where `.py` is associated)
4. Update `.claude/settings.json` references from `.sh` to `.py`
5. Use `python3 .claude/guardrails/hooks/bash_guard.py` as the command (or just the path if `.py` is executable)

**This is the highest-value Windows fix** — it affects every Claude Code session, and the Python code is already written (it's just wrapped in a bash heredoc today).

### 3.4 `claudechic-remote` — LOW PRIORITY

The `submodules/claudechic/scripts/claudechic-remote` script is a convenience wrapper for auto-restarting claudechic in remote mode. It uses:
- `trap` for signal handling
- Bash loop with sleep for restart logic
- `>/dev/null 2>&1` for output redirection

**Assessment:** Developer convenience script, not part of the core workflow. Low priority for Windows. Users on Windows can run `pixi run -e claudechic claudechic --remote-port 9999` directly.

### 3.5 `claudechic` Python Code — MOSTLY CROSS-PLATFORM

Claudechic's Python code has some Unix-specific areas:

| Component | Unix-specific? | Impact |
|-----------|---------------|--------|
| `shell_runner.py` (PTY execution) | **YES** — uses `pty` module | `/shell` command won't preserve colors on Windows; falls back to `interactive only` |
| `processes.py` (child process tracking) | **YES** — returns empty list on Windows | Shell process display won't work; non-critical |
| `features/worktree/git.py` | No — uses `subprocess` | Git commands are cross-platform |
| `app.py` (SDK hooks) | No — pure Python | Cross-platform |
| `commands.py` (shell dispatch) | Partial — auto-detects interactive commands | Already has Windows fallback logic |

**Assessment:** Claudechic already handles Windows gracefully with degraded features. The core workflow (Claude Code + TUI) works. Shell integration is degraded. Not a blocker.

### 3.6 Test Scripts (`tests/ci/*.sh`) — SEPARATE CONCERN

CI tests are bash scripts. They run in CI environments (Linux containers), not on user machines. **No Windows equivalent needed** — CI targets Linux.

### 3.7 `role_guard.py` — ALREADY CROSS-PLATFORM

Pure Python. Uses `os.environ`, `pathlib.Path`, `json`. No shell dependencies. Works on all platforms.

### 3.8 `generate_hooks.py` — ALREADY CROSS-PLATFORM (generator)

Pure Python. Uses `pathlib`, `yaml`, `json`. The generator itself runs anywhere. Only its **output** (bash scripts) is platform-specific.

---

## 4. Summary: What Needs Windows Equivalents?

### Must Have (blocks Windows users)

| Script | Current | Windows Fix | Effort |
|--------|---------|-------------|--------|
| **`activate`** | Bash only | Write `activate.ps1` OR leverage `pixi shell-hook` | Medium |
| **Guardrail hooks** (`hooks/*.sh`) | Bash + embedded Python | Change `generate_hooks.py` to emit pure `.py` scripts | Medium |

### Should Have (improves Windows experience)

| Script | Current | Windows Fix | Effort |
|--------|---------|-------------|--------|
| **Command wrappers** (`commands/*`) | Bash scripts on PATH | Add pixi tasks to `pixi.toml` as cross-platform equivalent | Small |

### Won't Need (acceptable as-is)

| Script | Rationale |
|--------|-----------|
| `claudechic-remote` | Developer convenience; direct `pixi run` works |
| `tests/ci/*.sh` | CI runs on Linux |
| `commands/require_env` | Being deleted in pixi migration |
| claudechic PTY/process tracking | Already degrades gracefully on Windows |

---

## 5. Recommended Strategy

### Phase 1 (v1): Pure Python Guardrail Hooks

**Highest impact, cleanest fix.**

Change `generate_hooks.py` to emit `*_guard.py` instead of `*_guard.sh`. The Python code is already written — it's just wrapped in a bash heredoc today. Unwrapping it:

1. Makes hooks cross-platform (Windows, macOS, Linux)
2. Removes the bash dependency for the most critical path (every Claude Code tool call goes through hooks)
3. Simplifies the generated code (no bash↔Python boundary)
4. Makes hooks testable as Python modules

**Estimated change:** ~50 lines in `generate_hooks.py` (the `generate_*_guard` functions). The inline Python becomes the entire script.

### Phase 2 (v1): Investigate `pixi shell-hook` for `activate`

Test whether `pixi shell-hook` + a cross-platform status script can replace the custom `activate` entirely:

```bash
# Unix:
eval "$(pixi shell-hook -s bash)"
pixi run -e default python scripts/show_status.py

# PowerShell:
pixi shell-hook -s powershell | Invoke-Expression
pixi run -e default python scripts/show_status.py
```

If this works, the `activate` script reduces to 5 lines per platform (bootstrap pixi + shell-hook + status). The status display moves to a Python script — cross-platform by construction.

If `pixi shell-hook` doesn't cover all our needs (PATH for `commands/`, PYTHONPATH for `repos/`), fall back to writing `activate.ps1`.

### Phase 3 (v1): Add Pixi Tasks

Add tasks to `pixi.toml` for every command wrapper. This provides a cross-platform invocation path that works without the `commands/` PATH mechanism:

```toml
[feature.claudechic.tasks]
claudechic = "claudechic"
```

Unix users still get `commands/claudechic` on PATH. Windows users use `pixi run -e claudechic claudechic`. Both work.

---

## 6. Architecture Impact on Seams

### The Commands Seam Splits on Windows

On Unix, the commands seam is: "drop an executable in `commands/`, it's on PATH."
On Windows, this doesn't work — no shebang, no `chmod +x`, PATH handling differs.

The cross-platform equivalent seam is: "add a pixi task in `pixi.toml`."

**This means the Commands seam has two expressions:**
- Unix: `commands/<name>` (shell script on PATH)
- Cross-platform: `pixi.toml [feature.<name>.tasks]` (pixi task)

The `activate` script (seam registry) only needs to know about the Unix variant. Pixi handles the cross-platform variant natively.

### The Guardrail Seam Becomes Cleaner

Moving from bash-wrapper-around-Python to pure Python hooks actually **improves** the guardrail seam:
- No shell dependency in the hook execution path
- Hooks are testable as Python modules
- `generate_hooks.py` generates simpler output
- `.claude/settings.json` references `python3 .claude/guardrails/hooks/bash_guard.py` — works everywhere Python3 is available (which pixi guarantees)

---

## 7. Open Questions

1. **Does Claude Code on Windows invoke hook commands via cmd.exe, PowerShell, or `python3 <script>`?** This determines whether pure Python hooks need a `python3` prefix in `settings.json` or can rely on `.py` file association.

2. **Does `pixi shell-hook` set custom env vars (PROJECT_ROOT) or only conda/pixi activation?** If only pixi activation, we still need custom logic for PROJECT_ROOT and PYTHONPATH.

3. **Is Windows a v1 target?** If not, document "Windows support: use WSL" and defer all fixes. If yes, prioritize pure Python hooks (Phase 1).
