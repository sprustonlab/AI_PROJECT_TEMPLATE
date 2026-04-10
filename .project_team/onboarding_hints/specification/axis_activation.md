# Axis: Activation

## Relevance Check

**Activation is a real, independent axis.** It is not collapsible into HintLifecycle.

- **Activation** answers: *Should this hint be considered at all?* It's about user preference — the user's conscious choice to suppress hints globally or individually.
- **HintLifecycle** answers: *Given an active hint, should it be shown right now?* It's about system logic — show-once tracking, cooldown timers, resolved-state detection.

These are orthogonal:
- A hint can be **active + lifecycle-exhausted** (user wants it, but it already showed once): don't show.
- A hint can be **deactivated + lifecycle-fresh** (user doesn't want it, but it's never been shown): don't show.
- Re-enabling a deactivated hint should NOT reset its lifecycle state. If you turned off `git-setup`, it was shown twice, then you re-enable it — the show-count stays at 2. Activation is a gate, not a reset.

**Collapse test:** If we merged Activation into Lifecycle (e.g., adding a "disabled-by-user" lifecycle state), then lifecycle would need to distinguish "I've shown this enough times" from "the user said stop." These have different re-entry semantics — re-enabling is a user action; lifecycle expiry is automatic. Merging them creates a dirty seam inside what should be one axis. They stay separate.

---

## Protocol Definition

```python
from typing import Protocol

class ActivationFilter(Protocol):
    """Pure filter: (hint_id, config) -> should_consider"""

    def is_active(self, hint_id: str) -> bool:
        """Return True if this hint should enter the pipeline.

        This is a pure filter. It does not:
        - Know what the hint checks (TriggerCondition's job)
        - Know when the hint runs (EvaluationTiming's job)
        - Know how the hint displays (Presentation's job)
        - Know the hint's show history (HintLifecycle's job)

        It only knows: does the user want this hint considered?
        """
        ...
```

**The seam is a boolean gate.** The pipeline calls `activation.is_active(hint_id)` before checking lifecycle or evaluating triggers. If `False`, the hint is skipped entirely — no trigger evaluation, no lifecycle state update, no presentation.

---

## Activation Levels

Three levels, implemented as dataclasses (per Skeptic: Python, not YAML):

```python
from dataclasses import dataclass, field
from enum import Enum, auto


class ActivationLevel(Enum):
    """The three activation states."""
    GLOBAL_ENABLED = auto()   # All hints active (default)
    GLOBAL_DISABLED = auto()  # No hints shown
    SELECTIVE = auto()        # Global on, with per-hint overrides


@dataclass
class ActivationConfig:
    """User's activation preferences. Persisted to config file.

    Default state: globally enabled, no overrides.
    This means new projects get all hints with zero configuration.
    """
    level: ActivationLevel = ActivationLevel.GLOBAL_ENABLED
    disabled_hints: set[str] = field(default_factory=set)

    def is_active(self, hint_id: str) -> bool:
        """Pure filter: should this hint enter the pipeline?"""
        if self.level == ActivationLevel.GLOBAL_DISABLED:
            return False
        if self.level == ActivationLevel.SELECTIVE:
            return hint_id not in self.disabled_hints
        # GLOBAL_ENABLED
        return True

    def disable_globally(self) -> None:
        self.level = ActivationLevel.GLOBAL_DISABLED

    def enable_globally(self) -> None:
        self.level = ActivationLevel.GLOBAL_ENABLED
        # Note: does NOT clear disabled_hints.
        # If user re-enables globally then goes to SELECTIVE,
        # their per-hint overrides are preserved.

    def disable_hint(self, hint_id: str) -> None:
        self.disabled_hints.add(hint_id)
        if self.level == ActivationLevel.GLOBAL_ENABLED:
            self.level = ActivationLevel.SELECTIVE

    def enable_hint(self, hint_id: str) -> None:
        self.disabled_hints.discard(hint_id)
        if not self.disabled_hints:
            self.level = ActivationLevel.GLOBAL_ENABLED
```

### Design decisions:

1. **No `PerHintOverride` as a separate class.** The Composability analysis listed three values: enabled, disabled, per-hint-override. But "per-hint-override" is really "globally enabled + some hints disabled." A single `ActivationConfig` with a `disabled_hints` set captures all three states cleanly. The `ActivationLevel` enum is derived state for fast-path checks.

2. **No `enabled_hints` set.** Only `disabled_hints`. The default is "everything on." This avoids the problem of new hints being invisible because they weren't in an allow-list. When the template adds a new hint, it's automatically active unless the user explicitly disabled it.

3. **Re-enable preserves overrides.** `enable_globally()` doesn't clear `disabled_hints`. If the user had disabled `git-setup`, turned off hints globally, then turned it back on — `git-setup` is still individually disabled. This respects explicit user choices.

---

## User-Facing Controls

The user said: *"I want to think about onboarding as a skill which you can turn off."* (Note: the system has since been renamed from "onboarding" to "hints".)

### Commands (via ClaudeChic slash commands or CLI):

| Command | Effect |
|---------|--------|
| `/hints off` | Set `level = GLOBAL_DISABLED` |
| `/hints on` | Set `level = GLOBAL_ENABLED` (preserves per-hint overrides) |
| `/hints disable <hint-id>` | Add to `disabled_hints`, set level to `SELECTIVE` |
| `/hints enable <hint-id>` | Remove from `disabled_hints` |
| `/hints status` | Show current activation state + list of disabled hints |
| `/hints reset` | Reset to defaults (all enabled, clear overrides) |

### Config persistence

> **Revision 2a** — Moved activation config from `.claudechic.yaml` into
> the hints system's own state. The `hints/` folder should be self-contained.

**Principle:** If the hints system is a self-contained folder that ClaudeChic discovers, its state should NOT leak into ClaudeChic's config file. ClaudeChic owns `.claudechic.yaml`; the hints module owns its own state.

**Decision: Activation config lives in `.claude/hints_state.json` alongside lifecycle state.**

Both activation preferences and lifecycle history are hints-system state. They share a single file, with clear separation:

```json
{
  "version": 1,
  "activation": {
    "enabled": true,
    "disabled_hints": ["git-setup"]
  },
  "lifecycle": {
    "git-setup": {"times_shown": 2, "last_shown": "2026-03-31T12:00:00Z"},
    "mcp-tools-empty": {"times_shown": 1, "last_shown": "2026-03-30T10:00:00Z"}
  }
}
```

**Why one file, not two:**
- Both are hints-system state, exclusively owned by the `hints/` module
- No other module reads or writes this file
- Simpler: one file to manage, one atomic write, one graceful-degradation path
- The two sections (`activation` vs `lifecycle`) have clean internal seams — `ActivationConfig` reads only `activation`, `HintStateStore` reads only `lifecycle`

**Why NOT `.claudechic.yaml`:**
- `.claudechic.yaml` is ClaudeChic's config — the hints module shouldn't depend on or write to ClaudeChic's files
- Breaks the directory-separation principle: if you delete `hints/` and `.claude/hints_state.json`, the hints system is fully gone. No orphaned config in `.claudechic.yaml`.
- The hints module should work without `.claudechic.yaml` existing at all

**Mapping to `ActivationConfig`:**
- `enabled: false` → `ActivationLevel.GLOBAL_DISABLED`
- `enabled: true` + empty `disabled_hints` → `ActivationLevel.GLOBAL_ENABLED`
- `enabled: true` + non-empty `disabled_hints` → `ActivationLevel.SELECTIVE`

**Loading priority:**
1. `.claude/hints_state.json` in project (read by `hints/_state.py`)
2. Sensible default: `ActivationConfig()` (all enabled)

No user-global override. Hints are project-scoped — a fresh project starts with hints enabled. The cost of one `/hints off` command is low; the risk of a global "never hint me" hiding useful project-specific hints is high.

---

## Integration with Copier

Two options were considered:

### Option A: Copier question at generation time
```yaml
# copier.yml
use_hints:
  type: bool
  default: true
  help: "Enable contextual hints?"
```

### Option B: Always included, toggled at runtime

**Recommendation: Option B (always included, runtime toggle).**

Reasons:
1. **Copier questions are for structural choices** (do you want guardrails? cluster support?). These affect which files are generated. Hints are a runtime behavior, not a file-structure decision.
2. **The hints code is tiny** — a few dataclasses and a config entry. There's no meaningful cost to including it.
3. **Hints are most valuable in new projects** — the exact moment Copier runs. Asking "do you want hints?" at project creation is asking the user to opt out of help before they know they need it.
4. **Copier's `_exclude` mechanism is for file-level feature gating.** Hints don't need file exclusion; they need a runtime flag.
5. **The existing pattern supports this.** `use_guardrails` and `use_cluster` exclude entire directories. The hints system is not a directory — it's a behavior flag in an existing config file.

**However:** The Copier `_tasks` post-generation step could set an initial config. If someone generating a template for experienced users wants hints off by default:

```yaml
# copier.yml — optional, future consideration
hints_default:
  type: bool
  default: true
  help: "Start with hints enabled? (Can be toggled with /hints)"
```

This would write `hints.enabled: true/false` into `.claudechic.yaml` during generation. But this is a v2 concern — for v1, just default to enabled.

---

## Seam Verification

Activation is a pure filter. Let's verify it doesn't leak into other axes:

### Activation ↔ TriggerCondition
- **What crosses:** Nothing. Activation is checked *before* triggers run.
- **Swap test:** Replace `PathNotExists` with `SessionCount` — activation code unchanged. ✅
- **Leak risk:** Could activation want to know *why* a hint exists to decide if it's active? No — activation is user preference, not system logic.

### Activation ↔ EvaluationTiming
- **What crosses:** Nothing. Activation filter runs regardless of when evaluation happens.
- **Swap test:** Change from startup to on-command — activation code unchanged. ✅

### Activation ↔ Presentation
- **What crosses:** Nothing. If activation says "no," presentation never sees the hint.
- **Swap test:** Replace toast with log — activation code unchanged. ✅

### Activation ↔ HintLifecycle
- **What crosses:** Nothing directly. But the pipeline must apply both filters independently.
- **Critical invariant:** Deactivating then reactivating a hint must NOT reset lifecycle state. These are independent state stores:
  - Activation state: `activation` section in `.claude/hints_state.json`
  - Lifecycle state: `lifecycle` section in `.claude/hints_state.json`
  - Same file, but independent sections — clean internal seam
- **Swap test:** Change from show-once to cooldown — activation code unchanged. ✅

### Pipeline position

```
for hint in registry:
    if not activation.is_active(hint.id):     # ← Activation gate (first)
        continue
    if not hint.trigger(project_state):        # ← TriggerCondition
        continue
    if not lifecycle.should_show(hint.id):     # ← HintLifecycle
        continue
    presentation.deliver(hint)                 # ← Presentation
```

Activation is checked first because it's the cheapest filter (dict lookup vs. filesystem check for triggers). This is a performance optimization, not a semantic requirement — the order of `activation` and `trigger` checks doesn't affect correctness because they're independent.

---

## Interaction with HintLifecycle: Detailed

This is the most subtle interaction, so let's be explicit:

### Scenario table

| Activation | Lifecycle says | Result | Why |
|-----------|---------------|--------|-----|
| Active | Should show | **SHOW** | Both gates pass |
| Active | Already shown (show-once) | **Don't show** | Lifecycle gate blocks |
| Active | In cooldown | **Don't show** | Lifecycle gate blocks |
| Inactive | Should show | **Don't show** | Activation gate blocks |
| Inactive | Already shown | **Don't show** | Activation gate blocks (lifecycle not even checked) |

### Re-enable scenario (critical)

1. User sees `git-setup` hint (lifecycle records: `shown_count: 1`)
2. User runs `/hints disable git-setup` (activation: `disabled_hints: {git-setup}`)
3. Later, user runs `/hints enable git-setup` (activation: `disabled_hints: {}`)
4. **What happens?** Lifecycle still says `shown_count: 1`. If lifecycle policy is `show-once`, the hint does NOT re-appear. Correct — the user already saw it.

If the user wants to see it again, that's a lifecycle reset, not an activation toggle:
- `/hints reset-hint git-setup` — resets lifecycle state for that hint
- This is a Lifecycle concern, not Activation's job

### Global disable/enable scenario

1. User runs `/hints off` at session 3
2. Hints `A`, `B`, `C` were shown in sessions 1-3 (lifecycle recorded)
3. User runs `/hints on` at session 10
4. **What happens?** Lifecycle checks kick back in with their original state. Hint `A` (show-once, already shown) stays quiet. Hint `D` (new, never shown) fires. Correct.

---

## Edge Cases

### Unknown hint IDs in disabled_hints
If `.claude/hints_state.json` lists `disabled_hints: ["old-hint-that-was-removed"]`, the activation system should silently ignore unknown IDs. No error, no warning. This handles template version upgrades gracefully (per Skeptic F3).

### Empty config file
If `.claude/hints_state.json` doesn't exist or has no `activation` section, default to `ActivationConfig()` — globally enabled. New projects get hints automatically.

### Race condition: config edited mid-session
Activation config is read at the start of each evaluation cycle (startup for v1). If the user edits `.claude/hints_state.json` by hand mid-session, changes take effect next session. This is acceptable for v1.

---

## Summary

| Concern | Decision |
|---------|----------|
| **Is Activation a real axis?** | Yes — orthogonal to Lifecycle (user preference vs. system state) |
| **Data structure** | `ActivationConfig` dataclass with `level` enum + `disabled_hints` set |
| **Persistence** | `activation:` section in `.claude/hints_state.json` |
| **User controls** | `/hints on/off/disable <id>/enable <id>/status/reset` |
| **Copier integration** | Always included, runtime toggle (not a Copier question) |
| **Seam cleanliness** | Pure boolean filter, no knowledge of other axes |
| **Lifecycle interaction** | Independent state stores, re-enable doesn't reset lifecycle |
| **Default** | All hints enabled for new projects |
