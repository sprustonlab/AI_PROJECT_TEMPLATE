# User Alignment Check — Specification Review

## Original Request Summary

User wants an architecture specification for a Workflow Guidance System in claudechic. See initial alignment check (below) for full requirement extraction.

---

## Specification Review

### Alignment Status: ✅ ALIGNED

The specification faithfully implements the user's design. All major design decisions from `USER_PROMPT.md` are preserved. Two minor issues flagged below.

---

### Check 1: All 7 User-Requested Examples Present?

User quote: "Include: full `project_team.yaml` manifest, `global.yaml` with setup checks, phase transition walkthrough, phase-scoped rule evaluation, hook closure code, manifest discovery, phase reference validation."

| # | Required Example | Present? | Section |
|---|---|---|---|
| 1 | Full `project_team.yaml` manifest | ✅ | §14 Example 1 |
| 2 | `global.yaml` with setup checks | ✅ | §14 Example 2 |
| 3 | Phase transition walkthrough | ✅ | §14 Example 3 |
| 4 | Phase-scoped rule evaluation | ✅ | §14 Example 4 |
| 5 | Hook closure code | ✅ | §14 Example 5 |
| 6 | Manifest discovery | ✅ | §14 Example 6 |
| 7 | Phase reference validation | ✅ | §14 Example 7 |

**Result: ✅ All 7 examples present.**

---

### Check 2: Existing Code Mapping Clear?

User quote (failure criteria): "fails to identify which existing claudechic code needs to change and how (refactors, new modules, modified interfaces)."

§11 Refactoring Map includes:
- ✅ **guardrails/rules.py** — detailed table of what changes per function (Rule dataclass modified, load_rules deleted, should_skip_for_phase simplified, read_phase_state moved)
- ✅ **app.py** — extraction of _guardrail_hooks, _merged_hooks modification, engine init, PostCompact addition
- ✅ **mcp.py** — agent folder prompt assembly added to spawn_agent
- ✅ **New files list** — 11 CREATE, 4 MODIFY, 3 UNCHANGED with rationale
- ✅ **Import dependency graph** (§12) — verifies no circular imports
- ✅ **Rule dataclass redesign** — before/after with field-level changes
- ✅ **should_skip_for_phase signature change** — old vs. new

**Result: ✅ Existing code mapping is comprehensive.**

---

### Check 3: All User Design Decisions Preserved?

| User Design Decision | Quote from USER_PROMPT.md | Preserved? |
|---|---|---|
| Unified loader with ManifestSection[T] | "A unified loader reads all manifests and distributes each section to a typed parser" | ✅ §5 |
| Two loader modes | "The loader has two modes: full load (startup, phase transitions) and rules-only load (every tool call)" | ✅ §5 (hot path vs. full load) |
| Namespace prefixing | "Every ID is namespace:name at runtime. Global = _global:pip_block" | ✅ §5 Namespace Prefixing |
| No mtime caching | "No mtime caching — NFS is unreliable on HPC clusters" | ✅ §5 NFS Performance Strategy |
| Atomic state writes | "state.json written atomically (temp file + rename)" | ✅ §7 Atomic State Persistence |
| Fail closed / fail open | "workflows/ unreadable → fail closed... Individual manifest malformed → fail open" | ✅ §5 Error Strategy Matrix |
| 4 check types | "CommandOutputCheck, FileExistsCheck, FileContentCheck, ManualConfirm" | ✅ §6 |
| ManualConfirm via callback | "The engine receives a confirmation callback at construction, not an app reference" | ✅ §6 ManualConfirm ↔ TUI Seam |
| CheckFailed → hints adapter | "A CheckFailed adapter bridges checks to the existing hints pipeline" | ✅ §6 CheckFailed → Hints Adapter |
| Pull-based content delivery | "Content delivery is pull-based. The engine does not inject content mid-session" | ✅ §2 Content Delivery |
| PostCompact recovery | "A PostCompact SDK hook re-injects phase context after /compact" | ✅ §7 PostCompact Hook |
| Advance checks AND semantics | "advance_checks in manifests have AND semantics with short-circuit on first failure" | ✅ §7 Phase Transition Flow |
| `warn` in schema but not used | "Don't use warn on any rules yet — it has an infinite-loop risk" | ✅ §8 Enforcement Levels (constraint box) |
| Qualified phase IDs | "Always use qualified phase IDs in phase_block/phase_allow" | ✅ §2 Qualified Phase ID, §5 |
| Agent folder = role type | "The folder name IS the agent's role type" | ✅ §9 Agent Folders |
| Agent prompt = identity + phase | "Agent prompt = identity + current phase file" | ✅ §9 Prompt Assembly |
| Hook closure per agent | "one per agent with the role type captured at creation time" | ✅ §8 Hook Closure Creation |
| Setup checks `when` clause | "`when` clause supports copier-answer conditions" | ✅ §6, §2 |
| Startup validation | "Startup validation catches duplicate IDs, invalid regexes, unknown phase references" | ✅ §5 Cross-Manifest Validation |
| Scope exclusions (4 items) | "CompoundCheck, content focus guards, multi-workflow, ShowUntilPhaseComplete" | ✅ §14 Scope Boundaries |

**Result: ✅ All user design decisions preserved.**

---

### Issues Found

#### ⚠️ Minor Issue 1: `exclude_if_matches` not in USER_PROMPT.md

The spec introduces `exclude_pattern` / `exclude_if_matches` on rules (§2 Terminology, Rule dataclass §11). This is NOT in `USER_PROMPT.md`.

**Assessment:** This is a small scope addition — a convenience feature for rule authoring. It's low-risk and doesn't conflict with any user requirement. However, per protocol:

> ℹ️ USER ALIGNMENT: This adds `exclude_if_matches` (exclude pattern on rules) which wasn't in the original request. Recommend: Accept as minor implementation convenience, or defer to v2.

**Recommendation:** Accept — it's a natural field on a regex-matching rule and adds no complexity to the architecture.

#### ❓ Minor Issue 2: Hint scoping model adds "workflow-wide" level

§5 Hint Scoping Model shows three levels: Global, Workflow-wide, Phase-scoped. USER_PROMPT.md says: "Phase hints are declared under phase entries in manifests — scoping is structural. Global hints go in global.yaml."

The spec adds a middle level — `workflow.yaml → hints:` (top-level, not under a phase). This isn't explicitly in USER_PROMPT.md but is a natural consequence of the manifest structure (if you put hints at the top level of a workflow manifest, they're workflow-scoped).

**Assessment:** This resolves one of the ambiguities I flagged in the initial alignment check. The three-level model is coherent and doesn't contradict the user's design. But the user should be aware of it.

> ❓ USER ALIGNMENT: User described hints as phase-scoped or global. Spec adds workflow-wide hints (top-level in workflow manifest). This is a reasonable architectural extension — flag for user awareness.

---

## Summary

| Criteria | Status |
|---|---|
| 7 required examples | ✅ All present |
| Existing code mapping | ✅ Comprehensive (§11, §12) |
| User design decisions | ✅ All 20+ decisions preserved |
| Scope exclusions | ✅ All 4 respected |
| Domain terms | ✅ All correctly used |
| Minor additions | ⚠️ `exclude_if_matches` (accept) |
| Minor extensions | ❓ Workflow-wide hints (flag for awareness) |

**Overall: The specification is faithful to the user's intent. Proceed.**

---

---

## Audit Review: Current System vs. Spec (User Alignment Perspective)

**Context:** The user expressed concern: "this is not making me feel like the spec is going to preserve all the current systems we are combining." The Researcher produced `current_vs_spec_audit.md` documenting 25 features in the current file-based guardrails system. My job: which of these gaps violate the user's explicit intent?

### What the User Actually Said

The user's `USER_PROMPT.md` has a specific "What exists in the codebase" section:

> "Build on these in `submodules/claudechic/claudechic/`:"
> - `guardrails/rules.py` — rule loading and matching
> - `guardrails/hits.py` — hit logging
> - `app.py` — hook closures and `SelectionPrompt` confirmation
> - `hints/` — trigger conditions, hint lifecycle, pipeline, project state

**Critical observation:** The user says "Build on these" and lists **claudechic** code (the closure-based system). The user does NOT list `.claude/guardrails/generate_hooks.py` or the file-based hook system. The spec's §11 Refactoring Map addresses every file the user listed:
- ✅ `guardrails/rules.py` — Rule dataclass modified, matching functions preserved
- ✅ `guardrails/hits.py` — user listed it but the spec doesn't address it (see below)
- ✅ `app.py` — hook extraction, merged hooks, engine init
- ✅ `hints/` — absorbed from template-side into claudechic

### Classification of Audit Gaps

#### ⚠️ USER ALIGNMENT ISSUE: `guardrails/hits.py` — User explicitly listed, spec ignores

The user said "Build on these" and listed `guardrails/hits.py — hit logging`. The spec's §11 Refactoring Map has no entry for `hits.py`. The closure code has no hit logging. This is the ONE file from the user's explicit list that the spec fails to address.

Quote from USER_PROMPT.md: "`guardrails/hits.py` — hit logging"

**This MUST be addressed.** The spec should either:
1. Preserve hit logging in the closure pipeline (add `log_hit()` calls), OR
2. Explicitly document that hits.py is superseded and why

#### ❓ NEEDS CLARIFICATION: Co-existence of file-based and closure-based systems

The audit raises a critical question: does the file-based system (`.claude/guardrails/`) co-exist or get replaced? The user's prompt doesn't say "replace the file-based system." It says "Build on" the claudechic closure-based system. But it also doesn't say "keep the file-based system."

The spec should explicitly state the relationship. This is an architectural decision the user should approve.

#### ✅ NOT USER ALIGNMENT ISSUES (Audit items about the file-based system)

The following audit gaps are about `.claude/guardrails/generate_hooks.py` and the file-based hook system — which the user did NOT list in "Build on these":

| Audit Item | Why NOT a User Alignment Issue |
|---|---|
| 1.1 Code-generation pipeline | User didn't list `generate_hooks.py`. Spec builds on closures, not file-based hooks. |
| 1.2 `inject` enforcement | User's enforcement table has 4 levels: `deny`, `user_confirm`, `warn`, `log`. No `inject`. |
| 1.7 `detect.type` enumeration | User's examples use `detect: { pattern, field }` only. No `regex_miss`, `always`, `spawn_type_defined`. |
| 1.8 `exclude_contexts` | Not in user prompt. |
| 1.9 `detect.flags` | Not in user prompt. |
| 1.11 `detect.conditions` | Not in user prompt. |
| 1.13 Session markers / team mode | Not in user prompt. The spec's `block_roles`/`allow_roles` matches what the user specified. |
| 1.15 `catalog_version` | Not in user prompt. |
| 1.16 `source` field | Not in user prompt. |
| 1.18 `enabled` field | Not in user prompt. |
| 1.19 Message files | Not in user prompt. Messages are inline in examples. |
| 1.20 Pattern lists | User examples show single patterns. |
| 1.22 `rules.d/` | Not in user prompt. |
| 1.24 `settings.json` auto-update | Not applicable — SDK hooks don't need settings.json. |
| 1.25 `GUARDRAILS_DIR` env var | User explicitly said "No env var overrides for state paths." |

These features exist in the file-based system but the user's prompt designs the NEW system around the closure-based approach. The user explicitly chose the 4-level enforcement model (`deny`/`user_confirm`/`warn`/`log`) — no `inject`. The user explicitly chose `detect: { pattern, field }` — no `detect.type` enumeration.

#### ❓ BORDERLINE: Ack mechanism and warn implementation

The audit flags the ack mechanism (items 1.3, 1.4, 1.5) as critical. However:

The user said: "Don't use `warn` on any rules yet — it has an infinite-loop risk (agent retries after acknowledging)."

This means:
1. The user KNOWS about the ack/retry problem
2. The user deliberately defers `warn` usage
3. The spec correctly keeps `warn` in the schema but doesn't implement the ack bypass

The ack mechanism is the SOLUTION to the infinite-loop problem. When the spec eventually enables `warn`, it will need ack. But the user explicitly said "not yet." So the spec's omission of ack implementation is ALIGNED with the user's deferral.

#### ❓ BORDERLINE: Multi-match priority

The audit flags that the closure uses early-return vs. collect-all-then-dispatch. The user's prompt doesn't specify multi-match behavior. The user's examples show single rules firing. This is an implementation detail — not a user alignment issue. But it's worth noting in the spec as a design decision.

### Summary

| Category | Count | Action |
|---|---|---|
| ⚠️ User alignment issue | 1 | `hits.py` — user explicitly listed, spec ignores |
| ❓ Needs clarification | 1 | Co-existence of file-based and closure-based systems |
| ❓ Borderline (acceptable) | 2 | Ack mechanism (deferred by user), multi-match priority |
| ✅ Not user alignment issues | 15+ | File-based system features not in user's "Build on" list |

### Recommendation

1. **MUST FIX:** Add `hits.py` to the spec — either preserve hit logging in the closure pipeline or explicitly document its fate. The user said "Build on" hits.py.
2. **SHOULD CLARIFY:** State whether file-based hooks co-exist or are replaced. This is an architectural decision the user should see.
3. **NO ACTION NEEDED** on the 15+ file-based system features. The user designed the new system around closures with a specific manifest format. Those features belong to the old system.

---

## Initial Alignment Check (Phase Start)

*(Preserved from earlier analysis for reference)*

### Core Requirements Extracted
1. Unified manifest loader with ManifestSection[T]
2. Workflow engine (phases, gates, state)
3. Check protocol (4 types, async, engine-run)
4. Agent folder structure
5. 2×2 guidance framing
6. SDK hooks and enforcement (4 levels)
7. Phase-scoped guardrail evaluation
8. Namespace convention
9. /compact recovery
10. global.yaml with setup checks
11. Directory structure under workflows/
12. Failure modes (fail closed / fail open)
