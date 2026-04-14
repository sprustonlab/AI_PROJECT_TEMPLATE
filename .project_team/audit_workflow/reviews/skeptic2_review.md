# Skeptic Fresh Review -- Specification v3

Reviewer: Skeptic (fresh review, no prior context carried over)
Date: 2026-04-13

Files reviewed:
- `.project_team/audit_workflow/specification/SPECIFICATION.md` (the v3 spec)
- `scripts/mine_patterns.py` (existing pattern mining tool)
- `submodules/claudechic/claudechic/chicsessions.py` (chicsession data model)
- `CLAUDE.md` (cross-platform rules)
- `workflows/` (existing workflow examples)
- `template/` (template directory structure)
- `copier.yml` (template configuration and exclude rules)

---

## 1. LLM-Driven Suggestions: NEW Risks

### CRITICAL: No validation gate for LLM-generated YAML

The spec says `suggestions.py` provides "YAML validation (ensure generated YAML is parseable)" but this is a code utility the LLM must *choose* to use. The suggest phase instructions (`suggest.md`) tell the LLM to "validate all YAML output before writing" -- but there is no enforcement mechanism. If the LLM writes malformed YAML to `suggestions.json`, nothing stops it.

### Concrete risks

- **Hallucinated file paths in ArtifactRef.** The LLM generates `file_path` strings for suggestions. Nothing validates these paths exist. A suggestion saying "modify `workflows/project_team/implementer/design.md`" when the file is actually `implementation.md` is worse than no suggestion -- it wastes user time.
- **Invalid rule/hint YAML syntax.** The LLM must generate valid `detect.pattern` regex, valid `trigger` values (e.g., `PreToolUse/Write`), valid `lifecycle` enums (`show-once`, `show-every-session`, `show-until-resolved`, `cooldown-period`). The `suggest.md` phase markdown would need to enumerate ALL valid values -- essentially embedding a mini-schema reference. Is that realistic given context window constraints?
- **Suggestions that contradict existing rules.** The cross-reference dedup checks for *matching* definitions but not *conflicting* ones. The LLM could suggest a rule that contradicts an existing rule.
- **proposed_content drift.** The LLM reads `current_content` from a file, then proposes changes. But between the analyze and suggest phases, the user could have modified those files. The suggestion becomes a stale diff.

### Recommendation

Add a programmatic validation step AFTER the LLM writes `suggestions.json` -- a post-write check that:
1. Parses all YAML snippets with `yaml.safe_load`
2. Validates ArtifactRef paths exist on disk
3. Validates enum values (`trigger`, `lifecycle`, `enforcement`, `gap_type`) against known sets
4. Flags but does not block suggestions that reference modified files

This should be a `validate_suggestions()` function in `suggestions.py` called by the report phase, NOT left to the LLM's judgment.

---

## 2. Template Shipping: What Breaks in Generated Projects

### MAJOR ISSUE: scripts/audit/ and session_lib.py don't exist in the template yet

Looking at the actual codebase:
- `template/scripts/` contains only `mine_patterns.py`
- The spec puts audit code in `scripts/audit/` and `scripts/session_lib.py`
- `scripts/` is NOT excluded in `copier.yml`, meaning ALL of `scripts/audit/` would ship to generated projects

### The spec must answer: does scripts/audit/ ship in the template?

**If YES (audit Python modules ship):**
- End users get `session_lib.py` + the entire `scripts/audit/` package
- End users also get `mine_patterns.py` which would need to import from `session_lib.py`
- The template's `mine_patterns.py` must be updated with the same extraction refactor
- This works but the spec doesn't acknowledge it

**If NO (only workflow YAML/markdown ships):**
- The workflow phase markdown instructions tell the auditor agent to use these modules, but they don't exist in the generated project
- The LLM would have to do everything from scratch each time
- This defeats the purpose of the code pipeline

### The spec MUST explicitly state which files go into template/ vs. stay repo-only

Section 9 (File Inventory) lists 22 new files but doesn't distinguish template vs. repo-only. This is a significant gap.

### Additional template concerns

- **Hardcoded agent roles.** `mine_patterns.py` has `DEFAULT_AGENT_ROLES` with roles like "Composability", "Terminology Guardian", "Sync Coordinator" -- these are THIS repo's roles, not the end user's. After extraction to `session_lib.py`, roles must be configurable or derived from the user's actual workflow manifests.
- **Hardcoded output paths.** `audit.yaml` uses `.project_team/audit_workflow/` as output directory for `parsed_timeline.json`, `findings.json`, `suggestions.json`, `AUDIT_REPORT.md`. Generated projects may not have `.project_team/`. The output path should either be configurable or use a more generic location.
- **copier.yml needs updating.** The spec mentions updating copier.yml in Section 9, but doesn't specify what changes. Need to add exclude rules for audit test fixtures and potentially conditional inclusion based on `quick_start` preset.

---

## 3. The Code/LLM Boundary

### The boundary is drawn correctly conceptually but underspecified operationally

The spec says: "Code detects THAT corrections happened. LLM analyzes WHY." This is the right idea. But:

**The GapDetectors (code) are doing more than detection.** Consider `PhaseGapDetector` -- it must "check if the correction topic is addressed in the relevant phase markdown." How? This requires understanding the *semantic content* of both the correction and the phase markdown. That is not a regex operation -- it is an NLU task. The spec does not specify the algorithm.

Possible approaches (each with different trade-offs):
1. **Keyword extraction + matching** -- extract keywords from correction text, check if they appear in phase markdown. Fast but high false-negative rate (synonyms, paraphrases).
2. **TF-IDF similarity** -- compute similarity between correction text and phase markdown sections. Better but adds a dependency and complexity.
3. **Always emit findings, let LLM filter** -- GapDetectors emit a finding for every correction signal, and the LLM in the suggest phase decides which ones are real gaps. Simplest code but floods the LLM with noise.

**Same problem for `CheckGapDetector`**: "Check if agents are skipping steps that should be enforced by advance checks." How does code determine that a correction signal represents a "skipped step"? This requires understanding the intent behind the correction.

**Risk: The GapDetectors become either (a) so simple they are useless (keyword matching that misses most gaps) or (b) so complex they are reimplementing what the LLM should do.**

### Recommendation

Be explicit about what each GapDetector does algorithmically. My suggestion: make them deliberately simple (keyword/pattern matchers that over-generate findings) and let the LLM in the suggest phase filter and refine. Document the expected false-positive rate and the LLM's filtering role.

---

## 4. session_lib.py Extraction: Import Chain Problem

### Where does session_lib.py live in generated projects?

- In this repo: `scripts/session_lib.py`
- In template: `template/scripts/session_lib.py` (presumably)
- In generated project: `scripts/session_lib.py`

### The extraction breaks mine_patterns.py independence

Current `mine_patterns.py` has ZERO sibling imports -- it is fully self-contained. After extraction, it depends on `session_lib.py` being importable. This needs one of:

1. **A `scripts/__init__.py`** (making `scripts/` a package) -- changes the semantics of the directory for all users
2. **`sys.path` manipulation in `mine_patterns.py`** -- fragile, non-standard
3. **Relative import via shared parent** -- requires package structure
4. **Template version stays self-contained** (duplicate the shared code) -- defeats the extraction purpose

None of these options are addressed in the spec. This is a concrete implementation blocker.

### Recommendation

Add a `scripts/__init__.py` (can be empty) and use relative imports. Document this decision in the spec. Update `template/scripts/` to include `__init__.py`. Verify that `mine_patterns.py` can still be invoked as `python scripts/mine_patterns.py` (it can, with `from __future__ import annotations` and careful import handling).

---

## 5. Testing LLM-Generated Suggestions

### The testing strategy has a fundamental gap: it does not test the LLM

The spec's test plan (Section 8) tests:
- Parser correctness (good)
- Scoring correctness (good)
- Cross-reference logic (good)
- Suggestion *structure* (AuditSuggestion dataclass fields)
- YAML parseability of suggestion snippets
- Report formatting

### What is NOT tested

- Whether `suggest.md` instructions actually produce good suggestions when given to an LLM
- Whether the LLM follows the evidence thresholds (2+ for markdown/hints, 3+ for checks/rules)
- Whether the LLM generates valid ArtifactRef paths
- Whether the LLM output can be deserialized into AuditSuggestion objects
- Whether the LLM generates suggestions that are actually copy-paste ready (valid syntax)

### This is understandable but must be acknowledged

You cannot deterministically test LLM output. But the spec should acknowledge this gap and propose mitigations:

1. **Golden-path integration tests with pre-canned LLM responses** -- mock the LLM, test the full pipeline with known-good suggestion JSON
2. **A "suggestion linter"** (`validate_suggestions()` from Recommendation #1) that validates LLM output post-hoc and is itself well-tested
3. **Manual QA checklist for `suggest.md` prompt engineering** -- when modifying `suggest.md`, run N real audit sessions and verify suggestion quality
4. **Regression fixtures** -- save real LLM-generated suggestions.json files as test fixtures; verify the pipeline handles them correctly

---

## 6. Cross-Platform (Windows)

### New Windows risks from template shipping

- **ArtifactRef.file_path is `str` not `Path`.** The LLM generates file paths as strings. On Windows, these could use backslashes depending on how the LLM sees the filesystem. The report renderer and validator must normalize paths. Consider making `file_path` a `Path` or at minimum document that it must use forward slashes.
- **JSONL file discovery assumes `~/.claude/projects/`.** `Path.home() / ".claude" / "projects"` works on Windows, but Claude Code's actual session storage path may differ on Windows. The spec inherits this assumption from `mine_patterns.py`.
- **Output directory `.project_team/audit_workflow/`** -- the `.` prefix is just a regular directory on Windows (no hiding behavior). Not a bug but could confuse Windows users expecting it to be hidden.

### These are minor

The main cross-platform rules (encoding='utf-8', pathlib, ASCII-only, no em-dash) are addressed in the spec's Section 5.1. The em-dash warning for `mine_patterns.py` line 304 is a good catch.

---

## 7. Does This Solve the Original Problem (Issue #29)?

### The spec is well-aimed but has a bootstrapping problem

**Cold-start problem:** The audit workflow requires existing sessions with corrections to analyze. A new user who just generated a project has zero sessions. The workflow would report "no findings." This is correct behavior but poor UX -- the user activates `/audit` expecting value and gets nothing.

**Recommendation:** The `identity.md` or a phase hint should handle this gracefully:
- Detect zero sessions and explain that the audit becomes useful after several workflow sessions
- Suggest running it after completing at least one full workflow cycle
- Consider a "sample findings" mode using bundled fixture data to demonstrate what the audit produces

### The value delivery chain is long

User runs sessions -> corrections accumulate -> user runs `/audit` -> parse -> analyze -> cross-reference -> LLM suggests -> user reads report -> user manually applies suggestions -> user runs more sessions -> repeat.

That is a LOT of steps before value materializes. Consider a "quick win" mode:
- Skip the full pipeline
- Just show correction hotspots (phase + agent with highest correction rate)
- No LLM suggestion generation needed
- Could be a `--quick` flag or automatic when < N sessions are available

---

## Summary: Top 5 Action Items (Priority Order)

1. **Add programmatic validation of LLM output** -- `validate_suggestions()` function that checks YAML parseability, path existence, and enum validity. Do not trust the LLM to self-validate. This is the highest-risk gap.

2. **Explicitly specify template vs. repo-only files** in Section 9. State whether `scripts/audit/` and `scripts/session_lib.py` ship in template. Address the import chain problem (recommend `scripts/__init__.py`). Update copier.yml specification.

3. **Define GapDetector algorithms concretely** -- specify whether they are keyword matchers, TF-IDF, or LLM-delegated. Current ambiguity will cause implementation confusion. Recommend deliberately simple (over-generate, let LLM filter).

4. **Acknowledge the LLM testing gap** and add mitigation strategies: golden-path mocks, post-hoc suggestion linter, QA checklist for `suggest.md`, regression fixtures.

5. **Address cold-start UX** for new generated projects with zero session history. Add graceful "no sessions yet" handling and consider a quick-win hotspot mode.

---

## Overall Assessment

The v3 spec is significantly improved over v2. The code/LLM boundary is the right architectural decision. The main risks are **operational** (validation, template plumbing, import chains) rather than **architectural**. The five action items above are all addressable without redesigning the system.
