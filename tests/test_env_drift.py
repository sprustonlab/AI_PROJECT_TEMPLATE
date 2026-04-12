"""Detect packages installed outside pixi (environment drift).

Compares pip list (what's actually installed in the current env) against
pixi list (what pixi manages). Any package in pip but not in pixi was
installed manually and should be added to pixi.toml.

This catches cases where someone runs `pip install foo` directly instead
of `pixi add --pypi foo`, which causes the environment to drift from
the lockfile and breaks reproducibility.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Packages that pip reports but pixi doesn't track (stdlib wrappers,
# editable self-installs, etc.) — not real drift.
KNOWN_EXCEPTIONS = {
    "pip",  # pip itself, sometimes version mismatch between conda/pip
}


def _get_pip_packages() -> dict[str, str]:
    """Get packages from pip list in the current environment."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "list", "--format=json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        pytest.skip(f"pip list failed: {result.stderr}")
    return {
        p["name"].lower().replace("-", "_"): p["version"]
        for p in json.loads(result.stdout)
    }


def _get_pixi_packages() -> dict[str, str]:
    """Get packages from pixi list (what pixi manages)."""
    result = subprocess.run(
        ["pixi", "list", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        pytest.skip(f"pixi list failed: {result.stderr}")
    return {
        p["name"].lower().replace("-", "_"): p["version"]
        for p in json.loads(result.stdout)
    }


def test_no_pip_packages_outside_pixi():
    """All pip-installed packages must be tracked by pixi.

    If this test fails, a package was installed with `pip install`
    instead of `pixi add --pypi`. Fix by running:
        pixi add --pypi <package-name>
    Then remove the stray install:
        pip uninstall <package-name>
        pixi install
    """
    pip_pkgs = _get_pip_packages()
    pixi_pkgs = _get_pixi_packages()

    drift = {
        name: ver
        for name, ver in pip_pkgs.items()
        if name not in pixi_pkgs and name not in KNOWN_EXCEPTIONS
    }

    if drift:
        lines = [f"  {name} == {ver}" for name, ver in sorted(drift.items())]
        pytest.fail(
            f"Environment drift: {len(drift)} package(s) installed via pip "
            f"but not managed by pixi:\n"
            + "\n".join(lines)
            + "\n\nFix: pixi add --pypi <package> (or pixi add <package> for conda)"
        )
