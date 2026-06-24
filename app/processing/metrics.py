"""Training-load and form metrics.

The headline signal is the **Fitness/Fatigue model** (Banister impulse-response):

- **CTL** (chronic training load) — fitness, a 42-day exponentially weighted
  average of daily internal load.
- **ATL** (acute training load) — fatigue, a 7-day exponentially weighted
  average of the same load.
- **TSB** (training stress balance) — form = CTL − ATL. Positive = fresh,
  strongly negative = fatigued.

The old **ACWR** is still computed but demoted to a *secondary* check (the
modern literature flags its limits — GAP 3). Load itself is now measured both
externally (km, elevation-adjusted) and internally (Session Load = RPE × min,
GAP 4/10). We also compute training **monotony**, the **80/20** easy split from
*real* intensity, plus a qualitative **form state** and **load trend**. All
functions are pure and deterministic given a reference date.
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta

from app.processing.efficiency import aerobic_efficiency
from app.processing.injury import injury_risk
from app.processing.load import internal_load, is_truly_easy
from app.processing.periodization import build_periodization, phase_for
from app.processing.recovery import readiness
from app.schemas import (
    AthleteProfile,
    DailyCheckin,
    RunSummary,
    TrainingMetrics,
    WeeklyBucket,
)

EASY_TYPES = {"easy", "recupero"}

# Time constants (days) for the impulse-response model.
CTL_TAU = 42
ATL_TAU = 7
# Internal load (sRPE = RPE × minutes) runs ~6× larger than the TrainingPeaks
# TSS scale the CTL/ATL/TSB thresholds are calibrated for. Normalise so that a
# ~1h threshold effort ≈ 100 units and steady training settles near TSB 0.
LOAD_SCALE = 6.0


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _distance_between(runs: list[RunSummary], start: date, end: date) -> float:
    """Total km for runs with start <= date <= end."""
    total = 0.0
    for r in runs:
        d = _parse_date(r.date)
        if d and start <= d <= end:
            total += r.distance_km
    return round(total, 2)


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weekly_buckets(runs: list[RunSummary], weeks: int = 8) -> list[WeeklyBucket]:
    """Aggregate runs into ISO-week buckets, most recent week last."""
    buckets: dict[date, WeeklyBucket] = {}
    for r in runs:
        d = _parse_date(r.date)
        if not d:
            continue
        wk = _monday(d)
        b = buckets.setdefault(wk, WeeklyBucket(week_start=wk.isoformat()))
        b.distance_km = round(b.distance_km + r.distance_km, 2)
        b.duration_min = round(b.duration_min + r.duration_min, 1)
        b.runs += 1
    ordered = [buckets[k] for k in sorted(buckets)]
    return ordered[-weeks:]


def _daily_internal_loads(
    runs: list[RunSummary], profile: AthleteProfile | None
) -> dict[date, float]:
    """Sum internal Session Load per calendar day."""
    daily: dict[date, float] = {}
    for r in runs:
        d = _parse_date(r.date)
        if d:
            daily[d] = daily.get(d, 0.0) + internal_load(r, profile)
    return daily


def fitness_fatigue(
    runs: list[RunSummary],
    ref: date | None = None,
    profile: AthleteProfile | None = None,
) -> tuple[float | None, float | None, float | None]:
    """Return ``(CTL, ATL, TSB)`` from the Banister impulse-response model.

    Daily internal load is smoothed with two exponentially weighted averages
    (42-day fitness, 7-day fatigue). Form (TSB) is yesterday's CTL minus ATL —
    the standard convention so a hard day doesn't instantly read as "fresh".
    """
    ref = ref or date.today()
    daily = _daily_internal_loads(runs, profile)
    if not daily:
        return None, None, None

    start = min(daily)
    if start >= ref:
        start = ref
    ctl = atl = 0.0
    ctl_k = 1.0 / CTL_TAU
    atl_k = 1.0 / ATL_TAU
    prev_ctl, prev_atl = 0.0, 0.0
    day = start
    while day <= ref:
        load = daily.get(day, 0.0) / LOAD_SCALE
        prev_ctl, prev_atl = ctl, atl
        ctl = ctl + ctl_k * (load - ctl)
        atl = atl + atl_k * (load - atl)
        day += timedelta(days=1)
    # TSB uses the *previous* day's balance (yesterday's fitness/fatigue).
    tsb = prev_ctl - prev_atl
    return round(ctl, 1), round(atl, 1), round(tsb, 1)


def _classify_form(
    tsb: float | None,
    ctl: float | None,
    acwr: float | None,
    acute: float,
    chronic: float,
) -> tuple[str, str]:
    """Map TSB (primary) to a form state, with ACWR as a secondary guardrail.

    Thresholds follow the TrainingPeaks convention on a TSS-like scale (see
    ``LOAD_SCALE``): positive TSB = fresh, deeply negative = overreaching.
    """
    has_history = (ctl is not None and ctl > 0) or chronic > 0
    if not has_history and acute <= 0:
        return "unknown", "Dati insufficienti per stimare lo stato di forma."
    if tsb is None:
        if acute > 0:
            return "fresh", "Carico recente presente ma storico ancora troppo corto."
        return "unknown", "Storico insufficiente."

    # No training in the last 7 days but a fitness base exists → losing condition.
    if acute <= 0 and has_history:
        return (
            "detraining",
            f"Nessun allenamento negli ultimi 7 giorni (TSB {tsb:+.0f}): "
            "stai perdendo condizione, riprendi con gradualità.",
        )

    acwr_note = ""
    if acwr is not None and acwr > 1.5:
        acwr_note = f" Nota: ACWR {acwr:.2f} elevato, occhio ai salti di carico."

    # TSB thresholds (TrainingPeaks convention on the normalised scale).
    if tsb > 8:
        # Fresh while acute load is collapsing = drifting into detraining.
        if acwr is not None and acwr < 0.8:
            return (
                "detraining",
                f"Forma fresca ma carico in calo (TSB {tsb:+.0f}, ACWR {acwr:.2f}): "
                "puoi aumentare un po' il carico.",
            )
        return (
            "fresh",
            f"Forma fresca (TSB {tsb:+.0f}): fatica bassa rispetto alla fitness, "
            "buon momento per una seduta di qualità o una gara." + acwr_note,
        )
    if tsb >= -10:
        return (
            "balanced",
            f"Equilibrio carico/recupero (TSB {tsb:+.0f}): prosegui con "
            "progressione graduale." + acwr_note,
        )
    if tsb >= -25:
        return (
            "fatigued",
            f"Fatica in accumulo (TSB {tsb:+.0f}): assorbi il lavoro, "
            "privilegia sedute facili." + acwr_note,
        )
    return (
        "fatigued",
        f"Fatica elevata (TSB {tsb:+.0f}): rischio sovraccarico, "
        "inserisci recupero o scarico." + acwr_note,
    )


def compute_metrics(
    runs: list[RunSummary],
    ref: date | None = None,
    profile: AthleteProfile | None = None,
    checkin: DailyCheckin | None = None,
) -> TrainingMetrics:
    """Compute the full :class:`TrainingMetrics` snapshot for the given runs.

    ``profile`` (optional) personalises internal load and the easy/hard split
    via the athlete's HR zones and thresholds. ``checkin`` (optional) adds a
    subjective readiness signal.
    """
    ref = ref or date.today()
    if not runs:
        return TrainingMetrics()

    # Acute = last 7 days; chronic = average week over last 28 days.
    acute = _distance_between(runs, ref - timedelta(days=6), ref)
    chronic_total = _distance_between(runs, ref - timedelta(days=27), ref)
    chronic = round(chronic_total / 4.0, 2)
    acwr = round(acute / chronic, 2) if chronic > 0 else None

    # Internal load (Session Load) over the same windows, plus Fitness/Fatigue.
    window7 = [
        r for r in runs if (d := _parse_date(r.date)) and ref - timedelta(days=6) <= d <= ref
    ]
    window42 = [
        r for r in runs if (d := _parse_date(r.date)) and ref - timedelta(days=41) <= d <= ref
    ]
    acute_internal = round(sum(internal_load(r, profile) for r in window7), 1)
    chronic_internal = round(sum(internal_load(r, profile) for r in window42) / 6.0, 1)
    ctl, atl, tsb = fitness_fatigue(runs, ref=ref, profile=profile)

    # Previous 7-day window for trend.
    prev_week = _distance_between(runs, ref - timedelta(days=13), ref - timedelta(days=7))
    if prev_week == 0:
        load_trend = "rising" if acute > 0 else "stable"
    elif acute > prev_week * 1.1:
        load_trend = "rising"
    elif acute < prev_week * 0.9:
        load_trend = "falling"
    else:
        load_trend = "stable"

    # Monotony over the last 7 days (daily load mean / std).
    daily: dict[date, float] = {}
    for r in runs:
        d = _parse_date(r.date)
        if d and ref - timedelta(days=6) <= d <= ref:
            daily[d] = daily.get(d, 0.0) + r.distance_km
    monotony = None
    if daily:
        loads = [daily.get(ref - timedelta(days=i), 0.0) for i in range(7)]
        mean = statistics.mean(loads)
        std = statistics.pstdev(loads)
        monotony = round(mean / std, 2) if std > 0 else None

    # 80/20 easy ratio over the acute window, from *real* intensity (GAP 5):
    # fall back to the activity label only when HR/zones/RPE are missing.
    easy_km = sum(r.distance_km for r in window7 if is_truly_easy(r, profile))
    total_km = sum(r.distance_km for r in window7)
    easy_ratio = round(easy_km / total_km, 2) if total_km > 0 else None

    form_state, form_explanation = _classify_form(tsb, ctl, acwr, acute, chronic)

    # Periodization: where are we in the macrocycle towards the goal race?
    phase = phase_focus = None
    weeks_to_race = phase_volume_target = None
    if profile and profile.goal:
        baseline = max(chronic, acute / 1.5, 20.0)
        plan = build_periodization(profile.goal, baseline_km=baseline, ref=ref)
        active = phase_for(plan, ref) if plan else None
        if plan and active:
            phase = active.name
            phase_focus = active.intensity_focus
            weeks_to_race = plan.weeks_to_race
            phase_volume_target = round(baseline * active.volume_factor, 1)

    m = TrainingMetrics(
        runs_count=len(runs),
        total_distance_km=round(sum(r.distance_km for r in runs), 2),
        total_duration_min=round(sum(r.duration_min for r in runs), 1),
        weekly_distance_km=acute,
        acute_load_km=acute,
        chronic_load_km=chronic,
        acute_load_internal=acute_internal,
        chronic_load_internal=chronic_internal,
        ctl=ctl,
        atl=atl,
        tsb=tsb,
        acwr=acwr,
        monotony=monotony,
        easy_ratio=easy_ratio,
        form_state=form_state,
        form_explanation=form_explanation,
        load_trend=load_trend,
        week_start=_monday(ref).isoformat(),
        phase=phase,
        phase_focus=phase_focus,
        weeks_to_race=weeks_to_race,
        phase_volume_target_km=phase_volume_target,
    )

    # Injury risk (needs the assembled load metrics) and efficiency progress.
    risk = injury_risk(runs, m, ref=ref)
    m.injury_score = risk.score
    m.injury_level = risk.level
    m.injury_factors = risk.factors
    m.aerobic_efficiency, m.efficiency_trend = aerobic_efficiency(runs, ref=ref)
    m.readiness, m.readiness_state = readiness(checkin)
    return m
