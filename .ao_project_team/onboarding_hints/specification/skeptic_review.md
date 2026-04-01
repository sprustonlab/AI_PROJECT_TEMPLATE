# Skeptic Review: Hints System

## Summary Verdict

The vision is **sound but under-specified in critical areas**. The core idea — contextual toast notifications driven by a declarative trigger registry — is good. But several assumptions need challenging before we build, or we risk shipping something that annoys users instead of helping them.

---

## Assumption Challenges

### 1. "1-2 toasts per session is the right amount"

**Challenge:** Who decides which 1-2 hints fire when multiple triggers match? The vision says "1-2 toasts/session" but provides no prioritization or rate-limiting mechanism. If a fresh project has no git, default guardrails, empty `mcp_tools/`, and has never run the pattern miner — that's 4+ triggers firing simultaneously.

**Risk:** Without explicit priority + throttling, either (a) all hints fire and overwhelm the user, or (b) we pick arbitrarily and the user never sees important ones.

**What's needed:** A priority scheme and a per-session budget with carryover/suppression logic. This is essential complexity — don't skip it.

### 2. "Declarative registry makes this easy to extend"

**Challenge:** "Declarative" is doing a lot of heavy lifting here. Some triggers are trivial path checks (`os.path.exists('.git')`). Others require counting sessions, checking config state, or determining "has the user ever run X." These are fundamentally different operations. A purely declarative registry either:
- Becomes so general it's a mini-language (accidental complexity), or
- Pushes complex checks into ad-hoc callback functions (declarative in name only)

**Risk:** We build a registry that's clean for simple cases but awkward for the interesting ones (pattern miner session counting, cluster "configured but unused").

**What's needed:** Be honest about what "declarative" means here. A registry of `{id, condition_fn, message, priority, category}` where `condition_fn` is a callable is simpler and more honest than a YAML DSL that can't express the real conditions.

### 3. "This should be a skill you can turn off"

**Challenge:** The existing skill system (via `help_data.py`) discovers skills from `~/.claude/plugins/installed_plugins.json` and `settings.json`. Skills are plugin-scoped. But hints are a **template-level feature**, not a plugin. The toggle mechanism needs to work differently — probably via the `.claudechic.yaml` config system (which already has `experimental.*` feature flags) or a per-project config.

**Risk:** Trying to shoe-horn this into the plugin/skill toggle system when it's architecturally a different thing. Or building a second toggle mechanism when one already exists.

**What's needed:** Decide: is this a config flag (`hints.enabled: true` in `.claudechic.yaml`) or a proper skill with a SKILL.md? These have different discovery, lifecycle, and UX implications. Don't conflate them.

### 4. "Toast notifications are the right delivery mechanism"

**Challenge:** Textual toasts are ephemeral — they disappear after timeout. For hints that require action (e.g., "spawn a Git agent"), the user may read the toast, not act immediately, and then lose the information. There's no "show me that hint again" path.

**Risk:** Users see hints but can't recall or retrieve them. The system does work but feels unreliable.

**What's needed:** Consider whether dismissed hints should be re-surfaceable (e.g., `/hints` command to list pending/recent hints). This isn't scope creep — it's completing the UX loop. Without it, a transient toast carrying actionable advice is a leaky bucket.

### 5. "Triggers run at startup"

**Challenge:** The vision implies startup-time checks. But some triggers only make sense mid-session (e.g., "you've been editing guardrails files — did you know about role-gated rules?"). Startup-only triggers miss contextual moments that are the whole point of contextual hints.

**Risk:** Building a startup-only system and then needing to retrofit event-driven triggers later, which is a fundamentally different architecture.

**What's needed:** Decide scope now. If startup-only, say so explicitly and accept the limitation. If event-driven triggers are in scope, the architecture needs hooks/observers, not just a startup scan. The six examples in the vision are all state-checks (startup-friendly), so startup-only may be the right v1 — but name that decision.

---

## Failure Modes

### F1: The Nag Machine
If hints re-fire every session until the user acts, the system becomes nagging software. Users will disable it entirely rather than address individual hints. **Mitigation:** Track shown hints with timestamps; implement cooldown periods and max-show counts per hint.

### F2: Stale Hints
A hint says "No git repo detected" but the user set up git 30 seconds ago in another terminal. State checks at startup can be stale by mid-session. **Mitigation:** Accept this as a v1 limitation. Don't over-engineer real-time state watching. But document it.

### F3: Template Versioning
The hint registry ships with the template via Copier. When the template is updated, new hints arrive but the user's suppression state (stored locally) may reference old hint IDs. Renamed/restructured hints could re-fire or silently never fire. **Mitigation:** Use stable hint IDs. Version the registry format. Handle unknown IDs gracefully in state files.

### F4: Condition Check Failures
If a condition function throws (e.g., permission error reading `.git/`), does the whole hint system crash, or is that hint skipped? The MCP discovery system has an iron rule: "discovery never crashes." The hint system needs the same. **Mitigation:** Wrap every condition check in try/except. Log failures, skip the hint. Never crash the app for a hint.

### F5: Contradictory Hints
Two hints could fire that suggest conflicting actions, or a hint could suggest something inappropriate for the user's setup (e.g., "set up cluster" when the user explicitly chose `use_cluster=false` during Copier generation). **Mitigation:** Hints must be aware of Copier answers / project config. Don't suggest features the user opted out of. This means the hint registry needs access to project config, not just filesystem state.

---

## Simplification Opportunities

1. **Don't build a DSL.** A Python list of hint dataclasses with callable conditions is simpler, more testable, and more honest than YAML-based trigger definitions. YAML is great for data; it's poor for logic.

2. **State file can be trivial.** `{hint_id: {shown_count: int, last_shown: timestamp, dismissed: bool}}` in JSON. Don't over-design this.

3. **Use the existing config pattern.** `.claudechic.yaml` already has feature flags. Add `hints: {enabled: true}` there. Don't invent a new toggle system.

4. **Start with startup-only triggers.** All six examples in the vision are startup-checkable. Don't build event infrastructure for v1.

---

## Essential Complexity That Must Not Be Avoided

1. **Priority + throttling logic** — Without this, the "1-2 per session" goal is unachievable. This is the hard part of the design.
2. **Copier-config awareness** — Hints must know what features the project was generated with, or they'll suggest disabled features.
3. **Graceful degradation** — Every condition check must be wrapped. The hint system must never crash the app.
4. **State persistence** — Tracking what's been shown, when, and whether it was dismissed. Without this, hints either nag or vanish.

---

## Four Questions Applied

1. **Does this fully solve what the user asked for?** The vision covers the "what" well. The "how" is under-specified on priority, throttling, toggle mechanism, and Copier-config awareness. These gaps must be addressed in the spec, not deferred to implementation.

2. **Is this complete?** Not yet. Missing: prioritization scheme, re-surfacing UX, condition error handling strategy, template-versioning story.

3. **Is complexity obscuring correctness?** Not yet — but the "declarative registry" language risks pulling toward a YAML DSL that adds accidental complexity. Keep it as code.

4. **Is simplicity masking incompleteness?** The "1-2 toasts per session" framing sounds simple but hides the hard problem of selection and suppression. Name the algorithm, don't just name the goal.
