"""Training-load and form metrics.

The headline metric is the **ACWR** (acute:chronic workload ratio): the last 7
days of load divided by the average weekly load over the last 28 days. Sports
science associates a ratio in roughly the 0.8-1.3 band with lower injury risk;
above ~1.5 the athlete is ramping too fast.

We also compute training **monotony** (how evenly load is spread), the **80/20**
easy-vs-hard volume split, and a qualitative **form state** and **load trend**.
All functions are pure and deterministic given a reference date.
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta

from app.schemas import RunSummary, TrainingMetrics, WeeklyBucket

EASY_TYPES = {"easy", "recupero"}


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


def _classify_form(acwr: float | None, acute: float, chronic: float) -> tuple[str, str]:
    """Map ACWR to a human form state plus a short explanation (Italian)."""
    if chronic <= 0 and acute <= 0:
        return "unknown", "Dati insufficienti per stimare lo stato di forma."
    if acwr is None:
        if acute > 0:
            return "fresh", "Carico recente presente ma storico ancora troppo corto."
        return "unknown", "Storico insufficiente."
    if acwr < 0.8:
        return (
            "detraining",
            f"Carico in calo (ACWR {acwr:.2f}): rischio di perdere condizione, "
            "puoi spingere un po'.",
        )
    if acwr <= 1.3:
        return (
            "balanced",
            f"Carico ben bilanciato (ACWR {acwr:.2f}): fascia ottimale, "
            "prosegui con progressione graduale.",
        )
    if acwr <= 1.5:
        return (
            "fatigued",
            f"Carico in rapida crescita (ACWR {acwr:.2f}): attenzione, "
            "privilegia il recupero.",
        )
    return (
        "fatigued",
        f"Carico molto alto (ACWR {acwr:.2f}): rischio infortunio elevato, "
        "riduci volume/intensità.",
    )


def compute_metrics(runs: list[RunSummary], ref: date | None = None) -> TrainingMetrics:
    """Compute the full :class:`TrainingMetrics` snapshot for the given runs."""
    ref = ref or date.today()
    if not runs:
        return TrainingMetrics()

    # Acute = last 7 days; chronic = average week over last 28 days.
    acute = _distance_between(runs, ref - timedelta(days=6), ref)
    chronic_total = _distance_between(runs, ref - timedelta(days=27), ref)
    chronic = round(chronic_total / 4.0, 2)
    acwr = round(acute / chronic, 2) if chronic > 0 else None

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

    # 80/20 easy ratio over the acute window.
    window_runs = [
        r for r in runs if (d := _parse_date(r.date)) and ref - timedelta(days=6) <= d <= ref
    ]
    easy_km = sum(r.distance_km for r in window_runs if r.activity_type in EASY_TYPES)
    total_km = sum(r.distance_km for r in window_runs)
    easy_ratio = round(easy_km / total_km, 2) if total_km > 0 else None

    form_state, form_explanation = _classify_form(acwr, acute, chronic)

    return TrainingMetrics(
        runs_count=len(runs),
        total_distance_km=round(sum(r.distance_km for r in runs), 2),
        total_duration_min=round(sum(r.duration_min for r in runs), 1),
        weekly_distance_km=acute,
        acute_load_km=acute,
        chronic_load_km=chronic,
        acwr=acwr,
        monotony=monotony,
        easy_ratio=easy_ratio,
        form_state=form_state,
        form_explanation=form_explanation,
        load_trend=load_trend,
        week_start=_monday(ref).isoformat(),
    )
