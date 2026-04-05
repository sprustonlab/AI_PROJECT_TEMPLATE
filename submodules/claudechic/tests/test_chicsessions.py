"""Tests for claudechic.chicsessions module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claudechic.chicsessions import (
    Chicsession,
    ChicsessionEntry,
    ChicsessionManager,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def mgr(root: Path) -> ChicsessionManager:
    return ChicsessionManager(root)


# --- ChicsessionEntry ---


class TestChicsessionEntry:
    def test_round_trip(self):
        entry = ChicsessionEntry(
            name="Worker",
            session_id="abc-123",
            cwd="/tmp/project",
        )
        d = entry.to_dict()
        assert d["name"] == "Worker"
        assert d["session_id"] == "abc-123"
        assert d["cwd"] == "/tmp/project"
        restored = ChicsessionEntry.from_dict(d)
        assert restored.name == "Worker"
        assert restored.session_id == "abc-123"
        assert restored.cwd == "/tmp/project"


# --- Chicsession ---


class TestChicsession:
    def test_round_trip(self):
        cs = Chicsession(name="test", active_agent="main")
        d = cs.to_dict()
        restored = Chicsession.from_dict(d)
        assert restored.name == "test"
        assert restored.active_agent == "main"
        assert restored.agents == []

    def test_with_agents(self):
        entry = ChicsessionEntry(
            name="A",
            session_id="id-1",
            cwd="/tmp/a",
        )
        cs = Chicsession(name="x", active_agent="A", agents=[entry])
        restored = Chicsession.from_dict(cs.to_dict())
        assert len(restored.agents) == 1
        assert restored.agents[0].name == "A"
        assert restored.agents[0].cwd == "/tmp/a"


# --- ChicsessionManager ---


class TestSave:
    def test_save_creates_file(self, mgr: ChicsessionManager, root: Path):
        cs = Chicsession(name="my-session", active_agent="main", agents=[])
        mgr.save(cs)
        assert (root / ".chicsessions" / "my-session.json").exists()

    def test_overwrite(self, mgr: ChicsessionManager):
        cs = Chicsession(name="ow", active_agent="main", agents=[])
        mgr.save(cs)
        cs.agents.append(
            ChicsessionEntry(name="X", session_id="s1", cwd="/tmp")
        )
        mgr.save(cs)
        loaded = mgr.load("ow")
        assert len(loaded.agents) == 1
        assert loaded.agents[0].name == "X"

    def test_no_temp_files_left(self, mgr: ChicsessionManager, root: Path):
        cs = Chicsession(name="clean", active_agent="main", agents=[])
        mgr.save(cs)
        files = list((root / ".chicsessions").iterdir())
        assert all(f.suffix == ".json" for f in files)


class TestLoad:
    def test_load_saved(self, mgr: ChicsessionManager):
        cs = Chicsession(name="loadme", active_agent="main", agents=[])
        mgr.save(cs)
        loaded = mgr.load("loadme")
        assert loaded.name == "loadme"
        assert loaded.active_agent == "main"

    def test_load_missing(self, mgr: ChicsessionManager):
        with pytest.raises(FileNotFoundError, match="not found"):
            mgr.load("nope")

    def test_load_corrupt(self, mgr: ChicsessionManager, root: Path):
        d = root / ".chicsessions"
        d.mkdir(parents=True)
        (d / "bad.json").write_text("not json!!!")
        with pytest.raises(ValueError, match="Corrupt"):
            mgr.load("bad")

    def test_load_missing_key(self, mgr: ChicsessionManager, root: Path):
        d = root / ".chicsessions"
        d.mkdir(parents=True)
        (d / "incomplete.json").write_text(json.dumps({"name": "incomplete"}))
        with pytest.raises(ValueError, match="Corrupt"):
            mgr.load("incomplete")


class TestListChicsessions:
    def test_empty(self, mgr: ChicsessionManager):
        assert mgr.list_chicsessions() == []

    def test_lists_names(self, mgr: ChicsessionManager):
        mgr.save(Chicsession(name="beta", active_agent="main", agents=[]))
        mgr.save(Chicsession(name="alpha", active_agent="main", agents=[]))
        assert mgr.list_chicsessions() == ["alpha", "beta"]
