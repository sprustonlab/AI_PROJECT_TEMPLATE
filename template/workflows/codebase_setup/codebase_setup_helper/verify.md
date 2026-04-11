# Verify Phase

Confirm the integrated codebase is importable and functional.

## Steps

1. **Test the import.** From the project root, run:
   ```
   python -c "import <module>; print('<module> imported successfully')"
   ```
   If this fails, diagnose the error:
   - `ModuleNotFoundError` -- check that `repos/<name>` is on `PYTHONPATH` and the module name is correct.
   - `ImportError` -- a dependency is missing. Go back to environment phase or install it now.
   - `SyntaxError` -- the codebase has issues unrelated to integration. Report and let the user decide.

2. **Check for existing tests.** Look for:
   - `tests/` or `test/` directory in the codebase
   - `pytest.ini`, `setup.cfg [tool:pytest]`, or `pyproject.toml [tool.pytest]`
   - Any `test_*.py` files

3. **Offer to run tests.** If tests are found, ask the user if they'd like to run them as a sanity check. Run with `pytest repos/<name>/tests/ -v --tb=short` (or the appropriate test command). Report results but don't block on test failures -- the goal is integration verification, not full test coverage.

4. **Summary.** Report the final status:
   - Import: working / failing
   - Tests: passed / failed / not found / skipped
   - Any remaining issues or manual steps needed

To advance: the module imports successfully from the project root.
