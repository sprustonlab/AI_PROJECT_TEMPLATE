# Skeptic Review: SPECIFICATION.md v2

## Verdict: PASS

This spec is correct. It solves what was asked for without inventing infrastructure. The v1→v2 rewrite eliminated every piece of speculative generality I flagged. I have two minor notes and one question for the user. None are blockers.

---

## 1. Is All Speculative Infrastructure Gone?

**YES.** Clean sweep.

| v1 Infrastructure | v2 Status |
|-------------------|-----------|
| `plugin.yaml` per plugin (10 fields, 1 consumer) | Gone |
| `plugins/` directory in generated project | Gone |
| `_plugin_deps` YAML parsing at runtime | Gone |
| `_plugin_enabled` awk parser for project.yaml | Gone |
| `project.yaml` manifest | Gone |
| Backend dispatch loop (`envs/backends/*/`) | Gone |
| 6 shell scripts per backend | Gone |
| Plugin activation order array | Gone |

What replaced it: nothing. The existing `activate` script already scans `envs/*.yml`, already adds `commands/` to PATH, already auto-chmods scripts. The spec correctly identified that **the directory structure was already the plugin system**. Copier selects which files land in which directories. After that, everything discovers itself through existing conventions.

This is the right answer. No notes.

---

## 2. Is the `rules.d/` Proposal the Right Scope?

**YES.** It's the only new system in the spec, and it's justified.

**Why it's needed:** The current `rules.yaml` is a single file. When contributed rule sets exist (scientific guardrails, HPC rules), they'd all collide in one file — merge conflicts, unclear ownership, no way to add/remove a rule set cleanly.

**Why it's the right scope:** `rules.d/` is a well-understood Unix convention (`cron.d/`, `conf.d/`, `systemd/*.d/`). The change to `generate_hooks.py` is small: glob `rules.d/*.yaml`, append to rule list, validate IDs don't collide. No new systems, no new abstractions.

**One minor note:** The spec says IDs "must not collide (enforced at validation time)" (§3.5) but doesn't specify what happens on collision. I'd expect `generate_hooks.py` to exit non-zero with a message naming both files. This is an implementation detail, not a spec gap — just mentioning it so the implementer handles it explicitly rather than silently using whichever loads last.

---

## 3. Are the Contributor Templates Concrete Enough?

**YES.** Each seam has a "How to Add" section with numbered steps and concrete file content. The R user running example (§2) threads through the entire spec, showing what a real user actually types. The command wrapper template (§3.2 Pattern A) is copy-pasteable.

The role template (§3.4) includes all required elements (heading, responsibility, output format, interaction table, authority bounds). The rule set template (§3.5) shows a complete YAML entry with ID namespacing.

These are usable as-is. No notes.

---

## 4. Does It Stay Lightweight?

**YES.** The explicit scope limits (§10) are exactly the list I demanded in my Phase 2 review. The spec adds one new mechanism (`rules.d/` merge) and one new tool (Copier template). Everything else is documenting and codifying what already exists.

Line count check: 7 code changes (§8), 4 of which are "tiny." The medium ones are the pattern miner port (unavoidable — it's a user requirement) and the Copier template (unavoidable — it's the onboarding mechanism). No framework tax.

---

## 5. Are the 7 Code Changes Necessary and Sufficient?

| # | Change | Necessary? | Sufficient? |
|---|--------|-----------|-------------|
| 1 | `rules.d/` in generate_hooks.py | Yes — enables contributed rule sets without file conflicts | Yes |
| 2 | Env var rename in role_guard.py | Yes — removes claudechic coupling | Yes — backward-compatible fallback included |
| 3 | Env var rename in claudechic | Yes — must match #2 | Yes |
| 4 | Pattern miner port | Yes — explicit user requirement | Yes — all 6 JSONL mitigations included (§6.3.1–6.3.6), including the snapshot tests I required |
| 5 | Copier template | Yes — onboarding mechanism | Yes |
| 6 | `require_env` relaxation | Yes — existing codebase integration | Yes — concrete before/after code shown |
| 7 | Contributor docs/templates | Yes — the seams need to be documented to be conventions | Yes |

**All necessary. All sufficient.** No missing changes that I can identify. No unnecessary additions.

One observation: change #5 (Copier template) is the largest and most complex piece of work. The copier.yml (§4.2) includes `project_type`, `science_domain`, and `autonomous_agents` questions that gate scaffolding for scientific computing patterns (§4.4). This is scope that didn't exist in v1. It's well-motivated (the Researcher found strong evidence for the overnight agent pattern), but the implementer should build the base Copier template first (just the 3 add-on toggles + existing codebase), then layer on the scientific questions.

---

## 6. `.claude/` Merge Spec

The v1 gap I flagged (merge algorithm underspecified) is now addressed in §5.2 step 4:

> - **Arrays:** Template entries appended to existing arrays
> - **Objects:** Template keys added; existing keys preserved
> - **Scalar conflicts:** Warn and preserve user's value
> - **Implementation:** Python merge script in Copier post-generation hook

This is concrete enough. The implementer knows what to build.

---

## 7. Pattern Miner Snapshot Tests

The v1 gap I flagged (missing snapshot JSONL tests) is now included as §6.3.6 with:
- Fixture files (`v2.1.59_main_session.jsonl`, `v2.1.59_subagent_session.jsonl`)
- Unit tests for the parsing layer
- Regression tests with snapshot comparison
- Maintenance rule for capturing new fixtures on Claude Code updates

This is complete. No notes.

---

## Minor Notes (Not Blockers)

### Note 1: `rules.d/` collision handling
As mentioned in §2 above — specify that `generate_hooks.py` exits non-zero on ID collision. Implementation detail, not a spec gap.

### Note 2: Copier scope ordering
The scientific computing scaffolding (§4.4: CLAUDE.md, CHANGELOG.md, test oracles, stricter guardrails) is good but should be implemented after the base template. Suggest the implementer treat the `autonomous_agents` path as Phase 2 of the Copier work.

---

## Question for the User (Not a Blocker)

§1.3 makes claudechic part of the **base** (always present). This means every project created from this template includes claudechic, its conda env, and the git submodule. Is that correct? A user who just wants env management + guardrails (no TUI) would still get claudechic files.

The v1 spec had claudechic as an optional add-on. The v2 spec makes it mandatory. Both are defensible — this IS an AI project template, so claudechic being the point makes sense. Just flagging the change for user confirmation.

---

## Summary

**PASS.** The spec is complete, correct, and as simple as possible — in that order. Ship it.
