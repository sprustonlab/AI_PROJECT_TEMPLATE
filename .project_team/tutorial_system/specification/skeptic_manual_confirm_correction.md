# Skeptic: ManualConfirm Correction — Acknowledging the Error

**Reviewer:** Skeptic
**Date:** 2026-04-04

---

## The error

My previous analysis (`skeptic_coordinator_checks.md`) said:

> "ManualConfirm gates duplicate existing Coordinator behavior. The Coordinator IS the gate."

This was wrong. The Coordinator is an LLM. LLMs skip steps, cut corners, and hallucinate that they performed actions they didn't. The Coordinator is not a reliable gate — it's the thing being gated.

**The correction:** ManualConfirm as an engine-level gate means the *engine* asks the user, not the Coordinator. The Coordinator cannot bypass it. This is enforcement, not duplication.

The principle I missed:

| Layer | What it prevents |
|---|---|
| Guardrails | Agent bypassing system constraints (running forbidden commands) |
| ManualConfirm gate | Coordinator bypassing user checkpoints (advancing without asking) |
| CommandOutputCheck gate | Coordinator claiming tests pass when they don't |

All three are the same pattern: **system-level enforcement of things the agent's prompt says to do but can't be trusted to always do.**

---

## What this changes

### 1. ManualConfirm is NOT redundant — REVERSED

My previous verdict: "ManualConfirm has zero v1 consumers. Cut it."

**New verdict: ManualConfirm is essential for every User Checkpoint 👤 in the team workflow.**

The Coordinator's prompt says "User Checkpoint 👤: Present Vision Summary. Loop until approved." But nothing enforces this. The Coordinator can:
- Skip the checkpoint entirely
- Present a summary and advance without waiting for approval
- Claim the user approved when they didn't (hallucination under context pressure)

ManualConfirm gates make these checkpoints load-bearing:

```yaml
- id: vision
  file: phases/phase-00-vision.md
  advance_checks:
    - type: manual-confirm
      question: "Has the user approved the Vision Summary?"
```

Now the engine won't advance past vision until the user explicitly confirms. The Coordinator's prompt still says to present and loop, but even if it fails to follow those instructions, the gate holds.

### 2. Team workflow advance_checks — REVERSED

My previous verdict: "Remove all advance_checks from team phases.yaml."

**New verdict: Most team phases SHOULD have advance_checks.** The mix is:

| Phase | Gate type | Why |
|---|---|---|
| vision → setup | `manual-confirm` | User must approve vision. Coordinator can't skip this. |
| setup → spawn-leadership | None needed | Mechanical steps, Coordinator creates files. If it fails, Phase 2 fails visibly. |
| spawn-leadership → specification | None needed | `list_agents` verification is already in the prompt AND agent spawn failures are visible. |
| specification → implementation | `manual-confirm` | User must approve spec. This is the highest-value gate — a bad spec causes cascading waste. |
| implementation → testing | `manual-confirm` | Leadership must approve implementation. User should confirm. |
| testing → signoff | `command-output-check` | Tests must pass. Machine-verifiable. |
| signoff → integration | `manual-confirm` | All agents confirm ready. User should verify. |

### 3. "1 out of 8 transitions is machine-verifiable" — STILL TRUE, but irrelevant

My observation that most gates are judgment-based was correct. My conclusion was wrong. The fact that "user approves spec" is subjective doesn't mean it can't be enforced — it means the enforcement mechanism is ManualConfirm (ask the human) rather than CommandOutputCheck (ask the machine). The gate is still real. The engine still enforces it.

### 4. The double-confirmation concern — was wrong

I said:

> "Adding ManualConfirm makes the user confirm twice."

In the happy path, yes — the Coordinator asks, user approves, engine confirms. Two interactions about the same thing. But this is **exactly how guardrails work**: the agent's prompt says "don't run pytest outside testing phase," AND the guardrail enforces it. The prompt is the first line of defense (handles 95% of cases). The system enforcement is the backstop (catches the 5%).

ManualConfirm is a backstop, not a primary interaction. In the happy path, the Coordinator asks the user, user approves, Coordinator calls advance, engine's ManualConfirm fires, user confirms. The "double ask" is the cost of enforcement — same cost we pay for every guardrail that catches an action the agent's prompt already says not to do.

If the cost is too high (UX friction from double-asking), the solution is to make ManualConfirm aware of the Coordinator's conversation — but that's a v2 optimization, not a reason to cut enforcement.

---

## What this does NOT change

### 1. Check primitive scope — still slim

CommandOutputCheck + ManualConfirm are the two check types with real v1 consumers. My previous analysis that FileExistsCheck is unnecessary still holds — file existence is either:
- A precondition for a command check (file must exist for pytest to find it)
- Something the Coordinator just created (checking your own work)
- Better handled by a domain-specific TriggerCondition

The Check system is: CommandOutputCheck (machine gates) + ManualConfirm (human gates). Two types, not three.

### 2. ManualConfirm is still not a "system assertion"

My previous analysis said ManualConfirm isn't a check on system state — it's a human interaction. That observation was correct. But the conclusion was wrong. It doesn't need to be a system assertion to be a Check. It needs to be a gate that the engine enforces. The Check protocol (`check(ctx) → CheckResult`) is the right interface: the engine calls it, it returns pass/fail, the engine gates on the result.

### 3. `ask_user()` on CheckContext — needs revisiting

In `improve_skeptic_v2.md`, I recommended removing `ask_user()` from CheckContext and having ManualConfirm call `input()` directly. Given that ManualConfirm is now a core v1 check type (not a cut candidate), this recommendation needs nuance:

- **The concern is still valid:** `ask_user()` on a "read-only context" is a side effect that breaks the pure-inspection model.
- **But ManualConfirm needs SOME way to ask the user.** `input()` directly works for CLI. But if the engine ever runs in a non-CLI context (MCP tool, web UI), `input()` breaks.
- **Revised recommendation:** ManualConfirm receives an `ask_user` callable as a constructor parameter (dependency injection), not via CheckContext. This keeps CheckContext pure AND makes ManualConfirm testable AND makes the interaction mechanism pluggable:

```python
@dataclass(frozen=True)
class ManualConfirm:
    question: str
    ask_user: Callable[[str], str] = input  # Default to input(), injectable for testing

    def check(self, ctx: CheckContext) -> CheckResult:
        answer = self.ask_user(f"{self.question} [y/N]: ").strip().lower()
        passed = answer in ("y", "yes")
        return CheckResult(
            passed=passed,
            message=self.question,
            evidence=f"User answered: {answer}",
            check_type="manual-confirm",
        )
```

### 4. `/check-setup` — still cut from v1

Standalone checks are still not a v1 requirement. ManualConfirm being restored doesn't change this.

### 5. `generate_hooks.py` spike first — still correct

The riskiest assumption is still guardrail integration. ManualConfirm being restored doesn't change the implementation order.

---

## Updated Check primitive scope

| Check type | v1 consumer | Purpose |
|---|---|---|
| **CommandOutputCheck** | Tutorial gates, team testing gate | Machine-verify system state |
| **ManualConfirm** | Team workflow user checkpoints | Enforce human approval at engine level |
| ~~FileExistsCheck~~ | ~~None that TriggerCondition can't handle~~ | Cut from v1 |

**Two check types. Not three, not one.** CommandOutputCheck gates machines. ManualConfirm gates the Coordinator. Both enforced by the engine.

---

## The lesson

I treated the Coordinator as a reliable component. It's not. It's an LLM following a prompt — same as every other agent. The entire guardrail system exists because agents can't be trusted to follow prompts perfectly. ManualConfirm is the same principle applied to phase transitions.

My role file says: "Is simplicity masking incompleteness?" Cutting ManualConfirm was simplicity masking incompleteness. The Coordinator's prompt-level User Checkpoints are the simple version that works 95% of the time. ManualConfirm is the complete version that works 100% of the time. I chose simple over complete. That was wrong.
