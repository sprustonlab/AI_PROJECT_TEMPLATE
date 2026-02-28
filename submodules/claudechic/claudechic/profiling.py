"""Lightweight profiling utilities for performance analysis."""

import functools
import inspect
import os
import time
from collections import defaultdict
from contextlib import contextmanager

_enabled = os.environ.get("CHIC_PROFILE", "true").lower() != "false"
_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "total": 0.0, "max": 0.0})
_start_time = time.perf_counter()


@contextmanager
def timed(label: str):
    """Context manager to time a block of code."""
    if not _enabled:
        yield
        return
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    _stats[label]["count"] += 1
    _stats[label]["total"] += elapsed
    _stats[label]["max"] = max(_stats[label]["max"], elapsed)


def profile(fn):
    """Decorator to track function call count and timing."""
    if not _enabled:
        return fn
    label = fn.__qualname__

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        elapsed = time.perf_counter() - start
        _stats[label]["count"] += 1
        _stats[label]["total"] += elapsed
        _stats[label]["max"] = max(_stats[label]["max"], elapsed)
        return result

    @functools.wraps(fn)
    async def async_wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await fn(*args, **kwargs)
        elapsed = time.perf_counter() - start
        _stats[label]["count"] += 1
        _stats[label]["total"] += elapsed
        _stats[label]["max"] = max(_stats[label]["max"], elapsed)
        return result

    if inspect.iscoroutinefunction(fn):
        return async_wrapper
    return wrapper


def get_stats_table():
    """Get statistics as a Rich Table (borderless, compact)."""
    from rich.table import Table

    duration = get_session_duration()
    table = Table(
        box=None,
        padding=(0, 4),
        collapse_padding=True,
        show_header=True,
        title=f"[dim]Session duration: {duration:.1f}s[/]",
        title_justify="left",
    )
    table.add_column("Function", style="dim")
    table.add_column("Calls", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Avg", justify="right")
    table.add_column("Max", justify="right")

    for name, data in sorted(_stats.items(), key=lambda x: -x[1]["total"]):
        avg = data["total"] / data["count"] * 1000 if data["count"] else 0
        table.add_row(
            name,
            str(data["count"]),
            f"{data['total'] * 1000:.1f}ms",
            f"{avg:.2f}ms",
            f"{data['max'] * 1000:.2f}ms",
        )
    return table


def get_session_duration() -> float:
    """Get session duration in seconds."""
    return time.perf_counter() - _start_time


def reset_stats() -> None:
    """Reset all profiling statistics and restart session timer."""
    global _start_time
    _stats.clear()
    _start_time = time.perf_counter()


def get_stats_text() -> str:
    """Get statistics as plain text for copying."""
    if not _stats:
        return "No profiling data collected."

    duration = get_session_duration()
    lines = [
        f"Session duration: {duration:.1f}s",
        "",
        f"{'Function':<45} {'Calls':>8} {'Total':>10} {'Avg':>10} {'Max':>10}",
        "-" * 85,
    ]
    for name, data in sorted(_stats.items(), key=lambda x: -x[1]["total"]):
        avg = data["total"] / data["count"] * 1000 if data["count"] else 0
        lines.append(
            f"{name:<45} {data['count']:>8} {data['total'] * 1000:>9.1f}ms {avg:>9.2f}ms {data['max'] * 1000:>9.2f}ms"
        )
    return "\n".join(lines)
