# Fresh User Alignment Review

> **Reviewer:** UserAlignment (fresh eyes, no prior context)
> **Date:** 2026-03-29
> **Spec reviewed:** `SPECIFICATION.md` (Draft v2)
> **Source of truth:** `userprompt.md` + user statements quoted in task brief

---

## Overall Alignment Status: ✅ STRONGLY ALIGNED

This spec is unusually faithful to user intent. It takes the user's own language ("seams," "lightweight," "composable") and builds the architecture around those words rather than reinterpreting them. The spec explicitly resists over-engineering (Section 10 scope limits) and identifies the directory structure as the plugin system — exactly what the user validated.

---

## Requirement-by-Requirement Check

### 1. "more composable and easier to start a project with"
**Status: ✅ ALIGNED**

The five-seam model (§1.2) directly addresses composability. Copier onboarding (§4) addresses ease of starting. The "swap test" language in §1.2 is the right framing — if you can add/remove without touching the other side, it's composable.

### 2. "onboarding experience maybe web based / claude conversation based"
**Status: ✅ ALIGNED (with honest deferral)**

The user said "maybe web based / claude conversation based" — this is tentative language, not a hard requirement. The spec delivers:
- **CLI via Copier** — MVP (§4.1)
- **Claude skill `/init-project`** — conversation-based, second priority (§4.5)
- **Web** — explicitly deferred (§4.1, §10)

The user's "maybe" is respected. The conversational path IS delivered. Web is honestly deferred. No misalignment.

### 3. "let them add an existing code base as well"
**Status: ✅ ALIGNED**

Section 5 covers this thoroughly: two modes (fresh vs. integrate), `.claude/` merge logic, `require_env` relaxation, and failure scenarios. The `existing_codebase` parameter in the Copier questionnaire (§4.2) makes it a first-class onboarding option.

### 4. "plugin type system (lightweight)"
**Status: ✅ ALIGNED — this is the spec's strongest point**

The user pushed back TWICE on over-engineering. The spec responds with:
- "There is no plugin framework. No runtime dispatch. No manifest loader. The directory structure IS the plugin system." (§1.1)
- Section 10 explicitly lists what's excluded (no base class, no manifest, no event bus, no dispatcher)
- Each seam's "How to Add" section is 3-5 steps of file creation — genuinely lightweight

This is exactly what the user validated. The spec heard the pushback.

### 5. "analyze the seams"
**Status: ✅ ALIGNED**

The five seams are identified, documented with conventions and contracts, and cross-referenced to detailed analysis files (`seam_env_management.md`, `seam_commands_and_skills.md`, `seam_roles_and_guardrails.md`). The seam analysis is the architectural backbone of the spec.

### 6. "we are not the first" — survey landscape, recommend plugins
**Status: ✅ ALIGNED**

- The spec references prior art throughout (Nx generators, ECC, Projen, Cookiecutter Data Science, FOCUS Framework, K-Dense-AI, STELLA/FutureHouse, Anthropic research, OpenAI Agents SDK)
- Section 9.2 lists concrete future add-on recommendations organized by general vs. scientific
- The spec references `research_env_backends.md` for the full landscape survey
- The Copier choice itself appears informed by landscape analysis

### 7. Port pattern miner from DECODE-PRISM
**Status: ✅ ALIGNED**

Section 6 covers the port with specific required changes: JSONL parsing isolation, version checking, configurable paths, validation mode, configurable role detection, and snapshot tests. The source path is correctly referenced. It's scoped as a Copier add-on (`use_pattern_miner` in §4.2).

### 8. User pushed back TWICE on over-engineering — "lightweight" is binding
**Status: ✅ ALIGNED**

Section 10 ("Explicit Scope Limits") is a direct response to this constraint. Seven explicit exclusions, each with the note "can be revisited when concrete need arises." The spec's entire philosophy — conventions over framework — respects this binding constraint.

### 9. Env management conventions ARE the extensibility model
**Status: ✅ ALIGNED**

The user identified this insight, and the spec builds on it. §1.1: "AI_PROJECT_TEMPLATE is already composable. Five filesystem conventions serve as clean seams." The running example (§2) demonstrates a user extending the system by following conventions, not by writing plugin code.

### 10. R users, C codebases — env seam must support multiple languages via conda-forge
**Status: ✅ ALIGNED**

- §2 is literally "Running Example: R User with Claudechic"
- §3.1 "Conda-forge as v1 Backend" includes an explicit table: R packages, C/C++ compilers, CUDA, HPC tools
- §3.1 "How to Add an Environment" shows both R and C/C++ toolchain examples
- The R user running example is threaded throughout the spec (§2, §3.1, §3.1.1)

### 11. User validated pixi on HPC cluster and Mac
**Status: ✅ ALIGNED**

§3.1.1 documents the validation results with a table of 6 tests (all passing), specific paths (`/groups/spruston/home/moharb/`), and platform details (linux-64 cluster, osx-arm64). Pixi is confirmed as the primary v1 backend, not a future consideration.

---

## Potential Issues (Minor)

### ⚠️ Issue 1: SLC Fallback May Contradict "Lightweight"

The spec says pixi is the primary backend but keeps SLC scripts as a "documented fallback" (§3.1.1, end). This means the template ships with TWO env management systems (pixi + SLC). The user's "lightweight" constraint may conflict with maintaining dual backends.

**Quote from user:** "lightweight" (binding constraint, pushed back twice)

**Recommendation:** Clarify whether the SLC fallback is template code that ships, or just documentation saying "if you can't use pixi, here's the old approach." If it's shipped code, it's not lightweight. If it's just docs, it's fine.

### ⚠️ Issue 2: Running Example Shows Both Old and New Workflows

§2 and §3.1 "How to Add an Environment" show the OLD SLC workflow (`install_env.py`, `lock_env.py`, `require_env`). Then §3.1.1 shows the NEW pixi workflow. This creates confusion about what v1 actually ships.

**Recommendation:** Since pixi is confirmed for v1, the running example and "How to Add" sections should use pixi as the primary workflow. Move SLC to an appendix or fallback section.

### ❓ Issue 3: Copier Requires `pip install copier` — Bootstrap Gap

§4.3 starts with `pip install copier`. But the whole point of the template is to manage environments. A user who doesn't have pip configured hits a chicken-and-egg problem. Pixi could install copier (`pixi global install copier` or similar).

**Recommendation:** Address the bootstrap story. How does a brand-new user (the target audience for "easier to start a project with") get from zero to `copier copy`? This is an onboarding gap.

### ❓ Issue 4: `/init-project` Skill Location Ambiguity

The `/init-project` skill (§4.5) lives in `.claude/commands/init_project.md` — but this is inside the template. A user who hasn't created a project yet doesn't have this skill. How do they discover it?

**Recommendation:** Clarify: is `/init-project` a skill in an ALREADY-created project (for re-configuration), or is it meant to be the entry point for new users? If the latter, it needs to live somewhere accessible before project creation (e.g., a global Claude skill, or documentation that says "run this command first").

---

## Scope Creep Check

### ℹ️ Minor: "Overnight Agent" Pattern (§4.4)

The user did NOT ask for autonomous/overnight agent scaffolding. This is an addition. However:
- It's gated behind `autonomous_agents: true` (opt-in)
- It's only shown for `project_type == 'scientific'`
- It's backed by Anthropic research evidence
- It doesn't add code complexity to the base

**Verdict:** Acceptable scope addition — opt-in, evidence-based, doesn't violate lightweight constraint.

### ℹ️ Minor: Scientific Domain Questions (§4.2)

The user didn't specifically ask for science-domain-specific onboarding questions (`science_domain`, `autonomous_agents`). But the user IS a neuroscience researcher on an HPC cluster, so this is anticipating their actual use case.

**Verdict:** Acceptable — it's conditional (`when:` clauses) and serves the actual user.

---

## What's NOT in the Spec That the User Asked For

Nothing significant is missing. Every explicit user request maps to a spec section. The only gaps are the minor bootstrap/discovery issues noted above.

---

## Summary

| Category | Count |
|----------|-------|
| ✅ Fully aligned | 11/11 user requirements |
| ⚠️ Minor issues | 2 (SLC dual-backend, running example ordering) |
| ❓ Needs clarification | 2 (bootstrap gap, /init-project discovery) |
| ℹ️ Acceptable scope additions | 2 (overnight agent, science domain) |
| 🚫 Missing user requirements | 0 |
| 🚫 Misaligned with user intent | 0 |

**Bottom line:** This spec is ready for implementation. The minor issues are editorial (running example ordering) and architectural clarifications (bootstrap story, SLC fallback scope) — none block implementation. The spec's core philosophy — directory conventions as the plugin system, no framework — is exactly what the user asked for and validated.
