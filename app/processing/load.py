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

from app.processing.tuning import easy_hr_reserve_ceiling, hard_hr_reserve_floor
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


# Default conversion from Garmin's EPOC-based ``activityTrainingLoad`` to the
# sRPE scale (RPE × min) the CTL/ATL/TSB model is calibrated for. Anchored on
# real data (a hard ~42' run: Garmin load 258 vs sRPE 7×42≈294 → ~1.15; easy
# runs sit higher), so 1.5 is a reasonable cold-start. Refined per-athlete by
# ``calibrate_garmin_factor`` once enough paired runs exist.
GARMIN_LOAD_TO_SRPE = 1.5


def _srpe_load(run: RunSummary, profile: AthleteProfile | None = None) -> float:
    """Subjective session load = effective RPE × duration (min), heat-adjusted."""
    if run.duration_min <= 0:
        return 0.0
    return round(estimate_rpe(run, profile) * run.duration_min * heat_factor(run), 1)


def internal_load(
    run: RunSummary,
    profile: AthleteProfile | None = None,
    garmin_factor: float | None = None,
) -> float:
    """Internal (physiological) session load, on the sRPE scale. GAP 4/10/18.

    Prefers Garmin's measured ``activityTrainingLoad`` (EPOC-based) when present,
    mapped onto the sRPE scale via ``garmin_factor`` (per-athlete calibration,
    see :func:`calibrate_garmin_factor`) or the :data:`GARMIN_LOAD_TO_SRPE`
    default. Heat is *not* re-applied to Garmin load — it already reflects the
    heat-elevated heart rate. Falls back to subjective sRPE when no Garmin load
    is available (demo / manual entries), keeping the offline path unchanged.
    """
    if run.garmin_training_load is not None and run.garmin_training_load > 0:
        return round(run.garmin_training_load * (garmin_factor or GARMIN_LOAD_TO_SRPE), 1)
    return _srpe_load(run, profile)


def calibrate_garmin_factor(
    runs: list[RunSummary], profile: AthleteProfile | None = None
) -> float | None:
    """Per-athlete sRPE/Garmin-load ratio from runs carrying both signals.

    Returns ``sum(sRPE) / sum(Garmin load)`` over paired runs — a total-load
    preserving ratio that maps Garmin's load onto *this athlete's* sRPE scale
    (keeping the CTL/ATL/TSB thresholds valid), or None when there isn't enough
    paired data. We only pair against a trustworthy sRPE — one backed by an
    explicit RPE or a heart rate, not a label-only guess.
    """
    srpe_total = 0.0
    garmin_total = 0.0
    pairs = 0
    for r in runs:
        gl = r.garmin_training_load
        if not gl or gl <= 0 or r.duration_min <= 0:
            continue
        if r.rpe is None and r.avg_hr is None:
            continue
        srpe = _srpe_load(r, profile)
        if srpe > 0:
            srpe_total += srpe
            garmin_total += gl
            pairs += 1
    if pairs < 3 or garmin_total <= 0:
        return None
    return round(srpe_total / garmin_total, 3)


def equivalent_flat_km(run: RunSummary) -> float:
    """Distance adjusted for elevation gain (GAP 19)."""
    base = run.distance_km
    if run.elevation_gain_m and run.elevation_gain_m > 0:
        base += run.elevation_gain_m * _ELEVATION_TO_FLAT_KM
    return round(base, 2)


# Intensity boundaries (HR-reserve fractions) come from ``tuning`` so they scale
# with the athlete's level: top of Z2 ≈ easy ceiling (the old fixed 0.75 was too
# strict and mislabelled honest aerobic runs as hard); above the hard floor ≈ Z4
# is clearly hard; in between is a distinct "moderate" (Z3) band.

# Fallback intensity by activity label when neither zones, HR nor RPE exist.
_LABEL_INTENSITY = {
    "recupero": "easy",
    "easy": "easy",
    "lungo": "easy",  # long aerobic volume counts as easy for 80/20
    "medio": "moderate",
    "trail": "moderate",
    "altro": "moderate",
    "tempo": "hard",
    "intervalli": "hard",
    "gara": "hard",
}


def intensity_class(run: RunSummary, profile: AthleteProfile | None = None) -> str:
    """Classify real intensity as ``easy`` | ``moderate`` | ``hard`` (GAP 5).

    Three states instead of a binary easy/hard split: a Z3 "medio" is its own
    thing, not lumped with intervals. Priority of evidence: personalised HR
    zones > HR reserve > RPE > activity label.
    """
    if profile and profile.zones is not None and run.avg_hr is not None:
        zone = profile.zones.zone_of(run.avg_hr)
        if zone is not None:
            if zone <= 2:
                return "easy"
            return "moderate" if zone == 3 else "hard"
    frac = _hr_fraction(run, profile)
    if frac is not None:
        if frac < easy_hr_reserve_ceiling(profile):
            return "easy"
        return "moderate" if frac < hard_hr_reserve_floor(profile) else "hard"
    if run.rpe is not None:
        if run.rpe <= 4:
            return "easy"
        return "moderate" if run.rpe <= 6 else "hard"
    return _LABEL_INTENSITY.get(run.activity_type, "moderate")


def is_truly_easy(run: RunSummary, profile: AthleteProfile | None = None) -> bool:
    """Whether a session was *actually* easy (real intensity, not the label)."""
    return intensity_class(run, profile) == "easy"
