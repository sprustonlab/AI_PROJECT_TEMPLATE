#!/usr/bin/env python3
# Source: postdoc_monorepo/submodules/gaby_arco @ 2026-02-27
import os
import urllib.request
import subprocess
import functools
import shutil
import platform

# Miniforge details
ENV = 'SLCenv'
MINIFORGE_VERSION = "24.11.3-0"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.join(SCRIPT_DIR, 'envs')

# Detect platform and set appropriate installer and download directory
PLATFORM = platform.system()
IS_WINDOWS = PLATFORM == 'Windows'

if PLATFORM == 'Darwin':
    MINIFORGE_URL = f"https://github.com/conda-forge/miniforge/releases/download/{MINIFORGE_VERSION}/Miniforge3-MacOSX-arm64.sh"
    DOWNLOAD_DIR = os.path.join(SCRIPT_DIR, f'{ENV}_offline_install_mac')
    INSTALLER_NAME = "Miniforge3.sh"
    BIN_DIR = "bin"
    EXE_SUFFIX = ""
elif PLATFORM == 'Linux':
    MINIFORGE_URL = f"https://github.com/conda-forge/miniforge/releases/download/{MINIFORGE_VERSION}/Miniforge3-Linux-x86_64.sh"
    DOWNLOAD_DIR = os.path.join(SCRIPT_DIR, f'{ENV}_offline_install')
    INSTALLER_NAME = "Miniforge3.sh"
    BIN_DIR = "bin"
    EXE_SUFFIX = ""
elif PLATFORM == 'Windows':
    MINIFORGE_URL = f"https://github.com/conda-forge/miniforge/releases/download/{MINIFORGE_VERSION}/Miniforge3-Windows-x86_64.exe"
    DOWNLOAD_DIR = os.path.join(SCRIPT_DIR, f'{ENV}_offline_install_win')
    INSTALLER_NAME = "Miniforge3.exe"
    BIN_DIR = "Scripts"
    EXE_SUFFIX = ".exe"
else:
    raise NotImplementedError(f"Unsupported platform: {PLATFORM}")

PIP_CACHE_DIR = os.path.join(DOWNLOAD_DIR, 'pip')
CONDA_CACHE_DIR = os.path.join(DOWNLOAD_DIR, 'conda')  # Fixed typo
INSTALLER_PATH = os.path.join(DOWNLOAD_DIR, INSTALLER_NAME)
INSTALL_DIR = os.path.join(SCRIPT_DIR, ENV)  # Install location for Miniforge
CONDA_BIN = os.path.join(INSTALL_DIR, BIN_DIR, f"conda{EXE_SUFFIX}")
PIP_BIN = os.path.join(INSTALL_DIR, BIN_DIR, f"pip{EXE_SUFFIX}")
PYTHON_BIN = os.path.join(INSTALL_DIR, BIN_DIR, f"python{EXE_SUFFIX}")

class CleanEnvFakeHome:
    """
    Create a temporary home directory to prevent modification of global user settings.
    Also unsets PYTHONPATH to avoid conflicts.
    """

    def __init__(self, dir_):
        self._dir = dir_
        self._temp_home = os.path.join(self._dir, 'temp_home')

    def __enter__(self):
        """Set HOME/USERPROFILE to a temporary directory and remove PYTHONPATH."""
        os.makedirs(self._temp_home, exist_ok=True)
        self._env_bak = os.environ.copy()
        if IS_WINDOWS:
            os.environ['USERPROFILE'] = self._temp_home  # Set temporary USERPROFILE on Windows
        else:
            os.environ['HOME'] = self._temp_home  # Set temporary HOME on Unix
        os.environ.pop('PYTHONPATH', None)  # Remove PYTHONPATH if it exists

    def __exit__(self, exc_type, exc_value, traceback):
        """Restore original environment variables."""
        os.environ.clear()
        os.environ.update(self._env_bak)
        shutil.rmtree(self._temp_home, ignore_errors=True)

    def __call__(self, func):
        """Allow using FakeHome as a decorator."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self:
                return func(*args, **kwargs)
        return wrapper       

def check_miniforge():
    """Returns True if Miniforge is installed, False otherwise."""
    return os.path.exists(CONDA_BIN)

@CleanEnvFakeHome(SCRIPT_DIR)
def download_miniforge():
    """Download Miniforge installer if not present."""
    if not os.path.exists(INSTALLER_PATH):
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        print(f"⬇ Downloading Miniforge {MINIFORGE_VERSION}...")
        urllib.request.urlretrieve(MINIFORGE_URL, INSTALLER_PATH)
        print("✔ Download complete.")

@CleanEnvFakeHome(SCRIPT_DIR)
def install_miniforge():
    """Install Miniforge without modifying the user's shell settings."""
    if not check_miniforge():
        print("⚙ Installing Miniforge without modifying user settings...")
        if IS_WINDOWS:
            # Windows installer uses different flags
            # /InstallationType=JustMe - Install for current user only
            # /AddToPath=0 - Don't modify PATH
            # /RegisterPython=0 - Don't register as system Python
            # /S - Silent install
            # /D= - Installation directory (must be last)
            subprocess.run([
                INSTALLER_PATH,
                "/InstallationType=JustMe",
                "/AddToPath=0",
                "/RegisterPython=0",
                "/S",
                f"/D={INSTALL_DIR}"
            ], check=True)
        else:
            subprocess.run(["bash", INSTALLER_PATH, "-b", "-s", "-p", INSTALL_DIR], check=True)
        print("✔ Miniforge installed.")

    # Ensure PIP_CACHE_DIR exists
    os.makedirs(PIP_CACHE_DIR, exist_ok=True)

    # Check if PyYAML is in the cache
    cached_pyyaml = any("pyyaml" in fname.lower() for fname in os.listdir(PIP_CACHE_DIR))

    if cached_pyyaml:
        print("📦 Installing PyYAML from cache...")
        subprocess.run([PIP_BIN, "install", "--no-index", "--find-links", PIP_CACHE_DIR, "PyYAML"], check=True)
    else:
        print("🌐 Downloading and caching PyYAML...")
        subprocess.run([PIP_BIN, "download", "--no-deps", "-d", PIP_CACHE_DIR, "PyYAML"], check=True)
        subprocess.run([PIP_BIN, "install", "--no-index", "--find-links", PIP_CACHE_DIR, "PyYAML"], check=True)

    print("✔ PyYAML installed.")

def main():
    """Ensure Miniforge and PyYAML are installed in a self-contained way."""
    print("🔍 Checking Miniforge setup...")
    download_miniforge()
    install_miniforge()

if __name__ == "__main__":
    main()
