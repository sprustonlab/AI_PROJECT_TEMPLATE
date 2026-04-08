# Phase 2: Add an Advance Check

In this exercise, the user adds a new advance check to this tutorial's own workflow YAML. This teaches them how phase transitions are gated.

## Step 1: Explain Advance Checks

> "Advance checks are gate conditions that must ALL pass before a phase can transition to the next one (AND semantics). There are four types:
> - **file-exists-check** -- verifies a file exists at a given path
> - **file-content-check** -- verifies file content matches a regex pattern
> - **command-output-check** -- verifies a command's stdout matches a regex pattern
> - **manual-confirm** -- prompts the user to approve in the TUI
>
> If any check fails, `advance_phase` is blocked and returns an error message."

## Step 2: Show an Example

Read and display `workflows/tutorial_extending/tutorial_extending.yaml` to the user. Point out the advance_checks sections:

> "Look at the phases in this workflow -- each one has a `file-exists-check` for a marker file. The `edit-yaml-config` phase only has a file-exists check. You're going to add a `manual-confirm` check to it, so advancing from that phase will require BOTH the marker file AND user confirmation."

## Step 3: Explain the Exercise

> "You're going to add a new advance check to this workflow's `edit-yaml-config` phase. Currently it only has a `file-exists-check`. You'll add a `manual-confirm` check.
>
> Find the `edit-yaml-config` phase in `workflows/tutorial_extending/tutorial_extending.yaml` and add this under its `advance_checks`:
>
> ```yaml
>       - type: manual-confirm
>         prompt: 'Ready to complete the extending tutorial?'
> ```
>
> This means advancing from `edit-yaml-config` will now require BOTH the marker file to exist AND user confirmation."

## Step 4: Guide the Edit

Help the user edit `workflows/tutorial_extending/tutorial_extending.yaml`. The new check goes under the existing `advance_checks` list for the `edit-yaml-config` phase.

**Before:**
```yaml
  - id: edit-yaml-config
    file: edit-yaml-config
    ...
    advance_checks:
      - type: file-exists-check
        path: "tutorial_extending_config_edited.txt"
        on_failure:
          message: "Create tutorial_extending_config_edited.txt after editing the YAML config."
          severity: warning
```

**After:**
```yaml
  - id: edit-yaml-config
    file: edit-yaml-config
    ...
    advance_checks:
      - type: file-exists-check
        path: "tutorial_extending_config_edited.txt"
        on_failure:
          message: "Create tutorial_extending_config_edited.txt after editing the YAML config."
          severity: warning
      - type: manual-confirm
        prompt: "Ready to complete the extending tutorial?"
```

## Step 5: Verify

After the edit, verify the YAML parses and the ManifestLoader accepts it:

```bash
python -c "
import yaml
data = yaml.safe_load(open('workflows/tutorial_extending/tutorial_extending.yaml'))
for phase in data['phases']:
    checks = phase.get('advance_checks', [])
    if checks:
        print(f'{phase[\"id\"]}: {len(checks)} checks')
        for c in checks:
            print(f'  - {c[\"type\"]}')
"
```

Also verify no loader errors:

```bash
python -c "
from pathlib import Path
from claudechic.workflows.loader import ManifestLoader
from claudechic.workflows import register_default_parsers
loader = ManifestLoader(Path('global'), Path('workflows'))
register_default_parsers(loader)
result = loader.load()
print(f'Errors: {len(result.errors)}')
if result.errors:
    for e in result.errors:
        print(f'  {e.source}: {e.message}')
else:
    print('No errors -- YAML is valid!')
"
```

## Step 6: Complete

Once verified, create the completion marker:

```bash
echo "Advance check added to tutorial_extending workflow" > tutorial_extending_check_added.txt
```

Then call `advance_phase` to proceed.

## What You Learned

> "You just modified this workflow while it was running! The change takes effect on the next `advance_phase` call. This is how workflows are iteratively refined -- edit the YAML, verify it loads, and the system adapts."
