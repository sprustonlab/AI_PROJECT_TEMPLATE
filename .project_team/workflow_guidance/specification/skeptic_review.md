# Skeptic Review — Workflow Guidance System

## Summary Verdict

The vision is **sound in its goal** — unifying scattered guidance into YAML manifests + markdown is a genuine improvement. But the spec has **several assumptions that need stress-testing**, **interface mismatches with the existing codebase**, and **underspecified failure modes** that will bite during implementation.

---

## 1. Assumptions Challenged

### 1.1 "Rules are loaded fresh on every tool call" — Performance on NFS

The spec says: no mtime caching, re-read rules every tool call, because NFS is unreliable. The existing `evaluate` hook in `app.py` already does this for a *single file* (`rules.yaml`). The new design requires discovering and loading *multiple manifests* (`global.yaml` + every workflow manifest) on every tool call.

**Risk:** On HPC NFS, each `Path.is_file()` and `open()` is a network round-trip. With 2+ manifests, that's 4+ NFS ops per tool call. The existing code already logs warnings when evaluation exceeds 5ms. Multi-manifest loading on NFS may routinely exceed that.

**Question the spec must answer:** What's the actual I/O cost of multi-manifest loading per tool call? The spec mentions "two modes: full load (startup) and rules-only load (every tool call)" — but the rules-only load still needs to discover and read multiple files. Is there a concrete plan for keeping the hot path fast?

### 1.2 "Folder name = identity everywhere"

The spec ties folder names to manifest filenames, state.json locations, rule ID namespaces, and role types. This means renaming a workflow requires coordinating changes across 4+ locations.

**Risk:** Fragile coupling. A user renames `project_team/` to `project-team/` and everything breaks silently.

**Question:** Should the loader validate that folder names match manifest `workflow_id` at startup, or is `workflow_id` the source of truth and folder name is just convention?

### 1.3 "The engine does not inject content mid-session"

Pull-based content delivery means the agent must know to read `state.json` and load its phase file. But agents are LLMs — they don't have native file-watching. They'll only check state.json if instructed to.

**Risk:** Phase transitions triggered by the coordinator won't be noticed by other agents until their next prompt includes a directive to check. If an agent is mid-task when the phase changes, it continues operating under stale phase guidance.

**Question:** How does an agent learn that the phase changed? Is there a mechanism (e.g., `tell_agent` from the engine) to notify agents of phase transitions? The spec says "pull-based" but the real coordination seems to require push.

### 1.4 "ManualConfirm is system-level — the engine prompts the user directly"

The spec says `ManualConfirm` uses `SelectionPrompt` in the TUI, with a "confirmation callback at construction." But looking at the existing code, `SelectionPrompt` requires `async with self._show_prompt(prompt, agent=agent)` — a context manager on the `ChatApp` instance. The engine won't have access to `self` (the app).

**Risk:** The check protocol claims to be independent of the UI layer, but `ManualConfirm` requires deep coupling to the TUI. This will either (a) force the engine to depend on `app.py`, breaking the clean architecture, or (b) require a callback indirection layer that the spec doesn't describe.

**Question:** What exactly is the "confirmation callback" signature? Who passes it? How does it avoid creating a circular dependency between the workflow engine and the app?

---

## 2. Interface Questions

### 2.1 YAML field naming — pick one, document it

Existing `rules.py` parses `block` and `allow` for roles. The spec uses `block_roles` and `allow_roles`. Since this is greenfield, just pick the cleaner name and use it consistently. The spec should nail down the exact YAML schema so implementers don't have to guess.

### 2.2 Hook closure creation needs workflow context

Existing hooks in `app.py._guardrail_hooks()` capture `agent_role` as a string. The new design needs hooks to also know which workflow is active and the current phase. But `_make_options()` only receives `agent_type`. How does workflow context flow from manifest loading into the hook closure?

**Risk:** The hook creation interface needs to change, but the spec doesn't describe the new signature.

---

## 3. Failure Modes

### 3.1 Fail-closed on `workflows/` unreadable is too aggressive

The spec says: "`workflows/` unreadable → fail closed (block everything)." This means if NFS has a transient hiccup (common on HPC), *all tool calls are blocked*. Every agent stops working.

**Alternative:** Fail closed on *startup* (refuse to start if manifests can't be loaded). But on subsequent per-tool-call loads, use the last-known-good ruleset. This is safer than blocking everything on a transient I/O error.

### 3.2 "Individual manifest malformed → skip it, load the rest" loses guardrails silently

If `global.yaml` has a YAML syntax error, all global rules are silently dropped. The user has no protection and no notification.

**Risk:** A typo in `global.yaml` disables all guardrails. The spec says "startup validation catches duplicate IDs, invalid regexes, unknown phase references" — but a YAML parse error happens *before* validation. The malformed file is just skipped.

**Mitigation needed:** At minimum, a prominent warning/hint when a manifest fails to parse. Ideally, a startup check that blocks execution if a manifest is syntactically invalid.

### 3.3 Atomic writes on NFS

The spec says: "`state.json` written atomically (temp file + rename)." On NFS, `rename()` is atomic *within the same filesystem*, but `os.replace()` across NFS mount points is not guaranteed atomic. Also, temp files in the same directory on NFS can have visibility delays.

**Risk:** Concurrent agents reading `state.json` while the coordinator writes it may see partial/stale data. This is a real HPC failure mode.

**Question:** Is there a locking strategy, or does the design rely on single-writer (coordinator only)?

### 3.4 No recovery from corrupted state.json

If `state.json` becomes corrupted (NFS partial write, disk full, etc.), the spec doesn't describe recovery. Does the engine refuse to start? Reset to phase 0? The phase is effectively lost.

### 3.5 `warn` enforcement infinite loop acknowledged but not solved

The spec says "Don't use `warn` on any rules yet — it has an infinite-loop risk." But `warn` is listed as a valid enforcement level, it's in the 2x2 framing, and the YAML schema allows it. Someone *will* use it.

**Risk:** A user writes a `warn` rule, the agent acknowledges and retries, triggering the same rule, ad infinitum.

**Question:** Should `warn` be removed from the schema entirely until the loop is solved? Or should the spec describe the fix (e.g., a per-conversation cooldown)?

---

## 4. Completeness Gaps

### 4.1 No spec for how the loader discovers workflows

The spec says "everything lives under `workflows/`" but doesn't specify:
- Does the loader glob for `workflows/*/?.yaml`?
- What if there are nested subdirectories?
- What determines which workflow is "active"?
- Can there be `workflows/foo/bar/manifest.yaml` or only `workflows/foo/foo.yaml`?

The discovery algorithm is critical and unspecified.

### 4.2 No spec for the ManifestSection protocol

The spec mentions `ManifestSection[T]` as the typed parser protocol but doesn't define it. What methods does it have? What's the input/output? This is a core architectural interface that implementers need.

### 4.3 No spec for prompt assembly

"Agent prompt = identity + current phase file" — but how? String concatenation? Injected as system prompt? Via `CLAUDE.md`? The agent spawning path in `mcp.py` passes an initial `prompt` string. Does the workflow engine construct this prompt? Does it modify `_make_options()`?

### 4.4 Phase transition mechanics are underspecified

- Who triggers phase transitions? (Coordinator agent? User? Engine automatically?)
- What happens to in-flight agents when phase changes?
- Are `advance_checks` blocking? (The spec says AND semantics with short-circuit, but blocking what exactly — the coordinator's `tell_agent` call? A TUI button?)
- Can you go backward (e.g., from `testing` back to `implementation`)?

### 4.5 `/compact` recovery hook

The spec mentions a `PostCompact` SDK hook but doesn't describe:
- What content is re-injected (identity.md? phase file? both? current rules?)
- Whether this is a new SDK hook event or uses an existing one
- How the hook knows which agent's context to restore

### 4.6 `when` clause for conditional checks

The spec shows `when: { copier: use_cluster }` but doesn't define:
- How copier answers are accessed at runtime
- What the evaluation semantics are (truthy? exact match? regex?)
- Whether this is extensible beyond copier answers

---

## 5. Simplification Opportunities

### 5.1 Two-mode loader adds accidental complexity — ADOPTED

~~"Full load (startup) and rules-only load (every tool call)" means the loader has two code paths.~~ **Resolved:** Single code path is the design. One loader, one parse.

### 5.2 Namespace prefixing — PRESERVED (user design decision)

~~Use bare IDs everywhere.~~ **Ruling:** The user explicitly designed the namespace convention (`_global:pip_block`, `project_team:close_agent`). This is essential complexity — the spec should ensure error messages include both the qualified ID and the source file/line so users can trace back to their YAML.

### 5.3 CheckFailed → hints adapter — PRESERVED (explicit build scope)

~~Checks produce messages, engine displays them directly.~~ **Ruling:** The user explicitly specifies the adapter and it's in the Build scope. The spec should define the adapter interface clearly so the wiring is thin — the risk is still that it becomes over-engineered if the boundary between checks and hints isn't clean.

### 5.4 `warn` enforcement — KEPT in schema, not used in rules

~~Remove from schema entirely.~~ **Ruling:** `warn` stays as a valid enforcement level but no example rules use it. The spec documents the infinite-loop risk. **Implementation note:** the spec should still describe what "agent acknowledges" means mechanically — even if no rules use `warn` yet, the enforcement evaluation code path needs to handle it without looping.

---

## 6. What the Spec Gets Right

To be clear — the core design is solid:

- **YAML manifests + markdown content** is the right separation of concerns
- **The 2x2 framing** is genuinely clarifying and will help users reason about guidance
- **Building on existing `rules.py`** rather than rewriting is pragmatic
- **Phase-scoped rules** are the right abstraction for workflow guardrails
- **Agent folders** with identity.md + phase files is clean and extensible
- **Explicit scope boundaries** (what to build vs. not build) prevent scope creep

The design is ambitious but grounded. The risks above are addressable — but they need to be addressed *in the spec*, not discovered during implementation.

---

## 7. Recommendations

Prioritized for simplicity and less code to maintain/test (greenfield, no backward compat):

**Adopted:**
1. ~~Drop the two-mode loader~~ — **Done.** Single code path is the design.

**Overruled (user design decisions — essential complexity):**
2. ~~Use bare IDs~~ — Namespace convention preserved. Spec should ensure error messages show both qualified ID and source file for traceability.
3. ~~Drop CheckFailed→hints adapter~~ — Adapter preserved. Spec should define a thin interface to keep the wiring minimal.
4. ~~Remove `warn` from schema~~ — Kept in schema, not used in rules. Spec should describe the `warn` code path mechanically even though no rules exercise it yet.

**Active — completeness gaps being addressed:**
5. **Spec the loader discovery algorithm** — Exact glob pattern, active workflow detection, validation sequence.
6. **Define the ManifestSection protocol** — Methods, types, error handling contract.
7. **Describe phase transition flow end-to-end** — Who triggers, what blocks, what notifies agents, what happens to in-flight work. Currently the biggest gap.
8. **Resolve the ManualConfirm → TUI coupling** — Define the callback interface explicitly so the check protocol stays UI-independent.
9. **Strengthen fail-open semantics** — YAML parse errors should warn loudly, not silently skip.
10. **Define `/compact` recovery content** — What exactly gets re-injected and how.
11. **Nail down the YAML schema** — Pick clean field names, document them, single source of truth for what the loader expects.
