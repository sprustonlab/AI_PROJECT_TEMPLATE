#!/usr/bin/env python3
# Source: postdoc_monorepo/submodules/SLC @ commit 71317e3 (2026-02-27)
"""Generate platform-specific lockfile from current conda environment.

Usage:
    # First activate the environment you want to lock
    conda activate claudechic

    # Then generate the lockfile
    python lock_env.py claudechic

This creates envs/claudechic.<platform>.lock (e.g., claudechic.osx-arm64.lock)
"""

import subprocess
import yaml
import hashlib
import datetime
import platform
import tempfile
import os
import sys
from pathlib import Path

# Emoji support detection - use ASCII fallbacks on Windows with non-UTF-8 encoding
def _supports_emoji():
    """Check if stdout can display emoji characters."""
    if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding:
        return sys.stdout.encoding.lower() in ('utf-8', 'utf8')
    return False

if _supports_emoji():
    E_CHECK = "\u2714"       # ✔
    E_PKG = "\U0001f4e6"     # 📦
    E_LOCK = "\U0001f512"    # 🔒
    E_WARN = "\u26a0\ufe0f"  # ⚠️
else:
    E_CHECK = "[OK]"
    E_PKG = "[pkg]"
    E_LOCK = "[lock]"
    E_WARN = "[WARN]"


def get_platform_subdir() -> str:
    """Return conda platform subdir for current system.

    Returns one of: linux-64, osx-64, osx-arm64, win-64

    Raises:
        ValueError: If platform is not supported
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Normalize machine names (Windows uses 'AMD64', others use 'x86_64')
    if machine in ('x86_64', 'amd64'):
        arch = '64'
    elif machine in ('aarch64', 'arm64'):
        arch = 'arm64' if system == 'darwin' else 'aarch64'
    else:
        raise ValueError(f"Unsupported architecture: {machine}")

    if system == 'linux':
        if arch == 'aarch64':
            raise ValueError("Linux ARM64 not yet supported. Add support when needed.")
        return 'linux-64'
    elif system == 'darwin':
        return f'osx-{arch}'  # osx-64 or osx-arm64
    elif system == 'windows':
        if arch != '64':
            raise ValueError("Windows ARM not supported")
        return 'win-64'
    else:
        raise ValueError(f"Unsupported OS: {system}")


def get_origin_hash(yml_path: Path) -> str:
    """SHA256 hash (first 16 chars) of the origin spec file."""
    if not yml_path.exists():
        return 'N/A'
    return hashlib.sha256(yml_path.read_bytes()).hexdigest()[:16]


def atomic_write(path: Path, content: str):
    """Write file atomically via temp + replace. Cross-platform."""
    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp"
    )
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        os.replace(tmp_path, path)  # Atomic on all platforms (POSIX + Windows)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def get_pip_package_hashes(env_prefix: Path) -> dict[str, str]:
    """Get SHA256 hashes for installed pip packages.

    Returns dict mapping 'package==version' to 'sha256:hash'.
    """
    # Platform-specific pip path: bin/pip on Unix, Scripts/pip.exe on Windows
    if platform.system().lower() == 'windows':
        pip_path = env_prefix / "Scripts" / "pip.exe"
    else:
        pip_path = env_prefix / "bin" / "pip"

    if not pip_path.exists():
        return {}

    # Get list of pip packages with their locations
    result = subprocess.run(
        [str(pip_path), "list", "--format=json"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return {}

    import json
    packages = json.loads(result.stdout)
    hashes = {}

    # Get site-packages location
    site_result = subprocess.run(
        [str(pip_path), "show", "pip"],
        capture_output=True, text=True
    )
    site_packages = None
    for line in site_result.stdout.splitlines():
        if line.startswith("Location:"):
            site_packages = Path(line.split(":", 1)[1].strip())
            break

    if not site_packages:
        return {}

    for pkg in packages:
        name = pkg["name"]
        version = pkg["version"]
        key = f"{name}=={version}"

        # Try to find the dist-info directory to get the RECORD file
        dist_info = site_packages / f"{name.replace('-', '_')}-{version}.dist-info"
        record_file = dist_info / "RECORD"

        if record_file.exists():
            # Hash the RECORD file as a proxy for package integrity
            pkg_hash = hashlib.sha256(record_file.read_bytes()).hexdigest()[:16]
            hashes[key] = f"sha256:{pkg_hash}"

    return hashes


def generate_lockfile(env_name: str, env_prefix: Path | None = None):
    """Export conda env to platform-specific lockfile.

    Args:
        env_name: Name of the environment (used for output filename)
        env_prefix: Optional path to environment. If None, exports currently active env.
    """
    plat = get_platform_subdir()
    envs_dir = Path(__file__).parent / "envs"

    # Export environment
    print(f"{E_PKG} Exporting conda environment...")
    export_cmd = ["conda", "env", "export"]
    if env_prefix:
        export_cmd.extend(["-p", str(env_prefix)])
    result = subprocess.run(
        export_cmd,
        capture_output=True, text=True, check=True
    )
    env_data = yaml.safe_load(result.stdout)

    # Get environment prefix for pip hash extraction
    env_prefix = Path(env_data.get("prefix", ""))

    # Clean up conda export
    env_data.pop("prefix", None)
    env_data["name"] = env_name
    env_data["channels"] = [c for c in env_data.get("channels", []) if c != "defaults"]

    # Build map of local pip packages from original spec
    # Local packages (e.g., ../some/path) get resolved to name==version by conda export.
    # We restore the original path so install_env.py can install from source.
    import re
    local_pip_map: dict[str, str] = {}  # normalized_name -> original_path
    origin_path_for_locals = envs_dir / f"{env_name}.yml"
    if origin_path_for_locals.exists():
        with open(origin_path_for_locals) as f:
            spec_for_locals = yaml.safe_load(f)
        for dep in spec_for_locals.get("dependencies", []):
            if isinstance(dep, dict) and "pip" in dep:
                for pip_dep in dep["pip"]:
                    if pip_dep.startswith((".", "..", "/")):
                        local_path = (origin_path_for_locals.parent / pip_dep).resolve()
                        if local_path.exists():
                            norm = re.sub(r"[-_.]+", "-", local_path.name).lower()
                            local_pip_map[norm] = pip_dep  # keep original relative path

    # Add hashes to pip packages for reproducibility
    if env_prefix.exists():
        print(f"{E_LOCK} Computing pip package hashes...")
        pip_hashes = get_pip_package_hashes(env_prefix)

        # Update pip dependencies with hashes
        for i, dep in enumerate(env_data.get("dependencies", [])):
            if isinstance(dep, dict) and "pip" in dep:
                new_pip_deps = []
                for pip_dep in dep["pip"]:
                    # pip_dep is like "package==1.2.3"
                    dep_name = re.sub(r"[-_.]+", "-", pip_dep.split("==")[0]).lower()
                    if dep_name in local_pip_map:
                        # Restore original local path instead of name==version
                        new_pip_deps.append(local_pip_map[dep_name])
                    elif pip_dep in pip_hashes:
                        new_pip_deps.append(f"{pip_dep} --hash={pip_hashes[pip_dep]}")
                    else:
                        new_pip_deps.append(pip_dep)
                env_data["dependencies"][i]["pip"] = new_pip_deps

    # Build header with _meta: prefix for SLC coordination
    origin_path = envs_dir / f"{env_name}.yml"
    origin_hash = get_origin_hash(origin_path)
    timestamp = datetime.datetime.utcnow().isoformat()

    # Read original constraints from spec for documentation
    original_constraints = ""
    if origin_path.exists():
        with open(origin_path) as f:
            spec_data = yaml.safe_load(f)
        deps = spec_data.get("dependencies", [])
        constraint_lines = []
        for dep in deps:
            if isinstance(dep, str):
                constraint_lines.append(f"#   {dep}")
            elif isinstance(dep, dict) and "pip" in dep:
                for pip_dep in dep["pip"]:
                    constraint_lines.append(f"#   {pip_dep} (pip)")
        if constraint_lines:
            original_constraints = "\n#\n# Original constraints (from spec):\n" + "\n".join(constraint_lines) + "\n"

    header = f"""# AUTO-GENERATED by SLC - Do not edit
# _meta:origin: {env_name}.yml
# _meta:origin_hash: {origin_hash}
# _meta:platform: {plat}
# _meta:generated: {timestamp}Z{original_constraints}

"""

    # Generate YAML content
    yaml_content = yaml.dump(env_data, sort_keys=False, default_flow_style=False)
    full_content = header + yaml_content

    # Write lockfile atomically
    lock_path = envs_dir / f"{env_name}.{plat}.lock"
    atomic_write(lock_path, full_content)

    print(f"{E_CHECK} Generated {lock_path}")
    print(f"  Platform: {plat}")
    print(f"  Origin hash: {origin_hash}")
    if origin_hash == 'N/A':
        print(f"  {E_WARN}  No origin spec found at {origin_path}")
        print(f"     Consider creating a minimal spec file.")


def main():
    if len(sys.argv) < 2:
        print("Usage: python lock_env.py <environment_name> [-p <prefix>]")
        print()
        print("Generates a platform-specific lockfile from a conda environment.")
        print("If -p is not provided, exports the currently active environment.")
        sys.exit(1)

    env_name = sys.argv[1].rstrip("/")

    # Parse optional -p flag
    env_prefix = None
    if "-p" in sys.argv:
        idx = sys.argv.index("-p")
        if idx + 1 < len(sys.argv):
            env_prefix = Path(sys.argv[idx + 1])

    generate_lockfile(env_name, env_prefix)


if __name__ == "__main__":
    main()
