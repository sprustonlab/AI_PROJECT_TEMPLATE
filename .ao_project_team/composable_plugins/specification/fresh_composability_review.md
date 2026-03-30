# Fresh Composability Review

> **Reviewer:** Composability (fresh eyes, no prior context)
> **Date:** 2026-03-29
> **Spec version:** Draft v2
> **Verdict:** Strong architecture. The "directory IS the plugin system" insight is genuinely compositional. A few hidden couplings and one structural concern below.

---

## 1. Do the Five Seams Pass the Swap Test?

### Environments (`envs/`) — PASS with caveat

**Swap test:** Can I replace conda with pixi without changing commands, skills, roles, or guardrails?

Yes — the spec correctly identifies that the rest of the template only checks `[[ -d envs/<name> ]]` and never reads spec/lockfile contents. The seam boundary is the directory existence check.

**Caveat:** The `commands/require_env` script IS the seam enforcement point. It currently hard-codes `conda activate`. The pixi migration replaces this with `pixi run -e <name>`, which means `require_env` is a shared coupling point between the Environments seam and the Commands seam. This isn't a violation — it's the *correct* place for this coupling to live — but the spec should acknowledge that `require_env` is a cross-seam adapter, not part of either seam independently. If someone swaps the env backend, they must also update `require_env`. This is fine as long as it's the ONLY thing they update.

**Status:** The pixi migration section handles this well. Clean.

### Commands (`commands/`) — PASS

**Swap test:** Can I add/remove a command without touching environments, skills, roles, or guardrails?

Yes. Drop an executable in `commands/`, `activate` discovers it. Remove it, it's gone. The discovery mechanism (glob `commands/*`, skip `.md` and dotfiles, auto-chmod) is completely agnostic to content.

**Clean seam.** No issues.

### Skills (`.claude/commands/`) — PASS

**Swap test:** Can I add/remove a skill without touching other seams?

Yes. Claude Code's auto-discovery is the seam mechanism. The spec correctly identifies the "short entry point" pattern (skill file is a pointer, logic lives elsewhere) which keeps skills from becoming monolithic.

**Clean seam.** No issues.

### Agent Roles (`AI_agents/**/*.md`) — CONDITIONAL PASS

**Swap test:** Can I add/remove a role without touching other seams?

Mostly yes. Adding a new role file is self-contained. BUT:

1. **Coordinator coupling:** The Coordinator must know about a role to spawn it. Adding `DATA_VALIDATOR.md` is useless unless Coordinator is told when to spawn it. The spec acknowledges this ("edit COORDINATOR.md or let Coordinator discover dynamically") but the "dynamic discovery" path is unspecified. This is a soft coupling — not a seam violation, but it means "drop a file" is necessary but not sufficient.

2. **Guardrail coupling:** If you add a role that should have guardrail restrictions, you need to also add rules targeting that role. This is cross-seam coordination. Again, not a violation (the role works without guardrails), but the spec should be explicit that the roles seam has *optional* cross-seam connections to guardrails.

**Verdict:** The seam is clean for the file convention. The human/agent workflow around it has soft coupling. Acceptable for v1.

### Guardrail Rules (`.claude/guardrails/`) — PASS

**Swap test:** Can I add/remove a rule without touching other seams?

Yes. The `rules.d/` directory is a clean extension point. Drop a YAML file, regenerate hooks. The ID namespace convention prevents collisions.

**One concern:** `generate_hooks.py` is a code generator that must be re-run after changes. This is a manual step that breaks the "just drop a file" pattern of other seams. Every other seam has automatic discovery; this one requires a manual regeneration step. Consider whether `generate_hooks.py` could auto-run as part of `activate` (or a git hook), so the "drop and discover" pattern holds.

---

## 2. Architecture Soundness — Hidden Coupling Analysis

### The `activate` Script: Hidden God Object

The `activate` script is the linchpin of the entire system. It:
- Bootstraps the env manager (SLC/pixi)
- Scans `envs/*.yml` for status display
- Adds `commands/` to PATH
- Scans `.claude/commands/` for skill display
- Sets `PROJECT_ROOT`, `SLC_BASE`, `PYTHONPATH`
- Checks for claudechic submodule specifically

This is a **hidden coupling point**. While each seam is independently extensible via files, the `activate` script hard-codes awareness of ALL five seams. If you add a sixth seam, you must modify `activate`.

**Recommendation:** This is acceptable for v1 (five seams is manageable), but document `activate` as the "seam registry" — the one file that knows about all seams. Future-proof by noting that a sixth seam requires an `activate` update.

### Claudechic as Base: Correct but Constraining

The spec puts claudechic in the base layer (always present). This is honest — "this is an AI project template, claudechic IS the point." But it means:

- The template cannot be used without claudechic
- Environments must always include the claudechic env
- The `activate` script hard-checks for the claudechic submodule

This is a **design decision, not a bug**. But if the template ever needs to support users who want the env management + commands + guardrails WITHOUT claudechic (e.g., using vanilla Claude Code), there's no clean way to remove it today. Worth documenting as a known constraint.

### The Env Var Protocol: Underspecified Seam

The connection between claudechic and guardrails flows through environment variables (`CLAUDE_AGENT_NAME`, `CLAUDE_AGENT_ROLE`, `AGENT_SESSION_PID`). This is a clean seam in principle — env vars are a universal interface. But:

- Which env vars are part of the contract vs. implementation detail?
- What happens if Claude Code changes its env var names?
- The `AGENT_SESSION_PID` rename (from `CLAUDECHIC_APP_PID`) shows this seam has already shifted once.

**Recommendation:** The spec should include a "Env Var Contract" table: which vars are guaranteed stable, which are internal. This prevents the guardrails team from depending on vars that might change.

---

## 3. Is Pixi the Right Choice? Seam Issues with Migration

### Pixi as Backend: Excellent Composability

Pixi is a strong choice. It:
- Replaces ~700 lines of custom Python with a single binary
- Provides multi-platform lockfiles (eliminates a per-platform coupling)
- Has native conda + PyPI co-resolution (eliminates the `pip:` section hack)
- `pixi-pack` solves HPC air-gap better than custom download+cache

The HPC validation table is convincing. The cross-platform pack test is exactly what a cluster user needs.

### Seam Issue: Dual-Backend Period

The spec says "SLC scripts remain as a documented fallback." This means during migration there are TWO env backends that must be kept compatible. The seam question: do both backends produce the same directory structure (`envs/<name>/`)?

If yes — clean, the rest of the template can't tell which backend was used.
If no — dirty seam, commands that depend on env structure will break.

**The spec implies yes** (both use `envs/*.yml` as spec format, both produce `envs/<name>/` directories). Make this explicit: "Both backends MUST produce `envs/<name>/` as the installed directory. This is the seam contract."

### Seam Issue: `pixi.toml` vs `envs/*.yml`

Pixi introduces `pixi.toml` as the spec format. But the current convention is `envs/<name>.yml`. The spec says "pixi reads both" — but this means during migration, specs could live in TWO places. This creates a discovery ambiguity: does `activate` scan `envs/*.yml` OR parse `pixi.toml`?

**Recommendation:** Pick one. For v1, if pixi is primary, the spec convention should migrate to `pixi.toml` with named features. The `envs/*.yml` files become a legacy format. Don't maintain parallel discovery.

---

## 4. Does the Copier Approach Create New Coupling?

### Copier as File Assembler: Clean

Copier is used correctly — it selects which files land in which directories, then gets out of the way. Post-generation, there's no trace of Copier in the running system. The `activate` script doesn't know it was Copier that created the files. This is the right pattern.

### Potential Coupling: `_exclude` Jinja Logic

The `copier.yml` `_exclude` section couples Copier to the internal directory structure of each add-on:

```yaml
- "{% if not use_guardrails %}.claude/guardrails/{% endif %}"
- "{% if not use_project_team %}AI_agents/{% endif %}"
```

If guardrails moves from `.claude/guardrails/` to `.guardrails/`, the Copier template must be updated. This is acceptable — Copier IS the assembly tool, it SHOULD know the structure. Not a violation.

### Potential Issue: Copier Update Story

The spec mentions `copier update` but doesn't address: what happens when the template evolves and a user who chose `use_guardrails: false` now wants to add guardrails? Can they re-run Copier with different answers? Does Copier handle additive updates cleanly?

This is a Copier limitation question, not an architecture issue. But worth noting in the spec — the "add an add-on later" story needs to be validated.

---

## 5. Missing Seams or Concerns

### Missing: The `.claude/settings.json` Seam

Claude Code's `settings.json` (or `CLAUDE.md`) is a configuration seam that the spec doesn't address. When guardrails are enabled, do they require specific `settings.json` entries? When project-team is enabled, does it need `CLAUDE.md` modifications? If so, there's an implicit sixth seam: **Claude Code Configuration**.

### Missing: The Git Seam

Several features interact with git:
- Claudechic is a git submodule
- The `activate` script resolves paths relative to git root
- The "overnight agent" pattern involves git commits
- `require_env` checks `PROJECT_ROOT == REPO_ROOT`

Git is an implicit seam. The spec addresses the `require_env` relaxation, which is good, but doesn't identify git as a seam dimension. What if someone uses the template outside of a git repo?

### Missing: State/Working Directory Convention

The project-team creates `.ao_project_team/<project>/` for state. Pattern miner presumably writes to `PATTERNS.md`. These are outputs that live in the project directory. Is there a convention for where add-ons store their runtime state? Without one, each add-on invents its own, and you get dotfile proliferation.

**Recommendation:** Consider a convention: add-on runtime state goes in `.state/<addon>/` or similar. Not critical for v1, but worth noting.

---

## 6. Over-Engineered or Under-Engineered?

### Appropriately Engineered

This spec hits a rare sweet spot. It:

1. **Resists framework temptation.** No plugin base class, no manifest loader, no event bus. The earlier composability analysis must have pushed for protocols and injection — the spec correctly identified that the filesystem conventions already provide the composition law.

2. **Documents what exists rather than inventing.** The five seams were already there. Codifying them (with Copier for assembly) is the minimum viable intervention.

3. **Keeps the crystal small.** The axes are essentially: {base} x {guardrails: on/off} x {project-team: on/off} x {pattern-miner: on/off} x {project-type: general/scientific}. That's roughly 2x2x2x2 = 16 configurations. Manageable. Testable.

### Slight Over-Engineering: The Four Verbs Taxonomy

The "Four Verbs" (Spec, Install, Lock, Activate) is useful documentation but risks becoming prescriptive. Not every future env backend maps cleanly to four verbs (e.g., Nix has a different model). Keep it as descriptive documentation, not a protocol that backends must implement.

### Slight Under-Engineering: Copier Testing Strategy

The spec doesn't mention how to test the 16 Copier configurations. A combinatorial matrix of `copier copy` with different flag combinations, each verified to produce a working project, would catch crystal holes. This is the 10-point test from the composability framework applied to the Copier template.

**Recommendation:** Add a CI job that runs Copier with each valid configuration and verifies `source activate` succeeds.

---

## Summary Verdict

| Aspect | Grade | Notes |
|--------|-------|-------|
| Seam independence | **A-** | Five seams are genuinely independent. `require_env` as cross-seam adapter is correctly placed. `generate_hooks.py` manual step is the only blemish. |
| Hidden coupling | **B+** | `activate` as god object is manageable for v1. Env var protocol needs a stability contract. |
| Pixi choice | **A** | Well-validated, solves real pain points, cleaner than SLC. Dual-backend period needs explicit contract. |
| Copier approach | **A** | Correct pattern — assembly-time only, no runtime trace. "Add add-on later" story needs validation. |
| Missing seams | **B** | Git, `.claude/settings.json`, and state directory conventions are implicit. Worth documenting. |
| Engineering level | **A** | Resists over-engineering. The "no framework" insight is the key architectural decision and it's correct. |

### Top 3 Action Items

1. **Make the dual-backend seam contract explicit:** "Both SLC and pixi MUST produce `envs/<name>/` directories. This is the seam boundary." Decide on `pixi.toml` vs `envs/*.yml` — don't maintain parallel discovery.

2. **Add Copier configuration testing:** CI matrix that generates all valid flag combinations and verifies each produces a bootable project.

3. **Document `activate` as the seam registry:** Acknowledge it's the one file that knows about all seams, and note that adding a sixth seam requires updating it.

---

*Reviewed with fresh eyes. The architecture is sound. The key insight — "the directory structure IS the plugin system" — is correct and avoids the framework trap that kills most plugin systems. Ship it.*
