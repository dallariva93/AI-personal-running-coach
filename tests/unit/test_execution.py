"""Unit tests for the Workout Execution Score engine (Roadmap #9)."""

from __future__ import annotations

from app.processing import merge_day_activities, rep_analysis, score_execution
from app.schemas import PlanSessionOut, RunSummary


def _sess(session_type: str, km: float | None = None, dur: float | None = None, pace=None):
    return PlanSessionOut(
        id=1,
        day_of_week=0,
        session_type=session_type,
        title=f"{session_type}",
        target_distance_km=km,
        target_pace=pace,
        target_duration_min=dur,
        completed=False,
    )


def _run(activity_type: str, km: float = 0.0, dur: float = 0.0, pace=None, rpe=None):
    return RunSummary(
        date="2026-06-22",
        activity_type=activity_type,
        distance_km=km,
        duration_min=dur,
        avg_pace=pace,
        rpe=rpe,
    )


def test_skipped_when_no_activity():
    r = score_execution(_sess("easy", km=8.0), None, "2026-06-22")
    assert r.execution_status == "skipped"
    assert r.execution_score == 0.0


def test_completed_well_on_match():
    r = score_execution(_sess("easy", km=8.0), _run("easy", km=8.0, dur=48.0), "2026-06-22")
    assert r.execution_status == "completed_well"
    assert r.execution_score >= 75


def test_too_short():
    r = score_execution(_sess("long", km=20.0), _run("lungo", km=10.0), "2026-06-22")
    assert r.execution_status == "too_short"
    assert r.execution_score < 60


def test_turned_easy_when_quality_run_easy():
    r = score_execution(_sess("intervals", km=10.0), _run("easy", km=10.0), "2026-06-22")
    assert r.execution_status == "turned_easy"


def test_too_hard_on_easy_day():
    r = score_execution(_sess("easy", km=8.0), _run("intervalli", km=8.0), "2026-06-22")
    assert r.execution_status == "too_hard"


def test_volume_excess():
    r = score_execution(_sess("easy", km=6.0), _run("easy", km=12.0), "2026-06-22")
    assert r.execution_status == "volume_excess"


def test_rpe_flags_hard_easy_day():
    r = score_execution(
        _sess("easy", km=8.0), _run("easy", km=8.0, rpe=9), "2026-06-22"
    )
    assert any("RPE" in e for e in r.evidence)


def test_evidence_present():
    r = score_execution(_sess("tempo", km=10.0), _run("tempo", km=10.0), "2026-06-22")
    assert r.evidence
    assert r.plan_session_id == 1


# ── P0-5: HR time-in-zone check ──────────────────────────────────────────────

def _run_with_hr(activity_type, km, dur=0.0, hr_zones=None, pace=None, rpe=None):
    return RunSummary(
        date="2026-06-22",
        activity_type=activity_type,
        distance_km=km,
        duration_min=dur,
        avg_pace=pace,
        rpe=rpe,
        hr_zones=hr_zones,
    )


def test_quality_session_low_time_in_zone_penalized():
    """Quality session with <20% time in Z3+ gets penalized."""
    r = score_execution(
        _sess("intervals", km=10.0),
        _run_with_hr("intervalli", km=10.0, dur=50.0,
                     hr_zones={"z1": 300, "z2": 200, "z3": 50}),
        "2026-06-22",
    )
    assert r.time_in_zone_pct is not None
    assert r.time_in_zone_pct < 20
    assert any("zona insufficiente" in e.lower() for e in r.evidence)
    assert r.intensity_score < 100


def test_quality_session_good_time_in_zone_not_penalized():
    """Quality session with >=20% time in Z3+ is not penalized for zones."""
    r = score_execution(
        _sess("intervals", km=10.0),
        _run_with_hr("intervalli", km=10.0, dur=50.0,
                     hr_zones={"z1": 100, "z2": 100, "z3": 300, "z4": 100}),
        "2026-06-22",
    )
    assert r.time_in_zone_pct is not None
    assert r.time_in_zone_pct >= 20
    assert not any("zona insufficiente" in e.lower() for e in r.evidence)


def test_easy_session_too_much_hard_zone_penalized():
    """Easy session with <60% in Z1-Z2 gets penalized."""
    r = score_execution(
        _sess("easy", km=8.0),
        _run_with_hr("easy", km=8.0, dur=48.0,
                     hr_zones={"z1": 100, "z2": 100, "z3": 300, "z4": 80}),
        "2026-06-22",
    )
    assert r.time_in_zone_pct is not None
    assert r.time_in_zone_pct < 60
    assert any("zona facile" in e.lower() for e in r.evidence)


def test_easy_session_mostly_easy_zone_not_penalized():
    """Easy session with >=60% in Z1-Z2 is fine."""
    r = score_execution(
        _sess("easy", km=8.0),
        _run_with_hr("easy", km=8.0, dur=48.0,
                     hr_zones={"z1": 600, "z2": 300, "z3": 50}),
        "2026-06-22",
    )
    assert r.time_in_zone_pct is not None
    assert r.time_in_zone_pct >= 60
    assert not any("troppo tempo fuori" in e.lower() for e in r.evidence)


def test_no_hr_zones_no_time_in_zone_pct():
    """When hr_zones is None, time_in_zone_pct stays None and no penalty."""
    r = score_execution(
        _sess("intervals", km=10.0),
        _run("intervalli", km=10.0, dur=50.0),
        "2026-06-22",
    )
    assert r.time_in_zone_pct is None


# ── P0-5: sub-scores ─────────────────────────────────────────────────────────

def test_sub_scores_populated_on_match():
    r = score_execution(
        _sess("easy", km=8.0),
        _run("easy", km=8.0, dur=48.0),
        "2026-06-22",
    )
    assert r.volume_score is not None
    assert r.intensity_score is not None
    assert r.pace_score is not None
    assert r.structure_score is not None


def test_distribution_score_from_splits():
    """Distribution score computed when >=3 splits available."""
    r = score_execution(
        _sess("easy", km=8.0),
        RunSummary(
            date="2026-06-22",
            activity_type="easy",
            distance_km=8.0,
            duration_min=48.0,
            avg_pace="6:00",
            splits_km=["6:00", "6:01", "5:59", "6:00", "6:02", "5:58", "6:01", "6:00"],
        ),
        "2026-06-22",
    )
    assert r.distribution_score is not None
    assert 40.0 <= r.distribution_score <= 100.0


def test_distribution_score_none_without_splits():
    r = score_execution(
        _sess("easy", km=8.0),
        _run("easy", km=8.0, dur=48.0),
        "2026-06-22",
    )
    assert r.distribution_score is None


# ── P0-6: _status rewrite ────────────────────────────────────────────────────

def test_status_intensity_takes_priority_over_too_short():
    """Intensity status should surface before too_short (P0-6 priority)."""
    r = score_execution(
        _sess("intervals", km=10.0),
        _run("easy", km=6.0),
        "2026-06-22",
    )
    assert r.execution_status == "turned_easy"


def test_status_volume_excess_dominates():
    """Volume excess is safety-relevant and always surfaces first."""
    r = score_execution(
        _sess("easy", km=6.0),
        _run("intervalli", km=10.0),
        "2026-06-22",
    )
    assert r.execution_status == "volume_excess"


def test_status_completed_well_when_score_high():
    r = score_execution(
        _sess("tempo", km=10.0),
        _run("tempo", km=10.0, dur=50.0, pace="5:00"),
        "2026-06-22",
    )
    assert r.execution_status == "completed_well"


def test_status_quality_missed_as_fallback():
    """Minor deviation with no intensity flag falls to quality_missed."""
    r = score_execution(
        _sess("tempo", km=10.0),
        _run("tempo", km=9.5, dur=48.0),
        "2026-06-22",
    )
    assert r.execution_status in ("completed_well", "quality_missed")


# ── Q3: per-lap rep analysis (v0) ────────────────────────────────────────────

def test_rep_analysis_detects_alternating_reps():
    stats = rep_analysis(["5:40", "4:20", "5:40", "4:20", "5:40", "4:20"])
    assert stats.changed_pace is True
    assert stats.detected_reps == 3
    assert stats.avg_rep_pace == "4:20/km"


def test_rep_analysis_uniform_splits_no_reps():
    stats = rep_analysis(["5:00", "5:01", "4:59", "5:00", "5:02", "4:58"])
    assert stats.changed_pace is False
    assert stats.detected_reps == 0


def test_rep_analysis_too_few_splits():
    assert rep_analysis(["4:20", "5:40"]).detected_reps == 0


def test_intervals_uniform_splits_flag_quality_missed():
    """An interval session run at a steady pace is quality_missed (Q3)."""
    r = score_execution(
        _sess("intervals", km=8.0),
        RunSummary(
            date="2026-06-22", activity_type="intervalli", distance_km=8.0, duration_min=40.0,
            splits_km=["5:00", "5:01", "4:59", "5:00", "5:02", "4:58", "5:00", "5:01"],
        ),
        "2026-06-22",
    )
    assert r.execution_status == "quality_missed"
    assert any("nessun cambio di ritmo" in e.lower() for e in r.evidence)


def test_intervals_with_reps_surfaces_detected_reps():
    r = score_execution(
        _sess("intervals", km=8.0, pace="4:15"),
        RunSummary(
            date="2026-06-22", activity_type="intervalli", distance_km=8.0, duration_min=40.0,
            splits_km=["5:40", "4:20", "5:40", "4:20", "5:40", "4:20"],
        ),
        "2026-06-22",
    )
    assert any("km veloci rilevati" in e for e in r.evidence)
    assert any("target 4:15" in e for e in r.evidence)


# ── Q3: multi-run same-day merge ─────────────────────────────────────────────

def test_merge_single_run_is_passthrough():
    run = _run("easy", km=8.0, dur=48.0)
    merged, idx, note = merge_day_activities([run], "easy")
    assert merged is run and idx == 0 and note is None


def test_merge_quality_day_picks_most_intense_and_sums_volume():
    warmup = _run("easy", km=3.0, dur=18.0)
    quality = _run("intervalli", km=8.0, dur=40.0)
    merged, idx, note = merge_day_activities([warmup, quality], "intervals")
    assert idx == 1  # the intervals run is principal, not the longest-by-accident
    assert merged.activity_type == "intervalli"
    assert merged.distance_km == 11.0  # day total: warm-up counts as volume
    assert note is not None and "3.0 km" in note


def test_merge_easy_day_picks_longest():
    short = _run("easy", km=4.0, dur=24.0)
    long_run = _run("easy", km=9.0, dur=54.0)
    merged, idx, note = merge_day_activities([short, long_run], "easy")
    assert idx == 1 and merged.distance_km == 13.0
