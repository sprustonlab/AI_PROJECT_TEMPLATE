# Axis Deep-Dive: Guidance <-> Hints Integration

## Design Principle

Tutorial guidance is **not a parallel system** — it registers hints into the existing `HintSpec`/`TriggerCondition`/`HintLifecycle` pipeline. Tutorial steps declare hints in content (YAML); the tutorial engine converts them into `HintSpec` objects and injects them into the existing `run_pipeline()`. The hints system doesn't know or care that some hints come from tutorials.

---

## 1. Tutorial-Aware TriggerConditions

New `TriggerCondition` implementations that fire based on tutorial state. These are frozen dataclasses satisfying the existing `TriggerCondition` protocol — just new values on the trigger axis, exactly like `GitNotInitialized` or `McpToolsEmpty`.

### Design: TutorialState as a ProjectState extension

Tutorial triggers need access to tutorial progress. Rather than coupling triggers to a tutorial engine, we extend `ProjectState` with an optional `tutorial_context` field (following the existing kwargs convention where `None` means "not provided"):

```python
@dataclass(frozen=True)
class TutorialContext:
    """Read-only snapshot of tutorial progress, injected into ProjectState.

    This is the seam between the tutorial engine and the hints pipeline.
    Triggers read from this; they never import the tutorial engine.
    """
    active_tutorial_id: str | None  # None if no tutorial running
    active_step_id: str | None
    step_entered_at: float | None   # Unix timestamp when user entered current step
    last_verification: VerificationResult | None  # Most recent verification attempt
    completed_steps: frozenset[str]  # Step IDs already completed


# Extended ProjectState (one new field, following existing kwargs pattern):
@dataclass(frozen=True)
class ProjectState:
    root: Path
    copier: CopierAnswers
    session_count: int | None = None
    tutorial: TutorialContext | None = None  # NEW — None when not in tutorial mode
```

### Trigger implementations

```python
@dataclass(frozen=True)
class TutorialStepActive:
    """Fires when user is on a specific tutorial step."""
    tutorial_id: str
    step_id: str

    def check(self, state: ProjectState) -> bool:
        if state.tutorial is None:
            return False
        return (
            state.tutorial.active_tutorial_id == self.tutorial_id
            and state.tutorial.active_step_id == self.step_id
        )

    @property
    def description(self) -> str:
        return f"Tutorial '{self.tutorial_id}' is on step '{self.step_id}'"


@dataclass(frozen=True)
class TutorialStepStuck:
    """Fires when user has been on a step longer than threshold."""
    tutorial_id: str
    step_id: str
    threshold_seconds: float = 120.0  # 2 minutes default

    def check(self, state: ProjectState) -> bool:
        if state.tutorial is None:
            return False
        if (
            state.tutorial.active_tutorial_id != self.tutorial_id
            or state.tutorial.active_step_id != self.step_id
        ):
            return False
        if state.tutorial.step_entered_at is None:
            return False
        import time
        elapsed = time.time() - state.tutorial.step_entered_at
        return elapsed >= self.threshold_seconds

    @property
    def description(self) -> str:
        return (
            f"User stuck on '{self.tutorial_id}/{self.step_id}' "
            f"for >{self.threshold_seconds}s"
        )


@dataclass(frozen=True)
class TutorialVerificationFailed:
    """Fires after a failed verification attempt on a step."""
    tutorial_id: str
    step_id: str

    def check(self, state: ProjectState) -> bool:
        if state.tutorial is None:
            return False
        if (
            state.tutorial.active_tutorial_id != self.tutorial_id
            or state.tutorial.active_step_id != self.step_id
        ):
            return False
        result = state.tutorial.last_verification
        return result is not None and not result.passed

    @property
    def description(self) -> str:
        return f"Verification failed on '{self.tutorial_id}/{self.step_id}'"
```

### Combinator usage

These compose naturally with existing combinators:

```python
# Show hint when user is on step AND has been stuck
AllOf((
    TutorialStepActive("ssh-cluster", "step-03"),
    TutorialStepStuck("ssh-cluster", "step-03", threshold_seconds=180),
))

# Show hint when verification failed OR user has been stuck
AnyOf((
    TutorialVerificationFailed("ssh-cluster", "step-03"),
    TutorialStepStuck("ssh-cluster", "step-03", threshold_seconds=300),
))
```

---

## 2. Hint Registration Flow

### Content declaration (YAML frontmatter in step markdown)

Tutorial step content declares hints declaratively. The content author writes what hint to show and under what condition — the tutorial engine converts this to `HintSpec` objects.

```yaml
# tutorials/content/ssh-cluster/tutorial.yaml
id: ssh-cluster
title: "SSH into your cluster"
steps:
  - id: step-01
    content: step-01.md
    verification: { type: command-output-check, command: "ssh-add -l", pattern: "RSA|ED25519" }
    hints:
      - message: "You'll need an SSH key pair first — check if you have one with `ls ~/.ssh/`"
        trigger: step-active        # shorthand for TutorialStepActive
        lifecycle: show-once
        priority: 3
        severity: info

      - message: "Still working on this? Try running `ssh-keygen -t ed25519` to generate a key."
        trigger: { type: step-stuck, threshold_seconds: 120 }
        lifecycle: show-until-step-complete
        priority: 2
        severity: info

      - message: "Verification failed — make sure `ssh-add -l` shows your key. Did you run `ssh-add`?"
        trigger: verification-failed
        lifecycle: show-until-resolved
        priority: 1
        severity: warning
```

### Conversion pipeline: YAML -> HintSpec -> existing pipeline

```python
def _build_hint_specs(
    tutorial_id: str,
    step: StepDefinition,
) -> list[HintSpec]:
    """Convert a step's YAML hint declarations into HintSpec objects.

    This is the only place YAML hint format is parsed. Output is standard
    HintSpec — the rest of the pipeline doesn't know about tutorials.
    """
    specs: list[HintSpec] = []

    for i, hint_decl in enumerate(step.hints):
        hint_id = f"tutorial:{tutorial_id}:{step.id}:hint-{i}"

        # Resolve trigger shorthand -> TriggerCondition
        trigger = _resolve_trigger(tutorial_id, step.id, hint_decl["trigger"])

        # Resolve lifecycle shorthand -> HintLifecycle
        lifecycle = _resolve_lifecycle(
            tutorial_id, step.id, hint_decl.get("lifecycle", "show-until-resolved")
        )

        specs.append(HintSpec(
            id=hint_id,
            trigger=trigger,
            message=hint_decl["message"],
            severity=hint_decl.get("severity", "info"),
            priority=hint_decl.get("priority", 3),
            lifecycle=lifecycle,
        ))

    return specs


def _resolve_trigger(
    tutorial_id: str, step_id: str, trigger_decl: str | dict
) -> TriggerCondition:
    """Map YAML trigger shorthand to TriggerCondition instances."""
    if trigger_decl == "step-active":
        return TutorialStepActive(tutorial_id, step_id)
    if trigger_decl == "verification-failed":
        return TutorialVerificationFailed(tutorial_id, step_id)
    if isinstance(trigger_decl, dict):
        if trigger_decl["type"] == "step-stuck":
            return TutorialStepStuck(
                tutorial_id, step_id,
                threshold_seconds=trigger_decl.get("threshold_seconds", 120.0),
            )
    raise ValueError(f"Unknown trigger: {trigger_decl}")


def _resolve_lifecycle(
    tutorial_id: str, step_id: str, lifecycle_decl: str
) -> HintLifecycle:
    """Map YAML lifecycle shorthand to HintLifecycle instances."""
    match lifecycle_decl:
        case "show-once":
            return ShowOnce()
        case "show-until-resolved":
            return ShowUntilResolved()
        case "show-every-session":
            return ShowEverySession()
        case "show-until-step-complete":
            return ShowUntilStepComplete(tutorial_id, step_id)
        case _:
            raise ValueError(f"Unknown lifecycle: {lifecycle_decl}")
```

### Data flow summary

```
tutorial.yaml (content author writes)
    |
    v
_build_hint_specs()  (tutorial engine, at tutorial load time)
    |
    v
list[HintSpec]  (standard hint objects — no tutorial-specific type)
    |
    v
get_hints() returns them alongside built-in hints
    |
    v
run_pipeline()  (existing hints/_engine.py — unchanged)
    |
    v
HintRecord -> presentation  (existing toast/notification system)
```

### Integration with get_hints()

The existing `get_hints()` function is the extension point. Tutorial hints are appended:

```python
def get_hints(
    *,
    get_taught_commands: Callable[[], set[str]] | None = None,
    tutorial_hints: list[HintSpec] | None = None,  # NEW parameter
) -> list[HintSpec]:
    hints = list(_STATIC_HINTS)

    if get_taught_commands is not None:
        # ... existing learn-command logic ...

    if tutorial_hints is not None:
        hints.extend(tutorial_hints)

    return hints
```

This is minimal — one new optional parameter. The tutorial engine builds `HintSpec` objects and passes them in. The hints system doesn't import anything from tutorials.

---

## 3. Lifecycle Policies for Tutorial Hints

### Existing lifecycles that work as-is

| Lifecycle | Tutorial use case | Example |
|-----------|-------------------|---------|
| `ShowOnce` | Introductory hints ("Welcome to step 3") | First-time context setting |
| `ShowUntilResolved` | Hints after verification failure (show until user dismisses or trigger goes false) | "Check your SSH agent" |
| `ShowEverySession` | Critical safety reminders | "Don't share your private key" |
| `CooldownPeriod` | Periodic encouragement for long steps | "Still working? Try asking the agent for help" (every 5 min) |

### New lifecycle: ShowUntilStepComplete

One new lifecycle is needed: **show until the user passes verification on this step**. This is distinct from `ShowUntilResolved` because resolution is tied to tutorial progression, not user dismissal.

```python
@dataclass(frozen=True)
class ShowUntilStepComplete:
    """Show on every evaluation until the tutorial step is verified complete.

    Unlike ShowUntilResolved (which stops when the user dismisses or the
    trigger returns False), this keeps showing as long as the step is
    incomplete — even across sessions.

    Reads completion state from TutorialContext on ProjectState,
    NOT from verification internals.
    """
    tutorial_id: str
    step_id: str

    def should_show(self, hint_id: str, state: HintStateStore) -> bool:
        # The lifecycle doesn't have access to ProjectState directly —
        # it only sees HintStateStore. We store step completion as a
        # special key in the hint state store.
        completion_key = f"tutorial:{self.tutorial_id}:{self.step_id}:complete"
        return not state.is_dismissed(completion_key)

    def record_shown(self, hint_id: str, state: HintStateStore) -> None:
        state.increment_shown(hint_id)
```

**Step completion recording**: When the tutorial engine confirms a step is verified, it marks the completion key as dismissed in the `HintStateStore`:

```python
# In tutorial engine, after successful verification:
completion_key = f"tutorial:{tutorial_id}:{step_id}:complete"
hint_state_store.set_dismissed(completion_key, True)
```

This reuses the existing `is_dismissed` / `set_dismissed` mechanism — no new state store methods needed.

### Lifecycle selection guidance for content authors

| Scenario | Recommended lifecycle |
|----------|----------------------|
| "Welcome to this step" intro | `show-once` |
| "You might need to check X" contextual nudge | `show-until-step-complete` |
| "Verification failed because Y" error guidance | `show-until-resolved` |
| "Still stuck? Ask the agent" timed nudge | `CooldownPeriod(seconds=300)` |
| "Never share private keys" safety reminder | `show-every-session` |

---

## 4. Agent-Assist Mode

### Single tutorial-runner agent

The tutorial system uses a single AI agent (the tutorial-runner) that provides interactive help. The agent is a specialist role within the existing agent team infrastructure.

### Agent capabilities and constraints

```yaml
# Role file: tutorials/_agent/tutorial-runner.md
role: tutorial-runner
description: "Interactive assistant for tutorial walkthroughs"

capabilities:
  - Read current step's markdown content
  - Read verification result messages (what failed, not how it checked)
  - Suggest commands for the user to run
  - Explain concepts referenced in step content
  - Answer questions about the current step

constraints:
  - MUST NOT execute verification-bypassing actions
  - MUST NOT modify tutorial state (step progression, completion flags)
  - MUST NOT run commands on behalf of the user that are part of the verification
  - CAN run diagnostic commands (e.g., "let me check if your SSH agent is running")
  - CAN explain what a command does before the user runs it
```

### How the agent gets context

The agent receives a structured context prompt built from the current tutorial state:

```python
@dataclass(frozen=True)
class AgentContext:
    """Read-only context provided to the tutorial-runner agent.

    This is the seam between the tutorial engine and agent-assist.
    The agent sees content and results, not engine internals.
    """
    tutorial_title: str
    step_number: int
    total_steps: int
    step_content: str               # The step's markdown — what to teach
    step_objective: str             # One-line summary of what the user should accomplish
    verification_description: str   # Human-readable: "Checks that ssh-add -l shows a key"
    last_result: VerificationResult | None  # What failed (message + evidence), not how

    def to_system_prompt(self) -> str:
        """Build the agent's system prompt from tutorial context."""
        prompt = f"""You are helping a user complete step {self.step_number}/{self.total_steps} of the "{self.tutorial_title}" tutorial.

## Current Step
{self.step_content}

## Objective
{self.step_objective}

## Verification
The step will be verified by: {self.verification_description}
"""
        if self.last_result and not self.last_result.passed:
            prompt += f"""
## Last Verification Attempt (FAILED)
{self.last_result.message}
"""
            if self.last_result.evidence:
                prompt += f"""
### Evidence
```
{self.last_result.evidence}
```
"""

        prompt += """
## Rules
- Help the user understand what to do and why
- Suggest commands, but let the USER run them
- Do NOT run commands that the verification will check — the user must do those themselves
- You CAN run diagnostic commands to help debug (e.g., checking environment variables)
- When the user thinks they're done, tell them to run the verification check
"""
        return prompt
```

### Verification bypass prevention

The agent cannot bypass verification because:

1. **Structural separation**: The agent has no access to the `Verification` protocol or the tutorial engine's `advance_step()` method. It receives an `AgentContext` (read-only frozen dataclass), not engine references.

2. **Verification is external**: Verification checks system state (files exist, commands succeed), not agent state. Even if the agent ran `ssh-keygen` on the user's behalf, the verification would pass — but the user wouldn't have learned anything. The guardrails system handles this:

```yaml
# Tutorial-specific guardrail rule (added to rules.yaml during tutorial mode)
- id: T01
  name: tutorial-agent-no-bypass
  description: "Tutorial agent must not execute commands that are verification targets"
  scope:
    tutorial_id: "*"  # All tutorials
    agent: tutorial-runner
  pattern: "\\b(ssh-keygen|git init|git remote add)\\b"  # Per-tutorial patterns
  enforcement: block
  message: "That command is part of the verification — help the user run it themselves"
```

3. **The per-tutorial guardrail patterns** are declared in `tutorial.yaml` alongside verification config:

```yaml
# In tutorial.yaml
steps:
  - id: step-03
    verification: { type: command-output-check, command: "ssh-add -l", pattern: "ED25519" }
    agent_blocked_commands:
      - "ssh-keygen"
      - "ssh-add"
```

The tutorial engine converts these into scoped guardrail rules at tutorial load time.

---

## 5. Guidance <-> Verification Seam

### Clean separation

```
Verification                          Guidance
-----------                          --------
Verification protocol                Reads: VerificationResult.message
check(context) -> VerificationResult  Reads: VerificationResult.passed
Owns: how to check                   Reads: VerificationResult.evidence
                                     Does NOT read: Verification internals
                                     (command strings, regex patterns, etc.)
```

### What guidance CAN see

```python
@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    message: str        # "SSH key not found in agent. Run ssh-add to load it."
    evidence: str | None  # "ssh-add -l returned: The agent has no identities."
```

Guidance reads `message` to craft targeted hints. The message is written by the verification author specifically to be user-facing.

### What guidance CANNOT see

Guidance never imports or inspects:
- The `Verification` implementation class
- The command being run (`ssh-add -l`)
- The regex pattern being matched (`ED25519`)
- The check logic

### Dynamic hint messages using verification results

```python
def _stuck_hint_message(state: ProjectState) -> str:
    """Dynamic message that incorporates verification failure info."""
    if state.tutorial is None or state.tutorial.last_verification is None:
        return "Still working on this step? Try asking the tutorial agent for help."
    result = state.tutorial.last_verification
    if not result.passed:
        return f"Hint: {result.message}"
    return "Almost there — run verification to check your work."
```

This callable is used as a dynamic `HintSpec.message`, following the existing pattern (see `LearnCommand.get_message`).

### Seam enforcement

The seam is enforced structurally:
- `TutorialContext` (which triggers/guidance read) contains `last_verification: VerificationResult | None`
- It does NOT contain a `Verification` instance
- The tutorial engine is the only code that calls `verification.check()` and stores the result

---

## 6. Guidance <-> Content Seam

### What guidance reads from content

Guidance reads the step's **markdown content** (the human-readable instruction text) and the **declared hint messages** from YAML. It uses these to understand context.

### What content declares about guidance

Content authors write hints as simple strings with trigger shorthands:

```yaml
hints:
  - message: "You might need to check file permissions with `ls -la ~/.ssh`"
    trigger: step-stuck
```

Content doesn't know:
- How hints are rendered (toast, inline, TUI panel)
- When exactly the hint appears (timing, delays)
- What lifecycle policy is used for display frequency
- How the agent-assist mode works

### Seam enforcement

```
Content                              Guidance
-------                              --------
Produces: step markdown              Reads: step markdown (for agent context)
Produces: hint messages (strings)    Reads: hint messages (wraps in HintSpec)
Produces: trigger shorthands         Converts: shorthands -> TriggerCondition
Does NOT know: HintSpec, lifecycle   Owns: HintSpec construction, timing
Does NOT know: agent system          Owns: agent context building
```

The content author's mental model is simple: "I write a message and say when it should show." The tutorial engine handles all the machinery.

---

## 7. State Management

### Recommendation: Use existing HintStateStore

Tutorial hint state should integrate with the existing `HintStateStore`, NOT use a parallel `TutorialStateStore`. Reasons:

1. **Tutorial hints are HintSpecs.** They enter the same pipeline, get the same lifecycle treatment. Their state (times_shown, last_shown_ts, dismissed) is semantically identical to regular hint state.

2. **Single state file.** The existing `.claude/hints_state.json` already supports arbitrary hint IDs. Tutorial hints just use namespaced IDs: `tutorial:ssh-cluster:step-03:hint-0`. No schema changes needed.

3. **Existing persistence.** Atomic write, graceful degradation on corrupt files, version checking — all handled by the existing `HintStateStore.save()`.

4. **No new state interface.** `HintLifecycle` implementations (including the new `ShowUntilStepComplete`) use `HintStateStore` methods that already exist: `get_times_shown()`, `is_dismissed()`, `set_dismissed()`, `increment_shown()`.

### What about tutorial progression state?

Tutorial progression (which steps are completed, current step, verification evidence) is a **separate concern** from hint state. It belongs in a `TutorialProgressStore` — but this is NOT guidance state. It's engine state.

```
hints_state.json                       tutorial_progress.json
----------------                       ----------------------
Hint display history                   Tutorial progression
(times_shown, dismissed, last_ts)      (current_step, completed_steps, evidence)
Used by: HintLifecycle                 Used by: Tutorial engine, TutorialContext
Includes tutorial hint entries         NOT used by hints pipeline
```

The `TutorialContext` on `ProjectState` is built from `tutorial_progress.json` at evaluation time. Tutorial triggers read from `TutorialContext`. This keeps the data flow clean:

```
tutorial_progress.json
    |
    v (tutorial engine reads at evaluation time)
TutorialContext (frozen, read-only)
    |
    v (injected into ProjectState)
ProjectState.tutorial
    |
    v (triggers read from it)
TutorialStepActive.check(state) -> bool
```

### Namespace convention

All tutorial hint IDs use the prefix `tutorial:` to avoid collisions:

```
tutorial:{tutorial_id}:{step_id}:hint-{index}    # Per-step hints
tutorial:{tutorial_id}:{step_id}:complete         # Step completion flag
```

The existing `ActivationConfig.disable_hint()` and `enable_hint()` work with these IDs — users can disable individual tutorial hints if they want.

---

## Summary

| Concern | Approach |
|---------|----------|
| Tutorial triggers | New `TriggerCondition` implementations (frozen dataclasses), same protocol |
| Hint registration | YAML -> `_build_hint_specs()` -> `HintSpec` list -> `get_hints()` |
| Lifecycles | Reuse `ShowOnce`, `ShowUntilResolved`, `CooldownPeriod`; add `ShowUntilStepComplete` |
| Agent-assist | Single agent with read-only `AgentContext`, blocked from verification commands |
| Guidance <-> Verification | Guidance reads `VerificationResult.{message,evidence}`, not verification internals |
| Guidance <-> Content | Content declares hint messages + trigger shorthands; guidance owns HintSpec construction |
| State | Tutorial hints use existing `HintStateStore`; progression uses separate `TutorialProgressStore` |

**Key invariant**: After `_build_hint_specs()` runs, the hints pipeline has no idea these hints came from a tutorial. They're just `HintSpec` objects with `TriggerCondition` values that happen to check `ProjectState.tutorial`. This is the composability guarantee — tutorials extend the hints system, they don't fork it.
