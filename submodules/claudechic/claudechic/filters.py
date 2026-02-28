"""Message filtering for SDK output.

Filters out known noisy/spurious messages from the SDK.
"""

import re

# Patterns to filter out (compiled for performance)
FILTERED_PATTERNS: list[re.Pattern[str]] = [
    # FSWatcher errors from Bun's bundled filesystem
    re.compile(r"\$bunfs/root/claude", re.IGNORECASE),
]


def should_filter_message(message: str) -> bool:
    """Return True if the message should be filtered out."""
    for pattern in FILTERED_PATTERNS:
        if pattern.search(message):
            return True
    return False
