# Fresh Composability Review v2: Final Architecture

**Reviewer:** Composability (Lead Architect)
**Scope:** Unified phase model, 2 primitives (Check + Phase), v1 scope, ~200 lines core
**Method:** Fresh read of all 23 specification files, review against composability principles

---

## 1. The Two Primitives

### Primitive 1: Check

```
Check protocol: check(ctx: CheckContext) → CheckResult
CheckContext: sandboxed system access (run_command, read_file, file_exists, ask_user)
CheckResult: passed + message + evidence
Built-ins: CommandOutputCheck, FileExistsCheck, ManualConfirm
```

### Primitive 2: Phase

```
Phase: named state with 3 facets
  guards:  activate_rules + deactivate_rules
  gates:   advance_checks (list of Checks)
  context: hints (list of HintDeclarations)

Workflow: ordered sequence of Phases
ActivePhase: runtime state (workflow_id, phase_id, entered_at, completed, last_check)
phase_state.json: persistent, project-scoped
```

### Key decisions reviewed:
- Session markers (WHO, ephemeral, PID-scoped) and phase state (WHAT stage, persistent, project-scoped) are SEPARATE ✅
- Phase transitions are NOT automated in v1 — Coordinator/user sets phases, hooks read state ✅
- "Step" demoted to sub-phase (instructions within a phase's content) ✅
- ConfigValueCheck dropped — it's CommandOutputCheck with `git config X` as the command ✅

---

## 2. Cross-Primitive Coherence

### Check ↔ Phase: CLEAN ✅

The relationship is one-directional: Phase references Check, Check doesn't know about Phase.

```
Phase.advance_checks: tuple[Check, ...]
    │
    ▼
Check.check(ctx) → CheckResult
```

**Swap test:** Can I use a Check without a Phase? Yes — the `/check-setup` health diagnostic does exactly this. Standalone checks, no workflow, no phase.

**Swap test:** Can I use a Phase without a Check? Yes — a phase with `advance_checks = ()` is valid. Guards and context still work. The Coordinator manually advances it.

**Verdict:** Clean separation. Neither primitive depends on the other's existence. Phase optionally references Check as a building block.

### Phase ↔ Guardrails: CLEAN ✅

The seam is `phase_state.json` — a file the workflow engine writes and guardrail hooks read.

```
WorkflowEngine                    phase_state.json                    phase_guard.py
(writes on transition)  ────►    {current_phase, ...}    ◄────    (reads at hook runtime)
```

**No import coupling.** The workflow engine writes JSON. The guardrail hook reads JSON. They share a file format, not code. This mirrors the existing session marker pattern (`setup_ao_mode.sh` writes, `role_guard.py` reads).

**Swap test:** Can I change the workflow engine without touching guardrails? Yes — as long as `phase_state.json` format is preserved.

**Swap test:** Can I change the guardrail enforcement without touching the workflow engine? Yes — `phase_guard.py` logic is independent.

### Phase ↔ Hints: CLEAN ✅

The seam is `ProjectState.active_phase: ActivePhase | None`.

```
WorkflowEngine                    ProjectState                    PhaseActive trigger
(builds ActivePhase)   ────►    .active_phase     ◄────    .check(state) → bool
```

**Swap test:** Can I change how phases work without touching the hints system? Yes — hints just read `active_phase.phase_id` from `ProjectState`. They don't know how the workflow engine manages transitions.

### Check ↔ Hints: NO DIRECT RELATIONSHIP ✅

Checks and hints don't interact. A hint trigger might semantically care about whether a check passed (via `ActivePhase.last_check_result`), but it reads that through `ProjectState`, not through the Check system directly. Clean.

### Check ↔ Guardrails: NO DIRECT RELATIONSHIP ✅

Checks don't interact with guardrails. The phase is the intermediary — a phase's guards are rule IDs, not checks. A phase's gates are checks, not guardrail rules. The two systems are connected through the phase, not through each other.

---

## 3. Seam Leakage Audit

### 3.1 `phase_state.json` — is the format a leaky seam?

The workflow engine writes it. Guardrail hooks read it. If the format changes, both must update.

**Risk:** Medium. But this is the same risk as the session marker (`ao_<PID>` JSON), which has been stable. Mitigations:
- `version` field in the JSON (already proposed)
- Format is minimal: `{version, workflow_id, phase_id, updated_at}`
- Hooks fail-open on missing/corrupt file (no phase scoping = rules follow defaults)

**Verdict:** Acceptable. Same pattern as existing session markers. Not a leak — it's a shared contract.

### 3.2 `ActivePhase` on `ProjectState` — seam leak?

This was flagged in the v1 review as `TutorialContext` coupling. The generalization to `ActivePhase` improves it:

- `ActivePhase` is a frozen dataclass with primitive fields (`str`, `float`, `frozenset[str]`)
- Only field that references another type: `last_check_result: CheckResult | None`
- `CheckResult` is a frozen dataclass with only primitive fields (`bool`, `str`, `str | None`, `tuple`)

**Where should `ActivePhase` and `CheckResult` be defined?**

The previous review recommended a shared types module. With the simplified 2-primitive model:

- `CheckResult` belongs in `checks/_types.py` (it's a Check primitive)
- `ActivePhase` belongs in `workflow/_types.py` (it's a Phase primitive)
- `ProjectState` in `hints/_state.py` imports `ActivePhase` from `workflow/_types.py`

This creates a dependency: `hints` → `workflow` (for the `ActivePhase` type). Is this a leak?

**Analysis:** It's a one-directional, type-only dependency. `hints/_state.py` imports the frozen dataclass definition but never calls workflow engine methods. The hints system doesn't depend on workflow behavior — it only reads a data snapshot.

**Alternative:** Define `ActivePhase` in a shared module (e.g., `_shared_types.py` at template root). Both `hints` and `workflow` import from shared. Neither depends on the other.

**Recommendation:** Use the shared module approach. It's cleaner and avoids any directional coupling. But honestly, either approach works — this is a LOW severity concern. The existing `ProjectState` already imports `CopierAnswers` from the same module, so the pattern of `ProjectState` referencing domain types is established.

### 3.3 `agent_blocked_commands` — previously identified leak

Previous review flagged this as Content ↔ Safety coupling. Status update:

With the unified phase model, this becomes a Phase concern. A phase declares its `activate_rules`. If the tutorial-runner agent needs to be blocked from certain commands, that's a guardrail rule scoped to the tutorial phase. The content manifest references rule IDs, not command patterns directly.

**But:** Someone still has to write those rules in `rules.yaml`. Who? The tutorial author? The infrastructure maintainer?

**Practical answer:** For v1, there's ONE tutorial ("First Pytest"). The rule set is small and hand-maintained. The auto-derivation concern from the v1 review is deferred — it's a v2 convenience, not a v1 necessity.

**Verdict:** Not a leak in v1. The phase references rule IDs. Rules live in `rules.yaml`. Separation is clean.

### 3.4 Phase transition authority — who writes `phase_state.json`?

The Skeptic identified this clearly: "If agents write it, it's trust-based. If a phase engine writes it, you need to build a phase engine."

**v1 decision:** Coordinator/user sets phases manually. No automated enforcement.

**Composability concern:** If the Coordinator writes `phase_state.json` directly, the phase state is effectively a suggestion, not an enforcement. A misbehaving agent could write `phase_id: "testing"` to bypass implementation-phase guardrails.

**But:** This is the SAME trust model as the existing system. The Coordinator writes `STATUS.md` with the current phase. Agents follow it by convention. The session marker is written by `setup_ao_mode.sh`, not by a verification engine. Trust-based phase transitions are consistent with how the template already works.

**Verdict:** Acceptable for v1. The composability principle holds — the seam is clean even if enforcement is trust-based. Adding programmatic enforcement later is incremental (the phase_state.json format supports it without changes).

---

## 4. Crystal Integrity

### The v1 Crystal

Two axes, each with values:

**Check axis:**
- CommandOutputCheck
- FileExistsCheck
- ManualConfirm

**Phase axis:**
- Project-team phase (manual transitions, R01 scoping)
- Tutorial phase (checkpoint-gated, tutorial rules)
- No-phase (standalone checks, default guardrails)

### 10-Point Crystal Test

| Check | Phase Context | Use Case | Works? |
|---|---|---|---|
| CommandOutputCheck | Project-team Phase 5 | "Did pytest pass?" | ✅ |
| FileExistsCheck | Tutorial: generate-key | "Does SSH key exist?" | ✅ |
| ManualConfirm | Project-team Phase 0 | "User approved vision?" | ✅ |
| CommandOutputCheck | No-phase | `/check-setup` health diagnostic | ✅ |
| FileExistsCheck | No-phase | Standalone file check | ✅ |
| ManualConfirm | Tutorial: verify-email | "Clicked GitHub email link?" | ✅ |
| CommandOutputCheck | Tutorial: test-connection | "SSH works?" | ✅ |
| FileExistsCheck | Project-team Phase 1 | "STATUS.md created?" | ✅ |
| CompoundCheck* | Tutorial: full-setup | SSH key + connection both work | ⚠️ |
| ManualConfirm | No-phase | Standalone user confirmation | ✅ |

*CompoundCheck: Not in the v1 built-ins (only 3: CommandOutput, FileExists, ManualConfirm). If needed, it's a v2 addition. No crystal hole — just a feature not yet built.

**Result: No holes in the v1 crystal.** All combinations of Check × Phase-context work.

---

## 5. Things That Compose Well

### 5.1 R01 refactoring as proof-of-concept

The plan to refactor R01 (pytest-output-block) with `scope.phase` is the perfect v1 validation:

```yaml
- id: R01
  name: pytest-output-block
  trigger: PreToolUse/Bash
  enforcement: deny
  scope:
    not_phase: ["testing"]    # Exempt during testing phase
  detect:
    type: regex_match
    pattern: '(?:^|&&|\|\||;|\brun\s+)\s*pytest\b'
  message: "..."
```

This exercises the full chain: `rules.yaml` → `generate_hooks.py` → `phase_guard.py` → `phase_state.json`. One rule change validates the entire infrastructure.

### 5.2 `/check-setup` health diagnostic

Standalone check usage (no phase) validates that checks are truly independent:

```python
checks = [
    FileExistsCheck("~/.ssh/id_ed25519"),
    CommandOutputCheck("git config user.email", r".+@.+"),
    CommandOutputCheck("pixi --version", r"pixi \d+"),
]
for check in checks:
    result = check.check(ctx)
    print(f"{'✓' if result.passed else '✗'} {result.message}")
```

No workflow, no phase, no guardrails. Just checks. This proves the Check primitive is genuinely independent.

### 5.3 "First Pytest" tutorial consuming both primitives

The tutorial consumes phases AND checks through the same infrastructure that R01 uses:

```yaml
# Tutorial as a sequence of phases
phases:
  - id: write-test
    description: "Write your first test file"
    advance_checks:
      - type: file-exists-check
        path: "tests/test_example.py"
    hints:
      - message: "Create a file tests/test_example.py with a function starting with test_"
        trigger: { type: phase-stuck, threshold_seconds: 120 }

  - id: run-test
    description: "Run pytest and see it pass"
    deactivate_rules: [R01]     # Allow free pytest during this tutorial phase
    advance_checks:
      - type: command-output-check
        command: "pixi run pytest tests/test_example.py"
        pattern: "passed"
    hints:
      - message: "Run: pixi run pytest tests/test_example.py"
        trigger: { type: phase-check-failed }
```

The tutorial uses the same `deactivate_rules` mechanism as the R01 refactoring, the same check types as `/check-setup`, and the same phase model as the project team. One infrastructure, three consumers.

---

## 6. Things That Don't Compose (or Are Unnecessary)

### 6.1 CompoundCheck — UNNECESSARY for v1 ❌

The v1 scope lists 3 built-in checks: CommandOutput, FileExists, ManualConfirm. The previous axis_verification.md spec designed `CompoundCheck` (AND/OR composition of sub-checks).

**For v1, CompoundCheck adds complexity without a consumer.** The "First Pytest" tutorial needs only FileExistsCheck and CommandOutputCheck. The R01 refactoring needs no checks at all (it's a phase scope change). `/check-setup` runs checks sequentially and reports results — no compound logic needed.

**Recommendation:** Confirmed: defer CompoundCheck. If a v2 tutorial needs "SSH key exists AND connection works," it's easy to add. The Check protocol supports it by construction — CompoundCheck is just another Check implementation.

### 6.2 ConfigValueCheck — UNNECESSARY, correctly dropped ✅

ConfigValueCheck was `command + pattern` for config values. CommandOutputCheck already does this: `CommandOutputCheck(command="git config user.email", pattern=".+@.+")`. Correct to drop.

### 6.3 Phase branching — NOT IN V1, correctly deferred ✅

Branching progression was never fully specified and is deferred. V1 phases are linear only. Correct.

### 6.4 Automated phase transitions — NOT IN V1, correctly deferred ✅

The Coordinator sets phases manually. No programmatic enforcement of transitions. This is trust-based and consistent with the existing system. Adding enforcement later is incremental.

### 6.5 Parallel phase spaces — NOT IN V1, correctly deferred ✅

Can't run a tutorial during a project phase. Mutually exclusive. The `phase_state.json` format could accommodate parallelism later (`workflow_id` field distinguishes phase spaces), but v1 doesn't need it.

---

## 7. What's Missing

### 7.1 Phase ID naming convention — NEEDED

The specs mention phase IDs in different formats:
- Project-team: integer (`3`, `4`, `5`) per COORDINATOR.md
- Tutorial: string slug (`generate-key`, `copy-key`) per tutorial manifest
- Skeptic proposed: namespaced (`project:4`, `tutorial:ssh-cluster:step-02`)

The `scope.not_phase` field on rules needs to match against phase IDs. If R01 says `not_phase: ["testing"]` and the phase_state says `phase_id: "5"`, they don't match.

**Recommendation:** Phase IDs are strings. Project-team phases use string labels: `"specification"`, `"implementation"`, `"testing"`. The COORDINATOR.md numbering (Phase 0–9) is human-facing; the machine-facing ID is the label. Tutorial phases use their step slugs: `"generate-key"`, `"run-test"`.

The `workflow_id` field distinguishes phase spaces: `workflow_id: "project-team"` vs `workflow_id: "first-pytest-tutorial"`. Rules scope on either or both:

```yaml
scope:
  not_phase: ["testing"]                # Matches any workflow in a "testing" phase
scope:
  workflow: "first-pytest-tutorial"     # Matches any phase of this tutorial
scope:
  phase: "implementation"
  workflow: "project-team"              # Specific workflow + phase
```

This is necessary before implementation. Without it, the R01 refactoring can't be written.

### 7.2 `phase_guard.py` discovery of `phase_state.json` — NEEDED

Generated hooks need to find `phase_state.json`. Where do they look?

Options:
- (a) Fixed path: `.ao_project_team/*/phase_state.json` — glob for active projects
- (b) Environment variable: `PHASE_STATE_PATH` set by the workflow engine
- (c) Convention: `phase_guard.py` reads from a symlink or pointer file

**Recommendation:** Option (b). The workflow engine (or setup script) sets `PHASE_STATE_PATH` as an environment variable. Guardrail hooks check `os.environ.get('PHASE_STATE_PATH')`. If unset, no phase scoping (fail-open, consistent with how `CLAUDE_AGENT_ROLE` works).

This is ONE environment variable. The workflow engine sets it when activating a workflow. The hooks read it. Clean.

### 7.3 YAML-to-Check deserialization — NEEDED

Tutorial manifests and any future workflow definition declare checks as YAML:

```yaml
advance_checks:
  - type: command-output-check
    command: "pixi run pytest tests/test_example.py"
    pattern: "passed"
```

The engine needs a registry to deserialize `type` → Check class:

```python
CHECK_REGISTRY: dict[str, type[Check]] = {
    "command-output-check": CommandOutputCheck,
    "file-exists-check": FileExistsCheck,
    "manual-confirm": ManualConfirm,
}
```

This is simple (< 20 lines) but must exist before any YAML-defined workflow can use checks. The naming convention should be hyphens in YAML (idiomatic YAML), and the registry normalizes to match class names.

---

## 8. Line Count Sanity Check

The Coordinator said ~200 lines core. Let me estimate:

| Component | Estimated Lines | Notes |
|---|---|---|
| `checks/_types.py` | ~40 | Check protocol, CheckContext, CheckResult, CommandResult |
| `checks/_builtins.py` | ~80 | CommandOutputCheck, FileExistsCheck, ManualConfirm |
| `checks/_registry.py` | ~15 | YAML type → class mapping |
| `workflow/_types.py` | ~30 | Phase, Workflow, ActivePhase |
| `workflow/_state.py` | ~40 | Read/write phase_state.json (atomic, versioned) |
| `phase_guard.py` | ~30 | Read phase_state.json, check phase scope |
| `generate_hooks.py` changes | ~40 | Emit phase_guard calls for scoped rules |
| `rules.yaml` R01 change | ~5 | Add scope.not_phase |
| **Total** | **~280** | |

Slightly over 200, but not significantly. The core primitives (Check + Phase types) are ~70 lines. The implementations + plumbing bring it to ~280. Reasonable for v1.

The `/check-setup` command and "First Pytest" tutorial are consumers that add more, but they're not core infrastructure.

---

## 9. Verdict

### What composes well:
- **Check as independent building block** — usable standalone (health checks), in phases (gate checks), or by agents (task verification). No coupling to phase or guardrails.
- **Phase as the organizer** — three facets (guards, gates, context) managed as one concept. Phase transition is one atomic operation, not three systems coordinating.
- **phase_state.json as the seam** — written by workflow engine, read by guardrail hooks. Same pattern as session markers. No code coupling.
- **R01 refactoring as proof** — one rule change validates the full infrastructure chain.
- **Two consumers proving generality** — R01 (project-team) and First Pytest tutorial (tutorial) use the same primitives differently.

### What needs attention before implementation:
1. **Phase ID convention** — must be defined (string labels, workflow_id namespacing, scope matching rules)
2. **phase_state.json discovery** — environment variable `PHASE_STATE_PATH` (simple, consistent with existing patterns)
3. **Check registry** — YAML type-to-class mapping (~15 lines but must exist)

### What's correctly omitted:
- CompoundCheck (no v1 consumer)
- ConfigValueCheck (subsumed by CommandOutputCheck)
- Automated phase transitions (trust-based is consistent with existing system)
- Branching progression (underspecified, no v1 need)
- Parallel phase spaces (mutually exclusive in v1)

### Composability assessment:

**The Step Protocol law from the original composability analysis is superseded by a simpler law:** All checks produce `CheckResult`. All phase consumers read `phase_state.json`. These are the two seam contracts. Everything else is internal to one primitive or the other.

**Crystal: No holes.** All combinations of {3 check types} × {project-team, tutorial, no-phase} work.

**Ready for implementation.**
