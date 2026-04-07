# Phase 4: Edit YAML Configuration

In this exercise, the user edits this tutorial's own workflow YAML to customize its behavior. This teaches them how to tune workflows without touching code.

## Step 1: Explain YAML Config Options

> "Workflow YAML files have several sections you can customize:
> - **rules** — add, remove, or change enforcement levels (deny/warn/log)
> - **hints** — add toast notifications that guide agents or users
> - **phases** — reorder phases, add new ones, change advance checks
> - **injections** — modify tool inputs based on patterns
>
> Every change takes effect immediately — no code changes needed."

## Step 2: Show Customization Options

Read `workflows/tutorial_extending/tutorial_extending.yaml` and highlight the hints and rules sections. Explain:

> "Here are three things you could change in this workflow's own YAML:
>
> **Option A: Add a new hint** — Add a workflow-level hint that shows every session:
> ```yaml
> hints:
>   - id: my-custom-hint
>     message: 'Remember: read the phase instructions before starting work!'
>     lifecycle: show-every-session
> ```
>
> **Option B: Change an enforcement level** — Change the `protect-workflow-engine` rule from `warn` to `log` (making it silent instead of blocking):
> ```yaml
>   - id: protect-workflow-engine
>     trigger: PreToolUse/Edit
>     enforcement: log    # was 'warn'
>     ...
> ```
>
> **Option C: Add a phase-scoped hint** — Add a hint to a specific phase:
> ```yaml
>   - id: edit-yaml-config
>     file: edit-yaml-config
>     hints:
>       - message: 'Phase 4/4: Almost done! Make one YAML edit to complete the tutorial.'
>         lifecycle: show-once
>       - message: 'Try adding a hint or changing a rule enforcement level.'
>         lifecycle: show-once
> ```
>
> Pick any option — or invent your own change!"

## Step 3: Guide the Edit

Help the user make their chosen edit to `workflows/tutorial_extending/tutorial_extending.yaml`. Make sure:

- The YAML indentation is correct (2 spaces)
- New hints have `id`, `message`, and `lifecycle`
- Enforcement levels are one of: `deny`, `warn`, `log`
- Phase IDs in `phases:` lists match existing phase IDs

## Step 4: Verify

After the edit, verify everything parses correctly:

```bash
python -c "
import yaml
data = yaml.safe_load(open('workflows/tutorial_extending/tutorial_extending.yaml'))
print(f'workflow_id: {data[\"workflow_id\"]}')
print(f'phases: {len(data[\"phases\"])}')
print(f'rules: {len(data.get(\"rules\", []))}')
print(f'hints: {len(data.get(\"hints\", []))}')
print('YAML is valid!')
"
```

And verify the ManifestLoader still loads cleanly:

```bash
python -c "
from pathlib import Path
from claudechic.workflows.loader import ManifestLoader
from claudechic.workflows import register_default_parsers
loader = ManifestLoader(Path('global'), Path('workflows'))
register_default_parsers(loader)
result = loader.load()
errors = [e for e in result.errors if 'extending' in e.source]
if errors:
    print(f'ERRORS in tutorial-extending workflow:')
    for e in errors:
        print(f'  {e.source}: {e.message}')
else:
    print(f'All workflows load cleanly ({len(result.workflows)} workflows, {len(result.rules)} rules)')
"
```

## Step 5: Complete

Once verified, create the completion marker:

```bash
echo "YAML config edited" > tutorial_extending_config_edited.txt
```

Then call `advance_phase` to proceed.

## Graduation

> "Congratulations! You've learned 4 ways to extend the AI Project Template:
>
> 1. **Add a global rule** — guardrails that apply everywhere
> 2. **Add an advance check** — gate conditions for phase transitions
> 3. **Edit an agent role** — customize how agents behave
> 4. **Edit YAML config** — tune workflows without code changes
>
> These are the same tools the Project Team uses internally. You can now customize the system for your own projects.
>
> **Next steps:**
> - Run `/tutorial` to learn about rules, injections, and hints in action
> - Run `/tutorial-toy-project` to build a real project with the agent team
> - Run `/project-team` to start your own project
>
> Run `/tutorial-extending stop` to deactivate this tutorial."

## Revert Note

> "You can revert all tutorial changes with:
> ```bash
> git checkout -- global/rules.yaml workflows/tutorial_extending/tutorial_extending.yaml workflows/project_team/
> rm -f tutorial_extending_*.txt
> ```"
