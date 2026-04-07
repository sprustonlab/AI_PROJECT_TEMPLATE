# Fresh Researcher Review: Architecture Validation Against Actual Code

**Requested by:** Coordinator
**Date:** 2026-04-04
**Tier of best source found:** T1 (Primary source code — the actual files)

## Query

Ground-truth the proposed architecture (phase_guard.py, scope.phase in rules.yaml, generate_hooks.py changes, Check protocol, R01 refactor) against the actual codebase. Answer 4 specific questions and validate the ~200 line estimate.

---

## Question 1: Can generate_hooks.py Be Extended to Emit Phase Checks Without a Rewrite?

### Answer: YES — It's designed for exactly this kind of extension.

**Evidence from the code:**

The code generation loop in `generate_bash_guard()` (line 672) iterates over rules and emits per-rule code blocks. Each rule gets an independent `if` block:

```python
for rule in rules:
    rule_id = rule["id"]
    enforcement = rule.get("enforcement", "warn")
    detect = rule.get("detect", {})
    # ... emit pattern match code ...
```

**The existing pattern for conditional code emission:**

The generator already conditionally emits code based on rule properties:
- Lines 688-745: `if detect_type in ("regex", "regex_match") and (has_allow or has_block)` — emits role-gated code
- Lines 747-771: `elif detect_type == "always"` — emits unconditional code
- Lines 832+: `elif detect_type in ("regex", "regex_match")` — emits universal code (no role gate)

**Adding phase checks follows the EXACT same pattern:**

For a rule with `scope: { phase: [4, 5] }`, the generator would wrap the existing per-rule `if` block in an outer phase check:

```python
# What generator would emit for a phase-scoped rule:
_phase = _get_current_phase()  # reads phase_state.json
if _phase in (4, 5):
    if re.search(r'...pattern...', command):
        _matched_rules.append(...)
```

**What needs to change in generate_hooks.py:**

| Change | Where | Lines Affected | Risk |
|--------|-------|---------------|------|
| Read `scope` field from rule dict | Per-rule loop (line 672+) | ~5 lines per generator function | None — new field, defaults to None |
| Emit `_get_current_phase()` helper at top of hook | Header section (line 616-660) | ~15 lines (one-time helper function) | Low — same pattern as role_guard import |
| Wrap rule's if-block in phase check | Per-rule code emission | ~4 lines wrapping per rule | Low — indentation change only |
| `needs_phase_guard()` helper (analogous to `needs_role_guard_import()`) | New function | ~10 lines | None — follows existing pattern |
| Validate `scope.phase` values in `validate_rules()` | Line 319-472 | ~15 lines | Low — same validation pattern |

**Total generate_hooks.py changes: ~50-60 lines across 5 functions.**

This is NOT a rewrite. It's adding a new conditional wrapper following the existing role-gate pattern. The generator is structured as a series of independent code-emission branches — adding a new branch is its intended extension mechanism.

### Risk Assessment

The main risk is **indentation correctness in generated code**. When a phase check wraps a role check which wraps a pattern match, the generated code has 3 levels of nesting. The existing code already handles 2 levels (role gate inside pattern match). Going to 3 is mechanical but the `indent()` helper (line 147) exists for exactly this.

---

## Question 2: Does the Hook Stdin Protocol Support Passing Phase State?

### Answer: NO — The hook must read the file directly. But this is fine.

**Evidence from the code:**

The hook stdin is a JSON blob from Claude Code's harness:

```python
# bash_guard.py line 22-26:
data = json.loads(sys.stdin.read())
session_id = data.get('session_id', 'unknown')
command = data.get('tool_input', {}).get('command', '')
cwd = data.get('cwd', os.getcwd())
```

The stdin protocol is defined by **Claude Code itself**, not by this codebase. We cannot add custom fields to it. The JSON contains:
- `tool_name` — which tool was invoked
- `tool_input` — the tool's parameters (command, file_path, etc.)
- `session_id` — session identifier
- `cwd` — current working directory

There is **no** `phase`, `mode`, or custom metadata field. We cannot inject one.

**How phase_guard.py should work instead:**

The hook reads `phase_state.json` from a known path at runtime. This is the SAME pattern that `role_guard.py` already uses for session markers:

```python
# role_guard.py line 108-111 (existing pattern):
guardrails_dir = Path(os.environ.get('GUARDRAILS_DIR', '.claude/guardrails'))
marker = guardrails_dir / 'sessions' / f'ao_{app_pid}'
if not marker.exists():
    return None  # no active team session
session = json.loads(marker.read_text(encoding="utf-8"))
```

**The phase_guard equivalent would be:**

```python
def get_current_phase(cwd: str) -> int | None:
    """Read current phase from any active project's phase_state.json."""
    ao_dir = Path(cwd) / '.ao_project_team'
    if not ao_dir.is_dir():
        return None
    for project_dir in ao_dir.iterdir():
        state_file = project_dir / 'phase_state.json'
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text(encoding='utf-8'))
                return data.get('current_phase')
            except (json.JSONDecodeError, OSError):
                return None
    return None
```

**Performance:** One `Path.iterdir()` + one `json.loads()` = 1-3ms local, 5-15ms NFS. The generated hook would only call this if any rule has `scope.phase` set. For hooks with zero phase-scoped rules (the current state), zero overhead.

**Discovery issue:** Multiple projects can exist under `.ao_project_team/`. Which one is "active"? Options:
1. **Last modified** — `phase_state.json` with most recent `updated_at`
2. **Environment variable** — `AO_ACTIVE_PROJECT=tutorial_system`
3. **Single active** — only one project can be in an active phase at a time

Recommendation: Option 1 (last modified) for v1 — simplest, no new env vars needed. The Coordinator already writes `STATUS.md` on every phase transition, so `phase_state.json` would have the same recency signal.

---

## Question 3: Is the Atomic-Write Pattern in hints_state Reusable As-Is?

### Answer: YES — Copy-paste with field changes. ~40 lines.

**Evidence from the code:**

The `HintStateStore.save()` method (lines 348-385 of `_state.py`):

```python
def save(self) -> None:
    self._path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _CURRENT_VERSION,
        "activation": self._activation,
        "lifecycle": self._lifecycle,
    }
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=self._path.parent,
            prefix=".hints_state_",
            suffix=".tmp",
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
                f.write("\n")
            Path(tmp_name).rename(self._path)
        except BaseException:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass
            raise
    except OSError:
        pass  # State remains in memory; next save will retry.
```

This is a **textbook atomic write**:
1. `mkstemp` in same directory (same filesystem for rename atomicity)
2. Write to temp file
3. Atomic rename
4. Cleanup on failure
5. Silent degradation on filesystem errors

**For PhaseStateStore, the save() method is identical** — only the `payload` dict changes:

```python
payload = {
    "version": 1,
    "project_id": self._project_id,
    "current_phase": self._current_phase,
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "updated_by": self._updated_by,
}
```

The `_load()` method (lines 223-262) is equally reusable — same graceful degradation pattern (missing file → defaults, corrupt JSON → defaults, future version → defaults).

**Estimate: ~40-50 lines** for a complete `PhaseStateStore` class with `_load()`, `save()`, `get_current_phase()`, `set_phase()`. No need to reinvent any persistence logic.

---

## Question 4: What's the Real Cost of Modifying generate_hooks.py?

### Answer: It's 2,155 lines, but you only touch ~60 of them. Here's the map.

**File structure (by line range):**

| Lines | Section | Touched? |
|-------|---------|----------|
| 1-99 | Constants, imports, YAML loader | NO |
| 100-128 | Message resolvers | NO |
| 130-196 | Helpers (escape, indent, strip_contexts) | NO |
| 198-281 | LOG_HIT_TEMPLATE (inlined into hooks) | NO |
| 282-316 | `needs_role_guard_import()`, `needs_strip_contexts()` | ADD: `needs_phase_guard()` (~10 lines) |
| 319-472 | `validate_rules()` | ADD: scope.phase validation (~15 lines) |
| 475-572 | `generate_matrix()` | NO |
| 574-595 | `group_rules_by_trigger()`, `needs_strip_contexts()` | NO |
| 597-970 | `generate_bash_guard()` | MODIFY: per-rule emission loop (~20 lines) |
| 971-1107 | `generate_read_guard()` | MAYBE: only if Read rules get phase scope |
| 1108-1244 | `generate_glob_guard()` | MAYBE: only if Glob rules get phase scope |
| 1245-1633 | `generate_write_guard()` | MAYBE: only if Write/Edit rules get phase scope |
| 1634-1873 | `generate_post_compact_injector()` | NO |
| 1874-1977 | `update_settings_json()` | NO |
| 1978-2072 | `generate_all()` | NO (rules.d/ handles contributed rules) |
| 2075-2155 | CLI (`check_mode`, `main`) | NO |

**Definite changes:**

| What | Lines | Description |
|------|-------|-------------|
| `needs_phase_guard()` function | ~10 | Check if any rule has `scope.phase` set |
| `validate_rules()` additions | ~15 | Validate scope.phase values are ints, non-empty list |
| Phase helper template (like `LOG_HIT_TEMPLATE`) | ~15 | `_get_current_phase()` function to inline into hooks |
| Per-rule phase wrapper in `generate_bash_guard()` | ~20 | Wrap existing if-block in phase check when scope.phase present |

**Total definite changes: ~60 lines in generate_hooks.py.**

**Conditional changes** (only if Write/Read/Glob rules get phase scope):
- Same ~20-line pattern repeated in each generator function
- But for v1, only `generate_bash_guard()` needs it (R01 is the only candidate)

**Why 2,155 lines doesn't mean 2,155 lines of risk:**

The file is 2,155 lines because it has 6 generator functions (one per trigger type), each ~200-400 lines, plus ~600 lines of templates/helpers. The generators are **independent** — modifying `generate_bash_guard()` cannot break `generate_write_guard()`. The code generation architecture is inherently modular despite being one file.

**The --check mode is your safety net:**
```bash
python3 .claude/guardrails/generate_hooks.py --check
```
This regenerates to a temp dir and diff-compares against committed hooks. Any change in generated output is caught. After modifying the generator, running `--check` with the old rules.yaml should produce zero drift (since no existing rules have `scope.phase`). Only when you ADD a phase-scoped rule will the generated hooks change.

---

## Complete Line Count Estimate

### phase_guard.py (NEW file)

| Component | Lines | Notes |
|-----------|-------|-------|
| Module docstring + imports | 10 | |
| `get_current_phase(cwd) -> int \| None` | 20 | Read phase_state.json, handle missing/corrupt |
| `get_current_mode(cwd) -> str \| None` | 15 | Read mode from state (normal/tutorial/team) |
| **Total** | **~45** | Standalone module, imported by generated hooks |

### phase_state.py (NEW file — or section in existing module)

| Component | Lines | Notes |
|-----------|-------|-------|
| `PhaseStateStore.__init__` + `_load()` | 30 | Copy HintStateStore pattern exactly |
| `PhaseStateStore.save()` | 25 | Copy atomic write pattern exactly |
| `get_current_phase()` / `set_phase()` | 15 | Simple getters/setters |
| `PhaseStateStore` total | **~70** | |

### generate_hooks.py CHANGES

| Component | Lines Changed | Notes |
|-----------|--------------|-------|
| `needs_phase_guard()` | 10 | New function |
| `validate_rules()` additions | 15 | Scope validation |
| Phase helper template constant | 15 | Inlined into hooks |
| `generate_bash_guard()` per-rule wrapper | 20 | Phase check wrapping |
| **Total changes** | **~60** | In a 2,155-line file |

### rules.yaml schema extension

| Component | Lines | Notes |
|-----------|-------|-------|
| Add `scope:` field to R01 (proof rule) | 3 | `scope: { phase: [4] }` |
| Document scope field in README.md | 10 | |
| **Total** | **~13** | |

### Check protocol (checks.py — NEW file)

| Component | Lines | Notes |
|-----------|-------|-------|
| `Check` Protocol class | 10 | `check(context) -> CheckResult` |
| `CheckResult` dataclass | 10 | `passed, message, evidence` |
| `CheckContext` dataclass | 10 | `cwd, env, project_state` |
| `CommandOutputCheck` | 25 | Run command, check exit code + output regex |
| `FileExistsCheck` | 15 | Check path exists |
| `CompoundCheck` | 15 | AND/OR of sub-checks |
| **Total** | **~85** | |

### Grand Total

| Component | Lines | Type |
|-----------|-------|------|
| phase_guard.py | 45 | New file |
| phase_state.py | 70 | New file |
| generate_hooks.py changes | 60 | Modifications |
| rules.yaml + README | 13 | Modifications |
| checks.py | 85 | New file |
| **TOTAL** | **~273** | |

### Verdict on ~200 Line Estimate

The ~200 line estimate was **optimistic but in the right ballpark**. A more realistic estimate is **~270 lines** when you include the full Check protocol with 3 built-ins. If you scope v1 to just phase_guard + phase_state + generate_hooks changes (without the Check protocol), it's **~175 lines** — under 200.

**Recommendation:** Split into two PRs:
1. **PR1: Phase-aware guardrails** — phase_guard.py + phase_state.py + generate_hooks.py changes + R01 refactor = ~175 lines
2. **PR2: Check protocol** — checks.py with 3 built-ins = ~85 lines

PR1 is the infrastructure that both tutorials and team workflow need. PR2 is the verification layer that tutorials need.

---

## Ground-Truth Risks

### Risk 1: NFS Latency on phase_state.json Read

The codebase runs on a cluster (`.groups/spruston/home/`). NFS file reads in hooks add latency to every tool invocation. Current hooks read session markers (same NFS path). Measured overhead of session marker read: appears acceptable (system is in production use).

**Mitigation:** Only read `phase_state.json` if a rule has `scope.phase` set. For the current 5 rules, only R01 would have it. The other 4 hooks (bash_guard for R02-R04, write_guard for R05) never touch the phase file.

### Risk 2: Multiple Active Projects

`.ao_project_team/` can contain multiple projects. The "which one is active?" question has no clean answer today. STATUS.md tracks phase as a human-readable string ("Phase 3: Specification"), not a machine-readable integer.

**Mitigation:** `phase_state.json` is a NEW file. Only projects that explicitly create it have phase state. For v1, the Coordinator writes it at phase transitions. Projects without it (all existing projects) are unaffected.

### Risk 3: generate_hooks.py Test Coverage

The existing `test_framework.py` (931 lines) tests generated hooks via subprocess execution. Adding phase-scoped rules requires new test cases that:
1. Create a temp `phase_state.json`
2. Set phase to various values
3. Verify that phase-scoped rules fire/don't fire based on phase

**Estimate: ~30-40 additional test lines.** Follows the existing test pattern in `test_framework.py`.

### Risk 4: Backward Compatibility

Adding `scope:` to rules.yaml means older `generate_hooks.py` will ignore it (unknown field = silently skipped). This is the correct fail-safe — old generator produces un-scoped hooks (rules always fire). When the new generator processes it, rules become phase-scoped.

**No backward compatibility risk.** The scope field is purely additive.

---

## Summary

| Question | Answer | Confidence |
|----------|--------|------------|
| Can generate_hooks.py be extended without rewrite? | YES — follows existing role-gate pattern | High — read the actual code generation loop |
| Does hook stdin support phase state? | NO — must read file directly, same as session markers | High — stdin protocol is Claude Code's, not ours |
| Is atomic-write pattern reusable? | YES — copy-paste with field changes | High — read the actual save() method |
| Real cost of generate_hooks.py changes? | ~60 lines in a 2,155-line file, touching 4 functions | High — mapped every function's line range |
| Is ~200 lines realistic? | Close — ~175 for infra-only, ~270 with Check protocol | Medium — depends on scope of Check protocol |
