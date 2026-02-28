# User Prompt

## Original Request
I want to use this workflow to ensure the readme is good. Not so much a rewrite of the sections I have manually added. But ensure things are accurate. Also I think the SLC management could be described both better and more concisely, or with the same number of lines. The important part is to figure out the major workflows / functionality that the env management has, how to think about it, what files / folders it will create.

## Approved Vision Summary

**Goal:** Review and improve the AI_PROJECT_TEMPLATE README for accuracy and clarity, with focus on the SLC environment management section.

**Value:** A clear, accurate README helps new users understand the template quickly and use it correctly.

**Domain terms:**
- SLC (environment management system)
- Lock files, environment yml files
- `activate` script
- `envs/` folder structure

**Success looks like:**
- All technical details are accurate (paths, commands, behavior)
- SLC environment management section explains the mental model: what it does, key workflows, what files/folders get created
- Same or fewer lines for env management, but more informative
- Sections user manually wrote (claudechic fork details, ao_project_team workflow) remain largely unchanged

**Failure looks like:**
- Rewriting user's carefully crafted sections about claudechic or the workflow phases
- Inaccurate information about how SLC/env management actually works
- More verbose without being more helpful

## User Decisions During Review

**Line count constraint relaxed:** User approved the +15 lines added by the ASCII folder structure diagram. The diagram provides significant value for understanding what files/folders are created, which was explicitly requested.
