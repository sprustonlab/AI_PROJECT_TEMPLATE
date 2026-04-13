# SPEC Appendix: Advance Check UX

**Parent:** [SPEC.md](SPEC.md)

---

## Appendix A: Architectural Decision -- Shared Helper, Not Three Methods

### The Question

Both advance check confirm prompts and guardrail override prompts need the same
UX treatment (context header, NEEDS_INPUT, toast, status restore). Three options:

| Option | Description | Verdict |
|--------|-------------|---------|
| A. Three methods | `_show_override_prompt` (existing) + `_show_advance_check_prompt` (new) + `_show_guardrail_override_prompt` (new) | **Reject.** Duplicates NEEDS_INPUT/toast/restore logic in 2+ places. Violates DRY and the algebraic principle. |
| B. Refactor in place | Modify existing `_show_override_prompt` to handle both flows | **Reject.** The method would need `if prompt_type == ...` branches -- profile-as-code-switch smell. |
| C. Extract shared law | One `_show_agent_prompt()` helper with the shared UX pattern. Two thin callers pass different parameters. | **Accept.** The shared behavior IS the compositional law. Callers are parameter presets, not code branches. |

### Why Option C

The shared UX pattern (mount prompt, set NEEDS_INPUT, toast, restore) is the
**compositional law** for all "agent needs user approval" interactions. The
differences between advance checks and guardrail overrides are just parameters:

| Parameter | Advance Check | Guardrail Override |
|-----------|--------------|-------------------|
| Title prefix | `[Advance check]` | `[Override]` |
| Header | `Phase 2/4: review` | `Rule: no_pip_install` |
| Subtitle | Check question from YAML | Tool + input that was blocked |
| Option labels | Advance / Stay | Allow / Deny |
| Toast key | `{agent_id}:advance` | `{agent_id}:{rule_id}` |
| Post-deny toast | "Phase advance blocked..." | "Override denied." |

Same code path, different parameters. No `if` branches on prompt type.

### Axis Impact

No new axes. The "Prompt Rendering" axis gains a second value (override prompt)
alongside the existing confirm prompt value. The `_show_agent_prompt()` helper
IS the law that governs this axis -- if you follow the law (provide title,
options, subtitle, agent), the UX works automatically. Adding a third prompt
type in the future = just a new caller.

---

## Appendix B: Implementation Guardrails

These rules prevent common mistakes during implementation.

1. **DO NOT auto-switch the active agent tab.** The user controls focus. Use
   the orange indicator + toast instead. Auto-switching while the user is
   mid-thought in another agent is disruptive.

2. **DO NOT use emoji in prompt titles.** The existing override prompt uses
   a shield emoji -- both prompts must use ASCII only per cross-platform rules.
   Use `[Advance check]` and `[Override]` prefixes.

3. **DO NOT add `if prompt_type == ...` branches in the shared helper.** The
   `_show_agent_prompt()` method must be prompt-type-agnostic. All differences
   are expressed as parameters by the thin callers. If you find yourself
   branching on the prompt type in the helper, the parameters are wrong.

4. **DO NOT add a dataclass/named type for the context dict in
   `protocol.py`.** The checks module is a leaf module (stdlib only). A plain
   `dict[str, Any] | None` keeps the import boundary clean. The dict's keys
   are documented in the docstring.

5. **DO NOT capture phase info in a closure.** Read `self._current_phase` and
   `self._phase_order` inside `_run_single_check` at execution time. Closures
   over phase state go stale if another advance completes between callback
   creation and invocation.

6. **DO NOT gate sidebar updates on the active agent.** The `AgentItem`
   reactive watcher already updates regardless of which agent is active. Do not
   add conditional logic around status rendering.

7. **DO NOT use `on_blur` refocusing.** No automatic cursor/focus movement
   when a prompt appears. The prompt mounts where it mounts; the user navigates
   to it via the sidebar or keyboard shortcut.

8. **DO NOT create separate NEEDS_INPUT/toast/restore logic for each prompt
   type.** That is exactly what `_show_agent_prompt()` exists to prevent. If
   a future prompt type needs agent awareness, it calls the same helper.

9. **DO NOT debounce in the thin callers.** Toast debounce is part of the
   shared UX law in `_show_agent_prompt`. Callers pass a `toast_key` and the
   helper handles cooldown. If a caller passes `toast_key=None`, no debounce
   is applied -- that is the caller's choice, not the helper's decision.
