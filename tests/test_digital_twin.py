"""Digital Twin v0 — learned athlete constants (Roadmap A5 / Passo 13).

Deterministic tests for the pure estimators, the DB orchestrator/persistence,
and the consumption points (decision recovery-gate, adaptive ramp cap, plan
prompt). The 5-scenario eval lives in ``tests/eval/test_twin.py``.
"""

from __future__ import annotations

from datetime import date

from app.coaching.prompts import build_multiweek_plan_message
from app.processing import decide_today
from app.processing.adaptive import adapt_plan
from app.processing.digital_twin import (
    DURABILITY_DEFAULT,
    HEAT_DEFAULT_S_PER_C,
    RAMP_DEFAULT_PCT,
    RECOVERY_DEFAULT_DAYS,
    WeekObservation,
    build_athlete_model,
    estimate_durability,
    estimate_heat_sensitivity,
    estimate_ramp_tolerance,
    estimate_recovery_halflife,
)
from app.schemas import (
    AthleteModel,
    DailyCheckin,
    PlanGenerateRequest,
    PlanSessionOut,
    TrainingMetrics,
)

REF = date(2026, 6, 22)


# ── Pure: ramp tolerance ─────────────────────────────────────────────────────


def _ramp_weeks(pcts_and_bad: list[tuple[float, bool]]) -> list[WeekObservation]:
    """Build a weekly series from (pct-increase, bad_after) steps, load base 40."""
    weeks = [WeekObservation(40.0, False)]
    for pct, bad in pcts_and_bad:
        weeks.append(WeekObservation(round(weeks[-1].load * (1 + pct / 100), 2), bad))
    return weeks


def test_ramp_collapse_at_12_estimates_below_12():
    # Increases up to 10% absorbed; 12% and 14% always followed by a bad outcome.
    weeks = _ramp_weeks(
        [(5, False), (8, False), (10, False), (12, True), (14, True),
         (5, False), (6, False), (7, False)]
    )
    est = estimate_ramp_tolerance(weeks)
    assert est.value < 12.0
    assert est.learning is False
    assert est.value == 10.0  # the max safely absorbed increase


def test_ramp_thin_history_uses_default():
    weeks = _ramp_weeks([(8, False), (9, False)])  # <8 pairs
    est = estimate_ramp_tolerance(weeks)
    assert est.value == RAMP_DEFAULT_PCT and est.learning is True


def test_ramp_clamped_to_max():
    weeks = _ramp_weeks([(30, False)] * 9)  # huge absorbed jumps
    est = estimate_ramp_tolerance(weeks)
    assert est.value == 15.0  # clamped to RAMP_MAX_PCT


# ── Pure: recovery half-life ─────────────────────────────────────────────────


def test_recovery_median_three_days():
    est = estimate_recovery_halflife([3, 3, 2, 4, 3])
    assert est.value == 3.0 and est.learning is False


def test_recovery_thin_history_defaults():
    est = estimate_recovery_halflife([2, 3])
    assert est.value == RECOVERY_DEFAULT_DAYS and est.learning is True


# ── Pure: heat sensitivity ───────────────────────────────────────────────────


def test_heat_slope_recovered():
    # gap = 300 + 2*(temp-15): true slope 2 s/km per °C, all hot.
    pts = [(t, 300 + 2 * (t - 15)) for t in [16, 18, 20, 22, 24, 17, 19, 21, 23, 25]]
    est = estimate_heat_sensitivity(pts)
    assert abs(est.value - 2.0) < 0.01 and est.learning is False


def test_heat_thin_history_defaults():
    pts = [(20.0, 320.0), (22.0, 330.0)]  # <10 hot
    est = estimate_heat_sensitivity(pts)
    assert est.value == HEAT_DEFAULT_S_PER_C and est.learning is True


def test_build_athlete_model_shape():
    m = build_athlete_model([], [], [], computed_at="2026-07-03")
    assert isinstance(m, AthleteModel)
    assert m.ramp_tolerance_pct.learning and m.computed_at == "2026-07-03"
    assert m.durability is not None and m.durability.learning  # thin history


# ── Pure: durability ─────────────────────────────────────────────────────────


def test_durability_thin_history_defaults():
    est = estimate_durability([2.0, 3.0])  # < min samples
    assert est.value == DURABILITY_DEFAULT and est.learning


def test_durability_high_when_no_fade():
    # Even/negative splits across enough long runs → high durability.
    est = estimate_durability([0.0, -1.0, 1.0, 0.0])
    assert not est.learning
    assert est.value >= 90  # ~100 minus a tiny median fade


def test_durability_low_when_big_fade():
    est = estimate_durability([10.0, 12.0, 9.0, 11.0])  # ~11% late fade
    assert est.value <= 50  # 100 - 11*5 clamped


def test_durability_from_splits_via_service():
    from app.schemas import RunSummary
    from app.services.athlete_model_service import _durability_fades

    # 18 km long run: first 6 km ~5:00, last 6 km ~5:30 → ~10% fade.
    splits = ["5:00"] * 6 + ["5:15"] * 6 + ["5:30"] * 6
    runs = [RunSummary(date="2026-06-10", distance_km=18.0, activity_type="long",
                       duration_min=95, splits_km=splits)]
    fades = _durability_fades(runs)
    assert len(fades) == 1
    assert 8 < fades[0] < 12  # last third vs first third


# ── Consumption: decision recovery-gate ──────────────────────────────────────


def _session(session_type: str, **kw) -> PlanSessionOut:
    return PlanSessionOut(
        id=kw.get("id", 1),
        day_of_week=REF.weekday(),
        session_type=session_type,
        title=kw.get("title", f"Sessione {session_type}"),
        description=None,
        target_distance_km=kw.get("target_distance_km"),
        target_pace=kw.get("target_pace"),
        target_duration_min=kw.get("target_duration_min"),
        completed=False,
    )


def _healthy_checkin() -> DailyCheckin:
    return DailyCheckin(date=REF.isoformat(), sleep_h=8.0, fatigue=2, hrv_rmssd=60.0)


def test_quality_gated_on_day_two_of_a_three_day_recovery():
    m = TrainingMetrics(tsb=2.0, acwr=1.0, injury_level="low", readiness_state="green")
    sess = _session("intervals", title="8x400")
    # Only 1 day since the last hard effort, personal recovery half-life = 3.
    d = decide_today(
        m, None, sess, _healthy_checkin(), ref=REF,
        days_since_last_hard=1, recovery_halflife_days=3,
    )
    assert d.decision != "quality"  # engine protects the recovery window
    assert d.session_type == "easy"


def test_quality_allowed_once_recovery_window_elapsed():
    m = TrainingMetrics(tsb=2.0, acwr=1.0, injury_level="low", readiness_state="green")
    sess = _session("intervals", title="8x400")
    d = decide_today(
        m, None, sess, _healthy_checkin(), ref=REF,
        days_since_last_hard=3, recovery_halflife_days=3,
    )
    assert d.decision == "quality"


def test_fresh_no_plan_quality_gated_during_recovery():
    m = TrainingMetrics(tsb=20.0, acwr=0.9, injury_level="low", readiness_state="green")
    d = decide_today(
        m, None, None, _healthy_checkin(), ref=REF,
        days_since_last_hard=1, recovery_halflife_days=3,
    )
    assert d.decision != "quality"


def test_no_recovery_signal_keeps_default_behaviour():
    m = TrainingMetrics(tsb=20.0, acwr=0.9, injury_level="low", readiness_state="green")
    d = decide_today(m, None, None, _healthy_checkin(), ref=REF)  # no twin args
    assert d.decision == "quality"


# ── Consumption: adaptive ramp cap + plan prompt ─────────────────────────────


def test_adapt_plan_accepts_personal_ramp_cap():
    m = TrainingMetrics(tsb=0.0, acwr=1.0, injury_level="low", readiness_state="green")
    factor, _ = adapt_plan(m, max_ramp_factor=1.12)
    assert 0.5 <= factor <= 1.12


def test_plan_prompt_includes_personal_ramp_line():
    req = PlanGenerateRequest(goal_type="10k", goal_date="2026-09-01", level="intermediate")
    msg = build_multiweek_plan_message(req, None, None, ramp_pct=12.0)
    assert "Ramp personale" in msg and "12%" in msg
    # Absent when unknown.
    assert "Ramp personale" not in build_multiweek_plan_message(req, None, None)


# ── Persistence round-trip + consumption helpers ─────────────────────────────


def test_save_and_load_round_trip(session):
    from app.services.athlete_model_service import (
        load_athlete_model,
        personal_ramp_factor,
        personal_recovery_halflife,
        save_athlete_model,
    )

    model = build_athlete_model(
        _ramp_weeks([(5, False), (8, False), (10, False), (12, True),
                     (5, False), (6, False), (7, False), (8, False)]),
        [3, 3, 3, 2],
        [(t, 300 + 2 * (t - 15)) for t in [16, 18, 20, 22, 24, 17, 19, 21, 23, 25]],
        computed_at=REF.isoformat(),
    )
    save_athlete_model(session, model)

    loaded = load_athlete_model(session)
    assert loaded.ramp_tolerance_pct.value == model.ramp_tolerance_pct.value
    assert loaded.recovery_halflife_days.learning is False
    assert personal_recovery_halflife(session) == 3
    assert personal_ramp_factor(session) == round(
        1 + model.ramp_tolerance_pct.value / 100, 3
    )


def test_durability_persists_and_is_consumable(session):
    from app.services.athlete_model_service import (
        load_athlete_model,
        personal_durability,
        save_athlete_model,
    )

    model = build_athlete_model(
        [], [], [], durability_fades=[0.0, -1.0, 1.0, 0.0], computed_at=REF.isoformat()
    )
    save_athlete_model(session, model)

    loaded = load_athlete_model(session)
    assert loaded.durability is not None and not loaded.durability.learning
    assert personal_durability(session) == loaded.durability.value


def test_personal_durability_none_while_learning(session):
    from app.services.athlete_model_service import personal_durability

    assert personal_durability(session) is None


def test_load_defaults_when_empty(session):
    from app.services.athlete_model_service import (
        load_athlete_model,
        personal_ramp_factor,
        personal_recovery_halflife,
    )

    loaded = load_athlete_model(session)
    assert loaded.ramp_tolerance_pct.learning is True
    assert personal_ramp_factor(session) is None
    assert personal_recovery_halflife(session) is None


def test_athlete_model_endpoint(client):
    resp = client.get("/api/athlete-model")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ramp_tolerance_pct"]["learning"] is True
    assert body["recovery_halflife_days"]["value"] == RECOVERY_DEFAULT_DAYS
