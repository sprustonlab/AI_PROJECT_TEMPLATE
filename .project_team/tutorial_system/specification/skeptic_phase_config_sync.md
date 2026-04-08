# Skeptic Review: Where Does Phase Configuration Live?

## The Core Tension

Three types of phase config:
- **advance_checks** — what must be true to advance (e.g., "all tests pass")
- **hints** — contextual nudges during this phase (e.g., "still stuck? try X")
- **guards** — what's blocked/allowed during this phase (e.g., "no full test suite in phase 4")

Each has a natural owner:
- Guards → `rules.yaml` (the guardrail system's single source of truth)
- Hints → `hints.py` / `get_hints()` (the hints system's registry)
- Checks → ??? (new concept, no existing home)

The question: should phase files try to own any of this, or should they be pure content?

---

## Option 1: Everything in Phase Files

```yaml
# phase-04-implementation.md frontmatter
---
id: implementation
advance_checks:
  - type: command-output-check
    command: "find src/ -name '*.py' -newer .ao_project_team/*/STATUS.md"
    pattern: ".+"
hints:
  - message: "Run targeted tests only — save full suite for testing phase"
    trigger: timed
    delay: 300
activate_rules: [R01]
deactivate_rules: []
---
```

**What breaks:**
- `activate_rules: [R01]` duplicates `rules.yaml` — already rejected by user.
- If you edit a guardrail rule's phase scoping, you must update BOTH `rules.yaml` (the rule definition) and the phase file (activate_rules). Two files, one concept.
- Hints defined in frontmatter bypass the hints pipeline's `get_hints()` entry point. The hints system doesn't know about them unless the phase engine translates them — same YAML→HintSpec conversion pipeline we cut for being over-engineered.
- advance_checks in frontmatter means the phase file is both content (markdown instructions) AND config (YAML verification specs). Two concerns in one file.

**What's simple:** Everything about a phase is in one place. To understand phase 4, read one file.

**Verdict: Already rejected for guards. Same duplication/sync problem applies to hints. Only advance_checks don't have an existing home, so they're the only candidate.**

---

## Option 2: Nothing in Phase Files — Pure Markdown

```markdown
# Phase 4: Implementation

Write the code. Follow the architecture from specification.
Implement features from userprompt.md.

## What to do
1. Read specification/composability.md for axis separation
2. Write code in the identified files
3. Run targeted tests only (full suite is phase 5)

## When you're done
All Leadership agents must approve your implementation.
```

No frontmatter. No YAML. Just instructions.

advance_checks, hints, and guards all live in their respective systems:
- Guards: `rules.yaml` with `phase_block: [implementation]`
- Hints: `hints.py` with `TutorialStepActive("project", "implementation")` trigger
- Checks: ??? — some new location

**What breaks:**
- advance_checks have no home. Where do they go? Options:
  - `workflow.yaml` (the file we just created for phase registration). It already lists phases — add checks per phase.
  - A new `checks.yaml` or `checks.py` in the workflow directory.
  - Inline in the tutorial engine / phase engine code.
- To understand what phase 4 requires, you must read 3-4 files: the phase markdown, rules.yaml (for guards), hints.py (for hints), and wherever checks live. Scattered.

**What's simple:** Phase files are trivially simple. No parsing, no validation, no frontmatter schema. Just markdown served to the agent.

**Verdict: Simplest phase files. But advance_checks need a home, and the "read 4 files" problem is real for maintainability.**

---

## Option 3: Auto-Generate Frontmatter from Other Sources

```python
# build_phase_context.py
def build_phase(phase_id: str) -> PhaseContext:
    """Assemble phase context from authoritative sources."""
    md_content = read_phase_markdown(phase_id)
    checks = read_checks_from_workflow_yaml(phase_id)
    hints = filter_hints_by_phase(phase_id)  # from hints.py
    guards = filter_rules_by_phase(phase_id)  # from rules.yaml
    return PhaseContext(content=md_content, checks=checks, hints=hints, guards=guards)
```

Phase files are pure markdown. A build step assembles the full phase context from authoritative sources at runtime.

**What breaks:**
- Adds a build/assembly step. More code. More indirection.
- Debugging: "why is this hint showing in phase 4?" requires tracing through the assembly logic to find the source.
- Over-engineering for v1 with 2-3 phases that have config.

**What's simple:** Each system owns its own config. No duplication. The assembly function is the single point where everything comes together.

**Verdict: Architecturally clean but over-engineered for v1. This is what you build when you have 20 phases with complex config. Not for 3 tutorials.**

---

## Option 4: Checks + Hints in Phase Files, Guards in rules.yaml

```yaml
# phase-04-implementation.md frontmatter
---
id: implementation
advance_checks:
  - type: command-output-check
    command: "grep -r 'def ' src/"
    pattern: ".+"
    message: "No implementation found in src/"
hints:
  - message: "Run targeted tests only during implementation"
    trigger: timed
    delay: 300
---
```

Guards stay in rules.yaml with `phase_block: [implementation]`.

**The argument:** Checks and hints are per-phase BY NATURE — they only make sense in the context of a specific phase. You'd never define an advance_check without knowing which phase it gates. You'd never define a tutorial hint without knowing which step it belongs to.

Guards are per-rule BY NATURE — R01 is "always redirect pytest output" with a phase exemption. The rule exists independently; the phase just modifies its scope.

**What breaks:**
- Hints in frontmatter still bypass `get_hints()`. The phase engine must translate YAML hints → HintSpec objects → inject into the hints pipeline. This is the conversion pipeline we cut. Reintroducing it.
- Two hint definition locations: `hints.py` for project hints, phase file frontmatter for phase hints. A developer looking for "where are hints defined?" must check both.

**What's simple:** advance_checks co-located with the phase they gate. Intuitive: "to advance past this step, these checks must pass" is right there in the step file.

**Verdict: Checks in phase files makes sense. Hints in phase files reintroduces the conversion pipeline problem.**

---

## Option 5: Checks in workflow.yaml, Hints in hints.py, Guards in rules.yaml

Each config type lives in its system's authoritative file. Phase files are pure markdown.

```yaml
# AI_agents/project_team/workflow.yaml
id: project
phases:
  - id: implementation
    file: phase-04-implementation.md
    advance_checks:
      - type: command-output-check
        command: "grep -r 'def ' src/"
        pattern: ".+"
  - id: testing
    file: phase-05-testing.md
    advance_checks:
      - type: command-output-check
        command: "pytest tests/ -v"
        pattern: "passed"
```

```python
# hints.py — phase-specific hints alongside project hints
HintSpec(
    id="phase:implementation:targeted-tests",
    trigger=PhaseActive("project", "implementation"),
    message="Run targeted tests only — full suite is for the testing phase",
    lifecycle=ShowOnce(),
)
```

```yaml
# rules.yaml — phase-scoped guards
- id: R01
  phase_block: [implementation]
  # ...
```

**What breaks:**
- Hints for phases are defined in `hints.py`, not near the phase content. To add a hint for a new tutorial step, you edit `hints.py` (or a tutorial-specific hints file), not the tutorial's markdown.
- For tutorials with many hints per step, `hints.py` gets cluttered with tutorial-specific entries far from the tutorial content.

**What's simple:**
- Each system owns its config. No translation layers.
- `workflow.yaml` already exists (from the phase registry decision). Adding `advance_checks` per phase is natural — it's phase metadata alongside phase IDs.
- Guards in rules.yaml: already decided.
- Hints in hints.py: follows existing pattern. `PhaseActive` trigger is just another TriggerCondition.

**Verdict: This is the cleanest separation. The "hints far from content" problem is real but bounded — v1 has few phase hints.**

---

## The Deciding Question: What Creates the Least Sync Burden?

Let me count sync points — places where changing one thing requires changing another:

**Option 1 (everything in phase files):**
- Change a guard's phase scope → update rules.yaml AND phase file (2 files)
- Add a hint → update phase file (1 file, but bypasses hints pipeline)
- Add a check → update phase file (1 file ✓)
- Rename a phase → update workflow.yaml + phase file + rules.yaml + hints.py (4 files)

**Option 2 (nothing in phase files):**
- Change a guard's phase scope → update rules.yaml (1 file ✓)
- Add a hint → update hints.py (1 file ✓)
- Add a check → update ??? (no home = problem)
- Rename a phase → update workflow.yaml + rules.yaml + hints.py + wherever checks are (4 files)

**Option 4 (checks + hints in phase files):**
- Change a guard's phase scope → update rules.yaml (1 file ✓)
- Add a hint → update phase file (1 file, but needs YAML→HintSpec translation)
- Add a check → update phase file (1 file ✓)
- Rename a phase → update workflow.yaml + phase file + rules.yaml (3 files)

**Option 5 (checks in workflow.yaml, hints in hints.py, guards in rules.yaml):**
- Change a guard's phase scope → update rules.yaml (1 file ✓)
- Add a hint → update hints.py (1 file ✓)
- Add a check → update workflow.yaml (1 file ✓)
- Rename a phase → update workflow.yaml + rules.yaml + hints.py (3 files)

Options 4 and 5 tie on sync burden. The tiebreaker: **Option 5 doesn't need a YAML→HintSpec translation layer.** Option 4 puts hints in YAML frontmatter, which requires the conversion pipeline we already cut. Option 5 puts hints in Python, which is what the hints system already consumes.

---

## But Wait: Tutorials Are Different from Project Phases

For the project team workflow (9 phases, few hints, few checks), Option 5 is clean. But tutorials have a different profile:

- 5-10 steps per tutorial
- 2-3 hints per step (on-failure, timed nudge, intro hint)
- 1 check per step
- Tutorials are authored as self-contained directories

For tutorials, putting 15-30 hints in `hints.py` (far from the tutorial content) is worse than putting them in `tutorial.yaml` (co-located with steps). The tutorial spec's original design — hints declared per-step in the manifest — was right for tutorials even though it requires YAML→HintSpec translation.

**This means the answer is different for different workflows:**

- **Project team phases:** Option 5 (checks in workflow.yaml, hints in hints.py). Few hints, few checks, clean separation.
- **Tutorials:** Option 4-ish (checks + hints in tutorial.yaml). Many hints per step, co-location matters, conversion pipeline is justified by volume.

**Is this inconsistency a problem?** Not really. The consuming systems (hints pipeline, check runner, guardrails) don't care where the config originates. They consume `HintSpec` objects, `Check` objects, and `rules.yaml` entries. How those are authored is a content-authoring concern, not an engine concern.

---

## Recommendation

**Two-track authoring, single consumption path:**

1. **Guards:** Always in `rules.yaml` with `phase_block`/`phase_allow`. One authoring location, one system. No exceptions.

2. **advance_checks:**
   - Project phases: in `workflow.yaml` (co-located with phase registration, natural fit)
   - Tutorial steps: in `tutorial.yaml` per step (co-located with step definitions, already designed this way)
   - Both consumed by the same Check primitive — `CommandOutputCheck.check(project_root)` doesn't care where it was declared.

3. **Hints:**
   - Project phases: in `hints.py` as `HintSpec` objects with `PhaseActive` triggers. Few hints, Python authoring is fine.
   - Tutorial steps: in `tutorial.yaml` per step. Many hints, YAML authoring is justified. The tutorial engine converts YAML → `HintSpec` at load time (this is the only place where conversion is needed, and it's bounded to tutorial loading).

4. **Phase files:** Pure markdown. No frontmatter. Just instructions served to the agent. The phase file's job is content, not config.

**Why this works:**
- No duplication. Each piece of config has one authoritative home.
- Each system owns its own config format. Guards use rules.yaml. Hints use HintSpec (whether authored in Python or converted from YAML). Checks use the Check primitive.
- The YAML→HintSpec conversion only exists for tutorials, where it's justified by volume (15-30 hints per tutorial vs. 2-3 per project workflow). It doesn't apply to project phases.
- Phase files are dead simple — just markdown. No schema, no validation, no frontmatter parsing.

**Total sync burden for common operations:**
| Operation | Files to touch |
|---|---|
| Add a tutorial step with hints + check | 1 (`tutorial.yaml`) |
| Add a project phase check | 1 (`workflow.yaml`) |
| Add a project phase hint | 1 (`hints.py`) |
| Add a phase-scoped guard | 1 (`rules.yaml`) |
| Rename a phase | 3 (`workflow.yaml` + `rules.yaml` + `hints.py`) |

Rename-a-phase touching 3 files is the worst case. But renaming phases is rare, and the phase registry validation (Option C from the previous review) will catch any missed references at generation time.
