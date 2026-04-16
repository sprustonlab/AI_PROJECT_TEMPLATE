# Skeptic Review: Proposed Fixes for Issue #37

## Fix 1: Guardrail warn on spawn_agent without `type=` during active workflow

### What can go wrong

**Catch-22 risk: LOW but worth noting.** The guardrail triggers on `spawn_agent` when `type` is missing. The coordinator must acknowledge the warning and retry with `type=`. This is two tool calls instead of one, but NOT a catch-22 -- the guardrail doesn't block the operation it requires. It blocks spawn, telling you to add `type=`, then you retry with `type=` and pass. Clean.

**False positives on utility agents.** Not every agent needs a role. A coordinator might spawn a "git-helper" agent to do a one-off task. This agent has no workflow role folder. The guardrail would fire a warning that's meaningless -- there IS no type to provide. The coordinator would have to acknowledge a warning for something that doesn't apply.

**Mitigation:** The guardrail should only warn when role folders actually exist for the active workflow. Or: only warn when the workflow manifest declares sub-agent roles. If this becomes "always warn when type= is missing," it'll generate noise for legitimate utility agents.

### Is there a simpler approach?

Yes. Instead of a guardrail that warns and forces a retry, **claudechic could infer the role from the agent name as a fallback.** But this is fragile (name "Skeptic" vs folder "skeptic", name "skeptic-agent" vs folder "skeptic"). The current `agent_type or name` fallback already attempts this and it's what fails in practice.

Better simple approach: **improve the spawn_agent tool description** to mention that `type` maps to role folders when a workflow is active. The LLM reads tool descriptions. If the description says "type: Agent role folder name. Required during active workflows for phase injection," the coordinator is far more likely to provide it. Zero code change, zero guardrail overhead.

**Verdict: The guardrail is reasonable but the tool description improvement should come first. If that's insufficient, add the guardrail. Don't skip straight to enforcement.**

---

## Fix 2: Phase-transition broadcast on advance_phase

### Critical prerequisite: Agent doesn't store its type

**This is the biggest risk.** I checked `agent.py` -- the `Agent` class has NO `agent_type` field. The type is passed through `_make_options()` into `CLAUDE_AGENT_ROLE` env var and into `assemble_phase_prompt()` at spawn time, then discarded. After spawn, there is no way to look up which role an agent has.

The phase broadcast needs to:
1. Iterate all running agents
2. For each typed agent, call `assemble_phase_prompt(role_name=agent.type, current_phase=new_phase)`
3. Send the result via `_send_prompt_fire_and_forget`

**Step 2 is impossible without storing the type on Agent.** This means the fix requires modifying `Agent.__init__` to accept and store `agent_type`, and modifying `AgentManager.create()` to pass it through. This is a larger change than it appears -- it touches the agent data model.

### Fire-and-forget delivery risks

`_send_prompt_fire_and_forget` creates an async task via `create_safe_task`. This means:

1. **Message ordering is not guaranteed.** If the coordinator also sends instructions after advance_phase, the phase broadcast and coordinator message could arrive in either order. The sub-agent might get "work on implementation" from the coordinator BEFORE it gets the implementation.md phase content.

2. **Agent might be busy.** If the sub-agent is mid-task when the broadcast arrives, it queues behind the current work. The agent finishes its old-phase task, THEN receives the new-phase context. This is actually fine -- `tell_agent` has the same behavior and it works.

3. **Agent client might be None.** The `do_send()` function checks `agent.client is None` and silently skips. If an agent is in a transient disconnected state, the phase broadcast is silently lost. No retry, no error surfacing.

4. **No delivery confirmation.** Fire-and-forget means we don't know if the agent received the message. If it fails, nobody knows. This is the same pattern as `tell_agent` so it's at least consistent, but for something as important as phase context, silent loss is concerning.

### What if a phase file doesn't exist for a role in the new phase?

`_assemble_agent_prompt` handles this gracefully (agent_folders.py line 66-73): if no `{phase}.md` file exists, `phase_content` stays empty and only `identity.md` is returned. If neither exists, empty string is returned, and `assemble_phase_prompt` converts that to `None` (line 102), so no broadcast is sent.

**This is correct behavior.** A role without a phase file for the new phase just gets no broadcast. But there's a subtlety: the agent still has the OLD phase content in its context window. It doesn't get told "you're now in a new phase" -- it just doesn't get new instructions. The agent may continue operating on stale phase assumptions.

**Mitigation:** Even when no phase file exists, send a minimal "Phase advanced to {new_phase}" notification so the agent at least knows the phase changed.

### Double-injection risk

The broadcast sends phase content as a chat message (via `_send_prompt_fire_and_forget`). The coordinator might ALSO tell the sub-agent "we've moved to implementation phase, here's what to do." Now the agent has:
- Phase content from broadcast (system-generated)
- Phase instructions from coordinator (human-authored)

These could contradict. The coordinator's version is later in context, so LLM recency bias means the coordinator's paraphrase wins -- which is exactly the problem we're trying to fix.

**Mitigation:** The broadcast message should be clearly marked as authoritative: "[Phase instructions from workflow system -- these are your primary instructions for this phase]". Or: send it as a system-level injection rather than a chat message if the SDK supports that.

### What about closed/reopened agents?

If an agent is closed and later reopened (`/agent reopen`), does it get phase broadcasts? Reopened agents aren't in the active agent list, so they'd miss transitions that happened while closed. The reopen path would need to re-inject current phase context.

**Verdict: Fix 2 is the most important fix but also the most complex. Prerequisites: (a) store agent_type on Agent, (b) decide on delivery semantics (fire-and-forget is probably fine for now but document the limitation), (c) handle the "no phase file but phase changed" case, (d) address double-injection with clear message framing.**

---

## Fix 3: close_agent guardrail to prevent premature closure

### What can go wrong

**Catch-22 risk: NONE.** The guardrail warns on close_agent, coordinator acknowledges, closes anyway. No circular dependency.

**But what does "premature" mean?** The guardrail needs a condition. Options:
- Warn if agent status is BUSY -- reasonable, but the coordinator might have a good reason to close a stuck agent
- Warn if agent has `_pending_reply_to` set -- means it owes someone an answer. Good signal.
- Always warn -- noisy, coordinator has to acknowledge every close

**Over-protection risk.** If the guardrail is too aggressive, coordinators learn to reflexively acknowledge it. The warning becomes invisible noise. This is worse than no guardrail because it gives false confidence ("we have protection") while providing none.

### Is there a simpler approach?

Instead of a guardrail, **`close_agent` could check if the agent has `_pending_reply_to` and include a warning in the response**: "Warning: this agent has an undelivered reply to {name}. Close anyway? (call close_agent again to confirm)." This is in-band, no guardrail infrastructure needed, and only fires when there's a real risk.

**Verdict: A status-aware warning in close_agent itself is simpler and more precise than a guardrail rule. If a guardrail is used, it should be conditional on agent state (busy or has pending reply), NOT unconditional.**

---

## Fix 4: encoding='utf-8' in agent_folders.py

### What can go wrong

**Nothing.** This is a correctness fix per CLAUDE.md cross-platform rules. Two `read_text()` calls (lines 63, 73) need `encoding='utf-8'`. No behavioral change on Linux/Mac. Prevents `UnicodeDecodeError` on Windows when system encoding isn't UTF-8.

### Edge cases

None. The files are markdown, expected to be UTF-8.

**Verdict: Do it. No risk. Should be included in any PR touching this file regardless of the other fixes.**

---

## Overall Assessment

### Ordered by risk/reward

| Fix | Risk | Reward | Complexity | Do it? |
|-----|------|--------|------------|--------|
| #4 encoding | None | Prevents Windows bugs | Trivial | Yes, immediately |
| #1 spawn guardrail | False positives on utility agents | Better type= usage | Low | Start with tool description fix; guardrail if insufficient |
| #3 close_agent | Over-protection noise | Prevents lost work | Low | Prefer in-band warning over guardrail |
| #2 phase broadcast | Delivery ordering, data model change, double-injection | Fixes the real gap | Medium-High | Yes, but design carefully |

### What's missing from the proposal

1. **Agent.agent_type storage** -- prerequisite for Fix 2 that isn't mentioned
2. **"Phase changed, no new instructions" notification** -- what happens when a role has no file for the new phase
3. **PostCompact hook already exists for phase re-injection** -- does the broadcast interact with it? Could an agent get phase content from broadcast AND PostCompact if both trigger near a phase transition?
4. **Test plan** -- how do we verify the broadcast works? The fire-and-forget pattern makes testing hard. Need to mock or capture the async tasks.
5. **Tool description improvement** -- the simplest fix (update spawn_agent description to mention type=role mapping) isn't listed at all
