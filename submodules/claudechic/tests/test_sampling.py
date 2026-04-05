"""Tests for CPU sampling profiler episodes and async metrics."""

import time

from claudechic.sampling import AsyncMetrics, Episode, Sampler, create


# --- AsyncMetrics ---


def test_async_metrics_record_lag():
    m = AsyncMetrics()
    m.record_lag(0.01)
    m.record_lag(0.05)
    m.record_lag(0.02)
    assert m.lag_count == 3
    assert m.lag_max == 0.05
    assert abs(m.lag_sum - 0.08) < 1e-9


def test_async_metrics_snapshot_resets_lag_max():
    m = AsyncMetrics()
    m.record_lag(0.1)
    m.text_chunks = 42
    snap = m.snapshot_and_reset_lag_max()
    assert snap["lag_max"] == 0.1
    assert snap["text_chunks"] == 42
    # lag_max reset, but cumulative counters preserved
    assert m.lag_max == 0.0
    assert m.text_chunks == 42


def test_async_metrics_reset():
    m = AsyncMetrics()
    m.record_lag(0.1)
    m.text_chunks = 10
    m.tool_uses = 5
    m.reset()
    assert m.lag_max == 0.0
    assert m.lag_count == 0
    assert m.text_chunks == 0


# --- Episode ---


def test_episode_duration():
    ep = Episode(start=100.0, end=106.5, peak_cpu=0.8)
    assert ep.duration == 6.5


def test_episode_hotspots_empty():
    ep = Episode(start=0, end=1, peak_cpu=0.5)
    assert ep.hotspots == []


# --- Sampler state machine (no thread started) ---


def _make_sampler() -> Sampler:
    """Create a Sampler without starting the thread."""
    return Sampler(threshold=0.2)


def test_episode_opens_on_first_hot_cycle():
    """First hot cycle immediately opens an episode."""
    s = _make_sampler()
    assert s._state == "idle"

    s.async_metrics.text_chunks = 10
    s.async_metrics.record_lag(0.03)

    cycle_start = time.time()
    samples = create()
    samples["count"] = 5  # simulate some samples
    s._start_episode(cycle_start, samples, 0.6)

    assert s._state == "high"
    assert s._ep_start == cycle_start
    assert s._ep_peak_cpu == 0.6
    assert s._ep_samples["count"] == 5  # seeded from cycle


def test_episode_lifecycle():
    """Episode opens on first hot cycle, closes after 3 cold cycles."""
    s = _make_sampler()

    # Simulate async activity before episode
    s.async_metrics.text_chunks = 10
    s.async_metrics.tool_uses = 2
    s.async_metrics.record_lag(0.03)

    # First hot cycle -> episode opens immediately
    cycle_start = time.time()
    samples = create()
    samples["count"] = 3
    s._start_episode(cycle_start, samples, 0.7)

    assert s._state == "high"
    assert len(s.episodes) == 0  # not closed yet

    # Simulate more activity during episode
    s.async_metrics.text_chunks = 30
    s.async_metrics.tool_uses = 8
    s.async_metrics.record_lag(0.07)
    s._ep_peak_cpu = 0.85

    # 3 cold cycles -> episode closes
    for _ in range(3):
        s._low_streak += 1
        if s._state == "high" and s._low_streak >= 3:
            s._close_episode()

    assert s._state == "idle"
    assert len(s.episodes) == 1

    ep = s.episodes[0]
    assert ep.peak_cpu == 0.85
    assert ep.text_chunks == 20  # 30 - 10 (delta)
    assert ep.tool_uses == 6  # 8 - 2
    assert ep.lag_max == 0.07
    assert ep.duration > 0


def test_brief_dip_keeps_episode_open():
    """1-2 cold cycles shouldn't close an episode (need 3)."""
    s = _make_sampler()
    s._start_episode(time.time(), create(), 0.5)

    s._low_streak = 2
    if s._state == "high" and s._low_streak >= 3:
        s._close_episode()

    assert s._state == "high"
    assert len(s.episodes) == 0


def test_multiple_episodes():
    """Multiple episodes accumulate in the deque."""
    s = _make_sampler()

    for _ in range(3):
        s._start_episode(time.time(), create(), 0.5)
        s._low_streak = 3
        s._close_episode()

    assert len(s.episodes) == 3


def test_reset_clears_episodes():
    s = _make_sampler()
    s._start_episode(time.time(), create(), 0.5)
    s._low_streak = 3
    s._close_episode()
    assert len(s.episodes) == 1

    s.reset()
    assert len(s.episodes) == 0
    assert s._state == "idle"


def test_episode_lag_scoping():
    """Each episode should capture lag_max only from its own window."""
    s = _make_sampler()

    # Pre-episode lag
    s.async_metrics.record_lag(0.5)

    # Open episode (snapshot resets lag_max)
    s._start_episode(time.time(), create(), 0.6)

    # Episode-scoped lag
    s.async_metrics.record_lag(0.02)

    # Close
    s._low_streak = 3
    s._close_episode()

    ep = s.episodes[0]
    assert ep.lag_max == 0.02  # not 0.5 from before
