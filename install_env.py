#!/usr/bin/env python3
# Source: postdoc_monorepo/submodules/SLC @ commit 71317e3 (2026-02-27)
"""Install SLC environment from lockfile (preferred) or spec file.

Usage:
    python install_env.py <environment_name> [--read-only]

The installer will:
1. Check for a platform-specific lockfile (e.g., claudechic.osx-arm64.lock)
2. If found, install from the lockfile (fast, reproducible)
3. If not found, show instructions to create the environment from the spec

By default, environments are kept writable. Use --read-only to make them immutable.
"""
import os
import sys
import subprocess
import shutil
import yaml
import hashlib
import platform as platform_module
import time
from pathlib import Path
from typing import Literal


def get_platform_subdir() -> str:
    """Return conda platform subdir for current system."""
    system = platform_module.system().lower()
    machine = platform_module.machine().lower()

    if machine in ('x86_64', 'amd64'):
        arch = '64'
    elif machine in ('aarch64', 'arm64'):
        arch = 'arm64' if system == 'darwin' else 'aarch64'
    else:
        raise ValueError(f"Unsupported architecture: {machine}")

    if system == 'linux':
        if arch == 'aarch64':
            raise ValueError("Linux ARM64 not yet supported")
        return 'linux-64'
    elif system == 'darwin':
        return f'osx-{arch}'
    elif system == 'windows':
        if arch != '64':
            raise ValueError("Windows ARM not supported")
        return 'win-64'
    else:
        raise ValueError(f"Unsupported OS: {system}")


def find_env_source(env_name: str, envs_dir: Path) -> tuple[Path, Literal["lockfile", "spec"]]:
    """Find the best install source for an environment.

    Returns: (path, source_type)
    Prefers lockfile for current platform, falls back to spec.
    """
    plat = get_platform_subdir()

    # Prefer lockfile for current platform
    lockfile = envs_dir / f"{env_name}.{plat}.lock"
    if lockfile.exists():
        return lockfile, "lockfile"

    # Fall back to minimal spec
    spec = envs_dir / f"{env_name}.yml"
    if spec.exists():
        return spec, "spec"

    raise FileNotFoundError(f"No spec or lockfile found for '{env_name}'")


def is_lockfile_stale(env_name: str, lockfile_path: Path, envs_dir: Path) -> bool:
    """Check if lockfile was generated from current spec."""
    spec_path = envs_dir / f"{env_name}.yml"

    if not spec_path.exists():
        return False  # No spec to compare against

    # Parse _meta:origin_hash from lockfile header
    lock_hash = None
    with open(lockfile_path) as f:
        for line in f:
            if line.startswith('# _meta:origin_hash:'):
                lock_hash = line.split(':')[-1].strip()
                break

    if lock_hash is None or lock_hash == 'N/A':
        return True  # No hash found, assume stale

    current_hash = hashlib.sha256(spec_path.read_bytes()).hexdigest()[:16]
    return lock_hash != current_hash


# --- Preliminary Setup ---
print("🛠️  Starting SLC environment setup...")

# ✅ Check if SLC is activated
if "SLC_BASE" not in os.environ:
    print("❌ Error: SLC_BASE environment variable is not set.")
    print(f"💡 Run: source <SLC_PATH>/activate and try again.")
    sys.exit(1)

SLC_PATH = os.environ["SLC_BASE"]
SCRIPT_DIR = Path(__file__).parent.absolute()
ENVS_DIR = SCRIPT_DIR / 'envs'

# ✅ Ensure script is executed inside SLC base environment
if os.environ.get("SLC_PYTHON") != sys.executable:
    print("❌ Error: This script must be run inside the SLC base environment!")
    print("💡 Activate the environment first:\n")
    print("   source {}/activate".format(SLC_PATH))
    sys.exit(1)

# ✅ Parse arguments
if len(sys.argv) < 2:
    print("❌ Error: No environment name provided.")
    print("💡 Usage: python install_env.py <environment_name> [--read-only]")
    sys.exit(1)

env_name = sys.argv[1].rstrip("/")  # Remove trailing slash if provided
make_readonly = "--read-only" in sys.argv  # Check for optional flag

# ✅ Inform the user about the read-only behavior
if make_readonly:
    print("🔒 This environment will be made **read-only** after installation.")
else:
    print("ℹ️  The environment will remain writable (default).")
    print("💡 Use `--read-only` to make it read-only after installation.")

time.sleep(2)

# ✅ Find the best source file (lockfile or spec)
try:
    source_path, source_type = find_env_source(env_name, ENVS_DIR)
except FileNotFoundError as e:
    print(f"❌ Error: {e}")
    print("💡 Make sure you provided the correct environment name.")
    print("   Available environments:")
    for f in sorted(ENVS_DIR.glob("*.yml")):
        print(f"     - {f.stem}")
    sys.exit(1)

plat = get_platform_subdir()

if source_type == "spec":
    # No lockfile for this platform - create environment from spec and generate lockfile
    print(f"")
    print(f"⚠️  No lockfile found for platform '{plat}'")
    print(f"📦 Creating environment from spec (requires internet)...")
    print(f"")

    INSTALL_DIR = ENVS_DIR / env_name

    # Check if already exists
    if INSTALL_DIR.exists():
        print(f"✔ Environment '{env_name}' already exists at {INSTALL_DIR}.")
        print(f"   Generating lockfile for reproducibility...")
    else:
        # Create the environment from spec
        subprocess.run(
            ["conda", "env", "create", "-f", str(source_path), "-p", str(INSTALL_DIR)],
            check=True
        )
        print(f"✔ Environment created from spec.")

    # Generate lockfile
    print(f"")
    print(f"🔒 Generating lockfile for reproducibility...")

    # Run lock_env.py from SLC base environment (has yaml) with -p pointing to new env
    lock_script = SCRIPT_DIR / "lock_env.py"

    # Use current python (SLC base) to run lock_env.py with -p flag
    result = subprocess.run(
        [sys.executable, str(lock_script), env_name, "-p", str(INSTALL_DIR)],
    )

    if result.returncode == 0:
        print(f"✔ Lockfile generated successfully.")
        print(f"")
        print(f"🎉 Environment '{env_name}' is ready!")
        print(f"   Location: {INSTALL_DIR}")
        print(f"   Lockfile: {ENVS_DIR}/{env_name}.{plat}.lock")
    else:
        print(f"⚠️  Lockfile generation failed (environment still usable)")
        print(f"   You can generate it manually:")
        print(f"   conda activate {INSTALL_DIR}")
        print(f"   python {lock_script} {env_name}")

    sys.exit(0)

# ✅ Installing from lockfile
print(f"📦 Installing from lockfile: {source_path.name}")

# Check for staleness
if is_lockfile_stale(env_name, source_path, ENVS_DIR):
    print(f"⚠️  Warning: Lockfile may be stale")
    print(f"   The spec has changed since the lockfile was generated.")
    print(f"   Consider running: python {SCRIPT_DIR}/lock_env.py {env_name}")
    print()

# Platform-specific cache directory (enables sharing on network drives)
FILES_DIR = ENVS_DIR / f"{env_name}.{plat}.cache"
ENV_YML_PATH = source_path

# --- Directory Definitions ---
PIP_CACHE_DIR = FILES_DIR / "pip"
CONDA_CACHE_DIR = FILES_DIR / "conda"
DOWNLOAD_COMPLETE_FILE = FILES_DIR / "download_complete"
INSTALL_DIR = ENVS_DIR / env_name

# ✅ Check if the target environment already exists
if INSTALL_DIR.exists():
    print("✔ Environment '{}' already exists at {}.".format(env_name, INSTALL_DIR))
    print("🔄 If you want to reinstall, please remove the existing environment first.")
    sys.exit(0)

# --- Read lockfile ---
with open(ENV_YML_PATH, "r") as f:
    env_data = yaml.safe_load(f)

# Extract dependencies from lockfile (already platform-specific, no relaxation needed)
conda_deps = []
for dep in env_data.get("dependencies", []):
    if isinstance(dep, str) and not dep.startswith("pip"):
        conda_deps.append(dep)

# Extract pip dependencies (strip --hash for installation, conda doesn't use them)
pip_deps = []
for dep in env_data.get("dependencies", []):
    if isinstance(dep, dict) and "pip" in dep:
        for pip_dep in dep["pip"]:
            # Remove --hash suffix if present (used for verification, not install)
            if " --hash=" in pip_dep:
                pip_dep = pip_dep.split(" --hash=")[0]
            # Resolve relative editable install paths to absolute
            # Paths in lockfile are relative to envs/ dir (same as the spec)
            if pip_dep.startswith("-e "):
                rel_path = pip_dep[3:].strip()
                if not os.path.isabs(rel_path):
                    abs_path = (ENVS_DIR / rel_path).resolve()
                    pip_dep = f"-e {abs_path}"
            pip_deps.append(pip_dep)

# ✅ Determine Online vs Offline Mode
offline_mode = DOWNLOAD_COMPLETE_FILE.exists()
if offline_mode:
    print("🚀 Running in offline mode. Using cached packages.")
else:
    print("🌍 Running in online mode. Downloading packages first.")

# ✅ Set Custom Conda Cache Directory
CONDA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ["CONDA_PKGS_DIRS"] = str(CONDA_CACHE_DIR)

# --- Install Conda Dependencies ---
if not offline_mode:
    print("📦 Downloading Conda packages...")
    subprocess.run(
        ["conda", "create", "--prefix", str(INSTALL_DIR), "--download-only", "--yes"] + conda_deps,
        check=True
    )
    print("✔ Conda packages downloaded.")

print("🛠️  Creating Conda environment...")
subprocess.run(
    ["conda", "create", "--prefix", str(INSTALL_DIR), "--offline", "--yes"] + conda_deps,
    check=True
)
print("✔ Conda environment successfully created!")

# --- Install Pip Dependencies ---
# --- Install Pip Dependencies ---
def install_pip_deps():
    """Handles pip dependency installation."""
    if not pip_deps:
        print("ℹ️   No pip dependencies found in lockfile.")
        return
    
    print("📦 Ensuring setuptools & wheel are installed...")
    pip_bin_new_env = INSTALL_DIR / "bin" / "pip"
    if not pip_bin_new_env.exists():
        pip_bin_new_env = INSTALL_DIR / "Scripts" / "pip.exe"  # Windows
    
    # Set up environment for pip install (copy parent env and add custom vars)
    pip_env = os.environ.copy()
    
    # For claudechic environment, set fake version for setuptools-scm
    if env_name == "claudechic":
        pip_env["SETUPTOOLS_SCM_PRETEND_VERSION_FOR_CLAUDECHIC"] = "0.1.0"
        print("ℹ️   Setting SETUPTOOLS_SCM_PRETEND_VERSION_FOR_CLAUDECHIC=0.1.0")
    
    subprocess.run([str(pip_bin_new_env), "install", "setuptools", "wheel"], check=True, env=pip_env)


    PIP_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Separate editable (local) installs from regular (cached) deps
    editable_deps = [dep for dep in pip_deps if dep.startswith("-e ")]
    regular_deps = [dep for dep in pip_deps if not dep.startswith("-e ")]

    if not offline_mode:
        for pkg in ["setuptools", "wheel"] + regular_deps:
            print("🌍 Downloading {}...".format(pkg))
            subprocess.run([str(pip_bin_new_env), "download", "--no-deps", "-d", str(PIP_CACHE_DIR), pkg], check=True, env=pip_env)
        print("✔ Pip packages downloaded.")

    print("📦 Installing pip dependencies from cache...")
    subprocess.run([str(pip_bin_new_env), "install", "--no-index", "--find-links", str(PIP_CACHE_DIR)] + regular_deps, check=True, env=pip_env)
    print("✔ Pip dependencies installed!")

    if editable_deps:
        print("📦 Installing local editable packages...")
        for dep in editable_deps:
            print("   {}".format(dep))
        subprocess.run([str(pip_bin_new_env), "install"] + editable_deps, check=True, env=pip_env)
        print("✔ Local editable packages installed!")

# Run pip installation
install_pip_deps()

# ✅ Mark download as complete
if not offline_mode:
    with open(DOWNLOAD_COMPLETE_FILE, "w") as f:
        f.write("download complete")
    print("✔ Download complete marker created.")

# ✅ Make environment read-only if --read-only was specified
if make_readonly:
    print("🔒 Making environment read-only...")
    if platform_module.system().lower() != 'windows':
        subprocess.run(["chmod", "-R", "a-w", str(INSTALL_DIR)], check=True)
        print("✔ Environment '{}' is now read-only.".format(env_name))
    else:
        print("ℹ️  Read-only mode not supported on Windows.")
else:
    print("ℹ️  Environment remains writable (default).")

print("🎉 New environment '{}' successfully installed at {}!".format(env_name, INSTALL_DIR))
