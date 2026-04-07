# Cross-System Config Patterns: Where Should Phase Config Live?

**Requested by:** Coordinator
**Date:** 2026-04-04
**Tier of best source found:** T1 (Primary source code)

## Query

How does this codebase handle config that spans multiple systems? Should phase files contain checks/hints config in their frontmatter, or should that config live elsewhere and be synced/generated?

---

## 1. How Hints Get Their Configuration

### Answer: All in code. Zero external config files.

Hint configuration is defined entirely in Python:

```python
# hints/hints.py — the ENTIRE configuration for all 7 hints:
_STATIC_HINTS: list[HintSpec] = [
    HintSpec(
        id="git-setup",
        trigger=GitNotInitialized(),           # trigger class
        message="No git repo detected...",      # inline string
        severity="warning",                     # literal
        priority=1,                             # int
        lifecycle=ShowUntilResolved(),          # lifecycle class
    ),
    # ... 5 more ...
]
```

**No YAML, no JSON, no frontmatter.** The trigger classes are frozen dataclasses with their own config fields:

```python
@dataclass(frozen=True)
class GuardrailsOnlyDefault:
    rules_file: str = ".claude/guardrails/rules.yaml"    # config as default field
    rules_dir: str = ".claude/guardrails/rules.d"        # config as default field

    def check(self, state: ProjectState) -> bool:
        # ... uses self.rules_file, self.rules_dir ...
```

**Why code-only works here:**
- Small set (7 hints) — no need for external discovery
- Config is tightly coupled to behavior (trigger class + config are the same object)
- Users extend by editing the Python file directly
- No generation step — hints are evaluated directly from code

### What hints DON'T have

- No YAML manifest listing hints
- No discovery from filesystem (hints are registered in `get_hints()`, not glob'd)
- No frontmatter in any file
- No config/code split — config IS the code

---

## 2. How copier.yml Coordinates Config Across Multiple Files

### Answer: Single source of truth → Jinja templates → multiple output files.

**The pattern:**

```
copier.yml (SINGLE SOURCE)
    ↓ answers
template/pixi.toml.jinja        → pixi.toml       (uses project_name, target_platform)
template/activate.jinja          → activate         (uses project_name)
template/rules.yaml.jinja       → rules.yaml       (uses project_name)
template/COORDINATOR.md.jinja    → COORDINATOR.md   (uses project_name)
template/lsf.yaml.jinja         → lsf.yaml         (uses cluster_ssh_target)
template/slurm.yaml.jinja       → slurm.yaml       (uses cluster_ssh_target)
template/ci.yml.jinja            → ci.yml           (uses project_name)
```

**Plus conditional inclusion/exclusion:**

```yaml
# copier.yml lines 105-121
_exclude:
  - "{% if not use_guardrails %}.claude/guardrails/{% endif %}"
  - "{% if not use_project_team %}AI_agents/{% endif %}"
  - "{% if not use_hints %}hints/{% endif %}"
  - "{% if not use_cluster %}mcp_tools/_cluster.py{% endif %}"
```

**Key properties:**
1. **One-time generation** — copier runs at project creation, produces static files
2. **No ongoing sync** — generated files are owned by the user after creation
3. **Simple variable substitution** — `{{ project_name }}`, not complex logic
4. **Feature gating** — entire directories excluded based on boolean flags

### The copier pattern is: "fan-out at creation time, then independent"

After copier runs, `pixi.toml` and `rules.yaml` are independent files. Editing one doesn't update the other. There's no ongoing sync mechanism — copier is a one-shot generator.

---

## 3. How generate_hooks.py Pulls From rules.yaml

### Answer: Single source of truth → generation step → multiple output files. With staleness detection.

**The pattern:**

```
rules.yaml + rules.d/*.yaml (SINGLE SOURCE)
    ↓ generate_hooks.py
.claude/guardrails/hooks/bash_guard.py     (R01, R02, R03, R04)
.claude/guardrails/hooks/write_guard.py    (R05)
.claude/settings.json                       (hook registrations)
```

**This is the most sophisticated generation pattern in the codebase.** Details:

**Input aggregation:**
```python
# generate_hooks.py lines 1924-1954
def load_rules_d(rules_d_dir):
    for yaml_file in sorted(rules_d_dir.glob("*.yaml")):
        data = load_rules_yaml(yaml_file)
        extra_rules.extend(data.get("rules", []))
```
Multiple input files merged into one rule list.

**Validation before generation:**
```python
validate_rules(rules)           # schema check each rule
check_id_collisions(rules)      # cross-rule uniqueness
```

**Code generation per trigger type:**
```python
# Rules grouped by trigger, each group gets its own hook file
grouped = group_rules_by_trigger(rules)
for trigger, trigger_rules in grouped.items():
    code = generate_bash_guard(trigger_rules)  # or write_guard, etc.
    output_dir / filename  →  write code
```

**Settings.json sync (the most nuanced part):**
```python
# generate_hooks.py lines 1896-1917
def update_settings_json(new_triggers):
    pre_tool_use = settings.setdefault('hooks', {}).setdefault('PreToolUse', [])
    for matcher, hook_filename in new_triggers:
        existing = next((e for e in pre_tool_use if e.get('matcher') == matcher), None)
        if existing:
            # Update in-place if command changed
            if current_cmd != hook_cmd:
                existing['hooks'] = [{'type': 'command', 'command': hook_cmd}]
                changed = True
        else:
            # Append new entry
            pre_tool_use.append({...})
            changed = True
    if changed:
        settings_path.write_text(json.dumps(settings, indent=2))
```

**This is NOT a full overwrite** — it merges into existing settings.json, preserving user-added entries.

**Staleness detection (activate script):**
```bash
# activate.jinja lines 41-47
if [[ ! -f "$_settings" ]] || [[ "$_rules" -nt "$_settings" ]]; then
    echo "🔄 Guardrail rules changed — regenerating hooks..."
    python3 "$BASEDIR/.claude/guardrails/generate_hooks.py"
fi
```
`rules.yaml` mtime vs `settings.json` mtime. If rules are newer, regenerate.

**Also invoked at:**
- Project creation: copier post-task (line 129)
- Manual: `pixi run generate-hooks`
- CI: `generate_hooks.py --check` (diff-compare, no write)

### The generate_hooks.py pattern is: "single source → validated transform → multiple outputs, with staleness auto-regen"

---

## 4. Existing Patterns Where One File's Content is Generated From Another

### Pattern A: rules.yaml → hook scripts (generate_hooks.py)

Already covered above. This is the primary and most mature example.

### Pattern B: copier.yml answers → .jinja templates (copier)

One-shot at project creation. Produces 8+ files from a single questionnaire.

### Pattern C: settings.json ← generate_hooks.py (merge, not overwrite)

Settings.json is a **shared config file** — both generate_hooks.py and potentially the user edit it. The generator carefully merges its entries without destroying user content.

### Pattern D: pixi.toml → pixi.lock (pixi)

External tool. `pixi.toml` is the source of truth for dependencies. `pixi.lock` is the deterministic resolved output. Never hand-edited.

### Pattern E: Auto-generated file markers

All generated hook files carry the header:
```python
"""bash_guard.py — AUTO-GENERATED by generate_hooks.py — DO NOT EDIT

Edit rules.yaml and re-run: python3 .claude/guardrails/generate_hooks.py
catalog_version: 1
Rules: R01, R02, R03, R04"""
```

This pattern: **generated files are clearly marked, with instructions pointing to the source of truth.**

### What does NOT exist

- **No YAML frontmatter consumed programmatically by Python code.** Skill files (`.claude/commands/*.md`) have YAML frontmatter, but it's consumed by Claude Code itself, not by any Python code in this codebase.
- **No Markdown file whose content drives code generation.** The Coordinator's COORDINATOR.md is read by agents at runtime, not parsed by any generator.
- **No bidirectional sync.** All generation flows are one-directional: source → output.

---

## 5. Analysis: Where Should Phase Config Live?

### The question restated

Phase files (`phase-01-leadership.md`, etc.) could contain:
1. **Content** — the instructions for the Coordinator during that phase
2. **Check definitions** — what to verify before moving to the next phase
3. **Guardrail scope** — which rules are active during this phase
4. **Hints config** — which hints are relevant during this phase

Should (2), (3), (4) live inside the phase file (as YAML frontmatter) or somewhere else?

### Option A: Frontmatter in phase files

```markdown
---
phase: 1
name: Leadership Alignment
checks:
  - type: file_exists
    path: "specification/leadership_*.md"
  - type: command
    cmd: ["grep", "-l", "recommendation", "specification/"]
guardrails:
  scope: { phase: [1] }
  rules: [R01]
hints:
  - id: "phase1-spawn-agents"
    message: "Remember to spawn Leadership agents"
---

# Phase 1: Leadership Alignment

Spawn three Leadership agents...
```

**Pros:**
- Single file per phase — everything in one place
- Easy to read/understand a phase's full definition
- Follows tutorial.yaml's step definition pattern (from axis_content.md spec)

**Cons:**
- **No existing pattern for this.** Zero files in the codebase have YAML frontmatter consumed by Python code.
- **Requires a new parser.** Need to split frontmatter from Markdown content, validate the YAML, and route config to three different systems (checks, guardrails, hints).
- **Violates the single-source-of-truth pattern.** Guardrail rules live in `rules.yaml`. Putting `guardrails.scope` in frontmatter means guardrail config is split across two places.
- **generate_hooks.py would need to parse Markdown.** Currently it only reads YAML. Adding a Markdown frontmatter parser is new complexity for no functional gain.

### Option B: Phase files = content only, config lives in existing systems

```
# Phase file: pure content (what the Coordinator reads)
.ao_project_team/<project>/phases/phase-01-leadership.md

# Guardrail scope: in rules.yaml (where ALL guardrail config lives)
rules.yaml:
  - id: R01
    scope: { phase: [4, 5] }   # ← the existing proposal

# Check definitions: in a phase manifest (new file, YAML)
.ao_project_team/<project>/phases/phases.yaml:
  phases:
    - number: 1
      checks:
        - type: file_exists
          path: "specification/leadership_*.md"

# Hints: in hints.py (where ALL hint config lives)
hints.py:
  HintSpec(id="phase1-spawn", trigger=PhaseIs(1), ...)
```

**Pros:**
- **Matches every existing pattern.** Guardrail config stays in rules.yaml. Hint config stays in code. New check config gets its own YAML file.
- **No new parser needed.** generate_hooks.py reads YAML (already does). Check engine reads YAML (new but straightforward).
- **Single source of truth per concern.** rules.yaml for guardrails. phases.yaml for checks. hints.py for hints.
- **Phase Markdown files stay human-readable.** No frontmatter clutter — just the content the Coordinator needs.

**Cons:**
- Config is spread across files — need to cross-reference to understand a complete phase definition
- Adding a new phase requires touching multiple files

### Option C: Phase manifest as the orchestrator (hybrid)

```yaml
# .ao_project_team/<project>/phases.yaml — the SINGLE SOURCE for phase structure
phases:
  - number: 1
    name: "Leadership Alignment"
    content: "phases/phase-01-leadership.md"    # pointer to content file
    checks:
      - type: file_exists
        path: "specification/leadership_*.md"
    guardrail_scope: [1]                        # referenced by generate_hooks.py
```

```yaml
# rules.yaml — references phases.yaml indirectly via scope field
- id: R01
  scope: { phase: [4, 5] }   # phase numbers, validated against phases.yaml
```

**generate_hooks.py reads phases.yaml for validation only** (cross-reference scope.phase values). The actual scope field stays in rules.yaml.

**Pros:**
- **One file defines all phases** — the manifest is the registry
- **Content files stay clean** — no frontmatter
- **Check config co-located with phase definitions** — natural grouping
- **Guardrail config stays in rules.yaml** — no split
- **Follows the tutorial.yaml pattern** from the specification (manifest + content files)

**Cons:**
- New file (phases.yaml) that needs to stay in sync with content files
- But this is the exact same relationship as rules.yaml ↔ hook files — proven pattern

---

## 6. Recommendation: Option C (Phase Manifest)

### Why

**It follows the generate_hooks.py pattern exactly:**

| Aspect | Guardrails | Phases |
|--------|-----------|--------|
| Config source | `rules.yaml` + `rules.d/*.yaml` | `phases.yaml` |
| Content files | Hook scripts (generated) | Phase Markdown (hand-written) |
| Validation | `validate_rules()` + `check_id_collisions()` | `validate_phases()` (new) |
| Discovery | `load_rules_d()` glob | `phases.yaml` manifest |
| Cross-reference | rule IDs unique globally | phase numbers unique per project |
| Staleness | `rules.yaml` mtime vs `settings.json` | `phases.yaml` mtime (if needed) |

**And it follows the tutorial.yaml pattern from the spec:**

```yaml
# From axis_content.md — tutorial manifest:
steps:
  - id: "create-feature-branch"
    file: "step-01-branch.md"
    verification:
      type: command_output
      command: "git branch --show-current"
      expected: "feature/"

# Analogous phases.yaml:
phases:
  - number: 1
    name: "Leadership Alignment"
    content: "phase-01-leadership.md"
    checks:
      - type: file_exists
        path: "specification/leadership_*.md"
```

The tutorial step manifest and the phase manifest are **structurally identical**. This validates the "tutorials and team workflow are the same pattern" insight.

### What NOT to do

1. **Don't put frontmatter in phase Markdown files.** No existing pattern for Python-consumed frontmatter. Don't invent one.
2. **Don't put guardrail scope in the phase manifest.** Scope lives in rules.yaml, validated by cross-reference. Don't split guardrail config.
3. **Don't put hint definitions in the phase manifest.** Hints are code (frozen dataclasses). A phase-aware trigger class (`PhaseIs(n)`) is cleaner than YAML-defined hints.
4. **Don't make generate_hooks.py parse Markdown.** It reads YAML. Keep it that way.

### The clean separation

| Concern | Where | Why |
|---------|-------|-----|
| Phase structure + checks | `phases.yaml` | New manifest, follows tutorial.yaml pattern |
| Phase content (agent instructions) | `phase-NN-*.md` | Pure Markdown, no frontmatter |
| Guardrail phase scope | `rules.yaml` (scope field) | Single source for all guardrail config |
| Phase-aware hints | `hints.py` (PhaseIs trigger) | Single source for all hint config |
| Cross-validation | `generate_hooks.py` | Validates scope.phase refs against phases.yaml |

**Each system's config stays in its own home.** The phase manifest defines structure and checks. Everything else cross-references by phase number.

---

## Summary

| Question | Answer |
|----------|--------|
| How do hints get config? | **All in Python code** — frozen dataclasses with default fields. No YAML, no frontmatter. |
| How does copier coordinate config? | **Single source (copier.yml) → Jinja templates → multiple files.** One-shot at creation. |
| How does generate_hooks.py pull from rules.yaml? | **YAML → validated transform → multiple hook files + settings.json merge.** Staleness auto-regen. |
| Any file content generated from another? | **Yes:** rules.yaml → hooks, copier.yml → templates, pixi.toml → pixi.lock. All one-directional. |
| Should phase files have frontmatter? | **No.** No existing pattern for Python-consumed frontmatter. Phase manifest (phases.yaml) is the right approach. |
| Where should check config live? | **In phases.yaml** — co-located with phase definitions, analogous to tutorial.yaml step verification. |
| Where should guardrail scope live? | **In rules.yaml** — where ALL guardrail config already lives. Cross-validated against phases.yaml. |
