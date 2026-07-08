"""Pydantic schemas shared across collection, processing and coaching modules.

These form the stable contract between the three independent layers:
- collection produces ``RunSummary`` objects,
- processing turns a list of them into ``TrainingMetrics``,
- coaching consumes both and returns ``CoachingResult``.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

ACTIVITY_TYPES = (
    "easy",
    "recupero",
    "medio",
    "trail",
    "lungo",
    "tempo",
    "intervalli",
    "gara",
    "altro",
)


class RunSummary(BaseModel):
    """Compact, LLM-friendly representation of one running activity."""

    model_config = ConfigDict(extra="ignore")

    garmin_activity_id: str | None = None
    strava_activity_id: str | None = None
    health_connect_id: str | None = None  # A2: no-Garmin Health Connect track
    live_id: str | None = None  # G1: phone-recorded live run (retry-safe id)
    date: str  # ISO YYYY-MM-DD
    start_time: str | None = None  # local start "HH:MM" (Q6 weather + habitual hours)
    sport: str = "run"  # run | bike | swim | strength (Feature 24)
    activity_type: str = "easy"
    duration_min: float = 0.0
    distance_km: float = 0.0
    avg_pace: str | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    elevation_gain_m: float | None = None
    avg_cadence: int | None = None
    rpe: int | None = None
    notes: str | None = None
    hr_zones: dict[str, float] | None = None
    splits_km: list[str] | None = None
    # Environment (GAP 18) and trail (GAP 20) extras — all optional.
    temperature_c: float | None = None
    humidity_pct: float | None = None
    elevation_loss_m: float | None = None  # D-
    # Garmin-derived rich metrics (filled when the Garmin payload is available).
    # None on manual entries or pre-enrichment activities.
    garmin_training_load: float | None = None  # Garmin's per-session load score
    vigorous_minutes: float | None = None  # minutes in Z4-Z5 (Garmin's count)
    moderate_minutes: float | None = None  # minutes in Z3
    body_battery_delta: int | None = None  # Body Battery change (negative = drained)
    stamina_drop: float | None = None  # beginPotentialStamina - end (positive = used)
    avg_grade_adjusted_pace: str | None = None  # Garmin GAP, e.g. "4:32/km"
    fastest_split_1k: str | None = None  # fastest 1 km segment, e.g. "4:22/km"
    fastest_split_5k: str | None = None  # fastest 5 km segment pace
    vo2max: float | None = None  # Garmin's estimated VO2max for the session
    aerobic_training_effect: float | None = None  # Garmin TE, 0.0-5.0
    anaerobic_training_effect: float | None = None  # Garmin anaerobic TE, 0.0-5.0
    aerobic_te_message: str | None = None  # e.g. "IMPROVING_LACTATE_THRESHOLD_12"
    anaerobic_te_message: str | None = None  # e.g. "NO_ANAEROBIC_BENEFIT_0"
    altitude_profile: list[float] | None = None  # per-km average altitude (m)
    route_polyline: str | None = None  # JSON list of [lat, lon] pairs
    # Optional shoe reference for mileage tracking (Roadmap #6).
    shoe_id: int | None = None


class DailyCheckin(BaseModel):
    """Subjective daily wellness check-in (GAP 9). Scales are 1-10."""

    model_config = ConfigDict(extra="ignore")

    date: str  # ISO YYYY-MM-DD
    sleep_h: float | None = None
    fatigue: int | None = None  # 1 (none) .. 10 (exhausted)
    soreness: int | None = None  # 1 (none) .. 10 (very sore)
    motivation: int | None = None  # 1 (none) .. 10 (high)
    notes: str | None = None
    hrv_rmssd: float | None = None
    # Provenance (A4): garmin_proxy | health_connect | manual | voice.
    # Drives precedence so a Garmin proxy never overwrites a voice debrief.
    source: str | None = None


class DailyWellnessSnapshot(BaseModel):
    """Garmin's native daily wellness values (GARMIN_DATA_PLAN.md phase 0c).

    Unlike :class:`DailyCheckin` (subjective 1-10 scales), this keeps Garmin's
    own numbers verbatim so the *live* metrics Garmin may stop exposing over
    time (A3 — body battery, training readiness, overnight HRV, stress) are
    captured the day they exist. Every metric is optional: a device that lacks
    one still produces a partial row.
    """

    model_config = ConfigDict(extra="ignore")

    date: str  # ISO YYYY-MM-DD
    sleep_seconds: int | None = None  # Garmin's measured sleep time
    sleep_score: int | None = None  # 0-100 overall sleep score
    hrv_last_night_avg: float | None = None  # ms, Garmin's overnight RMSSD average
    hrv_status: str | None = None  # e.g. BALANCED, UNBALANCED, LOW, POOR
    resting_hr: int | None = None  # bpm
    body_battery_charged: int | None = None  # points gained over the day
    body_battery_drained: int | None = None  # points spent over the day
    stress_avg: int | None = None  # 0-100, Garmin's daily average stress
    training_readiness_score: int | None = None  # 0-100
    training_readiness_level: str | None = None  # e.g. READY, LOW, MODERATE
    source: str = "garmin"

    def is_empty(self) -> bool:
        """True when no metric was captured, so the snapshot is not worth storing."""
        return all(getattr(self, name) is None for name in _WELLNESS_METRIC_FIELDS)


# Metric fields of DailyWellnessSnapshot (excludes date/source): a snapshot with
# all of these None carries no Garmin data and is skipped by the capture job.
_WELLNESS_METRIC_FIELDS: tuple[str, ...] = (
    "sleep_seconds",
    "sleep_score",
    "hrv_last_night_avg",
    "hrv_status",
    "resting_hr",
    "body_battery_charged",
    "body_battery_drained",
    "stress_avg",
    "training_readiness_score",
    "training_readiness_level",
)


class AthleteModelEstimate(BaseModel):
    """One learned athlete constant (Roadmap A5 · Digital Twin v0).

    ``value`` is the current best estimate; ``confidence`` is the number of
    samples it rests on; ``learning`` is True when there aren't enough samples
    yet, so ``value`` is the population default rather than a personal figure.
    """

    value: float
    confidence: int = 0
    learning: bool = True


class AthleteModel(BaseModel):
    """The athlete's learned model — three constants that become variables (A5).

    - ``ramp_tolerance_pct``: max week-over-week volume increase absorbed safely.
    - ``recovery_halflife_days``: typical days to bounce back from a hard effort.
    - ``heat_sensitivity_s_per_c``: pace penalty (s/km) per °C above 15°C.
    """

    ramp_tolerance_pct: AthleteModelEstimate
    recovery_halflife_days: AthleteModelEstimate
    heat_sensitivity_s_per_c: AthleteModelEstimate
    computed_at: str | None = None


class DebriefIn(BaseModel):
    """A free-text (or transcribed voice) post-run debrief (Roadmap A4)."""

    text: str
    activity_id: int | None = None


class DebriefResult(BaseModel):
    """Structured signals extracted from a voice/text debrief (Roadmap A4).

    ``notes`` always echoes the athlete's own words; every other field is
    ``None`` when the debrief didn't mention it (never invented).
    """

    model_config = ConfigDict(extra="ignore")

    rpe: int | None = None  # perceived effort 1-10
    soreness: int | None = None  # 1 (none) .. 10 (very sore)
    pain_location: str | None = None  # e.g. "polpaccio destro"
    mood: str | None = None  # short free text, e.g. "bene", "stanco"
    notes: str = ""
    activity_id: int | None = None  # the run the debrief was attached to


class Race(BaseModel):
    """A race in the season plan (GAP 16). Priority A is the main goal."""

    name: str | None = None
    race_type: str = "general"
    date: str | None = None  # ISO
    target_time: str | None = None
    priority: str = "A"  # A | B | C


class HRZones(BaseModel):
    """Personalised heart-rate zones (bpm), used to read real intensity.

    Closes GAP 6: the coach can only prescribe "run in Z2" if it knows the
    athlete's Z2. Each zone is an inclusive ``[low, high]`` bpm range.
    """

    z1_hr: tuple[int, int] | None = None
    z2_hr: tuple[int, int] | None = None
    z3_hr: tuple[int, int] | None = None
    z4_hr: tuple[int, int] | None = None
    z5_hr: tuple[int, int] | None = None

    def zone_of(self, hr: int | None) -> int | None:
        """Return the zone number (1-5) a heart rate falls into, if known."""
        if hr is None:
            return None
        for idx, bounds in enumerate(
            (self.z1_hr, self.z2_hr, self.z3_hr, self.z4_hr, self.z5_hr), start=1
        ):
            if bounds and bounds[0] <= hr <= bounds[1]:
                return idx
        return None


class AthletePhysiology(BaseModel):
    """Physiological thresholds that anchor intensity (GAP 7).

    Paces are ``M:SS`` strings; thresholds update over time as fitness changes.
    """

    lt1_pace: str | None = None  # aerobic threshold pace
    lt2_pace: str | None = None  # anaerobic / lactate threshold pace
    critical_speed: str | None = None
    resting_hr: int | None = None
    lactate_threshold_hr: int | None = None
    # AthleteModel v1: derived metrics that individualise coaching decisions.
    # Pace degradation per 10 km in long runs (sec/km per 10 km). Lower = more durable.
    durability_index: float | None = None
    # Difference between LT2 pace and best-5K pace (sec/km). Higher = more speed reserve.
    speed_reserve_sec: float | None = None


class Goal(BaseModel):
    """A target race the training plan works towards (GAP 1, 16).

    ``priority`` follows the A/B/C convention: A is the season's main race,
    B/C are supporting tune-up races.
    """

    goal_type: str = "general"  # e.g. marathon, half, 10k, general
    target_date: str | None = None  # ISO YYYY-MM-DD
    target_time: str | None = None  # HH:MM:SS
    priority: str = "A"  # A | B | C

    def days_to_go(self, ref: date | None = None) -> int | None:
        """Days from ``ref`` (default today) to the race, or None if no date."""
        if not self.target_date:
            return None
        try:
            target = date.fromisoformat(self.target_date[:10])
        except ValueError:
            return None
        return (target - (ref or date.today())).days


class AthleteProfile(BaseModel):
    """Structured athlete model (GAP 15, 23): replaces the free-text profile.

    Optional everywhere so the app keeps running with zero configuration.
    """

    age: int | None = None
    sex: str | None = None  # M | F | other
    height_cm: float | None = None
    weight_kg: float | None = None
    experience_years: float | None = None
    max_hr: int | None = None
    resting_hr: int | None = None
    weekly_runs: int | None = None
    # Coaching calibration (priority #4): scale all the thresholds coherently.
    level: str = "intermediate"  # beginner | intermediate | advanced
    risk_tolerance: str = "moderate"  # conservative | moderate | aggressive
    available_days: list[str] = Field(default_factory=list)
    zones: HRZones | None = None
    physiology: AthletePhysiology | None = None
    goal: Goal | None = None
    # Secondary races (B/C) beyond the main goal (GAP 16).
    races: list[Race] = Field(default_factory=list)
    notes: str | None = None


class TrailMetrics(BaseModel):
    """Trail/hilly-run specific metrics (GAP 20)."""

    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
    vertical_speed_m_per_h: float | None = None  # climb rate (VAM)
    climb_per_km: float | None = None  # D+ density
    time_on_feet_min: float | None = None
    equivalent_flat_km: float | None = None  # distance adjusted for climb
    is_trail: bool = False


class InjuryRisk(BaseModel):
    """Composite overuse-injury risk (GAP 14)."""

    score: float = 0.0  # 0-100
    level: str = "low"  # low | moderate | high
    factors: list[str] = Field(default_factory=list)


class AthleteSnapshot(BaseModel):
    """Long-horizon training memory for the coach (GAP 22)."""

    runs_count: int = 0
    total_distance_km: float = 0.0
    avg_weekly_volume_km: float = 0.0
    longest_run_km: float = 0.0
    best_5k: str | None = None
    best_10k: str | None = None
    best_half: str | None = None
    best_marathon: str | None = None


class RacePrediction(BaseModel):
    """Predicted finish time and target probability for the goal race (Fase 4)."""

    goal_type: str
    distance_km: float
    predicted_time: str | None = None
    predicted_seconds: float | None = None
    target_time: str | None = None
    target_seconds: float | None = None
    probability: float | None = None  # 0-1 of hitting the target time
    basis: str | None = None  # which effort/method the estimate rests on
    confidence: str = "low"  # low | medium | high


class WeeklyRecap(BaseModel):
    """Shareable weekly summary (Roadmap A6): the Sunday-evening recap card."""

    model_config = ConfigDict(extra="ignore")

    week_start: str  # ISO YYYY-MM-DD, Monday
    week_end: str  # ISO YYYY-MM-DD, Sunday
    distance_km: float
    runs_count: int
    adherence_pct: float | None = None  # % of plan-covered days honoured
    avg_execution_score: float | None = None
    best_moment: str | None = None  # a PR, a great session, or the week's long run
    narrative: str = ""  # LLM voice (A1) over the same facts, guarded, or a template


class RaceRecap(BaseModel):
    """Shareable race-day summary (Roadmap A6): prediction vs. reality."""

    model_config = ConfigDict(extra="ignore")

    activity_id: int
    date: str
    distance_km: float
    actual_time: str
    predicted_time: str | None = None
    delta_seconds: float | None = None  # actual - predicted; negative = faster
    delta_label: str | None = None  # e.g. "42s più veloce del previsto"
    splits_km: list[str] | None = None
    narrative: str = ""


class WhatIfRequest(BaseModel):
    """Request one what-if simulation on the active plan (Roadmap A7)."""

    scenario: str  # skip_next_long | sick_one_week | add_training_day


class WhatIfResultOut(BaseModel):
    """Baseline-vs-scenario comparison for a plan what-if (A7). No persistence."""

    scenario: str
    baseline_race_time: str | None = None
    scenario_race_time: str | None = None
    race_time_delta_seconds: float | None = None  # +ve = slower than baseline
    race_time_delta_label: str | None = None  # human "42s più lento", etc.
    baseline_tsb_at_race: float
    scenario_tsb_at_race: float
    risk_notes: list[str] = Field(default_factory=list)


class PhasePlan(BaseModel):
    """One periodization phase in the macrocycle (GAP 2/17)."""

    name: str  # base | build | specific | peak | taper | race
    start_date: str  # ISO
    end_date: str  # ISO
    weeks: int
    volume_factor: float  # weekly volume relative to the athlete's baseline
    intensity_focus: str
    key_workouts: list[str] = Field(default_factory=list)


class PeriodizationPlan(BaseModel):
    """The full macrocycle from today to the goal race."""

    goal_type: str
    target_date: str
    weeks_to_race: int
    baseline_km: float
    current_phase: str
    phases: list[PhasePlan] = Field(default_factory=list)


class TrainingMetrics(BaseModel):
    """Derived training-load and form metrics for a window of activities."""

    runs_count: int = 0
    total_distance_km: float = 0.0
    total_duration_min: float = 0.0
    weekly_distance_km: float = 0.0
    acute_load_km: float = 0.0  # last 7 days
    chronic_load_km: float = 0.0  # last 28 days (weekly average)
    # Internal (physiological) load over the acute window, in load units
    # (Session Load = RPE × minutes, with TRIMP/estimated fallbacks). GAP 4/10.
    acute_load_internal: float = 0.0
    chronic_load_internal: float = 0.0  # daily average over 42 days
    load_source: str | None = None  # garmin | mixed | srpe — internal-load origin
    # Fitness/Fatigue model (GAP 8) — the new headline signals.
    ctl: float | None = None  # chronic training load (fitness), 42-day EWMA
    atl: float | None = None  # acute training load (fatigue), 7-day EWMA
    tsb: float | None = None  # training stress balance (form) = CTL - ATL
    acwr: float | None = None  # acute:chronic ratio — kept as a SECONDARY check
    monotony: float | None = None  # weekly load monotony (mean/std of daily load)
    easy_ratio: float | None = None  # fraction of easy volume (target ~0.8)
    moderate_ratio: float | None = None  # fraction of Z3 "moderate" volume
    hard_ratio: float | None = None  # fraction of Z4+ "hard" volume
    form_state: str = "unknown"  # fresh | balanced | fatigued | detraining | unknown
    form_explanation: str = ""
    load_trend: str = "stable"  # rising | stable | falling
    week_start: str | None = None
    # Periodization (populated only when a goal with a target date is set). GAP 2/17.
    phase: str | None = None  # base | build | specific | peak | taper | race
    phase_focus: str | None = None
    weeks_to_race: int | None = None
    phase_volume_target_km: float | None = None
    # Injury risk (GAP 14) and aerobic-efficiency progress (GAP 13).
    injury_score: float | None = None
    injury_level: str | None = None  # low | moderate | high
    injury_factors: list[str] = Field(default_factory=list)
    aerobic_efficiency: float | None = None  # pace-sec per beat on easy runs
    efficiency_trend: str | None = None  # improving | stable | declining | unknown
    # Daily readiness from the latest wellness check-in (GAP 9).
    readiness: float | None = None  # 0-100
    readiness_state: str | None = None  # green | amber | red | unknown
    hrv_rmssd: float | None = None
    hrv_status: str | None = None  # "low" | "normal" | "high" | "unknown"
    hrv_learning: bool = False  # <21 days of history: baseline uses absolute fallback
    hrv_days_tracked: int | None = None  # valid HRV days seen, for "day X/21" UI copy
    # Goal-race forecast (Fase 4): predicted finish + probability of the target.
    predicted_race_time: str | None = None
    race_probability: float | None = None  # 0-1
    race_confidence: str | None = None  # low | medium | high
    # Latest Garmin VO2max and adaptive-plan adjustments (Fase 4).
    vo2max: float | None = None
    adaptive_notes: list[str] = Field(default_factory=list)


class CoachDecision(BaseModel):
    """Structured "what to do today" recommendation from the Coach Decision Engine.

    The single dominant output the home screen leads with. Every decision carries
    its reasoning: the signals it used, the confidence, what data was missing,
    alternatives and any safety flags — so the athlete can trust and understand it.
    """

    date: str  # ISO YYYY-MM-DD the decision is for
    decision: str  # run | easy | quality | long | rest | modify | caution
    headline: str  # short dominant title, e.g. "Corsa facile 8 km"
    prescription: str  # concrete what-to-do
    rationale: str  # plain-language why (the motivation)
    confidence: str = "medium"  # low | medium | high
    signals: list[str] = Field(default_factory=list)  # evidence used
    missing_data: list[str] = Field(default_factory=list)  # gaps that lower confidence
    alternatives: list[str] = Field(default_factory=list)  # other valid options
    safety_flags: list[str] = Field(default_factory=list)  # warnings
    # Link + prescription details when the decision maps to a plan session.
    plan_session_id: int | None = None
    session_type: str | None = None  # easy | long | tempo | intervals | rest | ...
    target_distance_km: float | None = None
    target_pace: str | None = None
    target_duration_min: float | None = None
    daily_note: str = ""  # short, human, motivational one-liner (Roadmap #3)
    source: str = "rules"  # rules | ai
    # Feedback loop (P2-1): what the coach expects to happen, so outcomes can be
    # compared retrospectively and the engine calibrated.
    expected_outcome: str | None = None
    # Engine version for compatibility between persisted and recomputed decisions.
    engine_version: str = "2.0"


class CoachActionRequest(BaseModel):
    """A Today-card action from the athlete (Roadmap #2, actionable decision)."""

    action: str  # done | reduce | defer | problem
    detail: str | None = None  # for "problem": tired | pain
    rpe: int | None = None  # 1-10, required for "done" to validate execution (P0-3)


class CoachEventOut(BaseModel):
    """One entry in the coach audit log (Roadmap #5)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    date: str
    event_type: str  # decision | plan_adapted | action | execution
    title: str
    detail: str = ""
    signals: list[str] | None = None
    before: dict | None = None
    after: dict | None = None
    plan_session_id: int | None = None
    notifiable: bool = False
    notified: bool = False
    created_at: str | None = None


class NotificationOut(BaseModel):
    """A pending coach notification (Roadmap #6), sourced from a notifiable event."""

    id: int
    title: str
    body: str
    date: str
    event_type: str
    priority: str = "medium"  # high | medium | low (P3-2)


class NotificationAck(BaseModel):
    """IDs of notifications the client has delivered, to mark them as sent."""

    ids: list[int] = Field(default_factory=list)


class DeviceIn(BaseModel):
    """FCM token registration payload (Roadmap A3)."""

    fcm_token: str = Field(..., min_length=1, max_length=512)
    platform: str = "android"


class DeviceOut(BaseModel):
    """Registered device response (Roadmap A3)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    fcm_token: str
    platform: str


class ExecutionResult(BaseModel):
    """How faithfully a completed activity matched its prescribed plan session.

    The Workout Execution Score (Roadmap #9): the coach can only adapt from real
    compliance if it knows whether "8 km easy" were actually run easy. Produced by
    comparing distance, duration, session type and intensity (with RPE/HR when
    present) of the executed activity against the prescription.
    """

    plan_session_id: int | None = None
    activity_id: int | None = None
    date: str
    execution_score: float = 0.0  # 0-100
    execution_status: str = "skipped"
    # completed_well | too_hard | too_short | skipped | turned_easy |
    # quality_missed | volume_excess
    execution_notes: str = ""
    evidence: list[str] = Field(default_factory=list)
    # Multi-dimensional sub-scores (P0-5, P0-6): volume, intensity (time-in-zone),
    # pace, structure and distribution. None when not computable.
    volume_score: float | None = None
    intensity_score: float | None = None
    pace_score: float | None = None
    structure_score: float | None = None
    distribution_score: float | None = None
    # Percentage of time spent in the target HR zone (when hr_zones available).
    time_in_zone_pct: float | None = None


class WeeklyBucket(BaseModel):
    """Aggregated stats for a single ISO week (used by the dashboard chart)."""

    week_start: str
    distance_km: float = 0.0
    duration_min: float = 0.0
    runs: int = 0


class CoachingResult(BaseModel):
    """Output of the coaching layer."""

    scope: str = "single"  # single | weekly
    model: str = "offline"
    analysis: str = ""
    next_workout: str = ""
    # Confidence and missing data for AI report transparency (Roadmap #5).
    confidence: str = "medium"  # low | medium | high
    missing_data: list[str] = Field(default_factory=list)

    def as_markdown(self) -> str:
        return f"## Analisi\n\n{self.analysis}\n\n## Prossimo allenamento\n\n{self.next_workout}\n"


class ActivityOut(BaseModel):
    """API response model for a stored activity."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    garmin_activity_id: str | None
    strava_activity_id: str | None = None
    health_connect_id: str | None = None
    live_id: str | None = None
    date: str
    sport: str = "run"
    activity_type: str
    duration_min: float
    distance_km: float
    avg_pace: str | None
    avg_hr: int | None
    max_hr: int | None
    elevation_gain_m: float | None
    avg_cadence: int | None
    rpe: int | None
    notes: str | None
    # Semi-structured extras and Garmin-derived rich metrics. All optional so
    # manual entries and demo runs without enrichment still validate. These let
    # the native app render a full per-activity detail view.
    hr_zones: dict[str, float] | None = None
    splits_km: list[str] | None = None
    temperature_c: float | None = None
    humidity_pct: float | None = None
    elevation_loss_m: float | None = None
    garmin_training_load: float | None = None
    vigorous_minutes: float | None = None
    moderate_minutes: float | None = None
    body_battery_delta: int | None = None
    stamina_drop: float | None = None
    avg_grade_adjusted_pace: str | None = None
    fastest_split_1k: str | None = None
    fastest_split_5k: str | None = None
    vo2max: float | None = None
    aerobic_training_effect: float | None = None
    anaerobic_training_effect: float | None = None
    aerobic_te_message: str | None = None
    anaerobic_te_message: str | None = None
    altitude_profile: list[float] | None = None
    route_polyline: str | None = None
    # Optional shoe reference for mileage tracking (Roadmap #6).
    shoe_id: int | None = None


class ReportOut(BaseModel):
    """API response model for a coaching report."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    activity_id: int | None
    scope: str
    model: str
    analysis: str
    next_workout: str
    metrics: dict | None = None
    # Confidence and missing data for AI report transparency (Roadmap #5).
    confidence: str = "medium"  # low | medium | high
    missing_data: list[str] | None = None
    created_at: str | None = None


class ManualActivityIn(BaseModel):
    """Payload for manually creating an activity via the API."""

    date: str
    activity_type: str = Field(default="easy")
    duration_min: float = 0.0
    distance_km: float = 0.0
    avg_hr: int | None = None
    rpe: int | None = None
    notes: str | None = None


class LiveSample(BaseModel):
    """One point of the sampled series of a phone-recorded run (G1)."""

    t: float  # seconds since start
    d: float  # cumulative distance, km
    hr: int | None = None


class LiveLap(BaseModel):
    """A manual lap press: cumulative time/distance at the press (G1)."""

    t: float
    d: float


class LiveRunIn(BaseModel):
    """A run recorded live on the phone, uploaded by the offline queue (G1).

    ``live_id`` is a client-generated UUID: retries of the same upload are
    deduped on it, so the queue can retry forever without duplicating.
    """

    live_id: str
    date: str  # ISO YYYY-MM-DD
    start_time: str | None = None  # local "HH:MM"
    duration_min: float
    distance_km: float
    samples: list[LiveSample] = Field(default_factory=list)
    laps: list[LiveLap] = Field(default_factory=list)
    route_polyline: str | None = None
    name: str | None = None


class HealthConnectRun(BaseModel):
    """One running session read from Android Health Connect (Roadmap A2).

    Compact by design: no per-km splits (v0 derives pace from distance+duration
    server-side). ``hr_samples`` is an optional sampled bpm series used only to
    fill avg/max HR when the source didn't provide them.
    """

    health_connect_id: str
    date: str  # ISO YYYY-MM-DD
    start_time: str | None = None  # local "HH:MM"
    duration_min: float = 0.0
    distance_km: float = 0.0
    avg_hr: int | None = None
    max_hr: int | None = None
    elevation_gain_m: float | None = None
    hr_samples: list[int] | None = None
    route_polyline: str | None = None
    name: str | None = None  # user-set title, feeds session-type inference


class HealthConnectWellness(BaseModel):
    """One day of sleep/HRV from Health Connect (Roadmap A2)."""

    date: str
    sleep_h: float | None = None
    hrv_rmssd: float | None = None


class HealthConnectImportIn(BaseModel):
    """Batch import payload from the Health Connect sync worker (Roadmap A2)."""

    runs: list[HealthConnectRun] = []
    wellness: list[HealthConnectWellness] = []


class HealthConnectImportResult(BaseModel):
    """Result of a Health Connect batch import (Roadmap A2)."""

    imported: int
    wellness_days: int
    activities: list[ActivityOut] = []


class StravaStatus(BaseModel):
    """Connection + webhook status for the Strava integration."""

    enabled: bool = False  # credentials configured
    connected: bool = False  # an athlete has authorised the app
    athlete_id: int | None = None
    athlete_name: str | None = None
    subscription_active: bool = False  # a push subscription exists at Strava
    pending_events: int = 0  # unprocessed webhook events in the inbox
    authorize_url: str | None = None  # where to send the user to connect


class ActivityPatch(BaseModel):
    """Partial update for an activity — only fields that are not None are written."""

    rpe: int | None = None
    notes: str | None = None


class PersonalRecord(BaseModel):
    """Best-ever performance at a canonical distance."""

    distance: str  # "1K", "5K split", "5K", "10K", "21K", "42K"
    pace: str  # "M:SS/km"
    date: str  # ISO date the PR was set
    activity_id: int | None = None


class Badge(BaseModel):
    """A gamification achievement."""

    id: str
    label: str
    earned: bool = False
    earned_date: str | None = None  # ISO date earned, if available


class GamificationData(BaseModel):
    """Streak and badge summary for the gamification layer."""

    streak_days: int = 0
    streak_days_best: int = 0
    streak_kind: str = "runs"  # "adherence" (plan-aware) | "runs" (legacy, no active plan)
    total_badges_earned: int = 0
    badges: list[Badge] = Field(default_factory=list)


class PeriodStats(BaseModel):
    """Aggregate training statistics for a time window."""

    period: str  # month | year | all-time
    total_runs: int = 0
    total_km: float = 0.0
    total_duration_h: float = 0.0
    total_elevation_m: int = 0
    avg_pace: str | None = None
    longest_run_km: float = 0.0
    fastest_pace: str | None = None


# ── Multi-week training plan schemas ──────────────────────────────────────────


class PlanSessionOut(BaseModel):
    """API response model for one session in a training plan week."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    day_of_week: int
    session_type: str  # easy|long|tempo|intervals|rest|race|cross|strides
    title: str
    description: str | None = None
    target_distance_km: float | None = None
    target_pace: str | None = None  # "M:SS/km"
    target_duration_min: float | None = None
    completed: bool
    completed_at: datetime | None = None
    adjustment_note: str | None = None  # set by the adaptive engine (Roadmap #8)
    # Workout Execution Score (Roadmap #9) — filled once a matching activity is
    # scored against this session.
    execution_score: float | None = None
    execution_status: str | None = None
    execution_note: str | None = None


class PlanWeekOut(BaseModel):
    """API response model for one week in a training plan."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    week_number: int
    phase: str
    target_km: float
    description: str | None = None
    sessions: list[PlanSessionOut]
    completion_pct: float = 0.0  # computed: completed non-rest / total non-rest


class TrainingPlanOut(BaseModel):
    """API response model for a complete multi-week training plan."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    goal_type: str
    goal_date: str
    goal_time: str | None = None
    level: str
    weeks_total: int
    start_date: str
    status: str
    current_week_number: int  # 1-based, computed from today vs start_date
    weeks_remaining: int
    overall_completion_pct: float
    current_week: PlanWeekOut | None = None
    weeks: list[PlanWeekOut]


class PlanSessionMoveRequest(BaseModel):
    """Move a plan session to another calendar day (Roadmap #12)."""

    target_date: str  # ISO YYYY-MM-DD, within the plan and not in the past


class PlanMoveResult(BaseModel):
    """Outcome of a session move: the recalculated plan plus safety warnings."""

    plan: TrainingPlanOut
    warnings: list[str] = Field(default_factory=list)


class PlanChatMessage(BaseModel):
    """One turn in the pre-plan AI chat."""

    role: str  # "user" or "assistant"
    content: str


class PlanChatRequest(BaseModel):
    """Request body for the pre-plan chat endpoint."""

    messages: list[PlanChatMessage]


class PlanChatResponse(BaseModel):
    """Response from the pre-plan chat endpoint."""

    message: str
    is_complete: bool = False
    runner_context: str | None = None  # JSON string with extracted runner profile


class PlanGenerateRequest(BaseModel):
    """Request body for generating a new multi-week training plan."""

    goal_type: str = "marathon"
    goal_date: str
    goal_time: str | None = None
    level: str = "intermediate"
    days_per_week: int = 4
    long_run_day: int = 6  # 0=Mon, 6=Sun (default Sunday)
    runner_context: str | None = None  # JSON summary from pre-plan chat


# ── Coach chat schemas ───────────────────────────────────────────────────────

class ChatMessageOut(BaseModel):
    """One turn in a coach chat session."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    role: str
    content: str
    model_used: str | None = None
    tier: str | None = None
    created_at: datetime


class ChatSessionOut(BaseModel):
    """A coach chat session with its message count."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    mode: str = "general"  # general | plan_negotiation (A8)
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ChatSendRequest(BaseModel):
    """Request body for sending a chat message to the coach."""

    session_id: int | None = None
    message: str
    # Unified chat (A8): only honoured when the session is created by this
    # message; an existing session keeps the mode it was born with.
    mode: str | None = None  # general | plan_negotiation


class ChatSendResponse(BaseModel):
    """Response after sending a chat message."""

    session_id: int
    session_title: str
    reply: str
    model_used: str
    tier: str
    # Unified chat (A8): plan-negotiation surface. ``plan_ready`` mirrors the
    # §READY§ sentinel; ``runner_context`` is the extracted §CTX§ JSON string,
    # ready to feed ``POST /api/plan/generate``.
    mode: str = "general"
    plan_ready: bool = False
    runner_context: str | None = None


# ── Workout builder schemas ───────────────────────────────────────────────────


class WorkoutSegmentIn(BaseModel):
    """One segment in a workout template (input)."""

    position: int
    segment_type: str  # warmup|interval_block|easy|threshold|cooldown|marathon_pace|strides
    repetitions: int = 1
    work_duration_sec: float | None = None
    work_distance_km: float | None = None
    work_pace: str | None = None  # "M:SS/km"
    rest_duration_sec: float | None = None
    rest_type: str | None = None  # jog|walk
    notes: str | None = None


class WorkoutSegmentOut(WorkoutSegmentIn):
    """One segment in a workout template (output)."""

    id: int
    model_config = ConfigDict(from_attributes=True)


class WorkoutTemplateIn(BaseModel):
    """Payload for creating a workout template."""

    name: str
    description: str | None = None
    type: str = "custom"
    segments: list[WorkoutSegmentIn]


class WorkoutTemplateOut(BaseModel):
    """API response model for a workout template."""

    id: int
    name: str
    description: str | None = None
    type: str
    estimated_distance_km: float | None = None
    estimated_duration_min: float | None = None
    created_at: datetime
    segments: list[WorkoutSegmentOut]
    model_config = ConfigDict(from_attributes=True)


class WorkoutSuggestRequest(BaseModel):
    """Request body for AI workout suggestion."""

    session_type: str = "intervals"  # intervals|tempo|long|easy|strides
    goal_type: str | None = None  # marathon|half|10k|5k
    goal_time: str | None = None
    notes: str | None = None  # free-text hint from user


class HeatmapRoute(BaseModel):
    activity_id: int
    date: str
    distance_km: float
    points: list[list[float]]  # [[lat, lon], ...]


class HeatmapResponse(BaseModel):
    routes: list[HeatmapRoute]
    total_with_gps: int
    total_activities: int


class Vo2maxPoint(BaseModel):
    date: str
    vo2max: float


class Vo2maxHistory(BaseModel):
    points: list[Vo2maxPoint]
    trend: str


# ── Shoe tracking schemas (Roadmap #6) ───────────────────────────────────────


class ShoeIn(BaseModel):
    """Payload for creating or updating a shoe."""

    name: str
    brand: str | None = None
    model: str | None = None
    purchase_date: str | None = None  # ISO YYYY-MM-DD
    max_km: float = 800.0
    retired: bool = False
    notes: str | None = None


class ShoeOut(BaseModel):
    """API response model for a shoe, with computed mileage and wear status."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: str | None = None
    model: str | None = None
    purchase_date: str | None = None
    max_km: float
    retired: bool = False
    notes: str | None = None
    total_km: float = 0.0  # computed from activities referencing this shoe
    wear_pct: float = 0.0  # total_km / max_km * 100
    replacement_due: bool = False  # wear_pct >= 100 and not retired


class OnboardingStatus(BaseModel):
    """Onboarding checklist completion state (Roadmap #4)."""

    connect_data: bool = False
    set_goal: bool = False
    first_checkin: bool = False
    generate_plan: bool = False
    first_recommendation: bool = False
    complete: bool = False
    next_step: str | None = None
