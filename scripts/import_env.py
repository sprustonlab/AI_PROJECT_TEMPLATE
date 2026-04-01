#!/usr/bin/env python3
"""import_env.py — Convert envs/<name>.yml to a pixi feature in pixi.toml.

Contributor-friendly entry point: drop a conda-style yml file in envs/,
run this script, and pixi.toml is updated with the corresponding feature
and environment mapping.

Usage:
    python3 scripts/import_env.py envs/r-analysis.yml
    python3 scripts/import_env.py envs/*.yml          # batch import

What it does:
    1. Reads the yml file (name, channels, dependencies)
    2. Adds [feature.<name>.dependencies] to pixi.toml
    3. Adds <name> = ["<name>"] to [environments] section
    4. Runs `pixi lock` to update pixi.lock

The yml format is the familiar conda env spec:
    name: r-analysis
    channels: [conda-forge]
    dependencies:
      - r-base=4.4
      - r-tidyverse
      - pip:
        - some-pip-package
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit(
        "ERROR: PyYAML is required. Install via: pip install pyyaml\n"
        "Or use: pixi run python3 scripts/import_env.py"
    )


def parse_yml(yml_path: Path) -> dict:
    """Parse a conda-style environment yml file.

    Returns:
        Dict with keys: name, conda_deps (list[str]), pypi_deps (list[str]).
    """
    with open(yml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    name = data.get("name") or yml_path.stem
    deps = data.get("dependencies", [])

    conda_deps: list[str] = []
    pypi_deps: list[str] = []

    for dep in deps:
        if isinstance(dep, str):
            conda_deps.append(dep)
        elif isinstance(dep, dict) and "pip" in dep:
            pypi_deps.extend(dep["pip"])

    return {
        "name": name,
        "conda_deps": conda_deps,
        "pypi_deps": pypi_deps,
    }


def parse_conda_dep(dep_str: str) -> tuple[str, str]:
    """Parse a conda dependency string into (package, version_spec).

    Examples:
        "r-base=4.4"  → ("r-base", "==4.4")
        "r-tidyverse"  → ("r-tidyverse", "*")
        "python>=3.10,<3.14" → ("python", ">=3.10,<3.14")
    """
    # Handle version constraints with >= or similar
    match = re.match(r'^([a-zA-Z0-9_-]+)\s*([>=<!].*)?$', dep_str)
    if not match:
        # Fallback: treat as package name with wildcard version
        return dep_str.strip(), "*"

    pkg = match.group(1)
    ver = match.group(2)

    if not ver:
        return pkg, "*"

    # Single = in conda means ==, convert for pixi
    if ver.startswith("=") and not ver.startswith("==") and not ver.startswith(">="):
        ver = "==" + ver[1:]

    return pkg, ver


def generate_feature_toml(env_data: dict) -> str:
    """Generate TOML feature sections for an environment.

    # Note: "feature" here is pixi terminology (optional dependency group),
    # not our project-level "Feature" (user-visible capability).

    Returns:
        TOML string for the feature (dependencies + optional pypi-dependencies).
    """
    name = env_data["name"]
    lines = []

    # Conda dependencies
    lines.append(f"[feature.{name}.dependencies]")
    for dep in env_data["conda_deps"]:
        pkg, ver = parse_conda_dep(dep)
        lines.append(f'{pkg} = "{ver}"')
    lines.append("")

    # PyPI dependencies (if any)
    if env_data["pypi_deps"]:
        lines.append(f"[feature.{name}.pypi-dependencies]")
        for dep in env_data["pypi_deps"]:
            # Handle editable installs
            if dep.startswith("-e "):
                path = dep[3:].strip()
                pkg_name = Path(path).name
                lines.append(f'{pkg_name} = {{ path = "{path}", editable = true }}')
            else:
                # Simple pip dep: name or name>=version
                match = re.match(r'^([a-zA-Z0-9_-]+)\s*([>=<!].*)?$', dep)
                if match:
                    pkg = match.group(1)
                    ver = match.group(2) or "*"
                    lines.append(f'{pkg} = "{ver}"')
                else:
                    # URL or complex spec — use as-is
                    lines.append(f'# TODO: manually add: {dep}')
        lines.append("")

    return "\n".join(lines)


def update_pixi_toml(pixi_path: Path, env_data: dict) -> None:
    """Update pixi.toml with a new feature and environment mapping.

    Inserts the feature section before the [environments] section,
    and adds the environment mapping.
    """
    name = env_data["name"]
    content = pixi_path.read_text(encoding="utf-8")

    # Check if feature already exists
    if f"[feature.{name}." in content:
        print(f"  ⚠️  Feature '{name}' already exists in pixi.toml — skipping feature section")
    else:
        feature_toml = generate_feature_toml(env_data)

        # Insert before [environments] section
        env_section_match = re.search(r'^(\[environments\])', content, re.MULTILINE)
        if env_section_match:
            insert_pos = env_section_match.start()
            content = content[:insert_pos] + feature_toml + "\n" + content[insert_pos:]
        else:
            # No [environments] section — append feature and create one
            content = content.rstrip() + "\n\n" + feature_toml + "\n"

    # Add environment mapping if not present
    env_mapping = f'{name} = ["{name}"]'
    if env_mapping not in content:
        # Find [environments] section and append
        env_match = re.search(r'^\[environments\]\s*$', content, re.MULTILINE)
        if env_match:
            # Find the end of the environments section (next section or EOF)
            rest = content[env_match.end():]
            next_section = re.search(r'^\[', rest, re.MULTILINE)
            if next_section:
                insert_pos = env_match.end() + next_section.start()
                content = content[:insert_pos] + env_mapping + "\n" + content[insert_pos:]
            else:
                content = content.rstrip() + "\n" + env_mapping + "\n"
        else:
            content = content.rstrip() + "\n\n[environments]\n" + env_mapping + "\n"

    pixi_path.write_text(content, encoding="utf-8")
    print(f"  ✔ pixi.toml updated with feature '{name}'")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert envs/<name>.yml to a pixi feature in pixi.toml"
    )
    parser.add_argument(
        "yml_files",
        nargs="+",
        type=Path,
        help="One or more conda-style yml files to import",
    )
    parser.add_argument(
        "--pixi-toml",
        type=Path,
        default=None,
        help="Path to pixi.toml (default: auto-detect from script location)",
    )
    parser.add_argument(
        "--no-lock",
        action="store_true",
        help="Skip running pixi lock after updating pixi.toml",
    )
    args = parser.parse_args()

    # Find pixi.toml
    if args.pixi_toml:
        pixi_path = args.pixi_toml
    else:
        # Auto-detect: script is in scripts/, pixi.toml is in parent
        pixi_path = Path(__file__).resolve().parent.parent / "pixi.toml"

    if not pixi_path.exists():
        print(f"ERROR: pixi.toml not found at {pixi_path}", file=sys.stderr)
        return 1

    for yml_file in args.yml_files:
        if not yml_file.exists():
            print(f"ERROR: {yml_file} not found", file=sys.stderr)
            return 1

        print(f"Importing {yml_file}...")
        env_data = parse_yml(yml_file)
        update_pixi_toml(pixi_path, env_data)

    # Run pixi lock to update pixi.lock
    if not args.no_lock:
        print("\nRunning pixi lock...")
        try:
            subprocess.run(
                ["pixi", "lock"],
                check=True,
                cwd=pixi_path.parent,
            )
            print("✔ pixi.lock updated")
        except FileNotFoundError:
            print("⚠️  pixi not found — run 'pixi lock' manually after installing pixi")
        except subprocess.CalledProcessError:
            print("⚠️  pixi lock failed — check pixi.toml for errors")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
