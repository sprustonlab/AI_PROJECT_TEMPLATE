# Phase Content Lock: Agent Knowledge Boundary = Phase Boundary

**Reviewer:** Composability (Lead Architect)
**Prompt:** "Only give the agent the MD file per phase. That syncs agentic and guardrail checkpoint behavior."

---

## The Insight

The user identifies a fundamental desync in the current design:

**Today:** The Coordinator reads ALL of COORDINATOR.md (275 lines, 9 phases). It "knows" about every phase. It's on the honor system to focus on the current one. STATUS.md says "Phase 3" but the agent can see Phase 4's instructions, Phase 5's instructions, everything.

**Proposed:** The agent ONLY receives the markdown for its current phase. It literally can't see Phase 5's instructions while in Phase 4. The content boundary IS the phase boundary.

This creates two locks from the same source:

```
phase_state.json: { phase_id: "implementation" }
         │
         ├──► CONTENT LOCK: agent prompt includes phase-04-implementation.md (only)
         │
         └──► GUARDRAIL LOCK: rules scoped to "implementation" are active
```

Both derive from `phase_id`. They can't desync because there's one source of truth.

---

## What This Changes

### Before: Phase is metadata on a data structure

```python
# Old model: Phase is a faceted data structure
@dataclass(frozen=True)
class Phase:
    id: str
    description: str
    activate_rules: tuple[str, ...]
    deactivate_rules: tuple[str, ...]
    advance_checks: tuple[Check, ...]
    hints: tuple[HintDeclaration, ...]
```

The agent reads a complete workflow definition and a state pointer. The phase is an entry in a list. The agent "knows" about all phases.

### After: Phase is a file

A phase IS its markdown file. The file contains both the agent instructions and the phase metadata (as frontmatter). The workflow is a directory of phase files.

```
workflow/project-team/
  phase-00-vision.md
  phase-01-setup.md
  phase-02-spawn-leadership.md
  phase-03-specification.md
  phase-04-implementation.md
  phase-05-testing.md
  phase-06-signoff.md

workflow/first-pytest-tutorial/
  phase-01-write-test.md
  phase-02-run-test.md
```

Each file:

```markdown
---
id: implementation
title: "Implementation"
activate_rules: [R-BLOCK-FULL-PYTEST]
deactivate_rules: []
advance_checks:
  - type: manual-confirm
    question: "Are all implementation tasks complete and Leadership-approved?"
hints:
  - message: "Focus on writing code, not running the full test suite"
    trigger: { type: phase-active }
    lifecycle: show-once
---

## Phase 4: Implementation

1. Spawn one Implementer agent per file, up to 6 implementer agents.
2. Inform Leadership about how many implementation agents have been started
   and what their names are, and that it is Leadership's role to guide.
3. If Researcher is active → ask Researcher to find reference implementations,
   API examples, and known pitfalls relevant to what Implementers are building.
4. Exit when all Leadership approve.
```

The agent receives this file's content (everything below the frontmatter) as its instructions. The engine reads the frontmatter for guards, gates, and context. Same file, two readers.

---

## How the Phase Primitive Changes

### Old: 3 types

```
Phase (data structure) + Workflow (list of phases) + ActivePhase (pointer)
```

### New: 2 types + filesystem convention

```
PhaseFile (markdown file with YAML frontmatter) + ActivePhase (pointer)
```

The `Workflow` type disappears. A workflow is just a directory. Ordering comes from filename convention (`phase-NN-slug.md`) or a manifest. The engine doesn't need to parse an in-memory workflow object — it reads the directory, sorts by prefix, loads the current phase file.

```python
@dataclass(frozen=True)
class PhaseMeta:
    """Parsed from YAML frontmatter of a phase markdown file.

    The engine reads this. The agent never sees it.
    """
    id: str
    title: str
    activate_rules: tuple[str, ...] = ()
    deactivate_rules: tuple[str, ...] = ()
    advance_checks: tuple[CheckDeclaration, ...] = ()
    hints: tuple[HintDeclaration, ...] = ()


@dataclass(frozen=True)
class ActivePhase:
    """Runtime state: which phase is current.

    Written to phase_state.json.
    Read by guardrail hooks and hints pipeline.
    """
    workflow_id: str
    phase_id: str
    phase_entered_at: float
    completed_phases: frozenset[str]
    last_check_result: CheckResult | None
```

`PhaseMeta` replaces `Phase`. It's parsed from the file's frontmatter, not constructed in Python. The markdown body is the agent's instructions — the engine passes it to the agent as a string, never as a data structure.

---

## The Two Readers

The same file serves two audiences:

```
phase-04-implementation.md
┌─────────────────────────────────┐
│  YAML frontmatter               │──► Engine reads: guards, gates, context
│  (id, rules, checks, hints)     │    (PhaseMeta)
├─────────────────────────────────┤
│  Markdown body                  │──► Agent reads: instructions
│  (what to do in this phase)     │    (string, injected into prompt)
└─────────────────────────────────┘
```

**Seam:** The frontmatter and body share a file but don't share data. The engine doesn't interpret the markdown body. The agent doesn't see the frontmatter. They read different parts of the same file.

**Why one file, not two?** Because the content lock guarantees coherence. If guards and instructions were in separate files, they could desync (update the instructions without updating the guards). One file = one atomic unit = one phase definition.

---

## How Transition Works

### Before: Update state, agent re-reads same workflow file

```
1. Coordinator decides "Phase 3 is done"
2. Coordinator updates STATUS.md: "Current Phase: 4"
3. Coordinator re-reads COORDINATOR.md, finds Phase 4 section
4. (Guardrails read phase_state.json — but this didn't exist before)
```

The problem: step 3 means the agent has ALWAYS had access to Phase 4 instructions. The "transition" is just the agent shifting attention within the same document.

### After: Engine delivers new file, updates state atomically

```
1. Gate check runs: advance_checks for current phase
2. If passed (or manually approved):
   a. Engine reads next phase file's frontmatter (PhaseMeta)
   b. Engine updates phase_state.json with new phase_id
      → guardrails now scope to new phase
   c. Engine injects new phase file's markdown body into agent prompt
      → agent now sees new instructions
   d. Engine registers new phase's hints, unregisters old phase's hints
```

Steps b and c are the two locks engaging simultaneously. They derive from the same phase file, so they can't disagree about which phase is active.

### What "inject into agent prompt" means concretely

For the project-team workflow, the Coordinator already re-reads COORDINATOR.md every turn ("EVERY TURN: Re-read AI_agents/project_team/COORDINATOR.md"). The content-lock version replaces this:

**Instead of:** "Re-read the full COORDINATOR.md and find your current phase section"
**Do:** "Read the phase file the engine gave you"

The engine provides the file path. The agent reads only that file. The agent's system prompt or role file says:

```
Your current phase instructions are at: {phase_file_path}
Read this file. Follow these instructions. Do not look for other phase files.
```

For tutorials, the tutorial-runner agent receives the phase markdown as its current step content — same as before, just with the explicit framing that this IS the phase.

---

## Impact on Seams

### Phase ↔ Guardrails seam: UNCHANGED ✅

Still `phase_state.json`. The guardrail hooks read `phase_id` from the file. They don't know or care that the phase is also a markdown file. The seam contract is the same.

### Phase ↔ Hints seam: UNCHANGED ✅

Still `ActivePhase` on `ProjectState`. Hint triggers check `active_phase.phase_id`. They don't know the phase is a file.

### Phase ↔ Agent seam: NEW AND CLEANER ✅

**Old seam:** Agent reads full workflow document + checks STATUS.md for current phase. Honor-based focus.

**New seam:** Agent receives one markdown file. Content boundary = phase boundary. Structural focus.

This is a new seam that didn't exist before. The agent's knowledge is bounded by what the engine provides. The engine is the gatekeeper.

### Phase ↔ Check seam: UNCHANGED ✅

Checks are still declared in frontmatter (replacing the Python `Phase.advance_checks`). The engine parses them from YAML and runs them. Checks don't know about files or agents.

---

## Impact on the Workflow Type

The `Workflow` data structure dissolves into a directory convention:

```python
# OLD
@dataclass(frozen=True)
class Workflow:
    id: str
    phases: tuple[Phase, ...]

# NEW — no Workflow type needed
# A workflow IS a directory of phase-NN-*.md files
# Discovery:
def discover_phases(workflow_dir: Path) -> list[tuple[int, Path]]:
    """Find all phase files, return sorted by numeric prefix."""
    phases = []
    for f in workflow_dir.glob("phase-*.md"):
        match = re.match(r"phase-(\d+)-", f.name)
        if match:
            phases.append((int(match.group(1)), f))
    return sorted(phases)
```

**Advantage:** No in-memory workflow object to construct, validate, or keep in sync. The filesystem IS the workflow definition. Adding a phase = adding a file. Removing a phase = removing a file.

**Disadvantage:** No single-file view of the full workflow. You can't see all phases at a glance without listing the directory. But this is actually the point — the agent shouldn't see all phases at a glance.

**Manifest option:** If a single-file overview is needed (for the engine or for documentation), a `workflow.yaml` manifest can list the phases and their ordering. But this is optional metadata, not the phase definition. The phase files are still the source of truth.

```yaml
# workflow.yaml (optional — for engine/docs, not for agents)
id: project-team
title: "Project Team Workflow"
phases:
  - phase-00-vision.md
  - phase-01-setup.md
  - phase-02-spawn-leadership.md
  - phase-03-specification.md
  - phase-04-implementation.md
  - phase-05-testing.md
  - phase-06-signoff.md
```

---

## Impact on COORDINATOR.md

This is the biggest concrete change. Today COORDINATOR.md is 275 lines containing ALL phase instructions. Under the content-lock model, it splits:

### Before

```
COORDINATOR.md (275 lines)
  ├── Prime Directive (20 lines, cross-phase)
  ├── Phase 0: Vision (15 lines)
  ├── Phase 1a-c: Setup (40 lines)
  ├── Phase 2: Spawn Leadership (50 lines)
  ├── Phase 3: Specification (30 lines)
  ├── Phase 4: Implementation (10 lines)
  ├── Phase 5: Testing (5 lines)
  ├── Phase 6-9: Ship (30 lines)
  └── Key Terms (10 lines, cross-phase)
```

### After

```
AI_agents/project_team/
  COORDINATOR.md (30 lines — Prime Directive + Key Terms only)
  phases/
    phase-00-vision.md
    phase-01-setup.md
    phase-02-spawn-leadership.md
    phase-03-specification.md
    phase-04-implementation.md
    phase-05-testing.md
    phase-06-signoff.md
```

The Coordinator always reads `COORDINATOR.md` (cross-phase identity and rules) PLUS the current phase file (phase-specific instructions). This is cleaner — the agent's identity is separate from its current task.

```
Agent prompt = COORDINATOR.md (who you are) + phase-03-specification.md (what to do now)
```

### Cross-phase content

Some content is phase-independent (Prime Directive, Key Terms, conflict resolution). This stays in `COORDINATOR.md`. The phase files contain only phase-specific instructions.

**Rule:** If removing a section from COORDINATOR.md would make any phase file unable to stand alone, that section is cross-phase and stays in COORDINATOR.md. If a section only matters during one phase, it goes in that phase's file.

---

## Impact on Tutorials

Tutorials already followed this pattern implicitly. The Content axis spec had separate step files (`step-01-generate-key.md`, etc.) with YAML frontmatter. The content-lock model just recognizes that tutorial steps ARE phases:

```
tutorials/first-pytest/
  phase-01-write-test.md      # was: step-01-write-test.md
  phase-02-run-test.md        # was: step-02-run-test.md
```

The frontmatter carries guards, gates, and context. The body is the instructions. The tutorial-runner agent receives one phase file at a time. Same infrastructure as the project-team workflow.

**Change from previous Content axis spec:** The `tutorial.yaml` manifest becomes optional. The phase files ARE the tutorial. If ordering and metadata are needed beyond what the filename prefix provides, a `workflow.yaml` manifest can list them. But the phase files are self-contained — each has its own frontmatter with checks, hints, and rules.

**Trade-off:** The previous spec put all verification/hint/guardrail config in `tutorial.yaml` (single source of truth for structure) with step files for content only. The content-lock model puts config IN the phase file's frontmatter. This means config is co-located with content (good: can't desync) but scattered across files (lose the single-file overview of all checks).

**Resolution:** Both can coexist. The phase file's frontmatter is the source of truth. A `workflow.yaml` manifest is an optional index that the engine can generate or verify against the phase files. For small workflows (2-5 phases), no manifest needed. For large workflows (9+ phases), the manifest helps orientation.

---

## The Two-Lock Guarantee

The core compositional property:

```
CONTENT LOCK:    agent sees phase-04-implementation.md body
GUARDRAIL LOCK:  hooks read phase_id: "implementation" from phase_state.json
                 ↓
BOTH derive from: the engine selecting "phase-04-implementation.md"
```

**Why they can't desync:**
1. The engine reads phase-04-implementation.md
2. From frontmatter: extracts `id: implementation`, `activate_rules: [R-BLOCK-FULL-PYTEST]`
3. Writes `phase_state.json: { phase_id: "implementation", activate_rules: [...] }`
4. Delivers markdown body to agent
5. Steps 3 and 4 happen in the same function call — atomic from the engine's perspective

If the engine delivers the wrong file, both locks are wrong in the same way — the agent sees the wrong instructions AND guardrails scope to the wrong phase. This is better than the old model where the agent could be reading Phase 4 instructions while guardrails think it's Phase 3 (because STATUS.md and phase_state.json were updated independently).

---

## Revised Primitive Definition

### Check: UNCHANGED

```
Check protocol: check(ctx) → CheckResult
3 built-ins: CommandOutputCheck, FileExistsCheck, ManualConfirm
```

### Phase: CHANGED — file-based, not struct-based

```
A phase IS a markdown file with YAML frontmatter.

Frontmatter (PhaseMeta): id, title, activate_rules, deactivate_rules, advance_checks, hints
Body (string): agent instructions in markdown

A workflow IS a directory of phase files.
Ordering: filename prefix (phase-NN-*) or optional workflow.yaml manifest.

ActivePhase: runtime pointer (workflow_id, phase_id, entered_at, completed, last_check)
phase_state.json: persistent state read by guardrail hooks
```

### Compositional law (updated):

1. All checks produce `CheckResult` (unchanged)
2. All phase consumers read `phase_state.json` (unchanged)
3. **NEW:** The agent's content boundary and the guardrail scope derive from the same phase file selection. One source, two projections, can't desync.

---

## What This Simplifies

1. **No `Workflow` type.** A workflow is a directory. Discovery is `glob("phase-*.md")`.
2. **No separate content files.** The phase file IS the content. No need to cross-reference manifest → step file → frontmatter.
3. **No honor-based phase focus.** The agent can't read ahead because it only has one file.
4. **One file per phase = one atomic unit.** Guards, gates, context, and instructions are co-located. Can't update one without the other.
5. **COORDINATOR.md gets smaller.** Only cross-phase identity content. Phase instructions are factored out.

## What This Complicates

1. **COORDINATOR.md must be split.** This is real work — 275 lines into 7+ files plus a stripped-down COORDINATOR.md. But it's a one-time refactor, and the result is cleaner.
2. **Config scattered across files.** Lose the single-file view of all checks/rules for a workflow. Mitigated by optional `workflow.yaml` manifest.
3. **Agent prompt assembly.** The engine must construct the agent's prompt from COORDINATOR.md (identity) + current phase file (instructions). Slightly more complex than "read one file."
4. **Frontmatter parsing.** Every phase file needs YAML frontmatter parsing. But this is a solved problem (the Content axis spec already required it for step files).

---

## Summary

The content-lock insight changes the Phase primitive from a data structure to a file. A phase IS its markdown file. The two-lock guarantee (content + guardrails derive from the same file selection) provides structural sync that the old model achieved only through convention.

| Aspect | Before | After |
|---|---|---|
| Phase definition | Python dataclass | Markdown file with YAML frontmatter |
| Workflow definition | `Workflow` type with `phases: tuple` | Directory of `phase-*.md` files |
| Agent knowledge scope | Full workflow doc + state pointer | Current phase file only |
| Guard/content sync | Convention (update both independently) | Structural (one file, two projections) |
| COORDINATOR.md | 275 lines, all phases | ~30 lines cross-phase + N phase files |

The Check primitive is unaffected. The seams to guardrails and hints are unaffected. The new seam (Phase ↔ Agent) is cleaner than before. The compositional law gains a third property: content and guardrail scope derive from the same phase file selection.
