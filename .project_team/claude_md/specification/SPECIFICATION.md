# CLAUDE.md Specification

## Overview
Write a root-level CLAUDE.md for the AI_PROJECT_TEMPLATE repo that gives agents essential context to work effectively on first contact.

## Design Principles
- **~120-150 lines** — Anthropic recommends <200; expanded to include extension recipes and cross-platform rules
- **Imperative tone** — DO/DON'T/NEVER format, terse and scannable
- **Lead with commands** — following Anthropic's claude-code-action pattern
- **Cross-reference, don't duplicate** — .claude/rules/ has 600+ lines of claudechic system docs; README.md covers end-user setup
- **Agent-facing pitfalls, not historical bugs** — address what agents trip on today
- **Use `@` imports** where appropriate for deep-dive docs

## Evidence Base
Specification informed by:
- Git history analysis of all 3 layers (331 commits main repo, 150+ claudechic)
- Anthropic's official CLAUDE.md guidelines (code.claude.com/docs/en/memory)
- Anthropic's claude-code-action CLAUDE.md as reference pattern
- Community best practices (HumanLayer, Dometrain, Builder.io)
- Leadership agent reviews (Composability, Terminology, Skeptic, UserAlignment)

## Target Audience
AI agents (Claude Code) working on the template repo itself — NOT end users of generated projects.

## Structure

### 1. Commands (~10 lines)
Commands agents actually run (environment is already active inside Claude Code / claudechic):
```
pytest tests/test_foo.py           # Run specific test (preferred)
TS=$(date -u +%Y-%m-%d_%H%M%S) && pytest --junitxml=.test_results/${TS}.xml --tb=short 2>&1 | tee .test_results/${TS}.log  # Full suite with required output capture
pixi run ruff check --fix && pixi run ruff format   # Lint + format (excludes submodules/ and .pixi/; lints template/*.py but skips *.jinja)
cd submodules/claudechic && pixi run ruff check --fix && pixi run ruff format  # Lint claudechic separately
pytest tests/test_copier_generation.py -v            # After template changes
```

### 2. What This Repo Is (~5 lines)
- Copier template source that generates Claude Code projects with guardrails, workflows, and multi-agent support
- NOT a generated project — this IS the template source
- Three layers: this repo (template source) | generated projects (copier output) | claudechic submodule (core engine)
- Development branch: `develop`. Releases: `main`.
- `.project_team/` contains dev history (specs, status, agent reports) — commit to `develop`, NEVER to `main`.

### 3. Project Layout (~15 lines)
Key directories with ONE-LINE purpose annotations:
- `template/` — Jinja2 source files processed by Copier (*.jinja files). This is what end users get.
- `submodules/claudechic/` — Core TUI + engine. Separate git repo, editable install (actively developed — most feature work happens here). Changes need own commits + parent pin update.
- `workflows/` — Workflow definitions for THIS repo's development (project_team, tutorial, etc.)
- `global/` — Always-active guardrail rules (rules.yaml) and contextual hints (hints.yaml)
- `.claude/rules/` — Agent context files documenting claudechic internals (developer mode only)
- `tests/` — Test suite (collects from both this repo AND submodules/claudechic/tests)
- `scripts/` — Utility scripts (pattern mining, mutation testing)
- `commands/` — Shell command launchers (claudechic, jupyter, mine-patterns)
- `copier.yml` — Copier template config. HIGH CHURN — check _exclude rules when adding/removing files.

### 4. Things That Will Bite You (~15 lines)
Evidence-based pitfalls (items already covered in Project Layout are not repeated):

1. **Default pytest skips slow+integration and runs in parallel** — `addopts` includes `-n auto -m 'not slow and not integration'`. Use `-m ""` for full suite. Don't rely on test ordering or shared mutable state.
2. **Cross-platform is mandatory** — see Cross-Platform Rules section below.
3. **Pre-commit auto-fixes staged files** — ruff --fix + ruff-format + check-added-large-files (100KB limit) run on commit. May modify staged files.
4. **Strict markers** — `strict_markers = true` in pyproject.toml. New test markers must be added to the markers list.
5. **Don't write guardrail rules that block their own prerequisites** — Historical catch-22 pattern where rules prevented the very operations they protected.

### 5. Extending the Systems (~20 lines)
Practical recipes for common development tasks, each ending with a cross-reference to deep docs.

#### Adding a Workflow
- Create `workflows/<name>/<name>.yaml` (filename MUST match dir name)
- Add role dirs: `<name>/<role>/identity.md` + one `<phase>.md` per phase
- 4 advance check types: `command-output`, `file-exists`, `file-content`, `manual-confirm`
- To ship in generated projects: mirror under `template/workflows/` and check copier.yml `_exclude`
- See `.claude/rules/workflows-system.md` for YAML schema and phase semantics

#### Adding Hints
- Global: add to `global/hints.yaml` (bare IDs, no colons — parser auto-qualifies as `global:<id>`)
- Workflow-specific: embed in phase YAML under `hints:` key
- Lifecycles: `show-once` | `show-every-session` | `show-until-resolved` | `cooldown-period`
- See `.claude/rules/hints-system.md` for pipeline details

#### System Pitfalls
- Workflow dir name must match YAML filename
- NEVER use colons in YAML IDs (parser auto-qualifies with namespace)
- Advance checks short-circuit — order matters (first failure stops evaluation)
- Import boundaries are strict: leaf modules (hints, checks, guardrails) never import upward

### 6. Cross-Platform Rules (~12 lines)
Targets linux-64, osx-arm64, win-64. Windows is the #1 bug source (30%+ of fix commits).

- ALWAYS pass `encoding='utf-8'` to `read_text()`, `write_text()`, `open()`, `subprocess.run()`. CI test `test_utf8_encoding.py` catches this.
- NEVER use non-ASCII characters (emoji, em-dash, box-drawing) — ASCII only
- Use `pathlib.Path` everywhere — never string-concatenate with `/`. Use `.as_posix()` for regex/string matching.
- Use `python` not `python3`. Use double quotes in shell commands. Provide `.cmd` wrappers alongside bash scripts.
- Guard `os.kill`, `os.killpg`, `pty`, `select` with `sys.platform != "win32"` — use `process.terminate()` on Windows.
- Use `os.replace()` not `Path.rename()` for atomic renames (rename fails on Windows if target exists).

### 7. Testing (~8 lines)
- 3-tier marker system: fast (default), integration (<60s each), slow/e2e (>30s)
- Template changes: `pytest tests/test_copier_generation.py -v`
- Test paths collect from BOTH `tests/` and `submodules/claudechic/tests`
- Template freshness tests verify template/ stays in sync with repo
- Always consider cross-platform impact (Windows is actively supported)

### 8. Terminology (~5 lines)
Key disambiguations (the word "rules" has 4 meanings in this project):
- **Guardrail rules** (global/rules.yaml) != **agent context files** (.claude/rules/*.md)
- **Workflow activation** (/{id} in claudechic) != **slash commands** (.claude/commands/)
- **Manifest** (YAML parsed by ManifestLoader) != **config** (pixi.toml, copier.yml)
- **claudechic** is always lowercase

## Explicitly Excluded
These are already documented elsewhere and should NOT be in CLAUDE.md:
- Claudechic architecture/internals (covered by .claude/rules/*.md)
- Deep workflow/phase/hint system internals (covered by workflows-system.md, hints-system.md, manifest-yaml.md)
- Check protocol and guardrail authoring details (covered by checks-system.md, guardrails-system.md)
- Onboarding/bootstrapping bridge internals (runtime behavior of generated projects)
- End-user setup instructions (README + getting-started.md)
- File-by-file codebase descriptions (agents can read code)
- Generic advice ("write clean code", standard Python conventions)
- Full Windows compatibility catalog (most fixes were in claudechic)

## Success Criteria
An agent new to this repo should, after reading CLAUDE.md:
1. Know it's a template repo, not a runnable project
2. Use pixi, not pip
3. Run tests correctly on first attempt
4. Work on develop branch
5. Understand template/ vs root distinction
6. Know submodules/claudechic/ is a separate git repo requiring separate commits
7. Find deeper docs via cross-references
8. Not duplicate effort already covered by .claude/rules/
9. Know how to add a new workflow (directory + YAML + role files)
10. Know how to add hints (global vs workflow-specific)

## Sources
- Anthropic Memory Docs: https://code.claude.com/docs/en/memory
- Anthropic Best Practices: https://code.claude.com/docs/en/best-practices
- claude-code-action CLAUDE.md: https://github.com/anthropics/claude-code-action
- Git history: 331 commits (main repo), 150+ commits (claudechic), 80+ commits (template/)
- Leadership reviews: Composability, Terminology, Skeptic, UserAlignment, Researcher
