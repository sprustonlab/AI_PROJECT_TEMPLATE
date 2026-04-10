# Fresh Skeptic Review — Complete Spec Package

Reading everything with fresh eyes against the user's original request and the actual codebase.

---

## The Big Question: Is This Over-Engineered?

**Yes. Significantly.**

The user asked for:
> Add a "tutorial" feature to the template that combines md files, a team of agents, hints, and guardrails in a new mode to help users complete a task.

What we've specified is:
- A 6-axis composability framework (Content × Progression × Verification × Guidance × Safety × Presentation)
- A `Verification` protocol with 5 concrete implementations, a `VerificationContext` sandbox, and a `VerificationResult` evidence system
- A tutorial-aware extension of `ProjectState` with `TutorialContext`
- 3 new `TriggerCondition` implementations for the hints pipeline
- A new `HintLifecycle` implementation (`ShowUntilStepComplete`)
- A `tutorial.yaml` manifest schema with 15+ fields
- A step markdown format with custom fence tags and HTML comment markers
- An `AgentContext` system prompt builder
- YAML-to-HintSpec conversion pipeline
- Scoped guardrail rules with per-step activation
- An auto-discovery mechanism for tutorial content directories

This is a specification for a **framework**. The user asked for a **feature**.

### The Smell

Count the new Python files implied by these specs: `_engine.py`, `_types.py`, `_state.py`, `_verification.py`, plus tutorial content files, plus `tutorial.yaml` schema validation, plus guardrail rule additions, plus hints system modifications. That's at minimum 4-5 new modules plus modifications to 3 existing systems (hints, guardrails, ProjectState).

Compare to what Rustlings is — the gold standard from our own prior art research. Rustlings is ~2,000 lines of Rust total. It does: manifest parsing, file watching, exercise compilation/testing, hint display, and progress tracking. That's the whole thing.

Our specification describes more infrastructure than Rustlings has code.

### What Went Wrong

The composability analysis is technically correct — these ARE orthogonal axes. But the specification confused "orthogonal concerns exist" with "each concern needs a formal axis with protocols, seam objects, and frozen dataclasses." Not every axis needs the same level of engineering.

---

## What v1 Actually Needs

Let me work backwards from the user's actual scenario: "A user types a command, picks 'SSH into my cluster,' and gets a guided, interactive walkthrough."

For this to work, you need exactly:

1. **A way to define a tutorial** — `tutorial.yaml` + step markdown files. ✅ The content spec is good here.

2. **A way to run a tutorial** — A tutorial-runner agent that reads the manifest, presents steps, and tracks progress. The engine doesn't need 6 axes. It needs: load manifest → present step → check verification → advance.

3. **A way to verify steps** — Run a command, check the output. That's `CommandOutputCheck`. Maybe `FileExistsCheck`. Maybe `ManualConfirm`. You do NOT need `CompoundCheck`, `ConfigValueCheck` (which is just `CommandOutputCheck` with a trim), `VerificationContext` with 5 callable fields, or a registry pattern for deserialization. You need a function: `run_command_and_check_output(command, pattern) → (passed, output)`.

4. **Hints that fire when the user is stuck** — The existing hints pipeline works. Add tutorial hints to `get_hints()`. ✅ The guidance spec handles this correctly.

5. **Guardrails that prevent mistakes** — Add scoped rules to `rules.yaml`. The existing guardrail system handles enforcement. ✅ This is mostly mechanical.

6. **State persistence** — A JSON file tracking which steps are done. Simple dict: `{step_id: {completed: bool, evidence: str}}`.

### What v1 Does NOT Need

- **`VerificationContext` as a frozen dataclass with callable fields** — Just pass the verification function a working directory and a timeout. The callable-injection pattern is for testability, which matters, but you can inject one function (`run_command`), not five.

- **`CompoundCheck` with AND/OR composition** — Write two separate checks. If both need to pass, check both. You're not building a query algebra; you're checking if an SSH key exists.

- **`ConfigValueCheck` as a separate type** — It's `CommandOutputCheck` where the command is `git config user.email`. Delete the class, use `CommandOutputCheck`.

- **The Presentation axis** — There is no presentation choice in v1. The tutorial runs as an agent conversation. Specifying `cli-interactive` | `agent-conversational` | `tui-panel` as axis values for a system that will only have one presentation mode is premature abstraction.

- **The Progression axis with `linear` | `branching` | `checkpoint-gated`** — v1 is checkpoint-gated. Period. `linear` is checkpoint-gated without checkpoints. `branching` is commented out in the spec. Kill both; add them if someone asks.

- **Auto-discovery of tutorial directories** — There will be 2-3 tutorials in v1. A hardcoded list or a simple glob is fine. Auto-discovery with validation is framework behavior for a feature that has 3 instances.

- **YAML→HintSpec conversion pipeline with trigger shorthand resolution** — The conversion code in `axis_guidance.md` (`_build_hint_specs`, `_resolve_trigger`, `_resolve_lifecycle`) is 50 lines of mapping code that translates YAML strings into Python objects. For 3 tutorials with ~3 hints each, that's 9 hint specs. You could construct them directly in Python with less code than the conversion pipeline.

---

## The "Framework Trap" — A Pattern I See Here

The specs repeatedly say things like "adding a new tutorial requires zero code changes" and "content authors write data, not code." This is the framework mindset: build it once, make it extensible, authors just add content.

But who is adding tutorials? In the near term: the template maintainer (probably the user who asked for this feature). They can write Python. They don't need a YAML-to-Python conversion layer to shield them from code. The framework pays off at scale (50+ tutorials, non-developer authors). For 3-5 tutorials written by the person who built the system, it's overhead.

**The prior art confirms this.** Rustlings started as a simple exercise runner and grew into its current form over years. Katacoda built its verification format iteratively based on thousands of scenarios. GitHub Skills evolved from Learning Lab through multiple redesigns. None of them started with a 6-axis composability framework. They started with working tutorials and extracted patterns later.

---

## Assumptions Not Validated

### A1: "Content authors are non-developers"

The terminology spec says tutorials should be "accessible to non-developers (scientists)." But the tutorial content format requires:
- Writing YAML with nested objects (`verification.params.expected_pattern`)
- Understanding regex patterns for verification (`pattern: "github\\.com"`)
- Managing frontmatter/manifest ID consistency
- Understanding trigger shorthands (`step-stuck`, `verification-failed`)

This is not non-developer-friendly. A scientist who can write this YAML can also write Python. The "data-only authoring" benefit is an illusion if the data is as complex as the code it replaces.

### A2: "The hints pipeline is the right delivery mechanism for tutorial guidance"

Tutorial hints (nudges when stuck) have fundamentally different timing needs than project hints (one-time feature discovery). The existing pipeline runs `await asyncio.sleep(delay)` between toasts and evaluates hints on startup or periodic evaluation. Tutorial hints need to fire reactively — when verification fails, when the user has been idle for N seconds on a step.

The spec says tutorial triggers (`TutorialStepStuck`) check elapsed time since step entry. But when does this trigger get evaluated? The hints pipeline runs on startup and periodically. If evaluation happens every 60 seconds, a `TutorialStepStuck(threshold_seconds=120)` hint fires sometime between 120-180 seconds — not exactly responsive.

This might work acceptably, but the assumption "tutorial hints fit the existing evaluation cadence" isn't validated. The spec should state the expected evaluation frequency during tutorial mode and whether it needs to increase.

### A3: "The guardrail system can support scoped rules"

The existing guardrail rules in `rules.yaml` are global — they apply to all sessions. The existing `block: [Subagent]` mechanism is the closest thing to scoping, and it scopes by agent type, not by mode.

The spec proposes `scope: { mode: tutorial_active }` for tutorial rules. But the existing `bash_guard.py` (auto-generated from rules.yaml) is a static Python script that reads stdin JSON and applies regex matches. It doesn't check what "mode" the session is in. Adding mode awareness requires:
- The guardrail hook receiving mode information in its stdin JSON
- The hook generation script understanding scope fields
- A mechanism for the tutorial engine to communicate "tutorial mode is active" to the guardrail hooks

This is a real implementation gap. The specs assume scoped rules are a minor extension, but the actual hook infrastructure doesn't support it today.

### A4: "The tutorial-runner agent can be constrained from executing verification-target commands"

`axis_guidance.md` proposes `agent_blocked_commands` per step, converted to scoped guardrail rules. But the existing guardrail system blocks commands via regex on bash commands. The tutorial-runner agent IS a Claude Code agent with bash access. Blocking `ssh-keygen` via regex means the agent can't run `ssh-keygen` — but can it run `bash -c 'ssh-keygen ...'`? Can it run `python -c "os.system('ssh-keygen')"'`? Regex-based command blocking is inherently bypassable.

This is the same problem as guardrail evasion in any regex-based system. It's probably acceptable (the agent isn't adversarial), but the spec presents it as a hard constraint when it's really a soft one.

---

## Missing Failure Modes

### FM1: Tutorial content is wrong

Nobody's talking about what happens when the tutorial itself has a bug. Step 2 says "run `ssh-keygen -t ed25519`" but the verification checks for `id_rsa`. The user does everything right, verification fails, they're stuck. The agent can't help because the agent reads the content, and the content is wrong.

This is the most common failure mode in tutorial systems (the prior art research should have found this — Rustlings issues are full of "exercise has wrong expected output"). No spec addresses tutorial testing.

### FM2: Verification command has side effects

The spec says verifications are "read-only." But `ssh -T git@github.com` creates a TCP connection to GitHub, which could trigger rate limiting or security alerts. `ssh -o BatchMode=yes ${CLUSTER_HOST} echo ok` attempts a real SSH connection. These are not side-effect-free. They're "mostly safe" but the spec calls them "read-only" which sets wrong expectations.

### FM3: User environment is non-standard

The SSH tutorial assumes `~/.ssh/` is the key directory. On some HPC systems, home directories are NFS-mounted and `.ssh` permissions are wrong, or the SSH agent is managed by a module system, or keys are managed by Kerberos. The verification checks standard paths but the user's environment isn't standard.

This is inherent to teaching system administration tasks — environments vary. The spec doesn't address what happens when verification is correct but the environment is non-standard.

### FM4: Tutorial blocks normal work

The user enters tutorial mode, starts SSH setup, then realizes they need to do something else urgently. Can they do normal work while in tutorial mode? The spec implies "normal project work is suspended" (terminology.md: "entering tutorial mode changes what agents are spawned"). If you literally can't do normal work in tutorial mode, the user is locked in. If you can, the tutorial guardrails might conflict with normal work.

---

## Implementability Assessment

### How long would this take to implement as specified?

Rough estimate for a strong developer:
- `_types.py` (Verification protocol, VerificationResult, TutorialStep, etc.) — 1 day
- `_verification.py` (5 verification types + VerificationContext) — 1-2 days
- `_engine.py` (manifest loading, step progression, verification orchestration) — 2-3 days
- Tutorial-specific guardrail rules + scope support in hooks — 2-3 days (this requires modifying `generate_hooks.py` and the hook scripts)
- Hints integration (TutorialContext on ProjectState, new triggers, hint conversion) — 1-2 days
- `_state.py` (TutorialProgressStore) — 1 day
- Tutorial content (2-3 actual tutorials with YAML manifests and step markdown) — 2-3 days
- Testing — 3-5 days
- Integration/debugging — 2-3 days

**Total: ~15-22 working days for the full spec.**

### How long would a simpler version take?

Strip it to: manifest loading, 2 verification types (command output + file exists), single-agent runner, progress JSON, 2 tutorials, basic guardrail rules.

**Total: ~5-8 working days.**

The delta is 10-14 days of framework engineering that adds extensibility nobody will use in v1.

---

## What I'd Actually Build for v1

```
tutorials/
  _runner.py          # Tutorial engine: load manifest, run steps, verify, persist
  _verify.py          # run_command_check() and file_exists_check() — two functions
  content/
    ssh-cluster/
      tutorial.yaml   # Steps, verification config, hints
      step-01.md
      step-02.md
      step-03.md
    first-pytest/
      tutorial.yaml
      step-01.md
      step-02.md
```

- **`_runner.py`**: Load YAML manifest. Present step content to the agent. Run verification. Persist progress to JSON. Advance. ~200 lines.
- **`_verify.py`**: `run_command_check(command, pattern, timeout) → (passed, output)`. `file_exists_check(path) → (passed, message)`. ~50 lines.
- **Hints**: Construct 5-10 `HintSpec` objects directly in Python (one function in `_runner.py` that returns them). No YAML→HintSpec conversion.
- **Guardrails**: Add 2-3 tutorial-specific rules to `rules.yaml` with a `scope` comment (enforce via convention initially, add mode-awareness to hooks in v2).
- **Agent role**: A `tutorial-runner.md` role file that gets the step content and verification result injected into context.

This delivers the user's actual request — "a tutorial feature that combines md files, agents, hints, and guardrails in a new mode" — in ~800 lines of new code plus 2 tutorial content directories. It's testable, shippable, and teaches the real lessons about what abstractions the system needs before building the framework.

---

## Summary

| Aspect | Verdict |
|---|---|
| **Composability analysis** | Technically correct, but overkill for v1. The axes are real; the formal protocols for each axis are premature. |
| **Verification spec** | Best part of the package. The Verification protocol and VerificationResult are the right abstractions. But 5 concrete types + VerificationContext + CompoundCheck is too much for v1. Ship CommandOutputCheck + FileExistsCheck + ManualConfirm. |
| **Content spec** | Good format (YAML + markdown). Over-specifies features nobody will use in v1 (branching, auto-discovery, environment variables, custom fence tags). |
| **Guidance spec** | Correct integration approach (extend hints pipeline, don't fork it). Over-engineers the conversion pipeline. The `AgentContext` system prompt builder is good — keep that. |
| **Prior art** | Solid research. Ironically, every cited system started simpler than what we're specifying and grew into their current form. |
| **Terminology** | Good. Clear terms, clean disambiguation. |
| **User alignment** | Correct — no scope creep, no scope shrink. |
| **Implementability** | As specified: 15-22 days. Stripped to essentials: 5-8 days. |
| **Guardrail scoping** | The biggest implementation gap. Existing hooks don't support mode-aware scoping. This needs design work before it can be implemented. |

## Recommendation

**Ship the feature, not the framework.**

1. Build the minimal tutorial runner (manifest loading, 3 verification types, progress persistence, agent role).
2. Write 2 real tutorials (SSH cluster, first pytest).
3. Add tutorial hints directly as `HintSpec` objects — no YAML conversion pipeline.
4. Add 2-3 tutorial guardrail rules to `rules.yaml` — enforce by convention, not by mode scoping.
5. Defer: CompoundCheck, ConfigValueCheck, auto-discovery, branching progression, VerificationContext sandbox, YAML→HintSpec pipeline, mode-aware guardrail scoping, Presentation axis, agent-team tutorial.
6. After v1 ships and people use it: extract the patterns that actually matter and build the framework.

The specification is a good v2 design document. It's a dangerous v1 implementation plan.
