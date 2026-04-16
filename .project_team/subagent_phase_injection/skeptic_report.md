# Skeptic Report: Sub-agent Phase Injection (Issue #37)

## TL;DR

The issue description is **partially wrong**. spawn_agent DOES try to inject phase markdown at spawn time -- the code exists at mcp.py lines 268-289. But the injection is fragile and can silently fail. The real gap is **phase transitions**: when the workflow advances, sub-agents get nothing. Two separate problems, not one.

---

## Finding 1: spawn_agent Already Attempts Injection

The issue says phase markdown is "never delivered." This is inaccurate. `mcp.py` `_make_spawn_agent` (line 268-289) does this:

```python
if _app._workflow_engine:
    folder_prompt = assemble_phase_prompt(
        workflows_dir=Path.cwd() / "workflows",
        workflow_id=_app._workflow_engine.workflow_id,
        role_name=agent_type or name,  # <-- KEY LINE
        current_phase=_app._workflow_engine.get_current_phase(),
    )
    if folder_prompt:
        full_prompt = f"{folder_prompt}\n\n---\n\n{prompt}"
```

**This code prepends identity.md + phase.md to the coordinator's prompt.** So if it works, the sub-agent DOES get phase context at spawn time.

### Why it can fail silently

1. **`agent_type or name` fallback**: If coordinator doesn't pass `type` param, `agent_type` is None, so it falls back to `name`. If the agent is named "Skeptic" but the folder is "skeptic", or "skeptic-agent" vs "skeptic" -- no match, silent None return.

2. **Bare `except Exception` swallows errors** (line 286-289): Any failure in `assemble_phase_prompt` is caught, logged at DEBUG level, and ignored. The agent gets spawned without phase context and nobody knows.

3. **No encoding param on `read_text()`** (agent_folders.py line 63, 73): `identity_path.read_text()` and `phase_path.read_text()` lack `encoding='utf-8'`. This is a cross-platform bug per CLAUDE.md rules and could cause failures on Windows.

### Evidence assessment

The JSONL analysis that found "skeptic/specification.md content never appears" is consistent with the coordinator not passing `type="skeptic"` on the spawn call. The code path exists but the coordinator doesn't know to use it -- the `type` parameter is undocumented in the coordinator's instructions and easy to omit.

**Verdict: The injection mechanism exists but is unreliable. The issue should say "phase markdown injection is fragile and frequently fails" not "never delivered."**

---

## Finding 2: Phase Transitions Are Completely Unhandled for Sub-agents

This is the **real bug**. When `advance_phase` runs (mcp.py line 793-878):

1. Phase prompt is assembled for the **main_role only** (line 846-856)
2. `_inject_phase_prompt_to_main_agent` writes `.claude/phase_context.md` -- which only the coordinator reads (line 865-866)
3. There is NO mechanism to notify sub-agents of phase changes

So even if a sub-agent was correctly injected at spawn, when the phase advances from "specification" to "implementation", the sub-agent stays on stale phase instructions forever (or until `/compact` triggers the PostCompact hook, which does re-inject -- but only for that agent's original role).

**Verdict: This is a real gap. Sub-agents are spawn-and-forget with respect to phase transitions.**

---

## Finding 3: The `close_agent` Problem

The STATUS.md mentions premature agent closure. Looking at `close_agent` (mcp.py line 602-644):

- No guardrails prevent the coordinator from closing agents at any time
- An agent cannot close itself (line 619) -- good
- Cannot close the last agent (line 622) -- good
- But there's no check for: "is this agent busy?", "has this agent completed its task?", "did we receive its output?"

**Risk**: Coordinator spawns skeptic, skeptic starts working, coordinator gets impatient and closes it before results arrive. This is a behavioral problem, not a code bug -- guardrails could address it.

**Verdict: Premature closure is real but behavioral. A `close_agent` guardrail warning is appropriate.**

---

## Risk Analysis of Fix Directions

### Direction 1: Guardrail-only fix

**What it does**: Warn coordinator to include phase markdown when spawning.

**Risks**:
- Coordinator can `acknowledge_warning` and ignore it -- the warning becomes noise
- Doesn't fix the phase transition gap at all
- Relies on the coordinator to correctly paraphrase phase content (the original problem)
- Adds friction to every spawn call

**Verdict: Insufficient as sole fix. Coordinator-authored prompts are the problem; a warning saying "include the content" still relies on the coordinator to do it right.**

### Direction 2: claudechic auto-injection (strengthen existing code)

**What it does**: Make spawn_agent injection reliable + add phase transition broadcasts.

**Risks**:
- **Double injection**: If the coordinator ALSO includes phase content in its prompt AND claudechic prepends it, the sub-agent gets duplicate instructions. The current code already prepends, so this is already a risk. Mitigation: document that claudechic handles injection, coordinator should not duplicate.
- **Agent type mismatch**: If `type` doesn't match a folder name, validation already exists (mcp.py line 206-226) and returns an error. This is good.
- **Utility agents without role folders**: If `type` is not provided, `agent_type` is None, and the code falls back to `name`. If no folder matches, `assemble_phase_prompt` returns None and no injection happens. **This is correct behavior** -- generic agents shouldn't get role context.
- **Phase transition broadcast to busy agents**: Sending a phase update to an agent mid-task could confuse it. Should we interrupt or queue? `tell_agent` queues behind current work -- this is the safer choice.
- **Stale agents**: An agent spawned in phase 1 that's still running in phase 3 gets broadcast for phase 2 and 3. Is that useful or confusing?

**Verdict: Best direction, but needs careful design for phase transitions. The spawn-time fix is straightforward (make `type` param more prominent, fix encoding). Phase broadcast is more complex.**

### Direction 3: Workflow-level fix

**What it does**: Restructure project-team workflow to handle context delivery.

**Risks**:
- Only fixes one workflow, not the general mechanism
- Puts the burden on workflow authors to solve a platform problem

**Verdict: Wrong layer. This is a platform responsibility.**

### Direction 4: Hybrid

**What it does**: Auto-inject via claudechic + guardrail for close_agent.

**Verdict: Best approach. claudechic handles the mechanical injection (it already tries to), guardrails handle the behavioral problems (premature closure).**

---

## Edge Cases to Watch

1. **Agent spawned with no `type` and a name that happens to match a role folder**: Gets injection it didn't ask for. Low risk since the fallback `agent_type or name` is intentional, but could surprise.

2. **Phase advances while sub-agent is being spawned**: Race condition between `advance_phase` and `spawn_agent`. The agent could get phase N instructions at spawn but phase N+1 is already active. The spawn code reads current phase from the engine, so this is a TOCTOU issue.

3. **PostCompact hook assumes original role**: `create_post_compact_hook` captures `agent_role` at creation time. If an agent is somehow reassigned roles (not currently possible, but future-proofing), the hook would inject the wrong content.

4. **`read_text()` without encoding**: Both calls in `agent_folders.py` (lines 63, 73) lack `encoding='utf-8'`. Per CLAUDE.md cross-platform rules, this WILL bite on Windows. Any fix must include this.

5. **Coordinator prompt AFTER injection**: The current code prepends phase content, then appends the coordinator's prompt: `f"{folder_prompt}\n\n---\n\n{prompt}"`. The coordinator's prompt comes last, so if it contradicts the phase file, the coordinator wins (recency bias). This is arguably correct -- the coordinator adds context -- but could dilute phase instructions.

---

## Recommendations

1. **Fix the encoding bug in agent_folders.py** -- trivial, no-risk, do it now
2. **Make the existing spawn-time injection more robust** -- don't swallow exceptions silently, validate `type` param usage
3. **Add phase transition broadcast to sub-agents** -- use `tell_agent` (queued, non-interrupting) to send new phase content
4. **Add a `close_agent` guardrail** -- warn level, not deny, so coordinator can still close when appropriate
5. **Do NOT add a `spawn_agent` guardrail for phase injection** -- the system should handle this automatically; warning the coordinator to do it manually is the wrong abstraction level
6. **Document that `type` param is the role-folder link** -- this is currently implicit and easy to miss

---

## Summary Table

| Claim in Issue #37 | Actually True? | Notes |
|---|---|---|
| "Phase markdown never delivered" | **Partially false** | Code exists at spawn time, but fragile |
| "phase_context.md only for coordinator" | **True** | .claude/phase_context.md is coordinator-only |
| "Sub-agents get coordinator-authored prompts" | **True but incomplete** | They get coordinator prompt WITH phase content prepended (when it works) |
| "No mechanism for phase transitions" | **True** | Sub-agents get no updates on advance |
| Premature closure risk | **Theoretical** | No evidence of actual premature closure, but no protection either |
