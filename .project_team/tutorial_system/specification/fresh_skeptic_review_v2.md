# Fresh Skeptic Review v2 — Final Architecture Line Count

## The Claim: ~200 Lines Core

Let me do the actual engineering. What files change, what files are new, and how many lines each.

---

## Component 1: Check Primitive

**New file: `checks/_types.py`**

```python
# CheckResult — frozen dataclass, 4 fields (passed, message, evidence, check_description)
# Check — Protocol with check() and description
```

That's ~25 lines. Comparable to `HintRecord` + `TriggerCondition` in hints/_types.py, which is ~40 lines for both.

**New file: `checks/_builtins.py`**

Three built-in checks:

```python
# CommandOutputCheck — run command, match regex on output
#   Fields: command, pattern, check_stderr, expected_exit_code
#   check(): ~15 lines (run command, match, build result)

# FileExistsCheck — check path exists
#   Fields: path
#   check(): ~8 lines

# ManualConfirm — ask user yes/no
#   Fields: question
#   check(): ~5 lines
```

Each check is a frozen dataclass with one method. Honest count:
- `CommandOutputCheck`: ~35 lines (with docstring, fields, description property, check method)
- `FileExistsCheck`: ~20 lines
- `ManualConfirm`: ~15 lines
- `_truncate` helper: ~5 lines
- Imports/module docstring: ~10 lines

**Total: ~85 lines.**

**New file: `checks/_context.py`**

```python
# CheckContext — frozen dataclass with run_command and file_exists callables
# CommandResult — frozen dataclass (exit_code, stdout, stderr)
# build_check_context() — factory that creates a sandboxed context
```

The factory is where real complexity lives. `run_command` needs:
- subprocess.run with timeout
- stdout/stderr capture
- output truncation (cap at 10KB)
- stdin closed (no interactive)

Honest count:
- `CommandResult`: ~5 lines
- `CheckContext`: ~15 lines
- `build_check_context()`: ~30 lines (subprocess wrapping, path expansion, timeout)
- Imports: ~5 lines

**Total: ~55 lines.**

**New file: `checks/__init__.py`**

Public API: just re-exports.

**Total: ~10 lines.**

### Check primitive subtotal: ~175 lines

That's already close to the 200 line budget and we haven't touched phase state yet. But it's honest — these are small, focused modules. For reference, hints/_types.py is 200 lines and hints/_engine.py is 178 lines. The check primitive is simpler than either.

---

## Component 2: Phase State

**New file: `phase_state.py`** (or integrated into an existing location)

```python
# PhaseState — read/write phase_state.json
#   Fields: current_phase (str), project_id (str | None)
#   Methods: get_phase(), set_phase(), load(), save()
```

This is a simple JSON file manager. Comparable to the activation section of `HintStateStore` (~50 lines of the 456-line file).

- `PhaseState` class: ~40 lines (load, save, get, set, atomic write)
- Phase state file path resolution: ~5 lines
- Imports/docstring: ~10 lines

**Total: ~55 lines.**

### Phase state subtotal: ~55 lines

---

## Component 3: Phase-Scoped Guardrails (the hard part)

This is where the 200-line claim breaks down. Let me count honestly.

**Modified file: `rules.yaml`** — Add `scope` field to R01

```yaml
- id: R01
  scope:
    not_phase: "project:5"
  # ... rest unchanged
```

~2 lines added. Trivial.

**Modified file: `generate_hooks.py`** — This is the 2,155-line code generator

Changes needed:
1. **Parse `scope` field from rules** — In the validation function. ~15 lines.
2. **Emit phase-checking code into generated hooks** — Each generated hook function (`generate_bash_guard`, `generate_write_guard`, etc.) needs to emit code that:
   - Reads the phase state file (or session marker)
   - Checks if the current phase matches the rule's scope
   - Skips the rule if out of scope

Let me look at how the generator currently emits per-rule code. Each rule becomes an `if re.search(...)` block in the generated hook. Adding phase scoping means wrapping that block in another `if`:

```python
# Generated code for a phase-scoped rule:
_current_phase = _phase_state.get('phase', '')
if _current_phase != 'project:5':  # not_phase check
    if re.search(r'pytest', command):
        _matched_rules.append(...)
```

Changes to the generator:
- Add phase state reading to the generated hook preamble: ~10 lines of generator code that emit ~5 lines of generated code
- Add scope-checking wrapper per scoped rule: ~20 lines of generator code (handling `phase`, `not_phase`, wildcard matching)
- Validation of scope field in `validate_rules()`: ~15 lines

But here's the hidden complexity: `generate_hooks.py` has **5 separate generator functions** (bash_guard, read_guard, glob_guard, write_guard, post_compact_injector). Each generates a different hook script. If phase scoping applies to any trigger type, **each generator function needs the same phase-checking code**. That's either duplication or a shared helper that all generators call.

Looking at the code: the generators are already heavily duplicated (each is 200-400 lines of string building). Adding phase scoping means adding it to each one.

Realistic count:
- Shared phase-reading preamble template: ~15 lines
- Per-generator scope emission (5 generators × ~10 lines each): ~50 lines
- Validation: ~15 lines
- Phase state file reading in generated hooks (emitted code): ~15 lines per hook

**Total changes to generate_hooks.py: ~80-100 lines.**

**Modified generated hooks** — Each regenerated hook gets ~10 additional lines for phase state reading + per-scoped-rule wrapping. This isn't code you write — it's code the generator produces. But it's complexity that exists at runtime.

**Modified session marker OR new phase state file** — The architecture says `phase_state.json` is separate from the session marker. The phase state writer (Coordinator or user) writes to this file. The generated hooks read it. Simple file I/O.

But: **Where does `phase_state.json` live?**
- If in `.ao_project_team/{project}/` — the generated hooks need to know the project name to find it. They don't currently.
- If in `.claude/guardrails/` — it's findable (hooks already know GUARDRAILS_DIR), but it's mixing concerns.
- If in `.claude/phase_state.json` — simple, findable, one per project.

This is a small decision but it matters for the hook code. The hooks run as standalone Python scripts invoked by Claude Code's hook protocol. They receive stdin JSON with `session_id`, `tool_input`, and `cwd`. They don't currently read any project state files. Adding file I/O to hooks introduces a failure mode (file missing, corrupt, permissions).

The existing hooks handle this for `hits.jsonl` (best-effort, try/except). Same pattern works for phase state. But it's real code.

### Phase-scoped guardrails subtotal: ~100-120 lines of changes + ~55 lines of phase_state.py = ~155-175 lines

---

## Component 4: First Pytest Tutorial

**New directory: `tutorials/content/first-pytest/`**

Files needed:
- `tutorial.yaml` — Manifest. Steps, verification config. ~40 lines of YAML.
- `step-01-create-test-file.md` — Write a test. ~30 lines of markdown.
- `step-02-run-pytest.md` — Run it. ~25 lines.
- `step-03-make-it-pass.md` — Fix the failing test. ~30 lines.

**Total content: ~125 lines** (YAML + markdown). Not code, but real work.

**Tutorial runner** — Something needs to orchestrate: load manifest → present step → run check → advance.

Options:
- **Agent role file only** (tutorial-runner.md that instructs the agent to follow the manifest): ~50 lines of markdown. The agent interprets the YAML and drives the flow. No Python engine.
- **Python engine** (_runner.py that loads YAML, manages state, exposes verify/advance functions): ~150-200 lines.

The "no Python engine" option is tempting but fragile — it relies on the agent correctly interpreting YAML, running checks, tracking progress. The agent can make mistakes. The whole point of this system is that verification is enforced, not voluntary.

A minimal Python engine:
- `load_manifest(path) → dict`: ~20 lines (YAML parsing + basic validation)
- `TutorialProgress` class: ~40 lines (current step, completed steps, persist to JSON)
- `run_check(step_config) → CheckResult`: ~15 lines (dispatch to CommandOutputCheck/FileExistsCheck)
- `advance(progress, check_result) → next step or error`: ~15 lines
- `format_step_context(step) → str`: ~20 lines (build the agent's context prompt)
- Entry point / CLI: ~30 lines

**Total engine: ~140-160 lines.**

### First Pytest tutorial subtotal: ~125 lines content + ~150 lines engine = ~275 lines

---

## Component 5: /check-setup Health Diagnostic

A command that runs verification checks against the project.

- Check definitions (is git configured? is pixi working? etc.): ~40 lines (5-6 CommandOutputCheck instances)
- Runner (iterate checks, collect results, format output): ~30 lines
- Integration as a command (CLI entry point or slash command): ~20 lines

**Total: ~90 lines.**

---

## Honest Total

| Component | New Lines | Changed Lines | Notes |
|---|---|---|---|
| Check primitive (types + builtins + context) | ~175 | 0 | Clean new code |
| Phase state (phase_state.py) | ~55 | 0 | Simple JSON store |
| Phase-scoped guardrails | 0 | ~100-120 | Changes to generate_hooks.py |
| Regenerated hooks | 0 | ~30 | Auto-generated, not hand-written |
| rules.yaml R01 refactor | 0 | ~3 | Trivial |
| Tutorial engine (_runner.py) | ~150 | 0 | Manifest loading, progress, orchestration |
| Tutorial content (first-pytest) | ~125 | 0 | YAML + markdown |
| /check-setup diagnostic | ~90 | 0 | Checks + runner + entry point |
| Tutorial-runner agent role | ~50 | 0 | Markdown role file |
| **TOTAL** | **~645 new** | **~150 changed** | **~795 total** |

### Tests

The existing guardrail system has a 931-line test framework. New tests needed:

- Check primitive tests (3 check types × ~3 tests each): ~100 lines
- Phase state tests: ~40 lines
- Phase-scoped guardrail tests (adapt existing test framework patterns): ~80 lines
- Tutorial engine tests (load, advance, verify): ~100 lines
- /check-setup tests: ~40 lines

**Test total: ~360 lines.**

### Grand total: ~1,150 lines (code + tests + content)

---

## Is "~200 Lines Core" Honest?

**The check primitive + phase state is ~230 lines. That's the "core" — and it's honest.** Two focused modules. Clean, testable, no dependencies on each other.

**But "core" doesn't ship.** You also need:
- generate_hooks.py changes (~120 lines) to make phase scoping do anything
- A tutorial engine (~150 lines) to make tutorials work
- Actual content (~125 lines) to have something to run
- A health check (~90 lines) to have a second consumer
- Tests (~360 lines) to know it works

The ~200 line core is the foundation. The ~800 lines of integration, consumers, and tests is what makes it real. That's a 4:1 ratio of "everything else" to "core."

**This is normal.** The hints system is 921 lines. The guardrail system is 2,930 lines. A new subsystem at ~1,150 lines is proportionate.

---

## Hidden Complexity

### HC1: generate_hooks.py is the riskiest change

This file is 2,155 lines of code generation. It builds Python scripts as strings. It's tested by a 931-line test framework. Changes to it can break all 5 existing guardrail rules.

Adding phase scoping means:
1. Every generated hook reads a phase state file (new I/O at hook runtime)
2. Every scoped rule gets a conditional wrapper (new logic in generated code)
3. The generator's validation function learns new fields
4. The generator's matrix display learns new fields

The test framework (`test_framework.py`) runs the generated hooks with mock stdin and checks exit codes. You'll need to extend it with phase state fixtures.

**Mitigation:** The changes are additive. Existing rules without `scope` are unaffected — the generator just skips scope emission for them. But you must verify this with the existing test suite before deploying.

**Estimated effort: 1-2 days** (careful, tested changes to a code generator).

### HC2: Tutorial engine is deceptively simple

The ~150-line engine loads YAML, tracks progress, and dispatches checks. That sounds simple. But:

- **YAML parsing errors** — What if the manifest is malformed? Need validation with clear error messages. Add ~30 lines.
- **Progress file corruption** — What if the JSON is truncated? Need atomic write + graceful fallback. The hints system's `HintStateStore` does this in ~50 lines. You'll duplicate that pattern.
- **Agent integration** — How does the engine communicate with the tutorial-runner agent? The agent is a Claude Code subagent. It runs in its own process. The engine either: (a) runs inside the agent's conversation (imported as Python), or (b) runs as an external command the agent calls. Option (a) is simpler but couples the engine to the agent runtime. Option (b) is cleaner but requires a CLI interface.

This isn't blocking, but "how does the agent invoke the engine?" is a design decision that needs to be made before implementation. The spec doesn't address it.

### HC3: /check-setup integration point

Where does `/check-setup` live? Options:
- A Claude Code slash command (`.claude/commands/check-setup.md`) — The command would instruct the agent to run checks. The agent imports the check module and runs them. Fits the existing pattern.
- A CLI command (`commands/check-setup`) — A standalone script the user runs. Doesn't need an agent. More accessible but less integrated.

For v1, the slash command is simpler: ~20 lines of markdown that tell the agent to run checks. The agent does the work.

### HC4: Phase state writer

Who writes `phase_state.json`? The architecture says "Coordinator or user, manually." Concretely:
- The Coordinator updates STATUS.md's "Current Phase" line by hand (editing the file). To also update `phase_state.json`, it needs to either: write the JSON file directly (simple but error-prone), or call a helper function/command.
- The user could run a slash command: `/set-phase 5`.

A helper function: `set_phase(phase: str, project: str | None = None)` — ~15 lines. A slash command that calls it — ~10 lines.

This is trivial but it must exist. Without it, phase_state.json never gets written and phase-scoped rules never activate.

---

## Is First Pytest Achievable with These Primitives?

Let me trace the whole flow:

1. **User starts tutorial.** How? A slash command: `/tutorial first-pytest`. The command instructs the agent to load the manifest and enter tutorial mode.

2. **Engine loads manifest.** `load_manifest("tutorials/content/first-pytest/tutorial.yaml")` → dict with steps. Each step has `file` (markdown path) and `verification` (check config).

3. **Engine presents step 1.** Reads `step-01-create-test-file.md`. Builds agent context: "Here's what to teach. Here's how it'll be verified." Agent presents the content to the user.

4. **User writes a test file.** The agent guides them. The user creates `tests/test_example.py`.

5. **Verification runs.** `FileExistsCheck(path="tests/test_example.py").check(ctx)` → `CheckResult(passed=True, evidence="file exists")`.

6. **Engine advances to step 2.** User reads step 2 content. Runs `pytest tests/test_example.py`.

7. **Verification runs.** `CommandOutputCheck(command="pytest tests/test_example.py", pattern="passed|failed")` → Shows test output.

8. **Step 3: Make it pass.** User edits test. Verification: `CommandOutputCheck(command="pytest tests/test_example.py", pattern="\\d+ passed")`.

9. **Tutorial complete.** Engine marks completion in progress JSON.

**Does this work with just the primitives?**

- `CommandOutputCheck` ✅ — runs pytest, checks output
- `FileExistsCheck` ✅ — checks test file exists
- Phase state ✅ — tutorial sets phase to `tutorial:first-pytest:step-01`
- Guardrail scoping ✅ — R01 (pytest block) could be exempted during tutorial (though for a single-file pytest run, R01's exclude pattern already allows it: `\bpytest\b[^\n]*\btests/\w+\.py\b`)

**Wait.** R01 already exempts single-file pytest runs. So the First Pytest tutorial doesn't actually need phase-scoped guardrails. The user runs `pytest tests/test_example.py`, which is allowed by R01's existing exclude pattern.

This is fine — it means the tutorial works without phase scoping. Phase scoping is validated by the R01 refactor (exempting full-suite pytest in phase 5), not by the tutorial itself. The two consumers validate different parts of the infrastructure:
- Tutorial validates: Check primitive + progress tracking + engine
- R01 refactor validates: Phase state + phase-scoped guardrails

**Good. The consumers are orthogonal.** Neither is redundant.

### What's missing for First Pytest?

One thing: **ManualConfirm isn't needed for this tutorial.** All three steps are machine-verifiable (file exists, pytest output). ManualConfirm can be deferred — it's only needed for tutorials with external actions (GitHub email links, etc.).

Revised: v1 needs only `CommandOutputCheck` + `FileExistsCheck`. Two check types, not three.

---

## What Fails First?

In order of likelihood:

### 1. generate_hooks.py regression (HIGH probability, MEDIUM severity)

The code generator is complex and fragile (string-building Python that generates Python). Any mistake in the phase-scoping emission produces hooks that either crash or silently skip rules. The existing test framework catches regressions, but only for the cases it covers.

**Mitigation:** Run the full test framework after every change to generate_hooks.py. Add phase-scoping test cases before changing the generator.

### 2. Tutorial YAML validation gap (MEDIUM probability, LOW severity)

The tutorial engine loads YAML. If a step references a verification type that doesn't exist, or a file path that doesn't exist, the error surfaces at runtime — mid-tutorial. The user's experience: "Step 2 crashed."

**Mitigation:** Validate the manifest at load time, not at step execution time. Check: all step files exist, all verification types are known, all required params are present. ~30 lines of validation code.

### 3. Phase state file not found (MEDIUM probability, LOW severity)

Generated hooks try to read `phase_state.json`. In solo mode (no team, no tutorial), this file doesn't exist. The hook must handle this gracefully — default to "no phase" which means unscoped rules fire normally and phase-scoped rules are skipped.

**Mitigation:** Existing pattern: `try: read file / except: default`. Already done for session markers. Same code.

### 4. Agent doesn't follow tutorial engine instructions (LOW probability, MEDIUM severity)

The tutorial-runner agent receives context from the engine but executes autonomously. It might skip steps, run checks itself, or fail to call the engine's advance function.

**Mitigation:** The agent role file (tutorial-runner.md) must be precise. And the checkpoint guardrail ensures the agent can't claim a step is done without verification passing. This is the existing design and it works — as long as the guardrail is active.

---

## Revised Recommendation

| Aspect | Verdict |
|---|---|
| "~200 lines core" | **Honest** — check primitive (~175) + phase state (~55) = ~230 lines. The core is real. |
| Total implementation | **~800 lines code + ~360 lines tests = ~1,150 total.** Not 200. But proportionate to existing subsystems. |
| Over-engineering | **No.** This is the right scope. Two primitives, two consumers, one tutorial. Nothing superfluous. |
| Achievable timeline | **5-8 working days** for a developer who knows the codebase. 2 days for generate_hooks.py (riskiest), 1 day for check primitive, 1 day for tutorial engine + content, 1-2 days for tests, 1 day for integration. |
| What to cut | Drop `ManualConfirm` from v1 (First Pytest doesn't need it). That's 15 lines saved — barely matters, but it's one fewer thing to test. |
| What fails first | generate_hooks.py regression. Mitigate with test-first development. |

**The architecture is right.** The 200-line claim is honest for the core primitives but misleading for total effort. ~1,150 lines including tests and consumers is the real number. That's fine — it's proportionate and everything serves a purpose. Ship it.
