# Skeptic Review: "v1 Infrastructure, v2 Tutorial"

The user's reframe: verification types, progress tracking, and mode-aware guardrail scoping are general-purpose template primitives. Tutorials are just one consumer. Build the primitives first.

This is a strong argument. Let me stress-test it.

---

## The Case FOR Infrastructure-First

The template already follows this pattern. The hints system was built as a general-purpose pipeline (TriggerCondition × HintLifecycle × Presentation), not as "the SSH key reminder feature." The guardrail system was built as a rules engine (rules.yaml × generate_hooks.py × role_guard.py), not as "the pip-install blocker." Both are now consumed by multiple features.

If the proposed primitives are genuinely general-purpose, building them as infrastructure is consistent with the template's design philosophy: composable subsystems with clean protocols.

---

## The Stress Test: Who Are the Other Consumers TODAY?

The infrastructure-first argument is only valid if the primitives have **real, non-hypothetical consumers beyond tutorials.** Let me evaluate each proposed primitive:

### 1. Verification Protocol (`check(ctx) → VerificationResult`)

**Proposed primitive:** A protocol for running a check against system state and returning a structured pass/fail with evidence.

**Tutorial consumer:** Checkpoint verification (did the user generate the SSH key?).

**Other consumers TODAY:**
- **Project initialization checks** — The template has an `init_project.md` command. After running it, there's no verification that pixi installed correctly, that git initialized, that the copier template applied. A verification check could confirm: `pixi info` works, `.git/` exists, `.copier-answers.yml` has expected fields.
- **Environment health checks** — "Is pixi working? Is git configured? Does the SSH key exist?" These are the same checks the tutorials would teach, but as a standalone diagnostic. The template could offer `/check-setup` that runs a suite of verifications.
- **Pre-commit/pre-push checks** — Before pushing, verify the project is in a good state. `VerificationResult` with evidence is more useful than a bare exit code.
- **Guardrail self-test** — The guardrail system has `test_framework.py` (a 34K file). Verification as a protocol could formalize the "did this guardrail rule fire correctly?" checks.

**Verdict: JUSTIFIED.** The Verification protocol is genuinely general-purpose. The `check(ctx) → VerificationResult` pattern with evidence capture is useful anywhere you need structured pass/fail with proof. The hints system already has `TriggerCondition.check(state) → bool` — the Verification protocol is the richer version of the same idea.

**BUT — scope it.** The protocol + `CommandOutputCheck` + `FileExistsCheck` are general. `ManualConfirm` is tutorial-specific (asking a user "did you click the email link?" is not a general primitive). `CompoundCheck` is useful but can wait — build it when two consumers need it.

### 2. Progress/State Tracking

**Proposed primitive:** A persistent store for tracking multi-step workflow progress (current step, completed steps, evidence per step).

**Tutorial consumer:** Tutorial progress persistence (which steps are done, can the user resume?).

**Other consumers TODAY:**
- **Project setup wizard** — The `init_project.md` command is a multi-step process. Currently it's a one-shot script. If it fails mid-way, there's no resume. A progress store would let it resume from where it left off.
- **Onboarding flow** — New user joins, needs to: configure git, set up SSH, install pixi, create first project. This is a multi-step workflow with state, even if it's not a "tutorial."

**Verdict: WEAK.** These consumers are hypothetical. The project setup wizard doesn't exist as a multi-step workflow today. The onboarding flow is literally what the tutorials would provide — calling it a separate consumer is circular. Progress tracking as a primitive is really only needed by tutorials and things that look like tutorials.

**Counter-argument:** Progress tracking is simple. A JSON file with `{step_id: {completed: bool, evidence: str, timestamp: str}}` is ~50 lines. It's not expensive enough to worry about YAGNI. But it's also not expensive enough to justify calling it "infrastructure."

### 3. Mode-Aware Guardrail Scoping

**Proposed primitive:** Guardrail rules that activate/deactivate based on the current operational mode (tutorial mode, team mode, solo mode).

**Tutorial consumer:** Tutorial-specific guardrails (don't delete SSH keys during SSH tutorial).

**Other consumers TODAY:**
- **Team mode already exists** — `role_guard.py` implements `block: [Subagent]` scoping. The session marker at `.claude/guardrails/sessions/ao_<PID>` is already a mode signal. The infrastructure for mode-aware rules is half-built.
- **Solo vs. team differences** — R04 (git push block) only applies in team mode via `block: [Subagent]`. But the scoping mechanism is per-role, not per-mode. Adding a `scope: { mode: tutorial }` field is a real generalization of the existing `block:` mechanism.
- **Future modes** — Review mode (stricter guardrails during code review), deploy mode (block destructive operations), debug mode (relaxed guardrails for debugging). These are plausible but not requested.

**Verdict: THIS IS THE STRONGEST CASE.** The guardrail system already has proto-mode-awareness (team mode detection, role-based scoping). Generalizing this to a proper `scope` field that supports arbitrary modes is a natural evolution. It benefits team mode (cleaner rule definitions), tutorial mode (scoped safety rules), and any future mode.

**The implementation gap I flagged is real but bounded.** The hook generation system (`generate_hooks.py`) needs to understand `scope` fields and emit mode-checking code. The hooks need a way to know what mode is active (extend the session marker mechanism, or read a mode file). This is ~200-300 lines of changes to `generate_hooks.py` + `role_guard.py`. Not trivial, but not a research project.

### 4. TutorialContext on ProjectState

**Proposed primitive:** Extending `ProjectState` with optional context fields for new subsystems.

**Other consumers TODAY:**
- **None.** `TutorialContext` is tutorial-specific. The general pattern (adding optional fields to `ProjectState`) already exists (`session_count`). There's nothing to build here — it's just adding a field when tutorials need it.

**Verdict: NOT INFRASTRUCTURE.** This is a tutorial implementation detail, not a primitive.

### 5. Tutorial-Aware TriggerConditions for Hints

**Proposed primitive:** New trigger condition types that fire based on workflow state.

**Other consumers TODAY:**
- **Project phase triggers** — "Fire a hint when the user enters the 'testing' phase of their project." This would use the same pattern as `TutorialStepActive` but scoped to project phases.
- **Onboarding triggers** — "Fire a hint when the user hasn't configured git yet" already exists in the hints system. Tutorial triggers are just a new category of the same thing.

**Verdict: MARGINAL.** The trigger pattern is already general (that's why it's a protocol). New trigger implementations are cheap. Building tutorial-specific triggers as "infrastructure" doesn't save anything — you're just writing the same code and calling it something different.

---

## Risk: Infrastructure Nobody Uses

The biggest risk with "v1 infrastructure, v2 tutorial" is: **v2 never ships.**

This is a real pattern. You build the framework, feel satisfied with the architecture, and the actual user-facing feature (the tutorials) keeps getting deferred because "the infrastructure is ready, we just need content." Meanwhile:

- The infrastructure has no users exercising it, so bugs hide
- The infrastructure's API was designed by imagination, not by actual usage — when v2 starts, you discover the API is wrong and refactor
- The user sees zero value from v1 because infrastructure is invisible

**The hints system avoided this trap** because it shipped with actual hints. `get_hints()` returns real `HintSpec` objects that fire in real projects. The infrastructure was validated by its first consumer at birth.

**The guardrail system avoided this trap** because it shipped with real rules (R01-R05). The hook generation was validated by rules that run in production.

If the verification infrastructure ships without a single tutorial, it has zero users. If mode-aware guardrail scoping ships without tutorial rules, it has zero rules using the new scope field.

---

## Minimum Viable Infrastructure That Proves Value Without Tutorials

If the user wants infrastructure-first, here's what proves value on day one:

### Ship together: Infrastructure + ONE Tutorial + ONE Health Check

**Infrastructure (the primitives):**

1. **Verification protocol** — `Verification` protocol, `VerificationResult`, `VerificationContext` (simplified: just `run_command` + `file_exists`, not 5 callables). Two implementations: `CommandOutputCheck`, `FileExistsCheck`.

2. **Mode-aware guardrail scoping** — Extend `rules.yaml` schema with `scope: { mode: <name> }`. Extend `generate_hooks.py` to emit mode-checking code. Extend session marker or add a mode file. Refactor existing `block: [Subagent]` R04/R05 rules to use the new scope mechanism as proof.

3. **Progress store** — Simple JSON-backed store: `{workflow_id: {step_id: {completed, evidence, timestamp}}}`. ~80 lines.

**First consumer A (tutorial):**

4. **One tutorial: "Write and Run Your First Pytest"** — This is the simplest tutorial. No network, no SSH, no external services. File exists → command output → done. It exercises: verification (did pytest pass?), progress (resume mid-tutorial), mode-aware guardrails (don't delete test files during tutorial). If this tutorial works end-to-end, the infrastructure is validated.

**First consumer B (non-tutorial):**

5. **`/check-setup` health diagnostic** — A command that runs a suite of `Verification` checks against the current project: Is pixi working? Is git configured? Does `.copier-answers.yml` exist? Outputs a report of `VerificationResult` entries. This proves the Verification protocol has value outside tutorials. It's also genuinely useful — "my project is broken, what's wrong?" is a real user need.

### Why this works

- Infrastructure has **two consumers from day one** (tutorial + health check), not zero
- The tutorial exercises the full stack: content loading → step progression → verification → hints → guardrails
- The health check exercises verification as a standalone primitive
- Mode-aware scoping is validated by refactoring existing R04/R05 rules AND adding tutorial rules
- If v2 never ships more tutorials, you still have one working tutorial + a health check command. That's value.

---

## What I'd Cut From the Spec Even in Infrastructure-First

Even accepting the infrastructure-first reframe, these are still premature:

| Item | Why Cut |
|---|---|
| `CompoundCheck` (AND/OR composition) | Build when two consumers need composite verification. Not needed for pytest tutorial or health check. |
| `ConfigValueCheck` | It's `CommandOutputCheck` with `.strip()`. Delete the class. |
| `ManualConfirm` | Tutorial-specific. No infrastructure value. Add in v2 with tutorials that need it. |
| Branching progression | No consumer needs branching. Checkpoint-gated only for v1. |
| Auto-discovery of tutorial dirs | 1 tutorial doesn't need discovery. `glob("tutorials/content/*/tutorial.yaml")` when you have 5+. |
| YAML→HintSpec conversion pipeline | Construct `HintSpec` objects in Python for 1 tutorial. Build the pipeline when there are 5+ tutorials. |
| Presentation axis | One presentation mode. No axis needed. |
| `AgentContext.to_system_prompt()` builder | Nice-to-have, but the agent prompt for 1 tutorial can be a template string. |

---

## Summary Verdict

| Question | Answer |
|---|---|
| Is "build infrastructure first" justified? | **Partially.** Verification protocol and mode-aware guardrail scoping are genuinely general-purpose. Progress tracking and TutorialContext are not. |
| Who are the other consumers TODAY? | Verification: health checks, project init validation. Mode-aware scoping: refactored team-mode rules. Progress tracking: nothing real. |
| Is there a risk of building infrastructure nobody uses? | **Yes, high.** Mitigate by shipping infrastructure WITH its first two consumers (one tutorial + one health check). |
| What's the minimum viable infrastructure? | Verification protocol (2 types) + mode-aware guardrail scoping + progress store + one tutorial + `/check-setup` health command. |

**The reframe is valid for two of the four proposed primitives.** Verification and mode-aware guardrails are real infrastructure with real consumers beyond tutorials. Progress tracking and TutorialContext are tutorial implementation details wearing infrastructure clothing.

**The critical constraint:** Ship infrastructure with consumers. Not before them, not after them. With them. The hints system and guardrail system both did this. The tutorial infrastructure should too.
