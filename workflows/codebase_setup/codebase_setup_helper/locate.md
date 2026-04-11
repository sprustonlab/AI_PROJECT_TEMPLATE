# Locate Phase

Find and validate the user's existing codebase.

## Steps

1. **Ask for the codebase path.** Ask the user for the absolute path to their codebase.

2. **Validate the path exists.** Check that the directory exists and is readable. If not, report the error and ask again.

3. **Characterize the codebase.** Determine what kind of project it is:
   - **Git repo?** Check for `.git/` directory. Note the current branch and remote if present.
   - **Python package?** Check for `__init__.py` in the top level, or `setup.py` / `pyproject.toml` indicating an installable package.
   - **Plain directory?** If neither of the above, treat as a plain directory of Python files.

4. **Identify the top-level module name.** This is the directory name that users will `import`. Look for:
   - A `src/<name>/` layout (src-layout package)
   - A top-level directory containing `__init__.py`
   - The directory basename as fallback

5. **Confirm with the user.** Summarize what you found (path, type, module name) and ask them to confirm before proceeding.

To advance: user confirms the codebase path and module name are correct.
