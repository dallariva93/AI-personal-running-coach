"""Training load: internal (physiological) and external (mechanical).

Two 60 km weeks can stress the body very differently. Counting only kilometres
(the old behaviour) hides that. This module computes, per session:

- **internal load** — how hard it felt for the body. Best signal is
  ``Session Load = RPE × minutes`` (GAP 10). When RPE is missing we fall back to
  a heart-rate based TRIMP-style estimate, and finally to an estimate from the
  activity label so the metric is always populated.
- **external load** — the mechanical work: distance, adjusted for elevation via
  an *equivalent flat distance* (GAP 19) so hilly runs count for more.

All functions are pure: no I/O, no network. They operate on
:class:`~app.schemas.RunSummary` plus, optionally, an athlete profile.
"""

from __future__ import annotations

from app.schemas import AthleteProfile, RunSummary

# Rough RPE (1-10) by activity label, used only when neither RPE nor HR is
# available. Deliberately conservative.
_RPE_BY_TYPE = {
    "recupero": 2.0,
    "easy": 3.0,
    "lungo": 5.0,
    # Medio: sustained Z3 effort (Italian "fondo medio" / Garmin TEMPO label).
    # Harder than lungo, easier than the threshold-based tempo run.
    "medio": 5.5,
    # Trail is rated between lungo and tempo: the climbing cost adds load
    # even at modest pace, but it is not as systemic as a true tempo effort.
    "trail": 6.0,
    "tempo": 7.0,
    "intervalli": 8.0,
    "gara": 9.0,
    "altro": 4.0,
}

# Climbing ~10 m costs roughly the energy of ~100 m on the flat (a common
# rule of thumb for running). Tunable; kept simple and explainable.
_ELEVATION_TO_FLAT_KM = 0.01  # +1 m of climb ≈ +0.01 km equivalent flat

EASY_TYPES = {"easy", "recupero"}


def _hr_fraction(run: RunSummary, profile: AthleteProfile | None) -> float | None:
    """Estimate average HR as a fraction of HR reserve (Karvonen) or of max."""
    if not run.avg_hr:
        return None
    max_hr = (profile.max_hr if profile else None) or run.max_hr
    rest_hr = profile.resting_hr if profile else None
    if max_hr and rest_hr and max_hr > rest_hr:
        return max(0.0, min(1.0, (run.avg_hr - rest_hr) / (max_hr - rest_hr)))
    if max_hr and max_hr > 0:
        return max(0.0, min(1.0, run.avg_hr / max_hr))
    return None


def estimate_rpe(run: RunSummary, profile: AthleteProfile | None = None) -> float:
    """Best-effort RPE (1-10): explicit value > HR-derived > label-based."""
    if run.rpe is not None:
        return float(run.rpe)
    frac = _hr_fraction(run, profile)
    if frac is not None:
        # Map HR reserve fraction ~[0.5, 1.0] onto RPE ~[2, 10].
        return round(max(1.0, min(10.0, (frac - 0.4) / 0.6 * 8.0 + 2.0)), 1)
    return _RPE_BY_TYPE.get(run.activity_type, 4.0)


def heat_factor(run: RunSummary) -> float:
    """Load multiplier for heat/humidity stress (GAP 18).

    Running in the heat raises HR and perceived effort for the same pace, so the
    same session costs more. Above ~20°C we add ~1.2%/°C, with a small extra
    penalty when humidity is high. Capped to avoid runaway values.
    """
    temp = run.temperature_c
    if temp is None or temp <= 20:
        return 1.0
    factor = 1.0 + (temp - 20) * 0.012
    if run.humidity_pct and run.humidity_pct >= 70:
        factor += 0.05
    return min(factor, 1.4)


def internal_load(run: RunSummary, profile: AthleteProfile | None = None) -> float:
    """Session Load = effective RPE × duration (min), heat-adjusted. GAP 4/10/18."""
    if run.duration_min <= 0:
        return 0.0
    return round(estimate_rpe(run, profile) * run.duration_min * heat_factor(run), 1)


def equivalent_flat_km(run: RunSummary) -> float:
    """Distance adjusted for elevation gain (GAP 19)."""
    base = run.distance_km
    if run.elevation_gain_m and run.elevation_gain_m > 0:
        base += run.elevation_gain_m * _ELEVATION_TO_FLAT_KM
    return round(base, 2)


def is_truly_easy(run: RunSummary, profile: AthleteProfile | None = None) -> bool:
    """Whether a session was *actually* easy, from real intensity not the label.

    Closes part of GAP 5: an "easy" mislabelled run that was run hard counts as
    hard. Uses personalised zones when available, else HR reserve, else falls
    back to the activity label.
    """
    if profile and profile.zones is not None and run.avg_hr is not None:
        zone = profile.zones.zone_of(run.avg_hr)
        if zone is not None:
            return zone <= 2
    frac = _hr_fraction(run, profile)
    if frac is not None:
        return frac < 0.75  # below ~75% HR reserve ≈ aerobic/easy
    if run.rpe is not None:
        return run.rpe <= 4
    return run.activity_type in EASY_TYPES
