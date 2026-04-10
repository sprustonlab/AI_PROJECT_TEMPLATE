# Tutorial System: Architecture Specification

**Status:** Definitive — all other files in `specification/` are superseded.
**Author:** Composability (Lead Architect)
**Date:** 2026-04-05 (updated for SDK hook architecture — PoC validated)

---

## 1. Vision

Build **general infrastructure primitives** that workflows consume. Tutorials, project-team builds, and future systems are all **workflows** — the umbrella term. The tutorial system is the first consumer, not the architecture.

**Principle:** v1 is infrastructure. v2 is tutorial.

### 1.0 Mental Model: 2×2 Guidance Framing

The entire guidance system — not just guardrails — operates on two independent axes: **Positive/Negative** × **Advisory/Enforced**.

|  | **Advisory** (suggestion, agent can bypass) | **Enforced** (deterministic, agent cannot bypass) |
|---|---|---|
| **Positive** (do this) | **A: Do's in MD files** — phase instructions, best practices, role guidance. "Write tests before implementation." | **C: Checkpoints** — verify something IS done correctly. `FileExistsCheck`, `CommandOutputCheck`, `ManualConfirm`. Enforced by the engine. |
| **Negative** (don't do this) | **B: Don'ts** — warnings, anti-patterns, scope boundaries. "Do not run the full test suite during implementation." | **D: Guardrails** — block forbidden actions. `deny` and `user_confirm` rules in workflow manifests. Enforced by SDK hooks. |

**Key insight:** A and B are advisory — the agent can bypass them. C and D are enforced — the agent cannot bypass them. The advisory/enforced boundary is about bypassability, not about where the guidance lives.

**Where `warn` and `log` fit:** These enforcement levels live in code (SDK hooks, manifest `rules:` section) but the agent CAN bypass them — `warn` requires acknowledgement but the agent proceeds, `log` is silent. They are **advisory-negative delivered via code** rather than markdown. They bridge B and D: they use D's infrastructure (manifests, SDK hooks) but have B's bypassability. For the purposes of the 2×2, they are advisory (B), not enforced (D). Only `deny` and `user_confirm` are truly enforced (D).

**Both advisory and enforced evolve across phases:**
- **Advisory (A, B):** Each phase has its own markdown file with phase-specific do's and don'ts. `warn`/`log` rules in manifests also scope per-phase via `phase_block`/`phase_allow`. The engine serves only the current phase file → the agent sees only current-phase guidance.
- **Enforced (C):** Checkpoints are defined per-phase in the manifest (`advance_checks`). Each phase has its own gates.
- **Enforced (D):** `deny`/`user_confirm` guardrails are scoped per-phase via `phase_block`/`phase_allow` in manifests. Rules activate/deactivate as phases change.

**The four quadrants map to concrete infrastructure:**

| Quadrant | Where it lives | Mechanism | Phase-scoping |
|---|---|---|---|
| **A** (advisory positive) | Phase markdown files | Agent reads instructions | Engine serves current phase file |
| **B** (advisory negative) | Phase markdown files + `warn`/`log` rules in manifests | Agent reads warnings; SDK hooks deliver `warn`/`log` | Engine serves current phase file; `phase_block`/`phase_allow` on rules |
| **C** (enforced positive) | Workflow manifests (`advance_checks`) | `advance_checks` — engine runs checks | Per-phase in manifest |
| **D** (enforced negative) | Workflow manifests (`rules:` section, `deny`/`user_confirm` only) | SDK hook closures block actions | `phase_block`/`phase_allow` on rules |

This framing is foundational: every piece of guidance in the system fits one quadrant, determined by bypassability (advisory vs enforced) and direction (positive vs negative).

### What v1 delivers

1. **Check primitive** — reusable assertion protocol with evidence
2. **Phase primitive** — unified state that scopes guardrails, gates, and hints
3. **Phase-scoped guardrails** — existing rules gain `phase_block` / `phase_allow` fields
4. **Agent folder split** — agent folders (identity + per-phase markdown) + `project_team.yaml` manifest that enable phase discovery
5. **Global manifest** — `workflows/global.yaml` with global rules, checks, and hints (setup checks as YAML)
6. **First Pytest tutorial** — proof-of-concept tutorial consuming the primitives

### What v1 does NOT deliver

See §9 (V2 Scope) for the full list. Key exclusions: CompoundCheck (`AnyOf`), content focus guards, tutorial catalog, multi-workflow, tutorial UI.

### 1.1 User Journey (First Pytest tutorial)

What the user actually types and sees:

```
$ claude
> /tutorial first-pytest

  Tutorial: Write Your First Pytest Test
  Phase 1 of 2: Write a test

  Create a file tests/test_example.py with a test function.
  The function name must start with test_.

  When you're done, I'll verify the file and ask you to confirm.

> [user writes test file with Claude's help]

  ✓ tests/test_example.py exists
  ✓ tests/test_example.py contains "def test_"
  ? Does tests/test_example.py contain a meaningful test? [yes/no]

> yes

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

### 2.1 Check (Quadrant C: Enforced-Positive)

A pure assertion: inspect system state, return a verdict with evidence.

**The engine runs checks, not the Coordinator.** Checks are quadrant C in the 2×2: enforced-positive. They verify something IS done correctly. Just as guardrails (quadrant D) prevent agents from doing forbidden things, checks prevent the Coordinator from skipping phases. Checks are to the Coordinator what guardrails are to agents.

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
```

```python
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
| `ManualConfirm` | `(question)` | User answers affirmatively | Prove the user actually approved |

**ManualConfirm is system-level in v1.** The engine prompts the user directly via the TUI — for guidance that requires human judgment and can't be transferred to a programmatic check. The `WorkflowEngine` holds a reference to the `app` instance and calls `await app._show_manual_confirm(question)`, which mounts a `SelectionPrompt` widget. The user sees the question from the manifest and selects Yes/No.

This is possible because claudechic is required and the engine runs in-process with access to the same `app` instance that guardrail hooks use. The PoC for `_show_guardrail_confirm()` proved the pattern; `ManualConfirm` reuses it.

#### Transferring guidance from advisory to enforced

If a rule can be verified programmatically, it should be a check (quadrant C) rather than an instruction in a markdown file (quadrant A). Checks transfer easily enforceable guidance from advisory to enforced — the agent doesn't need to remember to follow the rule because the engine verifies it.

**Example:** Instead of writing "Name your test function with `test_` prefix" in a phase markdown file (advisory — the agent might miss it), add a `FileContentCheck` that verifies the pattern exists. If the agent skips it, the check catches it at the gate.

The `advance_checks` list has AND semantics — all checks must pass. Compose programmatic checks with `ManualConfirm` for guidance that requires human judgment:

```yaml
advance_checks:
  - type: file-exists-check
    path: "tests/test_example.py"
  - type: file-content-check
    path: "tests/test_example.py"
    pattern: "def test_"
  - type: manual-confirm
    question: "Does tests/test_example.py contain a meaningful test?"
```

The engine evaluates checks **in declaration order with short-circuit on first failure**. Programmatic checks run first (fast, cheap). If they pass, `ManualConfirm` asks the user to verify what can't be checked programmatically. The user isn't bothered if the file doesn't even exist yet.

`FileContentCheck` reads a file and matches against a regex pattern. This transfers content requirements from advisory to enforced — e.g., "STATUS.md must contain spawn evidence for all Leadership agents" becomes a programmatic check instead of an instruction the Coordinator might overlook.

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

**Check type registry:** Checks are declared by type name in manifest files (e.g., `type: file-exists-check` in `project_team.yaml` or `first-pytest.yaml`). The registry maps type names to Python classes:

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
- **Discovery:** `WorkflowLoader` reads `checks:` sections from all manifests
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

#### v1 setup checks as YAML

Each check tests an OUTCOME (can you authenticate? can you import?), not an implementation detail (does this file exist?). Global checks live in `workflows/global.yaml`:

```yaml
# workflows/global.yaml — global manifest
checks:
  # Check 1: GitHub authentication works (tokens expire, keys get revoked,
  # scientists move between machines — installer only checks at install time)
  - id: github_auth
    type: command-output-check
    command: "git ls-remote https://github.com/sprustonlab/claudechic.git HEAD 2>&1 | head -1"
    pattern: "[0-9a-f]{40}"
    on_failure:
      message: "GitHub authentication failed. Run: gh auth login"
      severity: warning
      lifecycle: show-until-resolved

  # Check 2: Git identity configured (not checked anywhere in the template —
  # scientists on shared HPC nodes commit as root@login-node.cluster.edu)
  - id: git_identity
    type: command-output-check
    command: "git config user.email"
    pattern: ".+@.+"
    on_failure:
      message: "Git email not configured. Run: git config --global user.email 'you@example.com'"
      severity: warning
      lifecycle: show-until-resolved

  # Check 3: Pixi environment is healthy (activate checks pixi install ran,
  # but doesn't verify the result works — broken after pixi update or NFS
  # cache staleness on clusters)
  - id: pixi_env
    type: command-output-check
    command: 'pixi run python -c "import yaml; print(ok)" 2>&1'
    pattern: "ok"
    on_failure:
      message: "Pixi environment is broken. Try: pixi install --force"
      severity: warning
      lifecycle: show-until-resolved

  # Check 4: Cluster SSH works (conditional — only when use_cluster=true.
  # Without this, cluster MCP tools hang on SSH password prompt, appearing
  # as a frozen TUI. This is the single worst UX failure in the template.)
  - id: cluster_ssh
    type: command-output-check
    when: { copier: use_cluster }    # Only evaluate when copier answer is truthy
    command: "ssh -o ConnectTimeout=5 -o BatchMode=yes ${cluster_ssh_target} hostname 2>&1"
    pattern: "^[a-zA-Z]"
    on_failure:
      message: "Cannot SSH to cluster. Run: ssh-copy-id ${cluster_ssh_target}"
      severity: warning
      lifecycle: show-until-resolved
```

The `WorkflowLoader` reads these, `CheckSection` parses them with namespace `_global:`, and the engine creates `CheckFailed` → `HintSpec` objects internally. These fire automatically at session startup via the existing hints pipeline. `show-until-resolved` re-checks each session until the scientist fixes the issue.

The `when` clause supports simple copier-answer conditions: `when: { copier: field_name }` evaluates to true when the named copier answer is truthy. This handles the common case of conditional setup checks without requiring Python.

### 2.2 Phase

A named state in a workflow that determines what is allowed, what must be proven, and what guidance is relevant. Phases scope all four quadrants of the 2×2: the advisory layer (A, B) via phase markdown files, and the enforced layer (C, D) via `advance_checks` and `phase_block`/`phase_allow`.

#### Agent folders: identity + per-phase markdown

Each agent in a workflow has a folder. The folder name IS the agent's role type — used in `block_roles`/`allow_roles` in rules and passed to `_guardrail_hooks(agent_role=...)`.

Each agent folder contains:
- **`identity.md`** — cross-phase identity (who you ARE, always loaded)
- **Per-phase markdown files** — phase-specific instructions (what to do NOW, loaded when that phase is active)

All markdown files are pure advisory content (quadrants A, B). No YAML frontmatter, no configuration.

```
workflows/project_team/
  coordinator/
    identity.md              # "YOUR JOB IS TO DELEGATE, NOT TO DO." (~30 lines)
    vision.md                # Phase-specific Coordinator instructions
    setup.md
    specification.md
    implementation.md
    testing.md
    signoff.md
  composability/
    identity.md              # "You are Lead Architect..." (~100 lines)
    specification.md         # Phase-specific if needed
  skeptic/
    identity.md
    specification.md
  implementer/
    identity.md
    implementation.md
    testing.md
```

**Agent prompt assembly:** When spawning an agent, the system reads `identity.md` (always) + the current phase's markdown file if it exists in that agent's folder. Agent prompt = identity (who you are) + phase file (what to do now).

**Role type = folder name.** The folder name (`coordinator`, `composability`, `implementer`) is the agent's role type. This is the value passed to `_guardrail_hooks(agent_role="implementer")` and matched against `block_roles`/`allow_roles` in rules. No separate role-type registry — the folder name IS the identity.

#### Phase configuration lives in manifest files

Each workflow has a manifest that defines phase IDs, ordering, and gate checks:

**Project-team workflow (`project_team.yaml`):**

```yaml
# workflows/project_team/project_team.yaml
workflow_id: project-team

rules:
  - id: pip_block
    trigger: PreToolUse/Bash
    enforcement: deny
    detect: { pattern: '\bpip\s+install\b', field: command }
    message: "Use pixi, not pip."

  - id: pytest_output
    trigger: PreToolUse/Bash
    enforcement: deny
    phase_block: ["project-team:testing"]
    detect: { pattern: '(?:^|&&|\|\||;|\brun\s+)\s*pytest\b', field: command }
    message: "Redirect pytest output to .test_runs/"

  - id: close_agent
    trigger: PreToolUse/mcp__chic__close_agent
    enforcement: user_confirm
    phase_allow: ["project-team:specification"]
    block_roles: [implementer]                    # Only fires for implementer agents
    message: "Close agent during specification — user approval required."

phases:
  - id: vision
    file: coordinator/vision.md
  - id: setup
    file: coordinator/setup.md
  - id: spawn-leadership
    file: coordinator/spawn-leadership.md
  - id: specification
    file: coordinator/specification.md
  - id: implementation
    file: coordinator/implementation.md
    advance_checks:
      - type: manual-confirm
        question: "Are all implementation tasks complete and Leadership-approved?"
    hints:
      - message: "Focus on writing code, not running the full test suite"
        lifecycle: show-once
  - id: testing
    file: coordinator/testing.md
    advance_checks:
      - type: command-output-check
        command: "pixi run pytest --tb=short 2>&1 | tail -1"
        pattern: "passed"
  - id: signoff
    file: coordinator/signoff.md
```

**Tutorial workflow (`first-pytest.yaml`):**

```yaml
# workflows/first-pytest/first-pytest.yaml
workflow_id: first-pytest-tutorial
phases:
  - id: write-test
    file: learner/write-test.md
    advance_checks:                          # Evaluated in order, short-circuit on failure
      - type: file-exists-check
        path: "tests/test_example.py"
      - type: file-content-check             # Enforces naming convention programmatically
        path: "tests/test_example.py"
        pattern: "def test_"
      - type: manual-confirm                 # Only reached if programmatic checks pass
        question: "Does tests/test_example.py contain a meaningful test?"
    hints:
      - message: "Create tests/test_example.py with a function starting with test_"
        trigger: { type: phase-stuck, threshold_seconds: 120 }
  - id: run-test
    file: learner/run-test.md
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
| Agent identity | `<agent>/identity.md` in workflow folder | Cross-phase, always loaded for that agent |
| Phase-specific instructions | `<agent>/<phase>.md` in workflow folder | Per-phase, loaded alongside identity |
| Agent role type | Agent folder name (`coordinator`, `implementer`) | Used in `block_roles`/`allow_roles`, passed to hook closures |
| Phase IDs and ordering | Workflow manifest (`<name>.yaml`) | Per-workflow structure |
| Gate checks (advance_checks) | Workflow manifest (`<name>.yaml`) | Per-phase, defined alongside phase ID |
| Phase hints | Workflow manifest (`<name>.yaml`) | Per-phase, declared under phase entry |
| Global rules/checks/hints | `workflows/global.yaml` | Always-active, namespace `_global:` |
| Workflow-specific rules | Workflow manifest (`<name>.yaml`, `rules:` section) | Per-workflow, with `phase_block`/`phase_allow` |

#### Type definitions

```python
@dataclass(frozen=True)
class CheckDeclaration:
    """A check as declared in a manifest file (project_team.yaml / first-pytest.yaml).

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
    """A hint as declared in a workflow manifest or global manifest.

    Parsed from YAML. The engine converts these to HintSpec objects
    at phase entry time (phase hints) or at startup (global hints).
    """
    message: str
    trigger: dict[str, Any]            # {type: "phase-stuck", threshold_seconds: 120}
    lifecycle: str = "show-once"       # "show-once" (v1 only; "show-until-phase-complete" is v2)
```

```python
@dataclass(frozen=True)
class PhaseMeta:
    """Parsed from workflow manifest (e.g., project_team.yaml or first-pytest.yaml).

    The engine reads this. The agent never sees it.
    """
    id: str
    file: str                                      # Relative path to phase markdown (e.g., "coordinator/implementation.md")
    advance_checks: tuple[CheckDeclaration, ...] = ()
    hints: tuple[HintDeclaration, ...] = ()


@dataclass(frozen=True)
class ActivePhase:
    """Runtime state: which phase is current.

    Written to workflows/<name>/state.json.
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

**Qualified phase IDs in `phase_block` / `phase_allow`:** Rules use qualified IDs for phase references: `"workflow_id:phase_id"`. This prevents namespace collisions (e.g., two workflows both having a `"testing"` phase).

```yaml
# In workflows/project_team/project_team.yaml — qualified IDs prevent ambiguity
rules:
  - id: pytest_output
    phase_block: ["project-team:testing", "first-pytest-tutorial:run-test"]
```

The `WorkflowLoader` namespaces this as `project_team:pytest_output`. The runtime matches `f"{workflow_id}:{phase_id}"` from per-workflow `state.json` against the qualified IDs in the rule. Phase validation at startup checks qualified IDs against `{workflow_id}:{phase_id}` pairs from all manifests.

#### How the 2×2 maps to phase configuration

```
Phase in manifest (enforced layer — C, D configured here)
├── Gates (C):   advance_checks (list of Checks)
│   → Enforced-positive: what must be proven before advancing
│
└── Context:     hints (list of HintDeclarations)
    → What guidance is relevant during this phase (tutorials)

Phase markdown file (advisory layer — A, B content here)
├── Do's (A):    instructions, best practices for this phase
└── Don'ts (B):  warnings, scope boundaries for this phase

Rule scoping (D) in manifest rules: section via phase_block/phase_allow
└── Enforced-negative: which guardrails activate/deactivate per phase
```

Rules live in the same manifest as phases — single file per workflow. Global rules in `workflows/global.yaml`.

---

## 3. Phase Coherence

### 3.1 The single source of truth: per-workflow `state.json`

Each active workflow has its own state file in `workflows/<workflow_name>/state.json`. The subfolder name is the workflow identity — the same name used everywhere.

```
workflows/
  project_team/
    state.json
  first-pytest/
    state.json
```

```json
{
  "workflow_id": "project-team",
  "phase_id": "implementation",
  "phase_entered_at": 1712160000.0,
  "current_phase_file": "workflows/project_team/coordinator/implementation.md"
}
```

`current_phase_file` is the relative path to the current phase's markdown file (from the manifest). This enables any consumer — guardrails, hints, `/compact` recovery — to find the phase content without parsing the manifest.

Completed phases are not persisted. They are derivable from `phase_id` + manifest ordering (all phases before the current one are complete). This avoids redundant state.

- **Location:** `workflows/<workflow_name>/state.json` (one per active workflow)
- **Written by:** WorkflowEngine at phase transitions
- **Read by:** SDK guardrail hook closures, hints pipeline, SDK `PostCompact` recovery hook, agent prompt assembly

These files persist across sessions.

### 3.2 Phase transition

```
Phase A (current) → Phase B (next)

1. ENGINE runs Phase A's advance_checks → all must pass (gate)
   - The Coordinator requests advance; the ENGINE evaluates checks
   - ManualConfirm: engine prompts user directly via TUI (`SelectionPrompt`)
   - CommandOutputCheck: ENGINE runs the command (enforced, not advisory)
   - FileContentCheck: ENGINE reads the file (enforced, not advisory)
2. Unregister Phase A's hints
3. Register Phase B's hints
4. Update ActivePhase (new phase_id, reset phase_entered_at)
5. Persist to `workflows/<name>/state.json`
6. Deliver Phase B's markdown file to agent prompt
```

Steps 2-5 happen atomically from the engine's perspective. Rule scoping updates automatically: the SDK guardrail hook closure reads the new `phase_id` from the workflow's `state.json` and evaluates `phase_block`/`phase_allow` via `should_skip_for_phase()` at runtime. No explicit rule swap step needed.

### 3.2.1 WorkflowEngine interface

There is one engine. Tutorials and project-team workflows are both "a manifest + markdown files" — the engine doesn't distinguish them.

```python
class WorkflowEngine:
    """Drives phase transitions for any workflow (project-team or tutorial).

    Instantiated once per workflow session. Reads the manifest, manages
    phase state, evaluates gates, and provides the current phase file path.
    """

    def __init__(self, manifest_path: Path, project_root: Path) -> None:
        """Load manifest, parse PhaseMeta entries, read or create state.json in workflows/<name>/."""
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

        1. Run current phase's advance_checks **in declaration order**
        2. Short-circuit on first failure (don't run ManualConfirm if
           programmatic checks haven't passed yet)
        3. If all pass → transition (update state, persist, return success)
        4. If any fail → return failure with CheckResults
        5. If already on last phase → return workflow-complete

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

- **Project-team:** The Coordinator's `identity.md` includes 3 lines of cross-phase instruction: "Read `workflows/project_team/state.json`. Load the file at `current_phase_file`. Follow those instructions." The Coordinator reads its identity + current phase markdown at session start and after each advance.
- **Tutorials:** A `/tutorial` slash command (`.claude/commands/tutorial.md`) instantiates the engine, reads the current phase file, and prints it. The agent follows the instructions and calls `/tutorial advance` to attempt progression.
- **Phase file delivery is pull-based (agent reads), not push-based (engine injects).** Identity is always loaded; phase markdown is loaded for the current phase only.

**`/compact` recovery:** After `/compact` clears context, the agent loses phase awareness. A SDK `PostCompact` hook (~30 lines in `app.py`) reads the workflow's `state.json` and re-injects: "You are in phase `{phase_id}`. Read `{current_phase_file}` for your current instructions." This is registered alongside the guardrail hooks via `_merged_hooks()` — same pattern, same infrastructure.

### 3.3 Phase-scoped guardrails (Quadrant D: Enforced-Negative)

Rules live in workflow manifests — global rules in `workflows/global.yaml`, workflow-specific rules in `workflows/<name>/<name>.yaml`. All rules are in `rules:` sections alongside checks, hints, and phases. Rules gain `phase_block` / `phase_allow` fields for phase scoping.

#### Rules in manifests

**Global rules** (always active, no workflow required):

```yaml
# workflows/global.yaml
rules:
  - id: pip_block
    trigger: PreToolUse/Bash
    enforcement: deny
    detect: { pattern: '\bpip\s+install\b', field: command }
    message: "Use pixi, not pip."

  - id: conda_block
    trigger: PreToolUse/Bash
    enforcement: deny
    detect: { pattern: '\bconda\s+install\b', field: command }
    message: "Use pixi, not conda."
```

The `WorkflowLoader` namespaces these as `_global:pip_block`, `_global:conda_block`.

**Workflow-specific rules** (alongside phases in the same manifest):

```yaml
# workflows/project_team/project_team.yaml
rules:
  - id: pytest_output
    trigger: PreToolUse/Bash
    enforcement: deny
    phase_block: ["project-team:testing"]
    detect: { pattern: '(?:^|&&|\|\||;|\brun\s+)\s*pytest\b', field: command }
    message: "Redirect pytest output to .test_runs/"
```

The `WorkflowLoader` namespaces this as `project_team:pytest_output`.

**Namespace convention:** Rule IDs in YAML are bare (`pip_block`). The loader prefixes them with the namespace: `_global:` for `workflows/global.yaml`, `<folder_name>:` for `workflows/<name>/<name>.yaml`. Fully qualified IDs are structurally unique because folder names are unique.

#### SDK hook architecture (replaces file-based hooks)

**claudechic is required.** All guardrail hooks are SDK hooks registered via the claudechic Python SDK. There is no vanilla Claude Code fallback, no `generate_hooks.py`, no `settings.json` hook entries, no file-based hook scripts.

**What this replaces (~2860 lines deleted):**

| Deleted component | Lines | Why |
|---|---|---|
| `generate_hooks.py` | ~2155 | SDK hooks evaluate rules at runtime; no code generation needed |
| `bash_guard.py` | ~173 | Rule matching handled by `guardrails/rules.py` |
| `write_guard.py` | ~185 | Rule matching handled by `guardrails/rules.py` |
| `role_guard.py` | ~350 | Role scoping built into `should_skip_for_role()` |
| `settings.json` hook entries | — | SDK hooks registered programmatically |
| Session marker system + env vars | — | Per-agent closures replace dynamic role lookup |
| `.claude/guardrails/rules.d/` | — | Rules move into workflow manifests |

**What this adds (~210 lines):**

| New component | Lines | What it does |
|---|---|---|
| `guardrails/rules.py` | ~130 | Rule loader + matching + validation (YAML → Rule dataclass, regex matching, role/phase skip, startup validation) |
| `guardrails/hits.py` | ~30 | Hit logging to `.claude/hits.jsonl` |
| `app.py` changes | ~50 | `_guardrail_hooks()`, `_show_guardrail_confirm()`, `_merged_hooks()` |
| `_show_guardrail_confirm()` | ~30 | Reuses existing `SelectionPrompt` widget for `user_confirm` prompts |

**How it works (PoC validated, 2.4ms avg):**

1. `WorkflowLoader` reads all manifests (`workflows/global.yaml` + `workflows/*/<name>.yaml`) and extracts `rules:` sections. Rules are namespaced and concatenated into a single list. **No mtime caching** — NFS mtime is unreliable on HPC clusters. Rules are loaded fresh on every tool call.

2. **Per-agent closures with static role.** `_guardrail_hooks(agent_role)` creates a closure that captures `agent_role` at agent creation time. The `agent_role` is the agent's folder name (e.g., `"coordinator"`, `"implementer"`, `"composability"`). Each agent gets its own hook closure with its role baked in. No dynamic `current_agent_role()` lookup needed.

3. `_guardrail_hooks()` in `app.py` builds hook closures, wired into agent options via `_make_options()`. The closure is registered as a `PreToolUse` hook matcher.

4. **`user_confirm` enforcement** uses `{"decision": "block"}` + async `SelectionPrompt` in the TUI. The hook returns a block decision, then awaits `_show_guardrail_confirm()` which mounts a `SelectionPrompt` widget. If the user selects "Allow", the hook returns `{}` (proceed). If "Deny", it returns `{"decision": "block", "reason": ...}`. **NOT** `permissionDecision: "ask"` — that path is unverified in the SDK.

**Proven implementation (from PoC):**

```python
# guardrails/rules.py — Rule dataclass (frozen, immutable)
@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    trigger: list[str]                                # ["PreToolUse/Bash"] or ["PreToolUse/Write", "PreToolUse/Edit"]
    enforcement: str                                  # "deny" | "user_confirm" | "warn" | "log"
    detect_pattern: re.Pattern[str] | None = None     # Compiled regex
    detect_field: str = "command"                      # Which tool_input field to match
    exclude_pattern: re.Pattern[str] | None = None    # Exclusion regex
    message: str = ""
    block_roles: list[str] = field(default_factory=list)   # Rule only fires for these roles (folder names: "implementer", etc.)
    allow_roles: list[str] = field(default_factory=list)   # Rule never fires for these roles (folder names: "coordinator", etc.)
    phase_block: list[str] = field(default_factory=list)   # Rule doesn't fire during these phases (qualified IDs)
    phase_allow: list[str] = field(default_factory=list)   # Rule only fires during these phases (qualified IDs)

def matches_trigger(rule: Rule, tool_name: str) -> bool: ...
def match_rule(rule: Rule, tool_name: str, tool_input: dict) -> bool: ...
def should_skip_for_role(rule: Rule, agent_role: str | None) -> bool: ...
def should_skip_for_phase(rule: Rule, workflow_states: list[dict]) -> bool: ...
def read_all_workflow_states(workflows_dir: Path) -> list[dict]: ...  # Reads all workflows/*/state.json
```

```python
# app.py — hook closure (per-agent, static role)
def _guardrail_hooks(self, agent_role: str | None = None) -> dict[HookEvent, list[HookMatcher]]:
    workflows_dir = Path(self._cwd) / "workflows"
    app = self

    async def evaluate(hook_input: dict, match, ctx) -> dict:
        rules = WorkflowLoader(workflows_dir).load_rules_only()  # Rules only, always fresh — no caching
        workflow_states = read_all_workflow_states(workflows_dir)  # All state.json files
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input", {})

        for rule in rules:
            if not matches_trigger(rule, tool_name):
                continue
            if should_skip_for_role(rule, agent_role):      # Static role from closure
                continue
            if should_skip_for_phase(rule, workflow_states):
                continue
            if not match_rule(rule, tool_name, tool_input):
                continue

            if rule.enforcement == "deny":
                return {"decision": "block", "reason": rule.message}
            if rule.enforcement == "user_confirm":
                approved = await app._show_guardrail_confirm(rule)
                if not approved:
                    return {"decision": "block", "reason": f"User denied: {rule.message}"}
                return {}
            if rule.enforcement == "warn":
                return {"decision": "block", "reason": rule.message}
            # "log": fall through (allow)

        return {}

    return {"PreToolUse": [HookMatcher(matcher=None, hooks=[evaluate])]}

# app.py — user_confirm TUI prompt
async def _show_guardrail_confirm(self, rule) -> bool:
    options = [
        ("allow", "Allow — proceed with this action"),
        ("deny", "Deny — block this action"),
    ]
    title = f"🛡️ Guardrail {rule.id}: {rule.message}"
    prompt = SelectionPrompt(title, options)
    async with self._show_prompt(prompt):
        result = await prompt.wait()
    return result == "allow"
```

**Failure modes:**
- **`workflows/` directory unreadable** (missing, permissions): **fail-closed** — block all tool calls. If manifests can't be read, no guardrails are evaluable.
- **Individual manifest malformed** (parse error, invalid YAML): **fail-open** — skip the broken manifest with a warning, load from remaining manifests. One broken workflow shouldn't disable unrelated rules.
- **Individual rule error** (bad regex, missing field): **fail-open** — skip the broken rule, evaluate the rest. Log the error.

**Load-time validation (at startup):**
- **Namespaced IDs:** The loader prefixes rule IDs with the namespace (`_global:` or `<folder_name>:`). Duplicate fully-qualified IDs produce a warning (default) or hard error (strict mode / CI).
- **Valid regex:** All `detect.pattern` and `exclude_if_matches` values are compiled. Invalid regex produces a warning and the rule is skipped.
- **Valid enforcement:** Must be one of `deny`, `user_confirm`, `warn`, `log`. Unknown values produce a warning and the rule is skipped.
- **Valid triggers:** Must match `PreToolUse/ToolName` or bare `PreToolUse`. Unknown formats produce a warning.
- **Unknown fields:** Unexpected top-level fields in a rule produce a warning (forward compatibility).

**Runtime validation:** Same checks as load-time, but errors are logged rather than surfaced to the user. The loader returns only valid entries.

#### Phase registration and validation

The manifests are the phase registry. Discovery is structural — `WorkflowLoader` scans `workflows/*/`:

- `WorkflowLoader` reads all `workflows/<name>/<name>.yaml` manifests, extracts phase IDs and rules
- Every `phase_block`/`phase_allow` reference is validated against discovered phase IDs at startup
- Unknown phase IDs produce warnings (development-friendly) or hard errors in strict mode (CI)

**`project_team:pytest_output` is the v1 proof-of-concept:** Adding `phase_block: ["project-team:testing"]` exempts it during the project-team testing phase. Same convention as `block: [Subagent]` for role scoping — same YAML level, same mental model. Qualified IDs prevent namespace collisions across workflows.

#### Enforcement levels

All four enforcement levels use the same SDK hook infrastructure (manifest `rules:` sections + `guardrails/rules.py`), but they differ in bypassability — which determines their quadrant in the 2×2:

v1 adds **`user_confirm`**: the hook blocks the action and prompts the **user** directly via the TUI. If the user approves, the action proceeds; if not, it is denied. This sits between `warn` (agent decides) and `deny` (no bypass) — the user decides.

| Level | Who decides | Agent can bypass? | 2×2 quadrant | SDK hook return |
|---|---|---|---|---|
| `deny` | System | No | **D** (enforced-negative) | `{"decision": "block", "reason": "..."}` |
| `user_confirm` | User | No — hook prompts user via TUI | **D** (enforced-negative) | Block → `SelectionPrompt` → allow or block |
| `warn` | Agent | Yes — agent acknowledges | **B** (advisory-negative via code) | `{"decision": "block", "reason": "..."}` (agent sees reason) |
| `log` | Nobody | N/A — silent | **B** (advisory-negative via code) | `{}` (allow, logged) |

**Concrete use case:** Prevent closing agents during specification phase without user approval:

```yaml
# In workflows/project_team/project_team.yaml (rules: section)
  - id: close_agent
    trigger: PreToolUse/mcp__chic__close_agent
    enforcement: user_confirm
    phase_allow: ["project-team:specification"]
    message: "Close agent during specification — user approval required."
```

The loader namespaces this as `project_team:close_agent`.

**Runtime phase evaluation** is handled by `should_skip_for_phase()` in `guardrails/rules.py`:

```python
def should_skip_for_phase(rule: Rule, workflow_states: list[dict]) -> bool:
    """Check if a rule should be skipped based on active workflow phases.

    phase_block/phase_allow use qualified IDs: "workflow_id:phase_id".
    workflow_states is a list of state dicts read from workflows/*/state.json.
    """
    if not rule.phase_block and not rule.phase_allow:
        return False  # No phase restrictions

    if not workflow_states:
        return False  # No active workflows → rule fires normally

    # Build set of active qualified phase IDs across all workflows
    active_phases: set[str] = set()
    for state in workflow_states:
        workflow_id = state.get("workflow_id", "")
        phase_id = state.get("phase_id", "")
        if workflow_id and phase_id:
            active_phases.add(f"{workflow_id}:{phase_id}")

    if not active_phases:
        return False

    # phase_block: rule does NOT fire during these phases
    if rule.phase_block and active_phases & set(rule.phase_block):
        return True

    # phase_allow: rule ONLY fires during these phases
    if rule.phase_allow and not (active_phases & set(rule.phase_allow)):
        return True

    return False
```

### 3.4 Phase-scoped hints (Advisory layer support)

Hints bridge the advisory and enforced layers: they are delivered as suggestions (advisory), but their triggers can be enforced checks (`CheckFailed` adapter). Phase-scoped hints ensure the agent gets the right guidance for the current phase.

**All hints are YAML** — declared in manifests, same pattern for all workflows:

- **Phase hints:** Declared under the phase entry in the workflow manifest. Phase-scoping is structural — a hint under a phase fires during that phase. No `PhaseIs()` trigger class needed.
- **Global hints:** Declared in `workflows/global.yaml` `hints:` section. Always active.

```yaml
# workflows/project_team/project_team.yaml — phase hint (fires during implementation)
phases:
  - id: implementation
    file: coordinator/implementation.md
    hints:
      - message: "Focus on writing code, not running the full test suite"
        lifecycle: show-once
```

```yaml
# workflows/global.yaml — global hint (always active)
hints:
  - id: welcome
    message: "Read your identity.md for your role."
    lifecycle: show-once
```

The engine converts YAML `HintDeclaration` → `HintSpec` objects at phase entry time (for phase hints) or at startup (for global hints). This is the same pattern tutorials already use — now project-team workflows use it too.

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
2. The engine runs checks, not the agent — this is system-level enforcement (quadrant C in the 2×2)
3. All phase consumers read per-workflow `state.json` — this is the coherence mechanism for all four quadrants
4. Agent prompt is scoped to the current phase file — this is the advisory layer (quadrants A, B), optimization not enforcement
5. `CheckFailed` adapter bridges Check → TriggerCondition — checks compose into hints without either protocol knowing about the other
6. Advisory (A, B) and enforced (C, D) are independent — removing all markdown instructions doesn't weaken guardrails or checkpoints; removing all guardrails doesn't weaken instructions

### 3.6 Unified manifest loading (ManifestSection protocol)

All three systems (rules, checks, hints) follow the same organizational pattern: YAML declarations in manifests, global + workflow scoping, namespaced IDs. The `ManifestSection[T]` protocol enforces this pattern.

```python
class ManifestSection(Protocol[T]):
    """Parses one section from workflow manifests.

    Each system implements this to tell the loader:
    1. Which YAML key is mine
    2. How to parse raw dicts into typed objects
    3. How to validate the result
    """

    @property
    def key(self) -> str:
        """YAML section key: 'rules', 'checks', 'hints'"""
        ...

    def parse_entries(self, raw: list[dict], namespace: str) -> list[T]:
        """Parse YAML dicts into typed entries.

        namespace is '_global' for global.yaml,
        '<folder_name>' for workflows/<name>/<name>.yaml.
        Entries get namespaced IDs: f'{namespace}:{entry_id}'.
        """
        ...

    def validate(self, entries: list[T]) -> list[str]:
        """Validate entries. Returns list of issues (empty = valid)."""
        ...
```

Three implementations:

| Section | `key` | Entry type | What it parses |
|---|---|---|---|
| `RuleSection` | `"rules"` | `Rule` | Guardrail rules with trigger, enforcement, detect pattern |
| `CheckSection` | `"checks"` | `CheckDeclaration` | Setup/standalone checks with `on_failure` hint |
| `HintSection` | `"hints"` | `HintDeclaration` | Global hints (phase hints are parsed separately under `phases:`) |

```python
class WorkflowLoader:
    """Reads all manifests, distributes sections to ManifestSection parsers.

    Enforces the organizational pattern: one location (workflows/),
    one format (YAML), one namespace convention (folder_name:id).
    """

    def __init__(self, workflows_dir: Path) -> None:
        self._dir = workflows_dir
        self._sections: list[ManifestSection] = [
            RuleSection(),
            CheckSection(),
            HintSection(),
        ]

    def load(self) -> "WorkflowConfig":
        """Load global + all workflow manifests (all sections).

        1. Read workflows/global.yaml → parse sections with namespace='_global'
        2. Scan workflows/*/<name>.yaml → parse sections with namespace=<name>
        3. Validate all entries via each section parser
        4. Return merged config

        Called at startup and phase transitions — NOT on the hot path.
        """
        ...

    def load_rules_only(self) -> list[Rule]:
        """Load only the rules: sections from all manifests.

        Same discovery + namespacing as load(), but skips checks/hints/phases.
        Called on the guardrail hook hot path (every tool call, ~2.4ms).
        """
        ...

@dataclass
class WorkflowConfig:
    """Everything loaded from all manifests."""
    rules: list[Rule]                           # Global + all workflows, merged
    checks: list[CheckDeclaration]              # Global + all workflows
    hints: list[HintDeclaration]                # Global + all workflows
    workflows: dict[str, WorkflowMeta]          # name → phases + state path
```

**Adding a new system:** Implement `ManifestSection[T]`, register in `WorkflowLoader.__init__`, add field to `WorkflowConfig`. The YAML schema automatically supports the new `key:` section.

**Discovery is structural:** The loader scans `workflows/*/` for subfolders. A folder with `<name>.yaml` = a workflow. No registry file needed. `workflows/global.yaml` is the global manifest.

---

## 4. Content Focus

Content scoping is **attention management (~80% effective)**, not security enforcement. In the 2×2 framing, content focus operates on the advisory layer (quadrants A, B) — the agent receives only the current phase's do's and don'ts.

**Enforced layer (quadrants C, D — hard enforcement, system-level):**

```
workflows/*/state.json
├── Guardrail lock (D): rules scoped to current phase
│   → Agent can't DO wrong-phase actions
├── Gate lock (C): advance_checks must pass
│   → Agent can't ADVANCE without proof
└── Hint lock: hints scoped to current phase
    → Agent gets right-phase guidance
```

**Advisory layer (quadrants A, B — soft, prompt-level):**

```
Content scoping: agent only receives current phase markdown
→ Agent sees only current-phase do's (A) and don'ts (B)
→ Less likely to ATTEMPT wrong-phase actions
→ Reduces guardrail friction (fewer denied actions)
→ Better agent focus and output quality
```

The architecture does not depend on content focus. Even if the agent reads all phase files, the enforced layer (C, D) still prevents wrong-phase actions and enforces gates.

### v1 mechanism

v1 implements prompt-only content focus: the engine serves only the current phase file. The engine's file selection IS the content focus mechanism. No phase-aware read guards.

---

## 5. Integration with Existing Infrastructure

### 5.1 What already exists (unchanged)

| System | Key Components | Impact |
|---|---|---|
| **Hints** | `TriggerCondition`, `HintLifecycle`, `HintSpec`, `HintRecord`, `HintStateStore`, `run_pipeline()` — all in claudechic | Extended with `ActivePhase` on `ProjectState`; phase hints now YAML in manifests |
| **Guardrails** | SDK hook closures in `app.py`, `guardrails/rules.py` | Rules in manifest `rules:` sections; `WorkflowLoader` reads them; SDK hooks evaluate at runtime |
| **Agent system** | Agent folders, `spawn_agent()`, `tell_agent`/`ask_agent` | Each agent gets a folder (`coordinator/`, `composability/`, etc.) inside the workflow directory. Folder name = role type. Contains `identity.md` + per-phase markdown. |
| **Project state** | `ProjectState`, `CopierAnswers`, path utilities | Gains `active_phase: ActivePhase | None` field |

### 5.2 Seams

| Seam | Contract | Direction |
|---|---|---|
| Phase → Guardrails | `workflows/*/state.json` + manifest `rules:` sections | Phase writes state; SDK hooks read rules from manifests and state from state.json |
| Phase → Hints | `ActivePhase` on `ProjectState` | Phase updates state; hint triggers check it |
| Phase → Agent | `engine.current_phase_file` / `engine.get_phase_instructions()` | Pull-based: agent reads from engine; engine does not inject mid-session |
| Check → Phase | `CheckResult` | Checks return results; Phase gates consume them |
| Check → Hints | `CheckFailed` adapter | Bridges `Check` → `TriggerCondition`; failing checks fire as hints at startup |

### 5.3 Agent folder split (v1 — required for phase discovery)

Phase-scoped guardrails need a workflow manifest so phase IDs can be discovered and `phase_block`/`phase_allow` references validated.

```
Before:
  AI_agents/project_team/
    COORDINATOR.md (275 lines, all phases mixed with identity)
    COMPOSABILITY.md, SKEPTIC.md, IMPLEMENTER.md, ...

After:
  workflows/project_team/
    project_team.yaml (rules, phases, checks, hints)
    state.json (current phase state)
    coordinator/
      identity.md (cross-phase: Prime Directive, Key Terms ~30 lines)
      vision.md
      setup.md
      specification.md
      implementation.md
      testing.md
      signoff.md
    composability/
      identity.md
      specification.md
    skeptic/
      identity.md
      specification.md
    implementer/
      identity.md
      implementation.md
      testing.md
```

`AI_agents/` at project root goes away. Each agent has a folder inside the workflow directory. The folder name IS the agent's role type.

Agent prompt = `identity.md` (who you are, always loaded) + current phase markdown if it exists (what to do now).

**Splitting rule:** If removing a section from the old COORDINATOR.md would make any phase file unable to stand alone, that section is cross-phase and stays in `identity.md`.

---

## 6. File Structure

```
submodules/claudechic/claudechic/    # ALL infrastructure code lives in claudechic
  checks/                            # Primitive 1: Check system
    __init__.py                      # Re-exports
    _types.py                        # Check protocol, CheckContext, CheckResult (~40 lines)
    _builtins.py                     # 4 built-in checks + CHECK_REGISTRY dict (~100 lines)

  workflow/                          # Primitive 2: Phase system + unified loading
    __init__.py                      # Re-exports
    _types.py                        # PhaseMeta, ActivePhase, CheckDeclaration, HintDeclaration,
                                     #   AdvanceResult, WorkflowConfig, WorkflowMeta (~60 lines)
    _loader.py                       # WorkflowLoader, ManifestSection protocol, RuleSection,
                                     #   CheckSection, HintSection (~120 lines)
    _engine.py                       # WorkflowEngine: transitions, gate evaluation,
                                     #   per-workflow state.json persistence (~120 lines)

  hints/                             # Hint pipeline (extended)
    _types.py                        # TriggerCondition, HintLifecycle, HintSpec (unchanged)
    _state.py                        # ProjectState gains active_phase field
    _engine.py                       # run_pipeline() (unchanged)
    hints.py                         # Existing hints + CheckFailed adapter (no more PhaseIs
                                     #   or setup check declarations — those are now in YAML)

  guardrails/                        # SDK hook implementation (EXISTING — extended)
    rules.py                         # Rule matching (~80 lines) — ALREADY EXISTS (PoC, simplified)
    hits.py                          # NEW: hit logging to .claude/hits.jsonl (~30 lines)

  app.py                             # _guardrail_hooks(), _show_guardrail_confirm(),
                                     #   PostCompact recovery hook — ALREADY EXISTS (PoC, extended)

template project root/               # Template provides YAML config + content only
  .claude/
    hits.jsonl                       # Append-only log of guardrail hits (runtime artifact)

  workflows/                         # Single home for all workflow config + content (NEW)
    global.yaml                      # GLOBAL manifest: rules, checks, hints (no phases)
    project_team/                    # Project-team workflow
      project_team.yaml              # Manifest: rules, phases, checks, hints
      state.json                     # Current phase state (runtime)
      coordinator/                   # Agent folder — folder name = role type
        identity.md                  # Cross-phase identity (~30 lines)
        vision.md                    # Phase-specific instructions
        setup.md
        specification.md
        implementation.md
        testing.md
        signoff.md
      composability/                 # Agent folder
        identity.md                  # Cross-phase identity (~100 lines)
        specification.md             # Phase-specific if needed
      skeptic/                       # Agent folder
        identity.md
        specification.md
      implementer/                   # Agent folder
        identity.md
        implementation.md
        testing.md
    first-pytest/                    # First tutorial (v1 proof-of-concept)
      first-pytest.yaml              # Manifest: rules, phases, checks, hints
      state.json                     # Current phase state (runtime)
      learner/                       # Tutorial has one agent folder
        identity.md                  # Tutorial agent identity
        write-test.md                # Phase-specific
        run-test.md                  # Phase-specific
```

**Principle:** The template provides only YAML configuration (`workflows/`) and user content (agent identity + phase markdown files). All infrastructure code — Check protocol, WorkflowEngine, WorkflowLoader, ManifestSection, hint pipeline — lives in claudechic. When someone uses the template, they don't copy infrastructure; they just write YAML manifests and agent folders. This follows the same pattern as `chicsession` and `guardrails/` which already live in claudechic.

**What was removed from file structure (SDK hooks replace all of these):**
- `generate_hooks.py` (~2155 lines) — no code generation; SDK hooks evaluate rules at runtime
- `bash_guard.py` (~173 lines) — rule matching in `guardrails/rules.py`
- `write_guard.py` (~185 lines) — rule matching in `guardrails/rules.py`
- `role_guard.py` (~350 lines) — `should_skip_for_role()` in `guardrails/rules.py`
- `phase_guard.py` — phase evaluation built into `should_skip_for_phase()` in `guardrails/rules.py`
- `settings.json` hook entries — SDK hooks registered programmatically
- Session marker system + env vars — per-agent closures with static role

**What was cut from file structure (v1 simplification):**
- `claudechic/checks/_registry.py` → merged into `_builtins.py` (5-line dict doesn't need its own file)
- `claudechic/workflow/_state.py` → merged into `_engine.py` (state persistence is engine implementation detail)
- `claudechic/workflow/_lifecycle.py` → `ShowUntilPhaseComplete` is v2 scope
- `PhaseIs` trigger class → eliminated; phase-scoping is structural (hint under phase = fires during phase)
- `.claude/guardrails/rules.d/` → eliminated; rules live in workflow manifests
- `_workflows.yaml` registry → eliminated; discovery is structural (scan `workflows/*/`)

---

## 7. Concrete Examples

### 7.1 Project-team: implementation → testing transition

**`project_team.yaml` (relevant entries):**

```yaml
- id: implementation
  file: coordinator/implementation.md
  advance_checks:
    - type: manual-confirm
      question: "Are all implementation tasks complete?"
- id: testing
  file: coordinator/testing.md
  advance_checks:
    - type: command-output-check
      command: "pixi run pytest --tb=short 2>&1 | tail -1"
      pattern: "passed"
```

Rules and hints are in the same manifest (`project_team.yaml`):

```yaml
# Rules (in the same file, rules: section)
rules:
  - id: pytest_output                                          # → project_team:pytest_output
    phase_block: ["project-team:testing"]                      # Doesn't fire during testing

  - id: block_new_features                                     # → project_team:block_new_features
    phase_allow: ["project-team:testing", "project-team:signoff"]

# Phase hint (declared under the phase entry)
phases:
  - id: implementation
    hints:
      - message: "Focus on writing code, not running the full test suite"
        lifecycle: show-once
```

On transition from Phase 4 → Phase 5:
1. ManualConfirm gate passes (engine prompts user via TUI, user approves)
2. Phase 4 hints unregistered, Phase 5 hints registered
3. `workflows/project_team/state.json` updated: `phase_id: "testing"`
4. Agent receives `coordinator/testing.md` markdown
5. Rule scoping updates automatically — SDK hook closure reads new `phase_id`, `project_team:pytest_output` now skipped

### 7.2 Setup checks via global manifest

Setup checks fire automatically at session startup — no explicit command needed. Declared in `workflows/global.yaml`:

```yaml
# workflows/global.yaml
checks:
  - id: github_auth                                            # → _global:github_auth
    type: command-output-check
    command: "git ls-remote https://github.com/sprustonlab/claudechic.git HEAD 2>&1 | head -1"
    pattern: "[0-9a-f]{40}"
    on_failure:
      message: "GitHub authentication failed. Run: gh auth login"
      severity: warning
      lifecycle: show-until-resolved
```

Scientist starts a session → `WorkflowLoader` reads `workflows/global.yaml` → engine creates `CheckFailed` → `CommandOutputCheck` runs `git ls-remote` → if it returns a commit hash, check passes, hint doesn't fire → if auth fails, `show-until-resolved` shows warning toast every session until they fix it.

### 7.3 First Pytest tutorial (v1 proof-of-concept)

**`workflows/first-pytest/first-pytest.yaml`:**

```yaml
workflow_id: first-pytest-tutorial
phases:
  - id: write-test
    file: learner/write-test.md
    advance_checks:                          # Ordered: programmatic first, then user
      - type: file-exists-check
        path: "tests/test_example.py"
      - type: file-content-check             # Enforces naming convention programmatically
        path: "tests/test_example.py"
        pattern: "def test_"
      - type: manual-confirm                 # User verifies quality
        question: "Does tests/test_example.py contain a meaningful test?"
    hints:
      - message: "Create tests/test_example.py with a function starting with test_"
        trigger: { type: phase-stuck, threshold_seconds: 120 }
  - id: run-test
    file: learner/run-test.md
    advance_checks:
      - type: command-output-check
        command: "pixi run pytest tests/test_example.py"
        pattern: "passed"
    hints:
      - message: "Run: pixi run pytest tests/test_example.py"
        trigger: { type: phase-check-failed }
```

The pytest block rule (in `workflows/project_team/project_team.yaml`) is suspended during the `run-test` phase:

```yaml
# In project_team.yaml rules: section
  - id: pytest_output                                          # → project_team:pytest_output
    phase_block: ["project-team:testing", "first-pytest-tutorial:run-test"]
```

---

## 8. V1 Scope

### 8.1 Implementation size

| Category | Lines | What's in it |
|---|---|---|
| **SDK hook cleanup** | ~60 net new | Finalize `guardrails/rules.py` (exists), add `hits.py` (~30), add `/compact` recovery SDK hook (~30), remove PoC debug prints |
| **Deleted code** | **−2860** | File-hook infrastructure: `generate_hooks.py` (2155), `bash_guard.py` (173), `write_guard.py` (185), `role_guard.py` (~350), `settings.json` hook entries, session marker system, env vars, `.claude/guardrails/rules.d/` |
| **New infrastructure code** | ~430 | `claudechic/checks/` (~140 — 4 built-in types incl. FileContentCheck + ManualConfirm), `claudechic/workflow/` (~240 incl. engine + loader + ManifestSection), `CheckFailed` adapter (~15), `claudechic/guardrails/hits.py` (~30) — all in claudechic |
| **Moved/restructured content** | ~275 | Agent folder split: COORDINATOR.md (275 lines) → `coordinator/identity.md` (~30 cross-phase) + 7 phase files. Other role files → agent folders (`composability/identity.md`, etc.). `AI_agents/` eliminated. |
| **Tutorial content (markdown + YAML)** | ~175 | First Pytest tutorial files (~125) + tutorial-runner role file (~50) |
| **Tests** | ~250 | Check primitive (~100 — 4 types), WorkflowEngine + phase state (~80), SDK hook integration (~50), CheckFailed adapter (~20) |
| **Net change** | **~−1670** | Massive simplification: SDK hooks replace entire code-generation pipeline |

### 8.2 Risk assessment

| Risk | Probability | Severity | Mitigation |
|---|---|---|---|
| SDK hook regression when deleting file hooks | MEDIUM | MEDIUM | Delete file hooks AFTER SDK hooks are fully wired for all agents; run full test suite |
| Duplicate rule IDs across manifests | LOW | LOW | Structurally prevented by `WorkflowLoader` namespacing; caught at startup validation |
| Phase ID typo in `phase_block`/`phase_allow` | HIGH | LOW | Caught at startup by validation against manifest phase IDs |
| Tutorial YAML validation gap | MEDIUM | LOW | Validate manifest at load time |
| Phase state file not found | MEDIUM | LOW | try/except + default to "no phase" (fail-open) |
| Unknown phase_id at runtime | LOW | LOW | Defensive warning in `should_skip_for_phase()`, non-blocking |
| Agent doesn't follow tutorial engine | LOW | MEDIUM | Precise agent role file + checkpoint guardrail |
| `user_confirm` TUI prompt edge cases | LOW | LOW | Proven in PoC; fail-closed (deny on error) |

### 8.3 Implementation order

1. **WorkflowLoader + ManifestSection protocol** — `ManifestSection[T]` protocol, `RuleSection`, `CheckSection`, `HintSection` implementations, `WorkflowLoader` with structural discovery, `WorkflowConfig` result type. Create `workflows/global.yaml` (global rules + checks). This establishes the unified loading pattern that all subsequent steps use.
2. **Clean up PoC + delete file hooks** — Wire `WorkflowLoader` into `_guardrail_hooks()`. Rules come from manifests instead of `rules.d/`. Add `hits.jsonl` logging via `guardrails/hits.py`. Wire SDK hooks for all agents (per-agent closures). Add SDK `PostCompact` hook for phase recovery (~30 lines). Delete all file-hook infrastructure: `generate_hooks.py`, `bash_guard.py`, `write_guard.py`, `role_guard.py`, `settings.json` hook entries, session marker system, `.claude/guardrails/rules.d/`. This is the GO/NO-GO GATE.
3. **Check primitive + `CheckFailed` adapter** — Check protocol + 4 built-in types (incl. ManualConfirm via TUI `SelectionPrompt`), `CheckFailed` adapter (~15 lines). Setup checks declared in `workflows/global.yaml` `checks:` section.
4. **Agent folder split + `project_team.yaml`** — creates agent folders in `workflows/project_team/` (`coordinator/`, `composability/`, `skeptic/`, `implementer/`, etc.). Each has `identity.md` + per-phase markdown. Manifest references phase files. Rules, phase hints in manifest.
5. **WorkflowEngine + phase state** — engine reads manifests (via `WorkflowLoader`), manages transitions, persists per-workflow `state.json`. Phase validation at startup.
6. **First Pytest tutorial content** — consumes WorkflowEngine (same engine, different manifest in `workflows/first-pytest/`)

---

## 9. V2 Scope (Future)

| Feature | One-line description |
|---|---|
| CompoundCheck (`AnyOf`) | OR semantics for check composition |
| Content focus guards | Phase-aware read guards on phase files |
| Tutorial catalog | Discovery and listing of available tutorials |
| Multi-workflow | Multiple workflows active simultaneously |
| `ShowUntilPhaseComplete` | Phase-aware hint lifecycle |
| Tutorial UI | Presentation layer for tutorial progress |
| Agent-team tutorials | Tutorials that teach multi-agent workflows |

---

## 10. Open Decisions

### 10.1 Resolved

| Decision | Resolution |
|---|---|
| How many primitives? | Two: Check + Phase |
| Phase file = content + config or pure content? | Pure markdown. Config lives in manifest (`project_team.yaml` / `first-pytest.yaml`). |
| Content focus = security or optimization? | Optimization. Prompt-only: engine serves current phase file. |
| Phase ID format? | Bare slug in manifests (`"implementation"`), qualified in rules (`"project-team:testing"`) |
| Phase ID namespace collision? | Qualified IDs (`workflow_id:phase_id`) in `phase_block`/`phase_allow`. Runtime matches `f"{workflow_id}:{phase_id}"` from per-workflow `state.json`. |
| Phase state location? | `workflows/<workflow_name>/state.json` — one per workflow, alongside its manifest. No env var overrides — tests use real path convention with temp project root. |
| `ManualConfirm` implementation? | **System-level in v1.** Engine calls `app._show_manual_confirm(question)` → `SelectionPrompt` in TUI. Same proven pattern as `_show_guardrail_confirm()`. Agent not involved. |
| Standalone check discovery? | `CheckFailed` adapter bridges Check → TriggerCondition. Setup checks declared as YAML in `workflows/global.yaml` `checks:` section. Engine creates `CheckFailed` → `HintSpec` internally. |
| Phase registration? | Structural: `WorkflowLoader` scans `workflows/*/`. Validated at startup against known phase IDs. Default: warn. Strict mode: hard error (CI). |
| Workflow type needed? | No — a workflow is a manifest + directory of markdown files. One WorkflowEngine serves both project-team and tutorials. |
| What stays in identity.md? | Cross-phase content only (Prime Directive, Key Terms). Per-phase instructions go to phase markdown files in the agent folder. |
| Agent folders? | Each agent has a folder inside the workflow directory. Folder name = role type (used in `block_roles`/`allow_roles`). Contains `identity.md` (cross-phase) + per-phase markdown. `AI_agents/` eliminated. No separate `roles/` or `phases/` directories. |
| **Guardrail hook architecture?** | **SDK hooks in claudechic. Rules in workflow manifests (global + per-workflow). `WorkflowLoader` reads them. No file hooks, no `generate_hooks.py`, no `settings.json` entries. claudechic required.** |
| **`user_confirm` mechanism?** | **`{"decision": "block"}` + async `SelectionPrompt` in TUI. NOT `permissionDecision: "ask"` (unverified).** |
| **Rule caching?** | **No mtime caching. Always parse fresh. 2.4ms is fast enough. NFS mtime unreliable on HPC.** |
| **Agent role binding?** | **Per-agent closures with static role captured at creation time. No dynamic lookup.** |
| **Failure mode for broken rules?** | **`workflows/` unreadable: fail-closed (block all). Individual manifest malformed: fail-open (skip manifest, load rest). Individual rule error: fail-open (skip rule, evaluate rest).** |
| **Check composition?** | **`advance_checks` list has AND semantics with short-circuit. Programmatic checks first, `ManualConfirm` last for guidance requiring human judgment.** |

### 10.2 Unresolved (decide during implementation)

| Decision | Options | Notes |
|---|---|---|
| Check registry extensibility | Closed registry (v1) vs. plugin system (v2) | v1: hardcoded 4 types. v2: add registration API |
| `state.json` atomic write | Temp-then-rename vs. file lock | Temp-then-rename matches existing `HintStateStore` pattern |

### 10.3 Known bugs (fix during implementation)

| Bug | Description | Fix |
|---|---|---|
| `.test_runs/` missing from template | `project_team:pytest_output` redirects pytest output to `.test_runs/` but the directory doesn't exist in the copier template. New projects fail on first full test run. | Add `.test_runs/.gitkeep` to the copier template. |

---

## 11. Terminology

| Term | Definition |
|---|---|
| **2×2 Guidance Framing** | Foundational model: Positive/Negative × Advisory/Enforced. The advisory/enforced boundary is about bypassability: can the agent bypass it? All four quadrants evolve across phases. |
| **Advisory guidance (A, B)** | Guidance the agent can bypass. A: do's in markdown. B: don'ts in markdown + `warn`/`log` rules (advisory-via-code). |
| **Enforced guidance (C, D)** | Guidance the agent cannot bypass. C: checkpoints (engine runs checks). D: `deny`/`user_confirm` guardrails (SDK hooks block actions). |
| **Checkpoint (quadrant C)** | Enforced-positive: verify something IS done correctly. `advance_checks` in manifests, run by engine. |
| **Guardrail (quadrant D)** | Enforced-negative: block forbidden actions. Only `deny` and `user_confirm` rules in manifest `rules:` sections. `warn`/`log` are advisory (B). |
| **Workflow** | Umbrella term for any manifest + agent folders. Tutorials, project-team builds, and future systems are all workflows. |
| **Agent folder** | Directory inside a workflow named after the agent's role type (e.g., `coordinator/`, `implementer/`). Contains `identity.md` (cross-phase) + per-phase markdown files. Folder name = role type used in `block_roles`/`allow_roles` and `_guardrail_hooks(agent_role=...)`. |
| **`identity.md`** | Cross-phase agent identity file. Always loaded when the agent is spawned. Contains who the agent IS (Prime Directive, domain principles, vocabulary). |
| **Check** | Protocol: `check(ctx) → CheckResult`. Engine runs checks, not the agent — system-level enforcement (quadrant C). |
| **CheckResult** | Verdict with passed/failed, message, and evidence |
| **CheckFailed** | Adapter: bridges Check → TriggerCondition; fires when a check fails |
| **FileContentCheck** | Built-in check: passes when file content matches a regex pattern |
| **ManualConfirm** | Built-in check: engine prompts user directly via TUI `SelectionPrompt`. For guidance requiring human judgment that can't be transferred to a programmatic check. |
| **Phase** | Named state in a workflow; entry in manifest referencing a markdown file in an agent folder (e.g., `coordinator/implementation.md`) |
| **Phase transition** | Atomic switch from one phase to the next; engine evaluates gate checks before advancing |
| **Phase-scoped guardrail** | Guardrail rule with `phase_block` / `phase_allow` fields in manifest |
| **Phase-scoped hint** | Hint declared under a phase entry in the manifest; fires during that phase |
| **Phase coherence** | Guardrails, gates, hints, and content all derive from per-workflow `state.json` |
| **Phase registry** | Set of valid qualified phase IDs (`workflow_id:phase_id`), parsed from manifest files |
| **Qualified phase ID** | `"workflow_id:phase_id"` format used in `phase_block`/`phase_allow` to avoid namespace collisions |
| **Manifest** | Workflow YAML file named after the folder (e.g., `project_team.yaml`, `first-pytest.yaml`) — defines rules, phases, checks, hints. Global manifest: `workflows/global.yaml`. |
| **Global manifest** | `workflows/global.yaml` — rules, checks, hints that are always active (no phases). Namespace: `_global:`. |
| **WorkflowLoader** | Reads all manifests (global + per-workflow), distributes to `ManifestSection` parsers, enforces namespacing. Returns `WorkflowConfig`. |
| **ManifestSection[T]** | Protocol for parsing one section of a manifest. Implementations: `RuleSection`, `CheckSection`, `HintSection`. |
| **WorkflowConfig** | Merged result from `WorkflowLoader`: `rules`, `checks`, `hints`, `workflows`. |
| **WorkflowEngine** | Single engine class that drives phase transitions for any workflow (project-team or tutorial) |
| **Gate** | Check(s) that must pass before phase transition. Engine evaluates gates — enforced (quadrant C). |
| **Guard** | `phase_block` / `phase_allow` on a rule in a manifest (uses qualified phase IDs) |
| **Content focus** | Agent prompt scoped to current phase file (optimization, not enforcement) |
| **`user_confirm`** | Guardrail enforcement level: SDK hook blocks action via `{"decision": "block"}`, shows `SelectionPrompt` in TUI. User decides. Enforced (quadrant D). |
| **SDK hook** | In-process PreToolUse hook registered via claudechic SDK. Replaces file-based hooks. Per-agent closure with static role. |
| **File hook** | (DELETED) Former architecture: shell scripts in `.claude/hooks/` generated by `generate_hooks.py`, triggered via `settings.json` entries. Replaced entirely by SDK hooks. |
| **`hits.jsonl`** | Append-only log of guardrail hits at `.claude/hits.jsonl`. Each line: `{rule_id, tool_name, timestamp, decision, agent_role}`. Written by `guardrails/hits.py`. |
| **Fail-closed** | On unreadable `workflows/` directory: block all tool calls (safe default) |
| **Fail-open** | On malformed manifest or individual broken rule: skip it, load/evaluate rest (graceful degradation) |
| **Namespace** | Every ID is `namespace:name`. Global = `_global:pip_block`. Workflow = `project_team:close_agent`. No un-namespaced IDs at runtime. |

---

## Appendix: Reference Implementations

### A.1 WorkflowLoader structural discovery (`claudechic/workflow/_loader.py`)

```python
def _discover_workflows(workflows_dir: Path) -> dict[str, Path]:
    """Scan workflows/ for subfolders containing <name>.yaml manifests.

    Returns {workflow_name: manifest_path}.
    Discovery is structural — no registry file needed.
    """
    workflows: dict[str, Path] = {}
    if not workflows_dir.is_dir():
        return workflows
    for subdir in sorted(workflows_dir.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("_"):
            continue
        manifest = subdir / f"{subdir.name}.yaml"
        if manifest.is_file():
            workflows[subdir.name] = manifest
    return workflows
```

### A.2 Phase reference validator (`claudechic/workflow/_loader.py`)

```python
def validate_phase_references(
    config: WorkflowConfig,
    strict: bool = False,
) -> list[str]:
    """Validate that all phase_block/phase_allow qualified IDs exist in known phases.

    Extracts phase IDs from config.workflows, validates rule references.
    Called from app startup after WorkflowLoader.load().
    """
    known_phases: set[str] = set()
    for name, meta in config.workflows.items():
        for phase in meta.phases:
            known_phases.add(f"{meta.workflow_id}:{phase.id}")

    issues: list[str] = []
    for rule in config.rules:
        for field_name in ("phase_block", "phase_allow"):
            referenced = getattr(rule, field_name, [])
            for qualified_id in referenced:
                if ":" not in qualified_id:
                    msg = (
                        f"Rule '{rule.id}' has unqualified phase '{qualified_id}' "
                        f"in '{field_name}'. Use 'workflow_id:phase_id' format."
                    )
                    if strict:
                        raise SystemExit(f"[STRICT] {msg}")
                    _warn(msg)
                    issues.append(msg)
                elif qualified_id not in known_phases:
                    msg = (
                        f"Rule '{rule.id}' references unknown phase '{qualified_id}' "
                        f"in '{field_name}'. "
                        f"Known phases: {sorted(known_phases)}. "
                        f"Check for typos or add the phase to the manifest."
                    )
                    if strict:
                        raise SystemExit(f"[STRICT] {msg}")
                    _warn(msg)
                    issues.append(msg)
    return issues
```

