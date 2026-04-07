"""Root conftest: filter SDK submodule tests.

The claudechic submodule has many tests (app, widgets, cluster, etc.) that
need dependencies not available in this repo's pixi env. We collect only
workflow tests and hints integration tests here; the rest run in
claudechic's own CI.
"""
from pathlib import Path

_SDK_TESTS = Path("submodules/claudechic/tests")
_INCLUDE_PREFIXES = ("test_workflow_", "test_hints_")

collect_ignore = [
    str(f)
    for f in _SDK_TESTS.glob("test_*.py")
    if not any(f.name.startswith(p) for p in _INCLUDE_PREFIXES)
] if _SDK_TESTS.is_dir() else []
