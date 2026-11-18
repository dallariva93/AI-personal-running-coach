"""Unit tests for the plan-session → structured-workout projection (Fase E)."""

from __future__ import annotations

from app.processing.workout_segments import build_session_segments


def test_easy_is_a_single_segment():
    segs = build_session_segments("easy", 8.0, "5:30/km")
    assert [s.segment_type for s in segs] == ["easy"]
    assert segs[0].work_distance_km == 8.0
    assert segs[0].work_pace == "5:30/km"


def test_tempo_has_warmup_work_cooldown_that_sum_to_total():
    segs = build_session_segments("tempo", 9.0, "4:40/km")
    assert [s.segment_type for s in segs] == ["warmup", "threshold", "cooldown"]
    total = sum(s.work_distance_km * s.repetitions for s in segs)
    assert abs(total - 9.0) < 0.05  # nothing dropped
    assert segs[1].work_pace == "4:40/km"


def test_intervals_block_reflects_goal_distance():
    marathon = build_session_segments("intervals", 12.0, "4:15/km", "marathon")
    short = build_session_segments("intervals", 11.5, "3:55/km", "10k")
    block_m = next(s for s in marathon if s.segment_type == "interval_block")
    block_s = next(s for s in short if s.segment_type == "interval_block")
    assert (block_m.repetitions, block_m.work_distance_km) == (5, 1.5)
    assert (block_s.repetitions, block_s.work_distance_km) == (6, 1.0)
    assert block_m.rest_duration_sec and block_m.rest_type == "jog"


def test_strides_appends_a_strides_block():
    segs = build_session_segments("strides", 6.0, "5:30/km")
    assert [s.segment_type for s in segs] == ["easy", "strides"]
    assert segs[1].repetitions == 5


def test_long_is_single_steady_segment():
    segs = build_session_segments("long", 22.0, "5:45/km")
    assert len(segs) == 1
    assert segs[0].work_distance_km == 22.0


def test_rest_race_cross_have_no_segments():
    assert build_session_segments("rest", None, None) == []
    assert build_session_segments("race", None, None) == []
    assert build_session_segments("cross", None, 45.0) == []


def test_positions_are_sequential():
    segs = build_session_segments("intervals", 12.0, "4:15/km", "marathon")
    assert [s.position for s in segs] == [0, 1, 2]
