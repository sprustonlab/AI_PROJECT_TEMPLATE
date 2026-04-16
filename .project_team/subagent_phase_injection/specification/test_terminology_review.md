# Terminology Review: test_phase_injection.py

> Reviewed by Terminology Guardian against `terminology_report.md` glossary.
> File: `submodules/claudechic/tests/test_phase_injection.py`

---

## Overall Assessment

The test file is well-written and largely consistent with the glossary. The
module docstring (line 1) correctly uses "sub-agent phase injection" (hyphenated).
Most test names and docstrings use canonical terms. Found **3 issues to fix**
and **3 minor suggestions**.

---

## Issues to Fix

### 1. "typed sub-agents" / "typed subagent" -- Non-Canonical Compound

**Line 335 (test name):**
```python
async def test_typed_subagent_receives_broadcast_on_advance(
```

**Line 338 (docstring):**
```python
"""After advance_phase, typed sub-agents SHOULD receive phase broadcast."""
```

**Problems:**
- `test_typed_subagent` -- "subagent" without hyphen. The glossary says use
  **sub-agent** (hyphenated) for claudechic agents. Python identifiers can't
  have hyphens, so `sub_agent` (with underscore) is the correct code form.
- "typed sub-agents" -- "typed" means "has `agent_type` set," which is an
  implementation detail. Per the SPEC.md review, prefer "sub-agents that have
  a role."

**Fix test name:**
```python
async def test_sub_agent_receives_broadcast_on_advance(
```

**Fix docstring:**
```python
"""After advance_phase, sub-agents with a role SHOULD receive phase broadcast."""
```

---

### 2. "phase broadcast" / "phase content" -- Not in Glossary

**Lines 328-329 (section comment):**
```python
# DESIRED: After advance_phase, typed sub-agents receive their
#          role-specific phase content for the new phase.
```

**Lines 383-384, 386-387, 390-391, 393-394 (assertions):**
```python
"Skeptic (agent_type='skeptic') should receive phase broadcast"
"Skeptic's broadcast should contain its implementation.md content"
"Implementer (agent_type='implementer') should receive phase broadcast"
"Implementer's broadcast should contain its implementation.md content"
```

**Problem:** "phase broadcast" and "phase content" are not defined in the
glossary. The glossary defines the mechanism as **in-band delivery** and
the content as the **agent prompt** (identity file + phase file).

The SPEC.md (Fix 2) calls this a "Phase-Transition Broadcast" which is
descriptive but not a glossary term. For test code, "broadcast" is acceptable
as a *description* of what happens (sending to all sub-agents), but "phase
content" should be "agent prompt" to match the glossary.

**Fix section comment:**
```python
# DESIRED: After advance_phase, sub-agents with a role receive their
#          role-specific agent prompt for the new phase.
```

**Fix assertion messages:**
```python
"Skeptic (agent_type='skeptic') should receive agent prompt on phase advance"
"Skeptic's agent prompt should contain its implementation.md content"
"Implementer (agent_type='implementer') should receive agent prompt on phase advance"
"Implementer's agent prompt should contain its implementation.md content"
```

---

### 3. "prompt assembly" (line 529-530) -- Vague

**Lines 529-530 (section comment):**
```python
# DESIRED: spawn_agent uses ONLY agent_type (not `agent_type or name`)
#          for role lookup. When type= is None, skip prompt assembly.
```

**Problem:** "prompt assembly" is ambiguous -- assembly of what? The glossary
term is **agent prompt** and the function is `assemble_phase_prompt`. Should be:

**Fix:**
```python
# DESIRED: spawn_agent uses ONLY agent_type (not `agent_type or name`)
#          for role lookup. When type= is None, skip agent prompt assembly.
```

Small change -- just adding "agent" before "prompt assembly."

---

## Minor Suggestions

### A. `_FakeAgent.agent_type` Conditional Storage (line 85-86)

```python
if agent_type is not None:
    self.agent_type = agent_type
```

**Observation:** This conditionally sets `agent_type` only when not None,
meaning `hasattr(agent, 'agent_type')` returns False for agents without a
type. This is intentional (testing that the real Agent doesn't have the
attribute yet), but after the fix, the real `Agent` will always have
`agent_type` (defaulting to `None`). The fake should match:

```python
self.agent_type = agent_type  # Always set, default None in signature
```

This isn't a terminology issue but it affects test correctness post-fix.

---

### B. "role-specific phase content" (line 329) vs "agent prompt"

The section header comment uses "role-specific phase content." Per glossary,
the content delivered is the **agent prompt** (identity file + phase file).
"Phase content" could be confused with **phase context** (the coordinator's
`.claude/phase_context.md`).

Already covered in Issue #2 above.

---

### C. Helper Docstring: "agent folder prompt" Risk

**Line 42 (helper docstring):**
```python
"""Create a minimal workflow directory structure."""
```

This is fine -- no terminology issues. Just noting that the helper creates
agent folders with phase files, and correctly uses "roles" as the parameter
name (matching the glossary).

---

## Term-by-Term Audit

| Term Used in Test File | Glossary Status | Verdict |
|---|---|---|
| "sub-agent" (line 1, module docstring) | Canonical | OK |
| "subagent" (line 335, test name) | DO NOT USE | **Fix: use `sub_agent`** |
| "sub-agents" (line 338, docstring) | Canonical | OK |
| "agent_type" (throughout) | Acceptable as code identifier | OK (maps to "role" conceptually) |
| "phase broadcast" (lines 383, 390) | Not in glossary | **Fix: "agent prompt on phase advance"** |
| "phase content" (line 329) | Not in glossary, confusable with "phase context" | **Fix: "agent prompt"** |
| "prompt assembly" (line 530) | Vague | **Fix: "agent prompt assembly"** |
| "identity.md" (throughout) | Canonical ("identity file") | OK |
| "specification.md" / "implementation.md" (throughout) | Canonical ("phase file") | OK |
| "role" (lines 448, 541) | Canonical | OK |
| "coordinator" (throughout) | Canonical | OK |
| "spawn_agent" (throughout) | Tool name, not terminology | OK |
| "advance_phase" (throughout) | Tool name, not terminology | OK |
| "encoding='utf-8'" (throughout) | Cross-platform rule | OK |
| "Agent.agent_type" (lines 259-273) | Acceptable as attribute name | OK |

---

## Summary of Required Actions

| # | Severity | Line(s) | Action |
|---|---|---|---|
| 1 | Fix | 335, 338 | Rename `test_typed_subagent_*` to `test_sub_agent_*`; update docstring |
| 2 | Fix | 329, 383-394 | Replace "phase content"/"phase broadcast" with "agent prompt" |
| 3 | Fix | 530 | "prompt assembly" -> "agent prompt assembly" |
| A | Suggestion | 85-86 | Make `_FakeAgent.agent_type` unconditional (always set, default None) |
