# Skeptic Review: Content Lock (Phase-Gated MD Files)

## The Idea

The agent only receives the markdown file for its current phase. It can't read ahead because the next phase's file isn't in its context. This syncs agent behavior (what it knows how to do) with guardrail checkpoints (what it's allowed to do).

---

## Question 1: Does This Actually Prevent Skipping Ahead?

**No. Content lock is not a prevention mechanism. It's an attention-focusing mechanism.**

A Claude agent can always:
- Infer what comes next from context ("I just finished writing code, probably testing is next")
- Read files on disk (the agent has the Read tool — if per-phase files exist on the filesystem, the agent can read them all)
- Ask another agent what the next phase is
- Use general knowledge about software development workflows

Content lock doesn't prevent any of this. What it does:

**It removes the temptation and the distraction.** If the agent's system prompt says "here's your step, here's what to verify, here's what you can do," it won't spontaneously jump to step 5. Not because it can't, but because it has no reason to. The agent optimizes for its current instruction. If the current instruction is phase 4, it does phase 4.

This is the same reason COORDINATOR.md says "EVERY TURN: Re-read this file." Not because the Coordinator can't remember — it's because re-reading focuses attention on the current phase.

**The honest framing:** Content lock is a prompt engineering technique, not a security boundary. It works because LLMs are instruction-followers. They do what they're told, especially when what they're told is specific and actionable. Giving them only the current phase's instructions makes them very good at the current phase and unaware of future phases.

**For tutorials, this is sufficient.** The tutorial-runner agent doesn't need to be adversarially prevented from reading step 5. It needs to be focused on step 3. Giving it only step 3's markdown achieves this.

**The real enforcement is the guardrail checkpoint gate** — even if the agent reads ahead and tries to advance, the `advance_to_next_step()` function denies it unless verification passes. Content lock and guardrail lock work together: content lock prevents the agent from wanting to skip; guardrail lock prevents it from being able to skip.

---

## Question 2: Does This Mean Splitting COORDINATOR.md?

**This is the sharpest question. The answer reveals whether content lock is a real pattern or a tutorial-only trick.**

### Current state: COORDINATOR.md has ALL phases

The Coordinator reads COORDINATOR.md once and has all 9 phases in context. It self-manages which phase it's in by reading STATUS.md. This works because:
- The Coordinator is a trusted, long-running agent
- It needs the full picture to make coordination decisions
- Phase transitions involve user checkpoints (human in the loop)

### Would splitting help?

Imagine per-phase Coordinator files:

```
AI_agents/project_team/
  coordinator/
    phase-0-vision.md
    phase-1-setup.md
    phase-2-spawn.md
    phase-3-specification.md
    phase-4-implementation.md
    phase-5-testing.md
    ...
```

**Benefits:**
- Each file is shorter and more focused (~20-40 lines vs. 276 lines)
- The Coordinator only sees its current phase's instructions
- Phase transitions become explicit: "read phase-5-testing.md now"
- Content lock syncs with phase-scoped guardrails — the Coordinator's instructions match what the guardrails allow

**Costs:**
- The Coordinator loses the overview. It can't look at phase 5 to understand why phase 4 matters. Cross-phase coordination suffers.
- The Coordinator must be told to read the next file at each transition. Who tells it? A meta-instruction in the current phase file ("when done, read phase-5-testing.md")? Then the Coordinator has to know the next file name, which means it has the sequencing information anyway.
- The "EVERY TURN: Re-read this file" pattern breaks — which file? The current phase file? Then you need a pointer: "re-read the file for your current phase as listed in STATUS.md."

**My assessment: Don't split COORDINATOR.md.** The Coordinator is a different role than a tutorial-runner. It needs the full phase overview because it's the orchestrator. Content lock is for specialist agents (implementers, test engineers, tutorial runners) who should focus on one phase at a time.

**But this reveals the real pattern:** Content lock isn't about the Coordinator. It's about the agents the Coordinator spawns. The Coordinator already does this — when spawning an Implementer, it gives them a focused prompt:

```
"You are Implementer. Write code for X. Follow patterns in specification/composability.md."
```

The Implementer doesn't receive COORDINATOR.md. It doesn't know about phases 0-3 or 6-9. It only knows phase 4 (implementation). **Content lock already exists for spawned agents.** The insight is to formalize it and sync it with guardrails.

---

## Question 3: How Does the Coordinator Know When to Advance?

**The Coordinator knows when phase 4 is done because agents report back, not because it reads phase 5.**

Current flow:
1. Coordinator spawns Implementers with focused prompts
2. Implementers write code and report back: "Implementation complete. Files created: X, Y, Z."
3. Coordinator reads reports. Decides: "Implementation done. Time for testing."
4. Coordinator reads its own COORDINATOR.md, finds Phase 5 instructions, spawns TestEngineer.

The Coordinator doesn't need to see phase 5 to know phase 4 is done. It needs to see agent reports and its own coordination instructions.

**For tutorials, the pattern is different but simpler:** The tutorial engine (not an agent) manages transitions. When verification passes, the engine loads the next step's markdown and updates the agent's context. The agent doesn't decide when to advance — the engine does.

```
Step 3 verification passes
  → Engine loads step-04.md
  → Engine updates agent context: "You are now on step 4. Here's the content."
  → Agent sees only step 4
```

**Who gives the agent the next file?** The tutorial engine. It's the orchestrator for tutorials, just as the Coordinator is the orchestrator for team projects. The engine reads the manifest, knows the step sequence, and feeds one step at a time to the agent.

---

## Question 4: Content Lock — Real Security or Just Obscurity?

**Just obscurity. And that's fine.**

Security model:
- **Content lock** prevents the agent from *wanting* to skip ahead (attention control)
- **Guardrail checkpoint** prevents the agent from *being able to* skip ahead (enforcement)

Content lock is defense in depth, not the primary defense. It reduces the probability that the guardrail checkpoint even needs to fire. In practice, if the agent only sees step 3's instructions, it will never attempt to advance to step 4 unprompted. The checkpoint guardrail is there for the edge case where it does.

**This is the same security model as the existing team workflow:**
- Role files (IMPLEMENTER.md) tell the agent what it should do (attention control)
- Guardrail rules (R04, R05) enforce what it can't do (enforcement)
- An Implementer doesn't push to git because (a) its role file doesn't mention pushing and (b) R04 blocks it. Both mechanisms matter. Neither alone is sufficient.

For tutorials:
- Step markdown tells the agent what to help with (attention control)
- Checkpoint guardrail blocks advancement without verification (enforcement)
- The agent doesn't skip steps because (a) it only sees the current step and (b) the engine won't advance without verification. Both mechanisms matter.

**Is this "just obscurity"? Technically yes — the agent could use the Read tool to find tutorial files on disk. Practically no — an agent focused on "help the user generate an SSH key" has zero reason to go browsing the filesystem for step-05.md.**

---

## Question 5: What's the Phase Transition Mechanism?

This is the most important question because it determines the actual architecture.

### For Tutorials

```
                    ┌──────────────┐
                    │ Tutorial     │
                    │ Engine       │
                    │              │
  User action ───► │ 1. Verify    │
                    │ 2. Advance   │
                    │ 3. Load next │
                    │    step MD   │
                    │ 4. Update    │◄──── phase_state.json
                    │    agent ctx │
                    └──────┬───────┘
                           │
                           ▼
                    Agent sees new
                    step content
```

The engine owns the transition. Concretely:

1. Agent calls `verify_current_step()` (or the engine auto-runs verification after detecting user action)
2. Check passes → engine writes step completion to progress JSON
3. Engine loads next step's markdown file
4. Engine updates `phase_state.json` to `tutorial:first-pytest:step-02`
5. Engine sends new context to agent (system prompt update with step 2's content)
6. Guardrails now scope to the new phase

**The agent never reads step files directly.** The engine reads them and injects the content into the agent's context. This is how content lock works mechanically — it's not file permissions, it's context injection.

**Implementation detail:** How does the engine "send new context" to a running agent? Options:

- **Option A: Agent re-reads on each turn.** The engine writes the current step content to a well-known file (e.g., `tutorials/_current_step.md`). The agent's role file says "read `tutorials/_current_step.md` every turn." The engine updates this file on transition. Simple but relies on the agent following instructions to re-read.

- **Option B: Engine runs inside the agent's conversation.** The engine is a Python module the agent imports. The agent calls `engine.get_current_step()` and `engine.verify()`. The engine returns markdown content and check results. The agent never touches step files. Clean, but requires the agent to use Python tool calls.

- **Option C: Engine is a separate process/command.** The agent runs `python -m tutorials check` and `python -m tutorials advance`. The engine is a CLI. Output is the next step's content. Simple, decoupled, testable.

**Option C is the best fit for this codebase.** The guardrail system uses standalone Python scripts (hooks). The hints system uses a Python module called by ClaudeChic. A tutorial CLI command is consistent with both patterns and doesn't require the agent to import anything.

```bash
# Agent runs these commands:
python -m tutorials status          # → current step, progress
python -m tutorials verify          # → CheckResult (passed/failed + evidence)
python -m tutorials advance         # → next step content (or error if unverified)
python -m tutorials content         # → current step markdown
```

### For Team Project Phases

The Coordinator is the transition authority:

1. Coordinator reads agent reports, decides phase is complete
2. Coordinator updates STATUS.md: "Current Phase: Phase 5"
3. Coordinator runs `python -m phase_state set project:5` (or equivalent)
4. `phase_state.json` updates → guardrails now scope to phase 5
5. Coordinator reads its own COORDINATOR.md Phase 5 section and spawns TestEngineer

No content lock for the Coordinator — it has the full file. Content lock happens downstream when it spawns agents with focused prompts.

### For Both: phase_state.json Is the Sync Point

```
phase_state.json ◄── written by: Coordinator (project) or Tutorial Engine (tutorial)
       │
       ├──► read by: guardrail hooks (scope rules)
       ├──► read by: hints triggers (TutorialStepActive etc.)
       └──► read by: tutorial engine (resume on reconnect)
```

One file, multiple readers, one writer per mode. Clean.

---

## What's Actually New Here?

Content lock as described isn't a new mechanism. It's a name for three things that already exist or are already planned:

1. **Spawning agents with focused prompts** — The Coordinator already does this. Content lock formalizes it: "give the agent only its current phase's content."

2. **Tutorial engine managing step content** — Already in the architecture. The engine loads manifests and presents steps. Content lock is just saying "the engine gives the agent one step at a time, not the whole manifest."

3. **Phase-scoped guardrails** — Already specified. Content lock adds: "the agent's instructions match what the guardrails allow." This is a consistency property, not a new mechanism.

**The insight is real but the mechanism is free — it falls out of the existing design.** If the tutorial engine already loads one step at a time and already updates phase_state.json, then content lock is automatic. You don't build it; it's a consequence of building the engine correctly.

---

## What Could Go Wrong

### Failure Mode 1: Agent reads ahead via Read tool

The agent uses the Read tool to look at `tutorials/content/first-pytest/step-03.md` while on step 1. Content lock is bypassed.

**Severity: LOW.** The agent has no reason to do this. Its instructions say "help with step 1." The guardrail checkpoint still prevents advancement. The worst case: the agent spoils the surprise of what's in step 3. For a pytest tutorial, that's irrelevant.

**Mitigation (if needed):** A guardrail rule blocking Read access to tutorial step files not matching the current step. Possible but overkill for v1.

### Failure Mode 2: Context window fills up

If the engine injects step content via system prompt, and steps are long, the agent's context window accumulates all previous steps' content (from conversation history). By step 5, the agent has seen steps 1-4 in its history.

**Severity: LOW.** This is information the agent has already processed. It doesn't cause behavioral problems — the agent still focuses on the current step's instructions. Compaction may eventually drop old step content, which is actually desirable.

### Failure Mode 3: Engine fails to update phase_state.json

The engine advances the step but crashes before writing phase_state.json. Now the agent sees step 2 content but guardrails still scope to step 1.

**Severity: MEDIUM.** The guardrail might block an action that step 2 requires but step 1 didn't. The user sees a confusing guardrail denial.

**Mitigation:** Update phase_state.json BEFORE presenting the new step content. If the write fails, don't advance. Atomic: phase state update and step presentation are a transaction.

---

## Summary

| Question | Answer |
|---|---|
| Does content lock prevent skipping? | No. It removes the motivation to skip. The guardrail checkpoint is the actual enforcement. |
| Split COORDINATOR.md? | No. The Coordinator needs the full overview. Content lock is for spawned specialist agents and tutorial runners. |
| How does the Coordinator know when to advance? | Agent reports, not by reading the next phase. Same as today. |
| Real security or obscurity? | Obscurity — and that's the right design. Defense in depth with guardrail enforcement as the hard boundary. |
| Phase transition mechanism? | Tutorial engine owns transitions (verify → update phase_state.json → load next step → update agent context). CLI interface: `python -m tutorials verify/advance/content`. |
| Is this new? | Not really. It's a name for things the existing design already implies. It falls out of building the tutorial engine correctly. |

**Verdict:** Content lock is a good prompt engineering discipline, not a new mechanism to build. It's the principle: "give agents the minimum context needed for their current task." The existing architecture already supports it. The real enforcement is guardrail checkpoints. Call it out as a design principle in the tutorial-runner role file, not as a separate infrastructure component.
