# Project Types

At Phase 0, classify project by signals. Use default axes for that type.

| Type | Signals | Default Axes |
|------|---------|--------------|
| Implementation | add, build, create, new, implement | SourceModularity, LanguageTransferability, MemoryLayout, AbstractionLayers, APIvsGUI |
| Refactoring | refactor, restructure, clean up, extract | BeforeVsAfter, PublicVsInternal, TestCoverage, DependencyDirection, BreakingVsNonBreaking |
| Investigation | debug, why, broken, figure out, not working | SymptomVsCause, ReproducibleVsIntermittent, CodeVsConfig, RecentVsLongstanding, IsolatedVsSystemic |
| Bug Fix | fix, patch, issue #, repair | RootCauseConfirmed, RegressionRisk, TestCoverage, IsolatedVsSystemic |
| Research | explore, evaluate, compare, understand, options | BreadthVsDepth, TheoreticalVsPractical, ReversibleVsCommitting, DocumentedVsTribal |
| Documentation | document, README, guide, explain, docs | AudienceLevel, ReferenceVsTutorial, CurrentVsAspirations, CodeVsProse |
| Performance | slow, optimize, faster, memory, profiling | MeasuredVsAssumed, LatencyVsThroughput, SpaceVsTime, HotPathVsColdPath, AlgorithmVsImplementation |
| Migration | migrate, upgrade, port, move to, convert | BigBangVsIncremental, CompatibilityLayer, DataMigration, RollbackStrategy, FeatureParity |
| Security | secure, vulnerability, auth, audit, harden | ThreatModel, DefenseInDepth, TrustBoundary, SecretsManagement, AuditTrail |
| Testing | test, coverage, CI, regression | UnitVsIntegrationVsE2E, HappyPathVsEdgeCases, MocksVsReal, DeterministicVsFlaky, SpeedVsThoroughness |
| Deployment | deploy, Docker, CI/CD, release, ship | LocalVsRemote, ManualVsAutomated, RollbackStrategy, EnvironmentParity |
| Integration | integrate, connect, API, webhook, sync | ProtocolAlignment, ErrorHandling, AuthFlow, DataMapping |
| Workflow | workflow, process, coordination, handoff | InstructionVsReference, KernelVsInstance, RoleVsPhase, MandatoryVsOptional, CoordinatorVsAgent |
| Data/Schema | schema, database, migration, ETL, data model | BackwardsCompatibility, DataMigration, NullHandling, IndexStrategy, ValidationRules |

---

## Classification Procedure

1. **Match signals** from user prompt to Type column
2. **Overlapping signals** → ask user to confirm primary type
3. **No match** → default to Implementation
4. **Multiple types** → union axes, let N/A procedure filter irrelevant ones

Example multi-type:
- "Add authentication feature" → Implementation + Security
- "Speed up the API" → Performance + Refactoring

---

## Extending

Add row to table: `Type | Signals | Default Axes`

Axes should be 3-6 orthogonal dimensions relevant to that work type.
