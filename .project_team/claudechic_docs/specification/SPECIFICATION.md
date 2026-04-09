# Specification: claudechic Documentation & Context Rules

**Status:** Draft
**Date:** 2026-04-08

---

## Scope

Document the 4 core claudechic systems (Hints, Checks, Rules/Guardrails, Workflows) used by AI_PROJECT_TEMPLATE. Create `.claude/rules/` context rule files so agents get automatic guidance when working with these systems. Extend existing docs minimally — no duplication.

**Primary audience:** Agents helping build/extend this framework.

---

## Deliverable 1: `.claude/rules/` Context Rule Files (TOP PRIORITY)

### Files to Create

All paths relative to repo root. Each file uses YAML frontmatter with `paths:` globs for scoping.

#### 1. `.claude/rules/hints-system.md`

**Globs:** `submodules/claudechic/claudechic/hints/**`, `hints/**`, `global/hints.yaml`

**Content outline (30-50 lines):**
- LEAF MODULE: imports only stdlib. Never import from workflows/, checks/, or guardrails/.
- 6-stage pipeline: activation → trigger → lifecycle → sort → budget → present
- Extension: implement `TriggerCondition` protocol (`check(state) -> bool`) or `HintLifecycle` protocol (`should_show()` + `record_shown()`)
- IRON RULE: never crash for a hint — wrap all trigger.check() calls in try-except
- Hint IDs in YAML: bare names only (no colons). Qualified at runtime as `namespace:id`
- State persisted to `.claude/hints_state.json` — only `HintStateStore` reads/writes this file
- Freshness: if you modify hints source, check `docs/getting-started.md` glossary still matches

#### 2. `.claude/rules/checks-system.md`

**Globs:** `submodules/claudechic/claudechic/checks/**`

**Content outline (30-40 lines):**
- LEAF MODULE: protocol.py is stdlib only. adapter.py imports only checks/protocol.
- `Check` protocol: `async def check(self) -> CheckResult`
- Built-in types: `command-output-check`, `file-exists-check`, `file-content-check`, `manual-confirm`
- Extension: call `register_check_type(name, factory)` where factory is `(params: dict) -> Check`
- `CheckDecl` is the YAML declaration; `Check` is the executable. Conversion via `_build_check()` + registry.
- Adapter seam: `check_failed_to_hint()` bridges failed checks into the hints pipeline
- Advance checks use AND semantics — sequential, short-circuit on first failure
- Freshness: if you add a check type, register it in builtins.py and update this file

#### 3. `.claude/rules/guardrails-system.md`

**Globs:** `submodules/claudechic/claudechic/guardrails/**`, `.claude/guardrails/**`

**Content outline (40-60 lines):**
- LEAF MODULE: no imports from workflows/, checks/, or hints/. hooks.py uses TYPE_CHECKING only.
- Terminology: "guardrail rules" = always-active safety rules in `.claude/guardrails/rules.yaml`. "Runtime rules" = rules in `global/rules.yaml` or workflow YAML, active during workflows.
- Three enforcement levels: `deny` (hard block), `warn` (ack required), `log` (silent audit)
- Two-step hook pipeline: injections first (modify tool_input), then enforcement rules
- Rule scoping: `roles`/`exclude_roles`, `phases`/`exclude_phases` for fine-grained targeting
- Override tokens: one-time authorization via `OverrideTokenStore` — warn tokens cannot satisfy deny rules
- Hit logging: append-only JSONL audit trail via `HitLogger`
- Template-side guardrails: edit `.claude/guardrails/rules.yaml`, then run `generate_hooks.py`
- Freshness: if you modify guardrails source, verify hooks.py callback signatures still match

#### 4. `.claude/rules/workflows-system.md`

**Globs:** `submodules/claudechic/claudechic/workflows/**`, `workflows/**/*.yaml`, `workflows/**/identity.md`, `workflows/**/*.md`

**Content outline (40-60 lines):**
- ORCHESTRATION LAYER: imports from checks/, hints/, guardrails/. This is the integration point.
- `ManifestLoader` is the universal parser — discovers `global/*.yaml` + `workflows/*/*.yaml`, dispatches sections to registered `ManifestSection[T]` parsers
- Extension: implement `ManifestSection[T]` protocol (section_key + parse method), register with `loader.register()`
- `WorkflowEngine` manages in-memory phase state, executes advance checks, persists via callback
- Phases are bridge types: contain `advance_checks: list[CheckDecl]` and `hints: list[HintDecl]`
- Phase transitions: AND semantics on advance checks. Failed check → hint via adapter.
- Agent prompt assembly: `agent_folders.py` reads `identity.md` + `{phase}.md` from `workflows/{workflow}/{role}/`
- PostCompact hook: re-injects phase context after `/compact`
- Chicsessions: named multi-agent snapshots at `.chicsessions/{name}.json`. Store `workflow_state` as opaque dict. `ChicsessionManager` handles atomic save/load.
- Namespace qualification: all IDs are `namespace:bare_id`. Bare names in YAML, qualified at runtime.
- Freshness: if you modify workflow engine or loader, check that `register_default_parsers()` still registers all parser types

#### 5. `.claude/rules/manifest-yaml.md`

**Globs:** `global/*.yaml`, `global/**/*.yaml`, `workflows/**/*.yaml`

**Content outline (30-50 lines):**
- Manifest files are the user-facing configuration surface for all claudechic systems
- Valid top-level sections: `rules`, `injections`, `checks`, `hints`, `phases`, `workflow_id`, `main_role`
- Global manifests (`global/*.yaml`): namespace is always `"global"`. Can also be bare lists where section key is inferred from filename stem.
- Workflow manifests (`workflows/{name}/{name}.yaml`): namespace is `workflow_id` from YAML or directory name
- ID rules: bare names only in YAML (no colons). Parser qualifies as `namespace:id` automatically.
- Phase-nested items: `advance_checks` and `hints` can be nested inside `phases` entries
- Error handling: fail-open per item (bad entries skipped with warning), fail-closed on discovery (unreadable dirs → block everything)
- Duplicate ID detection: cross-manifest validation catches duplicates after namespace prefixing
- Phase reference validation: rules/injections referencing unknown phases produce warnings

#### 6. `.claude/rules/claudechic-overview.md`

**Globs:** `submodules/claudechic/**`

**Content outline (20-30 lines):**
- claudechic is the TUI wrapper + MCP server + workflow engine for Claude Code
- 4 core systems: Hints (advisory toasts), Checks (verification protocol), Guardrails/Rules (enforcement), Workflows (orchestration + phases + chicsessions)
- Dependency direction: Workflows → Phases/Rules/Hints → Checks. Never import upward.
- Seam discipline: systems communicate through frozen dataclasses and Protocol ABCs
- Key seam objects: `CheckResult`, `CheckDecl`, `HintDecl`, `HintSpec`, `Rule`, `Injection`
- All parsers registered via `register_default_parsers()` in `workflows/__init__.py`
- When modifying any system, respect its declared import boundary (check module docstrings)

---

## Deliverable 2: Documentation Updates

### Files to Modify

#### `docs/getting-started.md`

**Changes:**
- Add a "Core Systems" section (after "Understanding the Rule Systems") with brief descriptions of Hints, Checks, Workflows (including phases and chicsessions). Keep to ~30 lines — point to source for details.
- Update Glossary table: add entries for "advance check", "manifest" (YAML), "trigger condition", "chicsession", "ManifestLoader". Disambiguate "rule" entries per terminology conventions below.
- No other changes. The existing Rule Systems section is good.

#### `README.md`

**Changes:**
- No changes. README is an overview/quick-start — adding system details would bloat it.

### Files NOT Created

- No `docs/claudechic/` directory with per-system docs. The `.claude/rules/` files serve as the agent-facing documentation. The getting-started.md additions serve as human-facing documentation. Creating separate per-system docs would duplicate content and create staleness risk.
- No `docs/claudechic-architecture.md`. The dependency diamond and composition model are captured in `.claude/rules/claudechic-overview.md` and the getting-started.md "Core Systems" section.

---

## Terminology Conventions

All deliverables must use these terms consistently:

| Term | Use for | NOT |
|------|---------|-----|
| **guardrail rule** | Rules in `.claude/guardrails/rules.yaml` (always-active safety) | "guardrail", "safety rule" |
| **runtime rule** | Rules in `global/rules.yaml` or workflow YAML (active during workflows) | "global rule", "workflow rule" (too ambiguous) |
| **context rule file** | `.claude/rules/*.md` files (Claude Code's native rules system) | "rules file" (ambiguous with guardrail rules) |
| **advance check** | Phase-gating condition in workflow YAML | "gate", "precondition" |
| **Check** (capitalized) | The async protocol in `checks/protocol.py` | "check" (lowercase, for informal use only) |
| **trigger condition** | Hints system: `TriggerCondition` protocol | "trigger" (alone — ambiguous with rule triggers) |
| **trigger event** | Rules system: `PreToolUse/Bash` style hook triggers | "trigger" (alone) |
| **manifest** | Any YAML file parsed by ManifestLoader (`global/*.yaml`, `workflows/*/*.yaml`) | "config file", "YAML file" |
| **chicsession** | Named multi-agent session snapshot (`.chicsessions/*.json`) | "session" (ambiguous with Claude Code session) |
| **namespace** | Qualifier prefix for IDs (`global:`, `project-team:`) | "scope", "prefix" |

---

## Freshness Enforcement

### Self-enforcing pattern
Each `.claude/rules/` file includes a freshness reminder at the bottom:

```markdown
**Freshness:** If you modify source files matched by this rule, verify this
document still accurately describes the system behavior. Update if needed.
```

### No automated guardrail rule
A guardrail rule that warns on claudechic source changes would fire too often and create noise. The self-enforcing reminder in context rule files is sufficient — agents see it exactly when they're working on the relevant code.

---

## Implementation Order

1. Create `.claude/rules/` directory
2. Write all 6 context rule files (Deliverable 1)
3. Update `docs/getting-started.md` (Deliverable 2)
4. Review: verify glob scoping works, terminology is consistent, no duplication with existing docs

---

## Acceptance Criteria

1. **6 context rule files exist** at `.claude/rules/{name}.md` with correct YAML frontmatter globs
2. **Each context rule file is 20-60 lines** — imperative voice, single topic, agent-actionable
3. **Terminology is consistent** across all files per the conventions table above
4. **`docs/getting-started.md`** has a Core Systems section and updated glossary
5. **No duplication**: context rule files describe behavior/extension points, not internals. Getting-started.md is not duplicated.
6. **Freshness reminders** appear in every context rule file
7. **Import boundaries** are documented in each system-specific rule file
8. **README.md is unchanged**
9. **No new docs/ subdirectories** — lean approach, rules files ARE the agent docs
