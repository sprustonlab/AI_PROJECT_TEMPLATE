# Project Status

**EVERY TURN: Re-read AI_agents/project_team/COORDINATOR.md**

## Current Phase
Phase 4: Implementation — PoC validated, ready for full build

## Vision (from Phase 0)
**Goal:** Build general-purpose infrastructure primitives (Check + Phase) that tutorials, project-team workflows, and future systems consume.

**Principle:** v1 is infrastructure. v2 is tutorial.

**Key decisions (user-driven):**
- "v1 is infrastructure, v2 is tutorial"
- Guardrails move from generated file hooks to SDK in-process hooks in claudechic
- `user_confirm` enforcement level: proven via PoC (SelectionPrompt in TUI)
- claudechic is required — no vanilla Claude Code fallback
- "Workflow" is the umbrella term (tutorials = teams = workflows)
- 2x2 framing: advisory/enforced x positive/negative

## Architecture: SDK Hooks Replace File Hooks
**PoC VALIDATED** — commit pending

| What | Status |
|------|--------|
| SDK PreToolUse hook evaluates rules.yaml | ✅ Proven (2.4ms avg) |
| deny enforcement blocks commands | ✅ Proven (R02 pip install) |
| user_confirm shows TUI prompt, user decides | ✅ Proven (R99 test) |
| No performance regression on tool calls | ✅ Proven (<5ms) |

**Deletes (~2860 lines):**
- generate_hooks.py (2155 lines)
- bash_guard.py (173), write_guard.py (185)
- role_guard.py (~350)
- settings.json hook entries
- Session marker system, env vars

**Adds (~210 lines):**
- guardrails/rules.py (~100) — rule loader + matching
- guardrails/hits.py (~30) — hit logging
- app.py changes (~50) — _guardrail_hooks(), _show_guardrail_confirm()
- ConfirmPrompt widget (~30)

## What's Next
1. Remove R99 test rule, commit PoC state
2. Update SPECIFICATION.md with SDK hook architecture
3. Begin full implementation:
   - Clean up PoC code (remove debug logging)
   - Add hits.jsonl logging
   - Add phase_block/phase_allow evaluation
   - Add startup validation for rules.yaml
   - Delete generate_hooks.py and file hooks
   - Wire up for all agents (per-agent closures with role)

## Specification
Definitive spec: `.ao_project_team/tutorial_system/specification/SPECIFICATION.md`
(Needs update to reflect SDK hook architecture decision)

## Completed
- Phase 0: Vision confirmed
- Phase 1: Setup complete
- Phase 3: Specification (definitive spec written, 4 review rounds completed)
- SDK Hook PoC: validated (deny + user_confirm + timing)
