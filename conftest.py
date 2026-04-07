"""Root conftest: filter SDK submodule tests to workflow-related only.

The claudechic submodule has many tests (app, widgets, cluster, etc.) that
need dependencies not available in this repo's pixi env. We only collect
the workflow tests (guardrails, phases, activation, loading, hits) here;
the rest run in claudechic's own CI.
"""
from pathlib import Path

_SDK_TESTS = Path("submodules/claudechic/tests")

collect_ignore = [
    str(f)
    for f in _SDK_TESTS.glob("test_*.py")
    if not f.name.startswith("test_workflow_")
] if _SDK_TESTS.is_dir() else []
