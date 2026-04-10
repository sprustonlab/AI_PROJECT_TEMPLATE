# Composability Response: Phase Configuration Sync

**Reviewer:** Composability (Lead Architect)
**Prompt:** We removed activate_rules/deactivate_rules from phase files because they duplicated rules.yaml. Does the same logic apply to advance_checks and hints? How do we sync phase configuration across sources?

---

## The Duplication Test

The reason activate_rules/deactivate_rules were removed: they duplicated information that already had a natural home (rules.yaml). The test for any field in phase frontmatter is:

> **Does this field duplicate information that has a natural home elsewhere?**

Apply this test to each field:

| Field | Natural home | In phase file? | Duplication? |
|---|---|---|---|
| `activate_rules` / `deactivate_rules` | `rules.yaml` (rules define their own scoping) | Removed | Yes — rule scoping is a property of the rule |
| `advance_checks` | ? | Currently yes | **Analyze below** |
| `hints` | `hints/hints.py` (hints defined in Python) | Currently yes | **Analyze below** |

---

## Where Do Checks and Hints Naturally Live?

### Checks (advance_checks)

Today: no check configuration exists anywhere. Checks are a new primitive. There is no "other home" to duplicate.

The question is: are advance_checks a property of the phase, or a property of some other system?

**They're a property of the phase.** "What must be proven before advancing" is definitionally about the phase boundary. It doesn't make sense to say "FileExistsCheck on tests/test_example.py" without knowing which phase it gates. The check exists BECAUSE the phase exists.

Contrast with rules: R01 (pytest-output-block) exists independently of any phase. It was created before phases existed. Phase scoping was added to it later. The rule is the primary entity; the phase is a modifier.

For checks, the phase is the primary entity; the check is a detail of the phase.

### Hints

Today: hints are defined in Python (`hints/hints.py`), not YAML. The existing 7 hints are project-level (git-setup, guardrails-default-only, etc.) — none are phase-scoped.

Phase-scoped hints are new. They don't exist in the current system. Like checks, there is no "other home" to duplicate.

Are phase hints a property of the phase? **Yes.** "Show this guidance during this phase" is definitionally about the phase. The hint exists BECAUSE the phase exists.

---

## Analysis of Each Option

### Option 1: Everything in phase files (original spec, minus rules)

```yaml
# phase-02-run-test.md frontmatter
id: run-test
advance_checks:
  - type: command-output-check
    command: "pixi run pytest tests/test_example.py"
    pattern: "passed"
hints:
  - message: "Run: pixi run pytest tests/test_example.py"
    trigger: { type: phase-check-failed }
```

Rule scoping stays in `rules.yaml`. Checks and hints live in phase files.

| Criterion | Assessment |
|---|---|
| Single source of truth | **Yes** for checks and hints (defined only in phase file). **Yes** for rules (defined only in rules.yaml). No overlap. |
| Sync risk | **None.** Each concern has exactly one home. |
| Author experience | Phase author writes checks + hints in the phase file where they make sense. Rule author writes phase_block/phase_allow in rules.yaml where rules already live. |
| Composability | Phase file = gates + context. rules.yaml = guards. Clean separation by concern. |

### Option 2: Nothing in phase files (pure content)

```yaml
# phase-02-run-test.md frontmatter
id: run-test
title: "Run pytest"
# No checks, no hints — just markdown body below
```

Checks and hints live in separate config files (e.g., `checks.yaml`, `hints.yaml` per workflow).

| Criterion | Assessment |
|---|---|
| Single source of truth | Yes — each config file owns its domain. |
| Sync risk | **High.** Add a phase file, must also add entries to checks.yaml AND hints.yaml AND rules.yaml. Three files to keep in sync per phase. |
| Author experience | **Poor.** Author must cross-reference 3-4 files to understand one phase. Phase file alone is incomplete. |
| Composability | Clean separation, but at the cost of coherence. The phase is scattered across files. |

### Option 3: Generate frontmatter from other sources

Phase frontmatter is auto-generated from rules.yaml, checks.yaml, hints.yaml. A build step merges them into the phase file's YAML.

| Criterion | Assessment |
|---|---|
| Single source of truth | Yes — sources are the config files. Phase file is derived. |
| Sync risk | **Medium.** The generation step can fail or go stale. "Did you run the generator?" becomes a new failure mode. |
| Author experience | **Confusing.** Phase file frontmatter exists on disk but isn't authoritative. Edits get overwritten. Two mental models (source files vs. generated output). |
| Composability | Adds a build step to what is currently zero-build. Generated artifacts are fragile. |

### Option 4: Phase file owns per-phase concerns, rules.yaml owns per-rule concerns (current spec after the activate_rules removal)

This is Option 1, but with a clear principle for WHY:

- **Per-phase concerns** → phase file frontmatter (checks, hints)
- **Per-rule concerns** → rules.yaml (phase_block, phase_allow)

The dividing line: **what is the primary entity?**

| If the primary entity is... | Then config lives in... | Because... |
|---|---|---|
| The phase | Phase file | "This phase requires X" — X doesn't exist without the phase |
| The rule | rules.yaml | "This rule is exempt during Y" — the rule exists independently |

| Criterion | Assessment |
|---|---|
| Single source of truth | **Yes.** No field appears in two places. |
| Sync risk | **None.** Each concern has one home. |
| Author experience | **Good.** Phase author sees everything about the phase in one file (gates + context + instructions). Rule author sees everything about the rule in rules.yaml (trigger, enforcement, phase scoping). |
| Composability | Two concerns, two homes, zero overlap. |

---

## Recommendation: Option 4

Option 4 is what the spec already describes after the activate_rules removal. The question was whether to go further and remove checks and hints too. The answer is **no**, because:

1. **The duplication that triggered the activate_rules removal doesn't exist for checks and hints.** Rules had a natural home (rules.yaml) before phases existed. Checks and hints for phases are new — they have no other home to duplicate.

2. **Checks and hints are per-phase by nature.** "What must be proven before advancing past this phase" and "what guidance to show during this phase" are definitionally properties of the phase. Moving them elsewhere scatters the phase definition across files (Option 2) or adds a build step (Option 3).

3. **Rules are per-rule by nature.** "When should this rule be suspended" is a property of the rule. That's why phase_block/phase_allow on rules.yaml works — it's the rule saying "not during testing," not the phase saying "turn off R01."

The principle:

> **If the config wouldn't exist without the phase, it goes in the phase file.
> If the config wouldn't exist without the rule, it goes in rules.yaml.**

advance_checks wouldn't exist without the phase. hints wouldn't exist without the phase. phase_block wouldn't exist without the rule.

No changes to SPECIFICATION.md needed. The current structure (after activate_rules removal) already implements Option 4.

---

## Summary

| Concern | Home | Why |
|---|---|---|
| Gate checks (advance_checks) | Phase file frontmatter | Per-phase: "what must be proven before leaving this phase" |
| Phase hints | Phase file frontmatter | Per-phase: "what guidance during this phase" |
| Rule scoping (phase_block/phase_allow) | rules.yaml | Per-rule: "when should this rule be suspended" |
| Phase instructions | Phase file markdown body | Per-phase: "what to do in this phase" |

No duplication. No sync risk. Each concern has exactly one home.
