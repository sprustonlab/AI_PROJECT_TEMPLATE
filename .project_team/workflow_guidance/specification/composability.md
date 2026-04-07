# Composability Analysis: Workflow Guidance System

## Domain Understanding

The Workflow Guidance System is infrastructure inside claudechic that unifies scattered guidance mechanisms (rules, checks, hints) into a single system. Users author YAML manifests and markdown content in `workflows/`. The engine loads manifests, evaluates guidance, manages phases, and delivers content to agents. The project-team workflow is the first workflow built on this infrastructure.

The core value proposition: **decouple guidance authoring from guidance infrastructure**. A workflow author writes YAML + markdown. claudechic provides the loader, engine, checks, hooks, and delivery. No code changes needed to create a new workflow.

---

## Identified Axes

### Axis 1: Section Type (ManifestSection[T])

**What it is:** The kind of guidance declared in a manifest — rules, checks, hints, phases.

**Values:** `rules` | `checks` | `hints` | `phases` (extensible — adding a new section type means adding a parser, not changing the loader)

**Why it's independent:** Each section type has its own parser, its own runtime semantics, and its own delivery mechanism. The loader dispatches YAML sections to typed parsers without knowing what a "rule" or "check" means. A manifest with only rules and no checks is valid. A manifest with only checks and no rules is valid.

**Compositional law:** The `ManifestSection[T]` protocol. Every parser implements `parse(raw_yaml_section) -> list[T]`. The loader doesn't branch on section type — it dispatches uniformly.

**Seam:** Raw YAML dict (the output of `yaml.safe_load`) crosses the boundary between loader and parser. The loader doesn't interpret section contents. The parser doesn't know about other sections or about the file it came from.

---

### Axis 2: Check Type

**What it is:** How verification is performed — the implementation behind a check.

**Values:** `CommandOutputCheck` | `FileExistsCheck` | `FileContentCheck` | `ManualConfirm` (extensible via the Check protocol)

**Why it's independent:** All check types implement the same async protocol. The engine doesn't know which type it's running — it calls `check()` and gets pass/fail with evidence. A phase can gate on any mix of check types. Setup checks in `global.yaml` use the same protocol as `advance_checks` in phases.

**Compositional law:** The Check protocol — `async check() -> CheckResult(passed: bool, evidence: str)`. If a new check type follows this protocol, it works everywhere checks are used — no engine changes needed.

**Seam:** `CheckResult` crosses the boundary. The engine sees pass/fail + evidence string. It doesn't know whether the check ran a command, read a file, or asked the user. The check doesn't know whether it's gating a phase transition or reporting at startup.

---

### Axis 3: Scope (Where guidance applies)

**What it is:** The filtering dimensions that determine whether a piece of guidance is active for a given evaluation context.

**Sub-dimensions (these compose independently):**

| Filter | Values | Applies to |
|--------|--------|------------|
| **Namespace** | `_global` \| `{workflow_id}` | All guidance types |
| **Phase** | `phase_block` / `phase_allow` lists | Rules, hints |
| **Role** | `block_roles` / `allow_roles` lists | Rules |
| **Conditional** | `when: { copier: key }` | Checks |

**Why it's independent:** Each filter is a predicate evaluated independently. Phase filtering doesn't know about role filtering. Role filtering doesn't know about namespace. They compose with AND semantics: guidance is active only if ALL applicable filters pass. Adding a new filter dimension (e.g., `platform_allow`) requires no changes to existing filters.

**Compositional law:** Each filter is `(context) -> bool`. Evaluation is `all(f(ctx) for f in applicable_filters)`. No filter inspects another filter's state.

**Seam:** The evaluation context (tool name, agent role, current phase, copier answers) is a read-only snapshot passed to each filter. Filters return bool. No filter mutates context or depends on another filter's result.

**Potential issue — phase references cross workflow boundaries:** `phase_block: ["project-team:testing"]` requires the rule to know about a specific workflow's phase names. This is intentional (qualified IDs prevent ambiguity), but it means rules in `global.yaml` that reference phases create a coupling to specific workflows. The loader's startup validation (checking phase references against known phases) is the right mitigation — it makes this coupling explicit and fails fast.

---

### Axis 4: Enforcement / Delivery Mechanism

**What it is:** How guidance reaches the agent or user at runtime.

**Values:**

| Mechanism | Used by | Channel |
|-----------|---------|---------|
| **SDK hook (deny)** | Rules | PreToolUse → block decision |
| **SDK hook (user_confirm)** | Rules | PreToolUse → SelectionPrompt → block/allow |
| **SDK hook (warn/log)** | Rules | PreToolUse → log or soft block |
| **Toast hint** | Hints, check failures | TUI toast notification |
| **Prompt injection** | Agent folders, phases | Agent reads identity.md + phase.md |
| **PostCompact hook** | Phase context | Re-inject after `/compact` |

**Why it's independent:** A rule's enforcement level is a field on the rule, not a property of its content or scope. The same pattern-matching rule could be `deny` or `warn` — just change the YAML field. Hints use the toast pipeline regardless of whether they came from a manifest hint section or a `CheckFailed` adapter. Prompt injection works regardless of what the markdown contains.

**Compositional law:** Each delivery mechanism has its own protocol:
- SDK hooks: `(hook_input, match, ctx) -> decision_dict`
- Hints: `HintSpec` → `run_pipeline()` → `HintRecord` → toast
- Prompt injection: concatenate identity.md + phase.md → agent prompt string

**Seam between checks and hints:** The `CheckFailed` adapter bridges the Check protocol to the Hints pipeline. This is a clean adapter — it takes `CheckResult(passed=False, evidence=...)` and produces `HintSpec(trigger=AlwaysTrue, message=evidence, lifecycle=ShowUntilResolved)`. The check doesn't know about hints. The hints pipeline doesn't know about checks. The adapter is the only code that knows both.

---

### Axis 5: Lifecycle (Temporal behavior)

**What it is:** How guidance persists or changes over time — when it's shown, how often, when it disappears.

**Values:** `show-once` | `show-until-resolved` | `show-every-session` | `cooldown(seconds)` (existing in hints system, reusable)

**Why it's independent:** Lifecycle is orthogonal to content, scope, and delivery. A hint about git setup uses `ShowUntilResolved`. A hint about a command lesson uses `ShowEverySession`. Same pipeline, same delivery, different temporal policy.

**Compositional law:** The `HintLifecycle` protocol — `should_show(hint_id, state) -> bool` and `record_shown(hint_id, state)`. Any lifecycle implementation works with any hint.

**Seam:** The lifecycle protocol receives hint_id and state. It doesn't know what the hint says or why it was triggered. The hint doesn't know what lifecycle policy governs it.

---

### Axis 6: Content vs. Infrastructure

**What it is:** The separation between what users author (YAML manifests, markdown files in `workflows/`) and what claudechic provides (loader, engine, checks, hooks, delivery).

**Values:**
- **Content side:** `workflows/global.yaml`, `workflows/project_team/project_team.yaml`, agent folder markdown
- **Infrastructure side:** manifest loader, workflow engine, check protocol, SDK hook closures, hints pipeline, prompt assembly

**Why it's independent:** This is the foundational axis. A new workflow is pure content — YAML + markdown, no code changes to claudechic. The engine doesn't know what "project-team" means as a domain concept. It just loads manifests, runs checks, transitions phases, and delivers content.

**Compositional law:** Manifests follow a schema. Markdown files follow a naming convention (folder name = role, file name = phase). Infrastructure processes any content that follows these conventions.

**Seam:** The `workflows/` directory boundary. claudechic reads from it but never writes workflow-specific logic. Content authors write to it but never import claudechic internals.

**This is the most important axis.** If this seam leaks — if claudechic needs `if workflow == "project-team":` branches — the entire system fails its goal. Every workflow-specific behavior must be expressible in YAML + markdown.

---

## Crystal Analysis

### Crystal dimensions: 6 axes

The full crystal isn't a simple product (not all axes have discrete enumerable values), but the key compositional property holds: **any combination of axis values should produce a working system**.

### 10-Point Spot Check

| # | Section Type | Check Type | Scope | Enforcement | Lifecycle | Content/Infra | Works? |
|---|-------------|-----------|-------|-------------|-----------|--------------|--------|
| 1 | rule | N/A | global + phase_block | deny | N/A | YAML | Yes — existing guardrails |
| 2 | check | CommandOutput | global | N/A (→hint adapter) | show-until-resolved | YAML | Yes — setup checks design |
| 3 | check | ManualConfirm | workflow phase | N/A (→hint adapter) | show-once | YAML | Yes — advance_checks |
| 4 | hint | N/A | workflow phase | toast | show-once | YAML | Yes — phase hints |
| 5 | rule | N/A | global + role filter | user_confirm | N/A | YAML | Yes — role-scoped rules |
| 6 | check | FileExists | global | N/A (→hint adapter) | show-until-resolved | YAML | Yes — setup check |
| 7 | rule | N/A | workflow + phase_allow | deny | N/A | YAML | Yes — phase-scoped rule |
| 8 | check | FileContent | workflow phase advance | N/A | N/A | YAML | Yes — advance gate |
| 9 | hint | N/A | global | toast | cooldown | YAML | Yes — global hint |
| 10 | check | ManualConfirm | global setup | N/A (→hint adapter) | show-until-resolved | YAML | **Edge case** — ManualConfirm as a setup check is odd (asking the user to confirm something at startup that isn't gating a phase). Technically works but may not be useful. |

**Result: No crystal holes found.** Point 10 is a usability question, not a composability failure — the combination works mechanically even if it's unusual.

---

## Seam Analysis

### Seam 1: Loader ↔ Section Parsers
- **Interface:** `ManifestSection[T].parse(raw_yaml_dict) -> list[T]`
- **Status:** Clean by design. Loader dispatches by section key name. Parser receives raw dict.
- **Risk:** Low. The schema is simple (key → parser mapping). Adding a section type = registering a new key.

### Seam 2: Engine ↔ Check Protocol
- **Interface:** `async Check.check() -> CheckResult(passed, evidence)`
- **Status:** Clean. Engine calls check, gets result. Doesn't know implementation.
- **Risk:** Low for the four built-in types. `ManualConfirm` needs a confirmation callback injected at construction — this is the right pattern (dependency injection), but the engine must provide the callback. This callback is the seam between Check and TUI. It should be a simple `async () -> bool` callable, not an app reference.

### Seam 3: Checks ↔ Hints (CheckFailed adapter)
- **Interface:** `CheckResult → HintSpec` adapter
- **Status:** Clean adapter pattern. One-directional: checks produce results, adapter converts failures to hints.
- **Risk:** Low. The adapter is simple and stateless.

### Seam 4: Rules ↔ SDK Hooks
- **Interface:** `Rule` → hook closure captures rules_path and evaluates per tool call
- **Status:** Currently somewhat dirty. The existing `_guardrail_hooks()` in app.py captures `self` (the app) for `_show_guardrail_confirm()`. The hook closure knows about the TUI.
- **Recommendation:** The hook closure should receive a `confirm_callback: async (str) -> bool` rather than the app itself. This cleans the seam — the hook doesn't know about TUI, just about asking yes/no questions.

### Seam 5: Content ↔ Infrastructure (the critical seam)
- **Interface:** File system conventions — manifest schema, folder naming, file naming
- **Status:** Clean by design in the spec. No workflow-specific code in claudechic.
- **Risk:** Medium. The temptation to add `if workflow == "project-team":` will be strong during implementation. Guard this seam aggressively. Every apparent need for workflow-specific logic should be resolved by making the manifest schema more expressive, not by adding branches.

### Seam 6: Phase State ↔ Everything Else
- **Interface:** `state.json` read atomically, provides `current_phase` string
- **Status:** Clean. Phase state is a shared read-only resource. Rules read it for phase filtering. Engine writes it for phase transitions. Agent folders read it for prompt assembly.
- **Risk:** Low for reads. The atomic write (temp + rename) handles NFS correctly. No mtime caching avoids stale reads.

---

## Potential Issues

### 1. Loader Two-Mode Split (full load vs. rules-only)
The spec calls for two loader modes: full load at startup/phase transitions, and rules-only load on every tool call. This is a performance optimization that introduces a subtle coupling: the "rules-only" mode must know which sections are rules. If section types become more dynamic, this optimization may need revisiting.

**Recommendation:** Implement rules-only mode as a filter on the general loader (load all sections, return only rules), not as a separate code path. This preserves composability at a small performance cost. Profile before optimizing.

### 2. ManualConfirm Requires TUI Access
`ManualConfirm` is the only check type that needs user interaction. All others are pure computation. This breaks the "checks are async pure functions" mental model slightly. The mitigation (injecting a confirmation callback) is correct but should be documented clearly — `ManualConfirm` is a check that happens to have a side effect (user prompt).

### 3. warn Enforcement Infinite Loop Risk
The spec notes `warn` has an infinite-loop risk. This is a **seam leak**: the enforcement mechanism (warn) creates a feedback loop with the agent's behavior (retry). The fix isn't in the enforcement axis — it's in the delivery mechanism. `warn` needs a "acknowledged" state that prevents re-triggering for the same tool call sequence. This is a lifecycle concern applied to rules, which currently don't have lifecycle semantics.

### 4. Namespace Prefix Injection
The loader automatically prefixes IDs: `pip_block` → `_global:pip_block` or `project_team:pip_block`. This is invisible to the manifest author. If a manifest author writes a qualified ID by mistake (`project_team:pip_block` in the YAML), the loader would double-prefix to `project_team:project_team:pip_block`. The loader should validate that raw IDs don't contain `:`.

---

## Compositional Law Summary

The system has **three compositional laws** operating at different levels:

1. **ManifestSection[T] law** — All section parsers consume raw YAML dicts and produce typed objects. The loader doesn't know section semantics.

2. **Check protocol law** — All checks implement `async check() -> CheckResult`. The engine doesn't know check implementation details.

3. **Byte-equivalent: the `workflows/` convention law** — All workflows are YAML + markdown following a naming convention. claudechic doesn't know workflow domain semantics.

These three laws together guarantee: **a new workflow with new check types and new section types can be added without modifying claudechic infrastructure code.**

---

## File Structure Recommendation

The spec should organize claudechic code to reflect the axes:

```
claudechic/
  workflows/                    # Axis 6: Infrastructure side
    loader.py                   # ManifestSection[T] dispatcher
    engine.py                   # Phase transitions, state persistence
    checks.py                   # Check protocol + 4 built-in types
    agent_folders.py            # Prompt assembly from identity + phase files
    manifest_types.py           # Parsed types: Rule, CheckSpec, HintDecl, Phase
  guardrails/                   # Axis 4: SDK hook enforcement (existing, refactored)
    rules.py                    # Rule matching (already exists)
    hooks.py                    # Hook closure creation (extracted from app.py)
  hints/                        # Axis 4+5: Hint delivery + lifecycle (existing)
    _types.py                   # HintSpec, HintLifecycle, TriggerCondition
    _engine.py                  # Pipeline runner
    _state.py                   # State persistence
```

This makes the axes visible in the folder structure:
- `workflows/` = the engine/loader infrastructure (axes 1, 2, 6)
- `guardrails/` = enforcement delivery (axis 4 for rules)
- `hints/` = advisory delivery + lifecycle (axes 4, 5 for hints)
- Scope filtering (axis 3) lives in `workflows/loader.py` as composable predicates

---

## Recommended Deep-Dive Areas

1. **ManifestSection[T] protocol design** — The exact interface for section parsers, how the loader discovers and dispatches to them, and how the two-mode optimization works without breaking composability.

2. **Check ↔ TUI seam for ManualConfirm** — How the confirmation callback is injected without coupling checks to the app. This is the trickiest seam in the system.

3. **Existing code refactoring boundaries** — Exactly which code moves from `app.py` and `guardrails/rules.py` into the new `workflows/` module, and what interfaces change. The seam between old and new code must be clean.
