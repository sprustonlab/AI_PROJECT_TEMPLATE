# Phase 4: Hints

In this exercise, the user adds and customizes hints. This teaches them how the toast notification system works to guide users during workflows.

## Step 1: Explain Hints

> "Hints are toast notifications that appear in the TUI to guide the user. They're declared in workflow YAML and have three key properties:
>
> - **message** -- the text shown to the user
> - **lifecycle** -- controls when and how often the hint appears:
>   - `show-once` -- appears the first time the trigger fires, never again
>   - `show-until-resolved` -- keeps showing until the trigger condition becomes false
>   - `show-every-session` -- always shows when the trigger fires (for critical reminders)
>   - `cooldown` -- shows at most once per cooldown window (requires `cooldown_seconds`)
> - **id** -- unique identifier (auto-generated for phase hints if omitted)
>
> Hints can be defined at two levels:
> 1. **Workflow-level** -- in the top-level `hints:` section, shown whenever the workflow is active
> 2. **Phase-level** -- nested inside a phase definition, shown only during that phase"

## Step 2: Show Existing Hints

Read `workflows/tutorial_extending/tutorial_extending.yaml` and point out the hints sections:

> "Look at the hints already in this workflow:
>
> - **Workflow-level hint** (`extending-overview`) -- shows every session to remind users what this tutorial covers
> - **Phase-level hints** -- each phase has `show-once` hints that explain what to do in that phase
>
> Also look at `global/hints.yaml` -- these are global hints that fire regardless of which workflow is active. The welcome message and workflow tip are defined there."

Read and display `global/hints.yaml` to the user.

## Step 3: Explain the Exercise

> "You're going to add hints at both levels:
>
> **Task A: Add a workflow-level hint** to `workflows/tutorial_extending/tutorial_extending.yaml`:
> ```yaml
> hints:
>   - id: extending-overview
>     ...existing hint...
>   - id: my-custom-hint
>     message: 'Remember: read the phase instructions before starting work!'
>     lifecycle: show-every-session
> ```
>
> **Task B: Add a phase-level hint** to any phase in this workflow. For example, add a hint to the `add-rule` phase:
> ```yaml
>   - id: add-rule
>     file: add-rule
>     hints:
>       - message: 'Phase 1/4: Add a Rule...'
>         lifecycle: show-once
>       - message: 'Hint: rules can use regex patterns in the detect field'
>         lifecycle: show-once
> ```
>
> **Task C (optional): Add a global hint** to `global/hints.yaml`:
> ```yaml
> - id: my-global-hint
>   message: 'Tip: Use /hints off to disable toast notifications.'
>   lifecycle: show-once
> ```
>
> Try at least Task A and B."

## Step 4: Guide the Edits

Help the user edit the YAML files. Make sure:

- Workflow-level hints have `id`, `message`, and `lifecycle`
- Phase-level hints need `message` and `lifecycle` (id is auto-generated)
- The YAML indentation is correct (2 spaces)
- Lifecycle is one of: `show-once`, `show-until-resolved`, `show-every-session`, `cooldown`
- If using `cooldown`, `cooldown_seconds` must also be set

## Step 5: Verify

After the edits, verify everything parses correctly:

```bash
python -c "
import yaml
data = yaml.safe_load(open('workflows/tutorial_extending/tutorial_extending.yaml'))
wf_hints = data.get('hints', [])
phase_hints = sum(len(p.get('hints', [])) for p in data.get('phases', []))
print(f'Workflow-level hints: {len(wf_hints)}')
print(f'Phase-level hints: {phase_hints}')
for h in wf_hints:
    print(f'  [{h.get(\"lifecycle\")}] {h[\"id\"]}: {h[\"message\"][:60]}...')
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

## Step 6: Complete

Once verified, create the completion marker:

```bash
echo "Hints customized" > tutorial_extending_config_edited.txt
```

Then call `advance_phase` to proceed.

## Graduation

> "Congratulations! You've learned 4 ways to extend the AI Project Template:
>
> 1. **Add a global rule** -- guardrails that apply everywhere
> 2. **Add an advance check** -- gate conditions for phase transitions
> 3. **Edit an agent role** -- customize how agents behave
> 4. **Add hints** -- toast notifications to guide users through workflows
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
> git checkout -- global/rules.yaml global/hints.yaml workflows/tutorial_extending/tutorial_extending.yaml workflows/project_team/
> rm -f tutorial_extending_*.txt
> ```"
