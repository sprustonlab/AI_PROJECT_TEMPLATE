# User Alignment: Follow-Up (v2)

**Reviewer:** UserAlignment
**Date:** 2026-04-04

---

## 1. Proposed "User Journey" Section for the Spec

This should be inserted as **Section 1.1** right after the Vision, before the architecture begins. It grounds the reader in what v1 actually feels like to use.

---

### 1.1 User Journey: First Pytest Tutorial (v1)

**Starting a tutorial:**

```
User: /tutorial first-pytest
```

The tutorial-runner agent loads `tutorials/first-pytest/tutorial.yaml`, enters Phase 1, and delivers `phase-01-write-test.md` instructions to the conversation.

**Phase 1 — Write a test:**

```
Agent: "Let's write your first pytest test. Create a file called
        tests/test_example.py with a test function."
User:   (writes the file, or asks the agent for help)
Agent:  (checks: does tests/test_example.py exist?)
        "✓ Test file created. Moving to the next step."
```

If the user is stuck for 2 minutes, a hint appears: *"Create tests/test_example.py with a function starting with test_"*

**Phase 2 — Run the test:**

```
Agent: "Now run your test and make it pass."
User:   (runs pytest, or asks the agent to run it)
Agent:  (checks: does `pixi run pytest tests/test_example.py` output "passed"?)
        "✓ All tests pass. Tutorial complete!"
```

If the check fails, a hint appears: *"Run: pixi run pytest tests/test_example.py"*

**Standalone diagnostics (no tutorial needed):**

```
User: /check-setup
Agent: ✓ SSH key exists
       ✗ git email not configured
       ✓ pixi installed
```

---

## 2. "Team of Agents" — Tracked v2 Item

The user's original request explicitly includes "a team of agents" as a component of the tutorial system:

> *"combines md files, a team of agents, hints, and guardrails in a new mode"*

**v1 scope:** A single tutorial-runner agent guides the user through phases. This is sufficient for the proof-of-concept tutorials (first-pytest, check-setup) where one agent reads instructions and verifies checkpoints.

**v2 scope — Agent-team tutorials:** For complex tutorials (e.g., "creating a first project from the template"), the tutorial system should support spawning a team of specialized agents — e.g., a guide agent explaining concepts, a checker agent verifying steps, a helper agent answering side questions. This maps to the user's vision of agents collaborating to teach.

**Recommended v2 tracking entry:**

| Feature | Description |
|---|---|
| Agent-team tutorials | Tutorials that spawn multiple specialized agents (guide, checker, helper) working together. Required for complex multi-domain tutorials like "create your first project." Addresses user's explicit "team of agents" requirement. |

This should be added to **Section 9 (V2 Scope)** of the spec alongside the existing v2 items.
