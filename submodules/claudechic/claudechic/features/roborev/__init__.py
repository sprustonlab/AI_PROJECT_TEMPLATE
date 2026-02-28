"""Roborev integration - code review panel in sidebar.

Provides review listing and detail display via the roborev CLI.
"""

# Public API - only what app.py and commands.py need
from claudechic.features.roborev.cli import (
    get_current_branch,
    is_roborev_available,
    list_reviews,
    show_review,
)
from claudechic.features.roborev.models import ReviewDetail, ReviewJob

__all__ = [
    "get_current_branch",
    "is_roborev_available",
    "list_reviews",
    "show_review",
    "ReviewDetail",
    "ReviewJob",
]
