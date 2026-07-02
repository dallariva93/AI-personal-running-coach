"""Unit tests for coaching confidence and missing data (Roadmap #5)."""

from app.coaching.coach import OfflineCoach
from app.schemas import AthleteProfile, Goal, RunSummary, TrainingMetrics


def test_confidence_high_all_data_present():
    """When all data is present, confidence is high."""
    coach = OfflineCoach()
    run = RunSummary(
        date="2026-07-01",
        distance_km=10.0,
        duration_min=60.0,
        avg_hr=140,
        max_hr=180,
        rpe=5,
        elevation_gain_m=100,
    )
    metrics = TrainingMetrics(ctl=50.0, tsb=5.0)
    profile = AthleteProfile(
        goal=Goal(goal_type="marathon", target_date="2026-12-01", target_time="3:30:00")
    )

    confidence, missing = coach._assess_confidence(run, metrics, profile)
    assert confidence == "high"
    assert len(missing) == 0


def test_confidence_medium_one_missing():
    """When one data point is missing, confidence is medium."""
    coach = OfflineCoach()
    run = RunSummary(
        date="2026-07-01",
        distance_km=10.0,
        duration_min=60.0,
        avg_hr=140,
        max_hr=180,
        rpe=5,
        elevation_gain_m=None,  # missing
    )
    metrics = TrainingMetrics(ctl=50.0, tsb=5.0)
    profile = AthleteProfile(
        goal=Goal(goal_type="marathon", target_date="2026-12-01", target_time="3:30:00")
    )

    confidence, missing = coach._assess_confidence(run, metrics, profile)
    assert confidence == "medium"
    assert "Dislivello" in missing


def test_confidence_low_multiple_missing():
    """When three or more data points are missing, confidence is low."""
    coach = OfflineCoach()
    run = RunSummary(
        date="2026-07-01",
        distance_km=10.0,
        duration_min=60.0,
        avg_hr=None,  # missing
        max_hr=180,
        rpe=None,  # missing
        elevation_gain_m=None,  # missing
    )
    metrics = TrainingMetrics(ctl=50.0, tsb=5.0)
    profile = AthleteProfile(
        goal=Goal(goal_type="marathon", target_date="2026-12-01", target_time="3:30:00")
    )

    confidence, missing = coach._assess_confidence(run, metrics, profile)
    assert confidence == "low"
    assert len(missing) >= 3


def test_confidence_low_no_profile():
    """When profile is missing, confidence is medium (only 1 missing)."""
    coach = OfflineCoach()
    run = RunSummary(
        date="2026-07-01",
        distance_km=10.0,
        duration_min=60.0,
        avg_hr=140,
        max_hr=180,
        rpe=5,
        elevation_gain_m=100,
    )
    metrics = TrainingMetrics(ctl=50.0, tsb=5.0)

    confidence, missing = coach._assess_confidence(run, metrics, None)
    assert confidence == "medium"
    assert "Profilo atleta" in missing


def test_confidence_low_no_goal():
    """When goal is missing, confidence is medium (only 1 missing)."""
    coach = OfflineCoach()
    run = RunSummary(
        date="2026-07-01",
        distance_km=10.0,
        duration_min=60.0,
        avg_hr=140,
        max_hr=180,
        rpe=5,
        elevation_gain_m=100,
    )
    metrics = TrainingMetrics(ctl=50.0, tsb=5.0)
    profile = AthleteProfile()  # no goal

    confidence, missing = coach._assess_confidence(run, metrics, profile)
    assert confidence == "medium"
    assert "Obiettivo gara" in missing


def test_confidence_low_no_metrics():
    """When metrics are missing, confidence is medium (2 missing items)."""
    coach = OfflineCoach()
    run = RunSummary(
        date="2026-07-01",
        distance_km=10.0,
        duration_min=60.0,
        avg_hr=140,
        max_hr=180,
        rpe=5,
        elevation_gain_m=100,
    )
    metrics = TrainingMetrics(ctl=None, tsb=None)  # missing
    profile = AthleteProfile(
        goal=Goal(goal_type="marathon", target_date="2026-12-01", target_time="3:30:00")
    )

    confidence, missing = coach._assess_confidence(run, metrics, profile)
    assert confidence == "medium"
    assert "CTL (carico cronico)" in missing
    assert "TSB (forma)" in missing


def test_confidence_weekly_no_run():
    """For weekly analysis, run is None but other data is checked."""
    coach = OfflineCoach()
    metrics = TrainingMetrics(ctl=50.0, tsb=5.0)
    profile = AthleteProfile(
        goal=Goal(goal_type="marathon", target_date="2026-12-01", target_time="3:30:00")
    )

    confidence, missing = coach._assess_confidence(None, metrics, profile)
    assert confidence == "high"
    assert len(missing) == 0


def test_missing_data_lists_all_missing():
    """All missing data points are listed."""
    coach = OfflineCoach()
    run = RunSummary(
        date="2026-07-01",
        distance_km=10.0,
        duration_min=60.0,
        avg_hr=None,
        max_hr=180,
        rpe=None,
        elevation_gain_m=None,
    )
    metrics = TrainingMetrics(ctl=None, tsb=None)
    profile = AthleteProfile()

    confidence, missing = coach._assess_confidence(run, metrics, profile)
    assert confidence == "low"
    assert "Frequenza cardiaca" in missing
    assert "RPE" in missing
    assert "Dislivello" in missing
    assert "CTL (carico cronico)" in missing
    assert "TSB (forma)" in missing
    assert "Obiettivo gara" in missing  # profile exists but no goal
    assert "Profilo atleta" not in missing  # profile exists
