# User Request

I want to make this repo more composable and easier to start a project with. We have python env management, claudechic, project-team and the guardrail system. I want to have users have an onboarding experience maybe web based / claude conversation based to decide how to make their repo. We should be able to let them add an existing code base as well.

Additional: Port the pattern miner feature from DECODE-PRISM (scripts/mine_patterns.py) — 3-tier JSONL session scanner that extracts user corrections and feeds PATTERNS.md.

Additional: The team needs to analyze the seams between these systems to create the right type of plugin system.

Additional: Survey the landscape — we're not the first to try this. Research what exists, learn from prior art, and recommend additional plugins worth building or integrating.

## Vision Summary

**Goal:** Create a composable, plugin-based AI_PROJECT_TEMPLATE with an interactive onboarding experience that lets users pick features, integrate existing codebases, and easily extend with future plugins. Also: survey the landscape — research what exists, learn from prior art, and recommend additional plugins worth building or integrating.

**Value:** Lowers the barrier to entry — users get only what they need. The plugin architecture ensures current features are decoupled at their seams and future features drop in cleanly. The landscape survey prevents us from reinventing the wheel and surfaces plugin ideas we haven't thought of.

**Core features to become plugins:**
1. **Python env management** — conda/Miniforge bootstrap, install_env.py, lock_env.py, lockfiles, activate script
2. **Claudechic** — TUI wrapper for Claude Code, submodule at submodules/claudechic, its own conda env
3. **Project Team** — multi-agent workflow (AI_agents/project_team/, COORDINATOR.md, skill at .claude/commands/)
4. **Guardrails** — composable role x action permission system (generate_hooks.py, role_guard.py, rules.yaml)
5. **Pattern Miner** — 3-tier JSONL session scanner from DECODE-PRISM (mine_patterns.py: regex -> semantic -> clustering -> PATTERNS.md)
6. **TBD from research** — team should recommend additional plugins discovered from prior art

**Key design challenges:**
- Analyze the seams between existing systems — where they touch, what they assume about each other, what contracts they share
- Design a plugin interface that's lightweight but real
- Landscape survey — what similar tools/frameworks exist? What plugin ideas can we borrow or integrate?

**Onboarding:** Interactive first-run experience (web-based or Claude conversation) where users select plugins and optionally point to an existing codebase to wrap.

**Reference material:**
- Pattern miner source: /groups/spruston/home/moharb/DECODE-PRISM/scripts/mine_patterns.py
- PATTERNS.md example: /groups/spruston/home/moharb/DECODE-PRISM/PATTERNS.md
