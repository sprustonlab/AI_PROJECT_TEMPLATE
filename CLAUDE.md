# CLAUDE.md

## Commands

```bash
pytest tests/test_foo.py                # Run specific test (preferred)
TS=$(date -u +%Y-%m-%d_%H%M%S) && pytest --junitxml=.test_results/${TS}.xml --tb=short 2>&1 | tee .test_results/${TS}.log  # Full suite with required output capture
pixi run ruff check --fix && pixi run ruff format   # Lint + format (excludes submodules/ .pixi/; lints template/*.py but skips *.jinja)
cd submodules/claudechic && pixi run ruff check --fix && pixi run ruff format  # Lint claudechic separately
pytest tests/test_copier_generation.py -v  # After template changes
```

## What This Repo Is

- Copier template source that generates Claude Code projects with guardrails, workflows, and multi-agent support.
- NOT a generated project -- this IS the template source.
- Three layers: this repo (template source) | generated projects (copier output) | claudechic submodule (core engine).
- Development branch: `develop`. Releases: `main`.
- `.project_team/` contains dev history (specs, status, agent reports) -- commit to `develop`, NEVER to `main`.

## Project Layout

- `template/` -- Jinja2 source files processed by Copier (*.jinja files). This is what end users get.
- `submodules/claudechic/` -- Core TUI + engine. Separate git repo, editable install. When you change files here: (1) commit inside the submodule, (2) `git push origin main` inside the submodule, (3) commit the updated submodule pointer in the parent repo. CI cannot fetch submodule commits that only exist locally.
- `workflows/` -- Workflow definitions for THIS repo's development (project_team, tutorial, etc.)
- `global/` -- Always-active guardrail rules (rules.yaml) and contextual hints (hints.yaml).
- `.claude/rules/` -- Agent context files documenting claudechic internals (developer mode only).
- `tests/` -- Test suite (collects from both this repo AND submodules/claudechic/tests).
- `scripts/` -- Utility scripts (audit workflow, mutation testing).
- `commands/` -- Shell command launchers (claudechic, jupyter).
- `copier.yml` -- Copier template config. HIGH CHURN -- check `_exclude` rules when adding/removing files.

## Things That Will Bite You

1. **Default pytest skips slow+integration and runs in parallel** -- `addopts` includes `-n auto -m 'not slow and not integration'`. Use `-m ""` for full suite. DO NOT rely on test ordering or shared mutable state.
2. **Cross-platform is mandatory** -- see Cross-Platform Rules section below.
3. **Pre-commit auto-fixes staged files** -- ruff --fix + ruff-format + check-added-large-files (100KB limit) run on commit. May modify staged files silently.
4. **Strict markers** -- `strict_markers = true` in pyproject.toml. New test markers MUST be added to the markers list.
5. **DON'T write guardrail rules that block their own prerequisites** -- catch-22 pattern where rules prevent the very operations they protect.
6. **Every bug is OUR bug** -- every failed test, CI failure, lint error, or broken behavior in our code is ours to own, surface, and fix. NEVER dismiss a failure as "pre-existing", "flaky", or "unrelated". Investigate it, explain the root cause, and fix it or escalate to the user. Hiding or downplaying failures erodes trust.

## Extending the Systems

### Adding a Workflow

- Create `workflows/<name>/<name>.yaml` (filename MUST match directory name).
- Add role dirs: `<name>/<role>/identity.md` + one `<phase>.md` per phase.
- 4 advance check types: `command-output`, `file-exists`, `file-content`, `manual-confirm`.
- To ship in generated projects: mirror under `template/workflows/` and check copier.yml `_exclude`.
- See `.claude/rules/workflows-system.md` for YAML schema and phase semantics.

### Adding Hints

- Global: add to `global/hints.yaml` (bare IDs, no colons -- parser auto-qualifies as `global:<id>`).
- Workflow-specific: embed in phase YAML under `hints:` key.
- Lifecycles: `show-once` | `show-every-session` | `show-until-resolved` | `cooldown-period`.
- See `.claude/rules/hints-system.md` for pipeline details.

### System Pitfalls

- Workflow directory name MUST match YAML filename.
- NEVER use colons in YAML IDs (parser auto-qualifies with namespace).
- Advance checks short-circuit -- order matters (first failure stops evaluation).
- Import boundaries are strict: leaf modules (hints, checks, guardrails) NEVER import upward.

## Cross-Platform Rules

Targets linux-64, osx-arm64, win-64. Windows is the #1 bug source (30%+ of fix commits).

- ALWAYS pass `encoding='utf-8'` to `read_text()`, `write_text()`, `open()`, `subprocess.run()`. CI test `test_utf8_encoding.py` catches this.
- NEVER use non-ASCII characters (emoji, em-dash, box-drawing) -- ASCII only.
- Use `pathlib.Path` everywhere -- NEVER string-concatenate with `/`. Use `.as_posix()` for regex/string matching.
- Use `python` not `python3`. Use double quotes in shell commands. Provide `.cmd` wrappers alongside bash scripts.
- Guard `os.kill`, `os.killpg`, `pty`, `select` with `sys.platform != "win32"` -- use `process.terminate()` on Windows.
- Use `os.replace()` not `Path.rename()` for atomic renames (rename fails on Windows if target exists).

## Testing

- 3-tier marker system: fast (default), integration (<60s each), slow/e2e (>30s).
- Template changes: run `pytest tests/test_copier_generation.py -v`.
- Test paths collect from BOTH `tests/` and `submodules/claudechic/tests`.
- Template freshness tests verify template/ stays in sync with repo.
- ALWAYS consider cross-platform impact (Windows is actively supported).

## Terminology

- **Guardrail rules** (global/rules.yaml) != **agent context files** (.claude/rules/*.md).
- **Workflow activation** (/{id} in claudechic) != **slash commands** (.claude/commands/).
- **Manifest** (YAML parsed by ManifestLoader) != **config** (pixi.toml, copier.yml).
- **claudechic** is always lowercase.

## Conventions

- Use pixi, not pip/venv/conda. Guardrail rule `no_pip_install` enforces this.
