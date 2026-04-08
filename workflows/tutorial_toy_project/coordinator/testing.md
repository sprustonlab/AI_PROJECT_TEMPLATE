# Testing Phase

Spawn a TestEngineer agent to write and run tests for labmeta.

## Step 1: Explain to User

Tell the user:
> "Now I'm spawning a TestEngineer to verify the implementation. They'll write tests for each module and run them. If tests fail, Implementers fix the issues."

## Step 2: Spawn TestEngineer

Spawn a TestEngineer agent with `requires_answer: true`. Provide this assignment:

**Test the 4 labmeta modules:**

1. **test_store.py** -- YAML read/write, file discovery
   - Load a valid YAML file
   - Save and reload roundtrip
   - Discover files in a directory

2. **test_schema.py** -- Validation
   - Valid data passes
   - Missing required field fails
   - Invalid enum value fails
   - Out-of-range number fails
   - Nested field validation (coordinates)

3. **test_resolver.py** -- Inheritance resolution
   - Session inherits protocol defaults
   - Session overrides protocol values
   - Deep merge for nested fields (coordinates)
   - Missing protocol raises error
   - Internal fields (_type, _protocol, _locked) handled correctly

4. **test_cli.py** -- CLI commands
   - `init protocol` creates a protocol file
   - `create session` creates a session file with protocol reference
   - `validate` catches schema violations
   - `resolve` shows merged output
   - `lock` sets _locked to true
   - `tree` shows hierarchy
   - `dependents` lists sessions using a protocol

**Test location:** `tests/` directory.
**Run with:** `python -m pytest tests/ -v`

## Step 3: Handle Failures

If tests fail:
1. Spawn or re-contact an Implementer to fix the issue
2. Re-run tests via TestEngineer
3. Iterate until all tests pass

## Step 4: Save Results

Ensure test results are saved to `.test_runs/latest_results.txt` (advance check requirement). TestEngineer should pipe pytest output to this file:
```bash
python -m pytest tests/ -v 2>&1 | tee .test_runs/latest_results.txt
```

## Step 5: Advance

Once all tests pass and results are saved, call `advance_phase`.

## Active Rules This Phase

- **R-TOY-04** (warn): Hardcoded paths in test files get flagged
- **R-TOY-05** (deny): No git push allowed yet -- testing must complete first
