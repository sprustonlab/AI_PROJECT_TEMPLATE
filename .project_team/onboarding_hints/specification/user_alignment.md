# User Alignment Check — Specification Phase

## Original Request Summary

The user's core request (from `userprompt.md`):

1. **Contextual hints at startup** — "useful hints for users as they start interacting with ClaudeChic"
2. **Git repo check example** — "check if we are a git repo and advising to launch the Git agent if we are not"
3. **Toast notifications** — "this will use the Textual's toast notification system"
4. **Trigger + message architecture** — "We need a way to have triggers and messages"
5. **Onboarding as a toggleable skill** — "I want to think about onboarding as a skill which you can turn off"
6. **Feature discovery** — "I want to think about how users discover features like the pattern mining"

Context constraints:
- This is for **AI_PROJECT_TEMPLATE** repo, not ClaudeChic itself
- ClaudeChic is the TUI used within generated projects
- Toast notifications via Textual's `self.notify()`

## Vision (from STATUS.md) vs. User Intent

### Alignment Status: ✅ ALIGNED — with minor clarifications needed

## Detailed Analysis

### ✅ Well-Captured Requirements

| User Said | Vision Captures |
|-----------|----------------|
| "useful hints for users as they start interacting" | "contextual onboarding & feature discovery system" ✓ |
| "check if we are a git repo and advising to launch the Git agent" | Git setup trigger: No `.git` directory → hint about Git agent ✓ |
| "Textual's toast notification system" | "Toast notifications via Textual's `self.notify()`" ✓ |
| "triggers and messages" | "Declarative trigger+message registry" ✓ |
| "onboarding as a skill which you can turn off" | "Toggleable skill" ✓ |
| "how users discover features like the pattern mining" | Pattern Miner row in features table ✓ |

### ❓ Clarifications Needed

1. **❓ USER ALIGNMENT: User said "as they start interacting" — does this mean startup-only or also mid-session?**
   - The vision mentions "at startup or on events" in domain terms.
   - The user's phrasing "as they start interacting" could mean just startup, or could mean the first time they encounter a relevant context.
   - The vision's interpretation (startup + events) is reasonable and more useful, but this is an assumption.
   - **Recommend:** Proceed with startup + event triggers as the vision states — this is a safe superset. But keep the architecture open for both, don't hard-code startup-only.

2. **❓ USER ALIGNMENT: User said "I want to think about" (twice) — exploratory vs. prescriptive.**
   - Quote: "I want to think about onboarding as a skill which you can turn off"
   - Quote: "I want to think about how users discover features like the pattern mining"
   - The phrasing "I want to think about" signals these are **design directions to explore**, not hard requirements. The vision treats them as confirmed features, which is fine — but the team should know the user was in exploratory mode and be open to pivoting.
   - **Recommend:** No action needed, but don't over-engineer these areas. Keep them simple and easy to change.

3. **❓ USER ALIGNMENT: User said "advising to launch the Git agent" — specific wording.**
   - The vision table says: "No git repo detected — spawn a Git agent to set one up"
   - User said: "advising to **launch** the Git agent"
   - "Spawn" vs. "launch" is minor, but "advising" is key — the hint should **suggest**, not auto-launch.
   - **Recommend:** Ensure hints are advisory (toast notifications), not auto-actions. This seems already captured correctly.

### ✅ No Scope Creep Detected

The additional feature examples in the vision table (Guardrails, Project Team, MCP Tools, Cluster) are **reasonable extrapolations** of the user's request to "discover features like the pattern mining." The user listed one example (pattern mining) and the vision correctly generalized to all template features. This is aligned with intent.

The "1-2 toasts/session" constraint is a good addition that wasn't explicitly requested but serves the user's implicit intent (helpful, not annoying). ✅ Appropriate.

### ✅ No Scope Shrink Detected

All six core elements from the user's request are represented in the vision.

## Summary

| Aspect | Status |
|--------|--------|
| Core functionality | ✅ Aligned |
| Toast notifications | ✅ Aligned |
| Trigger/message architecture | ✅ Aligned |
| Toggleable skill | ✅ Aligned |
| Feature discovery | ✅ Aligned |
| Scope creep | ✅ None detected |
| Scope shrink | ✅ None detected |
| Wording fidelity | ✅ Minor ("spawn" vs "launch") — acceptable |

**Overall: ✅ ALIGNED** — The vision faithfully captures user intent. The team can proceed to specification with confidence. The main note is to keep the "I want to think about" areas simple and flexible, since the user was exploring rather than prescribing.
