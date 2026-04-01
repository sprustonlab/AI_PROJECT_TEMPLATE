"""State management for the hints system.

Owns all persistent state: project context, copier answers, hint lifecycle
history, and activation preferences. The single state file lives at
`.claude/hints_state.json` with independent sections for activation and
lifecycle — one file, one atomic write.

This module is the ONLY code that reads/writes `.claude/hints_state.json`.
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# CopierAnswers — parsed .copier-answers.yml
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CopierAnswers:
    """Parsed Copier template answers from .copier-answers.yml.

    This is a stable contract -- Copier generates this file in the destination
    project when the template includes {{_copier_conf.answers_file}}.jinja.

    Graceful fallback: if .copier-answers.yml is missing or corrupt, feature
    flags default to their copier.yml defaults. One source of truth rule:
    missing answers file = user accepted all Copier defaults.
    """

    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, project_root: Path) -> CopierAnswers:
        """Load from .copier-answers.yml, or return all-defaults if missing."""
        answers_file = project_root / ".copier-answers.yml"
        if not answers_file.is_file():
            return cls(raw={})
        try:
            import yaml  # type: ignore[import-untyped]

            data = yaml.safe_load(answers_file.read_text(encoding="utf-8"))
            return cls(raw=data if isinstance(data, dict) else {})
        except Exception:
            return cls(raw={})  # Corrupt file -> same as missing

    # -- Feature-toggle properties (defaults match copier.yml) --

    @property
    def use_guardrails(self) -> bool:
        return bool(self.raw.get("use_guardrails", True))

    @property
    def use_project_team(self) -> bool:
        return bool(self.raw.get("use_project_team", True))

    @property
    def use_pattern_miner(self) -> bool:
        return bool(self.raw.get("use_pattern_miner", False))

    @property
    def use_cluster(self) -> bool:
        return bool(self.raw.get("use_cluster", False))

    @property
    def use_hints(self) -> bool:
        return bool(self.raw.get("use_hints", True))

    @property
    def cluster_scheduler(self) -> str | None:
        if not self.use_cluster:
            return None
        return self.raw.get("cluster_scheduler", "lsf")

    @property
    def project_name(self) -> str:
        return self.raw.get("project_name", "")

    def get(self, key: str, default: Any = None) -> Any:
        """Generic accessor for non-typed answers."""
        return self.raw.get(key, default)


# ---------------------------------------------------------------------------
# ProjectState — read-only context for triggers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectState:
    """Read-only context passed to every TriggerCondition.check().

    Seam discipline: exposes ONLY:
    1. Project root path
    2. CopierAnswers (stable Copier contract)
    3. Context provided by ClaudeChic via evaluate() kwargs
    4. Generic filesystem primitives

    Does NOT expose typed representations of other modules' state.

    Kwargs convention: all ClaudeChic-provided fields are T | None,
    defaulting to None. None means "not provided" or "failed to compute."
    Triggers that depend on a field MUST check for None first.
    """

    root: Path
    copier: CopierAnswers
    session_count: int | None = None

    # --- Generic filesystem primitives ---

    def path_exists(self, relative: str) -> bool:
        """Check if a path exists relative to project root."""
        return (self.root / relative).exists()

    def dir_is_empty(self, relative: str) -> bool:
        """Check if a directory exists and contains no meaningful files.

        Ignores __pycache__, .gitkeep, README.md, .DS_Store, and other
        boilerplate. Returns True if dir doesn't exist (vacuously empty).
        """
        d = self.root / relative
        if not d.is_dir():
            return True
        ignored = {"__pycache__", ".gitkeep", "README.md", ".DS_Store"}
        return not any(
            child.name not in ignored
            for child in d.iterdir()
            if not child.name.startswith(".") or child.name == ".gitkeep"
        )

    def file_contains(self, relative: str, pattern: str) -> bool:
        """Check if a file contains a regex pattern."""
        p = self.root / relative
        if not p.is_file():
            return False
        try:
            return bool(re.search(pattern, p.read_text(encoding="utf-8")))
        except OSError:
            return False

    def count_files_matching(
        self,
        relative_dir: str,
        glob: str,
        exclude_prefixes: tuple[str, ...] = ("_",),
    ) -> int:
        """Count files matching a glob in a directory.

        Args:
            relative_dir: Directory path relative to project root.
            glob: Glob pattern (e.g., "*.py").
            exclude_prefixes: Skip files starting with these prefixes.
        """
        d = self.root / relative_dir
        if not d.is_dir():
            return 0
        return sum(
            1
            for f in d.glob(glob)
            if not any(f.name.startswith(p) for p in exclude_prefixes)
        )

    @classmethod
    def build(cls, project_root: Path, **kwargs: Any) -> ProjectState:
        """Build a ProjectState from a project root and optional kwargs.

        This is the canonical constructor used by the engine. It loads
        CopierAnswers from disk and forwards any ClaudeChic-provided
        context from kwargs.
        """
        root = Path(project_root).resolve()
        copier = CopierAnswers.load(root)
        return cls(
            root=root,
            copier=copier,
            session_count=kwargs.get("session_count"),
        )


# ---------------------------------------------------------------------------
# HintStateStore — lifecycle state for individual hints
# ---------------------------------------------------------------------------

# Default record values for hints never seen before
_DEFAULT_TIMES_SHOWN = 0
_DEFAULT_LAST_SHOWN_TS = None
_DEFAULT_DISMISSED = False

# State file location relative to project root
_STATE_FILE = ".claude/hints_state.json"
_CURRENT_VERSION = 1


class HintStateStore:
    """Manages the lifecycle section of .claude/hints_state.json.

    This is the ONLY class that reads/writes hint lifecycle state.
    Triggers, presenters, and activation logic access state through
    this interface, never directly.

    Graceful degradation:
    - Missing file = fresh start (all hints at zero)
    - Corrupt file = fresh start
    - Future version = fresh start (don't misinterpret)
    """

    def __init__(self, project_root: Path) -> None:
        self._project_root = Path(project_root).resolve()
        self._path = self._project_root / _STATE_FILE
        self._lifecycle: dict[str, dict[str, Any]] = {}
        self._activation: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load state from disk. Graceful on missing/corrupt files."""
        if not self._path.exists():
            self._lifecycle = {}
            self._activation = {"enabled": True, "disabled_hints": []}
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._lifecycle = {}
            self._activation = {"enabled": True, "disabled_hints": []}
            return

        if not isinstance(raw, dict):
            self._lifecycle = {}
            self._activation = {"enabled": True, "disabled_hints": []}
            return

        version = raw.get("version", 0)
        if version > _CURRENT_VERSION:
            # Written by a newer version we don't understand
            self._lifecycle = {}
            self._activation = {"enabled": True, "disabled_hints": []}
            return

        # Load lifecycle section
        lifecycle_raw = raw.get("lifecycle", {})
        if isinstance(lifecycle_raw, dict):
            self._lifecycle = {}
            for hint_id, data in lifecycle_raw.items():
                if not isinstance(data, dict):
                    continue
                self._lifecycle[hint_id] = {
                    "times_shown": data.get("times_shown", _DEFAULT_TIMES_SHOWN),
                    "last_shown_ts": data.get("last_shown_ts", _DEFAULT_LAST_SHOWN_TS),
                    "dismissed": data.get("dismissed", _DEFAULT_DISMISSED),
                    "taught_commands": list(data.get("taught_commands", [])),
                }
        else:
            self._lifecycle = {}

        # Load activation section
        activation_raw = raw.get("activation", {})
        if isinstance(activation_raw, dict):
            self._activation = {
                "enabled": activation_raw.get("enabled", True),
                "disabled_hints": list(activation_raw.get("disabled_hints", [])),
            }
        else:
            self._activation = {"enabled": True, "disabled_hints": []}

    def _ensure_hint(self, hint_id: str) -> dict[str, Any]:
        """Get or create a lifecycle record for a hint."""
        if hint_id not in self._lifecycle:
            self._lifecycle[hint_id] = {
                "times_shown": _DEFAULT_TIMES_SHOWN,
                "last_shown_ts": _DEFAULT_LAST_SHOWN_TS,
                "dismissed": _DEFAULT_DISMISSED,
                "taught_commands": [],
            }
        return self._lifecycle[hint_id]

    # --- Lifecycle query methods ---

    def get_times_shown(self, hint_id: str) -> int:
        """How many times this hint has been shown."""
        return self._ensure_hint(hint_id)["times_shown"]

    def get_last_shown_timestamp(self, hint_id: str) -> float | None:
        """Unix timestamp of last display, or None if never shown."""
        return self._ensure_hint(hint_id)["last_shown_ts"]

    def is_dismissed(self, hint_id: str) -> bool:
        """Whether the user explicitly dismissed this hint."""
        return self._ensure_hint(hint_id)["dismissed"]

    # --- Lifecycle mutation methods ---

    def increment_shown(self, hint_id: str) -> None:
        """Record that the hint was shown. Bumps count and timestamp."""
        rec = self._ensure_hint(hint_id)
        rec["times_shown"] += 1
        rec["last_shown_ts"] = time.time()

    def set_dismissed(self, hint_id: str, dismissed: bool = True) -> None:
        """Mark a hint as dismissed (or un-dismissed)."""
        self._ensure_hint(hint_id)["dismissed"] = dismissed

    def set_last_shown_timestamp(self, hint_id: str, ts: float) -> None:
        """Set the last-shown timestamp to a specific value.

        Note: increment_shown() already updates the timestamp to now.
        This method exists for CooldownPeriod which needs explicit
        timestamp control in record_shown().
        """
        self._ensure_hint(hint_id)["last_shown_ts"] = ts

    # --- Taught commands (learn-command hint) ---

    def get_taught_commands(self, hint_id: str = "learn-command") -> set[str]:
        """Get the set of commands already taught for a hint."""
        rec = self._ensure_hint(hint_id)
        return set(rec.get("taught_commands", []))

    def add_taught_command(self, command: str, hint_id: str = "learn-command") -> None:
        """Record that a command was taught."""
        rec = self._ensure_hint(hint_id)
        taught = rec.get("taught_commands", [])
        if command not in taught:
            taught.append(command)
            rec["taught_commands"] = taught

    # --- Activation section access (for ActivationConfig) ---

    def get_activation_data(self) -> dict[str, Any]:
        """Return a copy of the activation section data."""
        return dict(self._activation)

    def set_activation_data(self, data: dict[str, Any]) -> None:
        """Replace the activation section data."""
        self._activation = dict(data)

    # --- Persistence ---

    def save(self) -> None:
        """Persist state to disk. Atomic write via temp-then-rename.

        Creates parent directories if needed. On write failure, state
        remains in memory (will be retried on next save).
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": _CURRENT_VERSION,
            "activation": self._activation,
            "lifecycle": self._lifecycle,
        }

        # Atomic write: write to temp file in same directory, then rename.
        # Same-directory ensures same filesystem for rename atomicity.
        try:
            fd, tmp_name = tempfile.mkstemp(
                dir=self._path.parent,
                prefix=".hints_state_",
                suffix=".tmp",
            )
            try:
                with open(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                    f.write("\n")
                Path(tmp_name).rename(self._path)
            except BaseException:
                # Clean up temp file on failure
                try:
                    Path(tmp_name).unlink(missing_ok=True)
                except OSError:
                    pass
                raise
        except OSError:
            # Filesystem issue (permissions, disk full, etc.)
            # State remains in memory; next save will retry.
            pass


# ---------------------------------------------------------------------------
# ActivationConfig — user's activation preferences
# ---------------------------------------------------------------------------


class ActivationConfig:
    """Reads/writes the activation section of hints_state.json.

    Determines whether hints are globally enabled and which individual
    hints are disabled. This is a pure boolean filter -- it knows nothing
    about triggers, lifecycle, or presentation.

    Default: globally enabled, no per-hint overrides.
    """

    def __init__(self, store: HintStateStore) -> None:
        self._store = store
        data = store.get_activation_data()
        self._enabled: bool = data.get("enabled", True)
        self._disabled_hints: set[str] = set(data.get("disabled_hints", []))

    def _sync_to_store(self) -> None:
        """Push current state back to the store (not yet persisted to disk)."""
        self._store.set_activation_data(
            {
                "enabled": self._enabled,
                "disabled_hints": sorted(self._disabled_hints),
            }
        )

    def is_active(self, hint_id: str) -> bool:
        """Return True if this hint should enter the pipeline.

        Checked first in the pipeline (cheapest filter -- dict lookup
        before any disk I/O for triggers).
        """
        if not self._enabled:
            return False
        return hint_id not in self._disabled_hints

    def disable_globally(self) -> None:
        """Turn off all hints."""
        self._enabled = False
        self._sync_to_store()

    def enable_globally(self) -> None:
        """Turn hints back on. Preserves per-hint overrides."""
        self._enabled = True
        self._sync_to_store()

    def disable_hint(self, hint_id: str) -> None:
        """Disable a single hint."""
        self._disabled_hints.add(hint_id)
        self._sync_to_store()

    def enable_hint(self, hint_id: str) -> None:
        """Re-enable a single hint. Does NOT reset lifecycle state."""
        self._disabled_hints.discard(hint_id)
        self._sync_to_store()

    @property
    def is_globally_enabled(self) -> bool:
        """Whether hints are globally enabled."""
        return self._enabled

    @property
    def disabled_hints(self) -> frozenset[str]:
        """The set of individually disabled hint IDs."""
        return frozenset(self._disabled_hints)
