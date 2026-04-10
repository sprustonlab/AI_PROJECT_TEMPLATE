# Implementation User Alignment Review

> **Reviewer:** UserAlignment
> **Date:** 2026-03-30
> **Branch:** `composable-onboarding`
> **Compared against:** `userprompt.md` + spec + user statements

---

## Overall: ✅ ALIGNED with 3 gaps to close

The implementation delivers the core of what the user asked for. The `activate` script, `copier.yml`, pattern miner, and pixi integration are all real, working code that matches the spec. This is not a scaffold — it's a functional system.

---

## Requirement-by-Requirement

### 1. "more composable and easier to start a project with"
**✅ DELIVERED**

- `copier.yml` with `_subdirectory: "template"` and `_exclude` conditionals — add-ons are genuinely composable
- `template/` directory contains a complete project skeleton with Jinja2 templating
- `pixi.toml` in template uses `{{ project_name }}` — personalized from the start
- `source activate` bootstraps pixi automatically if not installed — genuinely easy

### 2. "onboarding experience maybe web based / claude conversation based"
**⚠️ PARTIALLY DELIVERED — `/init-project` skill is missing**

- **CLI onboarding via Copier:** ✅ Delivered — `copier.yml` is complete and matches the spec
- **Claude conversation-based (`/init-project`):** ❌ NOT IMPLEMENTED — no `init_project.md` skill found anywhere in the repo or template
- **Web:** Correctly deferred per spec

The spec (§4.5) designated `/init-project` as the "**recommended onboarding path for new users**" and "primary UX." The user said "claude conversation based." This is a gap.

**Quote from user:** "onboarding experience maybe web based / claude conversation based"
**Quote from spec:** "/init-project skill — Primary Onboarding Path"

**Impact:** Medium. The CLI path works, but the conversational path was the user's first instinct and the spec's recommended UX.

### 3. "let them add an existing code base as well"
**⚠️ PARTIALLY DELIVERED — question exists, integration logic does not**

- `copier.yml` has the `existing_codebase` question (line 62-67) ✅
- **But no post-generation hook or script exists** to actually symlink/copy the codebase into `repos/` ❌
- No `.claude/` merge logic implemented ❌
- The `require_env` relaxation (spec §5.4) is not applied ❌

The Copier questionnaire asks the question, but nothing acts on the answer. A user who provides an existing codebase path will see... nothing happen.

**Quote from user:** "let them add an existing code base as well"
**Quote from spec §5.2:** "Link codebase: Symlink or copy into repos/<basename>/." and "Python merge script in Copier post-generation hook"

**Impact:** High. This was an explicit user request and a key differentiator ("we should be able to let them add an existing code base as well").

### 4. "plugin type system (lightweight)"
**✅ DELIVERED — the strongest part of the implementation**

- No plugin framework, no manifest, no base class — correct
- `copier.yml` `_exclude` conditionals select files based on boolean flags — lightweight
- `activate` discovers seams by scanning directories — no registration needed
- `rules.d/` support in `generate_hooks.py` — drop-in rule sets work
- `import_env.py` — bridge script for users who think in `envs/*.yml` but need pixi

### 5. "analyze the seams"
**✅ DELIVERED (in spec; implementation follows the seam model)**

All five seams are implemented:
- **Environments:** `pixi.toml` features, `.pixi/envs/` discovery in `activate`
- **Commands:** `commands/*` auto-chmod'd and added to PATH
- **Skills:** `.claude/commands/*.md` discovered and displayed
- **Agent Roles:** `AI_agents/**/*.md` in template (conditionally included)
- **Guardrails:** `rules.yaml.jinja` + `rules.d/` support + `generate_hooks.py`

### 6. "we are not the first" — survey landscape, recommend plugins
**✅ DELIVERED (in spec; implementation reflects choices)**

Pixi chosen over alternatives. Copier chosen as templating tool. These are evidence of landscape analysis. The future add-ons table in the spec informs the template's extensibility points.

### 7. Port pattern miner from DECODE-PRISM
**✅ DELIVERED**

- `scripts/mine_patterns.py` — 40K+ bytes, full 3-tier pipeline
- All 5 spec changes implemented:
  1. ✅ JSONL parsing isolation (`Message`, `ParseResult`, `ParseStats` dataclasses)
  2. ✅ Version checking (`KNOWN_VERSIONS` set, `_detect_version`)
  3. ✅ Configurable project directories (`--project-dirs auto`)
  4. ✅ Validation mode (`--validate` flag)
  5. ✅ Configurable role detection (`DEFAULT_AGENT_ROLES`, `--roles`)
- `commands/mine-patterns` wrapper ✅
- `scripts/tests/test_parser.py` unit tests ✅
- `scripts/tests/test_regression.py` snapshot tests ✅
- `scripts/tests/fixtures/` with 3 JSONL fixtures ✅

This is the most complete implementation of any spec item.

### 8. "lightweight" binding constraint
**✅ RESPECTED**

- No plugin base class
- No manifest files
- No runtime dispatcher
- `activate` is ~230 lines of bash (reasonable)
- `copier.yml` is 75 lines
- Template `pixi.toml` is 17 lines

### 9. Env seam supports R, C via conda-forge
**✅ DELIVERED (via pixi + conda-forge)**

- `pixi.toml` uses `channels = ["conda-forge"]`
- `import_env.py` bridges `envs/*.yml` → `pixi.toml` features — the R user workflow works
- Multi-platform: `platforms = ["linux-64", "osx-arm64", "win-64"]` in template

### 10. Pixi validated on HPC + Mac
**✅ DELIVERED**

- `pixi.toml` and `pixi.lock` present at top level
- `activate` bootstraps pixi automatically
- `install_env.py` and `lock_env.py` still present (SLC fallback) — addressed in minor note below

### 11. Env var rename (AGENT_SESSION_PID)
**✅ DELIVERED**

- `role_guard.py` uses `AGENT_SESSION_PID` with `CLAUDECHIC_APP_PID` fallback (line 105)

---

## Gaps Summary

| # | Gap | Severity | User quote |
|---|-----|----------|------------|
| 1 | **`/init-project` skill not implemented** | Medium | "claude conversation based" |
| 2 | **Existing codebase integration is a no-op** — Copier question exists but no post-generation hook | High | "let them add an existing code base as well" |
| 3 | **`require_env` relaxation not applied** — spec §5.4 change not in `commands/require_env` | Low (blocks gap #2) | (supports existing codebase) |

---

## Minor Notes (not blocking)

1. **SLC scripts still present** — `install_env.py`, `lock_env.py`, `install_SLC.py` remain in the repo root alongside pixi. Per spec, they're a "documented fallback." This is fine, but they don't appear in `template/` — so new projects won't get them. Consistent with spec intent.

2. **`template/commands/` missing `require_env`** — The template ships `claudechic` and `mine-patterns` commands but not `require_env`. Users who want to add their own env-activating commands (Pattern A from spec §3.2) would need it. However, with pixi, `pixi run -e <name>` replaces this — so it may be intentionally omitted. Worth confirming.

3. **`activate` display is clean and welcoming** — Shows pixi version, installed/available envs, CLI commands, Claude skills, guardrails status. Good UX for new users.

4. **`import_env.py` is a nice bridge** — Not in the spec but serves the R-user workflow well. Users who think in `envs/*.yml` get a path to pixi. This is a good scope addition.

---

## Recommendation

The implementation is solid and ready to ship with two fixes:

1. **HIGH: Implement existing codebase integration** — Add a Copier `_tasks` post-generation hook that: (a) symlinks/copies the path into `repos/<basename>/`, (b) runs `.claude/` merge logic, (c) applies `require_env` relaxation if that file exists.

2. **MEDIUM: Create `/init-project` skill** — A `.claude/commands/init_project.md` that walks users through project setup conversationally and maps answers to `copier copy --data` flags. This was the spec's "primary onboarding path."

Everything else is delivered and aligned with user intent.
