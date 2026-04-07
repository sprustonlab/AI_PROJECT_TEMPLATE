# Skeptic Review — Phase: Specification

## Summary

The vision is clear and well-scoped. The four deliverables are concrete. But the **gap between the current codebase state and what the vision assumes** is larger than the vision acknowledges. Several assumptions are unexamined, and the project has significant failure modes if we don't address them during specification.

---

## Challenged Assumptions

### 1. "Fix the stale Copier template" assumes we know what's stale

**Risk: We underestimate the scope of staleness.**

The template has not received the April 6 infrastructure updates. The drift is not cosmetic — entire subsystems are missing from `template/`:

| Missing from template | Impact |
|---|---|
| `workflows/` directory (29 files) | Generated projects have NO workflow system |
| `global/` directory (`rules.yaml`, `hints.yaml`) | No centralized config in generated projects |
| 11 agent role files (COMPOSABILITY.md, USER_ALIGNMENT.md, RESEARCHER.md, etc.) | Generated Project Team is incomplete — only COORDINATOR, IMPLEMENTER, SKEPTIC, TEST_ENGINEER exist in template |
| `commands/jupyter` | Missing command in generated projects |
| Guardrail rules diverged (root uses `deny` for pip/conda; template uses `warn`) | Generated projects have weaker guardrails than the source repo |

**The "fix" is not a patch — it's a rebuild.** If the team treats this as "update a few files," we'll ship a template that generates broken projects.

**Question for Coordinator:** Does the team understand this is a significant sync effort, not a handful of file copies? The jinja templating adds complexity — every new file needs conditional inclusion logic in `copier.yml`.

### 2. "Stress test" assumes we know what to test

**Risk: Shallow stress testing that only covers happy paths.**

The existing test suite has meaningful coverage for some areas but critical gaps:

- **No tests for the tutorial workflow** — `workflows/tutorial/` is completely untested
- **No tests for workflow activation end-to-end** — no test starts a workflow, advances phases, and verifies rules/hints fire correctly
- **No tests for inter-agent communication** — `spawn_agent`, `ask_agent`, `tell_agent` are never exercised in tests
- **`test_template_freshness.py` only checks 16 paired files** — it will miss the entire `workflows/` and `global/` directories since they aren't in the paired-files list
- **Intent tests are "Red phase TDD"** — `test_intent_guardrail_wiring.py` and `test_intent_role_enforcement.py` are designed to FAIL (proving gaps exist), not to pass

A stress test that runs `pytest` and reports "N tests pass" will miss all of this. The stress test must go beyond existing tests.

### 3. "Getting Started Guide for agents AND humans" assumes one document works for both

**Risk: A document that's too abstract for humans and too vague for agents.**

Human readers need: what to install, what to click, what to expect on screen.
Agent readers need: exact file paths, tool names, expected return values, error patterns.

A single linear document trying to serve both audiences will likely satisfy neither. The User Alignment review flagged this as an ambiguity but didn't call it a risk — it is one. A bad Getting Started Guide is worse than none, because users will follow it, hit a wall, and blame the system.

**Recommendation:** Structure the guide with shared context sections and clearly marked "For Humans" / "For Agents" branches where the workflows diverge. Don't try to write one path that works for both.

### 4. "Runnable tutorial workflows" assumes the workflow system is stable enough to build on

**Risk: Building tutorials on infrastructure that hasn't been stress-tested.**

The workflow system (`workflows/`, `advance_phase`, `get_phase`, advance checks, workflow-scoped rules, workflow-scoped hints) was added on 2026-04-06. There are **no automated tests** for:
- Phase advance with `file-exists-check`
- Phase advance with `manual-confirm`
- Workflow-scoped rule enforcement (do rules fire only in the correct phase?)
- Workflow-scoped hint delivery
- Injection behavior (`echo_injection` in tutorial)

If we build two new tutorial workflows on top of untested infrastructure, every bug in the workflow system becomes a bug in the tutorials. The tutorials should be deliverable #3 and #4, but the **workflow system itself needs to be deliverable #0** — verified working before we build on it.

### 5. "Toy Project with Agent Team" assumes the agent team pipeline works end-to-end

**Risk: The tutorial can't be written until the pipeline is verified.**

The Project Team workflow has 7 phases. The Coordinator spawns agents, delegates, collects results. This involves:
- `spawn_agent` creating actual subprocesses
- `ask_agent` / `tell_agent` message passing
- `advance_phase` phase transitions with advance checks
- Guardrail rules scoped to phases (`no_push_before_testing`)
- State management in `.ao_project_team/`

Has anyone run the full pipeline recently? The agent role files were significantly expanded (13 new files) but the template wasn't updated. If the pipeline has latent bugs, the "Toy Project" tutorial will surface them — but tutorials are the wrong place to discover infrastructure bugs.

**Recommendation:** The stress test (deliverable #1) must include a dry-run of the full Project Team pipeline before we design the Toy Project tutorial.

---

## Failure Modes

### F1: Template generates projects that break on `pixi install`

**How:** Template `pixi.toml.jinja` references claudechic via git URL (standard mode), but the claudechic repo may have new dependencies not reflected in `envs/claudechic.yml`. Or the jinja conditionals produce invalid TOML.

**Detection:** Run `copier copy` with every combination of options, then `pixi install` each. This is what `test_e2e_smoke.py` does for ONE combination — we need all of them.

**Severity:** Critical. A broken `pixi install` means the generated project is DOA.

### F2: Template generates incomplete Project Team

**How:** Template only includes 4 agent role files (COORDINATOR, IMPLEMENTER, SKEPTIC, TEST_ENGINEER). The Coordinator's instructions reference 13+ roles. When Coordinator tries to spawn COMPOSABILITY or USER_ALIGNMENT, the role files won't exist.

**Detection:** `copier copy` with `use_project_team=true`, then check if all files referenced in COORDINATOR.md exist.

**Severity:** Critical. The Project Team is unusable without the full agent roster.

### F3: Tutorials break mid-way because advance checks fail silently

**How:** The tutorial workflow uses `file-exists-check` (e.g., `tutorial_basics_done.txt`). If the check mechanism has a bug (wrong path resolution, missing file-system access), the user gets stuck with no explanation.

**Detection:** Automated test: start tutorial workflow, create the expected file, call `advance_phase`, verify phase changes.

**Severity:** High. A stuck tutorial destroys user confidence.

### F4: "Extending the System" tutorial teaches outdated patterns

**How:** The tutorial teaches "add a new rule" — but if it teaches adding rules to `template/.claude/guardrails/rules.yaml.jinja` when rules now live in `global/rules.yaml` and workflow YAML `rules:` sections, the user learns the wrong thing.

**Detection:** The tutorial must be written AFTER the template is fixed, and must reference the post-fix file layout.

**Severity:** High. A tutorial that teaches wrong patterns is actively harmful.

### F5: Stress test doesn't test the "developer mode" path

**How:** `copier.yml` has `claudechic_mode: standard` (git URL) and `developer` (local editable). Most testing uses standard. If developer mode breaks, it silently fails for power users.

**Detection:** Run `copier copy` with `claudechic_mode=developer` and verify the submodule clone + editable install works.

**Severity:** Medium. Affects developer-mode users only, but those are the users most likely to contribute back.

### F6: Getting Started Guide goes stale immediately

**How:** The guide references specific file paths, command outputs, and workflows. Any subsequent change to the system invalidates parts of the guide. There's no test to detect guide staleness.

**Detection:** The guide needs a companion test (even a simple one) that verifies key claims: "running X produces Y," "file Z exists at path W."

**Severity:** Medium. Stale docs are the #1 complaint in developer tooling.

### F7: Global rules vs workflow rules create confusing enforcement

**How:** `global/rules.yaml` has 3 rules (no_rm_rf, warn_sudo, log_git). `project_team.yaml` has 3 rules (no_direct_code_coordinator, no_push_before_testing, no_force_push). When both are active, a user sees 6 rules from two sources with no unified view. The Getting Started Guide must explain this layering or users will be confused.

**Detection:** Document the rule layering clearly. Test that both global and workflow rules fire correctly when a workflow is active.

**Severity:** Medium. Confusion, not breakage — but confusion during onboarding is costly.

---

## Dependency Order (What Must Happen First)

The vision lists four deliverables as if they're parallel. They're not. There's a strict dependency chain:

```
1. Stress test the workflow system infrastructure
   └── 2. Fix the Copier template (requires knowing what's broken)
       └── 3. Getting Started Guide (requires the fixed template as source of truth)
           └── 4a. "Extending the System" tutorial (requires the guide's terminology and file layout)
           └── 4b. "Toy Project" tutorial (requires verified Project Team pipeline)
```

Attempting to parallelize deliverables 2-4 before deliverable 1 is complete risks building on broken foundations.

---

## What's Solid

Not everything is a risk. Credit where due:

- **The vision correctly identifies the core problem** — template staleness after the claudechic move
- **The test infrastructure exists** — `conftest.py` fixtures, `copier_output` factory, `pexpect`-based TUI tests
- **The terminology document is excellent** — clear canonical names prevent confusion
- **The workflow YAML schema is clean** — phases, advance_checks, rules, and hints are well-structured
- **The hints system is composable** — triggers, lifecycles, combinators make it extensible
- **User Alignment correctly flagged the "runnable workflow" ambiguity** — this needs resolution before implementation

---

## Four Questions (per Skeptic protocol)

1. **Does this fully solve what the user asked for?** — The vision captures all four deliverables. But it underestimates the infrastructure work needed before tutorials can be built.

2. **Is this complete?** — No. The vision doesn't account for the workflow system being untested, the template missing 29+ files, or the dependency ordering between deliverables. These gaps need to be addressed in the specification.

3. **Is complexity obscuring correctness?** — The copier.yml jinja conditional system is complex (conditional excludes, conditional tasks, mode-dependent file generation). Each template fix must be verified against all option combinations, not just the default. This combinatorial complexity is essential (it's what copier does) but must be explicitly tested.

4. **Is simplicity masking incompleteness?** — Yes. "Fix the stale Copier template" sounds like a single task. It's actually: (a) inventory all drift, (b) add missing files with jinja conditionals, (c) update copier.yml exclusions, (d) update _tasks, (e) verify all option combinations, (f) update test_template_freshness.py paired-files list. Calling it one task masks the scope.

---

## Recommendations for Specification Phase

1. **Inventory all template drift FIRST** — before designing tutorials. Produce a concrete list of every file that needs adding/updating in `template/`.
2. **Add workflow system tests before building tutorials on it** — at minimum: phase advance, advance checks, workflow-scoped rules.
3. **Resolve "runnable workflow" ambiguity NOW** — are tutorials `.yaml` workflow definitions or markdown guides? This changes everything.
4. **Define the Toy Project choice** — what is the pre-selected vision/goal? This must be small, self-contained, and exercise the full pipeline. Suggest: a tiny CLI tool (e.g., a Pomodoro timer) — small enough to complete, complex enough to need multiple agents.
5. **Add a freshness test for the Getting Started Guide** — even a smoke test that checks referenced paths exist.
6. **Test all copier option combinations** — not just the default. At minimum: guardrails on/off, project_team on/off, hints on/off, claudechic standard/developer, cluster on/off (LSF and SLURM).
