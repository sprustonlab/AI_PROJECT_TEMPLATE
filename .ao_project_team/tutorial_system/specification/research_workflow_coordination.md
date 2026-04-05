# Workflow Coordination Systems: Phase/Step Declaration and Validation Patterns

**Requested by:** Coordinator
**Date:** 2026-04-04
**Tier of best source found:** T1 (Official documentation and source code for all 7 systems)

## Query

How do real-world agent frameworks and workflow systems declare and validate their phases/steps/states? What's the industry standard pattern for "validate references to workflow phases at build time"?

---

## 1. LangGraph — Graph Nodes and Edges

### Declaration

Nodes registered on a `StateGraph` via `add_node()`, stored in an explicit `dict[str, StateNodeSpec]`:

```python
builder = StateGraph(MyState)
builder.add_node("chat", chat_function)
builder.add_node("tools", tool_function)
builder.add_edge(START, "chat")
builder.add_edge("chat", "tools")
builder.add_conditional_edges("tools", routing_fn, {True: "chat", False: END})
graph = builder.compile()
```

### Validation

**Two-phase: definition-time + compile-time.**

| Check | When | Error |
|-------|------|-------|
| Duplicate node name | `add_node()` call | `ValueError: Node 'X' already present` |
| Reserved name (START/END) | `add_node()` call | `ValueError` |
| Edge references non-existent node | `add_edge()` call | `ValueError: Need to add_node 'X' first` |
| No entry point from START | `compile()` | `ValueError: Graph must have an entrypoint` |
| Orphaned/unreachable nodes | `compile()` | Warning or error at compile |

### Summary

| Property | Value |
|----------|-------|
| Registry | **Explicit** — `dict[str, NodeSpec]` |
| Validation timing | **Definition-time** (immediate on add_edge) + **compile-time** (structural) |
| Invalid reference | **Immediate ValueError** — cannot even build the graph |
| Reference style | String names |

---

## 2. CrewAI — Tasks and Crews

### Declaration

Tasks are Pydantic `BaseModel` instances. Dependencies via `context=` (list of Task objects):

```python
research_task = Task(description="Research AI trends", expected_output="List of trends", agent=researcher)
analysis_task = Task(description="Analyze findings", expected_output="Report", agent=analyst, context=[research_task])
crew = Crew(agents=[researcher, analyst], tasks=[research_task, analysis_task], process=Process.sequential)
```

### Validation

**Crew instantiation time** (Pydantic validators):

| Check | When | Error |
|-------|------|-------|
| Context references future task (forward ref) | `Crew.__init__()` | `PydanticCustomError` |
| Missing agent in sequential mode | `Crew.__init__()` | `PydanticCustomError` |
| Missing manager in hierarchical mode | `Crew.__init__()` | `PydanticCustomError` |
| Conditional task as first task | `Crew.__init__()` | `PydanticCustomError` |
| Context task not in crew's task list | **Not caught** | Silent — output unavailable at runtime |

### Summary

| Property | Value |
|----------|-------|
| Registry | **No registry** — list of objects passed to Crew |
| Validation timing | **Instantiation-time** (Pydantic validators) |
| Invalid reference | Forward refs caught; missing-from-list refs **silent** |
| Reference style | Direct Python object references |

---

## 3. Apache Airflow — DAGs and Tasks

### Declaration

Three styles: context manager, constructor, or `@dag` decorator. Dependencies via bitshift operators:

```python
with DAG("my_dag", start_date=datetime(2021, 1, 1), schedule="@daily") as dag:
    extract = EmptyOperator(task_id="extract")
    transform = EmptyOperator(task_id="transform")
    load = EmptyOperator(task_id="load")
    extract >> transform >> load
```

### Validation

**Parse-time** (when `DagBag` loads DAG files) + **runtime**:

| Check | When | Error |
|-------|------|-------|
| Duplicate task_id | `DAG.add_task()` (parse time) | `DuplicateTaskIdFound` |
| Cycle in DAG | `DAG.test_cycle()` (parse time) | `AirflowDagCycleException` |
| Undefined variable in `>>` | Parse time (Python) | `NameError` |
| task_id lookup for non-existent task | Runtime | `TaskNotFound` / `AirflowException` |
| Import errors in DAG files | Parse time | Collected in `DagBag.import_errors` |

### Summary

| Property | Value |
|----------|-------|
| Registry | **Implicit** — `task_dict` built as tasks are added to DAG |
| Validation timing | **Parse-time** (cycle detection, duplicate IDs) + **runtime** (task lookups) |
| Invalid reference | Depends on type: `NameError` for Python refs, `TaskNotFound` for ID lookups |
| Reference style | Python objects for `>>`, string task_ids for API/cross-DAG |

---

## 4. Dagster — Ops, Assets, and Jobs

### Declaration

Two abstractions: assets (data-centric) and ops/graphs (compute-centric). Dependencies inferred from function signatures:

```python
@dg.asset
def raw_data() -> pd.DataFrame:
    return pd.read_csv("data.csv")

@dg.asset
def clean_data(raw_data: pd.DataFrame) -> pd.DataFrame:
    return raw_data.dropna()  # dependency inferred from parameter name
```

### Validation

**Definition/import time** — the most aggressive of all systems:

| Check | When | Error |
|-------|------|-------|
| Unmapped graph input | Definition (import) | `DagsterInvalidDefinitionError` |
| Unresolved op input | Definition (import) | `DagsterInvalidDefinitionError` |
| Invalid node in dependency dict | Definition (import) | `DagsterInvalidDefinitionError` |
| Conflicting asset keys/job names | `Definitions.validate_loadable()` | `DagsterInvalidDefinitionError` |
| Op input/output type mismatch | Runtime | `DagsterTypeCheckError` |

Dagster provides an explicit test helper:
```python
def test_definitions_valid():
    dg.Definitions.validate_loadable(defs)  # catches all definition errors
```

### Summary

| Property | Value |
|----------|-------|
| Registry | **Explicit** — `Definitions` object with `validate_loadable()` |
| Validation timing | **Import-time** (earliest possible) |
| Invalid reference | **Immediate DagsterInvalidDefinitionError** |
| Reference style | Function parameter names (assets) or `DependencyDefinition` (ops) |

---

## 5. Prefect — Flows and Tasks

### Declaration

Decorator-based, no static graph. Dependencies are implicit via Python data flow:

```python
@task
def extract(): return data
@task
def transform(raw): return processed

@flow
def pipeline():
    raw = extract()
    result = transform(raw)
```

### Validation

**Runtime only** — no static graph exists to validate:

| Check | When | Error |
|-------|------|-------|
| Undefined task reference | Runtime (Python execution) | `NameError` |
| Invalid `wait_for` type | Runtime (`submit()`) | `TypeError` |
| Parameter type mismatch | Runtime (flow entry) | Pydantic `ValidationError` |
| Task called outside flow | Runtime | Prefect context error |

### Summary

| Property | Value |
|----------|-------|
| Registry | **No registry** — pure Python execution |
| Validation timing | **Runtime only** |
| Invalid reference | Python `NameError` |
| Reference style | Python function calls / return values |

---

## 6. GitHub Actions — Jobs and Dependencies

### Declaration

Jobs as YAML keys, dependencies via `needs:`:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps: [...]
  test:
    needs: build
    runs-on: ubuntu-latest
    steps: [...]
  deploy:
    needs: [build, test]
    runs-on: ubuntu-latest
    steps: [...]
```

### Validation

**Parse-time** — before any job executes:

| Check | When | Error |
|-------|------|-------|
| `needs:` references non-existent job ID | Parse time | `Job 'X' depends on unknown job 'Y'` — **entire workflow rejected** |
| Cycle in job dependencies | Parse time | Workflow rejected |
| Invalid job ID characters | Parse time | Workflow rejected |

**Key behavior:** If ANY validation fails, NO jobs run. The entire workflow is marked invalid.

### Summary

| Property | Value |
|----------|-------|
| Registry | **Implicit** — job IDs are YAML keys under `jobs:` |
| Validation timing | **Parse-time** (before any runner allocated) |
| Invalid reference | **Entire workflow rejected**, no jobs execute |
| Reference style | String job IDs |

---

## 7. Kubernetes — Resource References

### Declaration

Resources reference each other via **name strings** and **label selectors**:

```yaml
# Pod referencing a ConfigMap
env:
  - name: DB_HOST
    valueFrom:
      configMapKeyRef:
        name: my-config    # string reference
        key: database_host
        optional: false
```

### Validation

**No cross-resource validation at apply time.** Each resource validated in isolation (schema only):

| Check | When | Error |
|-------|------|-------|
| Schema correctness (field types, required) | `kubectl apply` | API server rejection |
| Selector matches template labels (within one resource) | `kubectl apply` | API server rejection |
| Referenced ConfigMap/Secret exists | **Runtime** (container start) | `CreateContainerConfigError` |
| Service selector matches Pods | **Runtime** (eventual) | Silent — empty Endpoints |
| Ingress backend Service exists | **Runtime** (request time) | 503 errors |

**Key behavior:** `kubectl apply` succeeds. Failures surface **later** when controllers try to reconcile.

### Summary

| Property | Value |
|----------|-------|
| Registry | **Implicit** — resources exist in etcd, references are string names |
| Validation timing | **Runtime** (eventual consistency) |
| Invalid reference | Resource created successfully; failure surfaces at reconciliation |
| Reference style | String names, label selectors |

---

## 8. Terraform — Resource References

### Declaration

All resources declared in `.tf` files. References via typed expressions:

```hcl
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "web" {
  vpc_id     = aws_vpc.main.id    # typed reference → creates DAG edge
  cidr_block = "10.0.1.0/24"
}
```

### Validation

**Three-stage pipeline:**

| Check | `validate` | `plan` | `apply` |
|-------|-----------|--------|---------|
| Reference to undeclared resource | **YES — hard error** | YES | N/A |
| Invalid attribute type | YES | YES | N/A |
| Missing required argument | YES | YES | N/A |
| Cloud resource doesn't exist (data source) | No | YES | N/A |
| Variable validation failure | No | YES | N/A |
| Precondition failure | No | YES | N/A |
| Postcondition failure | No | No | YES |

**Key behavior:** `terraform validate` catches ALL reference errors with zero cloud API calls. Error:
```
Error: Reference to undeclared resource
A managed resource "aws_vpc" "nonexistent" has not been declared in the root module.
```

### Summary

| Property | Value |
|----------|-------|
| Registry | **Explicit** — all resources declared in `.tf` files |
| Validation timing | **Validate-time** (static analysis, pre-plan) |
| Invalid reference | **Hard error at validate** — nothing proceeds |
| Reference style | Typed expressions: `resource_type.name.attribute` |

---

## Cross-System Comparison Matrix

| System | Registry Type | Validation Timing | Invalid Ref Behavior | Reference Style |
|--------|--------------|-------------------|---------------------|----------------|
| **LangGraph** | Explicit dict | Definition + compile | Immediate ValueError | String names |
| **CrewAI** | No registry (list) | Instantiation | Partial (forward refs only) | Object refs |
| **Airflow** | Implicit (task_dict) | Parse-time | DuplicateTaskId / NameError | Objects + string IDs |
| **Dagster** | Explicit (Definitions) | Import-time | Immediate error | Param names / DependencyDef |
| **Prefect** | No registry | Runtime only | Python NameError | Function calls |
| **GitHub Actions** | Implicit (YAML keys) | Parse-time | Entire workflow rejected | String IDs |
| **Kubernetes** | Implicit (etcd) | Runtime (eventual) | Silent / delayed failure | String names + selectors |
| **Terraform** | Explicit (.tf files) | Validate (static) | Hard error, nothing proceeds | Typed expressions |

---

## Industry Patterns: Three Validation Schools

### School 1: "Fail at definition time" (Strictest)

**Systems:** LangGraph, Dagster, Terraform

**Pattern:** References are validated the moment they're declared. If you reference something that doesn't exist, you get an immediate error before any execution.

**Characteristics:**
- Explicit registry (all valid targets must be declared first)
- Typed references (not just string names)
- Build-time / compile-time / validate-time error
- Zero possibility of runtime reference failures
- Test helpers: Dagster's `validate_loadable()`, Terraform's `terraform validate`

**Trade-off:** Requires upfront declaration of everything. Less flexible for dynamic/late-bound systems.

### School 2: "Fail at parse/plan time" (Moderate)

**Systems:** Airflow, GitHub Actions

**Pattern:** The system parses all definitions, builds a dependency graph, and validates integrity before execution begins. References to non-existent targets are caught, but only after all definitions are loaded.

**Characteristics:**
- Implicit registry (IDs derived from declarations)
- String-based references
- Graph built, then validated as a whole
- Cycle detection, orphan detection, duplicate detection
- Some runtime failures still possible (API lookups, dynamic task IDs)

**Trade-off:** Good balance — catches most errors before execution, but allows definitions in any order.

### School 3: "Fail at runtime" (Loosest)

**Systems:** Prefect, Kubernetes, Temporal

**Pattern:** References are not validated until they're actually used. The system accepts definitions optimistically and fails at the point of use.

**Characteristics:**
- No static graph to validate (Prefect) or eventual consistency model (Kubernetes)
- Runtime errors surface per-reference, not globally
- Graceful degradation (Kubernetes: container stays Pending; Temporal: task retries)
- Maximum flexibility (resources can be created in any order)

**Trade-off:** Fast to define, but errors surface late and may be intermittent.

---

## What This Means for Our Phase System

### Our constraints map to School 2

Our system has:
- **Phases declared as files** (`phase-NN-*.md`) — like YAML keys in GitHub Actions
- **Phase references in rules** (`scope: { phase: [4, 5] }`) — like `needs:` in GitHub Actions
- **A generation step** (`generate_hooks.py`) — like Airflow's DagBag parse or GitHub's workflow parser
- **No typed programming language** — rules are YAML, phases are Markdown files, so School 1's "immediate ValueError" isn't available

### Recommended pattern: "Validate at generation time"

This is the **GitHub Actions / Airflow parse-time model** adapted to our system:

```
1. Discover all phase files (glob phase-*.md)
2. Extract phase numbers → build "valid phases" set
3. Load all rules (rules.yaml + rules.d/*.yaml)
4. For each rule with scope.phase:
   - Validate each phase number is in the valid set
   - Warn or fail on invalid references
5. Generate hooks
```

**Concretely in generate_hooks.py:**

```python
def discover_phases(project_root: Path) -> set[int]:
    """Derive valid phase set from filesystem (like GitHub derives job IDs from YAML keys)."""
    ao_dir = project_root / '.ao_project_team'
    phases = set()
    if not ao_dir.is_dir():
        return phases
    for project_dir in ao_dir.iterdir():
        if not project_dir.is_dir():
            continue
        phases_dir = project_dir / 'phases'
        if phases_dir.is_dir():
            for f in phases_dir.glob('phase-*.md'):
                match = re.match(r'phase-(\d+)', f.name)
                if match:
                    phases.add(int(match.group(1)))
    return phases

def validate_phase_references(rules: list[dict], valid_phases: set[int]) -> list[str]:
    """Cross-reference validation (like GitHub's needs: check or Airflow's cycle detection)."""
    warnings = []
    for rule in rules:
        scope = rule.get("scope", {})
        phases = scope.get("phase", [])
        for p in phases:
            if not isinstance(p, int):
                # Hard error — type violation
                print(f"ERROR: Rule {rule['id']} scope.phase contains non-integer: {p!r}", file=sys.stderr)
                sys.exit(1)
            if valid_phases and p not in valid_phases:
                # Warning — reference to non-existent phase file
                warnings.append(f"Rule {rule['id']} references phase {p} but no phase-{p:02d}-*.md found")
    return warnings
```

### Why not School 1 (strictest)?

School 1 (LangGraph/Dagster/Terraform) requires:
- A programming language with types and an execution model
- Explicit registration API (`add_node()`, `@asset`, `resource` block)
- Compile step that can halt immediately

Our phases are **files on disk**, not typed objects. We don't have an `add_phase()` API. The filesystem IS the registry — which maps perfectly to School 2's implicit-registry model (GitHub's YAML keys, Airflow's task_dict built from declarations).

### Why not School 3 (loosest)?

School 3 (Kubernetes/Temporal) is appropriate when:
- Resources are created independently by different actors at different times
- Eventual consistency is acceptable
- The system has built-in retry/reconciliation mechanisms

Our phases are NOT independent resources created by different actors. They're a coherent set defined by one author (the project creator). There's no reason to defer validation — we have a generation step that sees everything at once.

### The key insight from this research

**The "generation step" IS our equivalent of Airflow's DagBag parse or GitHub's workflow parser.** `generate_hooks.py` already:
1. Loads all rules from all sources
2. Validates structural integrity (validate_rules)
3. Cross-checks for collisions (check_id_collisions)
4. Generates output

Adding phase cross-validation is the same pattern — load all phases, load all rules, cross-reference, warn on mismatches. This is exactly what GitHub Actions does with `needs:` → job ID mapping.

---

## Validation Severity: Hard Error vs Warning

The systems split on what to do when cross-references fail:

| Severity | Systems | Rationale |
|----------|---------|-----------|
| **Hard error (abort)** | Terraform, LangGraph, Dagster, GitHub Actions | Invalid reference = broken system, don't proceed |
| **Warning (continue)** | Airflow (some cases), Kubernetes (always) | System can still function, issue is non-fatal |

**Recommendation for our system: Warning by default, hard error opt-in.**

Rationale:
- A rule with `scope: { phase: [4] }` and no `phase-04-*.md` file is **not broken** — the rule simply never fires (same as current behavior without phase scoping)
- Hard errors during generation would break `--check` for projects that haven't created phase files yet
- But a `--strict` flag (like `terraform validate` vs `terraform plan`) could upgrade warnings to errors for CI

```python
# In generate_hooks.py:
if args.strict and phase_warnings:
    for w in phase_warnings:
        print(f"ERROR: {w}", file=sys.stderr)
    sys.exit(1)
else:
    for w in phase_warnings:
        print(f"WARNING: {w}", file=sys.stderr)
```

---

## Summary Table

| Question | Answer | Evidence |
|----------|--------|----------|
| Where are valid states declared? | 5/7 systems: in code/config (explicit). 2/7: in runtime stores | LangGraph dict, Terraform .tf, GitHub YAML keys, Airflow task_dict, Dagster Definitions |
| Validation at definition, plan, or runtime? | **Industry standard is pre-execution.** 5/7 validate before any execution | Only Prefect and Kubernetes defer to runtime |
| Explicit or implicit registry? | Split: 4 explicit (LangGraph, Dagster, Terraform, CrewAI), 4 implicit (Airflow, GitHub, K8s, Prefect) | Implicit = derived from declarations; explicit = separate registration step |
| What happens on invalid reference? | **Majority: hard error, nothing proceeds.** 5/7 systems halt on invalid refs | LangGraph ValueError, Terraform hard error, GitHub rejects workflow, Dagster InvalidDefinitionError, Airflow DuplicateTaskIdFound |
| Industry standard for build-time validation? | **"Load everything → cross-reference → fail before execution"** | GitHub Actions and Airflow are the closest analogs to our file-based system |

**Bottom line:** The industry standard is **validate references before execution, fail early.** Our `generate_hooks.py` is the natural place for this validation — it already sees all rules and can discover all phase files. The pattern is: filesystem discovery → build valid set → cross-reference rules → warn/fail on mismatches. This is the GitHub Actions / Airflow model, adapted to our file-based architecture.
