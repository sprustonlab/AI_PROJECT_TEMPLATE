# Experiment: Short Spec vs Long Spec Implementation

**Date:** 2026-04-09
**Goal:** Compare implementation quality and speed when giving an implementer agent a lean spec (163 lines) vs a detailed spec (~1076 lines) describing the same system.

**Setup:**
- Both agents started from the same `develop` branch in separate git worktrees
- Both read the same existing source files (`_cluster.py`, `lsf.py`, `slurm.py`, YAML templates, tests)
- Neither had seen the spec before — fresh agents
- Both told: "implement everything, write tests, commit when done"

---

## Impl-Short (163-line spec)

| Metric | Value |
|--------|-------|
| **Spec size** | 163 lines |
| **Time to complete** | ~8 minutes (worktree created 19:36, commit at 19:44) |
| **Commit** | `e2df54f` |
| **Files changed** | 7 files, +1,397 / -49 lines |
| **Tests written** | 69 new (108 total including existing) |
| **All tests pass?** | Yes |
| **Decisions made independently** | 4 (legacy fallback, shlex import, readiness thresholds, spec delivery method) |
| **Questions asked** | 1 (spec file missing — resolved) |
| **Blockers** | 1 (spec not on branch — resolved by sending inline) |

### Files produced:
- `template/.claude/workflows/cluster_setup.md` — 130 lines
- `template/mcp_tools/_cluster.py` — +282 lines
- `template/mcp_tools/lsf.py` — +101/-49 lines
- `template/mcp_tools/slurm.py` — +97 lines
- `template/mcp_tools/lsf.yaml.jinja` — +16 lines
- `template/mcp_tools/slurm.yaml.jinja` — +16 lines
- `tests/test_cluster_path_mapping.py` — 804 lines (69 tests)

---

## Impl-Long (1076-line spec)

| Metric | Value |
|--------|-------|
| **Spec size** | 1,076 lines |
| **Time to complete** | ~9 minutes (worktree created 19:36, commit at 19:45) |
| **Commit** | `2121c63` |
| **Files changed** | 8 files, +2,565 / -53 lines (includes spec file itself: +1,076) |
| **Code-only changes** | 7 files, +1,489 / -53 lines |
| **Tests written** | 81 new (120 total including existing) |
| **All tests pass?** | Yes |
| **Decisions made independently** | 4 (legacy fallback via optional params, lazy config, workflow as pure markdown, backward compat for _read_logs) |
| **Questions asked** | 0 (after receiving spec) |
| **Blockers** | 2 (spec file missing x2 — resolved by file copy + absolute path) |

### Files produced:
- `template/.claude/workflows/cluster_setup.md` — 99 lines
- `template/mcp_tools/_cluster.py` — +346 lines
- `template/mcp_tools/lsf.py` — +105/-53 lines
- `template/mcp_tools/slurm.py` — +96 lines
- `template/mcp_tools/lsf.yaml.jinja` — +21 lines
- `template/mcp_tools/slurm.yaml.jinja` — +21 lines
- `tests/test_cluster_path_mapping.py` — 854 lines (81 tests, organized in 13 test classes)

---

## Comparison

| Dimension | Short Spec | Long Spec | Notes |
|-----------|-----------|-----------|-------|
| **Spec size** | 163 lines | 1,076 lines | 6.6x difference |
| **Time** | ~8 min | ~9 min | Near identical |
| **Tests written** | 69 | 81 | Long wrote 17% more tests |
| **Tests passing** | 108/108 | 120/120 | Both 100% |
| **Code added** | +1,397 lines | +1,489 lines | Long wrote ~7% more code |
| **Test organization** | Functions | 13 classes | Long mirrored spec's test structure |
| **Independent decisions** | 4 | 4 | Same count |
| **Blockers** | 1 | 2 | Both hit same issue (spec not on branch) |
| **Workflow file** | 130 lines | 99 lines | Short wrote MORE workflow detail |
| **_cluster.py additions** | +282 lines | +346 lines | Long wrote ~23% more infra code |

## Observations

1. **Speed was nearly identical** (~8 vs ~9 min). The long spec's extra 900 lines of detail didn't slow down the agent — but also didn't speed it up.

2. **Long spec produced more tests** (81 vs 69). The detailed test plan in the long spec (with specific parameterized inputs) directly translated to more test cases. The short spec's "you decide HOW" left the implementer to choose coverage.

3. **Long spec mirrored spec structure** in tests (13 classes matching spec's 13 test functions). Short spec organized tests by concept without prescribed structure.

4. **Short spec produced a MORE detailed workflow file** (130 vs 99 lines). With less spec to follow, the short-spec agent added more of its own thinking to the workflow design.

5. **Both made the same 4 independent decisions** around backward compatibility of existing functions — showing this is a real design gap regardless of spec detail.

6. **Both hit the same blocker** (spec files not committed to branch). The long spec agent had more trouble finding its file (2 attempts vs 1).

7. **Code quality comparison** — see Leadership Review below.

---

## Leadership Code Review (5 reviewers, all files)

**Verdict: Unanimous (B) Cherry-pick — Impl-Long as base, cherry-pick from Short**

### Bugs Found

| Bug | In | Severity | Fix |
|-----|----|----------|-----|
| `_normalize_local_path("/")` → `""` (empty string) | **Short** | Critical | Add `if p != "/" else p` guard (Long has it) |
| `to_cluster()` passthrough returns raw backslashes | **Long** | Critical | Return `normalized` not `local_path` |
| `to_local()` passthrough returns raw input | **Long** | Critical | Return `normalized` not `cluster_path` |
| Normalization order: expanduser before backslash fix | **Long** | Medium | Do backslash→`/` FIRST (Short's order) |
| `if readiness:` treats `"ready"` as truthy | **Long** | Medium | Return `None` for ready or fix comparison |
| SSHLogReader no try/except on `_run_ssh` | **Long** | Low | Add TimeoutExpired/OSError handling |

### Cherry-pick Plan

**Keep from Long:**
- PathMapper with two pre-sorted rule lists (cleaner, early exit)
- `_create_path_mapper()` factory with full config validation
- `LogReader` Protocol with `read_tail(cluster_path, tail)` naming
- AutoLogReader via dependency injection (testable)
- `_resolve_log_path()` as separate testable function
- `_error_with_hint()` structured error guidance
- `cluster_submit` blocking on `needs_setup`
- Tool descriptions (richer, spec-aligned)
- Test suite (81 tests, spec-aligned classes, config validation, round-trip)
- Workflow file (diagnose meta-phase, structured outputs, fix_phase mapping)
- Debug logging on SSH failures/fallback

**Cherry-pick from Short into Long:**
- `_normalize_local_path` order: backslash→`/` first, then expanduser, then expandvars
- Fix passthrough returns: `return normalized` not raw input
- `_translate_status_paths()` as standalone helper (DRY, spec §5.3)
- `has_rules` property on PathMapper
- Jinja placeholder detection: `"{{" in ssh_target` → `"needs_setup"`
- try/except in SSHLogReader (TimeoutExpired, OSError)
- Workflow file existence test
- `_check_config_readiness()` returning `"ready"` string (not None)

### Reviewer Highlights

- **Composability3:** Long's architecture is superior (protocol-typed returns, DI in AutoLogReader, validation factory). Short's `_translate_status_paths` is DRYer. Neither should have optional `log_reader` in `_read_logs`.
- **Skeptic3:** Long wins on validation/error handling. Short wins on placeholder detection. Short has root-path normalization bug. Long has missing exception handling in SSHLogReader.
- **UserAlignment3:** Long's tool descriptions and graduated readiness behavior are better UX. Long's workflow has diagnose meta-phase (better entry point). Found Long's readiness truthiness bug.
- **Terminology3:** Long wins on naming (cluster_path params, behavioral test names, annotated comments). Short's `read_log` vs Long's `read_tail` — Long matches spec better.
- **Researcher:** Long has passthrough backslash bug (debugpy Issue #1301). Long has normalization order bug (debugpy Issue #1240). Short has root-path bug. Long's validation is industry best practice.

## Conclusion

**Spec length had minimal impact on speed** (~8 vs ~9 min) **but significant impact on code quality:**

- **Long spec produced better architecture:** protocol-typed returns, validation factory, pre-sorted rule lists, DI composition, debug logging, structured error hints. The code samples in the long spec guided the agent toward proven patterns.
- **Long spec produced better tests:** 81 vs 69, config validation coverage, round-trip tests, spec-aligned naming.
- **Short spec produced some better patterns:** normalization order, DRY status translation helper, Jinja placeholder detection, `has_rules` property. These came from the agent thinking independently rather than following prescriptive code samples.
- **Both had bugs** — but different bugs. Long's bugs were in the spec's own code samples (passthrough returns, normalization order). Short's bugs were in areas the short spec didn't specify (root path handling, config validation).

**Key insight:** The long spec's code samples propagated their own bugs into the implementation. The short spec's lack of code samples caused the agent to miss edge cases the spec didn't mention. **Neither spec alone produced bug-free code.** The optimal approach is a short spec + code review, which is exactly what this experiment validated.

**Recommendation:** Use short specs for speed. Use leadership review to catch bugs from both approaches. Cherry-pick the best of both.
