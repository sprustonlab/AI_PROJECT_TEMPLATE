# Skeptic Stress-Test: Hints as Copier Question + ClaudeChic Discovery

## Context

New direction: hints becomes a Copier generation question (`use_hints: bool`). If enabled, Copier generates a `hints/` folder in the project. ClaudeChic discovers this folder at runtime and loads hints from it.

This is architecturally different from the previous spec (which assumed hints code lived inside ClaudeChic). It moves hints to the **template side**, with ClaudeChic as a **discovery engine**. Let me stress-test this.

---

## 1. Old ClaudeChic That Doesn't Know About Hints Discovery

**Scenario:** User generates a project with `use_hints=true` (gets `hints/` folder), but their ClaudeChic is an older version without the discovery code.

**What happens:** The `hints/` folder sits there inert. Old ClaudeChic never looks for it, never imports it, never crashes. The folder is just dead code from ClaudeChic's perspective.

**Verdict: Graceful ignore by default.** ✅

This is the same behavior as MCP tools: if `mcp_tools/` exists but ClaudeChic didn't have `discover_mcp_tools()`, the directory would be ignored. The filesystem doesn't force code execution.

**But there's a subtlety:** The user opted into hints and gets no hints. They don't know why. There's no error, no warning, nothing. Silent feature absence.

**Mitigation options (pick one):**

- **A. Version marker (recommended):** The `hints/` folder includes a `__version__` or `HINTS.md` that documents "requires ClaudeChic >= X.Y." This is documentation, not enforcement. Low cost, helps debugging.

- **B. Feature detection in a skill/hook:** A lightweight CLAUDE.md note or skill that says "this project uses contextual hints — update ClaudeChic if you don't see them." This is the "self-documenting project" approach.

- **C. Do nothing:** Accept that old ClaudeChic + new template = no hints. The user upgrades ClaudeChic eventually and hints appear. This is how every optional feature works.

**Recommendation: Option A** — a version marker file is cheap and aids debugging without adding machinery.

---

## 2. Malformed `hints/` Folder

**Scenario:** The `hints/` folder exists but is broken — missing files, syntax errors in Python, wrong structure, partial generation.

**What should happen:** Following ClaudeChic's iron rule ("discovery never crashes"), the system must degrade gracefully.

**Stress-testing specific failure modes:**

| Failure | Expected Behavior | Risk |
|---------|-------------------|------|
| `hints/` exists but is empty | No hints loaded, no error | None — same as `mcp_tools/` empty |
| `hints/__init__.py` has syntax error | Import fails, logged as warning, no hints | None — same as malformed MCP tool |
| `hints/hints.py` missing `BUILTIN_HINTS` | Discovery logs warning, skips | None — follows `get_tools()` missing pattern |
| `hints/triggers/` has import error in one trigger | That trigger skipped, others still work | **Tricky** — see below |
| `BUILTIN_HINTS` contains a hint with broken trigger | That hint's `check()` throws at evaluation time | **Must be caught** |
| State file `.claude/onboarding_state.json` is corrupt | Already handled — `HintStateStore._load()` resets to empty | None ✅ |

**The tricky case: broken trigger at evaluation time.**

MCP discovery catches errors at **import time** (when `get_tools()` is called). But hint triggers are evaluated **later** (at startup, after discovery). If `GitNotInitialized.check()` throws because of a bug in the trigger code, we need a try-except around each `trigger.check(state)` call in the evaluation pipeline.

The current spec's pipeline pseudocode:
```python
for hint in registry:
    if not activation.is_active(hint.id):
        continue
    if not hint.trigger.check(project_state):  # ← THIS CAN THROW
        continue
    ...
```

**Issue: The pipeline must wrap `hint.trigger.check()` in try-except.** This was implicit in my original review ("wrap every condition check in try/except") but is now more critical because triggers are **user-generated template code**, not ClaudeChic internals. Template code is more likely to have bugs than framework code.

**Required addition to pipeline:**
```python
for hint in registry:
    if not activation.is_active(hint.id):
        continue
    try:
        triggered = hint.trigger.check(project_state)
    except Exception:
        log.warning("hints: trigger %s failed, skipping", hint.id, exc_info=True)
        continue
    if not triggered:
        continue
    ...
```

This is not optional — it's the iron rule applied to evaluation, not just discovery.

---

## 3. Convention-Based vs Config-Based Discovery

**Convention-based:** ClaudeChic checks for `hints/` at a known path (like `mcp_tools/`).
**Config-based:** An entry in `.claudechic.yaml` points to the hints code location.

### Convention-based (recommended)

**How MCP tools do it:** `discover_mcp_tools(Path.cwd() / "mcp_tools")` — hardcoded path, no config entry. If the directory exists, tools are loaded. If not, nothing happens.

**Pros:**
- Zero configuration — Copier generates the folder, ClaudeChic finds it. Done.
- Matches the existing MCP tools pattern exactly. No new discovery paradigm.
- Can't misconfigure (no path to typo, no YAML key to forget).
- Works without `.claudechic.yaml` existing at all.

**Cons:**
- Path is hardcoded — can't relocate `hints/` without changing ClaudeChic.
- If two different template systems both want to provide hints, they'd conflict on the directory name.

**Risk assessment:** The cons are theoretical. This template owns both the generator and the discovery code. There's no reason to relocate the folder. And "two competing hints systems" is a problem we don't have and shouldn't design for.

### Config-based

**How it would work:**
```yaml
# .claudechic.yaml
hints:
  path: hints/   # or custom path
  enabled: true
```

**Pros:**
- Flexible — user can relocate the folder.
- Explicit — you can see in config that hints are active.

**Cons:**
- **Requires config entry to exist** — if Copier doesn't write this, or the user deletes it, or `.claudechic.yaml` doesn't exist yet, hints silently break.
- **Two things must agree** — the folder must exist AND the config must point to it. MCP tools avoid this by having only one condition (folder exists).
- **Violates convention over configuration** — adds a config knob where a convention suffices.
- **Config file ownership ambiguity** — `.claudechic.yaml` is a ClaudeChic file. Adding template-specific entries to it couples template concerns into framework config.

### Verdict: Convention-based. ✅

Same pattern as `mcp_tools/`. Known path, existence-check, graceful absence. The discovery function signature mirrors the existing one:

```python
def discover_hints(hints_dir: Path) -> list[HintSpec]:
    if not hints_dir.is_dir():
        return []
    # ... iron-rule-compliant loading
```

**One refinement:** The activation toggle (`enabled: true/false`) still lives in `.claudechic.yaml`. But that's a **runtime behavior flag**, not a discovery mechanism. The distinction:
- **Discovery:** "Is there a `hints/` folder?" → convention
- **Activation:** "Does the user want hints right now?" → config

These are different questions with different answers.

---

## 4. Version Coupling Between Template and ClaudeChic

This is the most important question. Let me be precise about what couples to what.

### The contract surface

Template's `hints/` code needs ClaudeChic to:
1. **Discover** the `hints/` folder (know to look for it)
2. **Import** and call a known entry point (e.g., `get_hints()` or `BUILTIN_HINTS`)
3. **Provide** a `ProjectState` object that triggers can query
4. **Evaluate** triggers and deliver toasts via `app.notify()`

ClaudeChic's discovery code needs the template's `hints/` to:
1. **Export** a known entry point (`BUILTIN_HINTS` list, or a `get_hints()` function)
2. **Follow** the `TriggerCondition` protocol (`.check(state) -> bool`)
3. **Use only** `ProjectState` for project introspection (no direct Textual/ClaudeChic imports)

### Where coupling is dangerous

**Scenario A: Template adds a new trigger type that needs data ClaudeChic doesn't provide in `ProjectState`.**

Example: Template v3 adds a trigger that checks "number of Claude API calls this month." This requires `ProjectState` to have an `api_usage` field. But the user's ClaudeChic (v2) doesn't populate that field.

**Result:** Trigger accesses `state.api_usage` → `AttributeError` → caught by iron-rule try-except → hint skipped. Graceful degradation. ✅ But the user doesn't get the hint they expected.

**Mitigation:** `ProjectState` should be treated as extensible. Triggers should use `getattr(state, 'api_usage', None)` or `ProjectState` should have a `.get(key, default)` generic accessor alongside typed properties. This way template-side triggers can check for capabilities without crashing.

**Scenario B: ClaudeChic changes the `ProjectState` interface (renames a field, changes a return type).**

Example: ClaudeChic renames `state.copier` to `state.template_config`. Template's `GuardrailsOnlyDefault` trigger calls `state.copier.use_guardrails` → `AttributeError`.

**Result:** Same as above — caught by iron rule, hint skipped. But now ALL Copier-aware triggers break simultaneously. Multiple hints disappear without explanation.

**Mitigation:** `ProjectState` is a versioned contract. ClaudeChic commits to backward-compatible changes:
- New fields: add, don't rename
- Removed fields: deprecate (keep as property returning default), don't delete
- This is the same discipline any plugin API requires

**Scenario C: Template uses a lifecycle policy that ClaudeChic doesn't understand.**

If lifecycle policies are template-side code (frozen dataclasses in `hints/`), this isn't a coupling issue — ClaudeChic just calls `.should_show()` on whatever object it gets. Protocol-based dispatch.

But if lifecycle policies are ClaudeChic-side enums referenced by name from the template (`lifecycle="show-until-resolved"`), then template v3 adding `lifecycle="show-on-weekdays"` breaks on ClaudeChic v2 which doesn't know that value.

**Recommendation:** Lifecycle policies should be **objects, not strings**. The current spec already does this — `HintSpec.lifecycle` is a string enum, but the actual lifecycle *behavior* is a `HintLifecycle` protocol implementation. If lifecycle objects live in the template's `hints/` code, there's no coupling. If they live in ClaudeChic, then the string→object mapping is the coupling point.

**Cleaner design:** `HintSpec` should carry a `lifecycle: HintLifecycle` object, not a `lifecycle: str`. The template instantiates `ShowOnce()` or `CooldownPeriod(3600)` directly. ClaudeChic just calls the protocol methods. No string mapping, no version coupling on lifecycle.

### The MCP tools precedent

MCP tools have the exact same coupling problem and solve it well:
- **Contract:** `get_tools(**kwargs) -> list[tool]`
- **Kwargs are extensible:** New kwargs added in new ClaudeChic versions; old tools ignore unknown kwargs via `**kwargs`
- **Tool protocol is stable:** `name`, `description`, `input_schema`, `handler` — hasn't changed
- **Iron rule:** If anything fails, skip and log

Hints should follow the same pattern:
- **Contract:** `get_hints(state: ProjectState) -> list[HintSpec]` (or just export `BUILTIN_HINTS`)
- **ProjectState is extensible:** New fields added, old triggers use only what they know
- **HintSpec protocol is stable:** `id`, `trigger`, `message`, `severity`, `lifecycle` — define once, don't change
- **Iron rule:** If anything fails, skip and log

### Coupling verdict

**Version coupling exists but is manageable.** The coupling surface is:
1. The discovery entry point name (`get_hints` or `BUILTIN_HINTS`)
2. The `ProjectState` interface
3. The `TriggerCondition` protocol
4. The `HintLifecycle` protocol (if lifecycle objects are template-side)

All four are small, stable interfaces. The MCP tools precedent shows this pattern works in production. The iron rule provides graceful degradation when versions mismatch.

**One required change:** Make `ProjectState` explicitly extensible with a `.get(key, default)` method for forward compatibility. Triggers for new features should use this instead of direct attribute access when they depend on data that older ClaudeChic versions might not provide.

---

## Summary

| Question | Verdict | Action Needed |
|----------|---------|---------------|
| Old ClaudeChic + new template? | ✅ Safe — folder is inert | Add version marker file for debuggability |
| Malformed `hints/` folder? | ✅ Safe IF iron rule is applied | **Must add try-except around each `trigger.check()` call in pipeline** — this is not optional |
| Convention vs config discovery? | Convention (like `mcp_tools/`) | No config entry for discovery. Activation toggle in `.claudechic.yaml` `hints:` section |
| Version coupling? | Manageable | Make `ProjectState` extensible (`.get()` method). Keep lifecycle as objects, not strings. Follow MCP tools precedent |

### Required Spec Changes

1. **Pipeline must wrap `trigger.check()` in try-except** — currently implicit, must be explicit in the pipeline spec. Template-side triggers are more likely to have bugs than framework code.

2. **`HintSpec.lifecycle` should be a `HintLifecycle` object, not a string** — eliminates version coupling on lifecycle policies. Template bundles its own lifecycle implementations.

3. **`ProjectState` needs a `.get(key, default)` escape hatch** — for forward-compatible triggers that depend on data newer ClaudeChic versions provide.

4. **Discovery function should mirror `discover_mcp_tools()` signature** — convention-based (`hints/`), iron-rule-compliant, returns empty list on absence.
