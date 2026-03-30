# Terminology Review: SPECIFICATION.md

> **Reviewer:** TerminologyGuardian
> **Document:** `specification/SPECIFICATION.md`
> **Reference:** `specification/terminology.md`
> **Date:** 2026-03-29

---

## Verdict: GOOD — 3 issues to fix, 4 minor observations, 2 new terms to add

The specification is remarkably consistent with terminology.md. The author clearly used the terminology file as a guide. The issues below are minor — no structural terminology drift.

---

## 1. Terms Used Consistently? ✅ Mostly Yes

"Plugin" is used correctly throughout as the independently enableable unit. "Manifest" is correctly used for both `project.yaml` (project manifest) and `plugin.yaml` (plugin manifest). "Seam" is used correctly with explicit cross-references to `composability.md`.

---

## 2. "Component" Where "Plugin" Should Be Used? ✅ Clean

No instances of "component" found in the spec. This is correct — the spec consistently uses "plugin."

---

## 3. "Hook" Always Qualified? ⚠️ ONE ISSUE

### Issue 3a: Bare "hook" on line 299

> `description: "Role-based permission system with code-generated hooks"`

**Problem:** Which hooks? These are **guardrail hooks** (generated shell scripts that intercept tool calls). The bare "hooks" could be confused with lifecycle hooks.

**Fix:** Change to: `"Role-based permission system with code-generated guardrail hooks"`

### Issue 3b: "hooks" in §1.2 (line 17)

> `Five plugins do not justify lifecycle hooks, event buses, or plugin loader classes.`

**Assessment:** ✅ Actually fine. This is correctly qualified as "lifecycle hooks" — it's explicitly distinguishing the *kind* of hook that was ruled out.

### Issue 3c: "hooks" in §11.1 (line 979)

> `guardrails is inert without claudechic because role_guard.py requires CLAUDECHIC_APP_PID to detect team mode`

**Assessment:** ✅ No bare "hook" here, but the nearby text on line 987 says:

> `All role checks return 0 (pass). Guardrails with regex-only rules (no role gates) still work.`

Clean usage — no hook ambiguity.

### Issue 3d: "hooks" in copier.yml help text (line 645)

> `Rules defined in rules.yaml, hooks auto-generated.`

**Problem:** Bare "hooks." A newcomer during onboarding (the exact moment they see this text) won't know what kind of hooks.

**Fix:** Change to: `"Rules defined in rules.yaml, guardrail hooks auto-generated."`

---

## 4. "Module" Always Qualified? ⚠️ ONE ISSUE

### Issue 4a: "module" in §9.2.1 (line 799)

> `Extract the JSONL parsing layer into a separate, clearly bounded module within the script`

**Assessment:** ✅ Acceptable. This is clearly a Python module in context ("within the script"). No risk of git submodule confusion.

### Issue 4b: "submodule" in file tree and activate scripts

> Line 285: `submodules/claudechic           # Git submodule reference`
> Line 542: `CLAUDECHIC_DIR="$PROJECT_ROOT/submodules/claudechic"`

**Assessment:** ✅ Clean. Always "submodule" (with context) or the path `submodules/`, never bare "module" for this meaning.

---

## 5. New Terms That Should Be Added to terminology.md? ⚠️ TWO ADDITIONS NEEDED

### New Term 5a: "Category"

Used in §1.3 (line 26) and throughout plugin manifests:

> `category: "infrastructure"          # infrastructure | runtime | post-hoc`

Three categories: **infrastructure**, **runtime**, **post-hoc**. This is a new classification axis for plugins. It determines activation order and integration pattern.

**Recommendation:** Add to terminology.md:

```markdown
### Category

A **classification of plugins by their integration pattern and activation timing.**
Three categories exist:
- **Infrastructure** — bootstrap/foundation plugins that run first (e.g., `python-env`)
- **Runtime** — plugins active during Claude Code sessions (e.g., `claudechic`, `guardrails`, `project-team`)
- **Post-hoc** — standalone tools that run after sessions (e.g., `pattern-miner`)

Category determines activation order: infrastructure → runtime → post-hoc.
```

### New Term 5b: "Dispatcher"

Used in §5.2 (line 369):

> `The new activate is a thin dispatcher that reads project.yaml and sources per-plugin activate fragments.`

Also "thin dispatcher" on line 107. This is a specific architectural pattern worth defining.

**Recommendation:** Add to terminology.md:

```markdown
### Dispatcher

The **thin shell script (`activate`) that reads `project.yaml` and sources per-plugin activate scripts** in dependency order. The dispatcher contains no plugin-specific logic — it only iterates the plugin list and delegates.

> "Thin dispatcher" emphasizes that the dispatcher has no business logic of its own.
```

---

## 6. "Feature" vs "Plugin" Distinction Maintained? ⚠️ ONE SOFT ISSUE

### Issue 6a: Copier help text uses "feature" language without the term

The copier questionnaire (lines 630–668) describes each plugin's **features** in the `help:` text:

> `Provides: Conda/Miniforge bootstrap, install_env.py, lock_env.py, reproducible lockfiles, and the require_env command.`

**Assessment:** ✅ Actually good practice. The help text describes what the user gets (features) without calling them "features" — avoiding the term is fine here since it's user-facing onboarding text describing capabilities, not architecture.

### Issue 6b: §14 (line 1119) — "No plugin base class or Python interface"

> `Plugins are directories with shell scripts and a YAML manifest.`

**Assessment:** ✅ Correct usage — "plugin" as the installable unit.

### Issue 6c: userprompt.md heading bleed

The spec's §1 header (line 5) correctly references terminology.md:

> `Terminology: All terms follow specification/terminology.md.`

✅ Good practice. This anchors the reader immediately.

---

## 7. Bare "System" Without Qualification? ⚠️ ONE ISSUE

### Issue 7a: §11.1 line 977

> `guardrails is inert without claudechic because role_guard.py requires CLAUDECHIC_APP_PID to detect team mode`

**Assessment:** ✅ No bare "system" here.

### Issue 7b: §6.1 title "Problem"

No bare "system" found anywhere in the spec. The spec avoids "system" almost entirely — "plugin system" is used once in §1.2 context and is properly qualified.

✅ Clean.

---

## Summary of Required Changes

### Must Fix (3 items)

| # | Location | Current Text | Fix |
|---|----------|-------------|-----|
| 1 | §4.2, guardrails `plugin.yaml`, line 299 | `"code-generated hooks"` | → `"code-generated guardrail hooks"` |
| 2 | §7.2, copier `use_guardrails` help, line 645 | `"hooks auto-generated"` | → `"guardrail hooks auto-generated"` |
| 3 | terminology.md | Missing "Category" and "Dispatcher" | Add definitions (see §5 above) |

### Nice to Have (0 items)

No other issues found.

---

## Newcomer Simulation

I read the spec as a newcomer who has never seen this project. Findings:

1. **Line 5 anchors terminology immediately** — excellent. A newcomer knows where to look.
2. **§1.3 Plugin Categories table** — clear, self-explanatory. No jargon without anchor.
3. **§10.2 Dependency Graph** — ASCII art is clear and readable.
4. **§14 "What This Specification Does NOT Include"** — extremely helpful for newcomers. Prevents them from looking for things that aren't there.
5. **§8.3 Failure Scenarios table** — good for a newcomer to understand edge cases without having to discover them.

**One implicit assumption:** §5.3 references `specification/composability.md §Seam 5` (line 365) — a newcomer would need that file to exist. Verify it does.

---

## Overall Assessment

The specification is **terminologically clean**. The three issues are minor qualification fixes, not structural drift. The author used terminology.md as intended. The two new terms (Category, Dispatcher) are natural extensions that emerged from the design work — they should be added to terminology.md to keep it current.

**Grade: A-** (A after the three fixes are applied)

---

*Reviewed: 2026-03-29 by TerminologyGuardian*
