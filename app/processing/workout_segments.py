"""Plan session → structured workout segments (Fase E — plan architecture review).

A plan session is a *structured workout*, not just a title + distance + pace +
prose. This pure module projects the prescription (session type, distance, pace,
goal) into the same segment model the Workout Builder uses
(:class:`app.schemas.WorkoutSegmentIn`): warm-up, work block(s), recovery and
cool-down. Deterministic and reversible — it recomputes exactly the structure the
periodization engine built the description from, so no extra state is persisted.

The segments unlock segment-by-segment execution scoring and a future
push-to-watch, and keep the plan coherent with the workout library.
"""

from __future__ import annotations

from app.schemas import WorkoutSegmentIn

# Interval structure by goal distance, mirroring the engine's ``_spec_render``.
_INTERVALS = {
    "marathon": (5, 1.5, 3),
    "half": (5, 1.5, 3),
    "10k": (6, 1.0, 2),
    "5k": (6, 1.0, 2),
    "trail": (5, 1.5, 3),
}
_TEMPO_WARMUP = 2.0
_TEMPO_COOLDOWN = 2.0
_INT_WARMUP = 2.5
_INT_COOLDOWN = 2.0


def build_session_segments(
    session_type: str | None,
    distance_km: float | None,
    pace: str | None,
    goal_type: str | None = None,
) -> list[WorkoutSegmentIn]:
    """Structured segments for one plan session (empty for rest/race/cross)."""
    stype = (session_type or "").lower()
    dist = float(distance_km) if distance_km else 0.0

    if stype == "easy" and dist > 0:
        return [_seg(0, "easy", work_distance_km=dist, work_pace=pace)]

    if stype == "long" and dist > 0:
        return [
            _seg(0, "easy", work_distance_km=round(dist, 1), work_pace=pace,
                 notes="Ritmo controllato, parti piano")
        ]

    if stype == "strides" and dist > 0:
        return [
            _seg(0, "easy", work_distance_km=round(dist, 1), work_pace=pace),
            _seg(1, "strides", repetitions=5, work_distance_km=0.1,
                 rest_duration_sec=90, rest_type="walk",
                 notes="Allunghi progressivi, tecnica"),
        ]

    if stype == "tempo" and dist > 0:
        quality = max(3.0, round(dist - _TEMPO_WARMUP - _TEMPO_COOLDOWN, 1))
        return [
            _seg(0, "warmup", work_distance_km=_TEMPO_WARMUP),
            _seg(1, "threshold", work_distance_km=quality, work_pace=pace,
                 notes="Z3-Z4, controllato ma sfidante"),
            _seg(2, "cooldown", work_distance_km=_TEMPO_COOLDOWN),
        ]

    if stype == "intervals" and dist > 0:
        reps, rep_dist, rec_min = _INTERVALS.get(goal_type or "", (5, 1.5, 3))
        return [
            _seg(0, "warmup", work_distance_km=_INT_WARMUP),
            _seg(1, "interval_block", repetitions=reps, work_distance_km=rep_dist,
                 work_pace=pace, rest_duration_sec=rec_min * 60, rest_type="jog",
                 notes=f"{reps}×{rep_dist:g} km, recupero {rec_min}'"),
            _seg(2, "cooldown", work_distance_km=_INT_COOLDOWN),
        ]

    return []


def _seg(position: int, segment_type: str, **kw) -> WorkoutSegmentIn:
    return WorkoutSegmentIn(position=position, segment_type=segment_type, **kw)
