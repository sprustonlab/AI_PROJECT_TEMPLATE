# Phase Pre-Registration and Validation Patterns

**Requested by:** Coordinator
**Date:** 2026-04-03
**Tier of best source found:** T1 (Primary source code)

## Query

Research existing codebase patterns for validation, registration, and discovery that inform how phase pre-registration should work. Specific questions: How does generate_hooks.py validate rule IDs? How does copier handle enums? Are there existing registry patterns? How does rules.d/ discovery work? Could generate_hooks.py auto-discover phase-*.md files?

---

## 1. How generate_hooks.py Validates Rule IDs

### Two-layer validation: structural + collision

**Layer 1: `validate_rules()` (lines 319-472) — Structural validation**

This function validates each rule's schema in isolation. It checks:

| Check | How | Failure Mode |
|-------|-----|-------------|
| Required fields present | `if "id" not in rule` | `sys.exit(1)` — hard fail |
| Enforcement value valid | `enforcement not in ("warn", "deny", "log", "inject")` | `sys.exit(1)` |
| allow/block mutual exclusivity | `if has_allow and has_block` | `sys.exit(1)` |
| Regex pattern compiles | `re.compile(pattern)` in try/except | `sys.exit(1)` |
| MCP trigger has required fields | `if trigger == "mcp" and not detect.get("mcp_server")` | `sys.exit(1)` |
| Named roles exist as agent files | `glob("AI_agents/**/" + name + ".md")` | `stderr warning` (soft) |
| Pattern field present for regex rules | `if detect_type in ("regex", ...) and not pattern` | `sys.exit(1)` |

Key design principle: **fail-fast on structural errors, warn on semantic issues.** A missing `id` field kills the generator. A named role that doesn't match an agent file gets a warning but proceeds.

**Layer 2: `check_id_collisions()` (lines 1957-1975) — Cross-rule validation**

```python
def check_id_collisions(core_rules, contributed_rules):
    seen = {}
    for rule in core_rules + contributed_rules:
        rid = rule["id"]
        if rid in seen:
            print(f"ERROR: Duplicate rule ID '{rid}' ...", file=sys.stderr)
            sys.exit(1)
        seen[rid] = source_label
```

This runs AFTER all rules are loaded (core + contributed from rules.d/). It enforces global uniqueness of rule IDs across all sources. The convention is:
- `R01`-`R99`: Core rules in `rules.yaml`
- `HPC01`, `BIO01`, etc.: Contributed rules in `rules.d/*.yaml`

**No formal registry of IDs exists.** Uniqueness is enforced at generation time by scanning all loaded rules. This is a **late-binding validation** pattern — you can use any ID you want, and the generator tells you if it collides.

### Relevance to phase registration

This pattern suggests phases should also use **late-binding validation** rather than a pre-defined registry. The generator discovers all phase references (from rules, from content files) and validates consistency at generation time.

---

## 2. How copier.yml Handles Enums

### Pattern: `choices` dict with display → value mapping

```yaml
target_platform:
  type: str
  help: "Target conda platform"
  choices:
    "Auto-detect (recommended)": "auto"
    "Linux x86_64": "linux-64"
    "macOS ARM64": "osx-arm64"
    "Windows x86_64": "win-64"
    "All platforms": "all"
  default: "auto"

claudechic_mode:
  type: str
  choices:
    "Standard — Hints + Guardrails": "standard"
    "Developer — Full customisation toolkit": "developer"
  default: "standard"
```

**Key properties:**
1. **Closed set** — all valid values enumerated at template time
2. **Human labels separate from machine values** — "Auto-detect (recommended)" → `"auto"`
3. **Default provided** — always a sensible default
4. **Immutable after instantiation** — choices are baked into `.copier-answers.yml`

**Boolean feature flags** follow a simpler pattern:
```yaml
use_guardrails:
  type: bool
  default: true
use_project_team:
  type: bool
  default: true
```

### Relevance to phase registration

Phases are NOT a copier-time concern. They're runtime state, not template configuration. The copier pattern is wrong for phases — phases change during execution, copier answers don't.

However, the **closed set** idea is relevant: the valid phase numbers (0-9) could be declared once and validated everywhere. The question is where that declaration lives.

---

## 3. Existing Registry Patterns in the Codebase

### Pattern A: Static list with extension point (`hints/hints.py`)

```python
def get_hints() -> list[HintSpec]:
    """Return all registered hints."""
    hints: list[HintSpec] = [
        HintSpec(id="git-not-initialized", ...),
        HintSpec(id="guardrails-only-default", ...),
        HintSpec(id="project-team-never-used", ...),
        HintSpec(id="pattern-miner-underutilized", ...),
        HintSpec(id="mcp-tools-empty", ...),
        HintSpec(id="cluster-configured-unused", ...),
    ]
    # Dynamic extension:
    hints.append(_make_learn_command_hint())
    return hints
```

**Properties:**
- All hints registered in one function
- IDs are string constants embedded in the list
- No external registry file — code IS the registry
- Extension via appending to the list
- Discovery: caller calls `get_hints()` and gets everything

### Pattern B: Directory scanning (`rules.d/` discovery)

```python
def load_rules_d(rules_d_dir: Path) -> list[dict]:
    """Load contributed rules from rules.d/*.yaml files."""
    if not rules_d_dir.is_dir():
        return []
    contributed = []
    for yaml_file in sorted(rules_d_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            rules = data.get("rules", [])
            for rule in rules:
                rule["_source"] = yaml_file.name
            contributed.extend(rules)
        except (yaml.YAMLError, OSError) as e:
            print(f"WARNING: Skipping {yaml_file.name}: {e}", file=sys.stderr)
    return contributed
```

**Properties:**
- Convention-based: any `*.yaml` in `rules.d/` is a rule file
- Sorted order for deterministic output
- Source tracking: `rule["_source"] = yaml_file.name`
- Graceful degradation: bad files get warnings, not crashes
- Merged into the main rules list for unified validation

### Pattern C: Convention-based discovery (ClaudeChic hints)

From `hints/_state.py`, `CopierAnswers` checks feature flags, and the hints system checks `Path.cwd() / "hints"` exists. No registry — presence of the directory IS the registration.

### Summary of registry patterns

| Pattern | Where | Registration | Discovery | Validation |
|---------|-------|-------------|-----------|------------|
| Static list | get_hints() | Code constants | Function call | Implicit (type system) |
| Directory scan | rules.d/ | Drop file in directory | Glob + sorted | Post-load (validate_rules) |
| Convention | ClaudeChic hints | Directory exists | Path.exists() | Import-time |

---

## 4. How rules.d/ Discovery Could Be Reused for Phase Discovery

### Direct analog: `phases.d/` or `content/phase-*.md`

**Option A: Directory-based (like rules.d/)**

```
.ao_project_team/<project>/phases/
  phase-01-leadership.md
  phase-02-composability.md
  phase-03-specification.md
  ...
```

Discovery:
```python
def load_phases(phases_dir: Path) -> list[dict]:
    if not phases_dir.is_dir():
        return []
    phases = []
    for md_file in sorted(phases_dir.glob("phase-*.md")):
        # Parse phase number from filename
        match = re.match(r'phase-(\d+)-(.+)\.md', md_file.name)
        if match:
            phases.append({
                "number": int(match.group(1)),
                "slug": match.group(2),
                "path": md_file,
            })
    return phases
```

**Option B: Manifest-based (like tutorial.yaml)**

```yaml
# phases.yaml
phases:
  - number: 1
    name: "Leadership Alignment"
    file: "phase-01-leadership.md"
    guardrails: { scope: { phase: [1] } }
    verification:
      - type: file_exists
        path: "specification/leadership_*.md"
  - number: 2
    name: "Composability Analysis"
    file: "phase-02-composability.md"
    ...
```

**Option C: Hybrid (directory + validation)**

Files discovered by convention (glob), validated against a schema. This is what `rules.d/` does — files are discovered by glob, then each is validated by `validate_rules()`.

### Recommendation: Option C (Hybrid)

**Why:** It combines the simplicity of directory scanning (drop a file → it's registered) with the safety of validation (bad files caught at generation time). This is the exact pattern `rules.d/` already uses, and it's proven in this codebase.

The generator would:
1. Scan `phases/phase-*.md` (or wherever phase files live)
2. Parse phase numbers from filenames
3. Validate: sequential, no gaps, no duplicates
4. Cross-reference against `scope.phase` values in rules — warn if a rule references a phase that has no content file

---

## 5. Could generate_hooks.py Auto-Discover phase-*.md Files?

### Answer: YES, but it shouldn't be the ONLY discovery mechanism.

**What generate_hooks.py already knows at generation time:**

1. All rules (core + contributed) — from `rules.yaml` + `rules.d/*.yaml`
2. All `scope.phase` values across all rules — by iterating loaded rules
3. The project root — from `GUARDRAILS_DIR` or cwd

**What it COULD discover:**

```python
def discover_phase_files(project_root: Path) -> dict[int, Path]:
    """Find all phase content files in the project."""
    ao_dir = project_root / '.ao_project_team'
    if not ao_dir.is_dir():
        return {}
    phase_files = {}
    for project_dir in ao_dir.iterdir():
        if not project_dir.is_dir():
            continue
        phases_dir = project_dir / 'phases'
        if not phases_dir.is_dir():
            continue
        for md_file in sorted(phases_dir.glob('phase-*.md')):
            match = re.match(r'phase-(\d+)', md_file.name)
            if match:
                phase_num = int(match.group(1))
                phase_files[phase_num] = md_file
    return phase_files
```

**Cross-validation at generation time:**

```python
# In validate_rules() or a new validate_phase_scope():
phase_files = discover_phase_files(project_root)
for rule in rules:
    scope = rule.get("scope", {})
    phases = scope.get("phase", [])
    for p in phases:
        if p not in phase_files:
            print(f"WARNING: Rule {rule['id']} references phase {p} "
                  f"but no phase-{p:02d}-*.md file found",
                  file=sys.stderr)
```

**Why it shouldn't be the ONLY mechanism:**

1. **generate_hooks.py runs at generation time**, not at phase transition time. Phase files might be added later (after initial generation).
2. **Hooks run at tool-invocation time.** The generated hooks read `phase_state.json` at runtime — they don't need to know about phase files.
3. **Phase content is consumed by the Coordinator** (via `Read` tool), not by the hook system.

**The right split:**

| Concern | When | Who |
|---------|------|-----|
| Phase file exists for referenced phase numbers | Generation time | generate_hooks.py (warning) |
| Current phase is valid (within declared range) | Runtime (phase transition) | PhaseStateStore.set_phase() |
| Phase-scoped rule fires/skips based on current phase | Runtime (tool invocation) | Generated hook via phase_guard.py |
| Phase content is loaded for current phase | Runtime (Coordinator turn) | Coordinator reads phase-NN-*.md |

---

## 6. Proposed Phase Validation Architecture

Based on all patterns discovered:

### Registration: Convention-based discovery

```
.ao_project_team/<project>/phases/
  phase-00-kickoff.md
  phase-01-leadership.md
  ...
  phase-09-retrospective.md
  phase_state.json          # runtime state (atomic writes)
```

Phase numbers are extracted from filenames. No separate registry file needed — the **filesystem IS the registry** (same as `rules.d/`).

### Validation: Three checkpoints

**Checkpoint 1: Generation time (generate_hooks.py)**
- Warn if `scope.phase` references non-existent phase files
- Validate `scope.phase` values are lists of positive integers
- No hard failure — rules without matching phase files still generate (they just never fire)

**Checkpoint 2: State transition time (PhaseStateStore.set_phase())**
```python
def set_phase(self, phase: int, updated_by: str) -> None:
    if not isinstance(phase, int) or phase < 0:
        raise ValueError(f"Invalid phase number: {phase}")
    # Optional: validate against discovered phases
    self._current_phase = phase
    self._updated_by = updated_by
    self._updated_at = datetime.now(timezone.utc).isoformat()
    self.save()
```

**Checkpoint 3: Hook runtime (phase_guard.py)**
```python
def get_current_phase(cwd: str) -> int | None:
    """Returns None if no phase state exists — rule fires unconditionally."""
    # ... read phase_state.json ...
    # No validation here — just read and return. Fast path.
```

### ID Convention

Following the existing patterns:
- Rule IDs: `R01`-`R99` (core), `HPC01`/`BIO01` (contributed)
- Phase numbers: `0`-`9` (matching COORDINATOR.md's 9 phases)
- Phase file naming: `phase-{NN}-{slug}.md` (zero-padded, like step files in tutorial spec)

### What NOT to build

1. **No central phase registry file** — filesystem discovery is sufficient (like rules.d/)
2. **No phase enum in copier.yml** — phases are runtime, not template-time
3. **No phase validation in hooks** — hooks read phase_state.json and trust it (fast path)
4. **No phase<->rule mapping file** — the mapping lives in `scope.phase` inside each rule

---

## Summary

| Question | Answer | Pattern Source |
|----------|--------|---------------|
| How are rule IDs validated? | Late-binding: load all → check_id_collisions() | generate_hooks.py lines 1957-1975 |
| How does copier handle enums? | `choices` dict, closed set, immutable after instantiation | copier.yml |
| Existing registry patterns? | Static list (hints), directory scan (rules.d/), convention (ClaudeChic) | hints.py, generate_hooks.py |
| Can rules.d/ pattern work for phases? | YES — glob phase-*.md, parse number from filename, validate | load_rules_d() lines 1924-1954 |
| Can generate_hooks.py auto-discover phases? | YES for cross-validation warnings; NO as sole mechanism | New discover_phase_files() function |

**Recommended approach:** Convention-based discovery (filesystem IS the registry) + three-checkpoint validation (generation time, state transition time, hook runtime). Total additional code for phase discovery+validation: ~30-40 lines in generate_hooks.py, ~10 lines in PhaseStateStore.

This adds to the previous estimate: ~273 lines (infrastructure) + ~40 lines (phase validation) = **~313 lines total**. Still well within a manageable scope for two PRs.
