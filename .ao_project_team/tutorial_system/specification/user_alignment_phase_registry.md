# User Alignment Check — Phase ID Registry & Validation

**Date:** 2026-04-04
**Quick check requested by Coordinator.**

---

## The Proposal

Phase IDs must be pre-registered. Typos in `phase_block`/`phase_allow` cause a clear error at generation time (when `generate_hooks.py` runs), not silent runtime failure (when a hook reads a misspelled phase ID and quietly does nothing).

## Alignment: ✅ FULLY ALIGNED

This is the user's "guardrails as checkpoints" philosophy applied recursively — to the guardrail configuration itself.

The user's pattern throughout this project:

| Level | "Don't trust claims — prove it" |
|---|---|
| Tutorial steps | Agent can't say "done" — checkpoint proves it |
| Phase transitions | Can't advance without advance_checks passing |
| Agent knowledge | Agent can't see future steps — structural impossibility |
| **Configuration** | **Can't deploy a misspelled phase ID — generation-time validation catches it** ← NEW, same pattern |

Every layer applies the same principle: catch mistakes structurally, don't rely on runtime behavior to be correct by convention.

## No Concerns

- Not scope creep — it's validation for infrastructure the user requested
- Not complexity — a registry is a set of strings checked at generation time
- Consistent with existing codebase patterns — `generate_hooks.py` already validates rule IDs, trigger types, etc.

## One Note

This also helps tutorial authors (v2). When they write `phase_block: ["tutoral:ssh:step-3"]` with a typo, they get a clear error, not a guardrail that silently never activates. The registry protects both infrastructure authors (team workflow phases) and content authors (tutorial steps).
