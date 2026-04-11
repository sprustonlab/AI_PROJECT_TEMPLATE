# Environment Phase

Scan the codebase for dependencies and configure the project environment.

## Steps

1. **Scan for dependency files.** Check the integrated codebase at `repos/<name>/` for:
   - `requirements.txt` -- pip requirements
   - `setup.py` or `setup.cfg` -- setuptools metadata with `install_requires`
   - `pyproject.toml` -- PEP 621 dependencies or tool-specific sections
   - `environment.yml` -- conda/mamba environment spec

2. **Report what you found.** List each discovered file and summarize the dependencies it declares. Flag any version conflicts or unusual requirements.

3. **Propose environment integration.** Suggest how to add the discovered dependencies to the project's pixi environment:
   - For conda-available packages: add as pixi dependencies
   - For pip-only packages: add under `[pypi-dependencies]` in `pixi.toml`
   - If an `environment.yml` exists, offer to merge its channels and dependencies

4. **Apply with user approval.** Only modify `pixi.toml` after the user confirms. Run `pixi install` to resolve and install.

5. **Note about PYTHONPATH.** Remind the user that `repos/<name>` is already on `PYTHONPATH` via the activate script -- no need to `pip install -e` the codebase unless they specifically want to.

To advance: user confirms the environment is configured and dependencies are resolved (or explicitly skips if there are none).
