# SPEC: Advance Check UX -- Show Context and Signal Pending Input

**Issue:** #21
**Status:** Draft (Rev 4)
**Date:** 2026-04-12

---

## 1. Summary

When a `manual-confirm` advance check or guardrail `request_override` fires,
the user currently sees a generic prompt with no domain context. If the
requesting agent is not the active tab, there is no visual signal that input is
needed.

This spec adds three capabilities to BOTH prompt types:

1. **Domain context in prompts** -- advance checks show phase name/progress;
   guardrail overrides show rule ID and severity. Both show the action detail
   as a subtitle.
2. **NEEDS_INPUT status on the requesting agent** -- the sidebar orange dot
   appears while any approval prompt is waiting.
3. **Toast notification for non-active agents** -- a notification tells the
   user which agent needs approval, without auto-switching tabs. Toasts are
   debounced per agent+key to prevent spam from retry loops.

---

## 2. Canonical Terminology

Use these terms exactly in code, comments, and commit messages.

| Term | Meaning |
|------|---------|
| **advance check** | Gate condition evaluated during phase transition (AND semantics, short-circuit). |
| **manual-confirm** | Built-in check type requiring user interaction via `AsyncConfirmCallback`. |
| **confirm prompt** | The `SelectionPrompt` shown for a manual-confirm advance check. |
| **override prompt** | The `SelectionPrompt` shown for a guardrail deny-level rule override. |
| **agent prompt** | The shared UX pattern: mount `SelectionPrompt` + set `NEEDS_INPUT` + toast + restore status. Both confirm prompt and override prompt are agent prompts. |
| **phase context** | The workflow phase metadata (name, index, total phases) shown in the confirm prompt header. NOT the phase prompt text (identity.md + phase.md). |
| **rule context** | The guardrail rule metadata (rule ID, blocked tool, severity) shown in the override prompt header. |
| **NEEDS_INPUT status** | `AgentStatus.NEEDS_INPUT` -- triggers the orange sidebar indicator. |
| **needs-attention** | CSS class on `HamburgerButton` for collapsed-sidebar highlight. Already exists. |
| **agent focus** | NOT auto-switching tabs. Defined as: set `NEEDS_INPUT` status + show toast notification. The user decides when to switch. |

---

## 3. Architecture

Shared `_show_agent_prompt()` helper with two thin callers. Both advance check
confirm prompts and guardrail override prompts use the same UX pattern
(NEEDS_INPUT, toast with debounce, status restore) -- only the parameters
differ. See Appendix A for decision rationale.

---

## 4. File-by-File Changes

All paths relative to `submodules/claudechic/claudechic/`.

### 4.1 `checks/protocol.py` -- Widen the callback seam

**What:** Add an optional context dict parameter to `AsyncConfirmCallback`.

**Before:**
```python
AsyncConfirmCallback = Callable[[str], Awaitable[bool]]
```

**After:**
```python
AsyncConfirmCallback = Callable[[str, dict[str, Any] | None], Awaitable[bool]]
"""The seam between ManualConfirm and the TUI.

ManualConfirm calls: await callback(question, context) -> bool
  - question: the prompt string from YAML
  - context: optional dict with phase metadata (may be None)
    Keys when present: "phase_id", "phase_index", "phase_total", "check_id"

The engine creates the callback, closing over app methods.
ManualConfirm never imports anything from claudechic.widgets or app.
"""
```

**Import addition:** Add `Any` to the existing `typing` import.

**Why:** The callback is the seam between engine and TUI. Widening it with an
optional dict passes phase metadata without coupling engine to TUI internals.
The dict is intentionally untyped (not a dataclass) to keep `protocol.py` as a
leaf module with no upward imports.

---

### 4.2 `checks/builtins.py` -- Pass context through ManualConfirm

**What:** Update `ManualConfirm` to accept and forward an optional context dict.

**Before:**
```python
class ManualConfirm:
    def __init__(self, question: str, confirm_fn: AsyncConfirmCallback) -> None:
        self.question = question
        self.confirm_fn = confirm_fn

    async def check(self) -> CheckResult:
        try:
            confirmed = await self.confirm_fn(self.question)
```

**After:**
```python
class ManualConfirm:
    def __init__(
        self,
        question: str,
        confirm_fn: AsyncConfirmCallback,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.question = question
        self.confirm_fn = confirm_fn
        self.context = context

    async def check(self) -> CheckResult:
        try:
            confirmed = await self.confirm_fn(self.question, self.context)
```

**Registration update:** Update the `manual-confirm` registration lambda to
forward the `context` key from params:

```python
register_check_type(
    "manual-confirm",
    lambda p: ManualConfirm(
        question=p.get("question") or p.get("prompt", "Confirm?"),
        confirm_fn=p["confirm_fn"],
        context=p.get("context"),
    ),
)
```

**Import addition:** Add `Any` to the existing `typing` import if not present.

---

### 4.3 `workflows/engine.py` -- Inject phase context into check params

**What:** In `_run_single_check()`, when building a `manual-confirm` check,
add phase context to the params dict. Read phase info at invocation time (not
closure time) to avoid stale data.

**Add `asyncio.Lock`** to prevent concurrent `attempt_phase_advance` calls
from showing double prompts.

**Changes to `__init__`:**
```python
def __init__(self, manifest, persist_fn, confirm_callback):
    # ... existing init ...
    self._advance_lock = asyncio.Lock()  # NEW: prevent concurrent advance
```

**Changes to `attempt_phase_advance`:**
```python
async def attempt_phase_advance(self, ...):
    async with self._advance_lock:
        # ... existing body (indented one level) ...
```

**Changes to `_run_single_check`:**
```python
async def _run_single_check(self, check_decl: CheckDecl) -> CheckResult:
    try:
        params = dict(check_decl.params)
        if check_decl.type == "manual-confirm":
            params["confirm_fn"] = self._confirm_callback
            # Inject phase context at invocation time (not closure time)
            current = self._current_phase
            phase_order = self._phase_order
            phase_index = (
                phase_order.index(current) + 1 if current in phase_order else 0
            )
            params["context"] = {
                "phase_id": current,
                "phase_index": phase_index,
                "phase_total": len(phase_order),
                "check_id": check_decl.id,
            }
        # ... rest unchanged ...
```

**Import addition:** Add `import asyncio` at the top.

---

### 4.4 `mcp.py` -- Pass calling agent to both prompt flows

**What:** Convert both `advance_phase` and `request_override` from bare
functions to factories so they know which agent triggered the prompt.

#### 4.4.a `advance_phase` -> `_make_advance_phase(caller_name)`

```python
def _make_advance_phase(caller_name: str | None = None):
    """Create advance_phase tool with caller name bound."""

    @tool(
        "advance_phase",
        "Advance the active workflow to its next phase. ...",
        {},
    )
    async def advance_phase(args: dict[str, Any]) -> dict[str, Any]:
        if _app is None or _app._workflow_engine is None:
            return _error_response("No active workflow")
        _track_mcp_tool("advance_phase")

        engine = _app._workflow_engine

        # Resolve calling agent for NEEDS_INPUT status
        caller_agent = None
        if caller_name and _app.agent_mgr:
            caller_agent = _app.agent_mgr.find_by_name(caller_name)

        # Temporarily set agent-aware confirm callback
        original_cb = engine._confirm_callback
        engine._confirm_callback = _app._make_confirm_callback(agent=caller_agent)
        try:
            current = engine.get_current_phase()
            # ... rest of existing logic unchanged ...
        finally:
            engine._confirm_callback = original_cb

    return advance_phase
```

#### 4.4.b `request_override` -> `_make_request_override(caller_name)`

```python
def _make_request_override(caller_name: str | None = None):
    """Create request_override tool with caller name bound."""

    @tool(
        "request_override",
        "Request user approval to override a deny-level rule. ...",
        { ... },  # existing schema unchanged
    )
    async def request_override(args: dict[str, Any]) -> dict[str, Any]:
        if _app is None or _app._token_store is None:
            return _error_response("App not initialized")
        _track_mcp_tool("request_override")

        rule_id = args["rule_id"]
        tool_name = args["tool_name"]
        tool_input = args.get("tool_input", {})

        description = (
            f"Agent wants to run blocked action:\n"
            f"  Tool: {tool_name}\n"
            f"  Input: {_format_tool_input(tool_input)}\n"
            f"  Blocked by: {rule_id}\n"
            f"Approve this specific action?"
        )

        # Resolve calling agent for NEEDS_INPUT status
        caller_agent = None
        if caller_name and _app.agent_mgr:
            caller_agent = _app.agent_mgr.find_by_name(caller_name)

        approved = await _app._show_override_prompt(
            rule_id, description, agent=caller_agent,
        )

        if approved:
            _app._token_store.store(
                rule_id, tool_name, tool_input, enforcement="deny",
            )
            return _text_response(
                f"Override approved for rule {rule_id}. "
                f"Retry the exact same command."
            )
        else:
            return _text_response("Override denied.")

    return request_override
```

#### 4.4.c `create_chic_server` updates

```python
# Replace:
advance_phase,
# With:
_make_advance_phase(caller_name),

# Replace:
request_override,
# With:
_make_request_override(caller_name),
```

---

### 4.5 `app.py` -- Shared helper + two thin callers

This is the core of the architectural change. We extract the shared UX
pattern into `_show_agent_prompt()`, then both advance checks and guardrail
overrides call it with different parameters.

#### 4.5.a `_show_agent_prompt` -- New shared helper (the compositional law)

Add this new method near `_show_override_prompt` (around line 690). This is the
**single implementation** of the "agent needs user approval" UX pattern:

```python
async def _show_agent_prompt(
    self,
    title: str,
    options: list[tuple[str, str]],
    subtitle: str | None = None,
    agent: Agent | None = None,
    toast_message: str | None = None,
    toast_key: str | None = None,
    post_deny_message: str | None = None,
) -> str | None:
    """Show an approval prompt with agent awareness.

    This is the shared UX law for all "agent needs user approval"
    interactions. Handles: mount SelectionPrompt, set NEEDS_INPUT on
    the requesting agent, toast if non-active, restore status after.

    Callers provide domain-specific parameters (title, options, etc.)
    without duplicating the agent-awareness logic.

    Args:
        title: Prompt title (ASCII only, no emoji).
        options: List of (value, label) tuples for SelectionPrompt.
        subtitle: Optional detail text below the title.
        agent: The agent requesting approval. If None, uses active agent.
        toast_message: Notification shown when agent is not active tab.
            If None, no toast is shown.
        toast_key: Deduplication key for toast_message. If a toast with
            the same key was shown within TOAST_COOLDOWN_SECONDS, the
            toast is suppressed (the prompt still shows). Typically
            "{agent_id}:{domain_id}" (e.g., "agent-1:no_pip_install").
            If None, toast is always shown (no debounce).
        post_deny_message: Toast shown after user selects a deny-equivalent
            option (any option whose value is not "allow"). If None, no
            post-deny toast.

    Returns:
        The selected option value (str), or None if cancelled.
    """
    from claudechic.widgets.prompts import SelectionPrompt

    target_agent = agent or self._agent
    previous_status = None

    # Set NEEDS_INPUT on the requesting agent
    if target_agent:
        previous_status = target_agent.status
        target_agent._set_status(AgentStatus.NEEDS_INPUT)

        # Toast if this agent is not the active tab (with debounce)
        if toast_message and target_agent.id != self.active_agent_id:
            if self._should_show_toast(toast_key):
                self.notify(toast_message, severity="information")

    try:
        prompt = SelectionPrompt(title, options, subtitle=subtitle)
        async with self._show_prompt(prompt, agent=target_agent):
            result = await prompt.wait()

        # Post-deny feedback
        if result != "allow" and post_deny_message:
            self.notify(post_deny_message, severity="warning")

        return result
    except Exception as e:
        log.warning("Agent prompt error: %s", e)
        return None  # Treat as cancel
    finally:
        if target_agent and previous_status is not None:
            restore_status = (
                previous_status
                if previous_status != AgentStatus.NEEDS_INPUT
                else AgentStatus.BUSY
            )
            target_agent._set_status(restore_status)
```

#### 4.5.b Toast debounce helper

Add instance state in `ChatApp.__init__` (or `on_mount`):

```python
self._toast_timestamps: dict[str, float] = {}
```

Add constant at class level:

```python
TOAST_COOLDOWN_SECONDS: float = 10.0
```

Add private helper:

```python
def _should_show_toast(self, toast_key: str | None) -> bool:
    """Check whether a toast should be shown, enforcing per-key cooldown.

    Returns True if:
    - toast_key is None (no debounce requested), OR
    - No toast with this key was shown within TOAST_COOLDOWN_SECONDS.

    When returning True, records the current timestamp for the key.
    """
    if toast_key is None:
        return True
    now = time.monotonic()
    last_shown = self._toast_timestamps.get(toast_key, 0.0)
    if now - last_shown < self.TOAST_COOLDOWN_SECONDS:
        return False
    self._toast_timestamps[toast_key] = now
    return True
```

**Import addition:** Add `import time` at the top of `app.py` (stdlib, no
boundary violation).

**Why toast_key, not automatic dedup on toast_message?** Different prompts
can have the same message text but different semantic contexts. The key gives
callers explicit control: override prompts key on `"{agent_id}:{rule_id}"`,
advance checks key on `"{agent_id}:advance"`. The helper is prompt-type-agnostic
-- no `if` branches on what kind of prompt is being shown.

---

#### 4.5.c `_show_advance_check_prompt` -- Thin caller for advance checks

```python
async def _show_advance_check_prompt(
    self,
    question: str,
    context: dict[str, Any] | None = None,
    agent: Agent | None = None,
) -> bool:
    """Show confirm prompt for manual-confirm advance checks.

    Thin caller over _show_agent_prompt with phase context formatting.
    """
    # Build phase context header
    header = "Confirm phase advance"
    if context:
        phase_id = context.get("phase_id", "")
        idx = context.get("phase_index", 0)
        total = context.get("phase_total", 0)
        if phase_id and total:
            header = f"Phase {idx}/{total}: {phase_id}"

    target = agent or self._agent
    agent_name = target.name if target else None

    result = await self._show_agent_prompt(
        title=f"[Advance check] {header}",
        options=[
            ("allow", "Advance to next phase"),
            ("deny", "Stay on current phase"),
        ],
        subtitle=question,
        agent=agent,
        toast_message=(
            f"Agent '{agent_name}' needs confirmation to advance"
            if agent_name
            else None
        ),
        toast_key=f"{target.id}:advance" if target else None,
        post_deny_message=(
            "Phase advance blocked. Agent will continue working on this phase."
        ),
    )
    return result == "allow"
```

#### 4.5.d `_show_override_prompt` -- Refactor to thin caller for guardrail overrides

**Before** (existing method, ~24 lines with emoji title and no agent awareness):
```python
async def _show_override_prompt(self, rule_id: str, description: str) -> bool:
    ...
    title = f"\U0001f6e1\ufe0f Override request: {rule_id}"
    ...
```

**After** (thin caller over shared helper, ASCII title, agent-aware):
```python
async def _show_override_prompt(
    self, rule_id: str, description: str, agent: Agent | None = None,
) -> bool:
    """Show override prompt for deny-level guardrail rules.

    Thin caller over _show_agent_prompt with rule context formatting.
    """
    target = agent or self._agent
    agent_name = target.name if target else None

    result = await self._show_agent_prompt(
        title=f"[Override] Rule: {rule_id}",
        options=[
            ("allow", "Allow -- approve this specific action"),
            ("deny", "Deny -- block this action"),
        ],
        subtitle=description,
        agent=agent,
        toast_message=(
            f"Agent '{agent_name}' needs override approval for {rule_id}"
            if agent_name
            else None
        ),
        toast_key=f"{target.id}:{rule_id}" if target else None,
        post_deny_message="Override denied.",
    )
    return result == "allow"
```

**Key changes from current implementation:**
- Emoji shield `\U0001f6e1\ufe0f` replaced with ASCII `[Override]` prefix.
- New `agent` parameter (optional, backward compatible).
- NEEDS_INPUT status + toast + restore all come for free from the shared helper.
- The `description` string (already built by `request_override` MCP tool with
  tool name, input, and blocking rule) becomes the subtitle.

#### 4.5.e `_make_confirm_callback` -- Accept optional agent parameter

**Before:**
```python
def _make_confirm_callback(self):
    async def confirm(message: str) -> bool:
        return await self._show_override_prompt("advance-check", message)
    return confirm
```

**After:**
```python
def _make_confirm_callback(self, agent=None):
    """Create async confirm callback for manual-confirm advance checks.

    Args:
        agent: The agent requesting confirmation. Used to set
            NEEDS_INPUT status and show toast if not active.
            If None, uses the currently active agent.
    """
    async def confirm(message: str, context: dict[str, Any] | None = None) -> bool:
        return await self._show_advance_check_prompt(
            message, context=context, agent=agent,
        )
    return confirm
```

#### 4.5.f `SelectionPrompt` subtitle support

**What:** Add an optional `subtitle` parameter to `SelectionPrompt` that
renders below the title and above the options.

**File:** `widgets/prompts.py`

In `SelectionPrompt.__init__`, add `subtitle: str | None = None` parameter.
Store as `self.subtitle`.

In `SelectionPrompt.compose`, after the title `Static`, conditionally yield:
```python
if self.subtitle:
    yield Static(self.subtitle, classes="prompt-subtitle")
```

**CSS addition** in `styles.tcss`:
```css
.prompt-subtitle {
    color: $text-muted;
    padding: 0 0 1 0;
}
```

---

## 5. Edge Cases and Mitigations

| Edge Case | Mitigation |
|-----------|------------|
| **Concurrent advance_phase calls** | `asyncio.Lock` in engine prevents double-prompt. Only one advance attempt at a time. |
| **Agent closed while prompt is pending** | `_show_prompt` context manager's `finally` block already handles widget cleanup. The `finally` in `_show_agent_prompt` restores status. If agent is gone, the status set is a no-op. |
| **No workflow engine active** | `advance_phase` MCP tool already returns error early. `_make_confirm_callback` with `context=None` still works (header falls back to generic text). |
| **Stale phase data** | Phase context is read in `_run_single_check` at invocation time, not captured in a closure. |
| **caller_name is None** | Both `_make_advance_phase(None)` and `_make_request_override(None)` produce callbacks with `agent=None`, which falls back to `self._agent` in `_show_agent_prompt`. |
| **Prompt cancelled (Escape)** | `prompt.wait()` raises on cancel, caught by the `except` block in `_show_agent_prompt`, returns `None`. Callers treat `None` as deny. |
| **Non-active agent prompt hidden** | Prompt gets `hidden` CSS class (existing behavior). Toast notification tells user which agent needs input. User switches manually. |
| **Override prompt called without agent (backward compat)** | `_show_override_prompt` now has `agent=None` as default. Existing internal callers (if any) that don't pass `agent` still work -- falls back to `self._agent`. |
| **Concurrent override + advance check** | These are independent flows on different agents. Each sets NEEDS_INPUT on its own agent. No lock needed between them -- the `_advance_lock` only serializes `attempt_phase_advance` calls. |
| **Toast spam from override retry loops** | When an agent repeatedly hits the same deny rule, each `request_override` call fires a toast. The `toast_key` debounce in `_show_agent_prompt` suppresses repeat toasts within 10 seconds. Key format `"{agent_id}:{rule_id}"` ensures different rules and different agents get independent cooldowns. The prompt still mounts every time -- only the toast is suppressed. |
| **Toast cooldown dict grows unbounded** | `_toast_timestamps` is a flat dict keyed by `"{agent_id}:{domain_id}"`. In practice this is bounded by (number of agents) x (number of rules + 1 advance key). No cleanup needed -- stale keys are harmless, timestamps just expire naturally. |

---

## 6. Testing Requirements

### 6.1 Unit Tests (fast marker)

| Test | Location | What It Verifies |
|------|----------|------------------|
| `test_manual_confirm_passes_context` | `tests/test_checks.py` | `ManualConfirm.check()` passes context dict to callback |
| `test_manual_confirm_none_context` | `tests/test_checks.py` | `ManualConfirm.check()` works when context is None (backward compat) |
| `test_engine_injects_phase_context` | `tests/test_engine.py` | `_run_single_check` for manual-confirm includes `phase_id`, `phase_index`, `phase_total`, `check_id` in params |
| `test_advance_lock_prevents_concurrent` | `tests/test_engine.py` | Two concurrent `attempt_phase_advance` calls serialize (second waits for first) |
| `test_should_show_toast_none_key` | `tests/test_app_ui.py` | `_should_show_toast(None)` always returns True (no debounce) |
| `test_should_show_toast_cooldown` | `tests/test_app_ui.py` | Same key within 10s returns False; after 10s returns True (mock `time.monotonic`) |
| `test_should_show_toast_independent_keys` | `tests/test_app_ui.py` | Different keys have independent cooldowns |

### 6.2 Widget Tests (fast marker)

| Test | Location | What It Verifies |
|------|----------|------------------|
| `test_selection_prompt_subtitle` | `tests/test_widgets.py` | `SelectionPrompt` with subtitle renders the subtitle text |
| `test_selection_prompt_no_subtitle` | `tests/test_widgets.py` | `SelectionPrompt` without subtitle does not render subtitle element |

### 6.3 Integration Tests (integration marker)

| Test | Location | What It Verifies |
|------|----------|------------------|
| `test_advance_check_prompt_shows_phase_context` | `tests/test_app_ui.py` | Confirm prompt displays phase name and progress (e.g., "Phase 2/4: review") |
| `test_advance_check_sets_needs_input` | `tests/test_app_ui.py` | Requesting agent gets `NEEDS_INPUT` status during prompt, restored after |
| `test_advance_check_toast_for_inactive_agent` | `tests/test_app_ui.py` | Toast shown when advance check fires for a non-active agent |
| `test_advance_check_deny_feedback` | `tests/test_app_ui.py` | Post-deny toast: "Phase advance blocked..." |
| `test_advance_check_no_auto_switch` | `tests/test_app_ui.py` | Active agent does NOT change when another agent's advance check fires |
| `test_override_prompt_shows_rule_context` | `tests/test_app_ui.py` | Override prompt displays `[Override] Rule: {rule_id}` title + tool/input as subtitle |
| `test_override_prompt_sets_needs_input` | `tests/test_app_ui.py` | Requesting agent gets `NEEDS_INPUT` status during override prompt |
| `test_override_prompt_toast_for_inactive_agent` | `tests/test_app_ui.py` | Toast shown when override fires for a non-active agent |
| `test_override_prompt_no_emoji` | `tests/test_app_ui.py` | Override prompt title contains no non-ASCII characters |
| `test_toast_debounce_suppresses_repeat` | `tests/test_app_ui.py` | Second override prompt for same agent+rule within 10s does NOT fire a toast (prompt still shows) |
| `test_toast_debounce_allows_different_keys` | `tests/test_app_ui.py` | Two override prompts for same agent but different rule_ids both fire toasts (independent keys) |
| `test_toast_debounce_expires_after_cooldown` | `tests/test_app_ui.py` | After 10s cooldown, same agent+rule fires toast again (mock `time.monotonic`) |

### 6.4 Cross-Platform

- No new non-ASCII characters. `[Advance check]` and `[Override]` prefixes
  replace the existing shield emoji (`\U0001f6e1\ufe0f`).
- No new file I/O paths (all changes are in-memory state and TUI rendering).
- No new subprocess calls.

---

## 7. Dependency / Merge Order

Changes should be implemented and reviewed in this order (each step builds on
the previous):

1. **`checks/protocol.py` + `checks/builtins.py`** -- Widen seam + update
   ManualConfirm. Unit tests pass independently.
2. **`workflows/engine.py`** -- Inject phase context + add lock. Engine tests
   pass with mocked callback.
3. **`widgets/prompts.py` + `styles.tcss`** -- Add subtitle support. Widget
   tests pass independently.
4. **`app.py`** -- New `_show_agent_prompt` shared helper +
   `_show_advance_check_prompt` thin caller + refactored `_show_override_prompt`
   thin caller + updated `_make_confirm_callback`. Integration tests pass.
5. **`mcp.py`** -- Convert both `advance_phase` and `request_override` to
   factories. Full flow works end-to-end.

Steps 1-3 can be developed in parallel. Steps 4-5 depend on all prior steps.

---

## 8. Composability Invariants (Post-Implementation Checks)

After implementation, verify these properties hold:

- [ ] `checks/protocol.py` imports only from stdlib (leaf module boundary).
- [ ] `checks/builtins.py` imports only from `checks/protocol` (leaf boundary).
- [ ] `workflows/engine.py` does NOT import from `widgets/` or `app.py`.
- [ ] `ManualConfirm` does NOT import from `claudechic.widgets` or `claudechic.app`.
- [ ] `SelectionPrompt` does NOT import from `workflows/` or `checks/`.
- [ ] The `AsyncConfirmCallback` type alias is the ONLY seam between engine and TUI.
- [ ] `_show_agent_prompt` contains NO `if prompt_type` or `if context_type` branches.
- [ ] Both `_show_advance_check_prompt` and `_show_override_prompt` are thin callers (under 25 lines each, no NEEDS_INPUT/toast/restore logic).
- [ ] All existing tests pass without modification (backward compatibility).
- [ ] No non-ASCII characters in any prompt title string.

---

See [SPEC_APPENDIX.md](SPEC_APPENDIX.md) for architectural decision rationale and implementation guardrails.
