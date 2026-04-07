# User Alignment Check — SDK Hooks Architecture

**Trigger:** Architecture change — SDK hooks replace file hooks, claudechic required
**Date:** 2026-04-05

---

## Original Request (verbatim)

> Add a "tutorial" feature to the template that combines md files, a team of agents, hints, and guardrails in a new mode to help users complete a task.

## Key User Decisions (from STATUS.md)

1. "v1 is infrastructure, v2 is tutorial" — infrastructure-first is deliberate
2. "claudechic is required" — no vanilla Claude Code fallback
3. "ship 1 thing, not 2" — one hook system, not hybrid
4. Guardrails move from generated file hooks to SDK in-process hooks in claudechic
5. `user_confirm` enforcement level: proven via PoC (SelectionPrompt in TUI)

---

## 1. Does the SDK Hook Architecture Serve Scientists Well?

### ✅ ALIGNED — SDK hooks are better for the target user

**User's success vision:**
> A user types a command, picks "SSH into my cluster," and gets a guided, interactive walkthrough — with agents helping, hints nudging, and guardrails both preventing mistakes AND verifying that each step was actually completed.

The SDK hook architecture serves this vision **better** than file hooks for scientists:

| Concern | File Hooks (old) | SDK Hooks (new) | Scientist impact |
|---|---|---|---|
| **Guardrail latency** | ~50-100ms (subprocess spawn) | <5ms (in-process) | Smoother interactive experience during tutorials |
| **`user_confirm` prompts** | Not possible (exit code protocol has no "ask user" path) | Native TUI prompt via `SelectionPrompt` | Scientists get the "guardrails ask YOU, not the agent" experience the user demanded |
| **Rule changes** | Requires `generate_hooks.py` rebuild | Runtime evaluation from YAML | Scientists editing `rules.yaml` see changes immediately — no rebuild step to forget |
| **Error diagnosis** | Separate process, opaque failures | In-process, stderr logging | When something goes wrong, scientists (or their support staff) can debug it |
| **NFS reliability** | Generated files can go stale on HPC NFS | No generated files — reads YAML at runtime | Eliminates a class of "works on my machine" cluster bugs |

**The `user_confirm` capability is critical.** The user's failure vision explicitly says:
> Tutorials where the agent claims success without verification — the user thinks they're set up but nothing actually works.

`user_confirm` is the mechanism that prevents this. The engine asks the **user** directly — the agent cannot fabricate approval. This enforcement level was impossible with file hooks (exit code 0 or 2, no middle ground). SDK hooks make it native.

**NFS note:** The spec correctly identifies that `rules.yaml` is loaded fresh each call without mtime caching, because "NFS mtime is unreliable on HPC clusters." This is scientist-aware design. ✅

### One concern: error message clarity

When SDK hooks block an action, the scientist sees the rule's `message` field. These messages (e.g., `"[GUARDRAIL DENY R02] Use pixi to manage packages..."`) are written for developers, not scientists learning to code.

❓ **USER ALIGNMENT: The tutorial user journey shows scientists getting guided walkthroughs.** When a guardrail fires during a tutorial, does the message make sense to a scientist who doesn't know what pip is?

**Recommendation:** This is a v2 content concern, not a v1 architecture concern. The SDK hook architecture supports per-rule messages — the infrastructure is sound. Tutorial-specific rule messages can be improved when tutorial content is authored. No architecture change needed.

---

## 2. Migration Safety — No Guardrail Gaps During Transition

### ✅ ALIGNED — the "ship 1 thing" decision eliminates gap risk

The user said **"ship 1 thing, not 2."** This means: delete file hooks, ship SDK hooks. No hybrid period where both systems coexist and might conflict.

**Migration plan from STATUS.md:**

| What's deleted (~2860 lines) | What's added (~210 lines) |
|---|---|
| `generate_hooks.py` (2155 lines) | `guardrails/rules.py` (~100) |
| `bash_guard.py` (173), `write_guard.py` (185) | `guardrails/hits.py` (~30) |
| `role_guard.py` (~350) | `app.py` changes (~50) |
| `settings.json` hook entries | `ConfirmPrompt` widget (~30) |
| Session marker system, env vars | |

**Gap analysis:**

| Capability | File hooks had it? | SDK hooks have it? | Gap? |
|---|---|---|---|
| R01: pytest output redirect | ✅ | ✅ (PoC proven) | No |
| R02: pip/conda install block | ✅ | ✅ (PoC proven: deny) | No |
| R03: git push block | ✅ | ✅ (same regex matching) | No |
| R04: conda install block | ✅ | ✅ (same regex matching) | No |
| R05: guardrail config protection | ✅ | ✅ (field-level detect) | No |
| Role-based scoping (`block:`) | ✅ (`role_guard.py`) | ✅ (`should_skip_for_role()`) | No |
| Hit logging (`hits.jsonl`) | ✅ | ⚠️ Planned (`hits.py` ~30 lines) | **Not yet implemented** |
| Ack token system (warn enforcement) | ✅ (`check_write_ack()`) | ❓ Not mentioned in PoC | **Needs verification** |
| `user_confirm` enforcement | ❌ | ✅ (NEW — PoC proven) | Net gain |
| Phase-scoped rules | ❌ | ✅ (NEW — `should_skip_for_phase()`) | Net gain |

### ⚠️ MINOR GAP: Ack token system for `warn` enforcement

The file-based `role_guard.py` has a `check_write_ack()` function that implements TTL-scoped acknowledgment tokens for warn-level Write/Edit operations. The SDK hook PoC logs warn matches but doesn't implement the ack token flow.

**Risk:** Low. The ack system was a workaround for file hooks' limited communication channel. SDK hooks can implement warn differently (e.g., log + continue, or use a simpler in-process ack). But this should be explicitly decided during implementation — not silently dropped.

**Recommendation:** Implementation team should document whether ack tokens are preserved, replaced, or intentionally removed. If removed, the rationale should be recorded (SDK hooks make ack unnecessary because X).

### ⚠️ MINOR GAP: hits.jsonl logging

STATUS.md lists `hits.py (~30 lines)` as planned but not yet implemented. The audit trail is important for scientists' supervisors who want to verify the guardrails are working.

**Recommendation:** Ensure hit logging is implemented before the file hooks are deleted. The audit trail should not have a gap.

---

## 3. User-Facing Documentation Needing Updates

### Documents that reference the old architecture:

| Document | What needs updating | Priority |
|---|---|---|
| `.claude/guardrails/README.md` (15 KB) | References `generate_hooks.py`, `bash_guard.py`, `write_guard.py`, role_guard, session markers. All of this is being deleted. | **HIGH** — scientists read this |
| `.claude/guardrails/rules.yaml.example` (11 KB) | May reference file-hook-specific patterns | **MEDIUM** — developer reference |
| `SPECIFICATION.md` Section 3.3 | Still references `generate_hooks.py` in several places (line 442: "The validator in `generate_hooks.py`", line 817: "`generate_hooks.py` can discover phase IDs"). Implementation order step 1 references `generate_hooks.py spike`. | **HIGH** — spec must be consistent |
| `SPECIFICATION.md` Section 6 (File Structure) | Lists `.claude/guardrails/generate_hooks.py` and `phase_guard.py` as separate files. With SDK hooks, `phase_guard.py` logic lives in `rules.py` (`should_skip_for_phase()`). | **HIGH** — file structure is wrong |
| `SPECIFICATION.md` Section 8.3 (Implementation order) | Step 1 says "extend `generate_hooks.py`" — this file is being deleted | **HIGH** — implementation plan is stale |
| `SPECIFICATION.md` Appendix B.1-B.2 | Reference implementations use `generate_hooks.py` for phase registry building and validation | **MEDIUM** — these are reference, not normative |

### ❓ USER ALIGNMENT: SPECIFICATION.md is internally inconsistent

The spec was "updated for SDK hook architecture" (line 5) but retains multiple references to `generate_hooks.py` as if it still exists. Section 3.3 correctly describes SDK hooks, but Section 6 (File Structure), Section 8.3 (Implementation Order), and Appendix B still reference the old system.

**Recommendation:** The spec needs a consistency pass. Every reference to `generate_hooks.py`, `phase_guard.py` as a separate file, `bash_guard.py`, `write_guard.py`, and `settings.json hook entries` should be updated or removed. This is not cosmetic — the implementation team will read the spec and encounter contradictions.

---

## 4. Onboarding Flow with claudechic as Required Entry Point

### ✅ ALIGNED — but documentation must be clear

The user decided: **"claudechic is required — no vanilla Claude Code fallback."**

This means every scientist using the template MUST use claudechic. The onboarding flow is:

```
Scientist gets template → installs pixi → runs claudechic (not `claude`)
                                              ↓
                                     SDK hooks active from first session
                                     Setup check hints fire automatically
                                     Guardrails protect from first command
```

**This is good for the user's vision.** The user wants guardrails "preventing mistakes AND verifying that each step was actually completed." If scientists could bypass claudechic and run vanilla `claude`, they'd get zero protection. The "no fallback" decision ensures 100% guardrail coverage.

### What must be true for this to work:

1. **The template's README/onboarding docs must say `claudechic`, not `claude`.** If any doc says "run `claude`" the scientist will do that instead and get no guardrails.

2. **Error messages when running vanilla `claude` should be helpful.** If a scientist accidentally runs `claude` instead of `claudechic`, they should get a clear message about what to do. (This may already exist — it's a claudechic concern, not a tutorial-system concern.)

3. **The setup check hints (Section 2.3 of spec) fire in claudechic.** These are the scientist's first interaction with the guardrail system — "GitHub auth failed," "Git email not configured," etc. They fire via the hints pipeline, which runs inside claudechic. ✅ This works because claudechic owns the hints engine.

4. **`/tutorial` slash command works in claudechic.** The spec says tutorials are launched via `.claude/commands/tutorial.md`. This must be accessible from claudechic's command system.

### ❓ Potential confusion: claudechic vs claude

Scientists on HPC clusters may have `claude` installed system-wide (via IT) and `claudechic` installed via pixi. The path resolution could surprise them.

**Recommendation:** The template's activation script (pixi environment) should ensure `claudechic` is on the PATH and ideally shadow any system `claude`. This is existing infrastructure (pixi handles PATH), but worth verifying during implementation.

---

## 5. Cross-Check: Do User Decisions Survive?

| User decision | Still respected? | Evidence |
|---|---|---|
| "v1 is infrastructure, v2 is tutorial" | ✅ | SDK hooks are infrastructure. Tutorial content is v2. The hook system serves both project-team and tutorials. |
| "claudechic is required" | ✅ | Spec Section 3.3: "claudechic is required. All guardrail hooks are SDK hooks registered via the claudechic Python SDK. There is no vanilla Claude Code fallback." |
| "ship 1 thing, not 2" | ✅ | STATUS.md deletes ~2860 lines of file hooks, adds ~210 lines of SDK hooks. No hybrid. |
| `user_confirm` enforcement | ✅ | PoC proven. `SelectionPrompt` in TUI. Agent cannot fabricate approval. |
| "Workflow" umbrella term | ✅ | Spec uses "workflow" consistently. WorkflowEngine serves both project-team and tutorials. |
| 2×2 framing (advisory/enforced × positive/negative) | ✅ | Spec Section 1.0 documents this. `user_confirm` is enforced-negative. All four quadrants represented. |

---

## 6. Scope Creep Check

### Is anything being added that the user didn't ask for?

**No.** The SDK hook migration is a pure implementation change — same rules, same enforcement, better mechanism. The net-new capabilities (`user_confirm`, `phase_block`/`phase_allow`) are directly required by the user's vision:
- `user_confirm` → "guardrails verifying that each step was actually completed" (user can't be bypassed)
- `phase_block`/`phase_allow` → "guardrails in a new mode" (mode-scoped safety)

### Is anything being removed that the user asked for?

**No.** All five rules (R01-R05) transfer. Role-based scoping transfers. Hit logging is planned. The only potential loss is the ack token system, which should be explicitly decided (see Section 2).

---

## Final Verdict

### ✅ ALIGNED — SDK hooks serve the user's vision better than file hooks

The architecture change is sound, well-motivated, and proven via PoC. It enables capabilities (`user_confirm`) that the user's vision requires and that were impossible with file hooks. The "ship 1 thing" and "claudechic is required" decisions eliminate transition risk.

### Action items for the team:

1. **SPECIFICATION.md consistency pass** — Remove/update all `generate_hooks.py` references. Section 6 file structure, Section 8.3 implementation order, and Appendix B are stale. (HIGH priority — blocks implementation)

2. **Decide ack token fate** — Explicitly document whether the warn-level ack token system is preserved, replaced, or removed in SDK hooks. Don't let it silently disappear.

3. **Implement hits.jsonl before deleting file hooks** — No audit trail gap during migration.

4. **Update `.claude/guardrails/README.md`** — Scientists read this. It must describe the SDK hook system, not the deleted file hook system.

5. **Verify claudechic PATH precedence** — Ensure pixi environment shadows any system-wide `claude` binary so scientists always get guardrail-protected sessions.

### My role going forward:

I'll continue checking that implementation decisions serve the scientist end-user. The SDK hook architecture is the right foundation — the remaining risks are documentation consistency and migration completeness, not architectural direction.
