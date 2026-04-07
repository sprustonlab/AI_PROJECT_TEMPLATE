# Phase 3: Edit an Agent Role

In this exercise, the user edits an agent role markdown file. This teaches them how agent behavior is defined.

## Step 1: Explain Agent Roles

> "Agent roles are markdown files in `workflows/project_team/`. Each file defines one agent's:
> - **Responsibilities** — what the agent does
> - **Workflow** — how it approaches tasks
> - **Communication patterns** — when to use `ask_agent` vs `tell_agent`
> - **Interaction rules** — how it works with other agents
>
> When an agent is spawned with a role, the role file shapes its behavior. Editing the file changes how the agent works in future sessions."

## Step 2: Show Available Roles

List the agent role files:

```bash
ls workflows/project_team/*/identity.md
```

Show the user one role file — `implementer/identity.md` is a good choice because it's clear and practical. Read it aloud and explain the sections.

## Step 3: Explain the Exercise

> "You're going to add a new section to an agent role file. Pick any role — `implementer/identity.md` is a good starting point.
>
> **Task:** Add a new guideline to the Implementation Guidelines section. For example:
>
> ```markdown
> ### Documentation
> - Add docstrings to all public functions
> - Include type hints for function signatures
> - Write a one-line module docstring at the top of each file
> ```
>
> Or add a new entry to the Interaction table, or a new rule in the Rules section.
>
> The point is: you're customizing how this agent behaves. Your change will take effect the next time this role is used."

## Step 4: Guide the Edit

Help the user pick a role file and add their new section or guideline. Suggestions:

- **implementer/identity.md** — add a documentation or logging guideline
- **skeptic/identity.md** — add a new category of things to challenge
- **coordinator/identity.md** — add a new delegation rule
- **test_engineer/identity.md** — add a test coverage requirement

The user should make a meaningful addition, not just change a word.

## Step 5: Verify

After the edit, verify the file is non-empty and well-formed:

```bash
wc -l workflows/project_team/implementer/identity.md
head -5 workflows/project_team/implementer/identity.md
```

Check that the markdown renders sensibly (no broken formatting):

```bash
python -c "
from pathlib import Path
content = Path('workflows/project_team/implementer/identity.md').read_text()
sections = [l for l in content.split('\n') if l.startswith('#')]
print(f'Sections ({len(sections)}):')
for s in sections:
    print(f'  {s}')
"
```

## Step 6: Complete

Once verified, create the completion marker:

```bash
echo "Agent role file edited" > tutorial_extending_role_edited.txt
```

Then call `advance_phase` to proceed.

## Revert Note

> "As before, you can revert with `git checkout workflows/project_team/implementer/identity.md` if you want to undo your change — or keep it to customize your team's behavior."
