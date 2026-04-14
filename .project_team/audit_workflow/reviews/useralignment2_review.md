# UserAlignment Fresh Review of Audit Workflow Specification v3

**Reviewer:** UserAlignment agent (fresh review, no prior context)
**Verdict:** STRONG -- v3 captures all three user corrections well, with a few actionable gaps remaining.

---

## 1. End-user positioning: PASS

The spec clearly states in Section 1: "ships in generated projects as a tool for end users" and "Audience: End users of generated projects who want to refine their agent interactions." Section 9 (File Inventory) includes "Mirror under `template/workflows/audit/`" in Phase 9. Section 11 Resolved Decisions table explicitly records "Ships in template = YES."

**One gap:** The `copier.yml` modification note (Section 9) says "Ensure `workflows/audit/` is included in template output" but doesn't mention the `scripts/audit/` module or `scripts/session_lib.py`. These code modules also need to ship in generated projects for the workflow to function. The file inventory should clarify which `scripts/` files need template counterparts.

---

## 2. LLM-driven suggestions front and center: PASS

This is well handled. Section 1 has a bold callout: "Tier-1 regex scoring detects THAT corrections happened. The auditor agent (LLM) analyzes WHY they happened and generates the actual suggestions." Section 5.5 is titled "Suggestion Generation (LLM-Driven -- the auditor agent)" and opens with "This is NOT a pure-code module." The data flow diagram (Section 2.2) clearly shows the LLM as the critical bridge between findings and suggestions. Section 11 records: "LLM-driven suggestions -- This IS the core feature."

No issues here -- it is unmistakably front and center.

---

## 3. Git/PR/commit references: PASS (clean)

I searched the entire spec for all git-related terms (PR, pull request, commit, git, merge, branch). The spec contains ZERO references to PRs, commits, branches, merges, or git operations as part of the audit workflow itself. Section 11 explicitly records: "No git workflow coupling -- User checkpoints = user saying 'advance to next phase.' No PRs, commits, or git operations in the workflow itself."

The advance checks are all `file-exists-check` + one `manual-confirm` at the end. Clean.

---

## 4. End-user UX flow: MOSTLY CLEAR, one gap

The invocation table (`/audit`, `/audit <name>`, `/audit --scan <path>`) is clear and practical. Default mode ("audit what just happened") is the right choice.

**Gap: What happens AFTER the report?** The workflow ends at the `report` phase with `manual-confirm: "Audit report reviewed and complete?"` But there is no guidance on what the user does next. The report produces copy-paste-ready suggestions, but the spec does not describe the UX for *applying* them. Does the user manually copy-paste? Does the auditor offer to apply them in a follow-up? A brief "post-audit UX" note would help -- even if it is just "user manually applies suggestions from the report."

---

## 5. suggest.md phase markdown content: NEEDS ELABORATION

Section 5.5 describes what `suggest.md` should guide the LLM to do, but it is listed as bullet points in the spec rather than actual content guidance. The spec says suggest.md should instruct the auditor to:
- Group findings by phase and artifact type
- Read current phase markdown and identify what is missing
- Draft specific text additions/modifications
- Apply minimum evidence thresholds
- Validate YAML output

**What is missing from suggest.md guidance:**

1. **Tone/voice instructions** -- The auditor's suggestions will become phase markdown that other LLMs read. suggest.md should instruct the auditor to write in the imperative voice matching existing phase markdown conventions (e.g., "Always read error output before retrying" not "The agent should consider reading error output").

2. **Concrete examples** -- suggest.md should include at least one worked example showing: "Given this finding, here is what the suggestion looks like." Without an example, the LLM has no calibration for output quality.

3. **Anti-patterns** -- What the auditor should NOT suggest (e.g., do not suggest rules that block their own prerequisites -- the catch-22 pattern called out in CLAUDE.md; do not suggest overly broad rules that would fire on legitimate operations).

4. **How to read workflow artifacts** -- suggest.md should tell the auditor exactly how to access the files (Read tool on the paths from ArtifactRef) rather than assuming it knows.

5. **Output schema enforcement** -- suggest.md should include the exact JSON structure expected for `suggestions.json` so the LLM produces valid output without hallucinating fields.

---

## 6. Output format / copy-paste readiness: PASS with minor note

The report format (Section 5.6) is well-structured with clear "Current text" / "Suggested text" blocks and "YAML (copy-paste ready)" sections. Each suggestion includes file path, rationale, evidence count, and priority.

**Minor concern:** For phase markdown suggestions, the "current text" / "suggested text" diff format works well. But for YAML suggestions (rules, hints, checks), the user needs to know WHERE in the YAML file to paste them. The report format shows the YAML snippet but not the insertion point. Consider adding an "Insert after:" or "Add to section:" hint for YAML suggestions.

**The LLM approach does not fundamentally change the output structure** -- it improves suggestion QUALITY (more contextual, better rationale) while keeping the same copy-paste format. This is correct.

---

## 7. Gaps between user ask and spec delivery

### Gap A (HIGH): Output paths use `.project_team/audit_workflow/`

The manifest advance checks reference paths like `.project_team/audit_workflow/parsed_timeline.json`. But `.project_team/` is a dev convention for THIS template repo. Generated projects will not have `.project_team/`. The audit workflow needs a different output location for end users -- perhaps `.audit/` or `audit_reports/` or a configurable output directory.

### Gap B (MEDIUM): scripts/ dependency in generated projects

The spec puts all code in `scripts/audit/` and `scripts/session_lib.py`. These need to ship in the template. But `session_lib.py` is extracted from `mine_patterns.py` which is a dev tool for THIS repo. Will `mine_patterns.py` also ship? If not, `session_lib.py` shipping alone is fine but needs its own template entry. The file inventory (Section 9) only lists `copier.yml` as an existing file to modify -- it should explicitly list which `scripts/*` files need `template/scripts/` counterparts.

### Gap C (LOW): No "first run" experience

For a brand-new generated project with zero session history, `/audit` would find nothing to audit. The spec handles "empty sessions / no corrections" (Risk table: "Report 'no findings' gracefully") but does not describe the UX for "no sessions exist at all." A friendly message like "No sessions found. Run some workflows first, then come back to audit." would help.

### Gap D (LOW): The `--scan <path>` mode loses context

The spec notes directory scan mode has "No agent_name or workflow context available -- all fields None" which means suggestions will all be unscoped/global. This significantly reduces suggestion quality. Worth noting this limitation explicitly in the UX or suggesting users prefer the chicsession modes.

---

## Summary: Recommended Changes (Priority Order)

| # | Issue | Severity | Action |
|---|-------|----------|--------|
| 1 | Output paths use `.project_team/` (dev convention, not end-user) | **HIGH** | Change to end-user-appropriate path (e.g., `.audit/`) |
| 2 | suggest.md needs concrete LLM guidance (examples, tone, anti-patterns) | **HIGH** | Expand Section 5.5 or add subsection with suggest.md content outline |
| 3 | scripts/ template shipping not fully specified | **MEDIUM** | Add explicit template file list to Section 9 |
| 4 | No post-report UX guidance | **LOW** | Add brief note on what user does after report |
| 5 | No "first run" / empty state UX | **LOW** | Add to Section 7 risks or Section 1 UX |
| 6 | YAML insertion point hints missing in report | **LOW** | Minor report format enhancement |

**Items 1 and 2 are blockers before implementation. The rest can be addressed during implementation.**
