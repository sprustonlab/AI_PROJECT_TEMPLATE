# Tutorial System: Architecture Specification

**Status:** Definitive — all other files in `specification/` are superseded.
**Author:** Composability (Lead Architect)
**Date:** 2026-04-04

---

## 1. Vision

Build **general infrastructure primitives** that tutorials, project-team workflows, and future systems consume. The tutorial system is the first consumer, not the architecture.

**Principle:** v1 is infrastructure. v2 is tutorial.

### What v1 delivers

1. **Check primitive** — reusable assertion protocol with evidence
2. **Phase primitive** — unified state that scopes guardrails, gates, and hints
3. **Phase-scoped guardrails** — existing rules gain `phase_block` / `phase_allow` fields
4. **COORDINATOR.md split** — phase files + `phases.yaml` manifest that enable phase discovery
5. **Setup check hints** — 3-4 outcome-based checks via `CheckFailed` adapter into hints pipeline (no separate `/check-setup` command)
6. **First Pytest tutorial** — proof-of-concept tutorial consuming the primitives

### What v1 does NOT deliver

- Tutorial UI / presentation layer
- CompoundCheck (composite assertions)
- Phase-aware content lock enforcement (Level 1+)
- Tutorial catalog / discovery
- Multi-workflow orchestration

### 1.1 User Journey (First Pytest tutorial)

What the user actually types and sees:

```
$ claude
> /tutorial first-pytest

  Tutorial: Write Your First Pytest Test
  Phase 1 of 2: Write a test

  Create a file tests/test_example.py with a test function.
  The function name must start with test_.

  When you're done, I'll check that the file exists and advance.

> [user writes test file with Claude's help]

  ✓ tests/test_example.py exists
  Advancing to Phase 2...

  Phase 2 of 2: Run the test

  Run: pixi run pytest tests/test_example.py
  The test must pass.

> pixi run pytest tests/test_example.py
  1 passed

  ✓ pytest output contains "passed"
  Tutorial complete!
```

---

## 2. Two Primitives

The entire architecture reduces to two primitives: **Check** and **Phase**.

### 2.1 Check

A pure assertion: inspect system state, return a verdict with evidence.

**The engine runs checks, not the Coordinator.** This is the same principle as guardrails: system-level enforcement of agent behavior. Just as guardrails prevent agents from running forbidden commands, checks prevent the Coordinator from skipping phases. The Coordinator cannot bypass a `ManualConfirm` gate — the engine asks the user directly. Checks are to the Coordinator what guardrails are to agents.

```python
@dataclass(frozen=True)
class CheckResult:
    """Outcome of a single check."""
    passed: bool
    message: str
    evidence: str = ""       # stdout, file content, etc.


class Check(Protocol):
    """Protocol: any object with check(ctx) → CheckResult."""
    def check(self, ctx: "CheckContext") -> CheckResult: ...


@dataclass(frozen=True)
class CheckContext:
    """Common inputs for checks: project root and system access helpers."""
    project_root: Path

    def run_command(self, cmd: str, timeout: float = 30.0) -> "CommandResult": ...
    def read_file(self, path: str | Path) -> str: ...
    def file_exists(self, path: str | Path) -> bool: ...
```

**Four built-in checks (v1):**

| Type | Constructor | Passes when | Enforcement role |
|---|---|---|---|
| `CommandOutputCheck` | `(command, pattern)` | Command stdout matches regex `pattern` | Prove system state (tests pass, tool installed) |
| `FileExistsCheck` | `(path)` | File exists at `path` | Prove work was done (artifact created) |
| `FileContentCheck` | `(path, pattern)` | File content matches regex `pattern` | Prove content is correct (STATUS.md has spawn evidence) |
| `ManualConfirm` | `(question)` | User answers affirmatively | Prove the user actually approved (engine asks, not agent) |

`ManualConfirm` calls `input()` directly — the engine presents the question to the user, not the Coordinator. This is engine-level enforcement: the Coordinator cannot fabricate user approval.

`FileContentCheck` reads a file and matches against a regex pattern. This enables checking artifacts like STATUS.md for required content (e.g., all Leadership agents spawned) without requiring the Coordinator to self-report honestly.

```python
class FileContentCheck:
    """Passes when file content matches a regex pattern."""
    def __init__(self, path: str | Path, pattern: str) -> None:
        self.path = path
        self.pattern = pattern

    def check(self, ctx: CheckContext) -> CheckResult:
        content = ctx.read_file(self.path)
        match = re.search(self.pattern, content)
        return CheckResult(
            passed=match is not None,
            message=f"File '{self.path}' {'matches' if match else 'does not match'} pattern",
            evidence=match.group(0) if match else content[:200],
        )
```

**Check type registry:** Checks are declared by type name in manifest files (e.g., `type: file-exists-check` in `phases.yaml` or `tutorial.yaml`). The registry maps type names to Python classes:

```python
CHECK_REGISTRY: dict[str, type[Check]] = {
    "command-output-check": CommandOutputCheck,
    "file-exists-check": FileExistsCheck,
    "file-content-check": FileContentCheck,
    "manual-confirm": ManualConfirm,
}
```

**Standalone usage (no Phase required):**

Checks are independent of Phase. They can be used anywhere — diagnostics, CI, health checks — without a workflow. See Section 2.3 for how standalone checks compose with the existing hints system.

`CheckContext` follows the same pattern as the existing hints system: `TriggerCondition.check()` receives `ProjectState` (a read-only context bag), `Check.check()` receives `CheckContext` (a read-only context bag). Both are parameter objects providing dependency injection for testing.

### 2.3 Checks as Hint Triggers (standalone check discovery)

**Design decision:** Standalone checks compose into the existing hints pipeline via a `CheckFailed` adapter — no new discovery or delivery mechanism needed.

#### Why this pattern

The hints system already solves the "WHO calls and WHEN" problem:
- **Discovery:** `hints.py` registers all `HintSpec` objects
- **Evaluation:** `run_pipeline()` evaluates triggers at startup and periodically
- **Delivery:** Toast notifications with lifecycle management
- **Error handling:** IRON RULE — pipeline never crashes, try-except everything

A Check is a condition about system state. A failing check = a hint that tells the user what to fix. The adapter bridges the two protocols:

```python
@dataclass(frozen=True)
class CheckFailed:
    """TriggerCondition adapter: fires when a Check fails.

    Bridges Check protocol (CheckContext → CheckResult) to
    TriggerCondition protocol (ProjectState → bool).
    """
    check_obj: Check
    timeout: float = 5.0  # Shorter than Check default — startup must be fast

    def check(self, state: ProjectState) -> bool:
        ctx = CheckContext(project_root=state.root)
        result = self.check_obj.check(ctx)
        return not result.passed  # Trigger fires when check FAILS

    @property
    def description(self) -> str:
        return f"CheckFailed({self.check_obj})"
```

#### v1 setup checks as hints

Each check tests an OUTCOME (can you authenticate? can you import?), not an implementation detail (does this file exist?). See `specification/check_inventory.md` for the full analysis and rejected alternatives.

```python
# In hints/hints.py — setup checks composed as hint triggers

# Check 1: GitHub authentication works (tokens expire, keys get revoked,
# scientists move between machines — installer only checks at install time)
HintSpec(
    id="setup-github-auth",
    trigger=CheckFailed(CommandOutputCheck(
        "git ls-remote https://github.com/sprustonlab/claudechic.git HEAD 2>&1 | head -1",
        r"[0-9a-f]{40}",
    )),
    message="GitHub authentication failed. Run: gh auth login",
    severity="warning",
    priority=1,
    lifecycle=ShowUntilResolved(),
)

# Check 2: Git identity configured (not checked anywhere in the template —
# scientists on shared HPC nodes commit as root@login-node.cluster.edu)
HintSpec(
    id="setup-git-identity",
    trigger=CheckFailed(CommandOutputCheck("git config user.email", r".+@.+")),
    message="Git email not configured. Run: git config --global user.email 'you@example.com'",
    severity="warning",
    priority=1,
    lifecycle=ShowUntilResolved(),
)

# Check 3: Pixi environment is healthy (activate checks pixi install ran,
# but doesn't verify the result works — broken after pixi update or NFS
# cache staleness on clusters)
HintSpec(
    id="setup-pixi-env",
    trigger=CheckFailed(CommandOutputCheck(
        'pixi run python -c "import yaml; print(\'ok\')" 2>&1',
        r"ok",
    )),
    message="Pixi environment is broken. Try: pixi install --force",
    severity="warning",
    priority=1,
    lifecycle=ShowUntilResolved(),
)

# Check 4: Cluster SSH works (conditional — only when use_cluster=true.
# Without this, cluster MCP tools hang on SSH password prompt, appearing
# as a frozen TUI. This is the single worst UX failure in the template.)
HintSpec(
    id="setup-cluster-ssh",
    trigger=AllOf((
        CheckFailed(CommandOutputCheck(
            "ssh -o ConnectTimeout=5 -o BatchMode=yes "
            f"{copier.cluster_ssh_target} hostname 2>&1",
            r"^[a-zA-Z]",
        )),
        # Only evaluate if cluster is configured
        lambda state: state.copier.use_cluster,
    )),
    message=lambda state: (
        f"Cannot SSH to cluster ({state.copier.cluster_ssh_target}). "
        f"Run: ssh-copy-id {state.copier.cluster_ssh_target}"
    ),
    severity="warning",
    priority=2,
    lifecycle=ShowUntilResolved(),
)
```

These fire automatically at session startup via the existing hints pipeline. No new slash command, no new discovery mechanism. `ShowUntilResolved` re-checks each session until the scientist fixes the issue.

**`/check-setup` cut from v1.** The CheckFailed → hints path IS the discovery mechanism. For an explicit diagnostic, `/hints` shows all active warnings. A parallel reporting tool for 3-4 checks is dead weight.

#### Composability analysis

| Option | New infrastructure | Composes with existing | Discovery mechanism |
|---|---|---|---|
| 1. Checks as hints | ~0 lines | Yes — IS the hints pipeline | Hints registry |
| 2. Standalone inventory | ~90 lines | No — parallel system | New registry |
| 3. Phase gates only | 0 lines | No standalone use | None |
| **4. CheckFailed adapter** | **~15 lines** | **Yes — bridges Check → TriggerCondition** | **Hints registry** |

Option 4 wins because:
- **Zero new infrastructure** for discovery (reuses hints pipeline)
- **~15 lines** for the adapter (smallest new code)
- **Check remains independent** — doesn't know about hints (clean seam)
- **Existing lifecycle policies apply** — `ShowUntilResolved` re-checks until fixed
- **Existing combinators apply** — `AllOf(CheckFailed(A), condition)` composes naturally
- **v2 payoff:** tutorial prerequisites, `/check-health` dashboard, user-defined checks — same objects, more consumers

### 2.2 Phase

A named state in a workflow that determines what is allowed, what must be proven, and what guidance is relevant.

#### Phase files are pure markdown

Phase files contain only agent instructions — no YAML frontmatter, no configuration. They are pure content.

```markdown
## Phase 4: Implementation

1. Spawn one Implementer agent per file, up to 6 implementer agents.
2. Inform Leadership about how many implementation agents have been started.
3. If Researcher is active, ask Researcher to find reference implementations.
4. Exit when all Leadership approve.
```

#### Phase configuration lives in manifest files

Each workflow has a manifest that defines phase IDs, ordering, and gate checks:

**Project-team workflow (`phases.yaml`):**

```yaml
# AI_agents/project_team/phases.yaml
workflow_id: project-team
phases:
  - id: vision
    file: phases/phase-00-vision.md
  - id: setup
    file: phases/phase-01-setup.md
  - id: spawn-leadership
    file: phases/phase-02-spawn-leadership.md
  - id: specification
    file: phases/phase-03-specification.md
  - id: implementation
    file: phases/phase-04-implementation.md
    advance_checks:
      - type: manual-confirm
        question: "Are all implementation tasks complete and Leadership-approved?"
  - id: testing
    file: phases/phase-05-testing.md
    advance_checks:
      - type: command-output-check
        command: "pixi run pytest --tb=short 2>&1 | tail -1"
        pattern: "passed"
  - id: signoff
    file: phases/phase-06-signoff.md
```

**Tutorial workflow (`tutorial.yaml`):**

```yaml
# tutorials/first-pytest/tutorial.yaml
workflow_id: first-pytest-tutorial
phases:
  - id: write-test
    file: phase-01-write-test.md
    advance_checks:
      - type: file-exists-check
        path: "tests/test_example.py"
    hints:
      - message: "Create tests/test_example.py with a function starting with test_"
        trigger: { type: phase-stuck, threshold_seconds: 120 }
  - id: run-test
    file: phase-02-run-test.md
    advance_checks:
      - type: command-output-check
        command: "pixi run pytest tests/test_example.py"
        pattern: "passed"
    hints:
      - message: "Run: pixi run pytest tests/test_example.py"
        trigger: { type: phase-check-failed }
```

**Where each concern lives:**

| Concern | Home | Why |
|---|---|---|
| Agent instructions | Phase markdown file | Per-phase content, read by agent |
| Phase IDs and ordering | `phases.yaml` / `tutorial.yaml` | Per-workflow structure |
| Gate checks (advance_checks) | `phases.yaml` / `tutorial.yaml` | Per-phase, defined alongside phase ID |
| Tutorial hints | `tutorial.yaml` | Per-phase, tutorial-specific |
| Project-team hints | `hints/hints.py` with `PhaseIs()` trigger | Follow existing hints pattern |
| Rule scoping | `rules.yaml` (`phase_block`/`phase_allow`) | Per-rule, defined alongside rule |

#### Type definitions

```python
@dataclass(frozen=True)
class CheckDeclaration:
    """A check as declared in a manifest file (phases.yaml / tutorial.yaml).

    Parsed from YAML. The engine resolves `type` via CHECK_REGISTRY to get
    the Check class, then passes remaining fields as constructor kwargs.
    """
    type: str                          # Registry key: "file-exists-check", etc.
    params: dict[str, Any] = field(default_factory=dict)
    # params holds type-specific fields: path, command, pattern, question, etc.
    # Example YAML: {type: file-exists-check, path: "tests/test_example.py"}
    #   → CheckDeclaration(type="file-exists-check", params={"path": "tests/test_example.py"})


@dataclass(frozen=True)
class HintDeclaration:
    """A hint as declared in tutorial.yaml.

    Parsed from YAML. The tutorial engine converts these to HintSpec objects
    at phase entry time.
    """
    message: str
    trigger: dict[str, Any]            # {type: "phase-stuck", threshold_seconds: 120}
    lifecycle: str = "show-once"       # "show-once" (v1 only; "show-until-phase-complete" is v2)


@dataclass(frozen=True)
class PhaseMeta:
    """Parsed from phases.yaml or tutorial.yaml manifest.

    The engine reads this. The agent never sees it.
    """
    id: str
    file: str                                      # Relative path to markdown file
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
    phase_entered_at: float          # Unix timestamp
```

#### Phase IDs

Phase IDs are strings defined in the manifest. Within a manifest, IDs are bare slugs (`"testing"`, `"write-test"`). The `workflow_id` field in the manifest distinguishes workflows.

| Workflow | Example phase IDs |
|---|---|
| `project-team` | `"specification"`, `"implementation"`, `"testing"` |
| `first-pytest-tutorial` | `"write-test"`, `"run-test"` |

**Qualified phase IDs in `phase_block` / `phase_allow`:** Because rules in `rules.yaml` scope across all workflows, phase references in rules use qualified IDs: `"workflow_id:phase_id"`. This prevents namespace collisions (e.g., two workflows both having a `"testing"` phase).

```yaml
# rules.yaml — qualified IDs prevent ambiguity
- id: R01
  phase_block: ["project-team:testing", "first-pytest-tutorial:run-test"]
```

The runtime matches `f"{workflow_id}:{phase_id}"` from `phase_state.json` against the qualified IDs in the rule. The validator in `generate_hooks.py` checks qualified IDs against `{workflow_id}:{phase_id}` pairs from all manifests.

#### Two facets of a phase (in the manifest)

```
Phase entry in manifest
├── Gates:   advance_checks (list of Checks)
│   → What must be proven before the engine advances to the next phase
│
└── Context: hints (list of HintDeclarations)
    → What guidance is relevant during this phase (tutorials)
```

Rule scoping (guards) is a third facet of the *system*, but it lives in `rules.yaml` via `phase_block`/`phase_allow` — not in the manifest. Single source of truth for rules.

---

## 3. Phase Coherence

### 3.1 The single source of truth: `phase_state.json`

```json
{
  "workflow_id": "project-team",
  "phase_id": "implementation",
  "phase_entered_at": 1712160000.0,
  "current_phase_file": "AI_agents/project_team/phases/phase-04-implementation.md"
}
```

`current_phase_file` is the relative path to the current phase's markdown file (from the manifest). This enables any consumer — guardrails, hints, `/compact` recovery — to find the phase content without parsing the manifest.

Completed phases are not persisted. They are derivable from `phase_id` + manifest ordering (all phases before the current one are complete). This avoids redundant state.

- **Location:** Default: `<project_root>/.ao_project_team/phase_state.json`. Override: `PHASE_STATE_PATH` environment variable (for testing).
- **Written by:** WorkflowEngine at phase transitions
- **Read by:** Guardrail hooks (`phase_guard.py`), hints pipeline, `/compact` recovery hook, agent prompt assembly
- **Discovery:** `PHASE_STATE_PATH` env var if set, otherwise default path

This file is distinct from session markers (`.claude/guardrails/*.session_marker`), which are ephemeral and PID-scoped. `phase_state.json` persists across sessions.

### 3.2 Phase transition

```
Phase A (current) → Phase B (next)

1. ENGINE runs Phase A's advance_checks → all must pass (gate)
   - The Coordinator requests advance; the ENGINE evaluates checks
   - ManualConfirm: ENGINE asks the user directly (Coordinator cannot fabricate approval)
   - CommandOutputCheck: ENGINE runs the command (Coordinator cannot fake output)
   - FileContentCheck: ENGINE reads the file (Coordinator cannot skip the read)
2. Unregister Phase A's hints
3. Register Phase B's hints
4. Update ActivePhase (new phase_id, reset phase_entered_at)
5. Persist to phase_state.json
6. Deliver Phase B's markdown file to agent prompt
```

Steps 2-5 happen atomically from the engine's perspective. Rule scoping updates automatically: `phase_guard.py` reads the new `phase_id` from `phase_state.json` and evaluates `phase_block`/`phase_allow` from `rules.yaml` at runtime. No explicit rule swap step needed.

### 3.2.1 WorkflowEngine interface

There is one engine. Tutorials and project-team workflows are both "a manifest + markdown files" — the engine doesn't distinguish them.

```python
class WorkflowEngine:
    """Drives phase transitions for any workflow (project-team or tutorial).

    Instantiated once per workflow session. Reads the manifest, manages
    phase state, evaluates gates, and provides the current phase file path.
    """

    def __init__(self, manifest_path: Path, project_root: Path) -> None:
        """Load manifest, parse PhaseMeta entries, read or create phase_state.json."""
        ...

    @property
    def current_phase(self) -> PhaseMeta:
        """The current phase entry from the manifest."""
        ...

    @property
    def current_phase_file(self) -> Path:
        """Absolute path to the current phase's markdown file.

        This is the primary content-delivery mechanism: the caller (agent
        prompt assembler or slash command) reads this file and includes it
        in the agent's context.
        """
        ...

    def try_advance(self, ctx: CheckContext) -> AdvanceResult:
        """Attempt to advance to the next phase.

        1. Run current phase's advance_checks via CheckContext
        2. If all pass → transition (update state, persist, return success)
        3. If any fail → return failure with CheckResults
        4. If already on last phase → return workflow-complete

        Called by the agent (agent-initiated advance for v1).
        """
        ...

    def get_phase_instructions(self) -> str:
        """Read and return the current phase markdown file content.

        This is what gets included in the agent prompt.
        """
        ...


@dataclass(frozen=True)
class AdvanceResult:
    """Outcome of a try_advance() call."""
    advanced: bool
    workflow_complete: bool = False
    failed_checks: tuple[CheckResult, ...] = ()
    new_phase_id: str = ""
```

**Content delivery to the agent:** The engine does NOT inject content into a running agent mid-session. Instead:

- **Project-team:** COORDINATOR.md gains 3 lines of cross-phase instruction: "Read `.ao_project_team/phase_state.json`. Load the file at `current_phase_file`. Follow those instructions." The Coordinator reads the phase file at session start and after each advance.
- **Tutorials:** A `/tutorial` slash command (`.claude/commands/tutorial.md`) instantiates the engine, reads the current phase file, and prints it. The agent follows the instructions and calls `/tutorial advance` to attempt progression.
- **Phase file delivery is pull-based (agent reads), not push-based (engine injects).** This matches how agents already read role files — no new delivery mechanism needed.

**`/compact` recovery:** After `/compact` clears context, the agent loses phase awareness. The existing `post_compact_injector.py` hook trigger in `generate_hooks.py` (currently zero consumers) fires after compaction. A new rule (~30 lines) reads `phase_state.json` and re-injects: "You are in phase `{phase_id}`. Read `{current_phase_file}` for your current instructions." Zero new infrastructure — uses an existing hook trigger.

### 3.3 Phase-scoped guardrails

Existing `rules.yaml` rules gain `phase_block` / `phase_allow` fields, plus a top-level `workflows` section that declares manifest files for phase validation:

```yaml
# Top of rules.yaml — declares manifests for phase validation
workflows:
  - AI_agents/project_team/phases.yaml
  - tutorials/first-pytest/tutorial.yaml

rules:
  - id: R01
    name: pytest-output-block
    trigger: PreToolUse/Bash
    enforcement: deny
    phase_block: ["project-team:testing"]   # Don't fire during project-team testing phase
    detect:
      type: regex_match
      pattern: '(?:^|&&|\|\||;|\brun\s+)\s*pytest\b'
    message: "..."
```

#### Phase registration and validation

The manifests (`phases.yaml` / `tutorial.yaml`) are the phase registry.

- `rules.yaml` `workflows` section lists manifest files to read
- `generate_hooks.py` parses each manifest, extracts phase IDs, builds the registry
- Every `phase_block`/`phase_allow` reference is validated against discovered phase IDs
- Default: warnings (development-friendly). `--strict` flag: hard errors (for CI)
- `KNOWN_PHASES` set is baked into generated hooks for runtime defensive warnings

**R01 is the v1 proof-of-concept:** Adding `phase_block: ["project-team:testing"]` exempts it during the project-team testing phase. Same convention as `block: [Subagent]` for role scoping — same YAML level, same mental model. Qualified IDs prevent namespace collisions across workflows.

#### Guardrail enforcement levels

Existing enforcement levels: `deny` (blocked, no bypass), `warn` (agent acknowledges and proceeds), `log` (silent record).

v1 adds **`user_confirm`**: the hook blocks the action and prompts the **user** directly. The agent cannot fabricate approval. If the user approves, the action proceeds; if not, it is denied. This sits between `warn` (agent decides) and `deny` (no bypass) — the user decides.

| Level | Who decides | Agent can bypass? |
|---|---|---|
| `deny` | System | No |
| `user_confirm` | User | No — hook prompts user directly |
| `warn` | Agent | Yes — agent acknowledges |
| `log` | Nobody | N/A — silent |

**Concrete use case:** Prevent closing agents during specification phase without user approval:

```yaml
- id: R06
  name: close-agent-during-spec
  trigger: PreToolUse/mcp__chic__close_agent
  enforcement: user_confirm
  phase_allow: ["project-team:specification"]
  message: "[GUARDRAIL USER_CONFIRM R06] Close agent during specification phase — user approval required."
```

**Implementation:** `generate_hooks.py` emits a `user_confirm` handler that calls `input()` (or equivalent UI prompt) before allowing the tool call. Same pattern as `ManualConfirm` in the check system — system-level, not agent-level.

**Runtime evaluation (`phase_guard.py`):**

```python
def should_skip_rule(rule_id: str, phase_block: list[str], phase_allow: list[str]) -> bool:
    """Check if a rule should be skipped for the current phase.

    phase_block/phase_allow come from rules.yaml (baked into generated hooks).
    They use qualified IDs: "workflow_id:phase_id".
    Current workflow_id + phase_id come from phase_state.json (read at runtime).
    """
    phase_file = Path(os.environ.get("PHASE_STATE_PATH", ""))
    if not phase_file.exists():
        return False  # No active phase → rule fires normally

    try:
        state = json.loads(phase_file.read_text())
    except (json.JSONDecodeError, OSError):
        return False  # Corrupt → fail-open, rule fires

    workflow_id = state.get("workflow_id", "")
    phase_id = state.get("phase_id", "")
    if not workflow_id or not phase_id:
        return False

    qualified = f"{workflow_id}:{phase_id}"

    # phase_block: rule does NOT fire during these phases
    if phase_block and qualified in phase_block:
        return True

    # phase_allow: rule ONLY fires during these phases
    if phase_allow and qualified not in phase_allow:
        return True

    return False
```

### 3.4 Phase-scoped hints

**For tutorials:** Hints are declared in `tutorial.yaml` alongside phase definitions (see section 2.2).

**For project-team phases:** Hints are defined in `hints/hints.py` using a `PhaseIs()` trigger, following the existing Python-based hint pattern:

```python
@dataclass(frozen=True)
class PhaseIs:
    """Fires when a specific phase is active."""
    workflow_id: str
    phase_id: str

    def check(self, state: ProjectState) -> bool:
        if state.active_phase is None:
            return False
        return (
            state.active_phase.workflow_id == self.workflow_id
            and state.active_phase.phase_id == self.phase_id
        )
```

```python
# In hints/hints.py — project-team phase hints
HintSpec(
    id="implementation-test-stubs",
    trigger=PhaseIs("project-team", "implementation"),
    message="Focus on writing code, not running the full test suite",
    priority=3,
    lifecycle=ShowOnce(),
)
```

`ProjectState` gains one field:

```python
@dataclass(frozen=True)
class ProjectState:
    root: Path
    copier: CopierAnswers
    session_count: int | None = None
    active_phase: ActivePhase | None = None  # NEW — None when no workflow active
```

### 3.5 Compositional law

1. All checks produce `CheckResult` — checks are independent of Phase and Hints
2. The engine runs checks, not the agent — this is system-level enforcement (same principle as guardrails)
3. All phase consumers read `phase_state.json` — this is the coherence mechanism
4. Agent prompt is scoped to the current phase file — this is optimization, not enforcement
5. `CheckFailed` adapter bridges Check → TriggerCondition — checks compose into hints without either protocol knowing about the other

---

## 4. Content Focus

Content scoping is **attention management (~80% effective)**, not security enforcement.

**Load-bearing (hard enforcement, system-level):**

```
phase_state.json
├── Guardrail lock: rules scoped to current phase
│   → Agent can't DO wrong-phase actions
├── Gate lock: advance_checks must pass
│   → Agent can't ADVANCE without proof
└── Hint lock: hints scoped to current phase
    → Agent gets right-phase guidance
```

**Optimization (soft, prompt-level):**

```
Content scoping: agent only receives current phase instructions
→ Agent is less likely to ATTEMPT wrong-phase actions
→ Reduces guardrail friction (fewer denied actions)
→ Better agent focus and output quality
```

### Enforcement levels

| Level | Mechanism | Effectiveness | v1/v2 |
|---|---|---|---|
| **0: Prompt-only** | Agent receives only current phase file | ~70% | **v1** |
| **1: Prompt + warn guardrail** | Advisory guardrail on reading other phase files | ~80% | v2 |
| **2: Prompt + deny guardrail** | Hard guardrail blocking other phase file reads | ~85% | v2+ |
| **3: On-demand generation** | Phase files don't exist until transition | ~90% | Future |

v1 implements Level 0. The engine serves only the current phase file. The engine's file selection IS the content focus mechanism. Level 1+ requires phase-aware hooks (v2).

---

## 5. Integration with Existing Infrastructure

### 5.1 What already exists (unchanged)

| System | Key Components | Impact |
|---|---|---|
| **Hints** | `TriggerCondition`, `HintLifecycle`, `HintSpec`, `HintRecord`, `HintStateStore`, `run_pipeline()` | Extended with `PhaseIs` trigger and `ActivePhase` on `ProjectState` |
| **Guardrails** | `rules.yaml` (R01-R05), `generate_hooks.py`, `role_guard.py`, `bash_guard.py` | R01 gains `phase_block`; `generate_hooks.py` emits `phase_guard` calls |
| **Agent system** | Role files, `spawn_agent()`, `tell_agent`/`ask_agent` | COORDINATOR.md splits: ~30 lines cross-phase + N phase files. Directory stays `AI_agents/`. |
| **Project state** | `ProjectState`, `CopierAnswers`, path utilities | Gains `active_phase: ActivePhase | None` field |

### 5.2 Seams

| Seam | Contract | Direction |
|---|---|---|
| Phase → Guardrails | `phase_state.json` | Phase writes; guardrail hooks read |
| Phase → Hints | `ActivePhase` on `ProjectState` | Phase updates state; hint triggers check it |
| Phase → Agent | `engine.current_phase_file` / `engine.get_phase_instructions()` | Pull-based: agent reads from engine; engine does not inject mid-session |
| Check → Phase | `CheckResult` | Checks return results; Phase gates consume them |
| Check → Hints | `CheckFailed` adapter | Bridges `Check` → `TriggerCondition`; failing checks fire as hints at startup |

### 5.3 COORDINATOR.md split (v1 — required for phase discovery)

Phase-scoped guardrails need a `phases.yaml` manifest so `generate_hooks.py` can discover phase IDs and validate `phase_block`/`phase_allow` references.

```
Before:
  AI_agents/project_team/
    COORDINATOR.md (275 lines, all phases)

After:
  AI_agents/project_team/
    COORDINATOR.md (30 lines — Prime Directive + Key Terms only)
    phases.yaml (phase IDs, ordering, gate checks)
    phases/
      phase-00-vision.md
      phase-01-setup.md
      phase-02-spawn-leadership.md
      phase-03-specification.md
      phase-04-implementation.md
      phase-05-testing.md
      phase-06-signoff.md
```

Agent prompt = `COORDINATOR.md` (who you are) + current phase markdown (what to do now).

**Splitting rule:** If removing a section from COORDINATOR.md would make any phase file unable to stand alone, that section is cross-phase and stays in COORDINATOR.md.

**Directory rename deferred to v2:** `AI_agents` → `teams` is cosmetic with a large blast radius. v1 keeps the existing `AI_agents/` directory name.

---

## 6. File Structure

```
template/
  checks/                          # Primitive 1: Check system
    __init__.py                    # Re-exports
    _types.py                      # Check protocol, CheckContext, CheckResult (~40 lines)
    _builtins.py                   # 3 built-in checks + CHECK_REGISTRY dict (~90 lines)

  workflow/                        # Primitive 2: Phase system
    __init__.py                    # Re-exports
    _types.py                      # PhaseMeta, ActivePhase, CheckDeclaration, HintDeclaration,
                                   #   AdvanceResult (~50 lines)
    _engine.py                     # WorkflowEngine: manifest parsing, transitions, gate
                                   #   evaluation, phase_state.json persistence (~150 lines)

  hints/                           # Existing (extended)
    _types.py                      # TriggerCondition, HintLifecycle, HintSpec (unchanged)
    _state.py                      # ProjectState gains active_phase field
    _engine.py                     # run_pipeline() (unchanged)
    hints.py                       # Existing hints + PhaseIs trigger + CheckFailed adapter
                                   #   + setup check hints + project-team phase hints

  .claude/guardrails/              # Existing (extended)
    rules.yaml                     # R01 gains phase_block; workflows section lists manifests
    phase_guard.py                 # NEW: runtime phase scope evaluation (~40 lines)
    generate_hooks.py              # Extended: phase registry + validation (~150 lines changed)

  AI_agents/project_team/          # Existing directory (no rename in v1)
    COORDINATOR.md                 # Stripped to cross-phase content (~30 lines)
    phases.yaml                    # Phase IDs, ordering, gate checks
    phases/                        # Pure markdown phase files (no frontmatter)
      phase-00-vision.md
      phase-01-setup.md
      ...

  tutorials/first-pytest/          # First tutorial (v1 proof-of-concept)
    tutorial.yaml                  # Phase IDs, ordering, checks, hints
    phase-01-write-test.md         # Pure markdown
    phase-02-run-test.md           # Pure markdown
```

**What was cut from file structure:**
- `checks/_registry.py` → merged into `_builtins.py` (5-line dict doesn't need its own file)
- `workflow/_state.py` → merged into `_engine.py` (state persistence is engine implementation detail)
- `workflow/_triggers.py` → `PhaseIs` lives in `hints/hints.py` (it's a `TriggerCondition`); `PhaseStuck`/`PhaseCheckFailed` are tutorial-engine-internal
- `workflow/_lifecycle.py` → `ShowUntilPhaseComplete` is v2 scope

---

## 7. Concrete Examples

### 7.1 Project-team: implementation → testing transition

**`phases.yaml` (relevant entries):**

```yaml
- id: implementation
  file: phases/phase-04-implementation.md
  advance_checks:
    - type: manual-confirm
      question: "Are all implementation tasks complete?"
- id: testing
  file: phases/phase-05-testing.md
  advance_checks:
    - type: command-output-check
      command: "pixi run pytest --tb=short 2>&1 | tail -1"
      pattern: "passed"
```

**`rules.yaml` (rule scoping with qualified IDs):**

```yaml
- id: R01
  phase_block: ["project-team:testing"]                     # R01 doesn't fire during testing
- id: R-BLOCK-NEW-FEATURES
  phase_allow: ["project-team:testing", "project-team:signoff"]  # Only fires during testing/signoff
```

**`hints/hints.py` (project-team phase hints):**

```python
HintSpec(
    id="implementation-focus",
    trigger=PhaseIs("project-team", "implementation"),
    message="Focus on writing code, not running the full test suite",
    priority=3,
    lifecycle=ShowOnce(),
)
```

On transition from Phase 4 → Phase 5:
1. ManualConfirm gate passes (user approves)
2. Phase 4 hints unregistered, Phase 5 hints registered
3. `phase_state.json` updated: `phase_id: "testing"`
4. Agent receives `phase-05-testing.md` markdown
5. Rule scoping updates automatically — `phase_guard.py` reads new `phase_id`, R01 now skipped

### 7.2 Setup checks via hints pipeline

Setup checks fire automatically at session startup — no explicit command needed:

```python
# GitHub auth broke since install (token expired, key revoked, new machine)
HintSpec(
    id="setup-github-auth",
    trigger=CheckFailed(CommandOutputCheck(
        "git ls-remote https://github.com/sprustonlab/claudechic.git HEAD 2>&1 | head -1",
        r"[0-9a-f]{40}",
    )),
    message="GitHub authentication failed. Run: gh auth login",
    severity="warning",
    priority=1,
    lifecycle=ShowUntilResolved(),  # Re-checks each session until fixed
)
```

Scientist starts a session → hints pipeline evaluates `CheckFailed` → `CommandOutputCheck` runs `git ls-remote` → if it returns a commit hash, check passes, hint doesn't fire → if auth fails, `ShowUntilResolved` shows warning toast every session until they fix it.

### 7.3 First Pytest tutorial (v1 proof-of-concept)

**`tutorials/first-pytest/tutorial.yaml`:**

```yaml
workflow_id: first-pytest-tutorial
phases:
  - id: write-test
    file: phase-01-write-test.md
    advance_checks:
      - type: file-exists-check
        path: "tests/test_example.py"
    hints:
      - message: "Create tests/test_example.py with a function starting with test_"
        trigger: { type: phase-stuck, threshold_seconds: 120 }
  - id: run-test
    file: phase-02-run-test.md
    advance_checks:
      - type: command-output-check
        command: "pixi run pytest tests/test_example.py"
        pattern: "passed"
    hints:
      - message: "Run: pixi run pytest tests/test_example.py"
        trigger: { type: phase-check-failed }
```

R01 (pytest block) is suspended during the `run-test` phase via `rules.yaml`:

```yaml
- id: R01
  phase_block: ["project-team:testing", "first-pytest-tutorial:run-test"]
```

---

## 8. V1 Scope

### 8.1 Implementation size

| Category | Lines | What's in it |
|---|---|---|
| **New infrastructure code** | ~435 | `checks/` (~150 — 4 built-in types incl. FileContentCheck), `workflow/` (~200 incl. engine), `phase_guard.py` (~40), `generate_hooks.py` changes (~150 changed, not new), `CheckFailed` adapter + setup HintSpecs (~45), `/compact` recovery rule (~30) |
| **Moved/restructured content** | ~275 | COORDINATOR.md split (275 lines reorganized into ~30 cross-phase + 7 phase files + `phases.yaml`) |
| **Tutorial content (markdown + YAML)** | ~175 | First Pytest tutorial files (~125) + tutorial-runner role file (~50) |
| **Tests** | ~300 | Check primitive (~120 — 4 types), WorkflowEngine + phase state (~80), guardrails (~80), CheckFailed adapter (~20) |
| **Total** | **~1,185** | |

**Realism note:** Line counts are estimates with ±25% uncertainty. The `generate_hooks.py` integration (step 1) is the highest-variance item — if the existing hook infrastructure resists `phase_block` cleanly, this number could grow. The spike-first implementation order (Section 8.3) catches this early.

### 8.2 Risk assessment

| Risk | Probability | Severity | Mitigation |
|---|---|---|---|
| `generate_hooks.py` regression | HIGH | MEDIUM | Run full test framework after each change |
| Phase ID typo in `phase_block`/`phase_allow` | HIGH | LOW | Caught at generation time by validation |
| Tutorial YAML validation gap | MEDIUM | LOW | Validate manifest at load time |
| Phase state file not found | MEDIUM | LOW | try/except + default to "no phase" (fail-open) |
| Unknown phase_id at runtime | LOW | LOW | Defensive warning in `phase_guard.py`, non-blocking |
| Agent doesn't follow tutorial engine | LOW | MEDIUM | Precise agent role file + checkpoint guardrail |

### 8.3 Implementation order

1. **`generate_hooks.py` spike + R01 `phase_block`** — GO/NO-GO GATE. Riskiest integration point (~2 days). Add `phase_block` field to R01 in `rules.yaml`, extend `generate_hooks.py` to read a stub `phases.yaml`, validate qualified phase references, emit `phase_guard` calls in generated hooks. If this doesn't work cleanly, everything else needs rethinking. Uses a hardcoded stub manifest (no COORDINATOR.md split yet).
2. **Check primitive + `CheckFailed` adapter + setup hints** — Check protocol + 3 built-in types, `CheckFailed` adapter (~15 lines), 3-4 setup HintSpecs in `hints/hints.py`
3. **COORDINATOR.md split + `phases.yaml`** — creates real phase files and manifest. No directory rename (deferred to v2). Replace stub manifest from step 1.
4. **WorkflowEngine + phase state + `phase_guard.py`** — engine reads manifests, manages transitions, persists `phase_state.json`. `phase_guard.py` enables runtime phase-scoped guardrails. Includes `/compact` recovery rule (~30 lines).
5. **First Pytest tutorial content** — consumes WorkflowEngine (same engine, different manifest)

---

## 9. V2 Scope (Future)

| Feature | Description |
|---|---|
| CompoundCheck | Composite assertions (AND/OR over multiple checks) |
| Content focus Level 1 | Warn guardrail on non-current phase file reads (requires phase-aware hooks) |
| Content focus Level 2 | Hard guardrail blocking reads of non-current phase files |
| Tutorial catalog | Discovery and listing of available tutorials |
| Multi-workflow | Multiple workflows active simultaneously |
| `ShowUntilPhaseComplete` lifecycle | Phase-aware hint lifecycle that auto-dismisses on phase transition |
| Tutorial UI | Presentation layer for tutorial progress |
| Agent-team tutorials | Tutorials that teach multi-agent workflows (e.g., "Run your first project-team build") |
| Directory rename | `AI_agents/` → `teams/` throughout codebase (cosmetic, large blast radius) |

---

## 10. Open Decisions

### 10.1 Resolved

| Decision | Resolution |
|---|---|
| How many primitives? | Two: Check + Phase |
| Phase file = content + config or pure content? | Pure markdown. Config lives in manifest (`phases.yaml` / `tutorial.yaml`). |
| Content focus = security or optimization? | Optimization (~80% effective attention management) |
| Content focus level for v1? | Level 0 (prompt-only; Level 1+ requires phase-aware hooks, deferred to v2) |
| Phase ID format? | Bare slug in manifests (`"implementation"`), qualified in rules (`"project-team:testing"`) |
| Phase ID namespace collision? | Qualified IDs (`workflow_id:phase_id`) in `phase_block`/`phase_allow`. Runtime matches `f"{workflow_id}:{phase_id}"` from `phase_state.json`. |
| `phase_state.json` discovery? | Default: `<project_root>/.ao_project_team/phase_state.json`. Override: `PHASE_STATE_PATH` env var (for testing). |
| `CheckContext.ask_user()`? | Removed. `ManualConfirm` calls `input()` directly — no need to thread user interaction through the context bag. |
| Standalone check discovery? | `CheckFailed` adapter bridges Check → TriggerCondition. Setup checks are HintSpecs that fire at startup. `/check-setup` cut — hints pipeline IS the discovery mechanism. See `specification/check_inventory.md` for full analysis. |
| Phase registration? | From manifest files (`phases.yaml` / `tutorial.yaml`). `generate_hooks.py` reads them, validates qualified `phase_block`/`phase_allow` references. Default: warn. `--strict`: hard error (CI). |
| Workflow type needed? | No — a workflow is a manifest + directory of markdown files. One WorkflowEngine serves both project-team and tutorials. |
| What stays in COORDINATOR.md? | Cross-phase content only (Prime Directive, Key Terms) |
| Directory naming? | `AI_agents/` stays in v1. Rename to `teams/` deferred to v2 (cosmetic, large blast radius). |

### 10.2 Unresolved (decide during implementation)

| Decision | Options | Notes |
|---|---|---|
| Check registry extensibility | Closed registry (v1) vs. plugin system (v2) | v1: hardcoded 3 types. v2: add registration API |
| `phase_state.json` atomic write | Temp-then-rename vs. file lock | Temp-then-rename matches existing `HintStateStore` pattern |

### 10.3 Known bugs (fix during implementation)

| Bug | Description | Fix |
|---|---|---|
| `.test_runs/` missing from template | R01 redirects pytest output to `.test_runs/` but the directory doesn't exist in the copier template. New projects fail on first full test run. | Add `.test_runs/.gitkeep` to the copier template. |

---

## 11. Terminology

| Term | Definition |
|---|---|
| **Check** | Protocol: `check(ctx) → CheckResult`. Engine runs checks, not the agent — system-level enforcement. |
| **CheckResult** | Verdict with passed/failed, message, and evidence |
| **CheckFailed** | Adapter: bridges Check → TriggerCondition; fires when a check fails |
| **FileContentCheck** | Built-in check: passes when file content matches a regex pattern |
| **Phase** | Named state in a workflow; pure markdown file + entry in manifest |
| **Phase transition** | Atomic switch from one phase to the next; engine evaluates gate checks before advancing |
| **Phase-scoped guardrail** | Guardrail rule with `phase_block` / `phase_allow` fields |
| **Phase-scoped context** | Hints whose triggers reference `ActivePhase` |
| **Phase coherence** | Guardrails, gates, hints, and content all derive from `phase_state.json` |
| **Phase registry** | Set of valid qualified phase IDs (`workflow_id:phase_id`), parsed from manifest files |
| **Qualified phase ID** | `"workflow_id:phase_id"` format used in `phase_block`/`phase_allow` to avoid namespace collisions |
| **Manifest** | `phases.yaml` (project-team) or `tutorial.yaml` (tutorials) — defines phase IDs, ordering, checks, hints |
| **Workflow** | A manifest + directory of phase markdown files. One `WorkflowEngine` serves all workflow types. |
| **WorkflowEngine** | Single engine class that drives phase transitions for any workflow (project-team or tutorial) |
| **Gate** | Check(s) that must pass before phase transition. Engine evaluates gates — agent cannot bypass. |
| **Guard** | `phase_block` / `phase_allow` on a rule in `rules.yaml` (uses qualified phase IDs) |
| **Content focus** | Agent prompt scoped to current phase file (optimization, not enforcement) |
| **`user_confirm`** | Guardrail enforcement level: hook blocks action, prompts user directly. Agent cannot fabricate approval. Between `warn` and `deny`. |

---
---

## Appendix A: Design Rationale

This appendix records design decisions and rejected alternatives. It is not part of the execution plan.

### A.1 Why manifests over frontmatter

Phase files were originally markdown with YAML frontmatter (config + content in one file). This was changed because:

- Phase files become simpler (pure markdown, no YAML knowledge needed to write instructions)
- Config is visible in one place per workflow (the manifest) instead of scattered across N phase files
- The manifest provides an explicit ordering and single-file overview of all phases
- Follows the pattern of `rules.yaml` (rule config) and `hints/hints.py` (hint config) — each system owns its configuration in its own file

### A.2 Why Level 0 content focus for v1, not Level 1

A warn guardrail on phase file reads cannot distinguish the current phase file from other phase files without phase-aware hooks (it would need to read `phase_state.json` to know which phase is current). Without that awareness, the rule fires on every legitimate read of the current phase file — a false positive every turn. Level 1 and Level 2 both require phase-scoped hook infrastructure, making them v2 work.

### A.3 Why the two-lock framing was wrong

The original design called content scoping and guardrail scoping "two locks, inherently synced." They are not both locks:

| Before | After |
|---|---|
| "Two locks, inherently synced" | One enforcement layer (guardrails + gates) + one optimization layer (content focus) |
| "Can't desync" | Enforcement can't be bypassed; focus is best-effort |
| Content lock is load-bearing | Content focus is performance optimization |

The agent CAN read `phase-05-testing.md` while guardrails scope to `phase-04-implementation`. But the guardrails still enforce Phase 4 rules. The gate checks still run. The hints still scope to Phase 4. The architecture does not depend on content focus.

### A.4 Research evidence for content focus

| Evidence | Source | Finding |
|---|---|---|
| Observation masking improves performance | JetBrains 2025 | 2.6% improvement + 52% cost savings |
| Irrelevant context degrades performance | Lost in the Middle, TACL 2024 | >30% degradation for buried info |
| Content lock cannot reach 100% | Attack surface analysis | Memory, inference, Bash bypass all file-level restrictions |

### A.5 Superseded files

All other files in `specification/` are working documents from the design process spanning four eras: tutorial-specific (axis specs, reviews), infrastructure reframe, phase unification, and content lock analysis. They record the evolution of the architecture but are no longer authoritative. If this document and a superseded file disagree, this document wins.

### A.6 Terminology migration

Previous specification files use inconsistent terminology across three eras:

| Era | Terms used |
|---|---|
| Layer 1 (Tutorial-specific) | Tutorial Step, Tutorial Mode, Tutorial Guardrail, Verification, VerificationResult |
| Layer 2 (Infrastructure) | Step, Scoped Mode, Scoped Guardrail, ModeContext, Check, CheckResult |
| Layer 3 (Phase unification) | Phase, Phase transition, Phase-scoped guardrail, ActivePhase, Check, CheckResult |

This specification uses Layer 3 exclusively. The "Replaces" column for each term: Check replaces Verification; Phase replaces Step/Tutorial Step/Workflow State/Mode; Phase-scoped guardrail replaces Tutorial Guardrail/Scoped Mode; Content focus replaces Content lock.

### A.7 Why rule scoping lives in rules.yaml, not phase files

Rules exist independently of phases (R01 existed before phases). Phase scoping is a modifier on the rule, not a property of the phase. Putting `activate_rules`/`deactivate_rules` in phase files duplicated information that already had a natural home in `rules.yaml`. The principle: if the config wouldn't exist without the rule, it goes in `rules.yaml`. If the config wouldn't exist without the phase, it goes in the manifest.

---

## Appendix B: Reference Implementations

### B.1 Phase registry builder (`generate_hooks.py`)

```python
def build_phase_registry(manifest_paths: list[str], project_root: Path) -> set[str]:
    """Parse manifest files (phases.yaml / tutorial.yaml), extract qualified phase IDs.

    Returns set of qualified IDs: {"project-team:testing", "first-pytest-tutorial:run-test", ...}.
    """
    qualified_ids: set[str] = set()
    for manifest in manifest_paths:
        full_path = project_root / manifest
        if not full_path.exists():
            _warn(f"Manifest not found: {manifest} "
                  f"(declared in rules.yaml 'workflows')")
            continue
        data = yaml.safe_load(full_path.read_text())
        workflow_id = data.get("workflow_id", "")
        if not workflow_id:
            _warn(f"Manifest missing workflow_id: {manifest}")
            continue
        for phase in data.get("phases", []):
            if "id" in phase:
                qualified_ids.add(f"{workflow_id}:{phase['id']}")
    return qualified_ids
```

### B.2 Phase reference validator (`generate_hooks.py`)

```python
def validate_phase_references(
    rules: list[dict],
    known_phases: set[str],
    strict: bool = False,
) -> list[str]:
    """Validate that all phase_block/phase_allow qualified IDs exist in the registry.

    known_phases: set of qualified IDs from build_phase_registry().
    Default: prints warnings, returns list of issues.
    --strict mode: raises SystemExit on first unknown phase ID (for CI).
    """
    issues: list[str] = []
    for rule in rules:
        for field in ("phase_block", "phase_allow"):
            referenced = rule.get(field, [])
            for qualified_id in referenced:
                if ":" not in qualified_id:
                    msg = (
                        f"Rule '{rule['id']}' has unqualified phase '{qualified_id}' "
                        f"in '{field}'. Use 'workflow_id:phase_id' format."
                    )
                    if strict:
                        raise SystemExit(f"[STRICT] {msg}")
                    _warn(msg)
                    issues.append(msg)
                elif qualified_id not in known_phases:
                    msg = (
                        f"Rule '{rule['id']}' references unknown phase '{qualified_id}' "
                        f"in '{field}'. "
                        f"Known phases: {sorted(known_phases)}. "
                        f"Check for typos or add the phase to the manifest."
                    )
                    if strict:
                        raise SystemExit(f"[STRICT] {msg}")
                    _warn(msg)
                    issues.append(msg)
    return issues
```

### B.3 v2 content focus Level 1 rule (requires phase-aware hooks)

```yaml
- id: R10
  name: phase-file-advisory
  trigger: PreToolUse/Read
  enforcement: warn
  phase_allow: []            # Requires phase-aware hooks to resolve current phase
  detect:
    type: regex_match
    field: file_path
    pattern: 'phases/phase-\d+'
  message: "[GUARDRAIL WARN R10] You are reading a phase file outside your current phase."
```
