# Fresh Skeptic Review — SPECIFICATION.md (Draft v2)

> **Reviewer:** Skeptic (fresh eyes, no prior context)
> **Date:** 2026-03-29
> **Verdict:** Spec is **good but has 4 real problems** that will block or derail implementation if not addressed. The architecture is sound — the issues are in gaps between what the spec says and what the codebase actually is.

---

## 1. Is This Spec Actually Implementable?

**Mostly yes, with caveats.**

The spec's strongest quality is its restraint — "the directory structure IS the plugin system" is correct and avoids the classic over-engineering trap. An implementer can read this and know what to build.

### Where an Implementer WILL Get Stuck

**Problem A: The Pixi migration scope is understated.**

The spec says "Simplify `activate` and `require_env`" as a line item. But `activate` is 261 lines and `require_env` is 285 lines. Both are deeply entangled with SLC/conda assumptions:

- `activate` lines 40-84: SLC bootstrap + conda activate
- `require_env`: hard-coded `SLC_BASE` checks, `conda activate` calls, Miniforge download logic

"Simplify" is not an implementation instruction. The implementer needs to know: **what does the pixi version of `activate` look like?** The spec shows updated command wrappers (4 lines) but never shows the updated `activate` script. That's the hard part.

**Recommendation:** Write a skeleton of the pixi-based `activate` script. Even 20 lines of pseudocode would unblock the implementer.

**Problem B: The `.claude/` merge logic (§5.2) is hand-waved.**

The spec says:
> - Arrays: Template entries appended to existing arrays
> - Objects: Template keys added; existing keys preserved
> - Scalar conflicts: Warn and preserve user's value
> - Implementation: Python merge script in Copier post-generation hook

This is a *description of desired behavior*, not a spec. What files get merged? `.claude/settings.json`? `.claude/commands/*.md`? What about `.claude/guardrails/rules.yaml` — do template rules merge with existing rules? What's the merge key? What if the user has a `rules.yaml` with IDs that collide with template IDs?

The existing codebase doesn't even have a `rules.yaml` yet (only `rules.yaml.example`), so the merge scenario hasn't been tested against reality.

**Recommendation:** Enumerate the specific files that need merge logic. For each, define the merge strategy concretely. For v1, consider the simpler approach: if `.claude/` exists, warn and don't overwrite — let the user merge manually. Premature merge automation is a bug factory.

**Problem C: Copier `_exclude` syntax is untested.**

The `copier.yml` in §4.2 uses Jinja2 in `_exclude`:
```yaml
_exclude:
  - "{% if not use_guardrails %}.claude/guardrails/{% endif %}"
```

This excludes an entire directory tree. Has this been tested with Copier 9.x? Copier's `_exclude` uses glob patterns, and mixing Jinja2 conditionals with directory paths has known edge cases (trailing slashes, nested paths). If this doesn't work as expected, the entire onboarding flow breaks.

**Recommendation:** Build and test the `copier.yml` early. This is a load-bearing file — don't defer it.

---

## 2. Are the 8 Code Changes the Right Ones?

**7 of 8 are correct. One is unnecessary for v1. One is missing.**

### Unnecessary for v1: Change #8 — Contributor docs/templates

The spec already IS the contributor documentation. The seam analyses, terminology, and "How to Add" sections are thorough. Writing separate contributor docs before the system is built and used is premature — you'll rewrite them after implementation reveals what actually confuses people.

**Recommendation:** Cut #8 from v1. The spec files serve as docs. Write contributor templates after the first external user tries to add a plugin and gets stuck.

### Missing: `activate` script rewrite

The Pixi migration (Change #1) says "Simplify `activate`" but this deserves its own line item. The `activate` script is the **user's first contact** with the system. It handles:
- SLC bootstrap (replaced by pixi)
- Env discovery and status display
- PATH setup for commands/
- PYTHONPATH setup for repos/
- Skill discovery display

Rewriting this is not a sub-task of "Pixi migration" — it's a distinct deliverable with its own test surface. The pixi migration deletes `install_env.py` and `lock_env.py` (clear). But `activate` needs a **rewrite**, not a deletion, and the spec doesn't specify what it looks like after.

**Recommendation:** Add Change #9: "`activate` script rewrite for pixi backend" with a clear description of what the new script does.

---

## 3. Pixi — Is the Migration Risk Real?

**The validation is solid. The risk is in the SLC fallback story, not in pixi itself.**

The HPC validation table (§3.1.1) is genuinely thorough — NFS, editable packages, cross-platform pack, offline unpack. These are the real failure modes for HPC, and they all pass. Good.

### The Real Risk: Dual-Backend Maintenance

The spec says:
> SLC scripts remain as a documented fallback for locked-down environments where pixi cannot be installed.

This means the codebase ships with **two complete env management backends**: pixi (primary) AND SLC (fallback). That's ~700 lines of SLC code kept alive "just in case." In practice:

1. Nobody will test the SLC fallback after pixi becomes primary
2. The first time someone needs the fallback, it will be broken
3. Maintaining two backends doubles the surface area for env-related bugs

**The honest choice is:** Either pixi is ready and SLC is deleted, or pixi isn't ready and SLC stays primary. The "keep both" option is a complexity trap disguised as caution.

**Recommendation:** For v1, pick one. The validation results say pixi is ready. Delete SLC scripts. If a user truly can't install pixi (a single static binary), they have bigger problems than this template can solve. Document the SLC approach in a `LEGACY.md` for historical reference, but don't ship it as a maintained fallback.

### Edge Cases Not Yet Tested (acknowledged in spec)

- **Concurrent NFS access:** The spec says "low risk, pixi uses atomic file operations." This is probably true but "probably" isn't "tested." On shared HPC filesystems, NFS's definition of "atomic" is... creative. This isn't a v1 blocker, but it should be a known risk, not a dismissed one.
- **SLURM job context:** Expected to work. Reasonable assumption, but add it to a post-launch validation checklist.

---

## 4. `rules.d/` — Is This Actually Needed for v1?

**No. It's premature.**

Here's the reality:
- `rules.yaml` doesn't even exist yet (only `rules.yaml.example`)
- There are zero contributed rule sets today
- The spec's own future add-ons table lists "Scientific Guardrails" as future work
- The `generate_hooks.py` change is "Small — add glob + merge before validation"

The change IS small. But the problem isn't effort — it's that you're building an extension mechanism for a system that has zero users and zero extensions. You don't yet know:
- What the ID collision resolution should actually be (first wins? error? namespace prefix?)
- Whether rule sets need dependency ordering (rule A must be processed before rule B)
- Whether contributed rules need to override core rules or only add new ones

Building `rules.d/` now means committing to a merge semantic before you have data on what merge semantics are needed.

**Recommendation:** Ship v1 with a single `rules.yaml`. Add `rules.d/` when the first person actually needs to contribute a rule set. The change is small enough to do reactively — there's no architectural risk in deferring it. Add a comment in `generate_hooks.py`: `# FUTURE: support rules.d/*.yaml for contributed rule sets`.

---

## 5. Existing Codebase Integration — Does the Merge Logic Work?

**The symlink approach is fine. The `.claude/` merge is the weak point.**

### What Works

- `repos/<basename>/` symlink — simple, clean, no magic
- `PYTHONPATH` auto-setup via `activate` — already works today
- `require_env` relaxation (§5.4) — correct and minimal change

### What Doesn't Work (Yet)

**The `.claude/` merge problem is harder than the spec acknowledges.**

A user with an existing codebase likely has:
- `.claude/settings.json` — with their own MCP servers, permissions, model preferences
- `.claude/commands/*.md` — their own skills
- `.claude/CLAUDE.md` — their project instructions

The template wants to add:
- `.claude/guardrails/` — entire new directory (no conflict, fine)
- `.claude/commands/ao_project_team.md` — new skill (no conflict if user doesn't have one)
- Settings for hooks pointing to guardrail scripts (CONFLICT with existing settings)

The hook configuration in `.claude/settings.json` is the real conflict point. The guardrails system requires specific `hooks` entries. If the user already has hooks, you need array merging with dedup. The spec says "Arrays: Template entries appended" but hook entries have structure — you can't just append blindly.

**Recommendation:** For v1, the integration flow should:
1. Symlink codebase into `repos/` (done)
2. Copy template's `.claude/guardrails/` (no conflict — new directory)
3. Copy template's `.claude/commands/` skills (skip if file exists)
4. For `.claude/settings.json`: **print a diff** showing what needs to be added, let user merge manually
5. Relax `require_env` (done)

This is less magical but actually correct. Automated JSON merging can come in v2 when you know the real conflict patterns.

---

## 6. Is the Scope Right?

**Slightly too much for v1. Two items should be deferred.**

### Keep for v1 (essential)
1. **Pixi migration** — this is the core value; makes env management actually good
2. **Copier template** — this is the onboarding; without it there's no "composable" story
3. **Pattern miner port** — user explicitly asked for it; 904 lines, clean code, medium effort is accurate
4. **Env var rename** — tiny, do it now to avoid tech debt
5. **`require_env` relaxation** — tiny, enables existing codebase integration

### Defer to v1.1
6. **`rules.d/` support** — premature (see §4 above)
7. **Contributor docs/templates** — premature (see §2 above)

### Why This Scope is Right

The user asked for: composability, onboarding, existing codebase integration, pattern miner port, and plugin architecture research. The spec delivers all of these. The research is already done (landscape survey, env backend research, seam analyses — 18 supporting documents). The implementation is focused on the actual code changes.

The risk isn't scope creep — it's that the Pixi migration alone is a "Large" effort that touches the most critical user-facing scripts (`activate`, `require_env`, command wrappers). If that goes sideways, nothing else matters.

**Recommendation:** Implement in this order:
1. Pixi migration (including `activate` rewrite) — get this working and tested first
2. Copier template — depends on knowing what the pixi-based project looks like
3. Pattern miner port — independent, can parallelize
4. Env var rename + `require_env` relaxation — tiny, slot in anywhere
5. Existing codebase integration — test after Copier works

---

## 7. Unvalidated Assumptions

### Assumption 1: "Copier is the right templating tool"
**Status: Probably fine, but not validated.**

The spec doesn't discuss why Copier over alternatives (cookiecutter, yeoman, custom script). Copier's `_exclude` + Jinja2 conditional approach is assumed to work for the directory-inclusion pattern. This should be validated with a minimal prototype before building the full `copier.yml`.

### Assumption 2: "pixi init --import reads envs/*.yml directly"
**Status: Claimed in spec, needs verification.**

§3.1.1 says: "Existing `envs/*.yml` specs are read directly by pixi — no manual rewrite needed." The `pixi init --import` command is shown, but was this actually tested with the project's specific yml files? The validation table tests pixi install/pack/unpack but doesn't explicitly list yml import.

### Assumption 3: "The Claude skill `/init-project` can invoke Copier"
**Status: Architecturally sound, implementation unclear.**

§4.5 says the skill "Maps answers to Copier — translates decisions into `copier copy --data` flags." This means the Claude skill runs a bash command with Copier. That's fine — Claude Code can do this. But the skill needs to handle Copier's output, errors, and the case where Copier isn't installed. None of this is specified.

### Assumption 4: "Users will add environments via `pixi add --feature`"
**Status: UX assumption, not validated.**

The running example shows `pixi add --feature r-analysis r-base r-tidyverse ...`. This is pixi's feature/environment system. But users coming from conda think in terms of `environment.yml` files. The spec needs to be clear about whether users interact with pixi directly or through template wrapper commands. The current approach (direct pixi) is simpler but requires users to learn pixi.

### Assumption 5: "The guardrails `rules.yaml.example` is sufficient as a starting point"
**Status: Gap.**

The codebase has `rules.yaml.example` but no actual `rules.yaml`. The spec doesn't mention creating the initial `rules.yaml` from the example. When Copier generates a project with `use_guardrails: true`, what `rules.yaml` does it create? The spec's Copier section doesn't show the rules file content.

---

## Summary Table

| Issue | Severity | Recommendation |
|-------|----------|----------------|
| `activate` rewrite not specified | **High** | Write skeleton of pixi-based activate |
| `.claude/` merge logic hand-waved | **High** | Enumerate files, simplify to manual merge for v1 |
| Dual SLC/pixi backend maintenance | **Medium** | Pick one — delete SLC for v1 |
| `rules.d/` premature | **Low** | Defer to v1.1 |
| Contributor docs premature | **Low** | Defer to v1.1 |
| Copier `_exclude` untested | **Medium** | Prototype early |
| `pixi init --import` not verified with project ymls | **Medium** | Test before implementation |
| Initial `rules.yaml` content unspecified | **Medium** | Define what ships in template |
| `activate` rewrite missing from change list | **Medium** | Add as Change #9 |

---

## Bottom Line

The architecture is right. "Directory conventions as plugin system" is the correct insight and avoids the framework trap. The seam analysis is thorough. The pixi validation is real.

The problems are all in the **implementation gap** — places where the spec describes desired behavior without specifying how. The `activate` rewrite, the merge logic, and the dual-backend decision are the three things that will actually block an implementer.

Fix those three, and this spec is ready to build.
