"""Chicsession management — named multi-agent session snapshots.

A chicsession is a named snapshot of agents persisted at
`<root>/.chicsessions/<name>.json`. Save and restore — that's it.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class ChicsessionEntry:
    """One agent within a chicsession snapshot."""

    name: str
    session_id: str
    cwd: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "session_id": self.session_id,
            "cwd": self.cwd,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ChicsessionEntry:
        return cls(
            name=data["name"],
            session_id=data["session_id"],
            cwd=data["cwd"],
        )


@dataclass
class Chicsession:
    """A named multi-agent session snapshot."""

    name: str
    active_agent: str
    agents: list[ChicsessionEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "active_agent": self.active_agent,
            "agents": [a.to_dict() for a in self.agents],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Chicsession:
        return cls(
            name=data["name"],
            active_agent=data["active_agent"],
            agents=[ChicsessionEntry.from_dict(a) for a in data.get("agents", [])],
        )


class ChicsessionManager:
    """Manages chicsession files in `<root_dir>/.chicsessions/`."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self._dir = root_dir / ".chicsessions"

    def _chicsession_path(self, name: str) -> Path:
        return self._dir / f"{name}.json"

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, chicsession: Chicsession) -> None:
        """Atomic write: write to temp file then os.replace."""
        self._ensure_dir()
        target = self._chicsession_path(chicsession.name)
        content = json.dumps(chicsession.to_dict(), indent=2) + "\n"
        fd, tmp_path = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, target)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def load(self, name: str) -> Chicsession:
        """Load a chicsession from disk. Raises FileNotFoundError or ValueError."""
        path = self._chicsession_path(name)
        if not path.exists():
            raise FileNotFoundError(f"Chicsession '{name}' not found")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Chicsession.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise ValueError(f"Corrupt chicsession file '{name}': {e}") from e

    def list_chicsessions(self) -> list[str]:
        """List available chicsession names."""
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.json") if p.is_file())
