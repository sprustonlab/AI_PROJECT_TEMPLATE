# Research Report: Test/CI Organization Best Practices

**Requested by:** Coordinator
**Date:** 2026-03-30
**Tier of best source found:** T1 (official pytest docs, official Textual docs, copier-uv CI analysis, direct analysis of our codebase)

## Query

How should local tests and CI relate? How do we avoid duplication between `tests/` and `.github/workflows/`? What do best-in-class template repos do?

---

## 1. Current State Analysis

### What We Have Now

**Local tests (`tests/` — 1996 lines, 6 test files):**

| File | Lines | Layer | What It Tests |
|------|-------|-------|---------------|
| `test_copier_generation.py` | 197 | Copier gen | Standard/dev mode, cluster configs, excluded dirs |
| `test_mcp_discovery.py` | 260 | MCP seam | get_tools() discovery, kwargs, error handling |
| `test_mcp_integration.py` | 397 | MCP tools | Cluster tool execution, MCP format, kwargs wiring |
| `test_cluster_tools.py` | 484 | Unit | LSF/SLURM parsers, command builders, SSH dispatch |
| `test_tui_chatapp.py` | 346 | TUI | ChatApp startup, widgets, agent commands, permissions |
| `test_e2e_smoke.py` | 312 | E2E | pixi install, import claudechic, TUI starts |

**CI workflow (`test-template.yml` — 308 lines, 4 jobs):**

| Job | What It Does |
|-----|-------------|
| `pytest-suite` | Runs `pytest tests/` on 3 OSes |
| `copier-smoke` | Generates project, verifies pixi.toml content, runs pixi install. Matrix: 3 OSes × 2 modes |
| `copier-cluster` | Generates with cluster=true, verifies cluster files present. Matrix: lsf/slurm |
| `copier-no-cluster` | Generates with cluster=false, verifies cluster files absent |

**CI workflow (`ci.yml`):** Runs bash/PowerShell E2E scripts that test activation, claudechic launch, skill availability — **completely separate from pytest**.

### The Duplication Problem

The CI `copier-smoke`, `copier-cluster`, and `copier-no-cluster` jobs **duplicate** what `test_copier_generation.py` and `test_e2e_smoke.py` already test in pytest:

| Test | In pytest? | In CI shell scripts? |
|------|-----------|---------------------|
| Copier generates standard mode correctly | ✅ `test_copier_generation.py` | ✅ `copier-smoke` job |
| Copier generates cluster files | ✅ `test_copier_generation.py` | ✅ `copier-cluster` job |
| Copier excludes cluster when disabled | ✅ `test_copier_generation.py` | ✅ `copier-no-cluster` job |
| pixi.toml has correct content | ✅ `test_copier_generation.py` | ✅ `copier-smoke` job |
| pixi install succeeds | ✅ `test_e2e_smoke.py` | ✅ `copier-smoke` job |
| SSH target in YAML | ✅ `test_copier_generation.py` | ✅ `copier-cluster` job |

**This is the anti-pattern.** The CI shell scripts are a shadow copy of the pytest tests, maintained separately, with different assertion styles and different failure reporting.

---

## 2. How Best-in-Class Projects Handle This

### Principle: CI Runs pytest. Period.

The universal best practice across well-maintained open source projects:

> **CI's job is to run `pytest` (the same command you run locally) on multiple platforms.** CI should NOT contain test logic in shell scripts.

### copier-uv (T5 — exemplary template CI)

The copier-uv template has the most sophisticated template testing I found:

**Structure:**
1. `test-project` job: Generates projects, runs `make setup`, `make test`, `make check` — across OS × Python version matrix
2. `test-project-ci` job: Pushes generated project to GitHub, monitors its CI passes

**Key insight:** All test logic lives in Python tests or Makefile targets. CI just invokes them across a matrix. There are NO shell script assertions in CI.

### scientific-python/cookie (T3 — scientific Python org)

Uses nox to run the complex CI jobs:
- `nox -s tests` runs pytest
- `nox -s generate` creates a project from the template, then runs pytest inside it
- CI calls `nox` — no inline shell assertions

**Key insight:** nox sessions are the bridge between local dev and CI. `nox -s generate` is runnable locally AND in CI.

### pytest-cookies (T5 — official cookiecutter testing plugin)

Provides a `cookies` fixture for pytest:
```python
def test_bake_project(cookies):
    result = cookies.bake(extra_context={"project_name": "test"})
    assert result.exit_code == 0
    assert result.project_path.is_dir()
```

**Key insight:** Template generation IS a pytest test, not a CI script.

### Textual (T3 — Textualize official)

Runs all tests via `pytest` in CI. Uses `run_test()` headlessly — no special CI configuration needed.

### Django (T3 — Django project)

Uses pytest markers: `@pytest.mark.slow`, `@pytest.mark.db`. CI runs `pytest -m "not slow"` for PRs, full suite nightly.

### dask-jobqueue (T3 — dask official)

- Unit tests: Mock scheduler commands, run in CI on every PR
- Integration tests: Run on actual HPC clusters, NOT in CI — triggered manually
- CI just runs `pytest` with appropriate markers

---

## 3. The Right Pattern: pytest Markers as the Organizing Principle

### The Golden Rule

```
CI workflow = pytest markers + OS matrix
```

CI should contain **zero test logic**. Its only job is:
1. Set up the environment (Python, pixi, etc.)
2. Run `pytest` with the right markers
3. Report results

### Recommended Marker Scheme

```python
# conftest.py
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "copier: tests that run copier copy (need copier installed)")
    config.addinivalue_line("markers", "pixi: tests that need pixi (skip if not installed)")
    config.addinivalue_line("markers", "network: tests that need internet (pixi install, git clone)")
    config.addinivalue_line("markers", "tui: tests using Textual App.run_test()")
    config.addinivalue_line("markers", "e2e: full end-to-end smoke tests")
    config.addinivalue_line("markers", "unix_only: tests that only work on Linux/macOS")
```

### How Each Test File Maps to Markers

| File | Markers | Speed | When to Run |
|------|---------|-------|-------------|
| `test_cluster_tools.py` | (none — always runs) | Fast (<1s) | Every push |
| `test_mcp_discovery.py` | (none — always runs) | Fast (<1s) | Every push |
| `test_copier_generation.py` | `@pytest.mark.copier` | Medium (~5s) | Every push |
| `test_mcp_integration.py` | (none — always runs) | Fast (<2s) | Every push |
| `test_tui_chatapp.py` | `@pytest.mark.tui` | Medium (~3s) | Every push |
| `test_e2e_smoke.py` (pixi install) | `@pytest.mark.slow`, `@pytest.mark.network`, `@pytest.mark.pixi` | Slow (~2min) | Weekly / manual |
| `test_e2e_smoke.py` (TUI start) | `@pytest.mark.slow`, `@pytest.mark.pixi`, `@pytest.mark.unix_only` | Slow (~30s) | Weekly |

### pytest Configuration

```toml
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "copier: tests that run copier copy",
    "pixi: tests that require pixi installed",
    "network: tests that require internet access",
    "tui: tests using Textual App.run_test()",
    "e2e: full end-to-end smoke tests",
    "unix_only: tests that only work on Linux/macOS",
]
# Default: skip slow tests locally
addopts = "-m 'not slow'"
```

### Running Tests Locally

```bash
# Default (fast tests only) — what you run during development
pytest

# Include copier generation tests
pytest -m "not slow"

# Run everything except network-dependent tests
pytest -m "not network"

# Run absolutely everything
pytest -m ""

# Just TUI tests
pytest -m tui

# Just cluster parser tests
pytest tests/test_cluster_tools.py
```

---

## 4. Recommended CI Structure

### Single Workflow: `test-template.yml`

Replace both `ci.yml` and the current `test-template.yml` with one unified workflow:

```yaml
name: Tests

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]
  schedule:
    - cron: "0 6 * * 1"  # Weekly Monday 6am UTC
  workflow_dispatch:

jobs:
  # ─── Fast tests: run on every push ───────────────────────────
  fast:
    name: Fast Tests (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    steps:
      - uses: actions/checkout@v4
        with: { submodules: recursive, fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install pytest pyyaml copier pytest-asyncio
      - run: pytest -m "not slow" -v --tb=short
        env:
          GIT_AUTHOR_NAME: CI
          GIT_AUTHOR_EMAIL: ci@test.com
          GIT_COMMITTER_NAME: CI
          GIT_COMMITTER_EMAIL: ci@test.com

  # ─── Slow tests: pixi install, network, E2E ─────────────────
  slow:
    name: E2E Tests (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    needs: fast
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        # Windows excluded: pexpect doesn't work, pixi install slower
    steps:
      - uses: actions/checkout@v4
        with: { submodules: recursive, fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - uses: prefix-dev/setup-pixi@v0.8.8
        with: { run-install: false }
      - run: pip install pytest pyyaml copier pytest-asyncio pexpect
      - run: pytest -m "" -v --tb=short --timeout=300
        env:
          GIT_AUTHOR_NAME: CI
          GIT_AUTHOR_EMAIL: ci@test.com
          GIT_COMMITTER_NAME: CI
          GIT_COMMITTER_EMAIL: ci@test.com
          SETUPTOOLS_SCM_PRETEND_VERSION: "0.0.1"
```

### What This Achieves

| Trigger | What Runs | Time |
|---------|-----------|------|
| **Every push/PR** | `fast` job: all tests except `@slow` (unit, copier gen, MCP, TUI) on 3 OSes | ~30s |
| **Weekly schedule** | `fast` + `slow` jobs: EVERYTHING including pixi install, import claudechic, TUI startup | ~5min |
| **Manual dispatch** | Same as weekly — for debugging | ~5min |

### What Gets Deleted

- **`copier-smoke` CI job** → replaced by `test_copier_generation.py` + `test_e2e_smoke.py` running in `fast`/`slow` jobs
- **`copier-cluster` CI job** → replaced by `TestClusterScheduler` in `test_copier_generation.py`
- **`copier-no-cluster` CI job** → replaced by `test_no_cluster` in `test_copier_generation.py`
- **`ci.yml` shell scripts** → replaced by `test_e2e_smoke.py` pytest tests
- **All inline `bash` assertions in CI** → replaced by `assert` in pytest

---

## 5. Test Directory Structure

### Current (flat — good enough)

```
tests/
├── conftest.py
├── test_cluster_tools.py      # L1: Unit (parsers, builders)
├── test_copier_generation.py  # L2: Copier gen (standard, dev, cluster)
├── test_mcp_discovery.py      # L3: MCP seam (get_tools discovery)
├── test_mcp_integration.py    # L3: MCP tools (execution, format)
├── test_tui_chatapp.py        # L4: TUI (Textual Pilot)
└── test_e2e_smoke.py          # L5: E2E (pixi install, import, TUI start)
```

### Recommended: Keep flat, use markers not directories

**Why not nested directories?** With only 6 test files and ~2000 lines, the overhead of `tests/unit/`, `tests/integration/`, `tests/e2e/` directories doesn't pay off. Markers achieve the same filtering:

```bash
pytest -m "not slow"     # equivalent to "run tests/unit/ and tests/integration/"
pytest -m e2e            # equivalent to "run tests/e2e/"
pytest -m tui            # equivalent to "run tests/tui/"
```

**When to switch to directories:** If the test suite grows beyond ~10 files or ~5000 lines, split into subdirectories. For now, flat + markers is the right trade-off.

---

## 6. conftest.py Patterns for CI vs Local

### Environment-Aware Fixtures

```python
# conftest.py

import os
import shutil

# Detect CI environment
IN_CI = os.environ.get("CI", "false").lower() == "true"
HAS_PIXI = shutil.which("pixi") is not None
HAS_NETWORK = not os.environ.get("NO_NETWORK", False)


@pytest.fixture
def generated_project(copier_output):
    """Generate a default project for tests that need one."""
    return copier_output({
        "project_name": "test_project",
        "claudechic_mode": "standard",
        "use_cluster": True,
        "cluster_scheduler": "lsf",
        "cluster_ssh_target": "login.example.com",
    })


def skip_unless_pixi(fn):
    """Decorator to skip tests when pixi is not available."""
    return pytest.mark.skipif(
        not HAS_PIXI,
        reason="pixi not installed"
    )(pytest.mark.slow(fn))
```

### Auto-Skipping by Environment

The existing `test_e2e_smoke.py` already does this well with `@pytest.mark.skipif`:

```python
@pytest.mark.skipif(
    shutil.which("pixi") is None,
    reason="pixi not installed"
)
def test_pixi_install(self, generated_project):
    ...
```

This means the test **self-skips gracefully** when run locally without pixi, AND runs in CI when pixi is installed. No separate CI logic needed.

---

## 7. Handling Platform-Specific Tests

### pexpect (Unix-only)

```python
import sys

@pytest.mark.skipif(sys.platform == "win32", reason="pexpect requires Unix PTY")
@pytest.mark.unix_only
def test_claudechic_starts(self, generated_project):
    import pexpect
    child = pexpect.spawn(...)
```

### Windows-Specific Tests

```python
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only test")
def test_powershell_activation(self, generated_project):
    ...
```

### CI Matrix + Markers = Full Coverage

The CI matrix already runs on all 3 OSes. Combined with `skipif` markers, the right tests run on the right platforms automatically:

- `test_claudechic_starts` (pexpect) → runs on ubuntu + macos, skips windows
- `test_powershell_activation` → runs on windows, skips others
- `test_cluster_parsers` → runs everywhere (pure Python)

---

## 8. Timeout Handling

### pytest-timeout Plugin

```toml
# pyproject.toml
[tool.pytest.ini_options]
timeout = 30  # Default timeout per test (seconds)
```

```python
# Override for slow tests
@pytest.mark.timeout(120)
@pytest.mark.slow
def test_pixi_install(self, generated_project):
    ...

@pytest.mark.timeout(60)
@pytest.mark.slow
def test_claudechic_starts(self, generated_project):
    ...
```

### CI-Level Timeout

```yaml
- run: pytest -m "" -v --tb=short --timeout=300
  timeout-minutes: 10  # GitHub Actions job-level timeout
```

---

## 9. Recommended Action Plan

### Phase 1: Add Markers to Existing Tests (30 min)

Add `@pytest.mark.slow`, `@pytest.mark.copier`, `@pytest.mark.tui`, etc. to existing test files. Register markers in `conftest.py`. Set default `addopts = "-m 'not slow'"` in pyproject.toml.

### Phase 2: Simplify CI Workflow (1 hour)

Replace `test-template.yml` with the unified workflow from Section 4. Delete `copier-smoke`, `copier-cluster`, `copier-no-cluster` jobs. CI becomes just `pytest -m "not slow"` (fast) and `pytest -m ""` (full).

### Phase 3: Migrate ci.yml Shell Scripts to pytest (1-2 hours)

Move the bash/PowerShell E2E assertions from `ci.yml` into `test_e2e_smoke.py`. Delete `ci.yml` (or keep it for just the pixi install + raw "claudechic starts" check as a minimal smoke).

### Phase 4: Add pytest-timeout (15 min)

Install `pytest-timeout`, set default 30s, override on slow tests.

### Result

| Before | After |
|--------|-------|
| 2 CI workflows with 7 jobs | 1 CI workflow with 2 jobs |
| Shell script assertions in CI | All assertions in pytest |
| `tests/` + CI scripts testing the same things | `tests/` is the single source of truth |
| Run different things locally vs CI | Run the SAME thing locally and CI (just different markers) |

---

## Sources

- [pytest markers documentation](https://docs.pytest.org/en/stable/how-to/mark.html) — T1, official pytest
- [pytest good practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html) — T1, official pytest
- [pytest custom markers examples](https://docs.pytest.org/en/stable/example/markers.html) — T1, official pytest
- [copier-uv E2E validation](https://deepwiki.com/pawamoy/copier-uv/5.3-end-to-end-validation) — T5, exemplary template CI
- [scientific-python/cookie noxfile](https://github.com/scientific-python/cookie/blob/main/noxfile.py) — T3, scientific Python org
- [pytest-cookies](https://github.com/hackebrot/pytest-cookies) — T5, official cookiecutter testing plugin, MIT ✅
- [Simon Willison: Testing cookiecutter templates with pytest](https://til.simonwillison.net/cookiecutter/pytest-for-cookiecutter) — T6
- [Organizing tests (Pytest with Eric)](https://pytest-with-eric.com/pytest-best-practices/pytest-organize-tests/) — T6
- [Textual testing guide](https://textual.textualize.io/guide/testing/) — T1
- Direct analysis of `AI_PROJECT_TEMPLATE/tests/` and `.github/workflows/` — T1

## Not Recommended (and why)

| Approach | Why Rejected |
|----------|-------------|
| **Shell script assertions in CI** | Duplicates pytest tests, different assertion style, harder to debug |
| **Separate test directories (unit/integration/e2e/)** | Overkill for 6 files — markers achieve the same thing with less overhead |
| **nox as test runner** | Adds a dependency; pytest markers + addopts achieve the same thing for our scale |
| **Separate CI workflows per test category** | More YAML to maintain; one workflow with marker-based jobs is cleaner |
| **Running ALL tests on every push** | Slow tests (pixi install) waste CI minutes; reserve for weekly |
