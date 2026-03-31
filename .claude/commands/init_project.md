# Initialize a New Project from AI_PROJECT_TEMPLATE

You are helping the user set up a new project using the AI_PROJECT_TEMPLATE. Guide them conversationally through the setup, explain WHY each option matters, then run Copier with their choices.

## Step 1: Understand the User's Context

Ask the user about their project. You need to understand:

1. **Project name** — What should we call this project? (used for directory name and environment naming)
2. **Project type** — Is this a general software project or scientific computing/research?
3. **Existing code** — Are they starting fresh or wrapping an existing codebase?

Be conversational. If they say "I have a Python project for analyzing neuroscience data", you already know: project_type=scientific, science_domain=biology. Don't ask questions you can infer.

## Step 2: Explain Add-ons and Get Choices

For each add-on, explain the VALUE (not just what it does). Recommend based on their context.

### Guardrails (default: on)
**What it does:** Creates a permission system that controls what Claude Code can do — which tools it can call, which files it can modify, what commands it can run.

**Why it matters:** Without guardrails, Claude Code has unrestricted access. For teams, for production code, or for overnight autonomous runs, guardrails prevent accidents. A single `rm -rf` in the wrong directory or a force-push to main can ruin your day.

**Recommendation:** Keep enabled unless this is a quick prototype you'll throw away.

### Project Team (default: on)
**What it does:** Sets up multi-agent roles — Coordinator, Implementer, Skeptic, Test Engineer, and others. When you run `/ao_project_team`, Claude Code spawns specialized agents that collaborate on your task.

**Why it matters:** Solo Claude is good. A team of specialized Claudes is better. The Skeptic catches bugs the Implementer misses. The Test Engineer writes tests the Implementer wouldn't think of. It's structured peer review, but faster.

**Recommendation:** Keep enabled for any project beyond trivial scripts.

### Pattern Miner (default: off)
**What it does:** Scans your Claude Code conversation history for moments where you corrected Claude — "no, that's wrong", "I already told you", "you missed the point". Extracts these into a structured report that feeds into PATTERNS.md.

**Why it matters:** Claude makes the same mistakes repeatedly across sessions. Pattern mining turns your frustration into systematic improvement. It's the difference between complaining and fixing.

**Recommendation:** Enable if you've been using Claude Code for a while and want to improve its behavior on your specific project.

### Scientific Questions (if project_type == scientific)

If the user chose scientific:

**Science domain** — Ask which domain. This affects suggested skill packs and conventions.
- Biology / Genomics / Neuroscience
- Physics / Cosmology / Materials
- Chemistry / Drug Discovery
- Data Science / ML / Statistics
- Other

**Autonomous agents** — Will Claude run unattended (overnight, weekend GPU jobs)?
If yes, the template adds:
- CLAUDE.md with research goals and success criteria
- CHANGELOG.md as structured agent memory
- Test oracle directories for self-validation
- Stricter guardrails for unattended operation

## Step 3: Run Copier

Once you have all answers, construct and run the Copier command:

```bash
copier copy --data project_name="<name>" \
  --data use_guardrails=<true|false> \
  --data use_project_team=<true|false> \
  --data use_pattern_miner=<true|false> \
  --data project_type="<general|scientific>" \
  --data science_domain="<domain>" \
  --data autonomous_agents=<true|false> \
  --data existing_codebase="<path_or_empty>" \
  https://github.com/<org>/AI_PROJECT_TEMPLATE <target_dir>
```

Before running, confirm the choices with the user in a clear summary table.

If Copier is not installed, install it first:
```bash
pip install copier
```

## Step 4: Report Results

After Copier runs, report:
1. What files were created
2. Which add-ons are active
3. Next steps:
   - `cd <project_name> && source activate` (Linux/macOS)
   - `cd <project_name>; . .\activate.ps1` (Windows/PowerShell)
   - If existing codebase was integrated, remind about `.claude/` merge if needed

## Important Notes

- If the user provides a path to an existing codebase, the post-generation task will symlink it into `repos/` and check for `.claude/` conflicts
- The `activate` script handles pixi bootstrap, environment installation, and PATH setup automatically
- All add-ons are just files in the right directories — they can be added or removed later without breaking anything
