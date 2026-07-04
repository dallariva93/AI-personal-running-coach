"""Recap facts — weekly + race summaries for sharing (Roadmap A6).

The engine's job is to decide *what happened*; the narrative (LLM voice, see
:mod:`app.coaching.recap_narrative`) only rewrites the surface. These pure
functions compute every number and pick the week's "best moment" from
already-fetched data, so the narrative can never invent a figure that isn't
already here — same discipline as the A1 verbalizer.

Pure: no I/O, no dates.today() — every date is passed in.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.processing.performance import seconds_to_time
from app.schemas import PersonalRecord, RunSummary

# A "long run" worth calling out as the week's best moment absent a PR.
_LONG_RUN_MIN_KM = 15.0
# A near-perfect execution worth calling out.
_GREAT_EXECUTION_SCORE = 90.0


@dataclass
class WeeklyRecapFacts:
    """Every number the weekly recap narrative is allowed to mention."""

    week_start: str
    week_end: str
    distance_km: float
    runs_count: int
    adherence_pct: float | None
    avg_execution_score: float | None
    best_moment: str | None


@dataclass
class RaceRecapFacts:
    """Every number the race recap narrative is allowed to mention."""

    activity_id: int
    date: str
    distance_km: float
    actual_time: str
    actual_seconds: float
    predicted_time: str | None
    predicted_seconds: float | None
    delta_seconds: float | None
    delta_label: str | None
    splits_km: list[str] | None


def _best_moment(
    runs: list[RunSummary],
    prs: list[PersonalRecord],
    week_start: str,
    week_end: str,
    best_execution: tuple[str, float] | None,
) -> str | None:
    """The week's standout fact, in priority order: a new PR, a near-perfect
    execution, a long run — or None if nothing stands out."""
    week_prs = [p for p in prs if week_start <= p.date <= week_end]
    if week_prs:
        p = week_prs[0]
        return f"Nuovo PB {p.distance}: {p.pace}"
    if best_execution and best_execution[1] >= _GREAT_EXECUTION_SCORE:
        title, score = best_execution
        return f"Seduta perfetta: {title} ({score:.0f}/100)"
    if runs:
        longest = max(runs, key=lambda r: r.distance_km)
        if longest.distance_km >= _LONG_RUN_MIN_KM:
            return f"Il lungo da {longest.distance_km:g} km"
    return None


def compute_weekly_recap_facts(
    runs: list[RunSummary],
    prs: list[PersonalRecord],
    adherence_pct: float | None,
    execution_scores: list[float],
    week_start: str,
    week_end: str,
    best_execution: tuple[str, float] | None = None,
) -> WeeklyRecapFacts:
    """Aggregate a week of running into shareable facts (pure)."""
    distance_km = round(sum(r.distance_km for r in runs), 1)
    avg_score = (
        round(sum(execution_scores) / len(execution_scores), 0)
        if execution_scores
        else None
    )
    return WeeklyRecapFacts(
        week_start=week_start,
        week_end=week_end,
        distance_km=distance_km,
        runs_count=len(runs),
        adherence_pct=adherence_pct,
        avg_execution_score=avg_score,
        best_moment=_best_moment(runs, prs, week_start, week_end, best_execution),
    )


def compute_race_recap_facts(
    activity_id: int,
    race_date: str,
    distance_km: float,
    duration_min: float,
    splits_km: list[str] | None,
    predicted_seconds: float | None,
) -> RaceRecapFacts:
    """Compare the race's actual result against the pre-race prediction (pure).

    ``predicted_seconds`` should come from :func:`app.processing.performance.
    predict_race_time` run over the athlete's history *before* the race date, so
    the comparison is a genuine prediction-vs-reality, not hindsight.
    """
    actual_seconds = round(duration_min * 60.0, 0)
    delta_seconds = None
    delta_label = None
    if predicted_seconds:
        delta_seconds = round(actual_seconds - predicted_seconds, 0)
        if delta_seconds <= 0:
            delta_label = f"{abs(int(delta_seconds))}s più veloce del previsto"
        else:
            delta_label = f"{int(delta_seconds)}s più lento del previsto"
    return RaceRecapFacts(
        activity_id=activity_id,
        date=race_date,
        distance_km=distance_km,
        actual_time=seconds_to_time(actual_seconds) or "-",
        actual_seconds=actual_seconds,
        predicted_time=seconds_to_time(predicted_seconds) if predicted_seconds else None,
        predicted_seconds=predicted_seconds,
        delta_seconds=delta_seconds,
        delta_label=delta_label,
        splits_km=splits_km,
    )
