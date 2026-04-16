# Manual Testing Plan: Sub-Agent Phase Injection (#37)

After restarting claudechic, follow these steps to verify each fix works in a live session.

## Setup

The project-team workflow should already be active. If not, activate it with `/project-team`.

---

## Test 1: prefer_ask_agent rule fires for coordinator

**What it proves:** Main agent role resolves to `coordinator` from `main_role`. Rules with `roles: [coordinator]` fire for the main agent.

1. Spawn a test agent: `spawn_agent name="TestDummy" type="skeptic" prompt="Wait for instructions"`
2. Use `tell_agent` to TestDummy with any message
3. **Expected:** Warning fires -- "Coordinator should use ask_agent, not tell_agent"
4. Use `ask_agent` to TestDummy with any message
5. **Expected:** Goes through clean, no warning

---

## Test 2: no_close_leadership rule blocks close

**What it proves:** Agents cannot be closed before signoff phase.

6. Try to close TestDummy with `close_agent`
7. **Expected:** Blocked with "Do not close agents during active workflow phases"
8. You can acknowledge the warning to override if needed

---

## Test 3: spawn warning when type= omitted

**What it proves:** Coordinator gets warned when spawning without role context.

9. Spawn agent WITHOUT type=: `spawn_agent name="NoTypeAgent" prompt="Just a helper"`
10. **Expected:** Response contains `[WARNING] No type= specified. This agent will not receive role-specific phase instructions.`

---

## Test 4: Phase broadcast to sub-agents

**What it proves:** Typed sub-agents get phase files when the workflow advances.

11. Make sure TestDummy (type="skeptic") is still running
12. Advance phase (e.g., implementation -> testing)
13. **Check TestDummy's chat** -- should show `--- Phase Update: testing ---` followed by skeptic/testing.md content
14. **Check YOUR chat (coordinator)** -- should NOT get a broadcast message (phase content is inline in the advance_phase tool response only)
15. **Check NoTypeAgent** -- should NOT get a broadcast (it has no type=)

---

## Test 5: Name fallback removed

**What it proves:** Agent named like a role folder does NOT get that role's content unless type= is explicitly set.

16. Spawn agent: `spawn_agent name="coordinator" prompt="I am just a helper"`
17. **Check its first message** -- should be ONLY the prompt you gave
18. **Expected:** NO identity.md content prepended (no "You are the coordinator" text)

---

## Expected Results Summary

| Action | Expected Result |
|--------|----------------|
| `tell_agent` from coordinator | Warning: prefer_ask_agent |
| `close_agent` before signoff | Blocked: no_close_leadership |
| `spawn_agent` without type= | Success + [WARNING] in response |
| `advance_phase` with typed agents | Typed agents get phase content |
| `advance_phase` with untyped agents | Untyped agents get nothing |
| Agent named "coordinator" no type= | No identity.md injected |

---

## If something fails

- Check `get_phase` to verify workflow is active and rules are loaded (should show 27+ rules)
- Check `whoami` to see your agent name
- The dynamic role resolution requires a workflow to be active -- rules with `roles: [coordinator]` won't fire if no workflow is activated
