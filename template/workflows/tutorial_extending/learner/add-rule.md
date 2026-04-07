# Phase 1: Add a Global Rule

In this exercise, the user adds a new rule to `global/rules.yaml`. This teaches them how the guardrail system works.

## Step 1: Show the Current Rules

Read and display `global/rules.yaml` to the user. Explain:

> "Global rules apply to every workflow in this project. Each rule has:
> - **id** — unique identifier
> - **trigger** — which tool use triggers evaluation (e.g., `PreToolUse/Bash`)
> - **enforcement** — `deny` (hard block), `warn` (must acknowledge), or `log` (silent audit)
> - **detect.pattern** — regex that matches the blocked action
> - **message** — what the agent sees when the rule fires"

## Step 2: Explain the Exercise

> "You're going to add a new rule. Here's an example — a `warn` rule that flags when someone tries to install Python packages during a workflow:"
>
> ```yaml
> - id: warn_pip_install
>   trigger: PreToolUse/Bash
>   enforcement: warn
>   detect:
>     pattern: "pip install|pip3 install"
>   message: "Installing packages during a workflow may break reproducibility. Acknowledge if intentional."
> ```
>
> "You can add this exact rule, or create your own. Some ideas:
> - Warn on `curl` or `wget` commands
> - Log when `docker` commands are used
> - Warn on `chmod 777`
> - Log when files in `docs/` are edited"

## Step 3: Guide the Edit

Help the user add their rule to `global/rules.yaml`. If they want to do it themselves, let them. If they ask for help, offer to add the example rule.

The rule should be appended to the existing `rules:` list in the file.

## Step 4: Verify

After the edit, verify the YAML still parses:

```bash
python -c "import yaml; data = yaml.safe_load(open('global/rules.yaml')); print(f'OK: {len(data)} rules'); [print(f'  - {r[\"id\"]}') for r in data]"
```

Also verify the ManifestLoader picks it up:

```bash
python -c "
from pathlib import Path
from claudechic.workflows.loader import ManifestLoader
from claudechic.workflows import register_default_parsers
loader = ManifestLoader(Path('global'), Path('workflows'))
register_default_parsers(loader)
result = loader.load()
print(f'Total rules: {len(result.rules)}')
for r in result.rules:
    if r.namespace == 'global':
        print(f'  {r.id} [{r.enforcement}]')
"
```

## Step 5: Complete

Once verified, create the completion marker:

```bash
echo "Rule added to global/rules.yaml" > tutorial_extending_rule_added.txt
```

Then call `advance_phase` to proceed.
