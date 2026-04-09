# Project: docs_audit

## Vision
Audit and fix documentation drift. Primary target: README.md. Secondary: minor fixes in project_team/README.md. New feature: git_setup slash command.

## User Decisions (Final)
- **README audience**: Template repo browsers
- **`.claude/rules/`**: Document with "developer mode only" caveat
- **Phase count (4 vs 7)**: Intentional — 4 are conceptual phases, NO FIX needed
- **Config table**: Not fictional — simplified summary. Needs `quick_start`/`project_name` added, misleading names fixed
- **`git_setup` slash command**: IN SCOPE — create `.claude/commands/git_setup.md`

## Prioritized Issues (Corrected)

| # | Issue | Location | Fix Size |
|---|-------|----------|----------|
| P0 | `/project-team` listed as command/skill — it's a workflow | README.md | Tiny |
| P1 | Config table missing `quick_start`, `project_name`; misleading row names | README.md | Moderate |
| P1 | `mcp_tools` link points to `template/` path | README.md | Tiny |
| P1 | "Claude Code skills" → "slash commands" | README.md | Tiny |
| P1 | `.claude/rules/` not in README tree (add with dev-mode caveat) | README.md | Small |
| P2 | Phantom `no_force_push` rule in README | README.md | Tiny |
| P2 | `git_setup` role missing from PT/README roster | PT/README (both locations) |Tiny |
| P2 | Tutorial count inconsistency | README.md | Small |
| P2 | Create `git_setup` slash command | .claude/commands/git_setup.md | New feature |
| P3 | Cross-reference links between docs | All 3 | Small |

## Principles
- Single source of truth per concept
- Progressive disclosure: README → getting-started → workflow READMEs
- Don't turn README into a second getting-started.md
- Fix both locations for project_team/README.md (root + template/)

## Phase: Leadership → advancing to Specification
## Status: READY TO ADVANCE
