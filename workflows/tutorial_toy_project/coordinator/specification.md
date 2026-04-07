# Specification Phase

In this phase, you spawn the Leadership team to analyze the labmeta project. Explain to the user what's happening as you go.

## Step 1: Explain What's About to Happen

Tell the user:
> "Now I'm spawning 4 Leadership agents to analyze the project from different angles. This is how the Project Team workflow works — specialized agents review the design before any code is written."

## Step 2: Spawn Leadership Agents

Spawn all 4 with `requires_answer: true`:

1. **Composability** — Identify the compositional axes of labmeta:
   - Protocol vs Session (data type axis)
   - Schema validation vs inheritance resolution (processing axis)
   - CLI vs library API (interface axis)
   - Ask: "What can vary independently?"

2. **Terminology** — Define canonical domain terms:
   - protocol, session record, resolved config, lock
   - Reject: "template", "base config", "experiment config", "freeze"

3. **Skeptic** — Challenge assumptions and identify risks:
   - What if circular protocol inheritance is attempted?
   - What if schema changes after sessions exist?
   - What if locked sessions need corrections?
   - Is single-level inheritance sufficient?

4. **UserAlignment** — Verify the pre-selected project matches intent:
   - Does the CLI interface cover the use case?
   - Are the 7 commands the right set?
   - Is the schema complete for neuroscience experiments?

Use absolute paths for all agent working directories.

## Step 3: Wait for Reports

Run `list_agents` periodically to check status. Wait for all 4 agents to report back via `tell_agent`.

## Step 4: Synthesize

Combine findings into a brief specification summary. Key deliverables:
- **Schema definition** (`protocols/schema.yaml`) — validation rules
- **Example protocol** — mouse surgery with cranial window
- **Example session** — mouse_001 with overrides
- **Module breakdown** — cli.py, resolver.py, schema.py, store.py

## Step 5: Create Schema File

Before advancing, ensure `protocols/schema.yaml` exists (advance check). Delegate to an Implementer or create a minimal one based on Leadership findings.

The schema should define:
```yaml
animal_id: {type: str, required: true}
strain: {type: str, required: true, enum: [C57BL/6J, Thy1-GCaMP6, PV-Cre, SST-Cre, VIP-Cre]}
age_weeks: {type: int, required: true, min: 1, max: 200}
weight_g: {type: float, required: true, min: 5.0, max: 100.0}
procedure: {type: str, required: true, enum: [cranial_window, injection, perfusion, behavior]}
anesthesia: {type: str, required: true, enum: [isoflurane, ketamine_xylazine, none]}
brain_region: {type: str, enum: [V1, S1, M1, PFC, HPC, VTA]}
coordinates:
  ap_mm: {type: float, min: -10.0, max: 10.0}
  ml_mm: {type: float, min: -10.0, max: 10.0}
  dv_mm: {type: float, min: -10.0, max: 10.0}
experimenter: {type: str, required: true}
notes: {type: str}
```

## Step 6: Present to User and Advance

Present the specification summary. Ask user to confirm the single-level inheritance model (protocol -> session, no chaining). Then call `advance_phase`.
