# Manual Test Plan

Step-by-step verification of bug fixes and the workflow system.
Run these tests in a generated project (not the template repo).

---

## Prerequisites

```bash
# Generate a test project with everything enabled
copier copy --trust --defaults \
  --data project_name=manual_test \
  --data quick_start=everything \
  --data claudechic_mode=standard \
  --data use_cluster=false \
  --data init_git=true \
  https://github.com/sprustonlab/AI_PROJECT_TEMPLATE manual_test

cd manual_test
source activate
pixi run claudechic
```

---

## Test 1: BUG #1 — Phase MD Inline Delivery

**Old behavior:** `advance_phase` returned only "Advanced to phase: X" with no
instructions. Agents had to separately read the phase file.

**Steps:**
1. In claudechic, activate the project_team workflow:
   ```
   /workflow activate project_team
   ```
2. Call `advance_phase` via MCP (type in the TUI):
   ```
   Advance to the next phase using advance_phase
   ```
3. **VERIFY:** The tool response includes a `--- Phase Instructions ---` section
   with the full content of the phase markdown file (not just "Advanced to phase: vision").
4. **VERIFY:** The instructions contain actionable content (e.g., "Goal: Understand
   what the user wants before any setup" for the vision phase).

**Pass criteria:** Phase instructions appear inline in the advance_phase response.

---

## Test 2: BUG #2 — spawn_agent Type Validation

**Old behavior:** Spawning with a nonexistent type silently created an agent with
no role context.

**Steps:**
1. Ensure a workflow is active (from Test 1, or activate one).
2. Ask Claude to spawn an agent with an invalid type:
   ```
   Spawn an agent with type="nonexistent_role" named "TestInvalid"
   ```
3. **VERIFY:** Error message is returned listing available roles from
   `workflows/project_team/*/identity.md`.
4. Now spawn with a valid type:
   ```
   Spawn an agent with type="coordinator" named "TestCoord"
   ```
5. **VERIFY:** Agent spawns successfully and loads the coordinator identity.

**Pass criteria:** Invalid types are rejected with helpful error; valid types work.

---

## Test 3: BUG #3 — tell_agent Message Preservation

**Old behavior:** Messages sent via `tell_agent` to a busy agent were silently
lost after the interrupt.

**Steps:**
1. Spawn two agents:
   ```
   Spawn agent "Worker1" with type="implementer"
   Spawn agent "Worker2" with type="implementer"
   ```
2. Give Worker1 a task that takes a few seconds (e.g., "Write a Python function
   that calculates Fibonacci numbers with memoization").
3. While Worker1 is still responding, send it a message via tell_agent:
   ```
   Tell Worker1: "After you're done, also add type hints to the function"
   ```
4. Wait for Worker1 to finish its current task.
5. **VERIFY:** Worker1 received and acted on the queued message (it should
   acknowledge the type hints request or incorporate them).

**Pass criteria:** Messages sent to busy agents are queued and delivered after
the agent finishes its current work.

---

## Test 4: BUG #4 — ChicSession TUI Prompt

**Old behavior:** No session management — workflow state was lost between
claudechic restarts.

**Steps:**
1. Start claudechic (if not already running):
   ```bash
   pixi run claudechic
   ```
2. Activate a workflow:
   ```
   /workflow activate project_team
   ```
3. **VERIFY:** TUI prompt appears asking for a session name. Options should
   include:
   - Any existing sessions (if resuming)
   - "New session" with a text input field
4. Select "New session" and enter a name (e.g., "test_session_1").
5. **VERIFY:** `.chicsessions/test_session_1.json` is created in the project
   directory:
   ```bash
   ls -la .chicsessions/
   cat .chicsessions/test_session_1.json
   ```
6. Deactivate the workflow:
   ```
   /workflow deactivate
   ```
7. **VERIFY:** Session name is cleared from the TUI status.

**Pass criteria:** Session file created on activation, persists, cleared on
deactivation.

---

## Test 5: BUG #5 — Post-Compact Hook

**Old behavior:** After `/compact`, the post-compact hook crashed with
"takes 0 positional arguments but 3 were given", losing phase context.

**Steps:**
1. Activate a workflow and advance to a phase with context:
   ```
   /workflow activate project_team
   ```
   Then advance through a couple of phases so there's phase context to preserve.
2. Run `/compact` to trigger context compaction:
   ```
   /compact
   ```
3. **VERIFY:** No error in the output about "takes 0 positional arguments but
   3 were given".
4. **VERIFY:** After compaction, ask the agent what phase it's in:
   ```
   What phase are we currently in?
   ```
   The agent should know its current phase (the post-compact hook should have
   re-injected the phase context).

**Pass criteria:** No crash on compact; phase context preserved after compaction.

---

## Test 6: UX — Message Preview

**Old behavior:** `tell_agent` returned "Message queued for 'AgentName'"
with no preview of what was sent.

**Steps:**
1. Spawn an agent:
   ```
   Spawn agent "Reviewer" with type="skeptic"
   ```
2. Send a message via tell_agent:
   ```
   Tell Reviewer: "Please review the architecture document for completeness"
   ```
3. **VERIFY:** The tool response shows a preview like:
   ```
   -> Reviewer: Please review the architecture document for com...
   ```
   Not just "Message queued for 'Reviewer'".

**Pass criteria:** Tool response includes first ~80 characters of the message.

---

## Test 7: Copier Quick Start Presets

**Steps (run from outside the test project, in a temp directory):**

### 7a: everything mode
```bash
cd /tmp
copier copy --trust --defaults \
  --data project_name=test_everything \
  --data quick_start=everything \
  --data claudechic_mode=standard \
  --data use_cluster=false \
  --data init_git=false \
  /groups/spruston/home/moharb/AI_PROJECT_TEMPLATE test_everything
```
**VERIFY:**
```bash
# All specialist roles present
ls test_everything/workflows/project_team/researcher/identity.md
ls test_everything/workflows/project_team/lab_notebook/identity.md
ls test_everything/workflows/project_team/ui_designer/identity.md

# Tutorial workflows present
ls test_everything/workflows/tutorial_extending/

# Pattern miner present
ls test_everything/scripts/mine_patterns.py
ls test_everything/commands/mine-patterns

# Global config present
ls test_everything/global/rules.yaml
ls test_everything/global/hints.yaml
```

### 7b: empty mode
```bash
copier copy --trust --defaults \
  --data project_name=test_empty \
  --data quick_start=empty \
  --data claudechic_mode=standard \
  --data use_cluster=false \
  --data init_git=false \
  /groups/spruston/home/moharb/AI_PROJECT_TEMPLATE test_empty
```
**VERIFY:**
```bash
# Core roles present (7)
ls test_empty/workflows/project_team/coordinator/identity.md
ls test_empty/workflows/project_team/implementer/identity.md
ls test_empty/workflows/project_team/skeptic/identity.md

# Specialist roles ABSENT
test -d test_empty/workflows/project_team/researcher && echo "FAIL: researcher present" || echo "PASS"
test -d test_empty/workflows/project_team/lab_notebook && echo "FAIL: lab_notebook present" || echo "PASS"

# No global examples
test -f test_empty/global/rules.yaml && echo "FAIL: global rules present" || echo "PASS"
test -f test_empty/global/hints.yaml && echo "FAIL: global hints present" || echo "PASS"

# No pattern miner
test -f test_empty/scripts/mine_patterns.py && echo "FAIL: miner present" || echo "PASS"

# Infrastructure still present
ls test_empty/.claude/guardrails/rules.yaml
ls test_empty/pixi.toml
ls test_empty/activate
```

### 7c: defaults mode
```bash
copier copy --trust --defaults \
  --data project_name=test_defaults \
  --data quick_start=defaults \
  --data claudechic_mode=standard \
  --data use_cluster=false \
  --data init_git=false \
  /groups/spruston/home/moharb/AI_PROJECT_TEMPLATE test_defaults
```
**VERIFY:**
```bash
# Specialist roles present
ls test_defaults/workflows/project_team/researcher/identity.md

# Tutorials ABSENT
test -d test_defaults/workflows/tutorial_extending && echo "FAIL" || echo "PASS: no tutorials"

# Pattern miner ABSENT
test -f test_defaults/scripts/mine_patterns.py && echo "FAIL" || echo "PASS: no miner"

# Global config present
ls test_defaults/global/rules.yaml
```

**Cleanup:**
```bash
rm -rf /tmp/test_everything /tmp/test_empty /tmp/test_defaults
```

**Pass criteria:** Each preset produces exactly the expected set of files.

---

## Test 8: Workflow System E2E

**Steps (in the generated test project):**
1. Start claudechic and activate the project_team workflow:
   ```
   /workflow activate project_team
   ```
2. **VERIFY:** Phases load correctly:
   ```
   What phase are we in? List all available phases.
   ```
   Should show: vision, setup, leadership, specification, implementation, testing, signoff.

3. Spawn a coordinator:
   ```
   Spawn agent "Coord" with type="coordinator"
   ```
4. **VERIFY:** Coordinator loads and reads `workflows/project_team/coordinator/identity.md`.

5. Try to advance past vision without meeting advance checks:
   ```
   Advance to the next phase
   ```
6. **VERIFY:** If the vision phase has a `manual-confirm` advance check, the
   system should block advancement until the user confirms. The response should
   explain what conditions need to be met.

7. Confirm the advance check (approve the phase):
   ```
   I approve advancing past vision
   ```
8. **VERIFY:** System advances to the next phase and delivers phase instructions
   inline (per Test 1).

**Pass criteria:** Phases load, coordinator spawns with identity, advance checks
gate transitions, phase instructions delivered inline.

---

## Summary Checklist

| Test | Bug/Feature | Status |
|------|------------|--------|
| 1 | Phase MD inline delivery | [ ] |
| 2 | spawn_agent type validation | [ ] |
| 3 | tell_agent message preservation | [ ] |
| 4 | ChicSession TUI prompt | [ ] |
| 5 | Post-compact hook | [ ] |
| 6 | Message preview UX | [ ] |
| 7 | Copier quick_start presets | [ ] |
| 8 | Workflow system E2E | [ ] |
