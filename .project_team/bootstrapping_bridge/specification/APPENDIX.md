# Bootstrapping Bridge Specification — Appendix

## A. Resolved Design Decisions

These decisions were debated during the specification process and are recorded here for context.

1. **SSH latency:** Synchronous/blocking. One-time check at session start. Simplicity over optimization.

2. **Queue on manual stop:** Skip to next. If user stops a queued workflow, auto-advance to the next one. Queue only clears when empty.

3. **Dismiss scope:** Permanent forever. "Don't show again" means never show again. No reset on `copier update`. User can run facet workflows manually.

4. **No bridge file.** `.copier-answers.yml` is used directly via the existing `CopierAnswers` class. No `bridge.yaml` or `project_state.yaml`.

5. **No claudechic core manifest changes.** The onboarding system does not add keys to workflow manifests (`concern:`, `copier_keys:`, `skip_when:` were all considered and rejected). The facet map is hardcoded in the session-start check. One-way dependency: onboarding knows about facet workflows; facet workflows know nothing about onboarding.

6. **No onboarding workflow.** Onboarding is a session-start prompt, not a workflow or MCP tool. Earlier designs included `workflows/onboarding/` with role files, an `mcp_tools/onboarding.py` tool, and an `/onboard` slash command — all removed in favor of the simpler prompt-and-queue model.

7. **No workflow_queue.** Considered a general-purpose `workflow_queue` MCP tool (~70 lines) for chaining facet workflows within a single session. Rejected because: (a) the session-start check already computes "what's next" from ground truth each session, making queue state redundant, (b) marathon multi-workflow sessions accumulate context and cause user fatigue, (c) one facet per session is natural and keeps context windows fresh. The welcome screen + idempotent health checks provide the sequencing for free.

8. **Welcome screen over prompt.** The original session-start check was a three-option prompt (yes/not now/don't show). Replaced with a visual checklist that shows status of ALL facets (configured and unconfigured), gives the user full choice of which to work on, and provides a richer first-session experience. Same dismiss semantics, better UX.

## B. Low-Priority Informational Facets

These facets have no facet workflow and are not part of the onboarding queue. They are informational only.

| Facet | Copier Key | Runtime State | Notes |
|-------|-----------|--------------|-------|
| Claudechic mode | `claudechic_mode` | standard or developer | No transition path exists today. |
| Content preset | `quick_start` | Which files exist | One-shot at generation. `copier update` to change. |
| MCP tools | `use_cluster` | Files in `mcp_tools/` | Both backends + single `cluster.yaml` ship when `use_cluster=true`. Bundled with cluster facet. |

## C. Pattern Mining

Pattern mining (`mine-patterns` command, `scripts/mine_patterns.py`) analyzes Claude Code session history for recurring corrections and should become a proper workflow (`/pattern-mining`). It is **not an onboarding facet** — it requires session history to exist, so it cannot run at project setup time. It is a separate effort outside this spec's scope.

## D. Spec Version History

1. **Initial design:** Generic bootstrapping bridge with `project_state.yaml`, per-concern protocol, self-describing manifest keys (`concern:`, `copier_keys:`, `skip_when:`), and claudechic core ManifestLoader changes.
2. **Onboarding MCP + workflow:** Replaced bridge file with onboarding MCP tool + dedicated onboarding workflow with role files and facet map in YAML.
3. **Session-start prompt + queue:** Eliminated onboarding workflow and MCP tool entirely. Onboarding became a session-start check that queues standalone facet workflows via `workflow_queue`.
4. **Copier simplification:** Reduced Copier to intent-only bools. Removed `cluster_scheduler`, `cluster_ssh_target`, `existing_codebase` (path), `codebase_link_mode`. Unified `lsf.yaml`/`slurm.yaml` into single `cluster.yaml`.
5. **Welcome screen:** Eliminated `workflow_queue` entirely. Replaced the yes/not-now/dismiss prompt with a visual welcome screen showing a checklist of facet statuses. User selects which facet to work on (full agency, no forced ordering). One facet per session; welcome screen reappears with updated status each session. Reduced core changes from ~150 lines to ~100-130 lines.
