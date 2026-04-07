# User Alignment — Specification Review

> **Reviewer:** UserAlignment Agent
> **Document reviewed:** `specification/SPECIFICATION.md` (Draft v1)
> **Date:** 2026-03-29
> **Source of truth:** `userprompt.md`

---

## Overall Verdict: ✅ ALIGNED — Strong spec with two items needing attention

The specification is faithful to the user's request. All core requirements are addressed. The design choices are well-justified. Below is a point-by-point evaluation.

---

## 1. Composability + Ease of Use

**User said:** "I want to make this repo more composable and easier to start a project with"

### ✅ Composability: STRONG

- Plugin system with per-plugin directories, YAML manifests, and conditional inclusion — directly delivers composability.
- The valid configurations table (§10.3) shows 9+ valid plugin combinations including "empty" — users genuinely pick and choose.
- Dependency resolution prevents invalid combos at onboarding time.

### ✅ Ease of Use: STRONG

- Three-command fresh start: `copier copy <url> my-project && cd my-project && source activate` — hard to beat.
- Copier questionnaire has helpful multi-line descriptions for each plugin.
- `copier update` for staying current is a major ease-of-use win over cookiecutter.
- The activate script prints clear status with checkmarks per plugin.

**No issues found.**

---

## 2. Onboarding Experience Quality

**User said:** "I want to have users have an onboarding experience maybe web based / claude conversation based"

### ✅ Implementation: ALIGNED (both options addressed)

The spec provides three tiers (§7.1):
1. **CLI via Copier** — MVP, implement first
2. **Claude skill `/init-project`** — conversational wrapper, low marginal cost
3. **Web** — deferred

This matches the user's "maybe web based / claude conversation based" — both are planned, web is deferred with justification.

### ⚠️ MINOR FLAG: Is the Copier CLI a real "experience"?

The Copier questionnaire (§7.2) asks yes/no questions with helpful descriptions. This is better than a terse CLI, but the user said "onboarding **experience**" — a word that implies more than a questionnaire.

**What's good:**
- Multi-line `help:` text explains each plugin
- Conditional questions (project-team only shown if claudechic enabled) prevent confusion
- `/init-project` Claude skill adds conversational warmth

**What could drift:**
- The Copier CLI alone might feel mechanical. The `/init-project` skill (§7.4) is described as a "thin wrapper" — it should be more than that. It should explain trade-offs, make recommendations, and feel like talking to a knowledgeable guide.

**Recommendation:** The spec should note that the `/init-project` skill is the **primary recommended onboarding path** for new users, with raw Copier CLI as a power-user alternative. The skill description (§7.4) should specify that it explains WHY you'd want each plugin, not just WHAT it does. Currently §7.4 says it "asks the user what they need conversationally" — good intent, but the implementer may interpret "thin wrapper" as minimal effort.

**Risk:** Low. The architecture supports a great experience; it just needs the implementer to invest in the skill's conversational quality.

---

## 3. Existing Codebase Integration

**User said:** "We should be able to let them add an existing code base as well"

### ✅ STRONG — First-class treatment

This is one of the spec's best sections. §8 dedicates a full section with:
- Two explicit modes: Fresh vs Integrate (§8.1)
- Detailed integration flow with 6 steps (§8.2)
- Four failure scenarios with mitigations (§8.3)
- `require_env` relaxation for non-standard project roots (§8.4)
- `.claude/` directory merging (not overwriting)

### ✅ "Add" vs "Wrap" concern resolved

In my Phase 2 review, I flagged that the vision said "wrap" while the user said "add." The spec handles this well:
- The Copier question says "Path to an existing codebase to integrate" — neutral term ✅
- The integration flow symlinks/copies into `repos/` — this is "add to the template" ✅
- The PYTHONPATH auto-setup means user code is importable — practical integration ✅

### ✅ Not an afterthought

Existing codebase integration is Phase 4 in the implementation plan — after the plugin foundation but before onboarding polish. This is the right sequence (you can't integrate a codebase if the plugin system doesn't work yet).

**No issues found.**

---

## 4. Lightweight Plugin System

**User said:** "plugin type system (lightweight)"

### ✅ LIGHTWEIGHT: STRONG — This is the spec's defining achievement

The spec explicitly structures around this constraint:

**What a plugin IS (§1.2):**
- A directory with shell scripts and a YAML manifest
- No base class, no Python interface, no framework

**What the system IS (§1.2):**
- "Manifest + convention, NOT a framework"
- YAML manifest declares enabled plugins
- Decomposed activate reads the manifest
- Convention-based directories

**What was explicitly excluded (§14):**
- No plugin base class
- No dynamic discovery
- No event bus
- No version compatibility matrix
- No distributable package format

**The "lightweight" test — would the user agree?**

To create a new plugin, you:
1. Create a directory under `plugins/`
2. Write a `plugin.yaml` (15-20 lines of YAML)
3. Add an `activate.sh` (optional, only if the plugin needs env vars)
4. Add a `setup.sh` and `check.sh`
5. Put your files in `files/`
6. Add one line to the activate dispatcher's `_PLUGIN_ORDER` array

This is lightweight. A developer familiar with bash could create a plugin in under 30 minutes. The user would look at this and say "yes, that's what I meant."

### ℹ️ NOTE: Fixed plugin order (§14)

The spec says "The activate script has a fixed plugin order list. New plugins require adding one line to the list." This is a deliberate simplicity trade-off. For 5-10 plugins, this is fine. The spec correctly notes the escape hatch: "revisited if the plugin count exceeds ~10."

**No issues found.**

---

## 5. Landscape Survey Reflected

**User said:** "we are not the first to try this. Research what exists, learn from prior art, and recommend additional plugins worth building or integrating."

### ✅ Survey influenced the spec

The landscape survey (`specification/landscape_survey.md`) recommended Copier over Cookiecutter — and the spec adopted Copier. This is direct evidence the survey shaped decisions.

### ✅ "TBD from research" slot preserved

The vision's "TBD from research" plugin category is reflected in the spec's extensibility: §14 notes the architecture can accommodate future plugins, and the fixed plugin order can be extended.

### ⚠️ MINOR GAP: Plugin recommendations not surfaced in the spec

The user explicitly said "recommend additional plugins worth building or integrating." The landscape survey exists separately, but the SPECIFICATION.md itself does not include a section like "Recommended Future Plugins" based on the survey findings. An implementer reading only the spec might not know about the researcher's plugin recommendations.

**Recommendation:** Add a brief §15 "Future Plugin Candidates (from Landscape Survey)" that references the survey's key recommendations — e.g., git-workflow plugin, testing-framework plugin, documentation-generator plugin, or whatever the Researcher identified. This keeps the spec self-contained and ensures the user's "recommend plugins" ask is visible to implementers.

**Risk:** Low. The information exists in the survey document. This is a discoverability issue, not a content gap.

---

## 6. "Lightweight" as Binding Constraint

**User emphasis:** "lightweight" was explicit

### ✅ Maintained throughout

The word "lightweight" or its spirit appears at every decision point:
- §1.2: "Manifest + convention, NOT a framework"
- §5.3: YAML parsing via grep/awk, "no yaml parser needed"
- §7.4: Claude skill is a "thin wrapper"
- §14: Entire section dedicated to what was excluded to stay lightweight
- Skeptic review influenced the spec to reject heavyweight patterns

The constraint has not drifted. Every section that could have ballooned (dependency resolution, plugin interface, onboarding) was kept minimal.

**No issues found.**

---

## 7. Missing or Deprioritized Features

### Checking all user requirements:

| User Requirement | Spec Section | Status |
|-----------------|-------------|--------|
| Composable repo | §1-4 (plugin system) | ✅ Present |
| Easier to start | §7 (onboarding), §13 (impl plan) | ✅ Present |
| Python env management as plugin | §4.2 (python-env manifest) | ✅ Present |
| Claudechic as plugin | §4.2 (claudechic manifest) | ✅ Present |
| Project-team as plugin | §4.2 (project-team manifest) | ✅ Present |
| Guardrails as plugin | §4.2, §11 (standalone mode) | ✅ Present |
| Onboarding experience | §7 (three tiers) | ✅ Present |
| Existing codebase integration | §8 (dedicated section) | ✅ Present |
| Seam analysis | §5.1, §6.1, referenced from composability.md | ✅ Present |
| Lightweight plugin system | §1.2, §14 | ✅ Present |
| Pattern miner port | §9 (detailed port plan) | ✅ Present |
| Landscape survey | Referenced, Copier adopted | ✅ Present |
| Plugin recommendations | Survey exists separately | ⚠️ Not in spec (see §5 above) |

### ✅ No features missing. No features deprioritized.

---

## Summary of Flags

### Items needing attention (neither is a blocker):

| # | Flag | Severity | Section | Action |
|---|------|----------|---------|--------|
| 1 | `/init-project` skill described as "thin wrapper" — should be the primary recommended path with emphasis on conversational quality, not just a CLI proxy | Minor | §7.4 | Clarify in spec that skill should explain WHY (not just WHAT) for each plugin. Note it's the recommended path for new users. |
| 2 | Landscape survey plugin recommendations not surfaced in the spec itself | Minor | Missing §15 | Add a brief "Future Plugin Candidates" section referencing the survey's top picks |

### Items confirmed resolved from Phase 2:

| Previous Flag | Resolution |
|--------------|------------|
| "Add" vs "Wrap" wording | ✅ Spec uses neutral "integrate" — good |
| Existing codebase priority | ✅ First-class treatment with dedicated section and failure scenarios |

---

## Final Assessment

**The specification is ready for implementation.** It is faithful to the user's request across all dimensions — composability, ease of use, existing codebase support, lightweight design, and landscape-informed decisions. The two minor flags above are quality improvements, not alignment corrections. The user would read this spec and recognize their vision.
