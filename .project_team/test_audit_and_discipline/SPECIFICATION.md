# Specification: test_audit_and_discipline

## User Decisions (Locked)

| # | Decision |
|---|---|
| 1 | Block **full-suite runs only** — targeted single-test/file runs pass through |
| 2 | **UTC** timestamps |
| 3 | **Dual output** — `.xml` (JUnit) + `.log` (tee) for every run |
| 4 | **Fix fixtures for xdist** — don't mark `serial`, rebuild to be parallel-safe |
| 5 | **Submodule tests in scope** (`submodules/claudechic/tests/`) |
| 6 | **`.test_results/`** directory, gitignored |
| 7 | **Measure baseline timing first** before xdist work |

---

## Axis 1: Claude Code Hook — Block Bare `pytest`

**Goal:** Prevent full-suite pytest runs that don't save results.

**Mechanism:** A `deny` rule in `global/rules.yaml` (claudechic rule system), using the existing pattern alongside `no_rm_rf`, `warn_sudo`, and `log_git_operations`.

**Rule definition:**
- `id: no_bare_pytest`
- `trigger: PreToolUse/Bash`
- `enforcement: deny`
- `detect.pattern`: regex matching pytest invocations without output saving
- BLOCK if: command runs pytest with no specific test file target AND no output capture (`tee`, `>`, `--junitxml` pointing to `.test_results/`)
- ALLOW if: command targets a specific file/function (`pytest tests/test_foo.py::test_bar`)
- ALLOW if: command includes output to `.test_results/` (via `tee`, redirect, or `--junitxml`)
- Must catch variants: `pytest`, `pixi run pytest`, `python -m pytest`

**Required output format for full-suite runs:**
```bash
pytest --junitxml=.test_results/YYYY-MM-DD_HHMMSS.xml --tb=short 2>&1 | tee .test_results/YYYY-MM-DD_HHMMSS.log
```

**Timestamps:** UTC, format `YYYY-MM-DD_HHMMSS`, filesystem-safe (no colons).

**Infrastructure:**
- Create `.test_results/` directory
- Add `.test_results/` to `.gitignore`
- New rule in `global/rules.yaml`

**Escape hatch:** Agent can request override (standard claudechic deny behavior). CI has its own artifact saving.

---

## Axis 2: Slow Test Triage & xdist Compatibility

**Step 1: Measure baseline**
- Run `pytest --durations=0` on the full suite (including slow) and save results
- Cross-reference actual durations with existing markers
- Any test >30s without `@pytest.mark.slow` → add marker + explicit timeout override

**Step 2: Fix xdist-incompatible fixtures**
- `e2e_project` (module-scoped in `tests/conftest.py`) — rebuild using `FileLock` + `tmp_path_factory.getbasetemp().parent` pattern so multiple workers can share safely
- `generated_project` in `test_e2e_smoke.py` — same treatment
- `test_mcp_integration.py` `set_app()` global state — isolate per-test
- `test_cluster_path_mapping.py` / `test_cluster_tools.py` `sys.modules` mutation — verify safe under xdist (separate processes), document

**Step 3: Enable xdist**
- Add `-n auto` to default `addopts` (or provide a wrapper command)
- Use `--dist loadscope` to keep module-scoped fixture tests on same worker
- Verify all tests pass with `pytest -n auto`

**Slow test threshold:** >30s (already codified in pyproject.toml)
**Timeout gap:** Verify all `@pytest.mark.slow` tests have explicit `@pytest.mark.timeout(N)` overrides above the default 30s.

---

## Axis 3: Critical Test Quality Audit

**Scope:** ALL test files in:
- `tests/` (13 files)
- `submodules/claudechic/tests/` (filtered to `test_workflow_*`, `test_hints_*`)
- `scripts/tests/` (2 files)

**Classification (3 buckets per Skeptic):**
1. **Intent-based** — tests behavior/contracts, survives refactoring → leave alone
2. **Necessarily implementation-coupled** — parser tests, regression tests for specific bugs, format validators → label, don't fix
3. **Gratuitously implementation-coupled** — will break on any refactor for no safety benefit → **rewrite these**

**Heuristics for bucket 3 (from Researcher):**
- Would the test break if you refactored internals without changing external behavior?
- Does it test a private/internal method directly?
- Does it mock 3+ collaborators to isolate a single class?
- Does the test file mirror the source file 1:1?
- Does it assert on internal state rather than observable output?

**Known suspects (from Composability + Skeptic):**
- `test_mcp_discovery.py` regex-extraction-and-exec pattern — "ticking time bomb"
- Submodule tests with heavy `mock_sdk()` patching — risk of "testing the mock"
- Any test asserting on exact log messages or mock call counts

**Deliverable:** Short, concrete hit list of tests to rewrite, with before/after sketches. NOT a wall of text. Must identify at least 3-5 concrete rewrites (per Skeptic's constraint).

---

## Axis 4: CI & Test Infrastructure Alignment

**Depends on:** Axes 1 + 2 completion.

**Tasks:**
- **Refactor `scripts/tests/` into `tests/`:**
  - Move `test_parser.py` → `tests/test_mine_patterns_parser.py`
  - **Delete** `test_regression.py` — it's a pure snapshot regression file redundant with `test_parser.py` which already covers the same fixtures with better property-based assertions.
  - Move `scripts/tests/fixtures/` → `tests/fixtures/mine_patterns/`
  - Replace `sys.path.insert` hack with proper import (add `scripts` to `pythonpath` in `pyproject.toml`)
  - Remove `scripts/tests/` after migration
- Enable xdist in CI (`-n auto`) for fast test job
- Ensure CI saves JUnit XML artifacts for all test jobs (not just E2E)
- Document the conftest.py submodule test prefix filter (`test_workflow_*`, `test_hints_*`)

---

## Agent Assignments

| Axis | Agent Type | Priority | Dependencies |
|------|-----------|----------|-------------|
| 1. Hook Implementation | Implementer | P0 | None |
| 2. Slow/xdist Triage | TestEngineer | P0 | None (measure first) |
| 3. Test Quality Audit | Researcher → TestEngineer | P0 | None (start immediately) |
| 4. CI Alignment | Implementer | P1 | Axes 1 + 2 |

Axes 1, 2, and 3 launch in parallel. Axis 4 waits.

---

## Terminology (Canonical)

| Term | Definition |
|---|---|
| **Intent test** | Tests behavior/contract; survives refactoring |
| **Implementation test** | Tests internal structure; breaks on refactor |
| **Bare pytest** | Full-suite run with no output saving |
| **Timestamped results** | UTC, `YYYY-MM-DD_HHMMSS`, dual `.xml` + `.log` |
| **xdist-compatible** | Passes correctly under `pytest -n auto` |
| **Slow test** | >30s, marked `@pytest.mark.slow` with explicit timeout override |
| **`.test_results/`** | Gitignored directory for all local test output |
| **Full suite run** | pytest against all `testpaths`, no specific file target |
