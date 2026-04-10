# Terminology Specification — Tutorial System

> **Canonical home** for all tutorial-system domain terms.
> Other documents MUST reference this file, not redefine terms.

---

## Core Terms

### Tutorial
A self-contained, interactive guided walkthrough that teaches a user how to complete a specific real-world task (e.g., "SSH into a cluster," "Set up Git SSH keys"). A tutorial combines **markdown content**, a **tutorial-runner agent**, **hints**, and **guardrails** into a single coherent experience. A tutorial is NOT static documentation — it requires interactivity and verification. See also: **agent-team tutorial** for the special category where multi-agent interaction is the teaching content itself.

### Tutorial Mode
A distinct operational mode of the template in which normal project work is suspended and a selected **tutorial** is active. Entering tutorial mode changes what agents are spawned, what guardrails are enforced, and what hints are surfaced. Only one tutorial runs at a time within tutorial mode.

### Tutorial Step
A single, discrete unit of work within a **tutorial**. Each step has:
- **Instructions** — what the user should do (markdown content)
- **Hints** — contextual nudges if the user is stuck
- **A checkpoint** — verification that the step was actually completed

Steps are ordered sequentially. A user must pass a step's **checkpoint** before advancing to the next step.

### Tutorial Content
The markdown files that provide the instructional material for a **tutorial**. Tutorial content is passive (read-only text/examples). It is distinct from **hints** (reactive nudges) and **guardrails** (enforcement/verification).

---

## Verification & Safety Terms

### Checkpoint
A programmatic verification gate at the end of a **tutorial step** that proves the step was actually completed — not just claimed as done. A checkpoint runs a concrete check (e.g., `ssh -T git@github.com` returns success, `git remote -v` shows a GitHub URL). Checkpoints are what distinguish this system from static documentation.

> **Disambiguation:** The term "checkpoint" also exists in ClaudeChic for session rewind/restore. In tutorial-system context, "checkpoint" ALWAYS means a step-completion verification gate. If referring to the ClaudeChic feature, use "session checkpoint" or "rewind checkpoint" explicitly.

### Tutorial Guardrail
A guardrail rule that is active ONLY during **tutorial mode** to prevent the user (or agent) from making mistakes that would derail the tutorial. Tutorial guardrails are layered ON TOP of the existing project guardrails — they do not replace them.

Examples:
- Preventing `rm -rf ~/.ssh` during an SSH-setup tutorial
- Blocking writes to production config during a Git-setup tutorial

> **Relationship to existing guardrails system:** Tutorial guardrails use the same composable guardrail engine (`.claude/guardrails/`). They are an additional guardrail **role** or **scope**, not a separate system.

### Checkpoint Guardrail
A specific type of **tutorial guardrail** that blocks advancement to the next **tutorial step** until the **checkpoint** verification passes. This is the enforcement mechanism that prevents an agent from claiming "done" without proof.

---

## Agent & Interaction Terms

### Tutorial-Runner Agent
The single agent that executes a **tutorial's** steps, manages progression, and triggers **checkpoint** verifications. All standard tutorials use exactly one tutorial-runner agent. It reads the **tutorial manifest**, presents **tutorial content**, surfaces **hints**, enforces step ordering, and invokes **checkpoints** before advancing.

> **Key constraint:** One runner per tutorial. The tutorial-runner agent is NOT a team — it is a single agent with a focused role. Contrast with **agent-team tutorial**, where additional agents are spawned as *teaching content*, not as additional runners.

### Agent-Team Tutorial
A special tutorial category where the tutorial content itself involves spawning and managing multiple agents — teaching the multi-agent workflow by actually doing it (e.g., a "Working with Agent Teams" tutorial). In an agent-team tutorial, the **tutorial-runner agent** still manages progression and checkpoints, but the **tutorial steps** instruct the user to spawn, coordinate, and interact with additional agents as the learning objective.

> **Disambiguation:** In a standard tutorial, only the **tutorial-runner agent** is active. In an agent-team tutorial, additional agents exist but they are part of the *lesson content*, not part of the tutorial execution machinery. The tutorial-runner agent remains the sole orchestrator of step progression and checkpoint verification.

### Hint (in tutorial context)
A contextual, reactive nudge surfaced to the user when they appear stuck on a **tutorial step**. Tutorial hints integrate with the existing hint engine (`/hints/`). They are triggered by inactivity, repeated errors, or explicit user request — NOT displayed all at once upfront.

> **Relationship to existing hints system:** Tutorial hints are delivered through the same hint engine and toast mechanism already in production. They are additional hint definitions scoped to tutorial steps, not a parallel system.

---

## Structural Terms

### Tutorial Registry
The index of all available tutorials. When a user enters **tutorial mode**, they select from this registry. Each entry includes the tutorial's name, description, difficulty, estimated time, and prerequisites.

### Tutorial Manifest
The configuration file for a single **tutorial** that declares its **steps**, **checkpoints**, required **guardrails**, **hints**, and **tutorial-runner agent** configuration. For **agent-team tutorials**, the manifest also declares what additional agents the tutorial steps will spawn as teaching content. This is the single source of truth for a tutorial's structure.

### Tutorial Selector
The interface (command or prompt) through which a user picks a tutorial from the **tutorial registry** to begin. This is the entry point into **tutorial mode**.

---

## Terms to AVOID (Synonym Control)

| DO NOT USE | USE INSTEAD | Reason |
|------------|-------------|--------|
| lesson | **tutorial** | "Lesson" implies passive learning; "tutorial" implies guided doing |
| walkthrough | **tutorial** | Synonym — one name only |
| task (for a tutorial unit) | **tutorial step** | "Task" is overloaded (project tasks, agent tasks); "step" is scoped to tutorials |
| verification / validation (for step gates) | **checkpoint** | One name for the concept |
| safety rail / safety net | **guardrail** | Matches existing system naming |
| guide / guided mode | **tutorial mode** | One name for the mode |
| phase (for tutorial units) | **tutorial step** | "Phase" is used in the project-team workflow; avoid collision |
| prompt / nudge (for contextual help) | **hint** | Matches existing system naming |
| tutorial agent team | **tutorial-runner agent** | Standard tutorials use ONE agent, not a team. The old term implied multiple agents |
| runner / executor (for the tutorial agent) | **tutorial-runner agent** | Full compound name required to avoid ambiguity |
| multi-agent tutorial | **agent-team tutorial** | "Agent-team" mirrors the project-team naming; "multi-agent" is vague |

---

## Term Relationships (Quick Reference)

```
Tutorial Mode
 └── Tutorial (selected from Tutorial Registry)
      ├── Tutorial Manifest (declares structure)
      ├── Tutorial-Runner Agent (single agent, manages progression)
      └── Tutorial Steps (ordered sequence)
           ├── Tutorial Content (markdown instructions)
           ├── Hints (contextual nudges)
           ├── Checkpoint (verification gate)
           └── Tutorial Guardrails
                └── Checkpoint Guardrail (blocks advancement until checkpoint passes)

 Special category:
 └── Agent-Team Tutorial
      ├── Tutorial-Runner Agent (still the sole orchestrator)
      └── Tutorial Steps that spawn additional agents (as teaching content)
```

---

## Open Questions for Composability Lead

1. **"Step" vs numbered sections** — Should steps be flat (step 1, 2, 3…) or can tutorials have sub-steps / nested structure? Recommend: flat only, to keep the model simple.
2. **Guardrail scope naming** — What should the guardrail role/scope be called for tutorial-specific rules? Propose: `tutorial:<tutorial-id>` as the scope identifier.
3. **Checkpoint failure behavior** — Should a failed checkpoint simply block, or also surface a specific **hint**? Propose: both — block AND auto-trigger a checkpoint-failure hint.
