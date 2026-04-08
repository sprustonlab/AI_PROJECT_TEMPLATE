# Skeptic Review — Tutorial System

## Summary Verdict

The vision is sound. With the clarification that users are already on the cluster with the template running, and that multi-agent is the *subject* of one tutorial rather than the delivery mechanism for all tutorials, the major architectural risks drop significantly. What remains are real but solvable engineering challenges around checkpoint reliability, tutorial mode lifecycle, and content format design.

---

## Corrected Assumptions (v2)

### ~~1. Bootstrap paradox~~ — WITHDRAWN

Original concern was that tutorials like "SSH setup" and "GitHub signup" require the system before the user has it. **Correction accepted:** Users are already on the cluster (SSH is available; the tutorial teaches *usage*, not installation). GitHub signup is post-install. The template is running locally before any tutorial starts. No bootstrap paradox exists for the proposed tutorial set.

**Residual risk (LOW):** If future tutorials are added that genuinely require pre-template setup, there's no mechanism to flag them as out-of-scope for the tutorial system. A simple `prerequisites` field in the tutorial format would prevent this.

### 2. "Guardrails can verify arbitrary step completion" — STANDS (refined)

This remains the hardest engineering problem. The vision says guardrails prove step completion, but verification quality varies wildly by step type:

| Verification Type | Reliability | Example |
|---|---|---|
| File exists / content matches | High | "Does `~/.ssh/config` contain a Host entry?" |
| Command output matches pattern | Medium | "`git remote -v` returns a GitHub URL" — but what if network is down? |
| Process state / agent state | Low | "Is ssh-agent running with the key loaded?" — shell-dependent, session-scoped |
| External service reachable | Low | "Can you SSH to the cluster?" — network, firewall, auth all involved |

**Risk:** A checkpoint system that treats all verifications as equally reliable will produce false positives on the flaky ones. Users trust it, but it's wrong.

**Mitigation required:** Each checkpoint must declare:
- The verification command
- Expected output pattern (regex or literal)
- A **confidence level** or at minimum a **retry/timeout strategy**
- A **failure message** that tells the user what to check manually if verification fails
- Whether failure is **blocking** (can't proceed) or **advisory** (warn and allow continue)

### ~~3. Multi-agent is accidental complexity~~ — WITHDRAWN (with caveat)

**Correction accepted:** V1 uses a single tutorial-runner agent for standard tutorials. Multi-agent appears only in the "Working with Agent Teams" tutorial, where spawning agents IS the lesson. This is essential complexity — the tutorial teaches multi-agent by doing multi-agent.

**Remaining concern (MEDIUM):** The "Working with Agent Teams" tutorial is architecturally different from every other tutorial. It's not "agent reads script, guides user through steps" — it's "agent spawns other agents as part of the tutorial content." This means:
- The tutorial-runner must have agent-spawning permissions (other tutorials don't need this)
- Cleanup is harder — what if user exits mid-tutorial with spawned agents still running?
- Checkpoint verification must check agent state, not just file/command output

**Recommendation:** Design the "Agent Teams" tutorial as a **separate tutorial type** with its own runner, or at minimum flag it as requiring elevated capabilities. Don't let it pollute the simple single-agent runner that handles 90% of tutorials.

### 4. "Hints integration adds value to tutorials" — STANDS (narrowed)

**Acceptable integration:** Hints system detects the user might benefit from a tutorial (e.g., "you've never run pytest — want a guided walkthrough?") and suggests it. This is a clean, one-directional dependency: hints → tutorial launcher.

**Red flag integration:** Tutorials running inside or through the hints pipeline; tutorial steps delivered as hint notifications; shared state between hint lifecycle and tutorial lifecycle.

**Mitigation required:** Specification must confirm the integration is one-directional (hints suggest tutorials, tutorials don't use hints infrastructure). If deeper integration is planned, it needs explicit justification.

### 5. "Tutorial mode is a distinct mode" — STANDS

This remains essential complexity that must be fully specified. Every "mode" in a system creates a matrix of interactions with everything else.

**Risk:** Underspecified mode lifecycle. Specifically:

- **Entry:** What command starts tutorial mode? What state is initialized?
- **Exit (clean):** User finishes all steps. What cleanup runs? How is completion recorded?
- **Exit (explicit abandon):** User types "quit" mid-tutorial. Is progress saved? Can they resume?
- **Exit (crash/disconnect):** Terminal dies. What state persists? On reconnect, is the user back in tutorial mode automatically, or do they re-enter manually?
- **Guardrail interaction:** Are normal-mode guardrails (R01-R05) active during tutorials? If a tutorial step requires `pip install` for teaching purposes, does R02 block it? Do tutorials need guardrail exemptions?
- **Nesting:** Can you start a tutorial while in another tutorial? (Answer should be "no" — but it needs to be enforced.)

**Mitigation required:** Full lifecycle state machine before implementation.

---

## Failure Modes (Updated)

| # | Failure Mode | Severity | Status | Notes |
|---|---|---|---|---|
| ~~F1~~ | ~~Bootstrap paradox~~ | ~~High~~ | WITHDRAWN | Users already have the system running |
| F2 | False-positive checkpoint — verification says "done" but step didn't work | **High** | STANDS | Flaky verification (network, timing, shell state). Most dangerous because user trusts it. |
| F3 | Tutorial rot — content drifts from actual tool behavior | **Medium** | STANDS | No automated testing of tutorial content against real system. Tutorials say "run X" but X changed. |
| F4 | Scope explosion — unbounded tutorial additions | **Low** | DOWNGRADED | Less risky now that architecture is simpler (single runner). But still need criteria for "tutorial vs. docs." |
| F5 | Agent over-help — agent does the step FOR the user | **High** | UPGRADED | This is now the #2 risk after checkpoint reliability. If the tutorial agent has Bash access and the user says "just do it for me," the entire pedagogical value is lost. The agent must be constrained to *guide*, not *execute*. |
| F6 | Stuck-in-mode — user can't exit or doesn't know they're in tutorial mode | **Medium** | STANDS | Requires clear mode indicator and escape hatch. |
| F7 | Checkpoint ordering — out-of-order steps confuse verification | **Low** | STANDS | Solvable by making checkpoints verify cumulative state, not step-transition state. |
| F8 | **NEW:** Agent Teams tutorial leaves orphaned agents | **Medium** | NEW | User exits "Working with Agent Teams" tutorial mid-way. Spawned tutorial agents are still running. Cleanup must be automatic. |
| F9 | **NEW:** Guardrail conflicts in tutorial mode | **Medium** | NEW | Tutorial step requires action that normal guardrails block (e.g., teaching `pip install` while R02 blocks it). Need exemption mechanism or tutorial-specific guardrail profile. |

---

## Essential Complexity (Must Solve, Not Avoid)

1. **Tutorial content format** — The core data model. Steps, checkpoints with per-step verification specs, hints, failure branches. This is the single most important design decision. Get it right and everything else follows; get it wrong and you rebuild.

2. **Checkpoint verification with honest reliability** — Each checkpoint must know how reliable its verification is and communicate that honestly to the user. "Verified: file exists" is different from "Verified: SSH connection succeeded (network-dependent)."

3. **Tutorial mode lifecycle** — Full state machine: entry, clean exit, abandon, crash recovery, guardrail interaction, nesting prevention. All of it, before implementation.

4. **Agent over-help prevention** — The tutorial agent must be *constrained* from executing steps the user should perform. This is a guardrail on the agent itself, not just on the user. This is hard because the agent has tool access by default.

---

## Accidental Complexity (Eliminate)

1. **Deep hints integration** — Keep it one-directional: hints suggest tutorials. Nothing more unless explicitly justified.

2. **Generic framework before concrete tutorials** — Write 2-3 real tutorials first, then extract the pattern. Premature abstraction of a "tutorial engine" will encode wrong assumptions.

---

## Four Questions (Updated)

1. **Does this fully solve what the user asked for?** — Yes, with the corrections. Single-agent runner for standard tutorials, multi-agent only where it's the subject matter. The vision maps well to the actual user need.

2. **Is this complete?** — Not yet. Missing: tutorial mode lifecycle, checkpoint verification specification per step type, agent over-help prevention mechanism, and guardrail interaction during tutorial mode.

3. **Is complexity obscuring correctness?** — Much improved after corrections. Single-agent runner is clean. The "Agent Teams" tutorial is the one area where complexity is justified but must be isolated from the standard path.

4. **Is simplicity masking incompleteness?** — Checkpoint verification is still the weak point. "Guardrails prove it" sounds simple but each checkpoint is a custom verification with its own reliability profile. The specification must make this explicit per tutorial, not abstract it away.

---

## Recommendations (Updated)

1. **Design the tutorial content format first** — This is the core data model. Every other decision (runner, mode, checkpoints) is shaped by it. Include: steps, checkpoint specs (command, expected output, confidence, failure action), hints per step, prerequisites.

2. **Define tutorial mode lifecycle as a state machine** — Entry, clean exit, abandon, crash, resume, guardrail profile. Draw it before coding it.

3. **Solve agent over-help** — Define what the tutorial agent CAN and CANNOT do. Can it run commands? Only verification commands? Can it write files? Only tutorial state files? This needs a guardrail profile specific to tutorial mode.

4. **Isolate the "Agent Teams" tutorial** — It has different requirements (spawn permissions, agent cleanup) from standard tutorials. Don't let it complicate the simple path.

5. **Write 2 concrete tutorials before abstracting** — "Write and run a first pytest" and "Understand pixi environments" are good candidates. Extract the format from reality, not imagination.
