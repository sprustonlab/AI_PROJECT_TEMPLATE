# Skeptic Review: Do Standalone Checks Need to Exist in v1?

**Reviewer:** Skeptic
**Date:** 2026-04-04

---

## The honest answer: No.

`/check-setup` is aspirational. Nobody asked for it. The only v1 consumer of Check is phase gates. Let me walk through the reasoning.

---

## 1. Stress test: cut `/check-setup`, what breaks?

| Component | Breaks without `/check-setup`? |
|---|---|
| Check primitive (`_types.py`, `_builtins.py`) | No — consumed by phase gates |
| Phase gates (`advance_checks`) | No — they call `check.check(ctx)` directly |
| `phase_guard.py` | No — doesn't use checks at all |
| `generate_hooks.py` | No — validates phase IDs, not checks |
| Tutorial engine | No — consumes checks via phase gates |
| Existing hints system | No — unrelated |

**Nothing breaks.** `/check-setup` is a leaf node with no dependents. Cutting it removes ~60-90 lines of code and ~60 lines of tests from v1 scope.

---

## 2. The architectural argument was: "checks are independent of Phase"

The spec uses `/check-setup` as proof that Check is a standalone primitive, not coupled to Phase. This is a legitimate design principle — but you don't need a slash command to prove it.

The Check protocol already proves independence through its type signature:

```python
class Check(Protocol):
    def check(self, ctx: CheckContext) -> CheckResult: ...
```

No `Phase` in the signature. No `ActivePhase`. No `workflow_id`. The protocol IS the proof of independence. `/check-setup` is a demo, not a proof.

---

## 3. "Checks can also be used standalone" — is this aspirational?

Yes. Here's why:

The spec lists three future standalone uses: "diagnostics, CI, health checks." None of these are v1 requirements. The v1 requirement is: **phase gates need to run assertions and get pass/fail verdicts.** That's it.

The spec is doing a common thing: designing the primitive to be general (good), then building a consumer to prove generality (unnecessary). The generality is already proven by the protocol design. Building a consumer is YAGNI.

---

## 4. But wait — is there a REAL standalone use case hiding here?

Yes, actually. But it's not `/check-setup`.

**The real standalone use case is testing the checks themselves.** During development, you'll want to run:

```python
# In a test file or REPL
result = CommandOutputCheck("pixi --version", r"pixi \d+").check(ctx)
assert result.passed
```

This is already how you'd test checks in pytest. No slash command needed. The Check primitive's standalone nature serves developers writing and debugging checks, not end users running diagnostics.

**The second real use case is CI preflight.** Before running the project-team workflow, CI could run checks to verify environment. But that's a CI script concern, not a v1 deliverable.

---

## 5. What pattern should standalone checks follow?

The Coordinator asks: should standalone checks follow the hints pattern or something else?

**They should follow no pattern yet.** Here's why:

The hints system has a specific pattern because it has a specific runtime: triggers fire, pipeline evaluates, state persists. Standalone checks don't have a runtime — they're just function calls. Adding a pattern (registry, runner, output formatter) is premature abstraction.

If standalone checks ever need a surface, the pattern should be:

| Option | Complexity | When it makes sense |
|---|---|---|
| **Just call `check.check(ctx)` in a script** | Zero | Always works, v1-forever |
| **Slash command (`.claude/commands/check-setup.md`)** | ~20 lines of markdown | When a user-facing diagnostic is needed |
| **CLI entry point (`python -m checks.run`)** | ~40 lines | When CI needs structured output |

All three consume the same Check protocol. The protocol is the pattern. The surface is chosen by the consumer.

---

## 6. Recommendation

**Cut `/check-setup` from v1.** Here's what changes:

| Section | Change |
|---|---|
| Section 1 (What v1 delivers) | Remove item 5 (`/check-setup diagnostic`) |
| Section 2.1 (standalone usage example) | Keep the example as a design note showing checks work without Phase, but label it "future consumer" not "v1 deliverable" |
| Section 5.2 (Seams) | Remove `Check → Standalone` row, or relabel as "v2" |
| Section 7.4 | Move to Appendix or label "future example" |
| Section 8.1 (line counts) | Remove ~60 lines from infrastructure, ~60 from tests. New total: ~120 lines lighter |
| Section 8.3 (implementation order) | Remove `/check-setup` from step 2 |
| Section 10.2 | Remove `/check-setup entry point` open decision |

**What we keep:** The Check primitive, its three built-in types, and the registry. These are consumed by phase gates. Their standalone usability is a design property, not a deliverable.

**Impact:** ~120 fewer lines in v1. One fewer open decision. One fewer thing to test. Zero functionality loss — phase gates still work identically.

---

## 7. The deeper point

The spec has a pattern of building consumers to justify primitives. `/check-setup` justifies Check independence. The "First Pytest tutorial" justifies the tutorial engine. These are demos, not requirements.

Good primitives don't need demos in v1. They need one real consumer that exercises them under load. For Check, that consumer is phase gates. For Phase, that consumer is the project-team workflow. Build those. If the primitives are well-designed (and they are), standalone use will emerge naturally when someone actually needs it.
