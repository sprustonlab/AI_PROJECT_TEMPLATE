# Seam Analysis: Commands and Skills

> Two seams that are already clean: `commands/` for CLI tools and `.claude/commands/` for Claude Code skills. Both work by filesystem convention — drop a file in the right directory, it's discovered automatically.

---

## Seam 2: Commands (`commands/`)

### What Exists Today

The `commands/` directory is a conventional bin directory. The `activate` script adds it to PATH and ensures everything in it is executable.

**Discovery mechanism (`activate` lines 113-121):**
```bash
# Ensure scripts in commands/ are executable (skip .md files)
if [[ -d "$BASEDIR/commands" ]]; then
    for script in "$BASEDIR/commands"/*; do
        [[ -f "$script" ]] && [[ "$script" != *.md ]] && chmod +x "$script"
    done
fi
# Add commands/ to PATH
export PATH="$BASEDIR/commands:$PATH"
```

**Display mechanism (`activate` lines 214-231):**
```bash
# Scans commands/ for executable, non-.md, non-dotfiles
# Prints them as "CLI commands:"
```

**Current contents:**
```
commands/
├── claudechic      # Env-activating wrapper (sources require_env, runs tool)
├── jupyter          # Env-activating wrapper (sources require_env, runs tool)
├── require_env      # Infrastructure utility (sources/executes, not a tool wrapper)
└── require_env.md   # Documentation (skipped by discovery — .md extension)
```

### The Two Command Patterns

Reading the actual files reveals two distinct patterns:

#### Pattern A: Env-Activating Wrapper

Used by `commands/claudechic` and `commands/jupyter`. The pattern:

```bash
#!/bin/bash
# 1. Resolve project root
if [[ -z "$PROJECT_ROOT" ]]; then
    PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi
cd "$PROJECT_ROOT" || exit 1

# 2. Ensure environment is installed and activated
source "$PROJECT_ROOT/commands/require_env" <env-name> || exit 1

# 3. (Optional) One-time setup
if ! python -c "import <package>" 2>/dev/null; then
    pip install -e "$PROJECT_ROOT/submodules/<package>" --quiet || exit 1
fi

# 4. Run the tool
python -m <tool> "$@"
```

**What varies:** env name (step 2), optional setup (step 3), tool invocation (step 4).
**What's constant:** project root resolution (step 1), require_env sourcing (step 2).

`commands/jupyter` is even simpler — it's the minimal case:

```bash
#!/bin/bash
source "$(dirname "${BASH_SOURCE[0]}")/require_env" jupyter || exit 1
jupyter lab "$@"
```

#### Pattern B: Infrastructure Utility

Used by `commands/require_env`. This is not a tool wrapper — it's infrastructure that other commands source. It can be both sourced (returns to caller's shell with env activated) and executed (exits with status code).

```bash
# Detect if sourced or executed
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    EXIT_CMD="return"
else
    EXIT_CMD="exit"
fi
```

This is a special case. Most commands will follow Pattern A.

### The Contract

A file in `commands/` is a command if and only if:

| Requirement | How enforced | Notes |
|-------------|-------------|-------|
| Is a regular file | `[[ -f "$script" ]]` in activate | Not a directory or symlink target |
| Not a `.md` file | `[[ "$script" != *.md ]]` in activate | `.md` files are documentation, not commands |
| Not a dotfile | `[[ "$basename_script" != .* ]]` in activate display | Hidden files are excluded from display |
| Made executable | `chmod +x` by activate | Automatic — author doesn't need to remember |

**Environment available to every command:**

| Env var | Value | Set by |
|---------|-------|--------|
| `PROJECT_ROOT` | Absolute path to project root | `activate` |
| `SLC_BASE` | Same as `PROJECT_ROOT` (if python-env active) | `activate` / python-env |
| `SLC_PYTHON` | Path to base conda python (if python-env active) | `activate` / python-env |
| `PATH` | Includes `commands/` itself | `activate` |
| `PYTHONPATH` | Includes `repos/*/` (if repos exist) | `activate` |

**No registration needed.** Drop a file in `commands/`, it's on PATH after next `source activate`. The activate script auto-discovers and auto-chmods.

### How to Add a New Command

#### For an env-activating wrapper (most common):

```
1. Create commands/<name> with this template:

   #!/bin/bash
   # <name> — Launch <description>
   source "$(dirname "${BASH_SOURCE[0]}")/require_env" <env-name> || exit 1
   <tool-command> "$@"

2. (Optional) Create commands/<name>.md with usage documentation.

3. Test:
   source activate          → shows <name> in CLI commands
   <name> --help            → runs the tool
```

#### For a standalone script (no env needed):

```
1. Create commands/<name> with any executable script (bash, python, etc.)
   - Use #!/bin/bash or #!/usr/bin/env python3 shebang
   - Can assume PROJECT_ROOT is set (if activate was sourced)

2. Test:
   source activate          → shows <name> in CLI commands
   <name>                   → runs the script
```

### Swap Test

**Add a Rust command without touching any existing files:**

```bash
#!/bin/bash
# commands/my-rust-tool — Run a Rust-based analysis tool
source "$(dirname "${BASH_SOURCE[0]}")/require_env" rust-env || exit 1
cargo run --manifest-path "$PROJECT_ROOT/repos/my-tool/Cargo.toml" -- "$@"
```

Does `activate` change? No — it discovers `commands/my-rust-tool` automatically.
Does `require_env` change? No — it installs and activates via the env backend.
Does any existing command change? No.

**The seam is clean.** Commands are fully decoupled from each other and from the env management backend.

---

## Seam 3: Skills (`.claude/commands/*.md`)

### What Exists Today

Claude Code discovers skills by scanning `.claude/commands/` for `.md` files. This is Claude Code's built-in convention — not something AI_PROJECT_TEMPLATE invented.

**Discovery mechanism:** Claude Code automatically registers any `.md` file in `.claude/commands/` (or `~/.claude/commands/` for global skills) as a slash command. The filename (minus `.md`) becomes the command name.

**Display mechanism (`activate` lines 233-251):**
```bash
# Scans .claude/commands/ for .md files
# Extracts first H1 heading as description
# Displays as: /<skill_name> - <H1 title>
```

**Current contents:**
```
.claude/commands/
└── ao_project_team.md    # Displayed as: /ao_project_team - Launch Project Team
```

### Skill File Format

Reading `ao_project_team.md`:

```markdown
# Launch Project Team

Read and follow: `AI_agents/project_team/COORDINATOR.md`
```

That's the entire file. A skill is a **prompt** — instructions that Claude receives when the user types `/<skill_name>`. Claude Code handles the rest.

**Format rules (from Claude Code's convention):**

| Element | Purpose | Required? |
|---------|---------|-----------|
| First `# ` heading | Skill title (shown in skill list) | Recommended — activate extracts it for display |
| Body text | Instructions for Claude | Required — this IS the skill |
| YAML frontmatter | Optional metadata (description, etc.) | Optional — Claude Code supports it |
| `$ARGUMENTS` placeholder | Captures user input after the slash command | Optional |

### The Contract

A file in `.claude/commands/` is a skill if and only if:

| Requirement | How enforced | Notes |
|-------------|-------------|-------|
| Is a `.md` file | Claude Code convention | Only `.md` files are registered |
| In `.claude/commands/` directory | Claude Code convention | Fixed path, not configurable |
| Contains text instructions | By definition | The file content IS the prompt |

**No registration, no manifest, no configuration.** Claude Code scans the directory. The skill exists if and only if the file exists.

**What the skill can assume:**
- Claude has access to the full project context (files, git history, tools)
- Claude can read any file the skill references (e.g., `AI_agents/project_team/COORDINATOR.md`)
- Claude can use all available tools (Bash, Read, Write, Edit, Agent, MCP tools)
- `$ARGUMENTS` contains any text the user typed after the slash command

### What Makes a Good Skill vs a Bad One

**Good skills:**

| Property | Why | Example |
|----------|-----|---------|
| Short entry point | Claude reads the whole file on invocation — long files waste context | `ao_project_team.md`: 2 lines, points to COORDINATOR.md |
| Delegates to persistent files | The skill triggers a workflow defined elsewhere — updates to the workflow don't require skill changes | Points to `AI_agents/project_team/COORDINATOR.md` |
| Clear instruction verb | Claude knows what to DO | "Read and follow:", "Analyze:", "Generate:" |
| Uses `$ARGUMENTS` for parameterization | Users can pass context | `/review $ARGUMENTS` where user types `/review PR #123` |

**Bad skills:**

| Anti-pattern | Why | Fix |
|--------------|-----|-----|
| 500-line skill file | Wastes context window on every invocation | Move logic to a referenced file, skill becomes a 2-line pointer |
| Hard-coded paths | Breaks if project structure changes | Use relative paths from project root |
| Duplicates logic from another skill | Maintenance burden — changes must be made in two places | Extract shared logic into a referenced file |
| No clear success criteria | Claude doesn't know when it's done | Include "Done when:" or "Output:" in the instructions |

### How to Add a New Skill

```
1. Create .claude/commands/<skill-name>.md with:

   # <Descriptive Title>

   <Instructions for Claude — what to read, what to do, what to output>

2. Test:
   source activate     → shows /<skill-name> - <Title> in skills list
   Type /<skill-name> in Claude Code → Claude follows the instructions

3. (Optional) If the skill needs supporting files:
   - Put them in a logical location (AI_agents/, scripts/, etc.)
   - Have the skill reference them: "Read and follow: <path>"
```

### Skill Template (Minimal)

```markdown
# <Title>

<One-line description of what this does.>

Read: `<path/to/instructions.md>`

<Additional context or constraints.>
```

### Skill Template (With Arguments)

```markdown
# <Title>

<One-line description.>

The user wants: $ARGUMENTS

<Instructions for how Claude should handle the request.>
```

### Swap Test

**Add a code review skill without touching any existing files:**

Create `.claude/commands/review.md`:
```markdown
# Code Review

Review the code changes described below. Check for:
- Correctness and edge cases
- Style consistency with existing code
- Performance implications
- Security concerns

Focus on: $ARGUMENTS
```

Does `activate` change? No — it discovers the new `.md` file automatically.
Does `ao_project_team.md` change? No.
Does Claude Code need reconfiguration? No — it auto-discovers.

**The seam is clean.** Skills are fully decoupled from each other, from commands, and from the rest of the template.

---

## Cross-Seam Interaction: Commands and Skills

Commands and skills are independent seams that occasionally reference each other:

| Direction | How | Example |
|-----------|-----|---------|
| Skill → Command | Skill instructs Claude to run a command via Bash tool | "Run `mine-patterns --scan-all`" |
| Skill → Skill | Skill references another skill by path | `ao_project_team.md` could reference a sub-skill |
| Command → Skill | Not possible — commands are shell scripts, skills are Claude prompts | N/A |
| Skill → Env | Skill instructs Claude to run code in a managed env | "Run `source commands/require_env jupyter && jupyter nbconvert ...`" |

The seams don't leak into each other. A command doesn't know skills exist. A skill doesn't know how commands are discovered. They share only the filesystem.

---

## Seam Summary

### Commands (`commands/`)

| Property | Value |
|----------|-------|
| **Seam location** | `commands/` directory |
| **Discovery** | Automatic — `activate` adds to PATH, auto-chmods |
| **Contract** | Regular file, not `.md`, not dotfile. Gets `PROJECT_ROOT` and `PATH`. |
| **The law** | Anything executable in `commands/` is a CLI command. Period. |
| **Extension mechanism** | Drop a file. Done. |
| **Documentation convention** | Optional `commands/<name>.md` companion file |
| **Current hole** | None. This seam is already clean. |

### Skills (`.claude/commands/`)

| Property | Value |
|----------|-------|
| **Seam location** | `.claude/commands/` directory |
| **Discovery** | Automatic — Claude Code scans `.md` files |
| **Contract** | `.md` file with instructions for Claude. First `# ` heading is the title. |
| **The law** | Any `.md` file in `.claude/commands/` is a slash command. Period. |
| **Extension mechanism** | Drop a `.md` file. Done. |
| **Best practice** | Short entry point → references detailed instructions elsewhere |
| **Current hole** | None. This seam is already clean. |
