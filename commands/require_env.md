# require_env - Auto-Install SLC and Environments

## Overview

`require_env` is a utility command that automatically installs the SLC base environment and specific SLC environments as needed. It's designed to:

- Bootstrap the SLC installation on fresh systems
- Declare environment dependencies in scripts
- Enable auto-installation during activation (controlled by `AUTO_INSTALL_SLC` variable)
- Provide both check and install modes

## Usage

### Basic Usage

```bash
# Ensure SLC base environment is installed
./commands/require_env

# Ensure SLC + suite2p environment are installed
./commands/require_env suite2p

# Check without installing (exits with error if missing)
./commands/require_env --check-only
./commands/require_env --check-only jupyter
```

### After Activation

Once the monorepo is activated, `require_env` is available on PATH:

```bash
source activate

# Use without path prefix
require_env
require_env cognitivemap
require_env --check-only suite2p_2025
```

### In Scripts

Declare environment dependencies at the top of scripts:

```bash
#!/bin/bash
# Ensure suite2p environment is available
require_env suite2p || exit 1

# Rest of script...
```

## How It Works

### Detection Logic

**SLC Base Installation:**
- Checks if `submodules/SLC/envs/SLCenv/bin/conda` exists
- This is the conda executable in the SLC base environment

**Environment Installation:**
- Checks if `submodules/SLC/envs/<env_name>/` directory exists
- Environment must have a corresponding `submodules/SLC/envs/<env_name>.yml` file

### Installation Process

**SLC Base:**
1. Runs `python3 submodules/SLC/install_SLC.py` using system Python3
2. Creates `submodules/SLC/envs/SLCenv/` with Miniforge conda/mamba
3. Installs PyYAML in the base environment

**Specific Environments:**
1. Validates environment YAML exists
2. Sets required environment variables (`SLC_BASE`, `SLC_PYTHON`, etc.)
3. Sources conda initialization scripts
4. Activates SLCenv
5. Calls `python submodules/SLC/install_env.py <env_name>`
6. Deactivates conda (cleanup)

The key challenge is that `install_env.py` validates it's running in an activated SLC environment. To solve this, `require_env` manually sets the required environment variables and activates conda in a subshell before calling `install_env.py`.

## Available Environments

As of the current version, these environments can be installed:

- `suite2p` - Suite2P for calcium imaging analysis
- `suite2p_2025` - Updated Suite2P version
- `jupyter` - Jupyter notebook environment
- `cognitivemap` - Cognitive mapping tools

To see the current list:

```bash
ls submodules/SLC/envs/*.yml
```

## Integration with activate

The main `activate` script can automatically call `require_env` to ensure SLC is installed before activation. This is controlled by the `AUTO_INSTALL_SLC` variable:

```bash
# Auto-install enabled (default)
source activate

# Auto-install disabled
AUTO_INSTALL_SLC=false source activate

# Or set in shell before sourcing
export AUTO_INSTALL_SLC=false
source activate
```

When auto-install is enabled:
1. `activate` calls `./commands/require_env` before sourcing `submodules/SLC/activate`
2. If installation fails, a warning is shown but activation continues
3. If SLC is missing, the SLC activation will show its normal error message

## Exit Codes

- `0` - Success (everything installed or already exists)
- `1` - Error (installation failed, missing components in check-only mode, or invalid arguments)

## Error Handling

**Permission Errors:**
```bash
❌ Error: No write permission to submodules/SLC/envs
💡 You may need to check directory permissions
```

**Missing Environment:**
```bash
❌ Error: Environment definition not found: submodules/SLC/envs/nonexistent.yml
💡 Available environments:
    - suite2p
    - suite2p_2025
    - jupyter
    - cognitivemap
```

**Installation Failures:**
- Returns non-zero exit code
- Prints error message from underlying installation script
- Safe to retry after fixing issues

## Design Philosophy

### Idempotent

Safe to call multiple times. If components are already installed, the script detects this and exits successfully without re-installing:

```bash
$ require_env suite2p
✔ SLC base environment is installed
✔ Environment 'suite2p' is already installed
```

### Bootstrap-Friendly

Works before activation (using `./commands/require_env`) and after activation (using `require_env` from PATH). This solves the chicken-and-egg problem of needing SLC to install SLC.

### Non-Interactive

Designed for use in scripts and automation. Uses exit codes to signal success/failure rather than prompting for input.

### Environment Isolation

Runs installation in a subshell to avoid polluting the parent shell's environment variables. After installation, the parent shell remains clean.

## Implementation Details

### Why Not Just Source activate?

The `submodules/SLC/activate` script fails gracefully if SLCenv is missing (returns 0 to prevent SSH disconnection). We can't simply source it in a subprocess because:

1. Sourcing in a subprocess doesn't affect the parent shell
2. `activate` returns 0 even on failure (by design)
3. We need to call `install_env.py` which validates environment variables

### Environment Variables Required

For `install_env.py` to work, these must be set:

```bash
SLC_BASE=$SLC_DIR                        # Path to SLC directory
SLC_PYTHON=$SLC_DIR/envs/SLCenv/bin/python  # SLCenv Python (must match sys.executable)
PYTHONPATH=$SLC_DIR/modules:$PYTHONPATH     # Include modules
CONDA_ENVS_PATH=$SLC_DIR/envs:$CONDA_ENVS_PATH  # Environment discovery
PATH=$SLC_DIR/envs/SLCenv/bin:$PATH         # Include conda/mamba
```

### Conda Activation Sequence

```bash
# Source conda initialization
source $SLC_DIR/envs/SLCenv/etc/profile.d/conda.sh
source $SLC_DIR/envs/SLCenv/etc/profile.d/mamba.sh

# Activate
conda activate $SLC_DIR/envs/SLCenv

# Run install_env.py (sees our env vars)
$SLC_PYTHON $SLC_DIR/install_env.py $env_name

# Cleanup
conda deactivate
```

## Troubleshooting

### Installation hangs or fails

Check the underlying installation logs. For SLC base:
```bash
# Run directly to see full output
python3 submodules/SLC/install_SLC.py
```

For environments:
```bash
# Activate first, then install
source submodules/SLC/activate
python submodules/SLC/install_env.py <env_name>
```

### Permission denied errors

Ensure you have write access to `submodules/SLC/envs/`:
```bash
ls -la submodules/SLC/envs/
# Should show your user or group with write permission
```

### Environment not found

List available environments:
```bash
ls submodules/SLC/envs/*.yml
```

Only environments with YAML definitions can be installed.

## Examples

### Fresh System Bootstrap

```bash
# Clone repo
git clone <repo-url> postdoc_monorepo
cd postdoc_monorepo

# Install SLC base
./commands/require_env

# Activate (SLC now exists)
source activate

# Install suite2p when needed
require_env suite2p
```

### Script with Environment Dependency

```bash
#!/bin/bash
# analyze.sh - Requires suite2p environment

# Ensure suite2p is installed
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/commands/require_env" suite2p || {
    echo "Failed to install suite2p environment"
    exit 1
}

# Activate monorepo
source "$SCRIPT_DIR/activate"

# Activate suite2p
conda activate suite2p

# Run analysis
python my_analysis.py "$@"
```

### Conditional Installation

```bash
# Only install if not already present
if ! ./commands/require_env --check-only jupyter; then
    echo "Jupyter not installed, installing now..."
    ./commands/require_env jupyter
fi
```

## Future Enhancements

Potential improvements for future versions:

- Support for `--force` flag to reinstall environments
- Parallel installation of multiple environments
- Progress indicators for long installations
- Logging of installation attempts
- Version checking and upgrade detection
