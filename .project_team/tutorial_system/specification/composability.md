# Composability Analysis: Tutorial System

## Domain Understanding

The tutorial system is an interactive teaching mode that guides users (primarily scientists) through foundational dev tasks (SSH setup, GitHub signup, git config, pixi environments, etc.). It combines markdown content, an agent team, contextual hints, and guardrails into a structured, step-by-step walkthrough with verification checkpoints.

The system lives inside an existing template that already has composable subsystems:
- **Hints system** — composable pipeline (Trigger × Lifecycle × Presentation) with clean protocol-based seams
- **Guardrails system** — rule catalog (rules.yaml) with hook generation, enforcement levels, regex-based detection
- **Agent team** — coordinator + specialist agents with role files

The tutorial system must compose with all three, not duplicate them.

---

## Identified Axes

### 1. **Content** — What is being taught
- Values: `github-signup` | `ssh-cluster` | `git-config-ssh-keys` | `first-project` | `pixi-environments` | `pytest-first-test` | `coding-feature-X` | (user-extensible)
- Why independent: A tutorial's subject matter is orthogonal to how it's delivered, verified, or navigated. Adding a new tutorial topic should require only adding content files — zero changes to engine, guardrails, or hints.
- Seam: Content produces a sequence of `TutorialStep` records; the engine consumes them. Content doesn't know about presentation or verification internals.

### 2. **Progression** — How the user moves through steps
- Values: `linear` | `branching` | `checkpoint-gated`
- Why independent: Whether steps are sequential, branch based on user answers, or gate on verification is a navigation concern separate from what the content says or how verification works.
- Seam: Progression consumes the current step + verification result → produces the next step ID. It doesn't know what the verification actually checked.

### 3. **Verification** — How step completion is confirmed
- Values: `command-output-check` | `file-exists-check` | `config-value-check` | `manual-confirm` | `compound` (AND/OR of sub-checks)
- Why independent: Whether we verify via `git remote -v` output, file existence, or user self-report is orthogonal to what's being taught and how steps are navigated. Each verification is a pure function: system state → pass/fail.
- Seam: Verification protocol: `check(context: VerificationContext) -> VerificationResult`. The engine calls it; verification doesn't know about content, progression, or presentation.
- **This is the critical axis.** The user prompt explicitly calls out that "the agent can't just say done — the guardrails prove it." Verification is what distinguishes this from static markdown.

### 4. **Guidance** — How the user receives help during a step
- Values: `agent-assist` | `hint-nudge` | `static-instruction` | `combined`
- Why independent: Whether an AI agent actively helps, hints fire contextually, or the user reads static markdown is orthogonal to what's being verified and what content is being taught.
- Seam: Guidance receives the current step + user context → produces messages/actions. It doesn't control progression or verification.
- Integration point: This axis reuses the existing hints system (HintSpec/TriggerCondition) for contextual nudges, and the agent team for interactive help.

### 5. **Safety** — What the user is prevented from doing
- Values: `tutorial-guardrails-active` | `permissive` | `custom-ruleset`
- Why independent: Tutorial-specific guardrails (e.g., "don't delete your SSH key mid-tutorial") are orthogonal to content and verification. Different tutorials need different safety profiles.
- Seam: Safety composes with the existing guardrails system (rules.yaml). Tutorial-specific rules are additive — they extend the catalog, not replace it.
- Integration point: Uses the existing guardrail enforcement pipeline. Tutorial rules are just additional entries with a `tutorial_id` scope.

### 6. **Presentation** — How the tutorial is rendered to the user
- Values: `cli-interactive` | `agent-conversational` | `tui-panel` (future)
- Why independent: Whether the tutorial renders in a structured CLI flow, an agent conversation, or a dedicated TUI panel doesn't affect content, verification, or progression logic.
- Seam: Presentation consumes `TutorialStep` + `VerificationResult` + guidance messages → renders them. It doesn't know how verification was done or what progression model is active.

---

## Compositional Law

**The Step Protocol** — the shared law enabling composition:

```python
@dataclass(frozen=True)
class TutorialStep:
    id: str
    content: str                    # Markdown instruction
    verification: Verification      # How to confirm completion
    hints: list[HintSpec]          # Contextual hints for this step
    guardrails: list[str]          # Rule IDs active during this step
    metadata: dict[str, Any]       # Extensible (difficulty, estimated_time, etc.)

class Verification(Protocol):
    def check(self, context: VerificationContext) -> VerificationResult: ...

@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    message: str                   # Human-readable explanation
    evidence: str | None           # Actual command output / file contents
```

**Why this is algebraic:**
- Content produces `TutorialStep` — doesn't know how it's verified or presented
- Verification checks against system state — doesn't know what content said or how progression works
- Progression reads `VerificationResult.passed` — doesn't know what was checked
- Presentation renders steps and results — doesn't know about internals of any other axis
- Adding a new tutorial = new content + picking verification values. No engine changes.

---

## Crystal Test (10 Random Points)

| Content | Progression | Verification | Guidance | Safety | Presentation | Works? |
|---------|-------------|--------------|----------|--------|-------------|--------|
| ssh-cluster | linear | command-output-check | agent-assist | tutorial-guardrails | cli-interactive | ✅ |
| github-signup | linear | manual-confirm | static-instruction | permissive | agent-conversational | ✅ |
| pixi-environments | checkpoint-gated | file-exists-check | hint-nudge | tutorial-guardrails | cli-interactive | ✅ |
| git-config | branching | config-value-check | combined | custom-ruleset | agent-conversational | ✅ |
| pytest-first-test | linear | command-output-check | agent-assist | tutorial-guardrails | cli-interactive | ✅ |
| first-project | checkpoint-gated | compound | combined | tutorial-guardrails | cli-interactive | ✅ |
| coding-feature | branching | manual-confirm | agent-assist | permissive | agent-conversational | ✅ |
| ssh-cluster | checkpoint-gated | compound | hint-nudge | custom-ruleset | cli-interactive | ✅ |
| github-signup | branching | file-exists-check | static-instruction | permissive | cli-interactive | ⚠️* |
| pixi-environments | linear | config-value-check | agent-assist | tutorial-guardrails | tui-panel | ✅ |

*⚠️ `github-signup` + `file-exists-check` is technically valid (checking for `~/.gitconfig` or SSH key file) but content-verification pairing would be author responsibility. The engine supports it — no hole in the crystal.

**Result: No structural holes.** All combinations work because the Step Protocol law is followed.

---

## Potential Issues

### 1. Verification ↔ Guidance coupling risk
If the agent-assist guidance mode needs to "know" what verification expects in order to help the user, there's a temptation to have guidance inspect verification internals. **Fix:** Guidance should read the step's `content` (which describes what to do) and the `VerificationResult.message` (which says what failed), not the verification implementation.

### 2. Guardrail scoping complexity
Tutorial-specific guardrails need to activate/deactivate per-step. The existing guardrails system is global (rules.yaml). **Fix:** Add a `scope` field to guardrail rules: `{ tutorial_id: "ssh-cluster", step_ids: ["step-3", "step-4"] }`. The guardrail enforcement pipeline filters by active scope.

### 3. Hints system integration — not a new axis
Tutorial hints should reuse the existing `HintSpec`/`TriggerCondition` infrastructure, not create a parallel system. Tutorial steps register their hints into the existing pipeline with tutorial-specific triggers. **Risk:** Creating a separate hint system for tutorials would be a composability violation (duplicated axis).

### 4. Content authoring format
Markdown files with YAML frontmatter is the natural format (consistent with existing template patterns). **Risk:** If content format becomes coupled to a specific presentation mode, the Content ↔ Presentation seam leaks.

### 5. State persistence across sessions
Tutorials are multi-session. Progress state (which steps completed, verification evidence) needs persistence. This is analogous to the hints system's `HintStateStore`. **Recommendation:** Reuse the same pattern — JSON file in a known location, with a `TutorialStateStore` protocol.

---

## File Structure Recommendation

```
template/
  tutorials/
    _engine.py              # Tutorial pipeline (analogous to hints/_engine.py)
    _types.py               # TutorialStep, Verification protocol, VerificationResult
    _state.py               # TutorialStateStore (progress persistence)
    _verification.py        # Built-in verification implementations
    content/                # Content axis — one dir per tutorial
      ssh-cluster/
        tutorial.yaml       # Steps, metadata, verification config
        step-01.md
        step-02.md
      github-signup/
        tutorial.yaml
        step-01.md
      ...
```

This mirrors the hints system's structure and makes axes visible in the directory layout.

---

## Recommended Deep-Dive Axes

1. **Verification** — Most critical axis. Needs detailed protocol design, built-in implementations (command-output, file-exists, config-value, compound), and clear seam with the guardrails system.
2. **Content** — Authoring format, YAML schema for tutorial.yaml, and how content references verifications without coupling to them.
3. **Guidance ↔ Hints integration** — How tutorial steps register hints into the existing pipeline without creating a parallel system.

---

## User Decisions (Phase 3)

1. **Agent model:** Single tutorial-runner agent for all standard tutorials. One special tutorial ("Working with Agent Teams") spawns actual agents as its content — teaching the multi-agent workflow by doing it.
2. **Bootstrap paradox resolved:** SSH and GitHub signup are valid post-install tutorials. No scoping restrictions needed.
3. **Deep-dive axes:** Verification, Content, Guidance↔Hints — each getting detailed axis specification.

---

## Deep-Dive Axis Specifications

- `axis_verification.md` — Verification protocol, built-in implementations, checkpoint guardrails
- `axis_content.md` — Tutorial authoring format (YAML manifest + markdown steps)
- `axis_guidance.md` — Guidance↔Hints integration with existing pipeline

---

## Summary

The tutorial system decomposes cleanly into 6 orthogonal axes: **Content × Progression × Verification × Guidance × Safety × Presentation**. The compositional law is the **Step Protocol** — a frozen dataclass that all axes produce/consume without knowing each other's internals. The system integrates with existing template infrastructure (hints, guardrails, agents) through clean seams rather than duplication. The critical axis is **Verification**, which is what elevates this from "static markdown" to "interactive teaching with proof of completion."
