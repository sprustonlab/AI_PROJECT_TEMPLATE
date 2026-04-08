# Fresh Terminology Review — Full Specification Audit

> **Reviewer:** TerminologyGuardian
> **Date:** 2026-04-03
> **Scope:** All 9 files in `specification/`
> **Canonical reference:** `terminology.md`

---

## 1. Banned Synonyms That Snuck Back In

### "walkthrough" (BANNED — use "tutorial")

| File | Line(s) | Exact Text |
|------|---------|------------|
| `terminology.md` | 11 | "A self-contained, interactive guided **walkthrough**" |
| `composability.md` | 5 | "a structured, step-by-step **walkthrough** with verification checkpoints" |
| `user_alignment.md` | 31 | "Interactive **walkthrough** (not static docs)" |

**Severity: HIGH in terminology.md** — the canonical definition of "tutorial" uses a banned synonym to define itself. Other files take their cue from here.

**Fix:** In terminology.md, rewrite the Tutorial definition to avoid "walkthrough." Suggested: *"A self-contained, interactive experience that teaches a user how to complete a specific real-world task."* Other files should follow suit.

---

### "guided" / "guide" (BANNED — use "tutorial mode" for the mode, "tutorial" for the experience)

| File | Line(s) | Exact Text |
|------|---------|------------|
| `terminology.md` | 11 | "interactive **guided** walkthrough" |
| `composability.md` | 5 | "interactive teaching mode that **guides** users" |
| `research_prior_art.md` | 7 | "interactive tutorial/learning systems" (fine — "tutorial" is used) |

**Severity: LOW** — "guided" as an adjective is borderline. The ban targets "guide" / "guided mode" as a noun/mode name, not as a general English adjective. However, in the Tutorial definition it stacks with "walkthrough" to create: "interactive guided walkthrough" — three near-synonyms for "tutorial" used to define "tutorial."

**Fix:** Rewrite the Tutorial definition (see above). Occasional use of "guides" as a verb (e.g., "guides users through steps") is acceptable English — the ban targets noun/mode usage.

---

### "lesson" (BANNED — use "tutorial")

| File | Line(s) | Exact Text |
|------|---------|------------|
| `terminology.md` | 58 | "they are part of the *lesson content*" (in agent-team tutorial definition) |
| `skeptic_review.md` | 39 | "spawning agents IS the **lesson**" |

**Severity: MEDIUM** — These use "lesson" to mean "what is being taught" (the learning objective), not as a synonym for "tutorial" (the guided experience). The distinction is subtle but real. However, "lesson content" in the canonical terminology file risks normalizing the word.

**Fix:** In terminology.md, replace "lesson content" with "teaching content" or "learning objective." In skeptic_review.md, replace "IS the lesson" with "IS the learning objective" or "IS what the tutorial teaches."

---

### "nudge" (BANNED — use "hint")

| File | Line(s) | Exact Text |
|------|---------|------------|
| `terminology.md` | 19, 25, 62, 100, 109 | "contextual **nudges**", "reactive **nudges**", "contextual **nudge**" |

**Severity: MEDIUM** — "nudge" appears 5 times in the canonical terminology file itself, always as a gloss for "hint." The ban table says `nudge → hint`, yet the definitions use "nudge" repeatedly to explain what a hint is.

**Fix:** The ban table bans "nudge" as a standalone term. Using it *inside* a definition to explain what a hint does is arguably acceptable as explanatory prose. However, using it 5 times normalizes the synonym. Recommendation: reduce to at most one occurrence (in the Hint definition) and use "contextual guidance" or "contextual help" elsewhere.

---

## 2. Term Drift — Same Concept, Different Names Across Files

### Step file reference key: `file:` vs `content:`

| File | Key Used | Example |
|------|----------|---------|
| `axis_content.md` | `file:` | `file: step-01-generate-key.md` |
| `axis_guidance.md` | `content:` | `content: step-01.md` |
| `axis_verification.md` | `content:` | `content: step-01.md` |

**Severity: HIGH** — Two different YAML key names for the same field in the tutorial manifest. Content authors will encounter both in the spec and not know which is correct. The canonical schema in `axis_content.md` (Section 2) uses `file:`, which is also more precise (it references a file path, not content).

**Fix:** Standardize on `file:` everywhere. Update `axis_guidance.md` and `axis_verification.md` YAML examples.

---

### Verification type naming: hyphens vs underscores

| File | Convention | Examples |
|------|-----------|----------|
| `axis_content.md` | **Hyphens** | `command-output-check`, `file-exists-check`, `manual-confirm`, `compound` |
| `axis_verification.md` | **Underscores** | `command_output_check`, `file_exists_check`, `manual_confirm`, `compound_check` |
| `composability.md` | **Hyphens** (prose) | `command-output-check`, `file-exists-check` |

**Severity: HIGH** — Content authors write YAML; the verification registry uses Python identifiers. The spec doesn't define which convention the YAML uses or how mapping works. Also note: `axis_content.md` uses `compound` but `axis_verification.md` uses `compound_check` — even the base name differs.

**Fix:** Pick one convention for YAML (recommend hyphens, as that's standard YAML style and what content authors see). Define the mapping explicitly in `axis_verification.md`: "YAML type names use hyphens; the engine normalizes to underscores for registry lookup." Reconcile `compound` vs `compound_check`.

**Already flagged by:** Skeptic spec review (N3), but not yet resolved.

---

### Hint trigger shorthands: inconsistent across specs

| File | Trigger Names | Format |
|------|--------------|--------|
| `axis_content.md` | `manual`, `timed`, `on-failure` | Strings in YAML |
| `axis_guidance.md` | `step-active`, `step-stuck`, `verification-failed` | Strings or dicts |

**Severity: MEDIUM** — These are different trigger vocabularies for the same hint-trigger concept. `axis_content.md` defines `timed` (delay-based); `axis_guidance.md` defines `step-stuck` (also delay-based, but tutorial-aware). Are these the same thing? Different things? Does `timed` from content get translated to `TutorialStepStuck`? The mapping is unclear.

**Fix:** Reconcile the two trigger vocabularies. Either: (a) content uses the guidance triggers (`step-active`, `step-stuck`, `verification-failed`) and the content spec is updated, or (b) content uses simplified shorthands (`manual`, `timed`, `on-failure`) and guidance defines the mapping from each content shorthand to the implementation trigger. Currently both specs define triggers independently.

---

### `failure_message` location: verification params vs VerificationResult

| File | Where failure_message lives |
|------|-----------------------------|
| `axis_content.md` | Inside `verification.params` (e.g., `failure_message: "SSH key not found"`) |
| `axis_verification.md` | Generated by the verification implementation, stored in `VerificationResult.message` |

**Severity: LOW** — Content authors write `failure_message` in YAML params. The verification implementation generates its own message. Who wins? If both exist, do they get merged? The content author's message is presumably more user-friendly. The implementation's message includes evidence.

**Fix:** Clarify the contract: content author's `failure_message` is the user-facing explanation; `VerificationResult.message` is the technical description. The engine should prefer the content author's message when presenting to the user, falling back to the implementation message.

---

## 3. New Terms Introduced in Specs but NOT in terminology.md

### Critical (should be added to terminology.md)

| Term | Introduced In | Meaning | Why It Matters |
|------|--------------|---------|----------------|
| **Verification** (as axis/protocol) | `composability.md`, `axis_verification.md` | The protocol and axis for confirming step completion | Central concept; currently only "checkpoint" is defined in terminology.md, but the Verification protocol is the broader mechanism |
| **VerificationResult** | `axis_verification.md` | The seam-crossing data object returned by all verifications | Used in every axis spec; key integration point |
| **TutorialContext** | `axis_guidance.md` | Read-only snapshot of tutorial progress injected into ProjectState | The seam between tutorial engine and hints pipeline |
| **Tutorial-runner agent role file** | `axis_guidance.md` | The agent role definition at `tutorials/_agent/tutorial-runner.md` | Concrete artifact that implements the tutorial-runner agent concept |
| **TutorialProgressStore** | `axis_guidance.md` | Persistence for tutorial progression state (current step, completed steps, evidence) | Distinct from hint state; new persistence concept |

### Recommended (useful but not blocking)

| Term | Introduced In | Meaning |
|------|--------------|---------|
| **Step Protocol** | `composability.md` | The compositional law (TutorialStep dataclass) enabling axis independence |
| **VerificationContext** | `axis_verification.md` | Sandboxed environment providing read-only system access to verifiers |
| **evidence** | `axis_verification.md` | Raw output/value captured by verification as proof of check result |
| **auto-discovery** | `axis_content.md` | Engine's mechanism for finding tutorials by scanning `content/*/tutorial.yaml` |
| **`run` fence tag** | `axis_content.md` | Markdown code block marker indicating a command the user should execute |
| **checkpoint reference** | `axis_content.md` | HTML comment `<!-- checkpoint: step-id -->` marking verification location in prose |
| **agent_blocked_commands** | `axis_guidance.md` | Per-step list of commands the tutorial-runner agent is forbidden from executing |
| **exempt_guardrails** | `skeptic_spec_review.md` | Proposed per-step field for temporarily disabling existing guardrail rules |
| **variables** (manifest section) | `skeptic_spec_review.md` | Proposed `tutorial.yaml` section declaring required environment variables |

---

## 4. Overloaded Terms

### "content"

| Usage | File | Meaning |
|-------|------|---------|
| "Tutorial Content" | `terminology.md` | The markdown instruction files |
| `content:` YAML key | `axis_guidance.md` | Reference to a step's markdown file path |
| "Content axis" | `composability.md` | The composability axis for "what is being taught" |
| "teaching content" | `terminology.md` | What the tutorial is about (learning objective) |
| "content author" | `axis_content.md` | Person writing tutorial markdown |

**Severity: MEDIUM** — "Content" means: (1) the markdown files, (2) the YAML key referencing them, (3) the composability axis, (4) the learning objective, and (5) the person writing them. Context usually disambiguates, but the `content:` YAML key vs "Tutorial Content" definition conflict is confusing.

**Fix:** Use `file:` for the YAML key (as axis_content.md does). Reserve "content" for the prose concept and axis name.

---

### "step" alone (without "tutorial")

Many files use bare "step" instead of the canonical "tutorial step":
- `composability.md`: "Steps proceed in order" (line 65)
- `axis_content.md`: "step markdown files" throughout
- `axis_guidance.md`: "step content", "step-active", "step-stuck"
- `axis_verification.md`: "step" used dozens of times alone

**Severity: LOW** — Within tutorial-system specs, bare "step" is unambiguous because the entire context is tutorials. The ban was against using "step" in contexts where it could collide with other "step" concepts. Within the tutorial specification, this is acceptable shorthand.

**Fix:** No action needed within tutorial specs. The full "tutorial step" should be used in cross-system documents (e.g., project-level docs that reference multiple subsystems).

---

## 5. Canonical Home Violations

### VerificationResult defined in two places

- `composability.md` (line 70-74): Defines `VerificationResult` dataclass with `passed`, `message`, `evidence`
- `axis_verification.md` (line 136-183): Defines `VerificationResult` with additional fields (`check_description`, `sub_results`)

**Severity: MEDIUM** — The composability doc has a simpler version. The axis spec has the full version. These are not contradictory (the axis version is a superset), but the composability doc's version is stale/incomplete.

**Fix:** Composability doc should say "See `axis_verification.md` for the full `VerificationResult` definition" rather than inlining a partial copy.

---

### TutorialStep defined in two places

- `composability.md` (line 58-65): Defines `TutorialStep` dataclass
- `axis_content.md`: Implicitly redefines it through the YAML schema

**Severity: LOW** — The composability doc defines the Python dataclass; the content spec defines the YAML representation. These are two views of the same concept. As long as they stay in sync, this is acceptable. But if they drift, it's a problem.

**Fix:** Composability doc should note: "The `TutorialStep` dataclass is populated from the YAML schema defined in `axis_content.md`."

---

## 6. Newcomer Blockers

### Acronyms and jargon used without definition

| Term | File | Issue |
|------|------|-------|
| "seam" | All specs | Used ~40 times across specs. Never defined. Means "interface boundary between axes" but a newcomer wouldn't know this. |
| "axis" | All specs | The composability decomposition concept. Defined implicitly in composability.md but never given a one-line definition. |
| "crystal test" | `composability.md` | Composability-specific jargon. Explained by example but never defined. |
| "frozen dataclass" | Multiple | Python-specific. Scientists unfamiliar with Python dataclasses won't know what this means. |

**Severity: LOW for specification docs** — these are internal team specs, not user-facing. But if any of this language leaks into user-facing tutorial content or authoring guides, it's a problem.

**Fix:** Add a brief "Specification Vocabulary" section to composability.md defining: axis, seam, crystal test, frozen dataclass. These are the spec's own terms, distinct from the tutorial system's domain terms.

---

## Summary: Issues by Priority

### Must Fix (before architecture phase)

| # | Issue | Type | Fix |
|---|-------|------|-----|
| 1 | `file:` vs `content:` YAML key drift | Term drift | Standardize on `file:` across all specs |
| 2 | Verification type naming (hyphens vs underscores) | Term drift | Pick YAML convention, define mapping |
| 3 | `terminology.md` uses "walkthrough" in Tutorial definition | Banned synonym | Rewrite definition |
| 4 | Hint trigger vocabulary inconsistency across specs | Term drift | Reconcile content vs guidance triggers |
| 5 | Missing terms in terminology.md (Verification, VerificationResult, TutorialContext, TutorialProgressStore) | Orphan terms | Add to terminology.md |

### Should Fix (during architecture phase)

| # | Issue | Type | Fix |
|---|-------|------|-----|
| 6 | "nudge" used 5x in terminology.md | Banned synonym | Reduce to 1 occurrence |
| 7 | "lesson content" in terminology.md | Banned synonym | Replace with "teaching content" |
| 8 | VerificationResult defined in 2 places | Canonical home | Composability doc should reference axis spec |
| 9 | `compound` vs `compound_check` type name | Term drift | Reconcile |
| 10 | `failure_message` ownership unclear | Ambiguity | Clarify content-author vs implementation message |

### Nice to Have

| # | Issue | Type | Fix |
|---|-------|------|-----|
| 11 | "seam", "axis", "crystal test" undefined for newcomers | Newcomer blocker | Add spec vocabulary section |
| 12 | Recommended terms not yet in terminology.md | Completeness | Add during architecture |
| 13 | "guided" in Tutorial definition | Banned synonym (borderline) | Remove in definition rewrite |
