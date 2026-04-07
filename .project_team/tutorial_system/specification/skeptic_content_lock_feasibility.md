# Skeptic Response: Content Lock Feasibility Research

## Does This Change My Assessment?

No. It confirms it. My previous review said:

> Content lock is a good prompt engineering discipline, not a new mechanism to build. The real enforcement is guardrail checkpoints.

The research quantifies what I called "attention focusing" — the JetBrains numbers (2.6% solve rate improvement, 52% cost reduction, >30% degradation from irrelevant context) are the empirical backing for the same claim. Content lock works because less irrelevant context = better performance, not because the agent can't access other files.

**The research and my review agree completely. Nothing changes.**

---

## Did We Oversell Content Lock?

**Yes, briefly, then we corrected.** The original discussion framed it as "the agent only gets the MD file for its current phase" — which implies information hiding. The research correctly reframes it as attention management. My review reached the same conclusion independently. The Researcher's framing is better: call it what it is.

**Recommendation for the spec:** Use the term "phase-scoped context" not "content lock." "Lock" implies security enforcement. "Phase-scoped context" says what it actually does — the agent's context contains only its current phase's instructions.

---

## Is Level 1 Right for v1?

**Yes.** The Researcher recommends: serve only current phase file + warn guardrail on reading other phase files. Let me verify this is consistent with the architecture.

Level 1 requires:
1. Tutorial engine serves one step's markdown at a time → **already in the architecture**
2. A `warn`-level Read guardrail for out-of-phase file access → **~5 lines in rules.yaml, no generate_hooks.py changes** (warn rules for Read already work — see the existing hook infrastructure)

Total implementation cost for "content lock" at Level 1: **~5 lines of YAML + documentation of the design principle.** This is negligible. It's not a feature to build; it's a guardrail rule to add.

The warn (not deny) level is correct because:
- The agent occasionally needs to read related files for legitimate reasons (debugging, understanding context)
- Warn creates a record in hits.jsonl (audit trail) without blocking recovery scenarios
- The checkpoint guardrail is the hard enforcement — content lock is the soft focus mechanism

---

## One Concern: The Warn Rule Pattern Matching

The Researcher proposes:

```yaml
- id: R10
  name: phase-file-advisory
  trigger: PreToolUse/Read
  enforcement: warn
  detect:
    type: regex_match
    field: file_path
    pattern: 'coordinator/phase-\d+'
  message: "You are reading a phase file. Confirm you need this for your current phase."
```

This fires on ALL phase file reads, including the current phase's file. The agent reads `phase-04-impl.md` (its assigned file) and gets warned. That's a false positive on every turn.

**Fix:** The rule needs phase awareness — only warn when reading a phase file that ISN'T the current phase. This requires the hook to know the current phase, which requires reading `phase_state.json`. That's the Level 2 mechanism.

**Simpler fix for v1:** Don't use a guardrail rule at all. Just serve the right file and rely on prompt focus. Level 0, not Level 1. The research shows Level 0 (prompt-only) already gives ~70% focus improvement. The marginal benefit of a warn rule that can't distinguish current from non-current phase files is near zero — and a rule that fires false positives is worse than no rule.

**Revised recommendation:** Level 0 for v1 (serve current phase file only, no guardrail rule). Level 1 requires phase-aware hooks, which is the same prerequisite as Level 2. Don't do either until phase-scoped guardrails are implemented. The tutorial engine already does Level 0 by construction — it gives the agent one step at a time.

---

## Summary

| Question | Answer |
|---|---|
| Does the research change the architecture? | No. Confirms it. |
| Did we oversell content lock? | Briefly. Now correctly framed as attention management. |
| What level for v1? | Level 0 (prompt focus only). Level 1 requires phase-aware hooks which are v2. |
| Implementation cost? | Zero. The tutorial engine already serves one step at a time. That IS content lock. |
| Naming? | Use "phase-scoped context" not "content lock." |
