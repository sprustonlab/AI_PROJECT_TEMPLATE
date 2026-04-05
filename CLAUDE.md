# CLAUDE.md — Project Conventions

## Environment paths (platform layout)

All installed environments live under `envs/{platform_subdir}/`, not directly under `envs/`.

- Spec files: `envs/{name}.yml` (shared across platforms)
- Lockfiles: `envs/{name}.{platform_subdir}.lock` (per-platform)
- Installed envs: `envs/{platform_subdir}/{name}/`
- Cache dirs: `envs/{platform_subdir}/{name}.cache/`
- SLCenv (base): `envs/{platform_subdir}/SLCenv/`

`platform_subdir` is one of: `win-64`, `osx-arm64`, `osx-64`, `linux-64`.

## Platform detection

Python scripts use `get_platform_subdir()` (defined in `install_SLC.py`, `install_env.py`, `lock_env.py`). It returns the conda platform_subdir string based on `platform.system()` and `platform.machine()`.

Bash uses `_detect_platform()` in `activate`. PowerShell hardcodes `$PLATFORM_SUBDIR = "win-64"`.

The value is exported as `$SLC_PLATFORM` by the activate scripts.

## Output conventions

Python scripts use emoji with ASCII fallback for terminal output. The pattern:

```python
def _supports_emoji():
    if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding:
        return sys.stdout.encoding.lower() in ('utf-8', 'utf8')
    return False

if _supports_emoji():
    E_CHECK = "\u2714"   # ✔
else:
    E_CHECK = "[OK]"
```

Then use `print(f"{E_CHECK} Done.")` — never hardcode emoji in print strings.

PowerShell scripts (`.ps1`) use ASCII-only output (`[OK]`, `[DL]`, etc.) since PS 5.1 console encoding is unreliable.

## Windows compatibility

- **Executables**: `Scripts/conda.exe` on Windows vs `bin/conda` on Unix. Use `get_env_executable()` from `install_env.py` or check `is_windows()`.
- **Home dir**: `USERPROFILE` on Windows, `HOME` on Unix. See `CleanEnvFakeHome` in `install_SLC.py`.
- **Read-only envs**: `chmod -R a-w` on Unix, `icacls /deny Everyone:(W) /T` on Windows.

## PowerShell 5.1 rules

- `Join-Path` takes exactly 2 arguments. Nest calls: `Join-Path (Join-Path $a "b") "c"`
- No `<>` characters inside double-quoted strings (PS 5.1 parsing bug)
- `.ps1` files should have UTF-8 BOM if they contain Unicode literals
- Use `$ProgressPreference = 'SilentlyContinue'` before `Invoke-WebRequest` (PS 5.1 progress bar is extremely slow)
- Use `[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12` before HTTPS calls (PS 5.1 defaults to TLS 1.0)

## Terminology

- **SLCenv**: the base conda environment (Miniforge). Never "base env".
- **Project environment**: a named env like `claudechic` or `jupyter`.
- **Spec file**: `.yml` file. **Lockfile**: `.lock` file.
- **platform_subdir**: the `win-64`/`osx-arm64`/etc. value.
- **Platform layout**: the `envs/{platform_subdir}/{name}` directory structure.

See `specification/terminology.md` for the full glossary (if running the project team workflow).

## Key files

| File | Purpose |
|------|---------|
| `activate` / `activate.ps1` | Project activation (shell setup) |
| `install_SLC.py` | Bootstrap SLCenv (cross-platform, needs Python) |
| `install_SLC.ps1` | Bootstrap SLCenv (Windows-native, no Python needed) |
| `install_env.py` | Install project environments from lockfile/spec |
| `lock_env.py` | Generate platform-specific lockfiles |
| `commands/require_env` / `.ps1` | CLI guard: ensure env is installed and activated |
