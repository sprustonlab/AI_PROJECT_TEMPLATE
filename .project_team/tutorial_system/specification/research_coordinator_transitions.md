# Research: Coordinator Phase Transition Map

**Author:** Researcher
**Date:** 2026-04-04
**Requested by:** Coordinator
**Source:** `AI_agents/project_team/COORDINATOR.md` (275 lines), cross-referenced with role files

---

## How to Read This Map

For each transition, I document:
- **Current trigger** — what COORDINATOR.md says causes the transition today
- **Verifiable?** — can a machine check prove the transition is valid?
- **Check type** — if verifiable, what kind of check
- **Residual** — what remains manual even with checks

---

## Phase 0 → Phase 1a: Vision Approved

**COORDINATOR.md says (line 51):**
> **User Checkpoint 👤:** Present Vision Summary. Loop until approved.

**Current trigger:** User says something that Coordinator interprets as approval. No formal approval signal — Coordinator uses judgment to decide "vision is clear."

**Verifiable?** NO — not machine-verifiable.

**Why:** "Approved" is a natural language signal. The user might say "looks good", "yes", "go ahead", "approved", "👍", or even just "ok." There's no structured approval token. The Coordinator judges intent.

**Check type:** `ManualConfirm` — "Has the user approved the Vision Summary?"

**Residual:** 100% manual. The check adds no value over what already happens — Coordinator already waits for user approval. A ManualConfirm check would just formalize what's already a natural conversation.

**Verdict:** ManualConfirm is appropriate here but adds friction for zero safety gain. The User Checkpoint pattern is already doing the job. **Skip the check for v1.**

---

## Phase 1a → Phase 1b: Working Directory Resolved

**COORDINATOR.md says (lines 59-68):**
> Determine `working_dir` (must be absolute path)... If unclear → ask user

**Current trigger:** Coordinator determines `working_dir` through a 4-option decision tree. Falls through to "ask user" if unclear.

**Verifiable?** YES — partially.

**Check type:** `FileExistsCheck(working_dir)` — does the resolved path exist?

**What the check catches:** Coordinator resolving a path that doesn't exist (e.g., typo in submodule name, wrong monorepo root). This happens when the Coordinator guesses wrong about project location.

**Residual:** Check can't verify the path is the *right* directory, only that it exists.

**Verdict:** Cheap check, real value. Catches a common error where Coordinator resolves a non-existent path and agents fail silently when they try to read/write there.

---

## Phase 1b → Phase 1c: Session Decision Made

**COORDINATOR.md says (lines 73-80):**
> Check if state already exists... "Resume or start fresh?" **User Checkpoint 👤:** Wait for decision.

**Current trigger:** If no existing state → automatic (skip to 1c). If existing state → user decides resume/fresh.

**Verifiable?** PARTIALLY.

**Check type:** Conditional:
- If `.ao_project_team/*/STATUS.md` exists → `ManualConfirm("Resume existing project or start fresh?")`
- If no state exists → automatic (no check needed)

**What the check catches:** Nothing new — this is already a User Checkpoint.

**Verdict:** The "if no existing state → continue" branch is already machine-verifiable: `NOT FileExistsCheck(".ao_project_team/*/STATUS.md")`. The resume branch is inherently manual. **Skip formal check — existing logic is fine.**

---

## Phase 1c → Phase 2: State Directory Initialized

**COORDINATOR.md says (lines 88-136):**
> Create state directory: STATUS.md, userprompt.md, specification/

**Current trigger:** Coordinator creates the files and proceeds. No verification that creation succeeded.

**Verifiable?** YES — fully.

**Check type:** Multiple `FileExistsCheck`:
```
FileExistsCheck("{project_state}/STATUS.md")
FileExistsCheck("{project_state}/userprompt.md")
FileExistsCheck("{project_state}/specification")  # directory
```

**What the check catches:** Silent write failures. On HPC clusters with quotas or permission issues, file creation can fail without the Coordinator noticing (Write tool returns success but the file isn't there, or it was written to wrong path due to relative path resolution).

**Residual:** Check can't verify the *content* is correct (STATUS.md has the right template, userprompt.md has the vision). But existence is the critical gate.

**Verdict:** HIGH VALUE. This is the foundation — every subsequent phase reads from this directory. A missing STATUS.md cascades silently through the entire workflow.

---

## Phase 2 → Phase 3: Leadership Spawned

**COORDINATOR.md says (lines 172-174):**
> VERIFY: Run `mcp__chic__list_agents`. Confirm all 4 Leadership agents appear.
> **GATE:** If all 4 Leadership agents are NOT visible, DO NOT proceed.

**Current trigger:** Coordinator runs `list_agents` and checks the output. This is already a machine-verifiable gate — the Coordinator is instructed to verify, not just proceed.

**Verifiable?** YES — fully.

**Check type:** `CommandOutputCheck("mcp__chic__list_agents", pattern matching 4 agent names)` — but this isn't a shell command, it's an MCP tool call.

**The mismatch:** `CommandOutputCheck` runs shell commands via `subprocess`. But `list_agents` is an MCP tool, not a CLI command. You can't `subprocess.run("mcp__chic__list_agents")`.

**What would actually work:**
```python
@dataclass(frozen=True)
class AgentsSpawned:
    """Check that required agents appear in list_agents."""
    required_agents: tuple[str, ...]

    def check(self, ctx: CheckContext) -> CheckResult:
        # Would need MCP tool access — not available in CheckContext
        ...
```

**Problem:** `CheckContext` has `run_command()` (shell commands) but no MCP tool access. Checking agent spawn status requires either:
1. A file-based proxy: Coordinator writes spawn evidence to STATUS.md, check reads STATUS.md
2. Extending CheckContext with MCP access (violates Check independence)

**The file proxy already exists:** COORDINATOR.md says to record spawn evidence in STATUS.md (lines 176-183). So the check becomes:

```python
# Check STATUS.md contains spawn evidence for all 4
FileContentCheck(
    "{project_state}/STATUS.md",
    pattern=r"Composability: spawned ✓.*TerminologyGuardian: spawned ✓.*Skeptic: spawned ✓.*UserAlignment: spawned ✓"
)
```

**Residual:** STATUS.md could say "spawned ✓" but the agent might have crashed immediately after spawn. The file check trusts Coordinator's record.

**Verdict:** HIGH VALUE. This is already an explicit gate in COORDINATOR.md. Formalizing it as a check makes it enforceable rather than advisory. The file-content proxy is the right approach — it reuses what Coordinator already writes.

---

## Phase 3 → Phase 4: Specification Approved

**COORDINATOR.md says (lines 223-228):**
> **User Checkpoint 👤:** Present specification. Handle response:
> - **Approve** → proceed to Phase 4
> - **Modify** → incorporate feedback, re-present
> - **Redirect** → adjust approach, re-present
> - **Fresh Review** → close Leadership, spawn fresh team, re-review

**Current trigger:** User approval after a multi-turn conversation. Four possible outcomes, only one advances.

**Verifiable?** PARTIALLY.

**Machine-verifiable preconditions (must all pass BEFORE presenting to user):**

```python
# All Leadership agents have reported findings
FileExistsCheck("{project_state}/specification/composability.md")
FileExistsCheck("{project_state}/specification/terminology.md")
FileExistsCheck("{project_state}/specification/skeptic_review.md")
FileExistsCheck("{project_state}/specification/user_alignment.md")
```

**What these checks catch:** Coordinator presenting a "specification" to the user before all Leadership agents have reported. This actually happens — if one agent is slow, Coordinator sometimes proceeds with 3/4 reports.

**Non-verifiable component:** User's approval decision. This is `ManualConfirm`.

**Verdict:** HIGH VALUE for the precondition checks. They prevent premature presentation. The user approval itself stays manual. **Split the gate: machine checks first (all reports filed), then ManualConfirm (user approves).**

---

## Phase 4 → Phase 5: Implementation Complete

**COORDINATOR.md says (lines 232-236):**
> 1. Spawn one Implementer agent per file, up to 6 implementer agents.
> 2. Inform Leadership...
> 3. If Researcher is active → ask Researcher...
> 4. Exit when all Leadership approve.

**Current trigger:** "All Leadership approve" — each Leadership agent reviews the implementation and signals approval via `tell_agent`.

**Verifiable?** PARTIALLY.

**Machine-verifiable preconditions:**

1. **Implementation files exist:** The specification should list which files will be created. After implementation, check they exist.
   ```python
   # Dynamic — files come from the spec, not hardcoded
   # Requires: spec parsing or Coordinator recording expected files
   ```

2. **Tests pass (preliminary):** Could run `pixi run pytest` to verify basic health.
   ```python
   CommandOutputCheck("pixi run pytest --tb=short 2>&1 | tail -1", r"passed")
   ```
   But this is Phase 5's job, not Phase 4's gate.

3. **All Implementers have reported back:**
   ```python
   # Proxy: check STATUS.md for implementation completion records
   # Or: count files in specification/ matching implementation_*.md
   ```

**Non-verifiable component:** "Leadership approve" — this is judgment about code quality, architecture alignment, and user intent. Can't be automated.

**Verdict:** MEDIUM VALUE. The precondition (files exist) is checkable. The approval (Leadership judgment) is manual. **Use ManualConfirm as the gate, with optional file-existence preconditions.**

---

## Phase 5 → Phase 6: Tests Pass

**COORDINATOR.md says (lines 239-241):**
> Spawn TestEngineer. Run tests. Fix failures. Exit when all pass.

**Current trigger:** Coordinator judges that tests pass based on TestEngineer's report.

**Verifiable?** YES — fully.

**Check type:**
```python
CommandOutputCheck(
    "pixi run pytest --tb=short 2>&1 | tail -1",
    r"passed"
)
```

**What the check catches:** Coordinator declaring tests pass when they don't. TestEngineer might report "mostly passing" or "fixed the critical ones" — a machine check is objective.

**Residual:** The check verifies pytest exit, not test quality. Tests could all be `assert True`. But that's a test quality concern, not a gate concern.

**Verdict:** HIGHEST VALUE in the entire workflow. This is the one transition where a machine check is strictly better than agent judgment. pytest's exit code is ground truth.

**Note:** This is the same check the spec uses in its examples. It's real.

---

## Phase 6 → Phase 7: Sign-Off Complete

**COORDINATOR.md says (line 246):**
> All agents confirm READY.

**Current trigger:** Each agent sends `tell_agent("Coordinator", "READY")` or similar.

**Verifiable?** PARTIALLY.

**Machine-verifiable proxy:** Agent messages contain "READY" — but parsing `tell_agent` history isn't possible from CheckContext. File proxy:

```python
# Coordinator records agent confirmations in STATUS.md
FileContentCheck("{project_state}/STATUS.md", r"Sign-Off.*READY")
```

**Non-verifiable component:** Whether agents actually reviewed everything vs. rubber-stamped.

**Verdict:** LOW VALUE as a formal check. The Coordinator already manages this manually. Formalizing it adds bureaucracy without safety.

---

## Phase 7 → Phase 8: Integration Complete

**COORDINATOR.md says (lines 250-251):**
> Create launch script. Test it.

**Current trigger:** Coordinator judges the launch script works.

**Verifiable?** YES — partially.

**Check type:**
```python
# Launch script exists
FileExistsCheck("launch.sh")  # or whatever the script is named

# Launch script runs without error (if safe to execute)
CommandOutputCheck("bash launch.sh --dry-run 2>&1", r"SUCCESS|OK|^$")
```

**Problem:** The launch script name and dry-run behavior are project-specific. Can't hardcode.

**Verdict:** LOW VALUE as a generic check. Would need project-specific configuration. **Skip for v1.**

---

## Phase 8 → Phase 9: E2E Decision Made

**COORDINATOR.md says (lines 254-255):**
> Ask user if E2E tests needed. **User Checkpoint 👤**

**Current trigger:** User decision — yes or no.

**Verifiable?** NO — purely manual.

**Check type:** `ManualConfirm("Are E2E tests needed?")`

**Verdict:** This is inherently a user decision point. ManualConfirm is appropriate but adds nothing over the existing User Checkpoint pattern. **Skip formal check.**

---

## Phase 9 → Done: Final Sign-Off

**COORDINATOR.md says (lines 258-259):**
> Present to user. **User Checkpoint 👤**

**Current trigger:** User says it's done.

**Verifiable?** NO — purely manual.

**Verdict:** Final approval is always human. **Skip formal check.**

---

## Summary: The Transition Map

| Transition | Current Trigger | Machine-Verifiable? | Check Type | Value |
|---|---|---|---|---|
| **0 → 1a** | User approves vision | NO | ManualConfirm | LOW (already a checkpoint) |
| **1a → 1b** | working_dir resolved | YES (path exists) | FileExistsCheck | MEDIUM |
| **1b → 1c** | Session decision | PARTIAL (auto if no state) | FileExistsCheck + manual | LOW |
| **1c → 2** | State dir created | YES | FileExistsCheck × 3 | **HIGH** |
| **2 → 3** | 4 Leadership spawned | YES (via file proxy) | FileContentCheck on STATUS.md | **HIGH** |
| **3 → 4** | Spec approved | PARTIAL (reports filed + user) | FileExistsCheck × 4 + ManualConfirm | **HIGH** (preconditions) |
| **4 → 5** | Leadership approve impl | PARTIAL (files exist + judgment) | FileExistsCheck + ManualConfirm | MEDIUM |
| **5 → 6** | Tests pass | **YES — FULLY** | CommandOutputCheck(pytest) | **HIGHEST** |
| **6 → 7** | Agents confirm READY | PARTIAL (file proxy) | FileContentCheck | LOW |
| **7 → 8** | Launch script works | PARTIAL (project-specific) | FileExistsCheck | LOW |
| **8 → 9** | User decides E2E | NO | ManualConfirm | LOW |
| **9 → Done** | User approves | NO | ManualConfirm | LOW |

---

## What Check Types the Coordinator Actually Needs

### Ordered by frequency of use:

| Check Type | Used In | Count | Notes |
|---|---|---|---|
| **FileExistsCheck** | 1a→1b, 1c→2, 3→4, 4→5 | **~10 instances** | Most common. Checks state files, specification files, implementation files. |
| **ManualConfirm** | 0→1a, 3→4, 4→5, 8→9, 9→Done | **5 transitions** | Every User Checkpoint. But adds little over existing pattern. |
| **CommandOutputCheck** | **5→6 only** | **1 instance** | pytest exit code. The single highest-value check. |
| **FileContentCheck** | 2→3, 6→7 | **2 instances** | STATUS.md contains spawn evidence / READY confirmations. |

### Key insight: FileContentCheck is a gap

The spec defines `FileExistsCheck` and `CommandOutputCheck` but not `FileContentCheck` (check that a file contains a regex pattern). But the Coordinator needs it for:
- Verifying STATUS.md records spawn evidence (Phase 2 → 3)
- Verifying STATUS.md records agent sign-offs (Phase 6 → 7)
- Verifying specification files have real content, not just empty files

`ProjectState` already has `file_contains(relative, pattern)` — the hints system can do this. But the Check primitive can't (CheckContext has `read_file()` + `file_exists()` but no `file_contains()`).

**Recommendation:** Either:
1. Add `FileContentCheck(path, pattern)` as a fourth built-in check type — ~20 lines
2. Or expose `read_file()` in CheckContext and let callers do their own regex (already there)

Option 1 is better — it's a declarative YAML type: `type: file-content-check, path: STATUS.md, pattern: "spawned ✓"`.

---

## The v1 Check Shortlist (Ordered by Value)

Based on real transitions, these are the checks worth implementing in v1:

| Priority | Check | Transition | Why |
|---|---|---|---|
| 1 | `CommandOutputCheck(pytest)` | 5→6 | Only fully machine-verifiable gate. Ground truth. |
| 2 | `FileExistsCheck(STATUS.md, userprompt.md, specification/)` | 1c→2 | Foundation — everything downstream depends on this. |
| 3 | `FileExistsCheck(specification/*.md)` × 4 | 3→4 (precondition) | Prevents premature spec presentation. |
| 4 | `FileContentCheck(STATUS.md, spawn evidence)` | 2→3 | Enforces the existing GATE instruction. |
| 5 | `FileExistsCheck(working_dir)` | 1a→1b | Catches path resolution errors. |
| 6 | `ManualConfirm(spec approved)` | 3→4 (post-precondition) | Formalizes existing User Checkpoint. |

**ManualConfirm adds the least value** — every transition that needs it already has a User Checkpoint in COORDINATOR.md. The check just formalizes what's already happening conversationally.

**FileExistsCheck and CommandOutputCheck handle 80% of verifiable gates.** FileContentCheck handles the remaining 20%.
