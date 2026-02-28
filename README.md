# Template Repository

A reusable template for bootstrapping new research projects with integrated environment management, Claude Code project team workflow, and consistent project structure.

## Requirements

- **Platform**: Linux, macOS, or Windows WSL
- **Python**: Python 3.8 or higher
- **Network**: Internet connection for first-time setup

## Quick Start

1. Clone this repository:
   ```bash
   git clone <url> <project-name>
   cd <project-name>
   ```

2. Initialize submodules (for claudechic MCP server):
   ```bash
   git submodule update --init --recursive
   ```

3. Activate the environment:
   ```bash
   source activate
   ```

   On first run, this will:
   - Install SLC (Miniforge) automatically
   - Set up paths and environment variables
   - Display available commands and skills

4. (Optional) Create a project-specific environment:
   ```bash
   # Edit envs/myenv.yml with your dependencies
   python lock_env.py myenv
   python install_env.py myenv
   conda activate myenv
   ```

## Customization

### Customize the activate script:
- **Line ~165**: Change `PROJECT_NAME="my-project"` to your project name
- **Section 2**: Add project-specific modules to PYTHONPATH
- **Section 3**: Add checks for additional submodules

### What to modify:
- This README
- `envs/*.yml` - your environment definitions
- `commands/*` - your CLI scripts
- `modules/`, `repos/` - your code

### What to keep as-is:
- `activate` script (except CUSTOMIZE sections)
- `install_SLC.py`, `install_env.py`, `lock_env.py`
- `.gitignore` patterns
- `AI_agents/` directory
- `.claude/commands/` structure

## Available Commands

Run `source activate` to see available CLI commands and Claude Code skills.

## AI_agents/ Version

Copied from: postdoc_monorepo @ commit 5fa199729c6bd586d2c46697597d0f33b8a7503c
Date: 2026-02-27
