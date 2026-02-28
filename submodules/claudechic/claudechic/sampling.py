"""CPU-conditional sampling profiler.

Samples the main thread's stack when CPU usage exceeds a threshold.
Builds a tree structure suitable for flame graph visualization.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections import deque
from typing import Any

import psutil


# Default threshold (fraction, not percentage)
DEFAULT_THRESHOLD = float(os.environ.get("CHIC_SAMPLE_THRESHOLD", "0.20"))

# Frames to skip - these are just waiting/scheduling, not real work
OMIT_FILENAMES = (
    # Python internals
    "asyncio/base_events.py",
    "asyncio/events.py",
    "asyncio/runners.py",
    "asyncio/selector_events.py",
    "selectors.py",
    "threading.py",
    "concurrent/futures",
    "<frozen runpy>",
    "__main__.py",
    # Textual framework internals
    "textual/app.py",
    "textual/timer.py",
    "textual/_callback.py",
    "textual/screen.py",
    "textual/_compositor.py",
    "textual/_styles_cache.py",
    "textual/widget.py",
    "textual/message_pump.py",
)


def create() -> dict[str, Any]:
    """Create an empty profile state tree."""
    return {
        "count": 0,
        "children": {},
        "identifier": "root",
        "description": {"filename": "", "name": "", "line_number": 0, "line": ""},
    }


def identifier(frame) -> str:
    """Create a string identifier from a frame."""
    co = frame.f_code
    return f"{co.co_name};{co.co_filename};{co.co_firstlineno}"


def info_frame(frame) -> dict[str, Any]:
    """Extract frame information for display."""
    co = frame.f_code
    return {
        "filename": co.co_filename,
        "name": co.co_name,
        "line_number": frame.f_lineno,
    }


def should_omit(frame) -> bool:
    """Check if frame should be omitted from profiling."""
    filename = frame.f_code.co_filename
    return any(omit in filename for omit in OMIT_FILENAMES)


def process(frame, child, state, depth: int = 50) -> dict[str, Any] | None:
    """Accumulate a frame stack into the tree structure.

    Walks up the stack (via f_back) and adds counts at each level.
    - At leaf level: skips omitted frames to find an interesting leaf
    - At intermediate level: stops at omitted frames (trims framework boilerplate)
    """
    if depth <= 0 or frame is None:
        return state

    if should_omit(frame):
        if child is None:
            # Leaf level: keep walking to find interesting leaf
            prev = frame.f_back
            if prev is not None:
                return process(prev, None, state, depth - 1)
        # Intermediate or end of stack: stop here
        return state

    prev = frame.f_back
    if prev is not None:
        new_state = process(prev, frame, state, depth - 1)
        if new_state is not None:
            state = new_state

    ident = identifier(frame)
    if ident not in state["children"]:
        state["children"][ident] = {
            "count": 0,
            "description": info_frame(frame),
            "children": {},
            "identifier": ident,
        }

    state["count"] += 1

    if child is not None:
        return state["children"][ident]
    else:
        state["children"][ident]["count"] += 1
        return None


def merge(*states: dict[str, Any]) -> dict[str, Any]:
    """Merge multiple profile states into one."""
    if not states:
        return create()

    result = create()
    result["identifier"] = states[0]["identifier"]
    result["description"] = states[0]["description"]

    for state in states:
        result["count"] += state["count"]
        for ident, child in state["children"].items():
            if ident in result["children"]:
                result["children"][ident] = merge(result["children"][ident], child)
            else:
                result["children"][ident] = child

    return result


def flatten(state: dict[str, Any], min_count: int = 1) -> list[tuple[str, int, dict]]:
    """Flatten tree to list of (identifier, count, description) sorted by count."""
    results = []

    def traverse(node):
        if node["count"] >= min_count and node["identifier"] != "root":
            results.append((node["identifier"], node["count"], node["description"]))
        for child in node["children"].values():
            traverse(child)

    traverse(state)
    results.sort(key=lambda x: -x[1])
    return results


class Sampler(threading.Thread):
    """Sample main thread stack when CPU exceeds threshold."""

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        interval: float = 0.02,
        cycle: float = 2.0,
        maxlen: int = 100,
    ):
        super().__init__(daemon=True, name="CPUSampler")
        self.threshold = threshold
        self.interval = interval
        self.cycle = cycle
        self.main_thread_id = threading.main_thread().ident
        self.log: deque[tuple[float, dict]] = deque(maxlen=maxlen)
        self.running = True
        self.process = psutil.Process()
        self.sample_count = 0
        self.high_cpu_count = 0

    def run(self):
        """Sample main thread stack at intervals when CPU exceeds threshold."""
        current = create()
        cycle_start = time.time()
        # Prime cpu_percent (first call returns 0)
        self.process.cpu_percent()
        time.sleep(0.1)

        while self.running:
            cpu = self.process.cpu_percent() / 100.0

            if cpu > self.threshold:
                self.high_cpu_count += 1
                frames = sys._current_frames()
                if self.main_thread_id in frames:
                    frame = frames[self.main_thread_id]
                    process(frame, None, current)
                    self.sample_count += 1
                    del frame
                del frames

            now = time.time()
            if now - cycle_start > self.cycle:
                if current["count"] > 0:
                    self.log.append((now, current))
                current = create()
                cycle_start = now

            time.sleep(self.interval)

    def stop(self):
        """Signal the sampler thread to stop."""
        self.running = False

    def get_merged_profile(self) -> dict[str, Any]:
        """Get all samples merged into one profile."""
        if not self.log:
            return create()
        return merge(*[entry[1] for entry in self.log])

    def get_stats(self) -> dict[str, Any]:
        """Get sampler statistics."""
        profile = self.get_merged_profile()
        return {
            "sample_count": self.sample_count,
            "recorded_count": profile["count"],
            "high_cpu_count": self.high_cpu_count,
            "threshold": self.threshold,
            "log_entries": len(self.log),
        }

    def reset(self) -> None:
        """Clear all samples and reset counters."""
        self.log.clear()
        self.sample_count = 0
        self.high_cpu_count = 0


# Global sampler instance
_sampler: Sampler | None = None


def start_sampler(threshold: float = DEFAULT_THRESHOLD) -> Sampler:
    """Start the global sampler."""
    global _sampler
    if _sampler is None or not _sampler.is_alive():
        _sampler = Sampler(threshold=threshold)
        _sampler.start()
    return _sampler


def stop_sampler():
    """Stop the global sampler."""
    global _sampler
    if _sampler is not None:
        _sampler.stop()
        _sampler = None


def get_sampler() -> Sampler | None:
    """Get the global sampler instance."""
    return _sampler
