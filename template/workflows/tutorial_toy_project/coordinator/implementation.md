# Implementation Phase

Spawn Implementer agents to build the 4 labmeta modules. You delegate -- you do NOT write code.

## Step 1: Explain to User

Tell the user:
> "Now I'm spawning Implementer agents to build the actual code. Each Implementer gets a specific module assignment. I coordinate, they code."

## Step 2: Spawn Implementers

Spawn 1-2 Implementer agents (the project is small enough for 1-2):

**Implementer-Core** -- builds the library modules:
- `labmeta/__init__.py` -- package init
- `labmeta/store.py` (~40 lines) -- YAML read/write, file discovery
- `labmeta/schema.py` (~50 lines) -- validation against schema.yaml
- `labmeta/resolver.py` (~80 lines) -- protocol+session inheritance merge

**Implementer-CLI** -- builds the CLI and examples:
- `labmeta/cli.py` (~60 lines) -- CLI entry point with all 7 commands
- `protocols/examples/mouse_surgery_protocol.yaml` -- example protocol
- `sessions/examples/mouse_001_session_20260406.yaml` -- example session

Use `requires_answer: true` so they report back when done.

## Module Specifications

### store.py (~40 lines)
- `load_yaml(path) -> dict` -- read YAML file
- `save_yaml(path, data)` -- write YAML file
- `discover_files(directory, pattern) -> list[Path]` -- find YAML files
- All paths relative to project root

### schema.py (~50 lines)
- `load_schema(path) -> dict` -- read schema.yaml
- `validate(data, schema) -> list[str]` -- return list of error messages
- Supports: type checking (str, int, float), required fields, enum validation, min/max ranges
- Nested field support (coordinates.ap_mm)

### resolver.py (~80 lines)
- `resolve(session_path, protocols_dir) -> dict` -- merge protocol + session
- Read session, find its `_protocol` reference, load protocol
- Deep merge: session values override protocol defaults
- Skip internal fields (`_type`, `_protocol`, `_locked`)
- Error if protocol not found

### cli.py (~60 lines)
- Entry point: `python -m labmeta <command> [args]`
- Commands: init, create, validate, resolve, lock, tree, dependents
- Uses argparse or click (implementer's choice, prefer argparse for zero deps)
- Each command delegates to store/schema/resolver

### Example Protocol
```yaml
_type: protocol
procedure: cranial_window
anesthesia: isoflurane
brain_region: V1
coordinates:
  ap_mm: -2.5
  ml_mm: 2.5
  dv_mm: 0.3
default_imaging_depth_um: 200
```

### Example Session
```yaml
_type: session
_protocol: mouse_surgery_protocol.yaml
_locked: false
animal_id: mouse_001
strain: C57BL/6J
age_weeks: 12
weight_g: 28.5
experimenter: moharb
coordinates:
  ap_mm: -2.7
notes: "Slight bleeding during craniotomy, resolved"
```

## Step 3: Monitor Progress

Run `list_agents` to check Implementer status. When they report done, review the output with Leadership (inform Skeptic of implementation for review).

## Step 4: Verify Advance Checks

Before calling `advance_phase`, verify these files exist:
- `protocols/examples/mouse_surgery_protocol.yaml`
- `sessions/examples/mouse_001_session_20260406.yaml`
- `labmeta/resolver.py`

## Step 5: Advance

Get Leadership approval, then call `advance_phase`.

## Active Rules This Phase

- **R-TOY-03** (warn): Editing schema.yaml triggers a warning
- **R-TOY-04** (warn): Hardcoded absolute paths get flagged
- **R-TOY-05** (deny): No git push allowed yet
