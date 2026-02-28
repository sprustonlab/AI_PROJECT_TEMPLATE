# Project Team

AI agents for developing new projects in the postdoc_monorepo.

**See [COORDINATOR.md](COORDINATOR.md) for team structure and workflow.**

## Agent Roster

| Agent | File | Role |
|-------|------|------|
| **Git Setup** | `GIT_SETUP.md` | Initialize repo, submodule, save prompt (runs first) |
| **Composability** | `COMPOSABILITY.md` | Lead — architecture, axis independence |
| **Terminology Guardian** | `TERMINOLOGY_GUARDIAN.md` | Leadership — naming consistency |
| **Skeptic** | `SKEPTIC.md` | Leadership — correctness through simplicity |
| **User Alignment** | `USER_ALIGNMENT.md` | Review — protect user intent, veto feature removal |
| **UI Designer** | `UI_DESIGNER.md` | Implementation — interface design (when applicable) |
| **Implementer** | `IMPLEMENTER.md` | Implementation — write the code |
| **Test Engineer** | `TEST_ENGINEER.md` | Implementation — tests and CI |
| **Binary Portability** | `BINARY_PORTABILITY.md` | Advisory — cross-language compatibility |
| **Sync Coordinator** | `SYNC_COORDINATOR.md` | Advisory — concurrency correctness |
| **Monorepo Integrator** | `POSTDOC_MONOREPO_INTEGRATOR.md` | Integration — SLC envs, commands/, launchers |

## Quick Reference

```
Leadership:     Composability + Terminology Guardian + Skeptic
Review:         User Alignment
Implementation: UI Designer + Implementer + Test Engineer
Integration:    Monorepo Integrator
Advisory:       Binary Portability + Sync Coordinator
```

## Key Rules

1. **Git Setup runs first** — Always save userprompt.md before coding
2. **User Alignment has veto** — Cannot remove user-requested features
3. **Skeptic ensures correctness** — Complete, simple, verifiable; no shortcuts
4. **Binary Portability is lower weight** — Advisory, not blocking
5. **Sync Coordinator when applicable** — Only spawns for concurrent systems
