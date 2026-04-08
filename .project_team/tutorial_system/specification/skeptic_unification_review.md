# Skeptic Review: Phase State Unification

## The Claim

Verification, guardrail scoping, and mode are all manifestations of a single concept: **phase state**. The system is always in a phase. The phase determines what's allowed (guardrails), what must be proven to advance (verification), and what context is active (mode).

## Is It Real or Forced?

**It's real.** But it's a narrower unification than it first appears. Let me show why.

---

## Mapping the Existing System to Phase State

### The Coordinator's Phases (COORDINATOR.md)

The team project workflow has 9 phases:

| Phase | What Happens | What's Allowed | What Gates Advancement |
|---|---|---|---|
| 0: Vision | Clarify what user wants | Free discussion | User approves vision |
| 1: Setup | Create project state dirs | File creation | Dirs exist |
| 2: Leadership Spawn | Spawn 4 agents | Agent spawning | All 4 visible in list_agents |
| 3: Specification | Leadership reviews, axis deep-dives | Writing to specification/ | User approves spec |
| 4: Implementation | Implementers write code | Code writing, NO full test suite | Leadership approves |
| 5: Testing | TestEngineer runs tests | Full test suite allowed | All tests pass |
| 6: Sign-Off | All agents confirm | Read-only review | All agents say READY |
| 7: Integration | Create launch script | Script creation | Script works |
| 8: E2E Checkpoint | User decides on E2E tests | Testing | User decides |
| 9: Final Sign-Off | Present to user | Presentation | User approves |

### Where Phase State Already Governs Behavior

**Guardrails:** R04 (`git push` block) uses `block: [Subagent]` — only Coordinator can push. This is role-scoped, not phase-scoped. But the user's insight is: R01 (pytest output block) is ALWAYS on. In the phase model, R01 should be:
- Phase 4 (Implementation): DENY full test suite (agents should write code, not test yet)
- Phase 5 (Testing): ALLOW full test suite (this is literally the testing phase)

Today R01 is unconditional. The workaround is agents writing to `.test_runs/` even in Phase 5. Phase-scoping R01 would remove that friction.

**Verification:** Phase transitions in COORDINATOR.md are **already verification gates**, they're just informal:
- Phase 2 → 3: "VERIFY: Run `mcp__chic__list_agents`. Confirm all 4 Leadership agents appear."
- Phase 4 → 5: "Exit when all Leadership approve." (approval = verification)
- Phase 5 → 6: "Run tests. Fix failures. Exit when all pass." (tests passing = verification)

These are prose instructions to the Coordinator agent. They're not enforced programmatically. The Coordinator can skip them because nothing prevents it.

**Mode:** The session marker (`ao_<PID>`) is a binary mode flag: team mode on/off. It doesn't carry phase information. Extending it to include phase would turn it into a state machine.

### The Unification

```
Session Marker (today):     {"coordinator": "AI_PROJECT_TEMPLATE"}
Session Marker (unified):   {"coordinator": "AI_PROJECT_TEMPLATE", "phase": 4, "project": "tutorial_system"}
```

With phase in the session marker:
- Guardrail hooks read `phase` and apply phase-scoped rules
- Phase transitions require verification checks to pass
- Tutorial mode is just a phase (or a parallel phase space)

---

## Where the Unification Works Cleanly

### 1. Phase-Scoped Guardrail Rules

This is the strongest application. Today:

```yaml
- id: R01
  name: pytest-output-block
  trigger: PreToolUse/Bash
  enforcement: deny
  detect:
    type: regex_match
    pattern: '(?:^|&&|\|\||;|\brun\s+)\s*pytest\b'
  message: "Full test suite must save output..."
```

With phase scoping:

```yaml
- id: R01
  name: pytest-output-block
  trigger: PreToolUse/Bash
  enforcement: deny
  scope:
    phases: [0, 1, 2, 3, 4, 6, 7, 8, 9]  # NOT phase 5 (testing)
  detect:
    type: regex_match
    pattern: '(?:^|&&|\|\||;|\brun\s+)\s*pytest\b'
  message: "Full test suite must save output..."
```

Or inversely:

```yaml
  scope:
    not_phases: [5]  # Exempt during testing phase
```

This is real, concrete, and immediately useful. The Coordinator already tracks phase in STATUS.md. Making it machine-readable in the session marker lets guardrails respond to it.

### 2. Tutorial as a Phase Space

A tutorial is a sequence of phases with verification gates. The team project workflow is a sequence of phases with verification gates. They're structurally identical:

| | Team Project | Tutorial |
|---|---|---|
| Phase definition | COORDINATOR.md phases 0-9 | tutorial.yaml steps |
| Phase state | STATUS.md "Current Phase" | Tutorial progress JSON |
| Phase transition gate | "User approves" / "tests pass" | Checkpoint verification |
| Phase-scoped rules | (proposed) R01 exempt in phase 5 | (proposed) tutorial guardrails per step |
| Mode signal | Session marker | (proposed) mode field in session marker |

The unification says: both are instances of **a workflow with phases, where phases have scoped guardrails and verification-gated transitions**.

### 3. Verification as Phase Transition Condition

The `Verification` protocol (`check(ctx) → VerificationResult`) works for both:
- Tutorial: "Did the user generate the SSH key?" → advance to next step
- Team project: "Did all tests pass?" → advance to phase 6
- Team project: "Are all 4 agents spawned?" → advance to phase 3

The `VerificationResult` with evidence is valuable in both: "Tests passed: 47/47, 0 failures" is the same pattern as "SSH key exists: /home/user/.ssh/id_ed25519."

---

## Where the Unification Breaks Down

### Problem 1: Team Project Phases Are Agent-Managed, Not System-Enforced

The Coordinator reads STATUS.md and follows COORDINATOR.md's instructions. Phase transitions happen when the Coordinator *decides* they happened by updating STATUS.md. There is no programmatic enforcement.

If you want phase-scoped guardrails, something must write the current phase to the session marker. Who does that?

- **Option A: Coordinator writes it.** The Coordinator updates the session marker when changing phases. This is simple but trust-based — the Coordinator could write phase 5 to bypass R01.
- **Option B: Verification gates enforce it.** Phase can only advance when verification checks pass. The system updates the marker, not the agent. This requires a phase-transition API: `advance_phase(current=4, next=5) → runs verifications → updates marker`.

Option B is the clean design, but it means building a **phase transition engine** that wraps the Coordinator's workflow. Today the Coordinator is autonomous — it reads instructions and follows them. A phase engine would constrain the Coordinator's freedom. That's a significant architectural change.

**Risk:** The Coordinator's phases are loosely defined. Phase 3 ends when "User approves spec." How do you programmatically verify "user approved"? Phase 4 ends when "all Leadership approve." How do you verify "Leadership approved"? Not all phase transitions have machine-verifiable conditions. Many require human judgment (user checkpoints 👤).

This doesn't break the unification — it means some phases gate on `ManualConfirm` (like tutorial steps that can't be automated). But it does mean the phase engine can't be fully automated for team projects. Some gates are just "someone said yes."

### Problem 2: Team Project Phases Are Linear; Tutorials Might Branch

The Coordinator's phases are strictly sequential: 0 → 1 → 2 → ... → 9. No branching. No skipping (well, phases 7-8 are semi-optional but the coordinator still passes through them).

The tutorial spec proposes `branching` progression. If phase state is the unified concept, the phase engine needs to support branching. That's more complex than a simple integer phase counter.

**But:** The tutorial spec's branching is barely specified and I've already recommended deferring it. If both systems are linear-with-gates, the unification is clean.

### Problem 3: Phase Spaces Are Parallel, Not Nested

A team project in phase 4 could have an agent running a tutorial. Is the tutorial a sub-phase of phase 4? A parallel phase space? A mode override?

Options:
- **Parallel phase spaces:** `{project_phase: 4, tutorial_phase: "step-03"}`. Each has its own guardrail scope. Rules check one or both.
- **Nested phases:** Tutorial is a sub-state of the project phase. Complicates the model significantly.
- **Mutually exclusive:** Can't run a tutorial while in a project phase (tutorial mode suspends project work). Simplest but most restrictive.

For v1, mutually exclusive is fine (you're either doing project work or a tutorial, not both). But the unified model should accommodate parallelism in the data structure even if v1 doesn't use it.

### Problem 4: Phase Granularity Mismatch

Team project phases are coarse (9 phases, each lasting hours/days). Tutorial steps are fine-grained (5-10 steps, each lasting minutes). If guardrails scope by phase, the team project gets 9 rule configurations. Tutorials get per-step rule configurations. The guardrail scoping mechanism must handle both granularities without over-complicating rules.yaml.

**This is solvable** with a namespace convention:
```yaml
scope:
  phase: "project:4"          # Team project phase 4
scope:
  phase: "tutorial:ssh-cluster:step-03"  # Tutorial step
scope:
  phase: "project:*"          # Any team project phase (= team mode is active)
```

But it turns a simple integer field into a hierarchical namespace. Whether that's justified depends on how many rules actually need phase scoping.

---

## Concrete Test: Rewrite Existing Rules with Phase Scoping

Let me check if the existing R01-R05 rules actually benefit from phase scoping:

| Rule | Today | With Phase Scoping | Benefit? |
|---|---|---|---|
| R01: pytest-output-block | Always on | Exempt in phase 5 (testing) | **YES** — removes friction during testing phase. Agents can run pytest normally in phase 5. |
| R02: pip-install-block | Always on | Always on (pixi is always correct) | **NO** — pip install is wrong in every phase. |
| R03: conda-install-block | Always on | Always on (pixi is always correct) | **NO** — same as R02. |
| R04: subagent-push-block | Team mode, Subagent only | Could be phase-scoped but role scope is sufficient | **MARGINAL** — role scope already works. Phase scope adds nothing. |
| R05: subagent-guardrail-config-block | Team mode, Subagent only | Same as R04 | **MARGINAL** |

**Result: 1 out of 5 existing rules benefits from phase scoping.** R01 is the clear winner. R02-R03 are universal. R04-R05 are already adequately scoped by role.

For tutorial guardrails (the proposed T01, T-SSH-001, etc.), phase scoping is essential — they only make sense during specific tutorials and steps. But those rules don't exist yet.

---

## The Honest Assessment

### What's genuinely unified:
1. **Guardrail scoping by phase** — Real and useful. The session marker can carry phase info. Rules can scope by phase. R01 benefits today. Tutorial rules benefit tomorrow.
2. **Verification as phase transition gate** — Real pattern. Both team projects and tutorials use "check condition → advance." The `Verification` protocol serves both.

### What's forced:
1. **"Phase state is the foundation of everything"** — Phase state is ONE dimension of the guardrail scoping model. Role is another (and it already works). Content type could be another. Elevating phase to THE foundational concept overstates its role. The guardrail system's real foundation is `rules.yaml + generate_hooks.py` — phase is just a new field in the scoping mechanism.
2. **Team project phase enforcement** — The Coordinator's phases are instruction-following, not system-enforced. Making them system-enforced is a big change that requires a phase transition API and verification of conditions that are sometimes subjective ("user approved").

### What actually simplifies:
1. **Session marker becomes a state carrier** — Today: `{"coordinator": "name"}`. Proposed: `{"coordinator": "name", "phase": "project:4"}`. This is a clean, small extension. Guardrail hooks read it. Rules scope on it.
2. **One scoping mechanism for roles AND phases** — Instead of `block: [Subagent]` being a separate mechanism from mode-aware scoping, unify into a `scope` field: `scope: {role: Subagent}` and `scope: {phase: "project:4"}` use the same code path.
3. **Tutorial guardrails fall out naturally** — No new "tutorial mode" concept. A tutorial is just a phase space. Tutorial guardrails scope to tutorial phases.

### What actually breaks / gets complicated:
1. **Phase transition authority** — Who writes the phase to the session marker? If agents do it, it's trust-based. If a phase engine does it, you need to build a phase engine.
2. **Rules.yaml complexity** — Adding `scope: {phase: ...}` to rules means `generate_hooks.py` needs to emit phase-checking code. The generated hooks get more complex. Today they're already ~100+ lines each.
3. **Parallel phase spaces** — If a tutorial runs during a project phase, the session marker needs to carry both. The scoping logic needs to check either or both.

---

## Minimum Viable Unification

If the goal is to validate the phase state unification without over-building:

### Step 1: Extend session marker with phase field
```json
{"coordinator": "AI_PROJECT_TEMPLATE", "phase": "project:4"}
```
One field. Written by the Coordinator when it transitions phases. Read by guardrail hooks.

### Step 2: Add `scope.phase` to rules.yaml schema
```yaml
- id: R01
  scope:
    not_phase: "project:5"
  # ... rest of rule unchanged
```

### Step 3: Modify `generate_hooks.py` to emit phase checks
When a rule has `scope.phase` or `scope.not_phase`, the generated hook reads the session marker's `phase` field and skips/applies the rule accordingly.

### Step 4: Refactor R01 as proof
Make R01 exempt in phase 5. This validates the mechanism with a real rule that has a real benefit.

### Step 5: Tutorial phases use the same mechanism
A tutorial sets `phase: "tutorial:ssh-cluster:step-02"` in the session marker. Tutorial guardrails scope to `phase: "tutorial:ssh-cluster:*"`.

**Total cost:** ~100-200 lines of changes to `generate_hooks.py` + session marker write logic. No new modules. No phase engine. No verification-gated transitions (that's a v2 concern).

**What this proves:** Phase scoping works for both team project rules and tutorial rules through the same mechanism. The "phase state unification" is real at the guardrail level.

**What this defers:** Programmatic phase transition enforcement (the Coordinator still manages phases manually). Verification-gated transitions (verification still runs, but enforcement is by agent instruction, not by system gate). Parallel phase spaces (tutorial mode is mutually exclusive with project phases in v1).

---

## Verdict

| Question | Answer |
|---|---|
| Is the unification real? | **Yes, at the guardrail scoping level.** Phase-scoped rules are a genuine generalization that serves both team projects and tutorials. |
| Is it forced? | **Partially, at the verification level.** Verification as a phase transition gate is a real pattern, but enforcing it programmatically for team projects requires a phase engine the system doesn't have and may not need. |
| Does the existing workflow map to this? | **The data model maps cleanly** (phases are already numbered, transitions are already described). **The enforcement model doesn't map** — the Coordinator follows instructions, it's not constrained by a system. |
| What breaks if we unify? | Nothing breaks. The risk is over-building: a phase transition engine for team projects that the Coordinator doesn't need because it's already autonomous. |
| What simplifies? | Guardrail scoping: one `scope` field handles roles, phases, and tutorials. No separate "tutorial mode" concept. R01 gets cleaner. Tutorial guardrails fall out naturally. |

**Recommendation:** Build the minimum viable unification (steps 1-5 above). It's ~200 lines of changes, validates the concept with R01, and provides the scoping mechanism tutorials need. Defer the phase transition engine — let the Coordinator keep managing phases manually. If programmatic enforcement proves necessary later, the session marker already carries the phase, so adding enforcement is incremental.
