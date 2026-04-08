# User Alignment — Specification v2 Review

> **Reviewer:** UserAlignment Agent
> **Document reviewed:** `specification/SPECIFICATION.md` (Draft v2 — complete rewrite)
> **Date:** 2026-03-29
> **Source of truth:** `userprompt.md`

---

## Overall Verdict: ✅ STRONGLY ALIGNED

This is a better spec than v1. The rewrite removed the plugin framework that the user never asked for and replaced it with something the user would instantly recognize: "oh, this is just files in directories — and Copier picks which ones." The shift from "manifest + convention" to "convention IS the system" is the right call.

---

## 1. Composable + Easy to Start?

**User said:** "I want to make this repo more composable and easier to start a project with"

### ✅ Composability: EXCELLENT

The Five Seams model (§1.2) is genuinely composable. Each seam passes the swap test — add, remove, or replace what's on one side without changing anything on the other. This isn't theoretical; the R user example proves it concretely.

The key insight — "AI_PROJECT_TEMPLATE is **already composable**" (§1.1) — means the spec isn't bolting on a plugin system but rather codifying and documenting what already works. That's both lighter and more robust.

### ✅ Ease of Use: EXCELLENT

Three commands to a working project:
```bash
copier copy <url> my-project
cd my-project
source activate
```

And the R user example (§2) shows that adding a new environment is five steps with zero template changes. The user would look at this and say "that's easier than what we had before."

**No issues.**

---

## 2. Onboarding is a Real "Experience"?

**User said:** "I want to have users have an onboarding experience maybe web based / claude conversation based"

### ✅ ALIGNED — and my v1 flag was addressed

In v1, I flagged that `/init-project` was described as a "thin wrapper" and might feel mechanical. The v2 spec (§4.5) explicitly addresses this:

> "The `/init-project` skill is the **recommended onboarding path for new users**"

And it specifies five qualities:
1. Understands user context
2. **Explains WHY each add-on matters** — not just "enable guardrails?"
3. Handles ambiguity
4. Maps answers to Copier
5. Reports results and next steps

This is what "experience" means. The user's "maybe web based / claude conversation based" maps to: Claude skill is primary, Copier CLI for power users, web deferred. Correct prioritization.

### ✅ BONUS: Scientific user onboarding

The `project_type` and `science_domain` questions (§4.2) and the "Overnight Agent" pattern (§4.4) are new in v2. These weren't explicitly requested but they directly serve the user's actual user base (neuroscience postdocs on HPC). This is appropriate scope expansion — it makes the onboarding more relevant, not more complex.

ℹ️ USER ALIGNMENT: These additions (scientific project types, autonomous agent scaffolding) go beyond the original request. However, they serve the user's stated goal of "easier to start a project with" for their actual audience. This is value-additive scope, not scope creep. The user should be aware these were added and can choose to defer them.

**No issues.**

---

## 3. Existing Codebase Integration — First-class?

**User said:** "We should be able to let them add an existing code base as well"

### ✅ FIRST-CLASS — unchanged from v1's strong treatment

§5 dedicates a full section:
- Two explicit modes: Fresh vs Integrate
- Detailed integration flow (validate → detect → link → merge → PYTHONPATH)
- `.claude/` merge logic with specific rules (arrays appended, objects merged, scalar conflicts warned)
- Four failure scenarios with mitigations
- `require_env` relaxation (§5.4)

### ✅ "Add" resolved correctly

The Copier question says "Path to an existing codebase to integrate" and the flow symlinks/copies into `repos/`. This is "add your code to the template" — matching the user's word "add." The v1 "wrap" language is gone.

**No issues.**

---

## 4. Lightweight?

**User pushed back TWICE on over-engineering.**

### ✅ DRAMATICALLY LIGHTER than v1

v1 had: `plugin.yaml` manifests, a manifest dispatcher in `activate`, a `project.yaml` runtime config, `_plugin_enabled()` bash function, dependency resolution at activate time, fixed plugin order array.

v2 has: **none of that.** The `activate` script stays as-is. There is no `project.yaml`. There is no `plugin.yaml`. There is no dispatcher. Files exist in directories, and the existing discovery mechanisms find them.

**The "lightweight" test — would the user say "yes, that's what I meant"?**

To add a new capability:
- New environment → drop a `.yml` in `envs/`, run `install_env.py`
- New command → drop a script in `commands/`
- New skill → drop a `.md` in `.claude/commands/`
- New guardrail rules → drop a `.yaml` in `.claude/guardrails/rules.d/`
- New agent role → drop a `.md` in `AI_agents/project_team/`

No config files to update. No manifests to edit. No regeneration step (except guardrails, which already requires `generate_hooks.py`).

The user would look at this and say: "that's lightweight."

### ✅ Scope limits are explicit

§10 lists seven things the spec intentionally excludes — including "No plugin base class," "No runtime manifest or dispatcher," "No `plugin.yaml` manifests." These are the exact things v1 had that the user pushed back on. The spec learned.

**No issues.**

---

## 5. Landscape Survey Reflected?

**User said:** "we are not the first to try this. Research what exists, learn from prior art, and recommend additional plugins worth building or integrating."

### ✅ Survey influenced decisions

- Copier adopted over Cookiecutter (from landscape survey)
- Pixi identified as future env backend (§9.1) — from research
- STELLA biomedical system validates pattern mining approach (§6.2)
- FOCUS Framework informs scientific guardrails (§9.2)
- Anthropic's "Long-Running Claude" informs overnight agent pattern (§4.4)

### ✅ Plugin recommendations surfaced in spec — my v1 flag addressed

§9.2 now includes two tables of future add-ons (General and Scientific) with evidence sources. This was missing in v1. The user's "recommend additional plugins worth building or integrating" is directly answered:

**General:** CI/CD, docs, observability, linting, secrets, MCP server templates
**Scientific:** HPC/SLURM, citation validator, AI contribution tracker, domain skill packs, scientific guardrails

Each is tied to evidence from the landscape survey. This is exactly what the user asked for.

**No issues.**

---

## 6. User's Key Insight — Env Convention IS the Extensibility Model?

### ✅ CAPTURED — This is the spec's central thesis

§1.1: "AI_PROJECT_TEMPLATE is **already composable**. Five filesystem conventions serve as clean seams."

§3.1 dedicates the most space of any seam to the environment convention, including:
- The Four Verbs (Spec → Install → Lock → Activate) design language
- The cross-seam connection diagram (envs → commands via `require_env`)
- Conda-forge as v1 backend with explicit line-level mapping of where to cut for future backends

The R user example (§2) demonstrates this isn't theoretical — a user adds `envs/r-analysis.yml`, runs `install_env.py`, creates a command wrapper, and `source activate` just works. The env convention IS how you extend the system.

§9.1 on Pixi shows the team understands this seam well enough to plan a backend swap without changing the convention.

**No issues.**

---

## 7. R User Example — Does it Work End to End?

**The running example (§2) traces:**

```
1. copier copy → project created with base (env management + claudechic)
2. source activate → SLC bootstrapped, claudechic env shown
3. Create envs/r-analysis.yml → conda spec with R packages
4. python install_env.py r-analysis → env installed, lockfile generated
5. python lock_env.py r-analysis → versions frozen
6. Create commands/r-analysis → wrapper using require_env
7. source activate → shows ✔ r-analysis (installed) + command in PATH
8. r-analysis --version → R 4.4.x
```

### ✅ End-to-end plausible

Each step maps to existing code:
- Step 1: Copier generates files (§4)
- Step 2: `activate` scans `envs/*.yml` (existing behavior)
- Steps 3-5: `install_env.py` and `lock_env.py` already handle arbitrary env names
- Step 6: `require_env` already handles arbitrary env names via argument
- Step 7: `activate` already discovers `commands/*` and displays them
- Step 8: The command wrapper sources `require_env r-analysis` which activates the conda env

### ⚠️ ONE MINOR QUESTION: Step 5 ordering

The example shows `install_env.py` before `lock_env.py`. But `install_env.py` prefers lockfiles when they exist (§3.1: "Creates `envs/<name>/` from lockfile (preferred) or spec"). On first install with no lockfile, `install_env.py` installs from spec, then `lock_env.py` freezes. This works — but the example could note that on subsequent installs (e.g., on a collaborator's machine), the lockfile ensures reproducibility. Minor — not a misalignment, just a teaching opportunity for the implementer writing docs.

---

## Summary

### Alignment Scorecard

| # | Requirement | Status | Notes |
|---|------------|--------|-------|
| 1 | Composable + easy | ✅ | Five Seams + 3-command start |
| 2 | Onboarding experience | ✅ | `/init-project` is primary path with WHY-explanations |
| 3 | Existing codebase | ✅ | First-class §5 with merge logic and failure scenarios |
| 4 | Lightweight | ✅ | No framework, no manifests, directory conventions only |
| 5 | Landscape survey | ✅ | Influenced Copier choice + §9.2 future add-on tables |
| 6 | Env convention = extensibility | ✅ | Central thesis of the spec |
| 7 | R user end-to-end | ✅ | All steps map to existing code paths |

### Flags

| # | Flag | Severity | Action |
|---|------|----------|--------|
| 1 | Scientific project type + autonomous agents are beyond original request | Info | User should know these were added — they're value-additive but should be approved |
| 2 | R user example could note lockfile-first install for collaborators | Trivial | Teaching opportunity in docs, not a spec issue |

### Comparison: v1 → v2

| Dimension | v1 | v2 |
|-----------|----|----|
| Plugin system | YAML manifests + dispatcher + dependency resolver | Directory conventions (no plugin system) |
| `activate` changes | Complete rewrite as thin dispatcher | Stays as-is |
| `project.yaml` | New runtime config file | Does not exist |
| `plugin.yaml` | Per-plugin manifest files | Do not exist |
| Lightweight | Claimed lightweight | Actually lightweight |
| User would recognize? | Probably yes with squinting | Immediately yes |

### Final Assessment

**The specification is ready for implementation.** It is more aligned with user intent than v1 was — not because v1 was wrong, but because v2 absorbed the user's pushback and found the simpler truth underneath. The user said "lightweight" twice and the spec heard it. The directory-convention approach is the kind of thing users describe as "it just works" — which is exactly what "easier to start a project with" means.
