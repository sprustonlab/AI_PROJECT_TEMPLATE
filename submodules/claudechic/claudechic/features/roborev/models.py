"""Dataclasses for roborev review data."""

from __future__ import annotations

from dataclasses import dataclass, field


def _str_id(value: object) -> str:
    """Coerce an ID (int, str, or None) to str. None becomes ""."""
    return "" if value is None else str(value)


def normalize_status(status: object) -> str:
    """Coerce a status value to a lowercase string, safely."""
    if status is None:
        return ""
    if not isinstance(status, str):
        return str(status).lower()
    return status.lower()


# Statuses that mean the review is still in progress
RUNNING_STATUSES = frozenset({"running", "queued", "pending"})

# Statuses shown in the sidebar/list (running + completed)
VISIBLE_STATUSES = RUNNING_STATUSES | {"done"}


@dataclass
class ReviewJob:
    """A single roborev review job from `roborev list --json`."""

    id: str
    git_ref: str = ""
    branch: str = ""
    agent: str = ""
    status: str = ""
    verdict: str = ""  # "pass", "fail", or ""
    addressed: bool = False
    commit_subject: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> ReviewJob:
        return cls(
            id=_str_id(data.get("id")),
            git_ref=data.get("git_ref") or "",
            branch=data.get("branch") or "",
            agent=data.get("agent") or "",
            status=data.get("status") or "",
            verdict=data.get("verdict") or "",
            addressed=bool(data.get("addressed", False)),
            commit_subject=str(data.get("commit_subject") or ""),
        )


@dataclass
class ReviewDetail:
    """Detailed review from `roborev show --json --job <id>`."""

    id: str
    job_id: str = ""
    agent: str = ""
    output: str = ""
    addressed: bool = False
    job: ReviewJob | None = field(default=None)

    @classmethod
    def from_dict(cls, data: dict) -> ReviewDetail:
        job_data = data.get("job")
        job = ReviewJob.from_dict(job_data) if isinstance(job_data, dict) else None
        return cls(
            id=_str_id(data.get("id")),
            job_id=_str_id(data.get("job_id")),
            agent=data.get("agent") or "",
            output=data.get("output") or "",
            addressed=bool(data.get("addressed", False)),
            job=job,
        )
