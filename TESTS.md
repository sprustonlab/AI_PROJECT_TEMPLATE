# Testing Requirements

## Minimum CI requirements

All CI tests must **actually execute** the scripts they are testing, not just check that files exist. Syntax validation alone is insufficient — scripts must run without error on each target platform.

### PowerShell compatibility

The CI must test against both PowerShell versions in use:

- **PowerShell 5.1** (Windows PowerShell, ships with Windows 10/11). This is what most Windows users will have by default.
- **PowerShell 7.x** (pwsh, cross-platform). This is what GitHub Actions `windows-latest` uses by default with `shell: pwsh`.

PowerShell 5.1 has stricter/different behavior than 7.x. Known incompatibilities that have caused real bugs:

| Feature | PS 5.1 | PS 7.x |
|---------|--------|--------|
| `Join-Path` arguments | 2 only | 3+ supported |
| File encoding without BOM | System default (CP1252) | UTF-8 |
| `<>` in double-quoted strings | Parse error (reserved operator) | Allowed |

**CI must include a job that runs with PowerShell 5.1** to catch these. On GitHub Actions, use `shell: powershell` (not `shell: pwsh`) for this.

### What each test must do

#### Test 1: `activate.ps1` / `activate`

- **Actually run** the activate script (`. .\activate.ps1` / `source ./activate`)
- Verify expected environment variables are set (`PROJECT_ROOT`, `SLC_BASE`, `SLC_PYTHON`)
- Verify `envs/SLCenv` was created
- Verify `conda` is available
- Must pass on both PS 5.1 and PS 7.x on Windows

#### Test 2: Syntax validation of all `.ps1` scripts

- Parse **every** `.ps1` file in the repo (not a hardcoded list) using `Parser::ParseFile`
- This includes `activate.ps1`, all scripts in `commands/`, and any other `.ps1` files
- Must pass on both PS 5.1 and PS 7.x

#### Test 3: Command scripts

- Verify all `.ps1` command scripts in `commands/` exist and have valid syntax
- Verify bash command scripts in `commands/` exist and are executable

#### Test 4: Python scripts

- Verify `install_SLC.py`, `install_env.py`, `lock_env.py` can be imported without error

### Implementation notes

To run a CI step with PowerShell 5.1 on GitHub Actions Windows runners:

```yaml
- name: Test with PowerShell 5.1
  shell: powershell    # <-- PS 5.1 (not pwsh)
  run: |
    . .\activate.ps1
```

To run with PowerShell 7.x:

```yaml
- name: Test with PowerShell 7.x
  shell: pwsh          # <-- PS 7.x
  run: |
    . .\activate.ps1
```

Both should be present in the Windows CI workflow.
