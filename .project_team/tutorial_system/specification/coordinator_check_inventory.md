# Coordinator Phase Gate Check Inventory

**Author:** Composability
**Date:** 2026-04-04

---

## How the Coordinator currently handles phase transitions

**Answer: Judgment + user checkpoints. No formal checks at all.**

The Coordinator reads COORDINATOR.md every turn, tracks state in STATUS.md, and advances phases based on:

1. **User checkpoints (5 of 9 phases):** Present a summary, wait for user approval/decision
2. **Hard gates (2 of 9 phases):** All Leadership agents spawned (Phase 2), all tests pass (Phase 5)
3. **Implicit judgment (rest):** "Leadership has reported," "all agents confirm ready," "code is written"

The workflow is **deliberately loose**. This is a feature, not a bug — the Coordinator is an LLM that synthesizes information from multiple agents and presents it to a human. Rigid state machines would fight the design.

---

## Phase-by-phase gate analysis

### Phase 0: Vision → Phase 1: Setup

**Current gate:** User approves Vision Summary (loop until approved).

**What it actually needs:** User says "yes, that's what I want."

**Check type:** `ManualConfirm("Does this vision match your intent?")`

**But:** This is already how it works — the Coordinator presents a summary and waits. Wrapping it in ManualConfirm adds ceremony without value. The Coordinator's judgment IS the mechanism.

**Verdict:** No formal check needed. Keep as-is.

### Phase 1a-c: Setup (Working Dir → Session Check → Initialize)

**Current gate:** Conditional logic (is there an existing session? git repo exists?).

**What it actually needs:** Working directory exists and is writable. `.ao_project_team/` directory created.

**Check type:** Could be `FileExistsCheck(".ao_project_team/STATUS.md")` after initialization.

**But:** These sub-phases happen in a single Coordinator turn. There's no user-facing gate. The Coordinator just does them.

**Verdict:** No formal check needed. Internal Coordinator flow.

### Phase 2: Leadership Spawn → Phase 3: Specification

**Current gate:** HARD GATE. All 4 Leadership agents must be visible in `mcp__chic__list_agents`. If not, STOP and re-read file.

**What it actually needs:** Composability, TerminologyGuardian, Skeptic, UserAlignment are all spawned and responsive.

**Check type:** This is genuinely a system query — `list_agents` returns agent names and statuses. A `CommandOutputCheck` could wrap it:

```yaml
type: command-output-check
command: "list_agents output or STATUS.md content"
pattern: "Composability.*spawned.*TerminologyGuardian.*spawned.*Skeptic.*spawned.*UserAlignment.*spawned"
```

**But:** The Coordinator already checks this by calling `list_agents` directly. Wrapping it in a Check adds indirection. The real mechanism is the Coordinator reading its own STATUS.md where it records spawn evidence.

**Verdict:** No formal Check. But this IS a candidate for a `FileContainsCheck` if we want to formalize it in v2:

```python
# v2: Verify STATUS.md has all spawn evidence
FileContainsCheck(".ao_project_team/.../STATUS.md", r"Composability:.*spawned ✓")
```

### Phase 3: Specification → Phase 4: Implementation

**Current gate:** USER CHECKPOINT. Present specification. Four possible outcomes: Approve, Modify, Redirect, Fresh Review.

**What it actually needs:** Two things:
1. All Leadership agents have reported their findings
2. User approves the synthesized specification

**Check types:**
- "All Leadership reported" → This is the interesting one. The Coordinator currently judges this by asking agents and checking for responses. There's no artifact to check — it's conversational state.
- "User approves" → `ManualConfirm`

**The "all agents reported" problem:** This cannot be a `CommandOutputCheck` or `FileExistsCheck`. Agent reports are messages in the conversation, not files. You could require agents to write reports to files (e.g., `specification/review_composability.md`), and then check for those files. But that changes the workflow to accommodate the check system — tail wagging the dog.

**Verdict:** `ManualConfirm("Approve specification?")` for the user gate. "All agents reported" stays as Coordinator judgment (no formal check).

### Phase 4: Implementation → Phase 5: Testing

**Current gate:** "Exit when all Leadership approve." Implicit — Coordinator judges when agents signal approval.

**What it actually needs:**
1. All implementation files exist (Implementers created them)
2. Leadership agents have reviewed and approved

**Check types:**
- File existence: `FileExistsCheck` for each expected output file. But the file list is dynamic (determined during specification). Can't hardcode in `phases.yaml`.
- Leadership approval: Same problem as Phase 3 — conversational, not file-based.

**Verdict:** `ManualConfirm("Are all implementation tasks complete and Leadership-approved?")` This is what the spec already has, and it's correct. The human-in-the-loop IS the gate for a judgment-heavy transition.

### Phase 5: Testing → Phase 6: Sign-Off

**Current gate:** HARD GATE. All tests must pass.

**What it actually needs:** `pixi run pytest` exits with 0 and output contains "passed."

**Check type:** `CommandOutputCheck("pixi run pytest --tb=short 2>&1 | tail -1", r"passed")`

**This is the cleanest phase gate in the entire workflow.** It's objective, automatable, and produces clear evidence. This is what the Check primitive was designed for.

**Verdict:** `CommandOutputCheck`. Already in the spec. Correct as-is.

### Phase 6: Sign-Off → Phase 7: Integration

**Current gate:** "All agents confirm READY." Vague, judgment-based.

**What it actually needs:** Each active agent has signaled completion. Currently informal.

**Verdict:** `ManualConfirm("Have all agents confirmed ready for integration?")` or just Coordinator judgment. Not worth a formal check — this phase is brief.

### Phase 7: Integration → Phase 8: E2E Checkpoint

**Current gate:** Launch script created and tested.

**What it actually needs:** A launch script exists and runs without error.

**Check type:** Could be `FileExistsCheck("launch.sh")` + `CommandOutputCheck("bash launch.sh --dry-run", r"ok")`. But launch scripts are project-specific — no generic check works.

**Verdict:** Coordinator judgment. No formal check.

### Phase 8: E2E Checkpoint → Phase 9: Final Sign-Off

**Current gate:** USER CHECKPOINT. Ask if E2E tests are needed.

**Check type:** `ManualConfirm("Do you want to run end-to-end tests?")`

**Verdict:** ManualConfirm fits, but this is a branching decision (yes → run E2E, no → skip). ManualConfirm is binary pass/fail, not a branch selector. This is better as Coordinator dialog.

### Phase 9: Final Sign-Off

**Current gate:** Present result to user. Terminal phase.

**Verdict:** No gate needed — this is the end.

---

## Summary: What check types does the Coordinator actually need?

| Gate type | Phases | Check primitive fits? | What to use |
|---|---|---|---|
| **User approval** | 0, 3, 4→5, 6, 8, 9 | ManualConfirm partially | ManualConfirm for simple yes/no. Coordinator dialog for multi-option (Phase 3 has 4 outcomes). |
| **Objective command** | 5→6 | CommandOutputCheck perfectly | `pixi run pytest` — this is the poster child |
| **Agent presence** | 2→3 | Not directly | Coordinator reads list_agents. Could formalize with FileContainsCheck on STATUS.md in v2. |
| **Agent consensus** | 3→4, 4→5, 6→7 | No | Conversational state. Can't check files that don't exist. |
| **Artifact existence** | 7→8 | FileExistsCheck partially | File names are dynamic (project-specific). Can't hardcode. |

**Honest count:**
- **1 phase gate cleanly uses CommandOutputCheck** (Phase 5: tests pass)
- **2-3 phase gates could use ManualConfirm** (Phase 3 approval, Phase 4→5 "all done?")
- **0 phase gates need FileExistsCheck** (file lists are dynamic)
- **0 phase gates can check agent consensus** (it's conversational)

---

## Does ManualConfirm make sense for phase gates?

**Yes, absolutely.** ManualConfirm was cut from `CheckContext.ask_user()` (Skeptic correctly said the context bag shouldn't have side effects). But ManualConfirm as a standalone Check type that calls `input()` directly is exactly right for user-approval gates.

The Coordinator's workflow is human-in-the-loop by design. Most phase transitions need human judgment. ManualConfirm formalizes the "user approves" gate that already exists informally.

**But ManualConfirm has a limitation:** It's binary (pass/fail). Phase 3 has 4 outcomes (Approve, Modify, Redirect, Fresh Review). ManualConfirm can only ask "Approve?" — it can't branch on Modify vs. Redirect. For multi-option gates, the Coordinator's dialog is the right mechanism.

**Recommendation:** Keep ManualConfirm for simple yes/no gates. Don't try to make it handle multi-option decisions.

---

## Should phase gates use the same Check primitive?

**Yes. Same protocol, same `CheckResult`.** Here's why:

The `Check` protocol is: `check(ctx) → CheckResult(passed, message, evidence)`. This is general enough for:

- `CommandOutputCheck`: runs command, checks output → `CheckResult`
- `ManualConfirm`: asks user, interprets answer → `CheckResult`
- `FileExistsCheck`: checks path → `CheckResult`
- Future `StatusFileCheck`: reads STATUS.md for spawn evidence → `CheckResult`

The protocol doesn't care HOW the check evaluates. It only says: "given context, produce a verdict." Phase gates consume `CheckResult` the same way standalone checks do — the only difference is WHO triggers the check (WorkflowEngine vs. hints pipeline).

**What the Check protocol buys for phase gates:**
- Uniform gate evaluation in WorkflowEngine: `for check in phase.advance_checks: result = check.check(ctx)`
- Evidence field captures WHY a gate failed (pytest output, user's answer)
- Same test infrastructure — mock CheckContext, verify gates

**What it does NOT try to do:**
- Replace Coordinator judgment for agent consensus
- Handle multi-option branching (that's Coordinator dialog)
- Check conversational state (messages aren't files)

---

## The real phases.yaml for project-team (v1)

Most phases don't need formal advance_checks. The Coordinator's judgment and user checkpoints already work. Forcing checks onto judgment-based transitions adds ceremony without value.

```yaml
# AI_agents/project_team/phases.yaml
workflow_id: project-team
phases:
  - id: vision
    file: phases/phase-00-vision.md
    # Gate: User approves vision. Coordinator dialog handles this
    # (4 possible outcomes — ManualConfirm is too simple).

  - id: setup
    file: phases/phase-01-setup.md
    # No gate. Internal Coordinator flow.

  - id: spawn-leadership
    file: phases/phase-02-spawn-leadership.md
    # Gate: All 4 Leadership agents spawned.
    # Coordinator checks list_agents directly — no Check needed.

  - id: specification
    file: phases/phase-03-specification.md
    # Gate: User approves specification.
    # Same as vision — multi-option, Coordinator dialog.

  - id: implementation
    file: phases/phase-04-implementation.md
    advance_checks:
      - type: manual-confirm
        question: "Are all implementation tasks complete and Leadership-approved?"

  - id: testing
    file: phases/phase-05-testing.md
    advance_checks:
      - type: command-output-check
        command: "pixi run pytest --tb=short 2>&1 | tail -1"
        pattern: "passed"

  - id: signoff
    file: phases/phase-06-signoff.md
    # Gate: All agents confirm ready. Coordinator judgment.
    # Terminal phase for v1 (integration/E2E are Coordinator-managed).
```

**Only 2 phases have formal advance_checks:**
- Phase 4→5: ManualConfirm (simple yes/no — "all done?")
- Phase 5→6: CommandOutputCheck (objective — tests pass)

The other transitions are Coordinator judgment or multi-option user dialog. Forcing them into the Check primitive would require either:
- Dumbing down multi-option gates to yes/no (loses information)
- Expanding Check beyond pass/fail (over-engineering for v1)

---

## What this means for the spec

1. **Keep ManualConfirm** as a v1 Check type. It's the right tool for simple user-approval gates.
2. **Keep the Check primitive unified** — same protocol for standalone and phase gates.
3. **Don't add new Check types for agent consensus.** That's Coordinator judgment, not a checkable condition. v2 could add `StatusFileContainsCheck` if agents are required to write reports to files.
4. **Most project-team phase gates are empty** (no advance_checks). This is correct — the Coordinator's dialog IS the gate mechanism for judgment-heavy transitions.
5. **The tutorial workflow is where Check shines** — tutorials have objective, automatable gates ("file exists," "command succeeds"). Project-team is judgment-heavy.

---

## v2 candidates

| Check type | What it does | When it's needed |
|---|---|---|
| `StatusFileContainsCheck` | Read STATUS.md for patterns (spawn evidence, agent reports) | If we want to formalize Phase 2 gate |
| `AllChecksPass` (CompoundCheck) | AND over multiple checks | If a gate needs "file exists AND tests pass" |
| `AgentReportedCheck` | Check that agent wrote a report file | If we require agents to write reports to files (changes workflow) |

None of these are needed for v1. The 3 built-in types (CommandOutputCheck, FileExistsCheck, ManualConfirm) cover the 2 real gates.
