"""File index for fuzzy file search - uses git ls-files with fallback."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from dataclasses import dataclass, field


# Patterns to exclude when not using git
EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".eggs",
    "*.egg-info",
}

EXCLUDE_EXTENSIONS = {".pyc", ".pyo", ".so", ".o", ".a", ".dylib"}


@dataclass
class FileIndex:
    """Cached index of project files for fuzzy searching."""

    root: Path
    files: list[str] = field(default_factory=list)

    async def refresh(self) -> None:
        """Refresh the file list."""
        self.files = await get_project_files(self.root)


async def get_project_files(root: Path, max_files: int = 10000) -> list[str]:
    """Get list of project files, respecting gitignore.

    Uses `git ls-files` if in a git repo, otherwise walks the directory.
    Returns paths relative to root.
    """
    # Try git ls-files first (fast, respects gitignore)
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0:
            files = stdout.decode().strip().split("\n")
            return [f for f in files if f][:max_files]
    except (asyncio.TimeoutError, FileNotFoundError, OSError):
        pass

    # Fallback: walk directory with exclusions
    return await _walk_directory(root, max_files)


async def _walk_directory(root: Path, max_files: int) -> list[str]:
    """Walk directory tree, excluding common noise."""
    files: list[str] = []

    def _walk():
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune excluded directories in-place
            dirnames[:] = [
                d
                for d in dirnames
                if d not in EXCLUDE_DIRS and not d.endswith(".egg-info")
            ]

            rel_dir = Path(dirpath).relative_to(root)

            for filename in filenames:
                if len(files) >= max_files:
                    return
                # Skip excluded extensions and hidden files
                if any(filename.endswith(ext) for ext in EXCLUDE_EXTENSIONS):
                    continue
                if filename.startswith("."):
                    continue

                rel_path = str(rel_dir / filename) if str(rel_dir) != "." else filename
                files.append(rel_path)

    # Run in thread to avoid blocking
    await asyncio.get_event_loop().run_in_executor(None, _walk)
    return files


def fuzzy_match_path(query: str, path: str) -> tuple[float, list[int]]:
    """Fuzzy match a query against a file path.

    Returns (score, matched_indices) where higher score = better match.
    Score of 0 means no match.

    Scoring priorities:
    - Exact substring matches score highest
    - Matches at word boundaries (after /, _, -) score higher
    - Consecutive character matches score higher
    - Matches in filename score higher than in directory
    - Shorter paths get a bonus
    """
    if not query:
        return (1.0, [])

    query_lower = query.lower()
    path_lower = path.lower()

    # Try exact substring match first (highest priority)
    idx = path_lower.find(query_lower)
    if idx != -1:
        # Bonus for matching at word boundary
        boundary_bonus = 0.2 if idx == 0 or path[idx - 1] in "/_-." else 0
        # Bonus for matching in filename (after last /)
        filename_start = path.rfind("/") + 1
        filename_bonus = 0.3 if idx >= filename_start else 0
        # Shorter paths are better
        length_penalty = len(path) / 200
        score = 1.0 + boundary_bonus + filename_bonus - length_penalty
        return (score, list(range(idx, idx + len(query))))

    # Fuzzy matching: find characters in order
    matched_indices: list[int] = []
    query_idx = 0
    consecutive_bonus = 0.0
    boundary_bonus = 0.0
    last_match = -2

    for i, char in enumerate(path_lower):
        if query_idx < len(query_lower) and char == query_lower[query_idx]:
            matched_indices.append(i)

            # Consecutive match bonus
            if i == last_match + 1:
                consecutive_bonus += 0.1

            # Word boundary bonus (after /, _, -, . or at start)
            if i == 0 or path[i - 1] in "/_-.":
                boundary_bonus += 0.15

            last_match = i
            query_idx += 1

    if query_idx < len(query_lower):
        # Didn't match all characters
        return (0.0, [])

    # Base score from match ratio
    base_score = len(query) / len(path)

    # Bonus if matches are in the filename portion
    filename_start = path.rfind("/") + 1
    filename_matches = sum(1 for i in matched_indices if i >= filename_start)
    filename_bonus = 0.2 * (filename_matches / len(query))

    # Length penalty for longer paths
    length_penalty = len(path) / 300

    score = (
        base_score
        + consecutive_bonus
        + boundary_bonus
        + filename_bonus
        - length_penalty
    )
    return (max(0.01, score), matched_indices)


def search_files(
    query: str, files: list[str], limit: int = 20
) -> list[tuple[str, float, list[int]]]:
    """Search files with fuzzy matching.

    Returns list of (path, score, matched_indices) sorted by score descending.
    """
    if not query:
        # Return first N files when no query
        return [(f, 1.0, []) for f in files[:limit]]

    results: list[tuple[str, float, list[int]]] = []
    for path in files:
        score, indices = fuzzy_match_path(query, path)
        if score > 0:
            results.append((path, score, indices))

    # Sort by score descending, then by path length (shorter = better)
    results.sort(key=lambda x: (-x[1], len(x[0])))
    return results[:limit]
