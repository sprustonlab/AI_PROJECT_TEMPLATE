# Improvement Review: Researcher (Codebase Perspective)

**Author:** Researcher
**Date:** 2026-04-04
**Scope:** Does the spec match how the codebase actually works? What existing patterns does it ignore or contradict?

---

## 1. `CheckContext` vs `ProjectState` — Parallel Context Bags With No Reuse Story

**The problem:** The spec introduces `CheckContext` with methods `file_exists()`, `read_file()`, `run_command()`, `ask_user()`. But `ProjectState` already provides `path_exists()`, `file_contains()`, `count_files_matching()`, `dir_is_empty()`. These are semantically overlapping but structurally independent.

**What the codebase actually does:** `ProjectState` is a frozen dataclass built via `ProjectState.build(project_root, **kwargs)` that loads `CopierAnswers` from disk. Every `TriggerCondition.check()` receives it. It's the established "read-only context bag" pattern.

**Risk:** Two parallel context bags means two places to add filesystem helpers, two patterns for tests to mock, and eventual drift. The spec even acknowledges the parallel on line 102 ("same pattern as the existing hints system") but doesn't resolve it.

**Recommendation:** The spec should explicitly state the relationship:
- Option A: `CheckContext` wraps/delegates to `ProjectState` (extending, not duplicating)
- Option B: `CheckContext` is intentionally independent because Checks must work without the hints system (the `/check-setup` standalone case)
- If B, state this explicitly and note that common filesystem helpers should live in a shared utility, not be duplicated

---

## 2. `ProjectState.active_phase` — Loading Mechanism Unspecified

**The problem:** The spec adds `active_phase: ActivePhase | None = None` to `ProjectState` (Section 3.4), but `ProjectState` is frozen and built via `ProjectState.build()` (line 173 of `_state.py`). The `build()` method currently loads `CopierAnswers` and forwards `session_count` from kwargs.

**What must happen:** `build()` needs to read `phase_state.json` to populate `active_phase`. But the spec says discovery is via `PHASE_STATE_PATH` environment variable. The hints system discovers everything via `project_root` — there is no env var pattern in the hints code.

**Inconsistency:** Three different discovery mechanisms now exist:
1. Hints state: `project_root / ".claude/hints_state.json"` (hardcoded relative path)
2. Guardrails: `GUARDRAILS_DIR` env var
3. Phase state: `PHASE_STATE_PATH` env var (spec proposal)

**Recommendation:** Specify exactly how `ProjectState.build()` discovers and loads `phase_state.json`. Preferred: follow the hints pattern (relative to `project_root`) with env var as override. E.g., `project_root / ".ao_project_team/phase_state.json"` by default, `PHASE_STATE_PATH` for testing/override.

---

## 3. Tutorial YAML Hints Break the Existing Python Hint Pattern

**The problem:** The spec introduces YAML-declared hints in `tutorial.yaml`:

```yaml
hints:
  - message: "Create tests/test_example.py..."
    trigger: { type: phase-stuck, threshold_seconds: 120 }
```

But the existing hint system is entirely Python-based. `run_pipeline()` takes `Sequence[HintSpec]`, where each `HintSpec` contains a Python `TriggerCondition` object and a `HintLifecycle` object. There is no YAML→HintSpec deserialization path.

**What must be built (but isn't specified):** A YAML hint deserializer that:
1. Maps `trigger.type: "phase-stuck"` → `PhaseStuck(threshold_seconds=120)` Python object
2. Maps `lifecycle: "show-once"` → `ShowOnce()` Python object
3. Maps inline `message` strings → `HintSpec.message`
4. Feeds the results into `run_pipeline()` alongside the Python-defined hints

**This is a non-trivial integration point** — it's effectively a second hint registry (YAML) alongside the existing one (Python). The spec should define:
- The trigger type registry for YAML hints (analogous to `CHECK_REGISTRY`)
- How YAML hints merge with Python hints in the pipeline
- Whether `get_hints()` returns both, or a higher-level function merges them

---

## 4. Undefined Trigger Classes: `PhaseStuck` and `PhaseCheckFailed`

**The problem:** The spec uses `phase-stuck` and `phase-check-failed` as trigger types in tutorial YAML examples (Sections 2.2, 7.5) but never defines the corresponding Python classes.

`PhaseIs` is fully defined (Section 3.4). But:
- `PhaseStuck` — needs `phase_entered_at` from `ActivePhase` + current time. How does a trigger access the clock? `TriggerCondition.check()` receives `ProjectState`, not a clock. `ProjectState` is frozen — no `time.time()` access.
- `PhaseCheckFailed` — needs `last_check_result` from `ActivePhase`. But when is `last_check_result` set? By the engine after a failed gate? The spec doesn't define the write path.

**Recommendation:** Either:
- Define these classes in the spec (preferred — they're v1 if tutorials are v1)
- Explicitly defer them to v2 and remove them from v1 examples

---

## 5. `show-until-phase-complete` Lifecycle — Used in v1 Example, Deferred to v2

**The problem:** Section 7.2 (SSH tutorial example) uses `lifecycle: show-until-phase-complete`. Section 9 (V2 Scope) lists "Phase-aware hint lifecycles: `ShowUntilPhaseComplete`" as future work.

**Contradiction:** You can't use it in a v1 example if it's v2 scope.

**Recommendation:** Either move it to v1 scope (it's ~15 lines: check if `active_phase.phase_id` has changed since hint was registered) or replace the v1 example with `show-once`.

---

## 6. The COORDINATOR.md Split — Mechanism for Phase File Delivery is Unspecified

**The problem:** The spec says "Agent prompt = COORDINATOR.md (who you are) + current phase markdown (what to do now)" but doesn't explain *how* this concatenation happens.

**What the codebase actually does:** The `ao_project_team.md` command in `.claude/commands/` launches the Coordinator. Role files are read by agents at spawn. There is no existing mechanism to inject a second file into an agent's prompt mid-session.

**The hard question:** When the workflow engine transitions from Phase 4 → Phase 5:
1. Who delivers `phase-05-testing.md` to the Coordinator agent?
2. Is it appended to the conversation? Read by the agent explicitly? Injected via a hook?
3. The Coordinator is already running — you can't re-spawn it with a different role file.

**This is the hardest integration point in the entire spec.** The spec should define the delivery mechanism. Options:
- A: Engine writes current phase file path to `phase_state.json`; Coordinator reads it at each transition (agent-driven)
- B: A SessionStart hook injects the current phase file content (hook-driven)
- C: `tell_agent` sends the phase content to Coordinator (message-driven)

---

## 7. `AI_agents` → `teams` Rename — Blast Radius Underestimated

**The problem:** The spec casually mentions "Directory rename: `AI_agents` → `teams`" in Section 10.1 (Resolved Decisions) and Section 5.3. But this rename touches:

- `.claude/commands/ao_project_team.md` (references `AI_agents/project_team/`)
- Every role file that references paths (COORDINATOR.md, IMPLEMENTER.md, etc.)
- `ProjectTeamNeverUsed` trigger in `hints/hints.py` (checks `.ao_project_team`)
- Any existing `.ao_project_team/` execution state directories
- Tests that reference these paths
- Documentation (README.md, etc.)

**This is not a "during implementation" task — it's a migration.** The spec should either:
- Scope it as a separate pre-implementation step with its own checklist
- Defer it entirely (the spec works fine with `AI_agents/project_team/phases.yaml`)

**Recommendation:** Defer the rename. It adds risk and zero functional value for v1. The directory name doesn't affect the architecture.

---

## 8. `generate_hooks.py` Changes — PyYAML Dependency for Manifest Parsing

**The problem:** The spec says `generate_hooks.py` will parse `phases.yaml` and `tutorial.yaml` manifests to build the phase registry. But `generate_hooks.py` line 86 shows it already handles PyYAML as an optional dependency with a fallback error.

**What this means:** If `generate_hooks.py` needs to parse YAML manifests, PyYAML becomes a hard requirement for hook generation. Currently it's already effectively required (the fallback is `SystemExit`). This is fine, but worth noting.

**More importantly:** The spec says `generate_hooks.py` should "read manifest files, extract phase IDs, build the registry." But the existing code structure generates *self-contained* hook scripts with all rule logic baked in. Phase IDs need to be baked in too (as `KNOWN_PHASES` set). This means:
- Every time you add a phase to a manifest, you must re-run `generate_hooks.py`
- The `--check` mode must also validate phase references
- The `--matrix` mode should show phase scoping

The spec mentions this but should be more explicit about the regeneration workflow.

---

## 9. Role Guard + Phase Guard Composition — Evaluation Order Unspecified

**The problem:** Currently, generated hooks call `role_guard.check_role()` to evaluate `block: [Subagent]`. The spec adds `phase_guard.should_skip_rule()` for `phase_block`/`phase_allow`. Both are called from generated hooks.

**What happens when both apply?** R01 has `phase_block: [testing]` and could conceivably also have `block: [Subagent]`. Does role check happen first? Phase check first? Either? Does it matter?

**It matters for logging.** If the phase guard skips R01 (phase = testing), but role guard would also skip it (Coordinator), what gets logged? The spec should define evaluation order:

```python
# Recommended: short-circuit with phase first (cheaper — file read vs marker lookup)
if should_skip_rule(rule_id, phase_block, phase_allow):
    return  # Skip — phase exemption
if not check_role(allow, block, enforcement):
    return  # Skip — role exemption
# ... evaluate rule
```

---

## 10. Existing Code Reuse Opportunities the Spec Doesn't Mention

### 10a. `HintStateStore.save()` as template for `phase_state.json` writes

The atomic write pattern (temp-then-rename, same-directory, cleanup-on-failure) at `_state.py:348-385` is exactly what `workflow/_state.py` needs. The spec should cite it as the reference implementation.

### 10b. `ActivationConfig` pattern for phase activation

`ActivationConfig` wraps `HintStateStore` to provide a boolean filter ("is this hint active?"). A similar `PhaseActivation` could wrap phase state to answer "is this phase active?" — same delegation pattern.

### 10c. Combinator triggers (`AllOf`, `AnyOf`, `Not`) for phase triggers

The existing combinators in `hints/hints.py` (lines 209-250) could compose with `PhaseIs` to create complex conditions like "PhaseIs(implementation) AND NOT GuardrailsOnlyDefault()". The spec doesn't mention this composability, but it's free.

### 10d. `CopierAnswers` for tutorial feature flag

A `use_tutorials` feature flag in `.copier-answers.yml` would follow the existing pattern (`use_guardrails`, `use_project_team`, `use_pattern_miner`, `use_cluster`, `use_hints`). The spec doesn't mention this but should — tutorials should be opt-in via the same mechanism.

---

## 11. `/check-setup` Entry Point — Simpler Than Spec Implies

**The problem:** The spec lists `/check-setup` entry point as an open decision (Section 10.2). But the answer is obvious from the codebase: it's a `.claude/commands/check_setup.md` file, following the exact pattern of `.claude/commands/ao_project_team.md` and `.claude/commands/init_project.md`.

**Recommendation:** Close this decision in the spec. It's a ~20-line command file that imports and runs checks. No CLI script needed.

---

## 12. Test Infrastructure — `test_framework.py` Is Reusable

The guardrails already have `test_framework.py` for testing rules. The spec's test plan (~360 lines) doesn't mention whether Check tests should reuse this framework or build a parallel one.

**Recommendation:** Check primitive tests should follow the existing test patterns in `tests/test_hints.py` and `tests/test_hints_e2e.py`. Guardrail-specific tests (phase_guard, generate_hooks changes) should use `test_framework.py`.

---

## Summary: Top 5 Risks (Ordered by Integration Difficulty)

| # | Risk | Why It's Hard | Spec Gap |
|---|------|---------------|----------|
| 1 | **Phase file delivery to running Coordinator** | No existing mechanism to inject content into a running agent mid-session | Mechanism unspecified (Section 6) |
| 2 | **YAML hints → HintSpec deserialization** | Creates a second hint declaration format with no existing bridge code | Deserializer not designed (Section 3 above) |
| 3 | **`generate_hooks.py` manifest parsing + phase baking** | Riskiest file in the codebase; 700+ lines of code generation | Regeneration workflow underspecified (Section 8) |
| 4 | **`PhaseStuck` trigger needs clock access** | `TriggerCondition.check()` protocol has no clock parameter; `ProjectState` is frozen | Trigger class undefined (Section 4) |
| 5 | **`AI_agents` → `teams` rename** | Large blast radius, zero functional value for v1 | Underestimated scope (Section 7) |
