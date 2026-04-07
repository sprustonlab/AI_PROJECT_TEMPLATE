# Fresh Composability Review

**Reviewer:** Composability (Lead Architect)
**Scope:** All files in `specification/` — composability.md, axis_verification.md, axis_content.md, axis_guidance.md, skeptic_spec_review.md, terminology.md, user_alignment.md, research_prior_art.md
**Focus:** Cross-axis coherence, seam leakage, crystal integrity, Step Protocol law

---

## 1. Cross-Axis Coherence

### Content ↔ Verification: CLEAN ✅

The seam is well-defined and consistent across both specs:

- **Content** declares verification as `{ type: ..., params: { ... } }` in YAML (axis_content.md §4)
- **Verification** deserializes via `VERIFICATION_REGISTRY` (axis_verification.md §YAML Serialization)
- `VerificationResult` is the only object crossing the boundary

**One naming inconsistency** (also caught by Skeptic N3): Content uses hyphens (`command-output-check`), Verification registry uses underscores (`command_output_check`). This is cosmetic but must be reconciled before implementation. **Recommendation:** YAML uses hyphens (idiomatic YAML), registry normalizes `s/-/_/g` on lookup. One line of code, define it in axis_verification.md.

### Content ↔ Guidance: CLEAN ✅

- Content declares hints as `{ message, trigger, lifecycle }` in YAML (axis_content.md §5)
- Guidance converts to `HintSpec` via `_build_hint_specs()` (axis_guidance.md §2)
- After conversion, pipeline has no idea hints came from a tutorial

**Minor inconsistency in trigger naming:** Content spec (axis_content.md) uses `manual`, `timed`, `on-failure`. Guidance spec (axis_guidance.md) uses `step-active`, `step-stuck`, `verification-failed`. These are different naming schemes for overlapping concepts:

| Content term | Guidance term | Same thing? |
|---|---|---|
| `manual` | `step-active` | No — `manual` means "available on-demand," `step-active` means "fires when on this step." Different semantics. |
| `timed` | `step-stuck` | Similar — `timed` is content-author language for "fire after N seconds," `step-stuck` is the engine's implementation. OK as long as `timed` in YAML maps to `TutorialStepStuck`. |
| `on-failure` | `verification-failed` | Same — `on-failure` is content-author shorthand for `TutorialVerificationFailed`. |

**Issue:** The two specs describe the trigger shorthands independently without a single canonical mapping table. Content author writes `timed`; what trigger class does it become? The guidance spec's `_resolve_trigger()` handles `step-active`, `step-stuck`, `verification-failed` — but content spec says `manual`, `timed`, `on-failure`.

**Recommendation:** Add a single canonical mapping table to axis_content.md (the author-facing spec):

```
YAML shorthand    →    TriggerCondition class
─────────────────────────────────────────────
manual            →    TutorialStepActive (fires immediately when step is active)
timed             →    TutorialStepStuck (fires after delay_seconds)
on-failure        →    TutorialVerificationFailed (fires after failed checkpoint)
```

And update `_resolve_trigger()` in axis_guidance.md to use these exact shorthands.

### Verification ↔ Guidance: CLEAN ✅

This is the seam I was most concerned about. Both specs agree:

- Guidance reads `VerificationResult.message` and `VerificationResult.evidence` (axis_guidance.md §5)
- Guidance never imports verification internals (no access to regex patterns, commands, etc.)
- `AgentContext.last_result` is typed as `VerificationResult | None` — the agent sees the result object, not the verifier

**The dynamic hint message pattern** (axis_guidance.md §5) is clean — it reads `state.tutorial.last_verification.message`, which is a string produced by the verification, not an inspection of verification internals.

### Verification ↔ Safety (Guardrails): COHERENT ✅ with one gap

The three-level integration (axis_verification.md §5) is well-designed:
- Level 1 (soft): system prompt injection — existing pattern
- Level 2 (hard): `CheckpointNotPassedError` — clean progression gate
- Level 3 (audit): evidence persistence — new but clean

**Gap:** The `T01` rule in axis_verification.md uses `detect.type: tutorial_checkpoint`, which is a new detection type not in the existing guardrail system. The existing system uses `regex_match`. This needs either:
- (a) A new detection type added to the guardrail engine, or
- (b) Reframing the checkpoint gate as engine-level logic (not a guardrail rule)

Option (b) is cleaner — the `CheckpointNotPassedError` in `advance_to_next_step()` already IS the enforcement. The `T01` rule in rules.yaml is redundant with the engine-level gate. **Recommendation:** Remove `T01` from rules.yaml. The checkpoint gate is an engine invariant, not a guardrail rule. Guardrails are for agent/user behavior; the checkpoint gate is structural.

---

## 2. Seam Leakage Audit

### `ProjectState.tutorial` field — MINOR LEAK ⚠️

Skeptic flagged this as N4 and I concur. Adding `tutorial: TutorialContext | None` to `ProjectState` means the hints system's core data model imports a tutorial-specific type. This is a seam leak from the tutorial axis into the hints axis.

**Severity:** Low. It's one optional field, and `TutorialContext` is a frozen dataclass with no behavior.

**Fix options (ranked):**
1. **Best:** Define `TutorialContext` in a shared `_types.py` module that both hints and tutorials import. Neither owns the type.
2. **Acceptable:** Keep it on `ProjectState` but define `TutorialContext` in `hints/_types.py` as a generic "external context" (rename to something like `ExternalContext` with tutorial-specific fields). Less clean but avoids a new module.
3. **Worst:** Have tutorial triggers reach into `ProjectState.__dict__` or `**kwargs` dynamically. Avoids the import but sacrifices type safety.

**Recommendation:** Option 1. Create a shared types module. This is consistent with how `HintRecord` already serves as a shared seam object.

### `agent_blocked_commands` in tutorial.yaml — POTENTIAL LEAK ⚠️

axis_guidance.md §4 introduces `agent_blocked_commands` per step in tutorial.yaml:

```yaml
agent_blocked_commands:
  - "ssh-keygen"
  - "ssh-add"
```

This means content authors must manually enumerate which commands the agent shouldn't run — essentially duplicating knowledge of what the verification checks. If the verification command changes, the blocked list must also change.

**This is a Content ↔ Safety seam leak.** Content knows too much about what verification does internally (which commands it checks), and the safety configuration is coupled to verification internals.

**Fix:** Instead of per-step `agent_blocked_commands`, the engine should auto-derive blocked commands from the verification config:
- `CommandOutputCheck(command="ssh-add -l")` → auto-block `ssh-add` for the agent
- `FileExistsCheck(path="~/.ssh/id_ed25519")` → auto-block `ssh-keygen` (creates that file)

The second case is harder (requires knowing which commands produce which files), so a hybrid approach is more practical:
- Auto-derive where possible (extract the base command from `CommandOutputCheck.command`)
- Allow manual `agent_blocked_commands` as an override for cases auto-derivation can't handle
- Document that this field exists to cover edge cases, not as the primary mechanism

**Impact:** Medium. Without this fix, every tutorial author must manually maintain two parallel lists (what to verify + what to block), which will drift.

### `exempt_guardrails` — NOT YET IN SPECS ⚠️

Skeptic identified that tutorials may need to temporarily exempt existing rules (e.g., R02 pip-install-block during a tutorial about why pixi manages dependencies). No spec addresses this.

**Composability concern:** If `exempt_guardrails` is added per-step in tutorial.yaml, it creates a Content → Safety coupling (content knows about guardrail rule IDs). But this coupling is inherent — content authors need to know which rules to exempt because exemption is a content-level decision ("this step intentionally does the thing that's normally blocked").

**Recommendation:** This coupling is acceptable because:
1. The coupling direction is correct: Content → Safety (content declares what it needs), not Safety → Content
2. Rule IDs are stable, named identifiers (R01, R02), not implementation details
3. The alternative (never exempting rules) is worse pedagogically

Add `exempt_guardrails: list[str]` per step. The engine deactivates those rule IDs for the step's duration and reactivates them on step completion/exit. This is a clean, scoped mechanism.

---

## 3. Crystal Integrity

### Original 6-axis crystal: Content × Progression × Verification × Guidance × Safety × Presentation

**Testing with new features added by specs:**

#### New features to test:
- `exempt_guardrails` (Skeptic recommendation)
- `variables` section in tutorial.yaml (Skeptic N2)
- `retries` on verification (Skeptic recommendation)
- `ShowUntilStepComplete` lifecycle (Guidance axis)
- `agent_blocked_commands` (Guidance axis)

#### Crystal points with new features:

| Point | Description | Works? |
|---|---|---|
| ssh-cluster + checkpoint-gated + CommandOutputCheck(retries=3) + timed hints + exempt_guardrails=[] + cli | Standard case with retries | ✅ Retries is a Verification-internal parameter, doesn't affect other axes |
| pixi-tutorial + linear + ManualConfirm + ShowUntilStepComplete + exempt_guardrails=[R02] + agent-conversational | Exempt R02 during pip step | ✅ Exemption is Safety-axis scoped, doesn't affect Verification or Content |
| github-signup + checkpoint-gated + CompoundCheck + hint with variables + tutorial-guardrails + cli | Variables in verification params | ⚠️ See below |
| git-config + branching + ConfigValueCheck + agent-assist + custom-ruleset + cli | Branching with agent-assist | ❌ Branching is unspecified (see §4) |

#### ⚠️ Variables interaction with Verification

The `variables` section (Skeptic N2) affects Content and Verification jointly: content declares variables, verification params reference them (`${CLUSTER_HOST}`). The resolution happens at the engine level before verification runs.

**Question:** Does `variables` introduce a hidden dependency between Content and Verification?

**Analysis:** No. Variables are resolved by the engine into concrete strings before they reach verification. Verification receives `command: "ssh user@login.hpc.edu echo ok"` — it never sees `${CLUSTER_HOST}`. The variable resolution is an engine concern, not a Content ↔ Verification coupling. Clean.

**But:** The `variables` section MUST be validated at tutorial start (before any step runs), not lazily. If `${CLUSTER_HOST}` is undefined when step 2 needs it, the tutorial should fail at start, not at step 2. This is an engine responsibility, not a composability concern, but worth noting.

#### ❌ Branching Progression

Branching is listed as a Progression axis value but is not specified anywhere:
- composability.md lists it as an axis value
- axis_content.md has a commented-out `branching_rules:` section
- Skeptic notes: "Either spec branching fully or explicitly defer it to v2"

**Crystal impact:** Any crystal point with `branching` is a hole. The axis value exists in theory but has no implementation contract.

**Recommendation:** Explicitly defer branching to v2. Remove it from the Progression axis values for v1. The v1 crystal is: Content × {linear, checkpoint-gated} × Verification × Guidance × Safety × Presentation. This is a smaller but complete crystal — no holes.

---

## 4. Step Protocol Law — Still Holding?

The Step Protocol law states: all axes produce/consume `TutorialStep` + `VerificationResult` + `HintSpec` without knowing each other's internals.

### Checking each axis against the law:

| Axis | Produces | Consumes | Crosses seam via | Law holds? |
|---|---|---|---|---|
| Content | `TutorialStep` (from YAML+MD) | Nothing at runtime | step files + manifest | ✅ |
| Progression | Next step ID | `VerificationResult.passed` | bool | ✅ |
| Verification | `VerificationResult` | `VerificationContext` (engine-constructed) | frozen dataclass | ✅ |
| Guidance | `HintSpec` objects | `VerificationResult.message`, step content | string, frozen dataclass | ✅ |
| Safety | Rule activation/deactivation | `VerificationResult.passed` (for checkpoint gate) | bool | ✅ |
| Presentation | Rendered output | `TutorialStep`, `VerificationResult`, `HintRecord` | frozen dataclasses | ✅ |

**The law holds.** No axis has acquired a dependency on another axis's internals through the spec additions.

**One nuance:** `AgentContext` (axis_guidance.md §4) bundles content + verification result + metadata into an agent prompt. This is a presentation-layer concern (how to show the agent its context), not a law violation. `AgentContext` reads FROM the seam objects (`step_content: str`, `last_result: VerificationResult`), it doesn't bypass them.

---

## 5. Terminology Consistency Audit

Cross-checking terminology.md against the axis specs:

| Term | terminology.md definition | Used consistently in specs? |
|---|---|---|
| Tutorial | ✅ Interactive guided walkthrough | ✅ All specs use consistently |
| Tutorial Step | ✅ Discrete unit of work | ✅ |
| Checkpoint | ✅ Programmatic verification gate | ⚠️ axis_verification.md uses "Verification" more than "Checkpoint." Both are used but "Checkpoint" is the canonical term per terminology.md. The specs use "checkpoint" for the guardrail and "verification" for the protocol — this distinction is actually correct and clear. |
| Tutorial-Runner Agent | ✅ Single agent | ✅ axis_guidance.md §4 is consistent |
| Hint (tutorial context) | ✅ Contextual reactive nudge | ✅ |
| Tutorial Manifest | ✅ Configuration file (tutorial.yaml) | ✅ |
| Tutorial Guardrail | ✅ Active only during tutorial mode | ✅ |
| Checkpoint Guardrail | ✅ Blocks advancement until checkpoint passes | ✅ Matches `CheckpointNotPassedError` in axis_verification.md |

**No terminology drift detected.** The specs are consistent with the canonical terms.

---

## 6. Issues Summary

### Must Fix Before Architecture

| ID | Issue | Severity | Fix |
|---|---|---|---|
| C1 | Trigger shorthand naming inconsistency between Content and Guidance specs | MEDIUM | Add canonical mapping table to axis_content.md; update `_resolve_trigger()` in axis_guidance.md to use content-author shorthands |
| C2 | Branching progression is a crystal hole | MEDIUM | Explicitly defer to v2; remove from v1 axis values |
| C3 | Verification type naming (hyphens vs underscores) | LOW | Registry normalizes `s/-/_/g`; document in axis_verification.md |

### Should Fix Before Architecture

| ID | Issue | Severity | Fix |
|---|---|---|---|
| C4 | `agent_blocked_commands` creates Content↔Safety leak | MEDIUM | Auto-derive from verification config where possible; keep manual override |
| C5 | `exempt_guardrails` not yet in specs | MEDIUM | Add per-step `exempt_guardrails: list[str]` to content schema |
| C6 | `T01` guardrail rule is redundant with engine checkpoint gate | LOW | Remove `T01`; checkpoint is engine-level, not guardrail-level |
| C7 | `ProjectState.tutorial` is a minor seam leak | LOW | Define `TutorialContext` in a shared types module |

### Deferred to v2 (Explicitly)

| ID | Item | Reason |
|---|---|---|
| D1 | Branching progression model | Underspecified; v1 uses linear + checkpoint-gated only |
| D2 | Agent-Team Tutorial | No specification; special-case tutorial with agent spawning |
| D3 | Tutorial mode lifecycle state machine | Skeptic identified gap; transitions (entry/exit/abandon/resume) need spec |

---

## 7. Verdict

**The compositional structure is sound.** The Step Protocol law holds across all specs. Seams are clean with two minor leaks identified (ProjectState.tutorial, agent_blocked_commands). The crystal has one hole (branching) that should be explicitly deferred.

The three axis specs (Verification, Content, Guidance) compose coherently — they agree on seam objects, naming conventions are reconcilable, and no axis has acquired knowledge of another's internals.

**Ready for architecture phase** after resolving C1-C3 (must-fix) and explicitly deferring D1-D3.
