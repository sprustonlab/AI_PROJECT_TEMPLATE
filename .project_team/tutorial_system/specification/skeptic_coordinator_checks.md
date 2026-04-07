# Skeptic: Coordinator Phase Gates — Do They Need Checks?

**Reviewer:** Skeptic
**Date:** 2026-04-04

---

## The question

The Coordinator already manages phase transitions through judgment and user checkpoints. Does formalizing `advance_checks` in `phases.yaml` add value, or does it duplicate gates that already exist?

---

## 1. Every phase transition, ruthlessly evaluated

I read COORDINATOR.md. Here's every transition and whether it's machine-verifiable:

| Transition | Current gate | Machine-verifiable? | What a Check would look like |
|---|---|---|---|
| Phase 0 → 1 | User Checkpoint 👤: "Present Vision Summary. Loop until approved." | **No.** Human judgment. | `ManualConfirm("Vision approved?")` — redundant with the checkpoint that already exists |
| Phase 1 → 2 | Coordinator creates STATUS.md, userprompt.md, state dir | **Partially.** Could check files exist. | `FileExistsCheck("STATUS.md")` — but Coordinator just created them. Checking your own work is pointless. |
| Phase 2 → 3 | "GATE: If all 4 Leadership agents are NOT visible, DO NOT proceed. Run `list_agents`." | **Yes, but already gated.** Coordinator runs `list_agents` and checks. | `CommandOutputCheck("list_agents", "Composability.*Skeptic.*UserAlignment.*TerminologyGuardian")` — but list_agents is an MCP call, not a shell command. Can't use CommandOutputCheck. |
| Phase 3 → 4 | User Checkpoint 👤: "Present specification. Handle response: Approve → proceed" | **No.** Human judgment on specification quality. | `ManualConfirm("Spec approved?")` — redundant |
| Phase 4 → 5 | "Exit when all Leadership approve." | **No.** Agent judgment across multiple agents. | Can't machine-verify "all Leadership approve" — it's a social protocol, not a system state. |
| Phase 5 → 6 | "Run tests. Fix failures. Exit when all pass." | **YES.** `pytest` exit code / output. | `CommandOutputCheck("pixi run pytest", "passed")` — **genuinely useful** |
| Phase 6 → 7 | "All agents confirm READY." | **No.** Agent consensus. | Can't machine-verify cross-agent consensus. |
| Phase 7 → 8 | "Create launch script. Test it." | **Partially.** Could run the script. | Depends on what "test it" means for this specific project. |
| Phase 8 → 9 | User Checkpoint 👤: "Ask user if E2E tests needed." | **No.** Human decision. | `ManualConfirm(...)` — redundant |

**Score: 1 out of 8 transitions is genuinely machine-verifiable.** Phase 5 → 6 (tests pass). That's it.

---

## 2. Is ManualConfirm needed for the team workflow?

**No.** Here's why:

The Coordinator already has **User Checkpoint 👤** markers in its instructions. These are prompts the Coordinator naturally follows — "Present Vision Summary. Loop until approved." The Coordinator asks the user, waits for approval, and proceeds.

Adding `ManualConfirm("Vision approved?")` as a formal gate check creates this flow:

1. Coordinator asks user: "Does the vision look good?" (natural workflow)
2. User says: "Yes, approved"
3. Coordinator tries to advance phase
4. Gate check fires: "Vision approved? [y/N]:" (ManualConfirm)
5. User says: "...I just told you yes?"

**ManualConfirm gates duplicate existing Coordinator behavior.** The Coordinator IS the gate. Its judgment about when to advance, informed by user checkpoints, is the mechanism. Adding a formal check on top makes the user confirm twice.

**For tutorials, it's different.** A tutorial engine doesn't have a Coordinator making judgment calls. The engine IS the gatekeeper, so it needs explicit checks. But the team workflow has a thinking agent managing transitions.

---

## 3. What's the REAL value of formalizing phase gates for the team workflow?

Let me steelman the case, then tear it down.

### The steelman

"The Coordinator sometimes skips phases or advances prematurely. Formal gates prevent this."

This is a real problem — agents do skip steps. But the solution in the current COORDINATOR.md is already working: bold text ("THIS IS NOT OPTIONAL. DO NOT SKIP"), explicit gates ("GATE: If all 4 Leadership agents are NOT visible, DO NOT proceed"), and STATUS.md tracking.

### The teardown

Formal `advance_checks` in `phases.yaml` enforce gates through the workflow engine. But who calls the workflow engine? The Coordinator. So the Coordinator has to:

1. Decide it's time to advance (judgment)
2. Call the engine to run gate checks (mechanical)
3. If checks fail, not advance (mechanical)

Step 1 is where the real gate is. If the Coordinator decides to advance prematurely, it's already past the meaningful gate. The formal check in step 2 can catch "tests don't pass" but can't catch "Leadership didn't actually approve." The machine-verifiable gates are the least likely to be violated — the Coordinator won't try to advance past testing without running tests. The judgment-based gates are the most likely to be violated — and those can't be machine-verified.

**Formal phase gates protect against the wrong failure mode for the team workflow.** They catch "system state isn't ready" (rare — the Coordinator checks this) but miss "the Coordinator is cutting corners" (the actual risk — and only prompt engineering addresses this).

---

## 4. Could team gates be ENTIRELY ManualConfirm while tutorial gates are CommandOutputCheck?

This is the cleanest framing. Let me evaluate:

### Team workflow: gates = Coordinator judgment + user checkpoints

The team workflow is **agent-mediated**. The Coordinator reads the room, checks agent status, presents to the user, and advances. Its gates are social and judgmental. Trying to formalize them into machine checks is:

- Redundant for user checkpoints (user already approves)
- Impossible for agent consensus ("all Leadership approve")
- Pointless for self-created artifacts (checking files you just wrote)

### Tutorial workflow: gates = machine verification

Tutorials are **engine-mediated**. No thinking agent manages transitions. The engine needs explicit, machine-verifiable checks: did the file get created? Does the command pass? These are real gates because there's no agent making judgment calls.

### The answer

**Don't use formal advance_checks for the team workflow at all.** The Coordinator IS the gate. Its phase files contain the instructions for what to verify (user checkpoints, agent consensus, etc.), and it executes those instructions through judgment.

Formal `advance_checks` exist for workflows where the engine is the gatekeeper (tutorials). For workflows where an agent is the gatekeeper (team), the phase file instructions ARE the gates.

---

## 5. The one exception: Phase 5 → 6 (tests pass)

This is the one genuinely machine-verifiable gate in the team workflow. "All tests pass" is a command output check. The Coordinator could forget to run tests, or misread output.

But even here: the Coordinator's Phase 5 instructions say "Run tests. Fix failures. Exit when all pass." The TestEngineer agent runs pytest. The Coordinator waits for the report. Adding a formal `CommandOutputCheck` is belt-and-suspenders — not wrong, but not necessary. The Coordinator already gates on test results.

**If we want one formal check for the team workflow, this is it.** Everything else is either human judgment or agent consensus that can't be machine-verified.

---

## 6. Recommendation

### For the team workflow (`phases.yaml`):

**Remove all `advance_checks`.** The Coordinator manages transitions through judgment and user checkpoints. Formal checks either duplicate existing gates (ManualConfirm) or can't verify the actual gate condition (agent consensus).

The `phases.yaml` manifest still has value for:
- **Phase IDs** — used by `phase_block`/`phase_allow` in guardrail scoping
- **Phase ordering** — explicit sequence
- **Phase file paths** — content discovery for prompt assembly

But `advance_checks` should be empty or absent for team workflow phases.

```yaml
# teams/project_team/phases.yaml
workflow_id: project-team
phases:
  - id: vision
    file: phases/phase-00-vision.md
  - id: setup
    file: phases/phase-01-setup.md
  - id: spawn-leadership
    file: phases/phase-02-spawn-leadership.md
  - id: specification
    file: phases/phase-03-specification.md
  - id: implementation
    file: phases/phase-04-implementation.md
  - id: testing
    file: phases/phase-05-testing.md
    # Optional: the ONE machine-verifiable gate
    advance_checks:
      - type: command-output-check
        command: "pixi run pytest --tb=short"
        pattern: "passed"
  - id: signoff
    file: phases/phase-06-signoff.md
```

### For tutorials (`tutorial.yaml`):

**Keep `advance_checks`.** The tutorial engine IS the gatekeeper. It has no Coordinator making judgment calls. Machine-verifiable checks are the primary gate mechanism.

```yaml
# tutorials/first-pytest/tutorial.yaml
workflow_id: first-pytest-tutorial
phases:
  - id: run-test
    file: phase-02-run-test.md
    advance_checks:
      - type: command-output-check
        command: "pixi run pytest tests/test_example.py"
        pattern: "passed"
```

### The principle

| Workflow type | Gatekeeper | Gate mechanism |
|---|---|---|
| Agent-mediated (team) | Coordinator agent | Phase file instructions + judgment + user checkpoints |
| Engine-mediated (tutorial) | Workflow engine | Formal `advance_checks` (machine-verifiable) |

**Don't build machine gates for judgment-based workflows.** The Coordinator's judgment IS the gate. Formalizing it into ManualConfirm checks creates double-confirmation without catching the actual failure mode (Coordinator cutting corners).

---

## 7. Impact on the spec

| Change | Effect |
|---|---|
| Remove `advance_checks` from team `phases.yaml` (except testing) | Simpler manifest, no ManualConfirm needed for team workflow |
| ManualConfirm may not be needed in v1 at all | If tutorials don't use it either (they use CommandOutputCheck), cut it entirely |
| `phases.yaml` becomes a phase registry + content map, not a gate definition | Cleaner separation of concerns |
| Check primitive serves tutorials exclusively | Narrower, more honest scope |

### ManualConfirm status after this analysis

| Consumer | Needs ManualConfirm? | Why not? |
|---|---|---|
| Team workflow | No | Coordinator + user checkpoints already gate |
| First Pytest tutorial | No | Gates are file-exists and command-output |
| `/check-setup` | Cut from v1 | N/A |
| Future tutorials | Maybe | Some tutorial phases may need "do you understand?" gates |

**ManualConfirm has zero v1 consumers.** Combined with the previous review (it's not a system check, it's a UX prompt), this is strong evidence to cut it from v1 entirely.
