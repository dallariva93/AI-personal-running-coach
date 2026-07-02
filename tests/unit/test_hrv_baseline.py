"""Tests for the personal HRV baseline (FINAL_ROADMAP §5-bis, Passo 1 / Q1)."""

from __future__ import annotations

from datetime import date, timedelta

from app.processing import compute_metrics
from app.processing.decision import decide_today
from app.processing.recovery import hrv_baseline
from app.schemas import AthleteProfile, DailyCheckin, RunSummary

REF = date(2026, 6, 24)


def _history(days_back_to_value: dict[int, float]) -> list[tuple[date, float]]:
    return [(REF - timedelta(days=i), v) for i, v in days_back_to_value.items()]


def _flat_history(recent: float, prior: float) -> list[tuple[date, float]]:
    """7 recent days at ``recent`` + 28 prior days at ``prior`` (35 total, no SD)."""
    return _history({i: recent for i in range(7)} | {i: prior for i in range(7, 35)})


def _run(d: str, km: float, t: str = "easy") -> RunSummary:
    return RunSummary(date=d, distance_km=km, activity_type=t, duration_min=km * 6)


# -- hrv_baseline() -----------------------------------------------------------
def test_baseline_low_when_recent_below_band():
    b = hrv_baseline(_flat_history(recent=40.0, prior=60.0))
    assert b.status == "low"
    assert b.learning is False


def test_baseline_high_when_recent_above_band():
    b = hrv_baseline(_flat_history(recent=80.0, prior=60.0))
    assert b.status == "high"


def test_baseline_normal_when_within_band():
    # Prior 28 days oscillate 50/70 (real SD), recent settles at their mean:
    # squarely inside +-0.75 SD, so it must read normal, not "any deviation".
    prior_values = {i: (50.0 if i % 2 else 70.0) for i in range(7, 35)}
    history = _history({i: 60.0 for i in range(7)} | prior_values)
    b = hrv_baseline(history)
    assert b.status == "normal"


def test_baseline_learning_below_21_days():
    history = _history({i: 60.0 for i in range(10)})
    b = hrv_baseline(history)
    assert b.learning is True
    # Falls back to absolute thresholds on the most recent value.
    assert b.status == "high"  # 60ms > 55 under the old absolute threshold


def test_baseline_empty_history_is_unknown():
    b = hrv_baseline([])
    assert b.status == "unknown"
    assert b.learning is True


def test_baseline_ignores_outliers():
    history = _history({i: 60.0 for i in range(35)})
    history.append((REF, 999.0))  # implausible outlier, must be dropped
    history.append((REF - timedelta(days=1), 0.0))
    b = hrv_baseline(history)
    assert b.status == "normal"


# -- Wired into compute_metrics + decision engine ------------------------------
def test_metrics_expose_personal_baseline_status_and_learning_flag():
    checkin = DailyCheckin(date=REF.isoformat(), hrv_rmssd=40.0)
    m = compute_metrics(
        [_run("2026-06-20", 8)], ref=REF, checkin=checkin,
        hrv_history=_flat_history(recent=40.0, prior=60.0),
    )
    assert m.hrv_status == "low"
    assert m.hrv_learning is False


def test_metrics_learning_flag_true_under_21_days():
    checkin = DailyCheckin(date=REF.isoformat(), hrv_rmssd=45.0)
    m = compute_metrics(
        [_run("2026-06-20", 8)], ref=REF, checkin=checkin,
        hrv_history=_history({i: 45.0 for i in range(10)}),
    )
    assert m.hrv_learning is True


def test_decision_engine_flags_low_hrv_that_old_thresholds_would_call_normal():
    """45ms reads 'normal' under the old 25-55 band but 'low' under a high
    personal baseline (mean ~60) — exactly the Q1 regression the brief calls out.
    """
    checkin = DailyCheckin(date=REF.isoformat(), hrv_rmssd=45.0, sleep_h=7, fatigue=3)
    runs = [_run(f"2026-06-{d:02d}", 6) for d in range(1, 21, 2)]
    profile = AthleteProfile()
    m = compute_metrics(
        runs, ref=REF, profile=profile, checkin=checkin,
        hrv_history=_flat_history(recent=45.0, prior=60.0),
    )
    assert m.hrv_status == "low"
    decision = decide_today(m, profile, None, checkin, ref=REF)
    assert not any("HRV" in msg for msg in decision.missing_data)


def test_compute_metrics_without_hrv_history_falls_back_to_absolute_thresholds():
    checkin = DailyCheckin(date=REF.isoformat(), hrv_rmssd=45.0)
    m = compute_metrics([_run("2026-06-20", 8)], ref=REF, checkin=checkin)
    assert m.hrv_status == "normal"  # legacy absolute-threshold behaviour, unchanged
    assert m.hrv_learning is False
