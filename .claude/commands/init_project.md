# Initialize a New Project from AI_PROJECT_TEMPLATE

You are helping the user set up a new project using the AI_PROJECT_TEMPLATE. Guide them conversationally through the setup, explain WHY each option matters, then run Copier with their choices.

## Step 1: Understand the User's Context

Ask the user about their project. You need to understand:

1. **Project name** — What should we call this project? (used for directory name and environment naming)
2. **Project type** — Is this a general software project or scientific computing/research?
3. **Existing code** — Are they starting fresh or wrapping an existing codebase?

Be conversational. If they say "I have a Python project for analyzing neuroscience data", you already know: project_type=scientific, science_domain=biology. Don't ask questions you can infer.

## Step 2: Explain Quick Start Presets

Every project always gets the full infrastructure: guardrails (permission rules), workflows (phase-gated processes), hints (onboarding notifications), and the Project Team (multi-agent collaboration). The `quick_start` preset controls how many **examples** are pre-loaded:

| Preset | What you get | Best for |
|--------|-------------|----------|
| **everything** | All example rules, specialist roles, tutorial workflows, hints, pattern miner | Learning the system — explore everything |
| **defaults** | Example rules, specialist roles, hints. No tutorials, no pattern miner. | First real project — useful defaults without clutter |
| **empty** | Infrastructure only — no examples, no tutorials, no hints | Experienced users who'll add what they need |
| **custom** | You pick each category individually | Specific needs |

**Recommendation:** Start with `defaults` for a first project, `everything` if they want to learn.

## Step 3: Run Copier

Once you have all answers, construct and run the Copier command:

```bash
copier copy --trust --data project_name="<name>" \
  --data quick_start="<everything|defaults|empty|custom>" \
  --data existing_codebase="<path_or_empty>" \
  https://github.com/sprustonlab/AI_PROJECT_TEMPLATE <target_dir>
```

For the `custom` preset, you can also pass individual flags:
```bash
copier copy --trust --data project_name="<name>" \
  --data quick_start="custom" \
  --data example_rules=true \
  --data example_agent_roles=true \
  --data example_workflows=false \
  --data example_hints=true \
  --data example_patterns=false \
  --data existing_codebase="" \
  https://github.com/sprustonlab/AI_PROJECT_TEMPLATE <target_dir>
```

Before running, confirm the choices with the user in a clear summary table.

If Copier is not installed, install it first:
```bash
pip install copier
```

## Step 4: Report Results

After Copier runs, report:
1. What files were created
2. Which preset was used and what's included
3. Next steps:
   - `cd <project_name> && source activate` (Linux/macOS)
   - `cd <project_name>; . .\activate.ps1` (Windows/PowerShell)
   - If existing codebase was integrated, remind about `.claude/` merge if needed

## Important Notes

- If the user provides a path to an existing codebase, the post-generation task will symlink it into `repos/` and check for `.claude/` conflicts
- The `activate` script handles pixi bootstrap, environment installation, and PATH setup automatically
- All example content is just files in the right directories — it can be added or removed later without breaking anything
