# Terminology: Phase Registry — Quick Analysis

> **Reviewer:** TerminologyGuardian
> **Date:** 2026-04-04

---

## The Need

A mechanism that declares valid phase IDs so that `phase_scope` fields on guardrail rules can be validated at generation time. When `rules.yaml` says `phase_scope: ["project:4"]`, the system needs to know: is "project:4" a real phase?

---

## "Registry" Conflict Check

**"Registry" already has 3 distinct meanings in the specs:**

| Existing Usage | Meaning | Files |
|---|---|---|
| **Check registry** (née Verification registry) | YAML `type` string → Python Check class mapping. `{"command-output-check": CommandOutputCheck}` | axis_verification.md (line 653), fresh_composability_review.md, SPECIFICATION.md |
| **Tutorial registry** | Index of available tutorials for user selection. Name, description, difficulty, prerequisites. | terminology.md (line 71), terminology_infrastructure_update.md |
| **Mode registry** | Proposed global concept of available modes (normal/tutorial/team) | existing_infrastructure_audit.md (line 256, 287) |

Adding a 4th meaning ("phase registry" = valid phase ID declarations) would make "registry" mean:
1. type→class lookup table (check registry)
2. user-facing feature catalog (tutorial registry)
3. available system modes (mode registry)
4. valid phase ID declarations (phase registry)

**That's too many.** "Registry" would become meaningless — it just means "a collection of things."

---

## Recommendation: Use "phase declarations"

| Candidate | Verdict | Reason |
|---|---|---|
| **phase registry** | ❌ | "Registry" already means 3 different things. 4th meaning is noise. |
| **phase catalog** | ❌ | "Catalog" implies browsing/selection (like `rules.yaml` is called a "rule catalog"). Phase declarations aren't browsed — they're referenced for validation. |
| **phase manifest** | ❌ | "Manifest" already means "the YAML config file for a workflow" (from terminology.md). A phase manifest would sound like the workflow's manifest file, not a validation reference. |
| **known_phases** | ⚠️ | Good for a Python variable name. Not a concept name. |
| **phase declarations** | ✅ | Accurate — phases are *declared* (stated to exist with their IDs) so rules can reference them. Follows natural language: "these are the declared phases." No collision with existing terms. |

---

## Definition

### Phase Declarations

The authoritative list of valid phase IDs within a workflow, used to validate `phase_scope` references on guardrail rules at generation time. Phase declarations are derived from workflow manifests — each manifest's `phases[].id` entries constitute the declarations for that workflow.

**Purpose:** When `generate_hooks.py` encounters a rule with `phase_scope: ["project:4"]`, it checks the phase declarations to confirm `project:4` exists. Invalid references produce a clear error at generation time, not a silent miss at runtime.

**Source:** Phase declarations are not a separate file — they are extracted from the workflow manifests that already exist:
- Project-team phases: derived from COORDINATOR.md's Phase 0–9 (or a machine-readable equivalent)
- Tutorial phases: derived from each `tutorial.yaml`'s `phases[].id` entries
- The namespace convention `{workflow_id}:{phase_id}` (e.g., `project:4`, `tutorial:ssh-cluster:generate-key`) makes declarations globally unique

> **Relationship to check registry:** The check registry maps YAML type names to Python classes (a type→implementation lookup). Phase declarations map phase IDs to validity (an existence check). Different purpose, different mechanism — no shared terminology needed.

---

## Synonym Control

| DO NOT USE | USE INSTEAD | Reason |
|---|---|---|
| phase registry | **phase declarations** | "Registry" is overloaded (3+ meanings already) |
| phase catalog | **phase declarations** | "Catalog" implies browsing; declarations are for validation |
| phase manifest (for the declarations concept) | **phase declarations** | "Manifest" already means the workflow config file |
| valid phases / allowed phases | **phase declarations** | "Declarations" is the canonical noun |
