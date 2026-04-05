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

# Emoji support detection - use ASCII fallbacks on Windows with non-UTF-8 encoding
def _supports_emoji():
    """Check if stdout can display emoji characters."""
    if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding:
        return sys.stdout.encoding.lower() in ('utf-8', 'utf8')
    return False

if _supports_emoji():
    E_CHECK = "\u2714"       # ✔
    E_CROSS = "\u274c"       # ❌
    E_WARN = "\u26a0\ufe0f"  # ⚠️
    E_TOOL = "\U0001f6e0\ufe0f"  # 🛠️
    E_PKG = "\U0001f4e6"     # 📦
    E_GLOBE = "\U0001f30d"   # 🌍
    E_LOCK = "\U0001f512"    # 🔒
    E_INFO = "\u2139\ufe0f"  # ℹ️
    E_BULB = "\U0001f4a1"    # 💡
    E_PARTY = "\U0001f389"   # 🎉
    E_ROCKET = "\U0001f680"  # 🚀
    E_CYCLE = "\U0001f504"   # 🔄
else:
    E_CHECK = "[OK]"
    E_CROSS = "[ERR]"
    E_WARN = "[WARN]"
    E_TOOL = "[..]"
    E_PKG = "[pkg]"
    E_GLOBE = "[net]"
    E_LOCK = "[lock]"
    E_INFO = "[i]"
    E_BULB = "[tip]"
    E_PARTY = "[done]"
    E_ROCKET = "[>>]"
    E_CYCLE = "[sync]"


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


def is_windows() -> bool:
    """Check if running on Windows."""
    return platform_module.system().lower() == 'windows'


def get_env_executable(env_path: Path, name: str) -> Path:
    """Get path to an executable in an environment, handling Windows differences.

    Args:
        env_path: Path to the conda environment
        name: Name of the executable (e.g., 'pip', 'python', 'conda')

    Returns:
        Path to the executable (with .exe suffix on Windows, in Scripts/ on Windows)
    """
    if is_windows():
        return env_path / "Scripts" / f"{name}.exe"
    else:
        return env_path / "bin" / name


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
print(f"{E_TOOL}  Starting SLC environment setup...")

# Check if SLC is activated
if "SLC_BASE" not in os.environ:
    print(f"{E_CROSS} Error: SLC_BASE environment variable is not set.")
    print(f"{E_BULB} Run: source <SLC_PATH>/activate and try again.")
    sys.exit(1)

SLC_PATH = os.environ["SLC_BASE"]
SCRIPT_DIR = Path(__file__).parent.absolute()
ENVS_DIR = SCRIPT_DIR / 'envs'

# Ensure script is executed inside SLCenv
if os.environ.get("SLC_PYTHON") != sys.executable:
    print(f"{E_CROSS} Error: This script must be run inside SLCenv!")
    print(f"{E_BULB} Activate the environment first:\n")
    print("   source {}/activate".format(SLC_PATH))
    sys.exit(1)

# Parse arguments
if len(sys.argv) < 2:
    print(f"{E_CROSS} Error: No environment name provided.")
    print(f"{E_BULB} Usage: python install_env.py <environment_name> [--read-only]")
    sys.exit(1)

env_name = sys.argv[1].rstrip("/")  # Remove trailing slash if provided
make_readonly = "--read-only" in sys.argv  # Check for optional flag

# Inform the user about the read-only behavior
if make_readonly:
    print(f"{E_LOCK} This environment will be made **read-only** after installation.")
else:
    print(f"{E_INFO}  The environment will remain writable (default).")
    print(f"{E_BULB} Use `--read-only` to make it read-only after installation.")

time.sleep(2)

# Find the best source file (lockfile or spec)
try:
    source_path, source_type = find_env_source(env_name, ENVS_DIR)
except FileNotFoundError as e:
    print(f"{E_CROSS} Error: {e}")
    print(f"{E_BULB} Make sure you provided the correct environment name.")
    print("   Available environments:")
    for f in sorted(ENVS_DIR.glob("*.yml")):
        print(f"     - {f.stem}")
    sys.exit(1)

plat = get_platform_subdir()

if source_type == "spec":
    # No lockfile for this platform - create environment from spec and generate lockfile
    print(f"")
    print(f"{E_WARN}  No lockfile found for platform '{plat}'")
    print(f"{E_PKG} Creating environment from spec (requires internet)...")
    print(f"")

    INSTALL_DIR = ENVS_DIR / plat / env_name
    (ENVS_DIR / plat).mkdir(parents=True, exist_ok=True)

    # Check if already exists
    if INSTALL_DIR.exists():
        print(f"{E_CHECK} Environment '{env_name}' already exists at {INSTALL_DIR}.")
        print(f"   Generating lockfile for reproducibility...")
    else:
        # Create the environment from spec
        subprocess.run(
            ["conda", "env", "create", "-f", str(source_path), "-p", str(INSTALL_DIR)],
            check=True
        )
        print(f"{E_CHECK} Environment created from spec.")

    # Generate lockfile
    print(f"")
    print(f"{E_LOCK} Generating lockfile for reproducibility...")

    # Run lock_env.py from SLCenv (has yaml) with -p pointing to new env
    lock_script = SCRIPT_DIR / "lock_env.py"

    # Use current python (SLC base) to run lock_env.py with -p flag
    result = subprocess.run(
        [sys.executable, str(lock_script), env_name, "-p", str(INSTALL_DIR)],
    )

    if result.returncode == 0:
        print(f"{E_CHECK} Lockfile generated successfully.")
        print(f"")
        print(f"{E_PARTY} Environment '{env_name}' is ready!")
        print(f"   Location: {INSTALL_DIR}")
        print(f"   Lockfile: {ENVS_DIR}/{env_name}.{plat}.lock")
    else:
        print(f"{E_WARN}  Lockfile generation failed (environment still usable)")
        print(f"   You can generate it manually:")
        print(f"   conda activate {INSTALL_DIR}")
        print(f"   python {lock_script} {env_name}")

    sys.exit(0)

# Installing from lockfile
print(f"{E_PKG} Installing from lockfile: {source_path.name}")

# Check for staleness
if is_lockfile_stale(env_name, source_path, ENVS_DIR):
    print(f"{E_WARN}  Warning: Lockfile may be stale")
    print(f"   The spec has changed since the lockfile was generated.")
    print(f"   Consider running: python {SCRIPT_DIR}/lock_env.py {env_name}")
    print()

# Platform-specific cache directory (enables sharing on network drives)
FILES_DIR = ENVS_DIR / plat / f"{env_name}.cache"
ENV_YML_PATH = source_path

# --- Directory Definitions ---
PIP_CACHE_DIR = FILES_DIR / "pip"
CONDA_CACHE_DIR = FILES_DIR / "conda"
DOWNLOAD_COMPLETE_FILE = FILES_DIR / "download_complete"
INSTALL_DIR = ENVS_DIR / plat / env_name
(ENVS_DIR / plat).mkdir(parents=True, exist_ok=True)

# Check if the target environment already exists
if INSTALL_DIR.exists():
    print("{} Environment '{}' already exists at {}.".format(E_CHECK, env_name, INSTALL_DIR))
    print("{} If you want to reinstall, please remove the existing environment first.".format(E_CYCLE))
    sys.exit(0)

# --- Read lockfile ---
with open(ENV_YML_PATH, "r") as f:
    env_data = yaml.safe_load(f)

# Extract channels from lockfile (e.g., pytorch, nvidia, conda-forge)
channels = env_data.get("channels", [])
channel_args = []
for ch in channels:
    channel_args.extend(["-c", ch])

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
            pip_deps.append(pip_dep)

# --- Separate local vs remote pip packages ---
# Local packages appear as paths (e.g., ../some/path) in the lockfile.
# Remote packages appear as name==version (optionally with --hash).
pip_deps_remote = []
pip_deps_local = []  # (original_path_str, resolved_absolute_path)
for dep in pip_deps:
    if dep.startswith((".", "..", "/")):
        local_path = (ENV_YML_PATH.parent / dep).resolve()
        pip_deps_local.append((dep, local_path))
    else:
        pip_deps_remote.append(dep)

if pip_deps_local:
    print("{} Detected {} local pip package(s): {}".format(
        E_INFO, len(pip_deps_local),
        ", ".join(p.name for _, p in pip_deps_local)))

# Determine Online vs Offline Mode
offline_mode = DOWNLOAD_COMPLETE_FILE.exists()
if offline_mode:
    print(f"{E_ROCKET} Running in offline mode. Using cached packages.")
else:
    print(f"{E_GLOBE} Running in online mode. Downloading packages first.")

# Set Custom Conda Cache Directory
CONDA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ["CONDA_PKGS_DIRS"] = str(CONDA_CACHE_DIR)

# --- Install Conda Dependencies ---
if not offline_mode:
    print(f"{E_PKG} Downloading Conda packages...")
    subprocess.run(
        ["conda", "create", "--prefix", str(INSTALL_DIR), "--download-only", "--yes"] + channel_args + conda_deps,
        check=True
    )
    print(f"{E_CHECK} Conda packages downloaded.")

print(f"{E_TOOL}  Creating Conda environment...")
subprocess.run(
    ["conda", "create", "--prefix", str(INSTALL_DIR), "--offline", "--yes"] + channel_args + conda_deps,
    check=True
)
print(f"{E_CHECK} Conda environment successfully created!")

# --- Install Pip Dependencies ---
def install_pip_deps():
    """Handles pip dependency installation."""
    if not pip_deps:
        print(f"{E_INFO}  No pip dependencies found in lockfile.")
        return

    # For claudechic environment, set fake version for setuptools-scm
    # (claudechic is embedded in this repo, not its own git repo, so
    # setuptools-scm can't detect the version from git tags)
    if env_name == "claudechic":
        os.environ["SETUPTOOLS_SCM_PRETEND_VERSION_FOR_CLAUDECHIC"] = "0.1.0"
        print(f"{E_INFO}  Setting SETUPTOOLS_SCM_PRETEND_VERSION_FOR_CLAUDECHIC=0.1.0")

    print(f"{E_PKG} Ensuring setuptools & wheel are installed...")
    pip_bin_new_env = get_env_executable(INSTALL_DIR, "pip")

    subprocess.run([str(pip_bin_new_env), "install", "setuptools", "wheel"], check=True)

    PIP_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not offline_mode:
        for pkg in ["setuptools", "wheel"] + pip_deps_remote:
            print("{} Downloading {}...".format(E_GLOBE, pkg))
            subprocess.run([str(pip_bin_new_env), "download", "--no-deps", "-d", str(PIP_CACHE_DIR), pkg], check=True)
        print(f"{E_CHECK} Pip packages downloaded.")

    # Install remote packages from cache
    if pip_deps_remote:
        print(f"{E_PKG} Installing pip dependencies from cache...")
        subprocess.run([str(pip_bin_new_env), "install", "--no-index", "--find-links", str(PIP_CACHE_DIR)] + pip_deps_remote, check=True)
        print(f"{E_CHECK} Remote pip dependencies installed!")

    # Install local packages directly from source
    for path_str, local_path in pip_deps_local:
        print("{} Installing local package from {}".format(E_PKG, local_path))
        subprocess.run([str(pip_bin_new_env), "install", "--no-deps", str(local_path)], check=True)

    print(f"{E_CHECK} All pip dependencies installed!")

# Run pip installation
install_pip_deps()

# Mark download as complete
if not offline_mode:
    with open(DOWNLOAD_COMPLETE_FILE, "w") as f:
        f.write("download complete")
    print(f"{E_CHECK} Download complete marker created.")

# Make environment read-only if --read-only was specified
if make_readonly:
    print(f"{E_LOCK} Making environment read-only...")
    if not is_windows():
        subprocess.run(["chmod", "-R", "a-w", str(INSTALL_DIR)], check=True)
        print("{} Environment '{}' is now read-only.".format(E_CHECK, env_name))
    else:
        # Windows: use icacls to remove write permissions
        # icacls <path> /deny Everyone:(W) /T makes it read-only recursively
        try:
            subprocess.run(
                ["icacls", str(INSTALL_DIR), "/deny", "Everyone:(W)", "/T", "/Q"],
                check=True,
                capture_output=True
            )
            print("{} Environment '{}' is now read-only.".format(E_CHECK, env_name))
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"{E_WARN}  Could not set read-only permissions on Windows.")
else:
    print(f"{E_INFO}  Environment remains writable (default).")

print("{} New environment '{}' successfully installed at {}!".format(E_PARTY, env_name, INSTALL_DIR))
