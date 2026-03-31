#!/usr/bin/env python3
"""Post-generation: integrate an existing codebase into the project.

Called by copier _tasks when existing_codebase is provided.
Usage: python3 scripts/integrate_codebase.py /path/to/codebase [link_mode]

link_mode: "symlink" (default on Linux/macOS) or "copy" (default on Windows)
"""
import os
import platform
import shutil
import sys
from pathlib import Path

if len(sys.argv) < 2 or not sys.argv[1]:
    sys.exit(0)  # No codebase specified, nothing to do

codebase = Path(sys.argv[1]).expanduser().resolve()
link_mode = sys.argv[2] if len(sys.argv) > 2 else ""
project_root = Path('.').resolve()
repos_dir = project_root / 'repos'

# 1. Validate path
if not codebase.is_dir():
    print(f'❌ Error: existing_codebase path does not exist or is not a directory: {codebase}')
    sys.exit(1)

# 2. Determine link mode (gate symlinks on OS)
is_windows = platform.system() == 'Windows'
if not link_mode:
    link_mode = 'copy' if is_windows else 'symlink'
elif link_mode == 'symlink' and is_windows:
    print('⚠️  Symlinks require admin privileges on Windows. Falling back to copy.')
    link_mode = 'copy'

# 3. Detect existing tooling
print(f'Integrating existing codebase: {codebase}')
detected = []
for marker in ['.git', 'environment.yml', 'requirements.txt', '.claude', 'pyproject.toml']:
    if (codebase / marker).exists():
        detected.append(marker)
if detected:
    joined = ', '.join(detected)
    print(f'  Detected existing tooling: {joined}')

# 4. Link or copy into repos/
repos_dir.mkdir(parents=True, exist_ok=True)
target = repos_dir / codebase.name
if target.exists() or target.is_symlink():
    print(f'  ⚠️  {target} already exists — skipping')
elif link_mode == 'symlink':
    try:
        target.symlink_to(codebase)
        print(f'  ✔ Linked {codebase.name} → repos/{codebase.name}/')
    except OSError as e:
        print(f'  ⚠️  Symlink failed ({e}), falling back to copy.')
        shutil.copytree(str(codebase), str(target))
        print(f'  ✔ Copied {codebase.name} → repos/{codebase.name}/')
else:
    shutil.copytree(str(codebase), str(target))
    print(f'  ✔ Copied {codebase.name} → repos/{codebase.name}/')

print(f'  ✔ PYTHONPATH: activate script already adds repos/*/ to PYTHONPATH')

# 5. Handle .claude/ conflicts
existing_claude = codebase / '.claude'
template_claude = project_root / '.claude'
if existing_claude.is_dir() and template_claude.is_dir():
    print()
    print(f'⚠️  Existing .claude/ directory detected at {existing_claude}')
    print()

    # Find what template wants to add
    template_files = set()
    for f in template_claude.rglob('*'):
        if f.is_file():
            template_files.add(f.relative_to(template_claude))

    # Find what already exists
    existing_files = set()
    for f in existing_claude.rglob('*'):
        if f.is_file():
            existing_files.add(f.relative_to(existing_claude))

    new_files = template_files - existing_files
    conflict_files = template_files & existing_files
    existing_only = existing_files - template_files

    if new_files:
        print('  The template wants to add these files:')
        for f in sorted(new_files):
            print(f'    + .claude/{f}')

    if existing_only:
        print()
        print('  These files already exist in your codebase (not overwritten):')
        for f in sorted(existing_only):
            print(f'    ≡ .claude/{f}')

    if conflict_files:
        print()
        print('  These files exist in BOTH (review manually):')
        for f in sorted(conflict_files):
            print(f'    ⚡ .claude/{f}')

    print()
    print('  Please review and merge manually:')
    if is_windows:
        print(f'    xcopy /s /y .claude\\commands\\* "{existing_claude}\\commands\\"')
        print(f'    xcopy /s /y .claude\\guardrails\\* "{existing_claude}\\guardrails\\"')
    else:
        print(f'    cp -n .claude/commands/* {existing_claude}/commands/ 2>/dev/null')
        print(f'    cp -n .claude/guardrails/* {existing_claude}/guardrails/ 2>/dev/null')
    print()
