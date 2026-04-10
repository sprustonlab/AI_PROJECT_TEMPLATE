# Seam Analysis: Agent Roles & Guardrail Rules

**Requested by:** Coordinator
**Date:** 2026-03-29
**Author:** Researcher

---

## Seam 4: Agent Roles (`AI_agents/project_team/*.md`)

### What EXISTS Today

**16 role definition files** in `AI_agents/project_team/`:

| File | Role Type (CamelCase) | Category | Spawned By |
|------|----------------------|----------|------------|
| `COORDINATOR.md` | Coordinator | Orchestration | Skill directly (top-level) |
| `COMPOSABILITY.md` | Composability | Leadership | Coordinator (Phase 2, always) |
| `TERMINOLOGY_GUARDIAN.md` | TerminologyGuardian | Leadership | Coordinator (Phase 2, always) |
| `SKEPTIC.md` | Skeptic | Leadership | Coordinator (Phase 2, always) |
| `USER_ALIGNMENT.md` | UserAlignment | Review | Coordinator (Phase 2, always) |
| `IMPLEMENTER.md` | Implementer | Implementation | Coordinator (Phase 4, per-file) |
| `TEST_ENGINEER.md` | TestEngineer | Implementation | Coordinator (Phase 5) |
| `UI_DESIGNER.md` | UIDesigner | Implementation | Coordinator (Phase 3, if UI-heavy) |
| `RESEARCHER.md` | Researcher | Advisory | Coordinator (Phase 2, conditional) |
| `LAB_NOTEBOOK.md` | LabNotebook | Advisory | Coordinator (Phase 2, conditional) |
| `BINARY_PORTABILITY.md` | BinaryPortability | Advisory | Coordinator (conditional) |
| `SYNC_COORDINATOR.md` | SyncCoordinator | Advisory | Coordinator (conditional) |
| `PROJECT_INTEGRATOR.md` | ProjectIntegrator | Integration | Coordinator |
| `GIT_SETUP.md` | GitSetup | Setup | Coordinator (Phase 1) |
| `COORDINATOR_WATCH.md` | CoordinatorWatch | Meta | (observer) |
| `MEMORY_LAYOUT.md` | MemoryLayout | Reference | (not spawned — documentation) |
| `PROJECT_TYPES.md` | ProjectTypes | Reference | (not spawned — documentation) |

**Naming convention:**
- **Filename:** `UPPER_SNAKE_CASE.md` — e.g., `TEST_ENGINEER.md`
- **Type string:** `CamelCase` — e.g., `TestEngineer`
- **Transform:** CamelCase → UPPER_SNAKE via two-pass regex:
  1. Insert `_` before uppercase ending a run: `UIDesigner` → `UI_Designer`
  2. Insert `_` before uppercase after lowercase/digit: `UI_Designer` → `UI_DESIGNER`
  3. Uppercase the whole string
- This transform is implemented in `generate_hooks.py` (the `spawn_type_defined` detector) and documented in the guardrails README.

### The Contract: What Must a Role File Contain?

By reading COORDINATOR.md's spawn patterns and examining role files, the **implicit contract** is:

#### Required Elements

| Element | Why Required | Evidence |
|---------|-------------|----------|
| **Role title** (H1 heading) | Coordinator's spawn prompt says "You are {RoleName}. Read your role file..." — the agent needs to know what it is | All role files start with `# <Role Name>` |
| **Responsibility statement** | Defines what this agent does vs. other agents | All files have a "Your Role" or equivalent section |
| **Output format** | Agents must produce structured output that Coordinator and other agents can consume | Most files define explicit output templates |
| **Interaction table** | Defines relationship with other agents (who this role receives from, hands off to) | Present in Implementer, Researcher, Skeptic |
| **Authority bounds** | What this agent CAN and CANNOT do — prevents scope creep | Present in Researcher ("You recommend. Others decide."), Skeptic, UserAlignment |

#### Strongly Recommended Elements

| Element | Why Recommended | Evidence |
|---------|----------------|----------|
| **"When to Activate" section** | Tells Coordinator when to spawn this role | Researcher has explicit phase table; LabNotebook has trigger table |
| **Rules / Red Flags section** | Defines anti-patterns specific to this role | Researcher has "Research Smells", Skeptic has "Red Flags" |
| **Phase-specific behavior** | How the role adapts across project phases | Researcher maps phases to research activities |
| **Core Principle / Insight** | The philosophical basis — helps the agent make judgment calls | Skeptic: "Complex code hides bugs"; LabNotebook: "Computational experiments are as real as bench experiments" |

#### NOT Required (But Common)

| Element | Status | Notes |
|---------|--------|-------|
| Specific code examples | Optional | Implementer doesn't have them; Composability has extensive examples |
| Workflow steps | Varies | Implementer has 5-step workflow; Skeptic has 4 questions; Researcher has tiered source hierarchy |
| Key terms table | Optional | Coordinator has one; most roles don't |

### How the Coordinator Spawns a Role

From COORDINATOR.md Phase 2, the spawn pattern is:

```
spawn_agent(
  name="<InstanceName>",         # Unique instance ID (e.g., "Composability", "Implementer_1")
  type="<RoleName>",             # CamelCase role type (e.g., "Composability", "Implementer")
  prompt="You are <RoleName>. Read your role file: {monorepo_root}/AI_agents/project_team/<UPPER_SNAKE>.md.
          Project state: {project_state}/.
          Read {project_state}/userprompt.md for context.
          Phase task: <specific task description>.
          Write findings to {project_state}/specification/<output_file>.md.
          Report to: Coordinator"
)
```

**Key observations:**
1. The `type` parameter sets `CLAUDE_AGENT_ROLE` env var — this is what guardrails match against
2. The `name` parameter sets `CLAUDE_AGENT_NAME` env var — used for routing and ack tokens
3. For multi-instance roles (Implementer), `name` is numbered (`Implementer_1`, `Implementer_2`) while `type` stays `Implementer`
4. The spawn prompt always includes: role identity, role file path, project state path, specific task, output location, reporting chain
5. **All paths must be absolute** — subagents cannot resolve relative paths

### How Someone Adds a New Role — Step by Step

Based on the existing conventions and the guardrails README "How to Add a Role" section:

**Step 1: Create the role definition file**
```
AI_agents/project_team/<UPPER_SNAKE>.md
```
Example: Adding a "DataValidator" role → create `DATA_VALIDATOR.md`

**Minimum viable role file:**
```markdown
# Data Validator

You verify data integrity, check for drift, and ensure datasets meet quality standards.

## Your Role

You are responsible for data quality assurance. You:
1. Validate input data against schemas
2. Check for data drift between versions
3. Verify statistical properties match expectations
4. Flag anomalies for human review

## Output Format

```markdown
## Data Validation: [Dataset Name]

### Checks Performed
- [Check name]: [PASS/FAIL] — [details]

### Anomalies Found
- [Description and severity]

### Recommendation
[Pass / Fail with remediation steps]
```

## Interaction with Other Agents

| Agent | Your Relationship |
|-------|-------------------|
| **Coordinator** | Receives validation requests, reports results |
| **Implementer** | Validate data used by implementation |
| **TestEngineer** | Provide test datasets and validation criteria |
| **Skeptic** | Your validations feed into correctness review |

## Authority

- You CAN flag data quality issues and recommend rejection
- You CAN request re-collection or re-processing of data
- You CANNOT make implementation decisions based on data findings
- You CANNOT modify data — only validate and report
```

**Step 2: Add to guardrail rules (if role needs permissions)**
```yaml
# In rules.yaml — add to allow: or block: lists as needed
- id: R30
  name: data-validator-no-write-data
  trigger: [PreToolUse/Write, PreToolUse/Edit]
  enforcement: deny
  detect:
    type: regex_match
    pattern: '/data/'
    target: file_path
  block: [DataValidator]
  message: "[GUARDRAIL DENY R30] DataValidator cannot write to data/ directories.\nInstead: Report findings to Coordinator for Implementer to act on."
```

**Step 3: Regenerate hooks**
```bash
python3 .claude/guardrails/generate_hooks.py
```

**Step 4: Add spawn instruction to COORDINATOR.md (or spawn dynamically)**

Option A — Add to COORDINATOR.md's Phase 2 conditional spawns:
```markdown
- **Spawn DataValidator** if the project involves: datasets, data pipelines, ML training data,
  or any work where data quality directly affects outcomes.
  - name: `DataValidator`
  - prompt: `You are DataValidator. Read your role file: {monorepo_root}/AI_agents/project_team/DATA_VALIDATOR.md. ...`
```

Option B — Coordinator spawns dynamically based on project needs (already happens for Researcher, LabNotebook).

**Step 5: Add to README.md roster**
```markdown
| **Data Validator** | `DATA_VALIDATOR.md` | Advisory — data quality verification |
```

**Step 6: Validate**
- `spawn_type_defined` rule will verify that `type="DataValidator"` has a corresponding `DATA_VALIDATOR.md`
- If the file doesn't exist, the guardrail fires a warning at spawn time

### Connection to Guardrails

The agent role system connects to guardrails through three mechanisms:

**1. Spawn-time validation (`spawn_type_defined`)**
When `spawn_agent(type="SomeRole")` is called, the guardrail:
- Converts `SomeRole` → `SOME_ROLE` via two-pass regex
- Searches `AI_agents/**/<UPPER_SNAKE>.md`
- If not found → fires warning (role has no definition file)
- This prevents spawning agents with undefined/typo'd role types

**2. Runtime permission matching (`allow:` / `block:` in rules.yaml)**
- `block: [Implementer]` → rule fires only for agents spawned with `type="Implementer"`
- `allow: [Implementer, TestEngineer]` → rule fires for everyone EXCEPT these roles
- Role groups (`Agent`, `TeamAgent`, `Subagent`) provide broader scoping
- Matching uses `CLAUDE_AGENT_ROLE` env var (set from `type=` parameter)

**3. The Coordinator special case**
- Coordinator has no `CLAUDE_AGENT_ROLE` — it's the top-level session
- Identified via session marker: `get_my_role()` returns `"Coordinator"` when session marker maps the agent name
- Can be targeted with `block: [Coordinator]` in rules

### What's Missing / Gaps for Plugin System

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| **No formal schema for role files** | New roles are written by convention, not validation. A role file could be missing key sections and nothing catches it. | Define a lightweight schema or checklist (required sections) that a linter can validate |
| **No role metadata beyond the .md file** | No version, no dependencies, no "requires plugins" declaration. A role can reference tools or databases that don't exist in the project. | Add a frontmatter block (YAML in markdown) or companion `role.yaml` with metadata |
| **Coordinator hardcodes spawn list** | Adding a new role requires editing COORDINATOR.md. Not plugin-friendly. | Plugin-contributed roles should be auto-discoverable — Coordinator reads a registry of available roles from plugin manifests |
| **No role composition** | Can't say "DataValidator extends Skeptic with additional data checks." Each role is independent. | For v1 this is fine. Role composition would add complexity without clear benefit yet. |
| **No per-role tool restrictions beyond rules.yaml** | A role file says "You CANNOT write code" but this is only enforced if a matching guardrail rule exists. | Consider: should role files declare their own tool restrictions that auto-generate guardrail rules? |

### Recommended Plugin Interface for Agent Roles

```yaml
# Plugin manifest declaring a new agent role
# plugins/bioinformatics-agents/plugin.yaml
name: bioinformatics-agents
version: "1.0"
contributes:
  agent_roles:
    - type: GenomicsAnalyst
      file: roles/GENOMICS_ANALYST.md
      category: domain-specialist
      spawn_condition: "project involves genomics, sequencing, or bioinformatics"
      guardrail_rules:
        - id: BIO01
          name: genomics-no-delete-fastq
          trigger: PreToolUse/Bash
          enforcement: deny
          detect:
            type: regex_match
            pattern: '\brm\b.*\.(fastq|fq|bam|sam)'
          block: [GenomicsAnalyst]
          message: "[GUARDRAIL DENY BIO01] Cannot delete sequencing data files."
    - type: StatisticsReviewer
      file: roles/STATISTICS_REVIEWER.md
      category: advisory
      spawn_condition: "project involves statistical analysis or hypothesis testing"
```

**How this works in the plugin system:**
1. Plugin install copies `roles/*.md` to `AI_agents/project_team/` (or symlinks)
2. Plugin's guardrail rules merge into `rules.yaml` (or a `rules.d/` include directory)
3. `generate_hooks.py` is re-run
4. Coordinator discovers available roles from plugin manifests → knows when to spawn them
5. `spawn_type_defined` validation works automatically (files are in the expected location)

---

## Seam 5: Guardrail Rules (`.claude/guardrails/rules.yaml`)

### What EXISTS Today — Already Well-Codified

The guardrails framework is the **most thoroughly documented seam** in the project. The README covers:

**Architecture:**
- Single `rules.yaml` file = source of truth for all rules
- `generate_hooks.py` = code generator that emits self-contained hook scripts
- `role_guard.py` = runtime library (role resolution, permission checking, ack tokens)
- Generated hooks live in `hooks/` directory (gitignored, regenerated)

**Rule anatomy (from `rules.yaml.example` — 23 synthetic test rules covering every mechanism):**

```yaml
- id: FW01                           # Unique rule identifier
  name: fw-regex-match-deny          # Human-readable name
  trigger: PreToolUse/Bash           # When to intercept (tool event)
  enforcement: deny                  # log | warn | deny | inject
  detect:
    type: regex_match                # regex_match | regex_miss | always | spawn_type_defined
    pattern: '\bdangerous_cmd\b'     # Regex pattern (string or list for OR)
    field: color                     # (optional) MCP tool field extraction
    target: file_path                # (optional) for Write/Edit/Read — which field to match
    flags: [IGNORECASE]              # (optional) Python regex flags
    exclude_contexts: [python_dash_c] # (optional) Strip contexts before matching
    conditions:                      # (optional) Additional conditions
      path_is_root: true
  exclude_if_matches: '\bbypass_ok\b'  # (optional) Suppression pattern
  allow: [SpecialRole]               # (optional) Exempt these roles — XOR with block:
  block: [Coordinator]               # (optional) Target these roles — XOR with allow:
  message: "[FW01] dangerous_cmd is denied."  # Inline message (or use messages/<ID>.md)
  enabled: false                     # (optional) Disable without removing
```

**Enforcement levels:**

| Level | Exit Code | Agent Experience | Use Case |
|-------|-----------|------------------|----------|
| `log` | 0 (allow) | Invisible — recorded to `hits.jsonl` only | Monitoring, hardening path |
| `warn` | 2 (reject) | Message + ack instructions | Soft guardrails, awareness |
| `deny` | 2 (reject) | Message, no ack path | Hard stops |
| `inject` | 0 (allow) | Modifies tool input silently | Input normalization |

**Detection types:**

| Type | Fires When | Valid Triggers |
|------|-----------|----------------|
| `regex_match` | Pattern matches command/field/file_path | All |
| `regex_miss` | Pattern does NOT match | All |
| `always` | Every invocation (requires allow/block) | All |
| `spawn_type_defined` | Agent type has no definition file | `mcp__chic__spawn_agent` only |

**Role scoping:**

| Scope | Syntax | When Active |
|-------|--------|-------------|
| No `allow:`/`block:` | (omitted) | Universal — fires for all agents always |
| `block: [Agent]` | Group | All agents with `CLAUDE_AGENT_NAME` set |
| `block: [TeamAgent]` | Group | Coordinator + sub-agents in team mode |
| `block: [Subagent]` | Group | Sub-agents only (not Coordinator) in team mode |
| `block: [Implementer]` | Named | Only agents with `CLAUDE_AGENT_ROLE=Implementer` |
| `allow: [Implementer]` | Named exempt | Everyone EXCEPT Implementer |

### The Extension Contract

From the README's "How to Add a Rule" section, the contract is:

**Step 1:** Add entry to `rules.yaml` under `rules:` with:
- Unique `id` (convention: `R01`–`R99` for project rules, `FW01`–`FW99` for framework test rules)
- Valid `trigger` (must map to a hook file in `TRIGGER_TO_FILE`)
- Valid `enforcement` (one of: `log`, `warn`, `deny`, `inject`)
- Valid `detect.type` (one of: `regex_match`, `regex_miss`, `always`, `spawn_type_defined`)
- Either `allow:` or `block:` (not both) for role-gated rules
- `message:` for inline messages, or create `messages/<ID>.md` for longer text

**Step 2:** For deny-level messages, include "Instead:" line with remediation guidance.

**Step 3:** Run `python3 .claude/guardrails/generate_hooks.py` to regenerate hooks.

**Step 4:** Verify by piping test input to the generated hook.

**Hardening path:** Start at `log` or `warn`, monitor `hits.jsonl`, promote to `deny` with confidence.

### How Rules Connect to Roles

The connection flows through three runtime env vars:

```
spawn_agent(name="Impl_1", type="Implementer")
    ↓
CLAUDE_AGENT_NAME = "Impl_1"        → identity (routing, ack tokens)
CLAUDE_AGENT_ROLE = "Implementer"   → permission matching
CLAUDECHIC_APP_PID = "12345"        → session (team mode detection)
    ↓
Hook fires → role_guard.check_role():
    1. Read CLAUDE_AGENT_ROLE → "Implementer"
    2. Check session marker → team mode active?
    3. For each allow:/block: entry in matched rules:
       - "Implementer" exact match? → yes → applies
       - "Agent" group? → yes (has CLAUDE_AGENT_NAME)
       - "TeamAgent" group? → yes if team mode
       - "Subagent" group? → yes if team mode AND not Coordinator
    4. Return: allow (exit 0) or reject (exit 2)
```

**Special case — Coordinator:**
- No `CLAUDE_AGENT_ROLE` set (it's the top-level session agent)
- `get_my_role()` identifies it via session marker mapping
- Can be targeted with `block: [Coordinator]`

### What's Missing from Existing Docs for Contributors

The README is good. Based on thorough reading, here are gaps a contributor would encounter:

| Gap | What a Contributor Needs | Current State |
|-----|------------------------|---------------|
| **No rule ID conventions for plugins** | If plugins contribute rules, ID collisions are possible. `R01` from plugin A vs. `R01` from plugin B. | No convention. Recommend: plugin rules use namespaced IDs (e.g., `BIO01`, `HPC01`) |
| **No `rules.d/` include mechanism** | Currently all rules must be in one `rules.yaml`. Plugins can't contribute rules without modifying the central file. | `generate_hooks.py` reads one file. Recommend: add `rules.d/*.yaml` glob support |
| **Trigger list not documented in README** | The valid triggers are in `generate_hooks.py` (`TRIGGER_TO_FILE` dict) but not in the README. A contributor has to read the source. | Document available triggers in README |
| **MCP trigger naming not obvious** | Custom MCP triggers (e.g., `mcp__chic__spawn_agent`) follow a `mcp__<server>__<tool>` convention. Not documented. | Add a section on custom trigger naming |
| **No versioning on rules.yaml** | `catalog_version` exists but isn't validated or used for compatibility checking. | For plugins, version compatibility matters |
| **`ack_ttl_seconds` only documented in code** | The README mentions TTL in the ack flow section but doesn't explain how to tune it or what values are reasonable. | Add tuning guidance (default 60s, range 30-300s) |
| **No guidance on enforcement level selection** | README says "start at log/warn, harden to deny" but doesn't explain when each level is appropriate for different rule types. | Add a decision table |

### Recommended Extension Points for Plugin System

**1. `rules.d/` include directory**

The most important change for plugin composability:

```
.claude/guardrails/
├── rules.yaml              # Core project rules
├── rules.d/                # Plugin-contributed rules (NEW)
│   ├── bioinformatics.yaml # From bioinformatics-agents plugin
│   ├── hpc.yaml            # From HPC plugin
│   └── scientific.yaml     # From scientific-computing plugin
├── generate_hooks.py       # Modified to glob rules.d/*.yaml
└── ...
```

**generate_hooks.py change:** Before validation, merge all `rules.d/*.yaml` into the rule set. Each file follows the same `rules:` schema. Plugin install drops a YAML file; plugin removal deletes it; `generate_hooks.py` re-run regenerates hooks.

**ID namespace convention:**
- `R01`–`R99`: Core project rules
- `FW01`–`FW99`: Framework test rules (reserved)
- `S01`–`S99`: Spawn validation rules
- `<PLUGIN_PREFIX>01`–`<PLUGIN_PREFIX>99`: Plugin rules (e.g., `BIO01`, `HPC01`, `SCI01`)

**2. Role file auto-discovery from plugins**

Instead of hardcoding role files in `AI_agents/project_team/`:

```
AI_agents/
├── project_team/           # Core roles (always available)
│   ├── COORDINATOR.md
│   ├── IMPLEMENTER.md
│   └── ...
└── plugins/                # Plugin-contributed roles (NEW)
    ├── bioinformatics/
    │   ├── GENOMICS_ANALYST.md
    │   └── STATISTICS_REVIEWER.md
    └── hpc/
        └── CLUSTER_OPERATIONS.md
```

**`spawn_type_defined` change:** Currently searches `AI_agents/**/<UPPER_SNAKE>.md` — this glob already covers subdirectories, so plugin roles placed under `AI_agents/plugins/<name>/` would be found automatically. No code change needed.

**3. Plugin manifest declares guardrail requirements**

```yaml
# plugin.yaml
contributes:
  guardrail_rules: rules/guardrails.yaml   # Installed to rules.d/
  agent_roles:
    - type: GenomicsAnalyst
      file: roles/GENOMICS_ANALYST.md      # Installed to AI_agents/plugins/<name>/
requires:
  guardrails: true                          # This plugin needs the guardrails framework
```

### Worked Example: Adding a Complete Plugin-Contributed Role + Rules

**Scenario:** An HPC plugin contributes a `ClusterOperations` agent that manages SLURM jobs.

**Plugin file structure:**
```
plugins/hpc/
├── plugin.yaml
├── roles/
│   └── CLUSTER_OPERATIONS.md
└── rules/
    └── hpc_guardrails.yaml
```

**`plugin.yaml`:**
```yaml
name: hpc
version: "1.0"
description: "HPC/SLURM integration for scientific computing"
contributes:
  agent_roles:
    - type: ClusterOperations
      file: roles/CLUSTER_OPERATIONS.md
      category: infrastructure
      spawn_condition: "project involves HPC, SLURM, or cluster computing"
  guardrail_rules: rules/hpc_guardrails.yaml
  commands:
    - name: slurm-submit
      script: commands/slurm_submit.sh
```

**`roles/CLUSTER_OPERATIONS.md`:**
```markdown
# Cluster Operations

You manage HPC cluster interactions: SLURM job submission, resource allocation, and compute monitoring.

## Your Role
1. Write and validate SLURM job scripts
2. Monitor job status and resource usage
3. Manage data transfers between local and cluster storage
4. Advise on resource allocation (GPUs, memory, walltime)

## Output Format
[...]

## Interaction with Other Agents
| Agent | Your Relationship |
|-------|-------------------|
| **Coordinator** | Receives cluster tasks, reports job status |
| **Implementer** | Provide SLURM wrappers for compute-intensive code |
| **TestEngineer** | Run test jobs on cluster, report results |

## Authority
- You CAN submit, cancel, and monitor SLURM jobs
- You CAN modify SLURM scripts and resource requests
- You CANNOT modify scientific code — only cluster infrastructure
- You CANNOT access data outside the project directory
```

**`rules/hpc_guardrails.yaml`:**
```yaml
rules:
  - id: HPC01
    name: cluster-ops-no-scancel-all
    trigger: PreToolUse/Bash
    enforcement: deny
    detect:
      type: regex_match
      pattern: '\bscancel\s+(-u|--user)\b'
    block: [ClusterOperations]
    message: "[GUARDRAIL DENY HPC01] Cannot cancel all jobs for a user.\nInstead: Cancel specific job IDs only."

  - id: HPC02
    name: cluster-ops-warn-large-allocation
    trigger: PreToolUse/Bash
    enforcement: warn
    detect:
      type: regex_match
      pattern: '--gres=gpu:(\d+)'
      flags: [IGNORECASE]
    block: [ClusterOperations]
    message: "[GUARDRAIL WARN HPC02] Large GPU allocation detected. Verify resource request is appropriate."
```

**Install flow:**
1. Plugin install copies `roles/CLUSTER_OPERATIONS.md` → `AI_agents/plugins/hpc/CLUSTER_OPERATIONS.md`
2. Plugin install copies `rules/hpc_guardrails.yaml` → `.claude/guardrails/rules.d/hpc.yaml`
3. `generate_hooks.py` re-runs, picks up new rules
4. `spawn_type_defined` finds `CLUSTER_OPERATIONS.md` via `AI_agents/**/*.md` glob
5. Coordinator reads plugin manifest → knows `ClusterOperations` exists and when to spawn it

---

## Cross-Seam Analysis: How Roles and Guardrails Interconnect

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Plugin Manifest                               │
│   plugin.yaml                                                        │
│   ├── contributes.agent_roles[].type: "ClusterOperations"           │
│   ├── contributes.agent_roles[].file: roles/CLUSTER_OPERATIONS.md   │
│   └── contributes.guardrail_rules: rules/hpc_guardrails.yaml        │
└────────┬──────────────────────────────┬──────────────────────────────┘
         │                              │
         ▼                              ▼
┌────────────────────┐     ┌──────────────────────────────┐
│   AI_agents/       │     │  .claude/guardrails/          │
│   plugins/hpc/     │     │  rules.d/hpc.yaml             │
│   CLUSTER_OPS.md   │     │  (merged by generate_hooks)   │
└────────┬───────────┘     └──────────┬───────────────────┘
         │                            │
         │ spawn_type_defined         │ generate_hooks.py
         │ validates at spawn         │ emits hook scripts
         │                            │
         ▼                            ▼
┌────────────────────┐     ┌──────────────────────────────┐
│  Coordinator       │     │  hooks/bash_guard.sh          │
│  spawns agent:     │     │  (contains HPC01, HPC02       │
│  type="Cluster     │     │   rule checks)                │
│  Operations"       │     └──────────┬───────────────────┘
└────────┬───────────┘                │
         │                            │
         ▼                            ▼
┌────────────────────────────────────────────────────────────────┐
│  Runtime: Agent with CLAUDE_AGENT_ROLE="ClusterOperations"    │
│  → hook intercepts tool calls                                  │
│  → role_guard.check_role() matches "ClusterOperations"        │
│  → block:[ClusterOperations] rules fire                        │
│  → hits.jsonl logs the match                                   │
└────────────────────────────────────────────────────────────────┘
```

### Key Design Invariants (Must Preserve)

1. **CamelCase type ↔ UPPER_SNAKE filename is bidirectional and deterministic.** Any code that resolves role types must use the same two-pass regex. Do not create a second transform.

2. **`allow:` XOR `block:` — never both.** `generate_hooks.py` enforces this at generation time. Plugin rules must follow the same constraint.

3. **Role names are case-sensitive.** `type="implementer"` ≠ `type="Implementer"`. Document this prominently for plugin authors.

4. **Reserved groups (`Agent`, `TeamAgent`, `Subagent`) cannot be used as type names.** Enforced at runtime by `_ROLE_GROUPS` frozenset in `role_guard.py`.

5. **Framework files are upstream-owned.** `generate_hooks.py`, `role_guard.py`, `README.md`, `rules.yaml.example` belong to AI_PROJECT_TEMPLATE. Plugin rules go in `rules.d/`, not by patching `generate_hooks.py`.

6. **The `AI_agents/**/<UPPER_SNAKE>.md` glob is the source of truth for role existence.** `spawn_type_defined` uses this. Plugins must place role files where this glob finds them.

---

## Summary of Recommendations

### For Seam 4 (Agent Roles):

1. **Define a minimal role file schema** — required H1, responsibility, output format, interaction table, authority bounds. Optional: a YAML frontmatter block for machine-readable metadata.
2. **Support plugin-contributed roles** via `AI_agents/plugins/<name>/<UPPER_SNAKE>.md` — already works with existing `rglob` pattern.
3. **Auto-discoverable role registry** — Coordinator should read plugin manifests to know what roles are available and when to spawn them, rather than hardcoding spawn lists.
4. **Consider role metadata frontmatter** for version, category, spawn conditions, and dependency declarations.

### For Seam 5 (Guardrail Rules):

1. **Add `rules.d/` include directory** — the single highest-impact change for plugin composability. `generate_hooks.py` merges `rules.d/*.yaml` before validation.
2. **Namespace plugin rule IDs** — `<PLUGIN_PREFIX>01` convention prevents collisions.
3. **Document available triggers** in README (currently only in `TRIGGER_TO_FILE` dict in source).
4. **Add enforcement level selection guidance** — when to use `log` vs `warn` vs `deny`.
5. **Document `ack_ttl_seconds` tuning** in README.
