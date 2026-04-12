# CLAUDE.md Specification — Generated Projects (template/CLAUDE.md.jinja)

## Overview
Write a Jinja2-templated CLAUDE.md that ships with every generated project, giving agents working IN that project the context they need.

## Key Difference from Developer CLAUDE.md
The developer CLAUDE.md (root of AI_PROJECT_TEMPLATE) is for agents working on the template source. THIS file is for agents working in a generated project — they're building their own code, using claudechic as a tool. No submodules, no template/ directory, no Copier development.

## Design Principles
- **~80-120 lines** (conditional sections expand/contract based on copier variables)
- **Jinja2 templated** — file is `template/CLAUDE.md.jinja`
- **Imperative tone** — same as developer CLAUDE.md
- **Lead with bootstrap command** — `source activate` is the critical first step
- **Conditional sections** — only show what's relevant to the user's choices

## Copier Variables Available
- `project_name` — project identity
- `quick_start` — controls which content ships (everything/defaults/empty/custom)
- `claudechic_mode` — standard (git URL) vs developer (editable submodule)
- `use_cluster` — whether cluster MCP tools are available
- `target_platform` — OS-specific instructions
- `init_git` — whether to initialize git repo
- `use_existing_codebase` — path to integrate existing project
- `example_rules` — whether guardrail rules ship
- `example_agent_roles` — whether specialist role directories ship (7 conditional roles)
- `example_workflows` — whether tutorial workflows ship
- `example_hints` — whether hints ship
- `example_patterns` — whether pattern miner ships

## Structure

### 1. Identity (~3 lines)
```
# {{ project_name }}
```
A Claude Code project managed by claudechic. Agents are already running inside the environment — no activation or launch commands needed.

### 2. Project Structure (~15 lines)
Key directories with purpose:
- `repos/` — Your codebases go here. Auto-added to PYTHONPATH.
- `workflows/` — Phase-gated workflow definitions (project-team, tutorials, setup wizards)
- `global/` — Always-active guardrail rules (rules.yaml) and contextual hints (hints.yaml)
- `mcp_tools/` — MCP tool scripts. Drop a .py file here and claudechic auto-discovers it.
- `commands/` — CLI commands
- `envs/` — Environment configurations
- `scripts/` — Utility scripts

### 3. Workflows (~10 lines)
Available workflows (activate with `/<workflow-id>` in claudechic):
- `/project-team` — Multi-agent development workflow
- `/tutorial` — Learn how workflows, checks, and hints work
- `/workflow list` — See all available workflows

### 4. Workflows (~15 lines)
- project-team: vision → setup → leadership → specification → implementation → testing → signoff
- The Coordinator agent delegates work — it does NOT write code itself
- Phase transitions are gated by advance checks (all must pass)
- Workflow rules can be phase-scoped (e.g., certain operations blocked until testing phase)

Available workflows:
- `project-team` — Full multi-agent development
- `tutorial` — Learn the workflow guidance system
{% if quick_start in ['everything', 'custom'] and example_workflows %}
- `tutorial-extending` — Learn to extend workflows
- `tutorial-toy-project` — Build a project end-to-end
{% endif %}
- `git-setup`, `codebase-setup`, `cluster-setup` — Onboarding wizards

### 5. repos/ Directory (~5 lines)
- Clone or symlink your codebases into `repos/`
- `activate` adds all `repos/*/` to PYTHONPATH automatically
- Your code is importable from anywhere in the project after activation

### 6. Guardrails (conditional) (~10 lines)
{% if example_rules or quick_start in ['everything', 'defaults'] %}
Active guardrail rules in `global/rules.yaml`:
- `rm -rf /` patterns → DENIED (hard block)
- `sudo` commands → WARNED (needs acknowledgment)
- `git` operations → LOGGED (audit trail)
- Bare `pytest` → DENIED (must target specific file or save timestamped results)
Override: agent calls `request_override()` for deny rules, `acknowledge_warning()` for warn rules.
{% endif %}

### 7. Cluster Tools (conditional) (~5 lines)
{% if use_cluster %}
MCP tools for HPC job management (LSF/SLURM) in `mcp_tools/`:
- Backend and connection details are in `mcp_tools/cluster.yaml` (populated by setup workflow, NOT at template time)
- Run `/cluster-setup` workflow to configure — it discovers your scheduler, SSH target, and path mapping
- `cluster.yaml` is the runtime source of truth for cluster config
{% endif %}

### 8. Extension Points (~15 lines)
- **Add MCP tools**: Create `mcp_tools/my_tool.py` — auto-discovered by claudechic
- **Add workflows**: Create `workflows/<name>/<name>.yaml` + role directories
- **Add guardrail rules**: Edit `global/rules.yaml` (deny/warn/log enforcement)
- **Add hints**: Edit `global/hints.yaml` (contextual toast notifications)
- **Add CLI commands**: Create executable in `commands/` — available after `source activate`
- **Add repos**: Clone into `repos/` — auto-added to PYTHONPATH

### 9. claudechic Mode (conditional) (~10 lines)
{% if claudechic_mode == 'developer' %}
**Developer mode** — claudechic source is in `submodules/claudechic/` (editable install).
- You CAN and SHOULD edit claudechic source here when extending the engine
- `.claude/rules/*.md` files document claudechic internals (auto-loaded by path)
- `submodules/claudechic/` is a separate git repo — changes need own commits + parent pin update
- Changes there don't appear in parent `git status`
- Ruff and pyright exclude `submodules/` — lint/typecheck inside the submodule separately
{% else %}
**Standard mode** — claudechic is installed via git URL (not editable).
- Do NOT try to edit claudechic internals — there's no local source to modify
- To customize behavior, use extension points: guardrail rules, hints, workflows, MCP tools
{% endif %}

### 10. Conventions (~5 lines)
- Use `pixi run <cmd>`, not pip/venv/conda
- `source activate` (or `. .\activate.ps1` on Windows) before any work session
- Workflows are activated with `/<workflow-id>` in claudechic (NOT Claude Code slash commands)
- claudechic is always lowercase

## Explicitly Excluded
- Detailed workflow/phase/hint system internals (agents learn via /tutorial)
- Copier template development (this is a generated project, not the template)
- claudechic source code details (handled by .claude/rules/ in developer mode)

## Success Criteria
An agent in a generated project should, after reading CLAUDE.md:
1. Know the environment is already active — no setup commands needed
2. Know to put code in `repos/`
3. Launch claudechic and start a workflow
4. Understand guardrail rules won't let them run bare pytest
5. Know how to extend the project (add tools, workflows, hints)
6. Know whether they can edit claudechic (developer mode) or should use extension points (standard mode)
7. Use pixi, not pip
