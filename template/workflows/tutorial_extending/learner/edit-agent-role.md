# Phase 3: Edit an Agent Role

In this exercise, the user edits an agent role markdown file. This teaches them how agent behavior is defined.

## Step 1: Explain the Role + Phase Architecture

> "In the project_team workflow, the **coordinator** is the main agent. It has phase-specific markdown files that change its instructions as the project progresses:
>
> | Phase | File | Purpose |
> |-------|------|---------|
> | vision | `vision.md` | Understand the project goals |
> | setup | `setup.md` | Set up repo, dependencies, structure |
> | leadership | `leadership.md` | Delegate research to Leadership agents |
> | specification | `specification.md` | Synthesize findings into a spec |
> | implementation | `implementation.md` | Delegate coding to Implementer agents |
> | testing | `testing.md` | Delegate testing to TestEngineer |
> | signoff | `signoff.md` | Final review and sign-off |
>
> The `identity.md` file is the agent's base personality -- it's always loaded. The phase file is layered on top for phase-specific instructions. Together they form the system prompt context."

## Step 2: Explain Agent Roles

> "Agent roles are markdown files in `workflows/project_team/<role>/`. Each role has:
> - **identity.md** -- the agent's base personality, responsibilities, and rules (always active)
> - **Phase files** (e.g. `vision.md`, `implementation.md`) -- phase-specific instructions
>
> When an agent is spawned with a role, identity.md shapes its core behavior. The active phase file adds context for what it should be doing right now. Editing these files changes how the agent works."

## Step 3: Show Available Roles

List the agent role files:

```bash
ls workflows/project_team/*/identity.md
```

Show the user the coordinator's identity.md -- it's the most important role and demonstrates the structure clearly. Read it aloud and explain the sections (Prime Directive, delegation rules, interaction patterns).

Then show a phase file like `coordinator/specification.md` to demonstrate how phase-specific instructions layer on top.

## Step 4: Explain the Exercise

> "You're going to add a new section to an agent role file. Pick any role -- `implementer/identity.md` is a good starting point.
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

## Step 5: Guide the Edit

Help the user pick a role file and add their new section or guideline. Suggestions:

- **implementer/identity.md** -- add a documentation or logging guideline
- **skeptic/identity.md** -- add a new category of things to challenge
- **coordinator/identity.md** -- add a new delegation rule
- **test_engineer/identity.md** -- add a test coverage requirement

The user should make a meaningful addition, not just change a word.

## Step 6: Verify

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

## Step 7: Complete

Once verified, create the completion marker:

```bash
echo "Agent role file edited" > tutorial_extending_role_edited.txt
```

Then call `advance_phase` to proceed.

## Revert Note

> "As before, you can revert with `git checkout workflows/project_team/implementer/identity.md` if you want to undo your change -- or keep it to customize your team's behavior."
