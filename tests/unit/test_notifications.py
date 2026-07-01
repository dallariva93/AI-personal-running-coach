"""Unit tests for notification filtering (P3-2: time-window, cooldown, priority)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.services.event_service import _in_time_window


def test_time_window_high_always():
    """High priority is always in window."""
    for hour in range(24):
        now = datetime(2026, 6, 22, hour, 0)
        assert _in_time_window("high", now) is True


def test_time_window_medium_daytime():
    now = datetime(2026, 6, 22, 10, 0)
    assert _in_time_window("medium", now) is True
    now = datetime(2026, 6, 22, 23, 0)
    assert _in_time_window("medium", now) is False
    now = datetime(2026, 6, 22, 5, 0)
    assert _in_time_window("medium", now) is False


def test_time_window_low_narrow():
    now = datetime(2026, 6, 22, 10, 0)
    assert _in_time_window("low", now) is True
    now = datetime(2026, 6, 22, 7, 0)
    assert _in_time_window("low", now) is False
    now = datetime(2026, 6, 22, 22, 0)
    assert _in_time_window("low", now) is False


def test_time_window_none_defaults_medium():
    now = datetime(2026, 6, 22, 10, 0)
    assert _in_time_window(None, now) is True
    now = datetime(2026, 6, 22, 23, 0)
    assert _in_time_window(None, now) is False
