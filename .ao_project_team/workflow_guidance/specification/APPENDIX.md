# Appendix

> Supporting material: risk register, worked examples, future scope, and deferred optimizations.

---

## NFS Performance Strategy

Rules are loaded fresh on every tool call. No mtime caching — NFS is unreliable on HPC clusters.

**Cost analysis:** ~2 small YAML files, ~0.5ms each for `yaml.safe_load`. Accept the I/O cost for simplicity.

**Day-one optimization — compiled regex cache:**
```python
_REGEX_CACHE: dict[str, re.Pattern[str]] = {}

def cached_compile(pattern: str) -> re.Pattern[str]:
    """Compile regex with caching. Safe for concurrent reads."""
    if pattern not in _REGEX_CACHE:
        _REGEX_CACHE[pattern] = re.compile(pattern)
    return _REGEX_CACHE[pattern]
```

**If optimization is needed later (priority order):**
1. Content hash cache (SHA256 before parsing — marginal gain)
2. Lazy section parsing (breaks single-path principle — last resort)

---

## Future MCP Tools

### 1. `get_workflow_info`

```python
@server.tool()
async def get_workflow_info() -> dict:
    """Return full workflow state as a dict."""
```

**Returns:** `workflow_id`, `current_phase`, list of all phase IDs, active `advance_checks` for current phase, workflow manifest path.

**Why:** Agents that need situational awareness beyond just the phase name — e.g., understanding what gates the next transition or which phases remain.

---

### 2. `set_phase`

```python
@server.tool()
async def set_phase(phase_id: str) -> str:
    """Manually set the current phase, bypassing advance_checks."""
```

**Behavior:** Engine updates `self._current_phase` directly and persists via chicsession. Logs a warning that advance_checks were skipped.

**Why:** Debugging, recovery, or manual intervention — e.g., rolling back to a previous phase after discovering an issue, or skipping a gate during development.

---

### 3. `list_phases`

```python
@server.tool()
async def list_phases() -> list[dict]:
    """Return all phases in the active workflow."""
```

**Returns:** List of `{"id": str, "has_advance_checks": bool}` for each phase.

**Why:** Agents can understand the workflow structure without reading the manifest YAML — useful for coordinators planning work or reporting progress.

---

### 4. `list_checks`

```python
@server.tool()
async def list_checks(phase_id: str | None = None) -> list[dict]:
    """Return advance_checks for a phase (default: current phase)."""
```

**Returns:** List of `{"type": str, "params": dict, "last_result": "pass" | "fail" | "not_run"}` for each check.

**Why:** Debugging why a phase advance is blocked — see exactly which checks exist and their last known status.

---

### 5. `run_check`

```python
@server.tool()
async def run_check(check_index: int, phase_id: str | None = None) -> dict:
    """Run a single advance_check by index and return the CheckResult."""
```

**Returns:** `{"passed": bool, "evidence": str}`.

**Why:** Debug individual checks without triggering a full phase advance — useful when one check in an AND-chain is failing and you want to iterate on fixing it.

---

## Future Hint Lifecycles

### 6. `show-until-phase-complete`

**Problem it solves:** Some hints are relevant for the duration of a phase but should automatically disappear when the phase advances. Currently, `show-once` fires once and is gone (too brief), and `show-until-resolved` requires an explicit check to pass (requires authoring a check just to suppress a hint). There's no lifecycle that says "keep showing this hint while we're in phase X, stop when we leave."

**Desired behavior:**
- Hint is shown on every evaluation cycle while the current phase matches the phase it was declared in
- When the engine advances to the next phase, the hint is automatically suppressed — no check needed
- If the workflow rolls back to the phase, the hint reactivates

**Example use case:**
```yaml
phases:
  - id: implementation
    hints:
      - message: "Run tests after every code change"
        lifecycle: show-until-phase-complete
```

This hint reminds the user throughout the implementation phase but stops once the team advances to testing (where running tests is already the primary activity).

**Why deferred:** Requires the hints pipeline to be phase-aware — `should_show()` would need access to the engine's current phase. In v1, the hints pipeline is phase-agnostic (it receives pre-filtered `HintSpec` objects). Adding phase awareness means either passing phase state into the lifecycle evaluator or having the engine pre-filter before calling `run_pipeline()`. Both are tractable but add coupling that v1 avoids.

**Implementation sketch (v2):**
- Add `source_phase: str | None` field to `HintSpec` (set by `PhasesParser` for phase-nested hints)
- New lifecycle class: `ShowUntilPhaseComplete.should_show(hint_id, state)` returns `True` when `engine.get_current_phase() == hint.source_phase`
- The engine passes current phase into `run_pipeline()` as context, or the lifecycle queries it via a callback

---

## Risk Register

### R1: NFS Performance on Every Tool Call

**Risk:** Multi-manifest loading (2+ files, 4+ NFS ops) on every `PreToolUse` hook invocation. Existing code logs warnings >5ms.

**Severity:** Medium.

**Mitigation:** Accept I/O cost for small YAML files (~0.5ms each). Regex cache from day one. Profile before adding complexity. If optimization needed: content hash cache → lazy section parsing (last resort). Note: manifests are fully parsed at startup (and on `/workflow reload`); the per-tool-call I/O cost is for live rule edits only, not full manifest discovery.

### R2: Folder-Name Coupling

**Risk:** Folder name = identity ties together manifest filename, namespace, agent folder names, and role type. Renaming requires coordinating multiple locations.

**Severity:** Medium.

**Mitigation:** `workflow_id` in YAML is source of truth for namespace. Folder name is convention. Loader validates that folder names match manifest `workflow_id` at startup where possible.

### R3: Pull-Based Content Delivery Staleness

**Risk:** Phase transitions triggered by coordinator won't be noticed by other agents until they next query via `get_phase` MCP tool. Agents may operate under stale phase guidance.

**Severity:** Medium.

**Mitigation:** Design accepts this — pull-based is intentional. Agents receive phase context at spawn time. The coordinator uses `tell_agent` to notify agents of transitions. Agents can call `get_phase` MCP tool to re-check. PostCompact hook restores context after `/compact`.

### R4: ManualConfirm TUI Coupling

**Risk:** ManualConfirm is the only check requiring user interaction — breaks "checks are pure" mental model.

**Severity:** Low (mitigated by design).

**Mitigation:** Callback injection. ManualConfirm receives `AsyncConfirmCallback` at construction. Never sees TUI, app, or widgets. Swap test passes (CLI, test, web UI all work with different callbacks).

### ~~R5: `warn` Enforcement Infinite Loop~~ — RESOLVED

Eliminated by the unified one-time token mechanism. `warn` rules block the tool call; the agent calls `acknowledge_warning` MCP tool (stores token), then retries. The hook's `consume_override()` callback (backed by `OverrideTokenStore.consume()`) detects and consumes the token. Per-command scoping means no session state, no loop risk — each invocation is independently evaluated.

### R6: Silent Rule Loss on Parse Error

**Risk:** YAML syntax error in a `global/*.yaml` file silently drops those global rules. No protection, no notification.

**Severity:** Medium.

**Mitigation:** Prominent warning/hint when a manifest fails to parse. `LoadResult.errors` is always checked. Fail-closed only for `global/` or `workflows/` directory unreadable. Individual manifest failures logged loudly.

### ~~R7: NFS Atomic Write Visibility~~ — REMOVED

Eliminated by moving persistence to chicsession. The session system handles its own I/O; the engine has no direct file writes.

### R8: hints/ Package Name Collision

**Risk:** `claudechic/hints/` vs template-side `hints/` — different systems, similar names.

**Severity:** Low.

**Mitigation:** Different import paths: `claudechic.hints` vs dynamic load of `{project}/hints`. No collision at Python level. Migration absorbs template-side infrastructure in one step.

### R9: PostCompact Hook SDK Protocol

**Risk:** The PostCompact hook return value format (`phase_context` key) is speculative. SDK may not support context injection this way.

**Severity:** Medium.

**Mitigation:** Verify SDK docs/source for PostCompact hook protocol before implementing. Fallback: write to a file that the SDK's system prompt mechanism reads, or use SystemMessage injection.

### ~~R10: Corrupted state.json Recovery~~ — REMOVED

Eliminated by moving persistence to chicsession. Session system manages its own integrity.

### R11: Single Point of Failure (Engine Process)

**Risk:** In-memory phase state is lost if the engine process crashes.

**Severity:** Low — if the app crashes, all agents die anyway (they run as subprocesses). Chicsession auto-save on every phase transition (~6 writes per workflow run) ensures session resume loses at most the in-progress phase transition.

**Mitigation:** `persist_fn` fires on every successful phase transition, saving `engine.to_session_state()` to `Chicsession.workflow_state`. On session resume, `WorkflowEngine.from_session_state()` restores the last persisted phase.

### R12: Agent `get_phase` MCP Tool Call Cost

**Risk:** Agents must make an MCP tool call to query the current phase, adding latency compared to a direct file read.

**Severity:** Low — agents rarely poll mid-task. Phase is injected into the agent prompt at spawn time. The `get_phase` MCP tool is only needed if an agent wants to re-check the phase after a transition it wasn't notified about.

**Mitigation:** Engine's `get_current_phase()` is an in-memory attribute lookup — the MCP call overhead is the transport only, no I/O.

---

## Examples

### Example 1: Full `project_team.yaml` Manifest

```yaml
# workflows/project_team/project_team.yaml
workflow_id: project-team

rules:
  - id: pytest_output
    trigger: PreToolUse/Bash
    enforcement: deny
    phases: [testing]
    detect: { pattern: '(?:^|&&|\|\||;|\brun\s+)\s*pytest\b', field: command }
    message: "Redirect pytest output to .test_runs/"

  - id: close_agent
    trigger: PreToolUse/mcp__chic__close_agent
    enforcement: deny
    phases: [specification]
    roles: [implementer]
    message: "Close agent during specification — user approval required."

  - id: force_push_warn
    trigger: PreToolUse/Bash
    enforcement: warn
    detect: { pattern: 'git\s+push\s+.*--force', field: command }
    message: "Force push detected — verify this is intentional."

  - id: tool_usage_tracking
    trigger: PreToolUse/Bash
    enforcement: log
    detect: { pattern: '\b(curl|wget)\b', field: command }
    message: "Network tool usage detected."

phases:
  - id: vision
    file: coordinator/vision.md
  - id: setup
    file: coordinator/setup.md
  - id: specification
    file: coordinator/specification.md
  - id: implementation
    file: coordinator/implementation.md
    advance_checks:
      - type: manual-confirm
        question: "Are all implementation tasks complete?"
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

**After loading, rule IDs become:**
- `project-team:pytest_output` (deny)
- `project-team:close_agent` (deny)
- `project-team:force_push_warn` (warn)
- `project-team:tool_usage_tracking` (log)

**Note:** `pip_block` is in `global/rules.yaml` only (as `global:pip_block`), not duplicated here.

**Phase IDs become:**
- `project-team:vision`, `project-team:setup`, ..., `project-team:signoff`

### Example 2: `global/` Directory with Rules and Setup Checks

```yaml
# global/rules.yaml — bare list, section inferred from filename
- id: pip_block
  trigger: PreToolUse/Bash
  enforcement: deny
  detect: { pattern: '\bpip\s+install\b', field: command }
  message: "Use pixi, not pip."
```

```yaml
# global/checks.yaml — bare list, section inferred from filename
- id: github_auth
  type: command-output-check
  command: "git ls-remote https://github.com/sprustonlab/claudechic.git HEAD 2>&1 | head -1"
  pattern: "[0-9a-f]{40}"
  on_failure:
    message: "GitHub authentication failed. Run: gh auth login"
    severity: warning
    lifecycle: show-until-resolved

- id: cluster_ssh
  type: command-output-check
  when: { copier: use_cluster }
  command: "ssh -o ConnectTimeout=5 -o BatchMode=yes ${cluster_ssh_target} hostname 2>&1"
  pattern: "^[a-zA-Z]"
  on_failure:
    message: "Cannot SSH to cluster. Run: ssh-copy-id ${cluster_ssh_target}"
    severity: warning
    lifecycle: show-until-resolved
```

Global files are bare YAML lists — the loader infers the section key from the filename stem (`rules.yaml` → `rules` parser, `checks.yaml` → `checks` parser). All files in `global/` share the `global` namespace. **After loading, IDs become:** `global:pip_block`, `global:github_auth`, `global:cluster_ssh`.

**At startup:** Engine runs all setup checks (no short-circuit). `github_auth` runs always. `cluster_ssh` runs only if `use_cluster` is truthy in copier answers. Failures produce hints via CheckFailed adapter with `show-until-resolved` lifecycle.

### Example 3: Phase Transition Walkthrough

Coordinator decides implementation is done, calls the `advance_phase` MCP tool:

1. **MCP tool `advance_phase` invoked** — engine determines current phase is `project-team:implementation`, next is `project-team:testing`.

2. **Engine reads advance_checks for `implementation` phase:**
   ```yaml
   advance_checks:
     - type: manual-confirm
       question: "Are all implementation tasks complete?"
   ```

3. **Engine builds check:** `ManualConfirm(question="Are all implementation tasks complete?", confirm_fn=<callback>)`

4. **Engine calls `check.check()`:**
   - Callback fires → SelectionPrompt appears in TUI
   - User sees: `✅ Check: Are all implementation tasks complete?` with Yes/No options

5. **User selects "Yes":**
   - `CheckResult(passed=True, evidence="User confirmed")`
   - All checks passed (only one in this case)

6. **Engine updates in-memory state + persists via chicsession:**
   ```python
   self._current_phase = "project-team:testing"  # In-memory — authoritative
   self._persist_fn()  # → session.workflow_state = engine.to_session_state(); manager.save(session)
   ```

7. **MCP tool returns `{"success": true, "phase": "testing"}`** — coordinator notifies other agents via `tell_agent`. Next hook evaluation calls `engine.get_current_phase()` (in-memory) and evaluates phase-scoped rules against `project-team:testing`.

8. **If user had selected "No":**
   - `CheckResult(passed=False, evidence="User declined")`
   - Short-circuit: phase transition blocked
   - If `on_failure` configured, hint fires via CheckFailed adapter
   - MCP tool returns `{"success": false, "reason": "Advance checks failed"}`
   - Coordinator remains in `implementation` phase

### Example 4: Phase-Scoped Rule Evaluation

Rule from manifest (in `project_team.yaml`):
```yaml
- id: pytest_output
  trigger: PreToolUse/Bash
  enforcement: deny
  phases: [testing]
  detect: { pattern: '(?:^|&&|\|\||;|\brun\s+)\s*pytest\b', field: command }
  message: "Redirect pytest output to .test_runs/"
```

After loading, the bare `testing` is qualified to `project-team:testing`.

**Current phase: `project-team:implementation`** — agent runs `pytest`:

1. Trigger match: `PreToolUse/Bash` ✅
2. Role skip: no `roles`/`exclude_roles` → no skip
3. Phase skip: `phases: ["project-team:testing"]` (qualified at load time) — current phase is `project-team:implementation`, NOT in `phases` → **skip** ✅
4. Rule does NOT fire. `pytest` runs normally.

**Current phase: `project-team:testing`** — agent runs `pytest`:

1. Trigger match: `PreToolUse/Bash` ✅
2. Role skip: no restrictions → no skip
3. Phase skip: `phases: ["project-team:testing"]` — current phase IS in `phases` → **does not skip**
4. Detect match: `pytest` matches pattern ✅
5. Hit logged: `HitRecord(rule_id="project-team:pytest_output", outcome="blocked", ...)`
6. Enforcement: `deny` → `{"decision": "block", "reason": "Redirect pytest output to .test_runs/\nTo request user override: request_override(rule_id=\"project-team:pytest_output\", tool_name=\"Bash\", tool_input={...})"}`

Rule for `close_agent` with `phases` and `roles` (in `project_team.yaml`):
```yaml
- id: close_agent
  trigger: PreToolUse/mcp__chic__close_agent
  enforcement: deny
  phases: [specification]
  roles: [implementer]
```

After loading, `specification` is qualified to `project-team:specification`.

**Agent: implementer, phase: specification** — calls `close_agent`:
1. Trigger: `PreToolUse/mcp__chic__close_agent` ✅
2. Role: `roles: [implementer]` — agent IS implementer → does not skip
3. Phase: `phases: ["project-team:specification"]` (qualified at load time) — current phase IS in `phases` → does not skip
4. No detect pattern → fires
5. Enforcement: `deny` → block with message: "Close agent during specification — user approval required.\n\nTo request user override: request_override(rule_id=\"project-team:close_agent\", tool_name=\"mcp__chic__close_agent\", tool_input={...})"
6. Agent calls `request_override(rule_id="project-team:close_agent", tool_name="mcp__chic__close_agent", tool_input={...})` → user sees exact command in SelectionPrompt → if approved, one-time token stored → agent retries exact same command → token consumed → allowed through

**Agent: coordinator, phase: specification** — calls `close_agent`:
1. Trigger: ✅
2. Role: `roles: [implementer]` — agent is coordinator, NOT in roles → **skip** ✅
3. Rule does NOT fire.

### Example 5: Hook Closure Code

```python
# At agent spawn time (e.g., spawning an "implementer" agent):

# 1. app._make_options() calls _merged_hooks(agent_type="implementer")
# 2. _merged_hooks calls create_guardrail_hooks() (evaluates all rules, all enforcement levels):

hooks = create_guardrail_hooks(
    loader=app._manifest_loader,       # Shared instance (parsers registered once at app init)
    hit_logger=app._hit_logger,        # Shared instance (audit trail)
    agent_role="implementer",          # Captured in closure
    get_phase=app._workflow_engine.get_current_phase,  # In-memory lookup, no I/O
    get_active_wf=lambda: app._workflow_engine.workflow_id if app._workflow_engine else None,
    consume_override=app._token_store.consume,  # Per-command tokens (app-level, not engine-level)
)

# 3. The returned hooks dict contains a PreToolUse hook.
# 4. On every tool call by this agent, the hook closure:
#    a. Calls loader.load() — reads manifests fresh (no mtime cache — NFS safe)
#    b. Filters rules by active workflow namespace (global rules always evaluate)
#    c. Evaluates each rule with agent_role="implementer"
#    d. Rules with exclude_roles=["implementer"] are skipped
#    e. Rules with roles=["implementer"] always fire for this agent
#    f. Phase from get_phase() — in-memory engine attribute, no file I/O

# The closure captures loader + hit_logger + agent_role + get_phase + get_active_wf + consume_override.
# Different agents get different closures with different roles,
# but share the same loader, hit_logger, and engine callbacks.
```

### Example 6: Manifest Discovery

Given this file tree:
```
global/
  rules.yaml
  checks.yaml
  hints.yaml
  .notes.yaml                  # Hidden — ignored
workflows/
  project_team/
    project_team.yaml
    coordinator/
      identity.md
      ...
  another_workflow/
    another_workflow.yaml
  .hidden/
    hidden.yaml
  project_team/
    notes.txt                 # Not a manifest (wrong name)
```

`discover_manifests(Path("global/"), Path("workflows/"))` returns:
```python
[
    Path("global/checks.yaml"),                              # 1. Global first, alphabetical
    Path("global/hints.yaml"),                               # 2. Global, alphabetical
    Path("global/rules.yaml"),                               # 3. Global, alphabetical
    Path("workflows/another_workflow/another_workflow.yaml"), # 4. Workflows, alphabetical
    Path("workflows/project_team/project_team.yaml"),        # 5. Workflows, alphabetical
]
```

**Ignored:**
- `global/.notes.yaml` — starts with `.`
- `workflows/.hidden/` — starts with `.`
- `notes.txt` — not a manifest (filename doesn't match parent directory)

**Namespaces assigned:**
- All `global/*.yaml` files → `global`
- `another_workflow.yaml` → value of `workflow_id` field, fallback to `another_workflow`
- `project_team.yaml` → value of `workflow_id` field (e.g. `project-team`), fallback to `project_team`

**Workflow commands registered** (assuming both parse cleanly):
- `/project-team` — activates the project-team workflow
- `/another-workflow` — activates the another-workflow workflow
- `/workflow list` — shows: `project-team (valid), another-workflow (valid), none active`

### Example 7: Phase Reference Validation

```yaml
# workflows/project_team/project_team.yaml
workflow_id: project-team

rules:
  - id: bad_ref
    trigger: PreToolUse/Bash
    enforcement: deny
    phases: [nonexistent]                    # ← references unknown phase (bare name)
    message: "This rule has a bad phase reference"

  - id: good_ref
    trigger: PreToolUse/Bash
    enforcement: deny
    phases: [testing]                        # ← valid phase reference (bare name)
    message: "This rule is correctly scoped"

phases:
  - id: implementation
    file: coordinator/implementation.md
  - id: testing
    file: coordinator/testing.md
```

**After loading:**
- Known phases: `project-team:implementation`, `project-team:testing`
- Rule `project-team:bad_ref` has `phases: ["project-team:nonexistent"]`
- Validation produces:
  ```
  LoadError(source="validation", section="rules", item_id="project-team:bad_ref",
            message="unknown phase ref 'project-team:nonexistent' in phases")
  ```
- The rule still loads (fail-open) but `phases` filter is vacuously false for `project-team:nonexistent` — the rule never activates on phase grounds
- Rule `project-team:good_ref` validates cleanly
