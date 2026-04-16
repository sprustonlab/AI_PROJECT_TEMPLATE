# Project: bootstrapping_bridge
## Phase: specification (approved)
## Status: advancing_to_implementation

### Vision (approved)
Design the bootstrapping bridge — a mechanism that connects what the Copier questionnaire collects at template generation time with the runtime workflows that act on it. Solve generically for cluster setup, git setup, codebase integration, and future setup concerns.

### Identified Seams
1. Cluster setup (Copier asks ssh_target → workflow re-detects from scratch)
2. Git setup (Copier runs git init → no trigger for remote setup)
3. Existing codebase integration (Copier integrates → no workflow for late addition)
4. Claudechic mode (standard vs developer, no transition path)
5. Quick start presets → feature discovery mismatch
6. MCP tools availability (conditional generation, no late addition)

### Key Design Questions
1. State handoff: How does Copier output become workflow input?
2. Trigger mechanism: What activates setup workflows?
3. Skip vs re-verify: Adapt to pre-existing config?
4. Late addition: Add features skipped at Copier time?
5. Single orchestrator vs independent workflows?

### Reference
- PR #18: https://github.com/sprustonlab/AI_PROJECT_TEMPLATE/pull/18
- Template entry: copier.yml
- Activate script: template/activate.jinja
