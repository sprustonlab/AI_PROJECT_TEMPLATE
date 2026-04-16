# User Alignment Review: Test File (test_phase_injection.py)

## User Requirements Being Checked

The coordinator relayed these user directives for testing:
1. **TDD -- all tests written before code**
2. **ZERO mocking -- no fake async or anything else**
3. **All tests RED before any code is written**
4. **Each issue should have a failing test**
5. **Simulate TUI with workflow activation and phase advance**

---

## Assessment

### 1. TDD -- Tests Written Before Code

**[OK] ALIGNED.** The file header says "EVERY test asserts desired post-fix behavior and MUST FAIL before production code is written." Each test block has clear comments explaining why it should fail now:

- Test 1: "FAILS: Current code has bare read_text() without encoding"
- Test 3: "FAILS: Current code silently falls back to name"
- Test 4: "FAILS: advance_phase has no broadcast loop"
- Test 5: "FAILS: The rule doesn't exist in the YAML yet"
- Test 6: "FAILS: Current code does exact path match"
- Test 8: "FAILS: Current code has `agent_type or name` fallback"

Every test describes the desired post-fix behavior and why it currently fails. This is proper TDD.

### 2. ZERO Mocking -- The _FakeAgent/_FakeApp Question

**[WARNING] POTENTIAL MISALIGNMENT.** The user said "no fake async or anything else." The test file contains:

- `_FakeAgent` (lines 69-93) -- hand-written class with `async def send()` that captures messages
- `_FakeAgentManager` (lines 96-129) -- hand-written class with `async def create()`
- `_FakeApp` (lines 132-156) -- hand-written class wrapping a **real** WorkflowEngine

The file header explicitly claims: "Zero mocking -- no unittest.mock, no MagicMock, no AsyncMock, no monkeypatch."

**Analysis of what "zero mocking" means:**

The file avoids `unittest.mock` entirely -- no `MagicMock`, `AsyncMock`, `patch`, or `monkeypatch`. That's one valid interpretation of "zero mocking."

However, the user said "no fake async or **anything else**." These `_Fake*` classes ARE fakes. They're hand-written test doubles (stubs/fakes), not mocks in the unittest.mock sense, but they ARE synthetic stand-ins for real objects. `_FakeAgent.send()` is a fake async method. `_FakeApp._inject_phase_prompt_to_main_agent` is a no-op stub.

**The question is: did the user mean:**
- (A) "Don't use unittest.mock/MagicMock" -- the file satisfies this
- (B) "Don't use ANY test doubles -- exercise only real objects" -- the file violates this

**Context clue:** The SPEC itself (lines 390, 417) says "Mock agent_mgr.agents with typed agents" and "unit/mock tests." This suggests the SPEC was written before the user's "zero mocking" directive, and the test file is trying to reconcile them by using hand-written fakes instead of unittest.mock.

**My assessment:** The hand-written fakes are a reasonable pragmatic compromise. Testing MCP handlers against the real TUI (Textual app, SDK connections) would require an integration test with a running claudechic instance, which is slow, fragile, and likely not what the user meant. The fakes use a **real WorkflowEngine** and **real file I/O** -- the core logic under test is exercised with real objects. Only the delivery mechanism (Agent.send) is stubbed.

**However,** the user's words were "no fake async or anything else," and `_FakeAgent.send()` is literally fake async. If the user is strict about this, the tests need restructuring.

```
? USER ALIGNMENT: User said "ZERO mocking -- no fake async or anything else."
The test file uses hand-written _FakeAgent with `async def send()` -- this IS fake async.
It avoids unittest.mock entirely, but _FakeAgent/_FakeApp are still test doubles.
Is this what the user intended to prohibit?
Recommend: Ask user to clarify. If strict, tests need to use real Agent/App objects
(much harder, likely requires integration test infrastructure).
```

### 3. All Tests RED Before Code

**[OK] ALIGNED (with one caveat).** The tests are designed to fail against current code. However, I cannot verify they actually all fail right now without running them. Tests 2 and 7 check for `agent_type` on `Agent` -- if that attribute was already added as part of another change, they might pass. The file should be run to confirm all RED before any production changes.

### 4. Each Issue Has a Failing Test

**[OK] ALIGNED.** Coverage mapping:

| Issue | Test(s) |
|-------|---------|
| encoding='utf-8' missing | Test 1 (`test_read_text_calls_have_encoding_param`) |
| Agent.agent_type storage | Tests 2, 7 (`test_agent_accepts_agent_type_kwarg`, `test_agent_manager_passes_agent_type_to_agent`) |
| spawn without type= silent failure | Tests 3, 8 (`test_spawn_without_type_emits_warning`, `test_spawn_agent_no_name_fallback`) |
| Phase broadcast missing | Test 4 (`test_typed_subagent_receives_broadcast_on_advance`) |
| close_agent unguarded | Test 5 (`test_close_leadership_rule_exists_in_manifest`) |
| Case-insensitive role lookup | Test 6 (`test_mixed_case_role_finds_lowercase_folder`) |

All issues from the spec have corresponding failing tests.

**One gap:** No test for "sub-agents WITHOUT agent_type should NOT receive broadcast." The SPEC lists this as test case #4 (`test_broadcast_skips_untyped`), but it's not in the file. This is a **scope shrink** -- a spec-required test is missing.

```
[WARNING] USER ALIGNMENT: SPEC lists test_broadcast_skips_untyped (spec item #4)
but the test file does not include it. This is a missing negative test --
the broadcast must NOT spam untyped agents.
```

**Another gap:** No test for "broadcast skips coordinator" (SPEC item #3, `test_broadcast_skips_coordinator`). The coordinator should not receive a duplicate broadcast since it already gets phase content inline.

```
[WARNING] USER ALIGNMENT: SPEC lists test_broadcast_skips_coordinator (spec item #3)
but the test file does not include it.
```

### 5. Simulate TUI with Workflow Activation and Phase Advance

**? NEEDS CLARIFICATION.** The tests exercise MCP handler functions directly (`spawn_agent.handler({...})`, `advance.handler({})`), NOT the actual TUI. They:
- Create a real WorkflowEngine with real phases
- Create real workflow files on disk
- Call MCP handlers that would normally be invoked by Claude through the TUI
- Use `_FakeApp`/`_FakeAgentManager` instead of the real Textual app

This is testing the **MCP layer** (where the bugs live), not the TUI layer. For the bugs in question, this is the correct test surface -- the TUI is just a wrapper around these MCP handlers.

However, the user said "simulate TUI with workflow activation and phase advance." If they meant a full end-to-end test with the Textual app running, these tests don't do that. If they meant "test the same code path the TUI uses," these tests DO do that (MCP handlers are exactly what the TUI calls).

```
? USER ALIGNMENT: User said "simulate TUI with workflow activation and phase advance."
Tests call MCP handlers directly (the layer where bugs live), not the Textual TUI.
This tests the RIGHT code but not via the TUI path.
Is this adequate, or does the user want actual TUI integration tests?
Recommend: Clarify with user. MCP-level testing is more reliable and faster,
but doesn't exercise the full TUI → MCP → Agent stack.
```

---

## Summary

| Requirement | Status | Notes |
|------------|--------|-------|
| TDD (tests before code) | [OK] ALIGNED | All tests describe desired behavior + why they fail now |
| Zero mocking | ? NEEDS CLARIFICATION | No unittest.mock, but uses hand-written _Fake* classes with fake async |
| All tests RED | [OK] ALIGNED (unverified) | Designed to fail, should be run to confirm |
| Each issue has test | [WARNING] 2 MISSING | `test_broadcast_skips_untyped` and `test_broadcast_skips_coordinator` from spec not included |
| TUI simulation | ? NEEDS CLARIFICATION | Tests MCP handlers (correct layer) but not actual TUI |

## Recommendations

1. **Ask user about _Fake* classes** -- Are hand-written fakes acceptable if unittest.mock is avoided? This determines whether a major restructuring is needed.
2. **Add the two missing tests** -- `test_broadcast_skips_untyped` and `test_broadcast_skips_coordinator` are in the spec and should be in the file.
3. **Run the tests** to confirm they all fail (RED) before any production code changes.
4. **Clarify "TUI simulation"** -- MCP-level testing is pragmatic and correct; full TUI testing is expensive and fragile. User should confirm which they want.
