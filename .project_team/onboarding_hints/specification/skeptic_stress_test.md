# Skeptic Stress-Test Review: Consolidated Architecture

## Verdict: PASS with 2 issues to address (no blockers)

The architecture is solid. The four specs are internally consistent, the seams are clean, and the essential complexity I flagged in my initial review has been addressed. Two issues need resolution before implementation; neither is a blocker if handled.

---

## 1. Priority + Throttle: Does It Prevent Toast Spam?

**Verdict: YES — with one gap to close.**

### Fresh project walkthrough (worst case)

A brand-new project generated with all features enabled fires all 6 triggers:

| Hint | Priority | Lifecycle |
|------|----------|-----------|
| git-setup | 1 (blocking) | show-until-resolved |
| pattern-miner-ready | 2 (high-value) | show-once |
| project-team-discovery | 2 (high-value) | show-once |
| guardrails-default-only | 3 (enhancement) | show-until-resolved |
| mcp-tools-empty | 3 (enhancement) | show-once |
| cluster-ready | 3 (enhancement) | show-once |

**Session 1:** Algorithm sorts by (priority ASC, last_shown ASC). All have `last_shown=null`. Takes top 2: `git-setup` (priority 1) + one of the priority 2 hints. Budget exhausted. **4 hints suppressed. No spam.** ✅

**Session 2:** If git resolved, `git-setup` drops out. Remaining priority 2 hint fires (never shown). One priority 3 hint also shown. **Still 2 max.** ✅

**Session 3+:** Priority 3 hints rotate via `last_shown` tiebreaker. Each gets its turn. ✅

### The gap: `pattern-miner-ready` won't fire on a fresh project

The trigger requires `session_count >= 10` AND `miner.exists == False`. A fresh project has 0 sessions. So in practice, session 1 only fires 5 hints, not 6. The pattern miner hint won't appear until session 10+, at which point most other show-once hints will be exhausted. This is actually good design — the hint arrives when it's relevant, not before.

**No action needed.** The algorithm works correctly for the real scenario.

### One gap: tiebreaker for equal (priority, last_shown)

When multiple hints share the same priority and `last_shown=null` (both never shown), the spec says "pick alphabetically or by definition order." The UI design spec says "sort by priority ASC, then last_shown ASC." But `null` vs `null` is undefined ordering.

**Issue #1 (minor):** Define the tiebreaker explicitly. Recommendation: use definition order in `BUILTIN_HINTS` (list index). This is deterministic, controllable by the developer, and requires zero additional machinery. Treat `null` as `0` (oldest possible timestamp) for sorting.

---

## 2. HintStateStore vs ActivationConfig Separation

**Verdict: Clean separation, one latent concern.**

### What's good

- **Different files:** Lifecycle state in `.claude/onboarding_state.json`, activation config in `.claudechic.yaml`. Different locations, different ownership patterns. ✅
- **Different semantics:** State is mutable (incremented each show), config is user-preference (edited via commands). ✅
- **Re-enable doesn't reset lifecycle:** Explicitly documented and correct. The activation axis is a gate, not a reset. ✅
- **Unknown hint IDs handled gracefully:** Both stores silently ignore unknown IDs. ✅

### The concern: two persistence locations with different gitignore expectations

- `.claudechic.yaml` — project-level config, likely checked into git (it has non-hints settings like `experimental.*`, `vi-mode`, etc.)
- `.claude/hints_state.json` — per-user display history, should be gitignored

The activation axis spec says `.claudechic.yaml` is "checked into git or .gitignored." But `disabled_hints` is a user preference — if Alice disables `git-setup` and commits `.claudechic.yaml`, Bob also loses that hint.

**Issue #2 (medium):** The hints section of `.claudechic.yaml` has mixed shareability. `enabled: true/false` could reasonably be a team decision (e.g., "our team doesn't need hints"). But `disabled_hints` is personal preference.

**Recommendation:** Accept this for v1. The config is small and the edge case (one team member's dismissals affecting another) is minor for template projects, which are typically single-developer. Document that `disabled_hints` is per-user preference and suggest gitignoring `.claudechic.yaml` if multiple developers share the project. No architectural change needed.

---

## 3. Copier-Awareness Strategy

**Verdict: SOUND. This is well-designed.**

### What works

- **Per-trigger self-skip:** Each trigger checks `state.copier.use_<feature>` as first operation. Clean, no engine branching. ✅
- **CopierAnswers from `.copier-answers.yml`:** Standard Copier convention. File always exists in generated projects. ✅
- **Frozen dataclass:** `CopierAnswers` is immutable — triggers can't accidentally mutate it. ✅
- **Graceful defaults:** `raw.get("use_guardrails", True)` — if the key is missing, assume the feature is enabled (show the hint rather than silently suppress it). Correct default bias. ✅

### Stress tests

1. **User says `use_cluster=false` during Copier:** `ClusterConfiguredUnused.check()` → `state.copier.use_cluster` → `False` → returns `False`. Hint never fires. ✅
2. **`.copier-answers.yml` deleted:** `CopierAnswers.raw` would be empty dict → all `.get()` calls return defaults → hints fire for default-enabled features, skip for default-disabled ones. Reasonable degradation. ✅
3. **New Copier feature added in template v2:** If `use_new_feature` isn't in old `.copier-answers.yml`, `raw.get("use_new_feature", True)` returns `True` (or whatever the default is). New hints for new features work automatically as long as the default matches. ✅
4. **Custom hints don't know about Copier:** A user-written trigger that doesn't check `state.copier` will fire regardless of Copier answers. This is correct — custom triggers own their own gating logic. ✅

**No issues found.** The Copier strategy is the cleanest part of the design.

---

## 4. `/hints` Command Design

**Verdict: GOOD — one clarification needed.**

### What works

- **Re-evaluates triggers at command time:** Resolved hints disappear. Directly addresses my "stale hints" concern. ✅
- **Groups by state:** Active first, dismissed below separator. Clear visual hierarchy. ✅
- **Dismiss via keyboard:** `d` and `a` keys. Lightweight. ✅
- **Chat output, not modal:** Consistent with existing command patterns. ✅

### Clarification needed: `/hints` vs lifecycle interaction

The UI spec says `/hints` lists "all hints whose triggers currently fire." But the lifecycle axis has policies like `ShowOnce` — if a hint was already shown once and its lifecycle is exhausted, should it appear in `/hints`?

**Scenario:** `mcp-tools-empty` has `lifecycle=show-once`. It was shown as a toast in session 1. The trigger still fires (no custom tools added). User types `/hints` in session 2.

**Option A:** `/hints` shows it (trigger fires, it's still relevant information).
**Option B:** `/hints` hides it (lifecycle exhausted, we decided not to show it anymore).

The spec implies Option A (it lists "all hints whose triggers currently fire" with badges like `[seen ×1]`). This is the right call — `/hints` is an explicit user action requesting information. Lifecycle throttling should apply to unsolicited toasts, not to user-requested summaries. The badge `[seen ×1]` tells the user they've already been notified.

**No change needed**, but this should be documented explicitly: `/hints` bypasses lifecycle suppression for display purposes, but respects activation (disabled hints don't appear) and trigger evaluation (resolved hints don't appear).

---

## 5. Additional Observations (No Issues — Noting for Completeness)

### Pipeline ordering is correct
```
Activation → Trigger → Lifecycle → Throttle → Present
```
Cheapest filter first (dict lookup), then filesystem checks, then state checks. Each stage can short-circuit. ✅

### Error handling follows MCP discovery iron rule
`ProjectState` methods use try/except on all filesystem operations. `HintStateStore._load()` handles corrupt files gracefully. Triggers are pure functions of `ProjectState` — if `ProjectState` construction fails, no triggers run but the app doesn't crash. ✅

### `ShowUntilResolved` + `dismissed` interaction is clean
Lifecycle checks `dismissed`, pipeline checks trigger. No cross-seam leakage. The scenario where a user dismisses a hint but the trigger still fires is handled correctly: hint doesn't toast (dismissed), but reappears in `/hints` under the "Dismissed" section (trigger still true, user can un-dismiss if they change their mind). ✅

### Atomic write pattern in HintStateStore
Write-to-temp-then-rename prevents corruption on crash. Matches existing patterns in the codebase. ✅

### The "first toast gets toggle suffix" rule
UI spec says only the first hint toast per session includes "disable with /hints off." This is a nice touch — teaches discoverability without nagging. ✅

---

## Summary

| Check | Verdict | Action |
|-------|---------|--------|
| Priority + throttle prevents spam | ✅ PASS | Define tiebreaker for equal (priority, last_shown) — use definition order |
| HintStateStore vs ActivationConfig | ✅ PASS | Document that `disabled_hints` in `.claudechic.yaml` is per-user; suggest gitignore if multi-dev |
| Copier-awareness | ✅ PASS | No issues |
| `/hints` command | ✅ PASS | Document that `/hints` bypasses lifecycle suppression for display |
| Error handling | ✅ PASS | Iron rule followed throughout |
| Seam cleanliness | ✅ PASS | All axes independent, swap tests pass |

**Overall: PASS. Ready for implementation planning.**
