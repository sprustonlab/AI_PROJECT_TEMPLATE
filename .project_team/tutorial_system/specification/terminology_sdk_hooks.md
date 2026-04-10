# Terminology Review: SDK Hook Architecture Update (Re-review)

**Reviewer:** TerminologyGuardian
**Date:** 2026-04-05
**Spec reviewed:** `specification/SPECIFICATION.md` (dated 2026-04-05, "updated for SDK hook architecture — PoC validated")
**Context:** Re-review after Composability updated the spec to reflect SDK hook architecture.

---

## Previously Identified Issues — Resolution Status

### P0: `generate_hooks.py` Ghost References → ✅ RESOLVED

All 9+ stale references have been cleaned up. The remaining 6 mentions of `generate_hooks.py` are **correctly in deletion/replacement context**:
- §3.3 line 599: "no `generate_hooks.py`" (describing what doesn't exist)
- §3.3 line 605: Deleted component table (−2155 lines)
- §6 line 974: "What was removed from file structure"
- §8.1 line 1101: Deleted code line count (−2860)
- §8.3 line 1122: "Delete `generate_hooks.py`" (implementation step)
- §10.1 line 1166: Resolved decision — "No file hooks, no `generate_hooks.py`"

**Verdict:** Clean. Every reference now correctly describes deletion.

### P0: §6 File Structure → ✅ RESOLVED

File structure now shows:
- `submodules/claudechic/claudechic/guardrails/rules.py` (existing, PoC)
- `submodules/claudechic/claudechic/guardrails/hits.py` (new)
- `submodules/claudechic/claudechic/app.py` (existing, PoC)
- "What was removed" section lists all deleted files
- `phase_guard.py` correctly listed as removed (merged into `should_skip_for_phase()`)

### P0: §8.3 Implementation Order → ✅ RESOLVED

Rewritten for SDK hooks. Step 1 is now "Clean up PoC + delete file hooks" (not "extend generate_hooks.py"). Step 2 correctly says "4 built-in types" (was "3"). All steps are SDK-hook-aware.

### P1: Line Counts → ✅ RESOLVED

§8.1 now shows:
- SDK hook cleanup: ~0 net (PoC exists)
- Deleted code: −2860
- New infrastructure: ~290 lines
- Net change: ~−2070 (massive simplification)

### P1: `ConfirmPrompt` vs `SelectionPrompt` → ⚠️ PARTIALLY RESOLVED (see below)

### P1: "3 built-in types" → "4 built-in types" → ✅ RESOLVED

§8.3 step 2 now says "4 built-in types". §10.2 says "hardcoded 4 types". Consistent with §2.1's table of 4 checks.

### P2: Terminology Table → ✅ RESOLVED

§11 now includes:
- `ManualConfirm` — with v1/v2 distinction
- `SDK hook` — defined with key characteristics
- `Fail-closed` / `Fail-open` — defined
- `Workflow` — promoted to top of table as umbrella term

### P2: `hits.jsonl` → ✅ RESOLVED

Mentioned in §3.3 "What this adds" table (line 617).

---

## New Issues Found in Updated Spec

### Issue 1: `ConfirmPrompt` vs `SelectionPrompt` — Name Conflict (P1)

The spec uses **two different names** for what appears to be the same TUI widget:

| Location | Term used |
|---|---|
| §3.3 "What this adds" table (line 619) | **`ConfirmPrompt`** widget |
| §3.3 code example (line 629) | `SelectionPrompt` |
| §3.3 code example (line 704) | `SelectionPrompt(title, options)` |
| §3.3 enforcement table (line 734) | `SelectionPrompt` |
| §10.1 resolved (line 1167) | `SelectionPrompt` |
| §11 terminology (line 1209) | `SelectionPrompt` |
| Appendix A.8 (line 1284) | `SelectionPrompt` |

→ **`ConfirmPrompt`** appears once (in the "adds" table); **`SelectionPrompt`** appears 6+ times (in code, tables, terminology).

**Question for Composability:** Are these the same widget? If so, pick one name. If `ConfirmPrompt` is a new wrapper around `SelectionPrompt`, clarify the relationship. Currently a newcomer would be confused by the inconsistency.

### Issue 2: Dead Variable in `should_skip_for_phase()` (P2)

Line 764: `current_phase = phase_state.get("current_phase", "")` — this variable is **declared but never used**. The code on lines 765-780 uses `workflow_id` and `phase_id` directly. And the `phase_state.json` schema (line 468-474) has no `current_phase` field — it has `workflow_id`, `phase_id`, `phase_entered_at`, and `current_phase_file`.

→ **Recommend:** Remove the dead line. It references a field that doesn't exist in the schema and would confuse implementers.

### Issue 3: `/compact` Recovery Mechanism — Still Vague (P1)

Line 573: "The existing `post_compact_injector.py` hook trigger (currently zero consumers) fires after compaction."

This references a **file** (`post_compact_injector.py`) that sounds like it's part of the old file-hook system. Is `post_compact_injector.py` an independent infrastructure piece that survives the SDK hook migration? Or does it need to become an SDK hook?

The spec says "Zero new infrastructure — uses an existing hook trigger." But it's unclear whether this "existing hook trigger" is:
1. A file hook trigger in `generate_hooks.py` (deleted) — then this needs rewriting
2. An independent Python module that survives — then clarify this
3. A new SDK hook — then it IS new infrastructure

→ **Recommend:** Clarify whether `/compact` recovery uses an SDK hook or the existing `post_compact_injector.py`. If the latter, explicitly state it survives the file-hook deletion.

### Issue 4: `block` vs `block_roles` Field Name Drift (P2)

The `Rule` dataclass (line 646) uses `block_roles` and `allow_roles`. But §3.3 line 723 says:

> "Same convention as `block: [Subagent]` for role scoping"

And the old spec (before SDK update) used `block: list[str]` in the Rule dataclass. The YAML examples throughout the spec don't show the role-scoping field explicitly, so it's unclear whether `rules.yaml` uses `block:` or `block_roles:`.

→ **Recommend:** Show one YAML example with role scoping and confirm the YAML field name matches the Python field name (or document the mapping).

---

## Consistently Used Terms ✓ (No Drift)

| Term | Status |
|---|---|
| **Workflow** | Consistent umbrella term throughout |
| **Advisory / Enforced** | 2×2 framing clear, consistent in §1.0, §3.3, §4 |
| **ManualConfirm** (check gate) vs **`user_confirm`** (guardrail enforcement) | Correctly disambiguated everywhere, including §11 |
| **Check** / **Phase** | Layer 3 exclusively — no regression to old terms |
| **SDK hook** (new) vs **file hook** (old) | Consistently distinguished |
| **phase_block / phase_allow** | Consistent in YAML, code, and prose |
| **Qualified phase ID** | Consistent format `workflow_id:phase_id` throughout |
| **Gate** (check-based) vs **Guard** (rule-based) | §11 distinguishes them cleanly |
| **Content focus** (not "content lock") | Consistent — A.3 documents why the old term was wrong |

---

## Summary

| Category | Count |
|---|---|
| P0 issues from first review | 3 → all **resolved** ✅ |
| P1 issues from first review | 4 → 3 resolved, 1 partially resolved |
| P2 issues from first review | 2 → all **resolved** ✅ |
| New issues found | 4 (1×P1, 2×P2, 1×P1) |

**Overall assessment:** The spec is in **good shape** after Composability's update. The SDK hook architecture is well-integrated. The 9+ ghost `generate_hooks.py` references are all gone. The remaining issues are minor naming inconsistencies, not architectural confusion. The spec is newcomer-readable for the SDK hook architecture.
