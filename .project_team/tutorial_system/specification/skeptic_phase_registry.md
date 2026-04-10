# Skeptic Review: Phase Pre-Registration and Validation

## The Problem

If a rule says `phase_block: [testng]` (typo for "testing"), it silently never matches. The rule appears to work but never fires. This is the same class of bug as a role name typo in `block: [Subagnt]` — which the generator already catches by checking role names against `AI_agents/**/*.md`.

The question: where do valid phase IDs come from?

---

## Option A: Auto-Discover from phase-*.md Files

**Mechanism:** `generate_hooks.py` scans known directories for `phase-*.md` files and builds the valid phase set from filenames.

```python
# In generate_hooks.py
def discover_phases() -> set[str]:
    phases = set()
    # Project team phases
    for f in Path("AI_agents/project_team/coordinator/").glob("phase-*.md"):
        phases.add(f.stem)  # "phase-04-implementation" → "phase-04-implementation"
    # Tutorial phases
    for tutorial_dir in Path("tutorials/content/").glob("*/"):
        manifest = tutorial_dir / "tutorial.yaml"
        if manifest.exists():
            steps = yaml.safe_load(manifest.read_text()).get("steps", [])
            for step in steps:
                phases.add(f"tutorial:{tutorial_dir.name}:{step['id']}")
    return phases
```

**Stress test:**

| Scenario | What happens |
|---|---|
| Normal: rule references `phase-04-implementation` | ✅ Found in `coordinator/phase-04-implementation.md` |
| Typo: rule references `phase-04-implmentation` | ✅ Warning: not found on disk |
| Tutorial: rule references `tutorial:first-pytest:step-01` | ✅ Found in tutorial manifest |
| New tutorial added, rule references it | ✅ Works if you run generate_hooks.py after adding tutorial |
| Phase file renamed | ⚠️ Rules silently break until generate_hooks.py re-runs |
| Phase files don't exist yet (v1: COORDINATOR.md not split) | ❌ **Discovers nothing.** No phase-*.md files exist today. |

**The killer problem:** Option A requires the phase files to exist on disk. Today, COORDINATOR.md is a single file. If we don't split it, there's nothing to discover. And we decided not to split it.

For tutorials, discovery works — `tutorial.yaml` manifests exist and contain step IDs. But project-team phases don't have files to discover from unless you split the Coordinator file or create stub phase files solely for discovery.

**Maintenance burden:** Medium. Every new workflow that defines phases needs files in a discoverable location. The generator needs to know where to look (hardcoded paths or a config).

**Verdict: Doesn't work for project-team phases without file splitting. Works for tutorials. Partial solution.**

---

## Option B: Declare in rules.yaml

**Mechanism:** A top-level `known_phases` section in rules.yaml declares all valid phase IDs.

```yaml
catalog_version: "1"
ack_ttl_seconds: 60

known_phases:
  project:
    - vision
    - setup
    - spawn
    - specification
    - implementation
    - testing
    - signoff
    - integration
    - e2e
    - final
  tutorial:
    - "first-pytest:create-test"
    - "first-pytest:run-test"
    - "first-pytest:make-pass"

rules:
  - id: R01
    phase_block: [testing]
    # ...
```

**Stress test:**

| Scenario | What happens |
|---|---|
| Normal: rule references `testing` | ✅ Found in known_phases.project |
| Typo: `testng` | ✅ Warning: not in known_phases |
| New tutorial added | ⚠️ Must update known_phases in rules.yaml manually |
| Phase renamed in workflow | ⚠️ Must update both known_phases and all rules referencing it |
| Phase list grows large (20 tutorials × 5 steps = 100 entries) | ⚠️ rules.yaml bloats with phase IDs |
| Two maintainers: one edits tutorials, one edits rules | ⚠️ Must coordinate: tutorial author must also update rules.yaml |

**The killer problem:** Phase definitions live in the wrong file. Tutorial phases are defined by tutorial manifests (`tutorial.yaml`). Project phases are defined by the workflow (`COORDINATOR.md`). Declaring them again in `rules.yaml` creates a second source of truth. When someone adds a tutorial step, they must also update `rules.yaml` — or the new step's phase ID can't be used in guardrail rules.

This is the same problem as hardcoding role names in a config instead of deriving them from agent definitions. The generator already avoids this for roles — it discovers them from `AI_agents/**/*.md`.

**Maintenance burden:** High. Every workflow change requires a rules.yaml update. Two files must stay in sync.

**Verdict: Works for validation but creates a sync problem. The wrong file owns the phase definitions.**

---

## Option C: Declare in workflow.yaml per Workflow Directory

**Mechanism:** Each workflow defines its own phases in its own directory. The generator discovers and merges them.

```yaml
# AI_agents/project_team/workflow.yaml
id: project
phases:
  - vision
  - setup
  - spawn
  - specification
  - implementation
  - testing
  - signoff
  - integration
  - e2e
  - final
```

```yaml
# tutorials/content/first-pytest/tutorial.yaml (already exists)
id: first-pytest
steps:
  - id: create-test
  - id: run-test
  - id: make-pass
# Steps ARE the phase definitions — no separate declaration needed
```

Generator discovers phases:

```python
def discover_phases() -> dict[str, set[str]]:
    phases = {}
    # Project team workflow
    wf = Path("AI_agents/project_team/workflow.yaml")
    if wf.exists():
        data = yaml.safe_load(wf.read_text())
        phases[data["id"]] = set(data["phases"])
    # Tutorial workflows (tutorial.yaml manifests)
    for manifest in Path("tutorials/content/").glob("*/tutorial.yaml"):
        data = yaml.safe_load(manifest.read_text())
        tid = data["id"]
        phases[f"tutorial:{tid}"] = {s["id"] for s in data.get("steps", [])}
    return phases
```

**Stress test:**

| Scenario | What happens |
|---|---|
| Normal: rule references `project:testing` | ✅ Found in workflow.yaml |
| Typo: `project:testng` | ✅ Warning: not in workflow.yaml phases |
| Tutorial reference: `tutorial:first-pytest:run-test` | ✅ Found in tutorial.yaml steps |
| New tutorial added | ✅ Auto-discovered from tutorial.yaml |
| New project phase added | ✅ Edit workflow.yaml (one file, one place) |
| Phase renamed | ⚠️ Must update workflow.yaml + rules referencing it (but only 2 files, co-located) |
| rules.yaml and workflow.yaml disagree | Impossible — workflow.yaml is the source, rules.yaml references it |
| workflow.yaml doesn't exist | ✅ No project phases — generator warns if rules reference `project:*` phases |
| 20 tutorials × 5 steps | ✅ Each tutorial's phases are defined in its own manifest. Generator merges. No single file bloats. |
| Maintainer adds tutorial, doesn't know about rules | ✅ Tutorial phases auto-discovered. Rules can reference them whenever. |

**New file needed:** `AI_agents/project_team/workflow.yaml` — ~15 lines. Defines the project team's phase names.

**Changes to generator:** Add phase discovery to `validate_rules()`. ~30 lines. Same pattern as the existing role-name validation (lines 448-462 of generate_hooks.py):

```python
# Existing pattern for roles:
_expected = f'{_s.upper()}.md'
if _agents_dir.exists() and not list(_agents_dir.rglob(_expected)):
    print(f"[GUARDRAIL NOTE] ... role '{_entry}' ... no agent definition file found ...")

# Same pattern for phases:
if phase_ref not in all_known_phases:
    print(f"[GUARDRAIL NOTE] ... phase '{phase_ref}' ... not found in any workflow.yaml ...")
```

**Maintenance burden:** Low. Each workflow owns its phases. Tutorial manifests already define steps (no new declaration). Project workflow gets one small YAML file.

---

## Comparison Matrix

| Criterion | A: Auto-discover files | B: Declare in rules.yaml | C: Per-workflow YAML |
|---|---|---|---|
| Single source of truth | ⚠️ Files are the source (but project phase files don't exist) | ❌ Duplicated in rules.yaml | ✅ Each workflow owns its phases |
| Works without splitting COORDINATOR.md | ❌ No | ✅ Yes | ✅ Yes (workflow.yaml is a new, small file) |
| Tutorial phase registration | ✅ Auto from tutorial.yaml | ⚠️ Manual sync | ✅ Auto from tutorial.yaml |
| Typo detection | ✅ At generation time | ✅ At generation time | ✅ At generation time |
| Scales to many tutorials | ✅ | ❌ rules.yaml bloats | ✅ Distributed across manifests |
| Generator complexity | Medium (multi-path discovery) | Low (single-file read) | Medium (multi-path discovery) |
| New workflow setup cost | Must create phase files | Must update rules.yaml | Must create workflow.yaml (~15 lines) |
| Consistency with existing patterns | Partial (similar to role discovery) | Inconsistent (roles aren't declared in rules.yaml) | ✅ Matches role pattern: define near source, discover in generator |

---

## Should Runtime phase_guard.py Also Validate?

**No. And this matters.**

The generator validates at generation time. If a phase reference is invalid, the developer sees a warning when running `generate_hooks.py`. This is the right time — it's cheap, it's before deployment, it catches typos early.

Runtime validation would mean: every time a guardrail hook fires, it reads all workflow.yaml files to check if the current phase is valid. This is:
- **Expensive** — file I/O on every hook invocation
- **Fragile** — if a workflow.yaml is corrupted or missing, the hook fails
- **Redundant** — the generator already validated

Runtime should do one thing: read `phase_state.json`, get the current phase string, compare against the rule's `phase_allow`/`phase_block` list. If the current phase isn't in the list, skip the rule. No validation of whether the phase is "known" — that was done at generation time.

The only runtime check worth considering: if `phase_state.json` contains a phase that was never seen during generation, log a warning to `hits.jsonl`. This catches the case where someone manually edits `phase_state.json` with a typo. But it's not enforcement — just audit.

---

## Recommendation

**Option C.** One new file (`AI_agents/project_team/workflow.yaml`, ~15 lines). Tutorial phases auto-discovered from existing `tutorial.yaml` manifests. Generator validates all `phase_allow`/`phase_block` references against the merged phase set. Warn (not error) on unknown phases — same as the existing role-name validation pattern.

**Why not A:** Requires phase files on disk. Project phases don't have files (COORDINATOR.md isn't split). Would work for tutorials but fails for the primary use case.

**Why not B:** Creates a second source of truth. Tutorial authors must update `rules.yaml` when adding steps. This is the sync problem that Option C avoids by deriving phases from their source.

**Why C over a simpler approach:** Option C follows the existing pattern in `generate_hooks.py` — roles are discovered from agent definition files on disk, not declared in rules.yaml. Phases should be discovered from workflow definitions on disk, not declared in rules.yaml. Same pattern, same code path, same developer experience.

**Implementation:**

1. Create `AI_agents/project_team/workflow.yaml` (~15 lines):
```yaml
id: project
phases: [vision, setup, spawn, specification, implementation, testing, signoff, integration, e2e, final]
```

2. Add `discover_phases()` to `generate_hooks.py` (~30 lines):
   - Read `AI_agents/project_team/workflow.yaml` for project phases
   - Read `tutorials/content/*/tutorial.yaml` for tutorial phases
   - Return merged `dict[str, set[str]]`

3. Add phase validation to `validate_rules()` (~15 lines):
   - For each rule with `phase_allow` or `phase_block`, check references against discovered phases
   - Warn (not error) on unknown phase — same as role validation

4. No runtime validation beyond reading `phase_state.json`.

**Total: ~60 lines of new code + 15 lines of YAML.**
