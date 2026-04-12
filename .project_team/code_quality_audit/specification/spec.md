# Code Quality Audit — Specification

**Project:** AI_PROJECT_TEMPLATE (dev repo only, not the copier template)
**Date:** 2026-04-11
**Priority:** Testing > Documentation > Code Quality

---

## Terminology

Per the Terminology Guardian's glossary, this spec uses precise language:

- **Static analysis** = automated code checking (ruff, pyright). Not "code review."
- **PR review** = human or AI review of pull requests (CodeRabbit, PR-Agent). Not "code review."
- **API reference docs** = auto-generated from docstrings (pdoc, sphinx-autodoc).
- **Narrative docs** = hand-written guides, tutorials, architecture explanations.
- **AI context docs** = documentation consumed by AI coding tools (Claude rules, workflow files).
- **AI-powered tool** = uses an ML model at runtime. Distinct from deterministic/traditional tools.
- **Coverage** = line/branch coverage measurement (pytest-cov). Not test quality.

---

## Architecture: 4 Orthogonal Axes

The audit decomposes into 4 independent axes. Choices on one axis don't constrain choices on others. The compositional law: **every tool is a CLI command that produces structured output**, composing freely with pixi tasks and CI steps.

```
Axis 1: Static Analysis (linting, formatting, type checking)
Axis 2: Test Quality (coverage, mutation, generation)
Axis 3: Documentation (API reference, narrative, AI context)
Axis 4: CI Enforcement (where/when tools run)
```

"AI vs traditional" is NOT a separate axis — it's a value within each axis. Each tool below is evaluated on its own merits regardless of whether it uses ML.

---

## Axis 1: Static Analysis

### Current State

- **Linting/formatting:** None. Zero config, zero enforcement.
- **Type checking:** None.
- **claudechic alignment:** claudechic uses ruff (v0.9.1, defaults) + pyright, enforced via pre-commit.

### Tools to Evaluate

| Tool | Tier | Pros | Cons |
|------|------|------|------|
| **ruff** | **Must-have** | Subsumes black+isort+flake8+pyflakes. ~100x faster than alternatives. Zero-config defaults work. Configurable via `pyproject.toml [tool.ruff]`. Mirrors claudechic. Python 3.14 compatible. | None significant. |
| **pyright** | **Should-have** | Mirrors claudechic. Catches real bugs. Configurable via `pyproject.toml [tool.pyright]`. Faster than mypy. Better Python 3.14 support than mypy. | Requires type annotations to be useful. Scoped to the claudechic integration seam (see below). May produce noise on untyped test fixtures. |
| **mypy** | **Skip** | Pyright is already used by claudechic. No reason to diverge. mypy has slower Python 3.14 support. |
| **bandit** | **Could-have** | Security-focused static analysis. Low effort to add. | This repo has minimal attack surface (no web endpoints, no user input handling). Noise-to-signal ratio likely poor for a template generator. |

### Recommendation

Adopt **ruff** immediately (Layer 0). Adopt **pyright** after ruff is stable (Layer 3a), mirroring claudechic's exact config. Skip mypy — no reason to maintain a different type checker than the upstream dependency.

> **Maintenance reality check:** pyright requires ongoing human effort — maintaining type stubs, fixing new errors when code changes, updating exclude lists. If nobody will maintain pyright config after initial setup, don't adopt it. A neglected type checker (with growing ignore lists or disabled checks) is worse than no type checker.

### Pyright Scope (Decided)

**Target: the claudechic integration seam.** Not just `scripts/`, not everything. The critical boundary is where this repo imports, wraps, or extends the claudechic submodule — that's where type mismatches and API drift cause real bugs.

**The integration surface (6 test files + conftest, ~2,744 lines):**

| Module Imported | Used In | What's Tested |
|----------------|---------|---------------|
| `claudechic.mcp` | test_mcp_integration.py, test_mcp_discovery.py | MCP tool discovery/registration |
| `claudechic.app.ChatApp` | test_tui_chatapp.py, test_e2e_cross_platform.py, test_windows_crash_fixes.py | TUI app lifecycle |
| `claudechic.agent.Agent` | test_windows_crash_fixes.py | Agent process management |
| `claudechic.onboarding`, `claudechic.hints.state` | test_onboarding.py | Onboarding health checks |
| `claudechic.widgets.*` | test_tui_chatapp.py | TUI widget rendering |
| `claudechic.workflows.engine` | test_e2e_cross_platform.py | Workflow execution |
| `claudechic.chicsession_cmd` | test_e2e_cross_platform.py | Session persistence |

**Also included:** `scripts/` (no claudechic imports, but worth type-checking as the repo's own production code).
**Files NOT in scope:** `template/mcp_tools/` (decoupled by design — uses callbacks, not imports), remaining test files that don't touch claudechic.

Pyright on this seam catches: wrong argument types when claudechic's API changes, missing attributes after refactors, type mismatches in mock fixtures that mask real bugs.

### Proposed Config

```toml
# pyproject.toml additions
[tool.ruff]
target-version = "py310"
exclude = ["submodules", "template", ".pixi"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
# E=pycodestyle, F=pyflakes, I=isort, UP=pyupgrade, B=bugbear, SIM=simplify

[tool.pyright]
pythonVersion = "3.10"
include = [
    "tests/test_mcp_integration.py",
    "tests/test_mcp_discovery.py",
    "tests/test_onboarding.py",
    "tests/test_tui_chatapp.py",
    "tests/test_e2e_cross_platform.py",
    "tests/test_windows_crash_fixes.py",
    "tests/conftest.py",
    "scripts",
]
exclude = ["build", ".pixi", "template", "submodules"]
```

---

## Axis 2: Test Quality

### Current State

- **Framework:** pytest, well-configured. Parallel execution (xdist), cross-platform CI, 8 custom markers, 3-layer timeout strategy. This is solid.
- **Coverage:** Zero tracking. No pytest-cov, no coverage reports, no visibility into what's tested.
- **Test gaps:** `import_env.py` (~250 lines, parses YAML, modifies TOML) has zero tests. `mine_patterns.py` (41KB) coverage unknown. Scripts are testable pure functions — low-hanging fruit.
- **Test quality:** No mutation testing. No property-based testing. Tests exist but their effectiveness is unmeasured.

### Tools to Evaluate

| Tool | Tier | Pros | Cons |
|------|------|------|------|
| **pytest-cov** | **Must-have** | Standard coverage measurement. Plugs into existing pytest via `--cov` flag. Reports to terminal, XML, HTML. Integrates with every CI coverage service. Zero coupling — it's a pytest plugin. | Measures lines hit, not test quality. Coverage number can be gamed. |
| **coverage reporting (Codecov or Coveralls)** | **Should-have** | PR-level coverage diffs. Trend tracking. Free for public repos. | External service dependency. But exit cost is zero — remove the CI step and you lose nothing permanent. |
| **hypothesis** | **Should-have** | Property-based testing for parsers (`import_env.py` YAML parsing, `mine_patterns.py` pattern extraction). Finds edge cases humans miss. | Learning curve. Best for pure functions with well-defined input domains — which is exactly what the scripts are. |
| **mutmut** | **Could-have** | Mutation testing — measures whether tests actually catch bugs, not just execute code. Answers "are these tests any good?" | Slow (modifies code + reruns tests). Best run manually or in nightly CI, not on every PR. Limited value until baseline coverage exists. |
| **qodo-cover (AI)** | **Could-have** | AI-generated test suggestions. Free tier exists. Can bootstrap coverage for untested modules (`import_env.py`). | Skeptic's concern is valid: AI test tools struggle with async/mocked code. But `import_env.py` is synchronous pure Python — good candidate. Evaluate honestly: does it produce tests worth keeping, or disposable scaffolding? |
| **CodiumAI / PR-Agent for tests** | **Could-have** | Auto-suggests tests in PR context. | Platform coupling (GitHub App). Generated tests for complex fixtures (copier, pexpect) will likely be low quality. Best for simple modules only. |

### Recommendation

**Layer 1 (immediate):**

> **Prerequisite (blocking):** Verify coverage.py compatibility with Python 3.14 before adopting pytest-cov. This repo uses Python 3.14 — coverage.py must support it. Check the [coverage.py changelog](https://coverage.readthedocs.io/en/latest/changes.html) for 3.14 support status. If unsupported, Layer 1 is blocked until it is.

1. Add `pytest-cov` to pixi.toml. Add `--cov=scripts --cov-report=term-missing` to pytest addopts.
2. Add coverage step to CI workflow. Establish baseline number. **No gate** — reporting only, no minimum threshold enforced. (Decided: coverage is for visibility, not gatekeeping.)

**Follow-up recommendation (dev task, not a tool task):** Write tests for `import_env.py` — it's pure Python (~250 lines) with clear inputs/outputs, and currently has zero tests. This is the highest-value test-writing target in the repo, but it's a development effort, not a tooling decision.

**Layer 3b (after baseline, when someone has time):**
3. Try hypothesis on `import_env.py` parser and `mine_patterns.py` parser.
4. Try qodo-cover on `import_env.py` specifically. Evaluate output quality honestly.
5. Consider mutmut as a one-off audit, not a CI gate.

### Key Constraint

pytest-xdist is already in use with `--dist loadscope`. Coverage + xdist requires `pytest-cov` (not bare `coverage run`), because pytest-cov handles subprocess aggregation. This is the only cross-axis dependency — and it's a clean one (pytest plugin seam).

---

## Axis 3: Documentation

### Current State

- **Narrative docs:** `docs/getting-started.md` (22KB, comprehensive), `README.md`. Good quality. Static HTML served via GitHub Pages.
- **API reference docs:** None. No docstring extraction, no auto-generated API docs.
- **Docstring coverage:** Varies 33-100% across modules.
- **AI context docs:** Extensive. `.claude/rules/`, `workflows/`, `global/rules.yaml`, `global/hints.yaml`. This repo's primary audience includes AI coding tools.
- **Doc generator:** None. Raw HTML + GitHub Pages.
- **claudechic current state:** claudechic uses mkdocs + mkdocs-material. **This will change** — both repos will migrate to Zensical (see below).

### Decision (Decided): Zensical for Both Repos

**User decision:** Migrate BOTH claudechic AND this template repo to [Zensical](https://zensical.org/) — the successor to mkdocs-material, built by the same team (squidfunk).

**Why Zensical:**
- Built by the mkdocs-material creators as its intentional successor
- Rust core with differential builds (milliseconds, not minutes)
- MIT licensed, fully open-source
- Python package (`pip install zensical`), requires Python 3.10+
- Designed for seamless migration from mkdocs-material — reads `mkdocs.yml` as a transition mechanism, preserves URLs/anchors/SEO
- Markdown extensions, admonitions, code annotations, tabbed content all carry over
- Latest release: April 7, 2026 (actively maintained)

**This is a cross-repo effort:**
1. **claudechic:** Migrate FROM mkdocs-material TO Zensical. Migration path is smooth — Zensical reads existing `mkdocs.yml` and builds without changes in most cases. Template overrides need minor MiniJinja adjustments.
2. **This repo:** Adopt Zensical directly (no mkdocs-material to migrate from). Start fresh with `zensical.toml` config.
3. **Unified system:** Both repos use the same doc generator, same theme conventions, same extension ecosystem.

**Risks to flag:**
- Zensical is new (v0.0.x as of April 2026). Expect rough edges, missing features, and breaking changes.
- `mkdocs.yml` compatibility is a transition mechanism — it will eventually leave core. Plan to migrate to native `zensical.toml` config.
- Plugin ecosystem is nascent. If claudechic uses mkdocs plugins beyond material's built-ins, check Zensical compatibility before migrating.
- The Rust build system is a different debugging surface than pure-Python mkdocs.

> **Maintenance reality check:** Any doc generator requires ongoing effort — updating nav, fixing broken links, keeping config current. If nobody will maintain the docs site after initial setup, static HTML (current approach) is more honest. A stale doc site with outdated nav is worse than a simple getting-started.md. Zensical's fast builds reduce friction but don't eliminate the maintenance commitment.

### Tools to Evaluate

| Tool | Tier | Pros | Cons |
|------|------|------|------|
| **Zensical** | **Should-have** | Successor to mkdocs-material by the same team. Rust core, fast builds. MIT licensed. Smooth migration from mkdocs-material. Unified system for both repos. | New (v0.0.x). Expect rough edges. Plugin ecosystem still growing. Breaking changes possible. |
| **pdoc** | **Should-have** | Best lightweight API reference generator. Zero config — reads docstrings, produces HTML. Python-only (perfect for this repo). | Only does API reference. Doesn't replace Zensical for narrative docs. But that's fine — they compose. **Honest value note:** For this repo's 2 scripts alone, API reference is ceremony. The primary value of pdoc here is **template validation** — proving it works before recommending it to downstream copier projects. |
| **interrogate** | **Should-have** | Docstring coverage measurement. CI-enforceable. Configurable via pyproject.toml. | Only measures presence, not quality. **Honest value note:** Same as pdoc — for 2 scripts, this is lightweight. Primary value is **template validation**: proving the tool integrates cleanly with pixi + CI before recommending it downstream. |
| **DeepWiki (AI)** | **Could-have** | Free for public repos. Auto-generates architecture docs and relationship maps. | External service. No local control. Quality varies. **Key insight:** DeepWiki's primary value for this repo is **AI context docs**, not human docs. Evaluate whether its output is useful as `.claude/rules/` source material or `CLAUDE.md` supplement — that's the real test, not whether it produces nice HTML. |

### Recommendation

**Dual-purpose docs strategy** (human guidance + AI context):

1. **Zensical** for narrative docs — adopt for this repo, migrate claudechic. Start with `mkdocs.yml` compatibility mode for claudechic, then move both repos to native `zensical.toml`.
2. **pdoc** for API reference — add to CI, auto-generate from docstrings. Composes with Zensical (separate output, can be linked/embedded).
3. **interrogate** as a quality gate — measure docstring coverage, enforce minimum threshold in CI.
4. **DeepWiki** — evaluate as an AI context source, not a human doc replacement. Test: does its output improve `.claude/rules/` or `CLAUDE.md`? If yes, extract the useful parts. Don't depend on the service itself.

**Composability note:** pdoc and Zensical compose cleanly. pdoc generates HTML from docstrings; Zensical generates HTML from markdown. They can be separate CI steps outputting to separate directories. No coupling. Both are CLI commands with structured output — the compositional law holds.

---

## Axis 4: CI Enforcement

### Current State

- **CI:** GitHub Actions with 2 workflows. `test-template.yml` (fast + full test suites, 3 OSes). `pages.yml` (static docs to GitHub Pages).
- **Local enforcement:** None. No pre-commit hooks. No format-on-save.
- **claudechic alignment:** claudechic uses pre-commit with ruff + pyright + large-file check.

### Tools to Evaluate

| Tool | Tier | Pros | Cons |
|------|------|------|------|
| **pre-commit** | **Should-have** | Mirrors claudechic. Catches issues before CI. ruff hook runs in ~1s (Skeptic approved). Configurable per-hook. | Can become a monolithic gate — if one hook breaks, nothing commits. Mitigation: keep hooks fast (<5s total), run same checks in CI as backup. |
| **CI-only enforcement** | **Must-have (baseline)** | Every tool runs in CI regardless of pre-commit. CI is the source of truth. Pre-commit is convenience, not the gate. | Slower feedback loop than pre-commit. But reliable — CI always runs. |
| **CodeRabbit (AI PR review)** | **Could-have** | Free for public repos. AI-powered PR review — catches logic issues, not just style. Complements static analysis. | External service. Can be noisy. **Success criterion:** Keep if it catches at least 1 issue that ruff/pyright missed across 3 PRs. Remove if it only restates static analysis findings. |
| **PR-Agent** | **Could-have** | Self-hostable alternative to CodeRabbit. More control. | Setup overhead. Requires API key for AI model. "Free" but with operational cost. |

### Recommendation

**Layer 0 (with ruff):** Add ruff to CI as a check step. Fast, no dependencies.

**Layer 1 (with coverage):** Add coverage reporting to CI. Add interrogate check.

**Layer 2 (after tools stabilize):** Add pre-commit config mirroring claudechic. Keep it optional for developers — CI is the enforcer.

**Layer 3a (tooling):** Add pyright to CI and pre-commit (only if someone will maintain it).

**Layer 3b (evaluate, untimeboxed):** Try CodeRabbit on 3 PRs. Success criterion: keep if it catches at least 1 issue that ruff/pyright missed. Remove if it only restates static analysis findings. Exit cost is zero (GitHub App toggle).

### Proposed CI Structure

```yaml
# New job in test-template.yml
lint:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: prefix-dev/setup-pixi@v0.8.8
    - run: pixi run ruff check .
    - run: pixi run ruff format --check .
    - run: pixi run interrogate --fail-under 80 scripts/
    # pyright added in Layer 3a (scoped to claudechic integration seam):
    # - run: pixi run pyright

# Modified fast job
fast:
  # existing config...
  steps:
    # existing steps...
    - run: pixi run pytest --cov=scripts --cov-report=xml -n auto --dist loadscope -m 'not slow and not integration'
    - uses: codecov/codecov-action@v4  # or equivalent
```

---

## Adoption Sequence

Respecting dependencies and the user's priority order:

```
Week 1: Layer 0 — Foundation
  [x] Add ruff to pixi.toml (pypi-dependencies)
  [x] Add [tool.ruff] config to pyproject.toml
  [x] Add ruff check + format steps to CI
  [x] Run ruff --fix on existing code (one cleanup commit)

Week 1: Layer 1 — Test Coverage (parallel with Layer 0)
  [!] PREREQUISITE: Verify coverage.py Python 3.14 compatibility (blocking)
  [x] Add pytest-cov to pixi.toml
  [x] Add --cov flags to pytest addopts
  [x] Add coverage reporting to CI
  [x] Establish baseline coverage number
  Follow-up (dev task): Write tests for import_env.py (~250 lines, zero tests)

Week 2: Layer 2 — Documentation (parallel with Layer 1)
  [x] Add interrogate to pixi.toml, measure docstring coverage
  [x] Add pdoc, generate API reference for scripts/
  [x] Add Zensical to pixi.toml, set up narrative docs for this repo
  [x] Migrate claudechic from mkdocs-material to Zensical (cross-repo)

Week 2-3: Layer 3a — Tooling (depends on Layers 0-1, ~1 week)
  [ ] Add pyright scoped to claudechic integration seam (only if someone will maintain it)
  [ ] Add pre-commit config (ruff + pyright + large-file check)

Untimeboxed: Layer 3b — Evaluations (just try them, zero exit cost)
  [ ] Try qodo-cover on import_env.py — evaluate output quality
  [ ] Try CodeRabbit on 3 PRs — keep if it catches ≥1 issue ruff/pyright missed
  [ ] Try DeepWiki — evaluate as .claude/rules/ source, not human docs
  [ ] Consider hypothesis for parser testing
  [ ] One-off mutmut audit on scripts/
```

---

## Decisions (All Resolved)

All user decisions have been made and are reflected in the spec above:

1. **Coverage threshold:** Reporting only, no gate. (Axis 2)
2. **Docs system:** Zensical for both claudechic and this repo. (Axis 3)
3. **Pyright scope:** Claudechic integration seam — the 6 test files + conftest that import claudechic, plus scripts/. (Axis 1)
4. **AI tool evaluation depth:** Just try them. All have zero exit cost. (Layer 3b)

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Zensical immaturity (v0.0.x) | Medium | Medium | It's MIT licensed and built by the mkdocs-material team. Fallback: revert to mkdocs-material (migration is reversible). Breaking changes expected — pin versions in pixi.toml. |
| claudechic Zensical migration breaks docs | Low | Medium | Zensical reads mkdocs.yml natively. Test migration in a branch first. Keep mkdocs-material as fallback until Zensical build is verified. |
| AI tools produce low-quality output | High | Low | Evaluate on simple targets first. Don't commit generated code without review. Exit cost is zero for all recommended AI tools. |
| Pre-commit friction slows development | Low | Medium | Keep hooks fast (<5s). Make pre-commit optional — CI is the enforcer. |
| Tool config proliferation | Medium | Low | All recommended tools configure via pyproject.toml. Only pre-commit needs a separate file. |
| Python 3.14 compatibility | Low | High | ruff and pyright both support 3.14. pytest-cov uses coverage.py which tracks CPython releases. Check before adopting any new tool. |
| CI time increase | Medium | Medium | Lint job runs on ubuntu-only (~30s). Coverage adds ~10% to test time. Parallel jobs keep total CI time flat. |

---

## Summary Table

| Tool | Axis | Tier | Layer | claudechic Parity | AI-Powered |
|------|------|------|-------|-------------------|------------|
| ruff | Static Analysis | Must-have | 0 | Yes | No |
| pytest-cov | Test Quality | Must-have | 1 | — | No |
| CI coverage reporting | CI Enforcement | Must-have | 1 | — | No |
| interrogate | Documentation | Should-have | 2 | — | No |
| pdoc | Documentation | Should-have | 2 | — | No |
| Zensical | Documentation | Should-have | 2 | Migration | No |
| pyright | Static Analysis | Should-have | 3a | Yes | No |
| pre-commit | CI Enforcement | Should-have | 3a | Yes | No |
| hypothesis | Test Quality | Could-have | 3b | — | No |
| qodo-cover | Test Quality | Could-have | 3b | — | Yes |
| CodeRabbit | CI Enforcement | Could-have | 3b | — | Yes |
| DeepWiki | Documentation | Could-have | 2 | — | Yes |
| mutmut | Test Quality | Could-have | 3b | — | No |
| bandit | Static Analysis | Could-have | — | — | No |
| mypy | Static Analysis | Skip | — | No (pyright instead) | No |
| semgrep | Static Analysis | Skip | — | — | No |
