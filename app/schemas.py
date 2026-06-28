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
    date: str  # ISO YYYY-MM-DD
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


class DailyCheckin(BaseModel):
    """Subjective daily wellness check-in (GAP 9). Scales are 1-10."""

    model_config = ConfigDict(extra="ignore")

    date: str  # ISO YYYY-MM-DD
    sleep_h: float | None = None
    fatigue: int | None = None  # 1 (none) .. 10 (exhausted)
    soreness: int | None = None  # 1 (none) .. 10 (very sore)
    motivation: int | None = None  # 1 (none) .. 10 (high)
    notes: str | None = None


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
    # Goal-race forecast (Fase 4): predicted finish + probability of the target.
    predicted_race_time: str | None = None
    race_probability: float | None = None  # 0-1
    race_confidence: str | None = None  # low | medium | high
    # Latest Garmin VO2max and adaptive-plan adjustments (Fase 4).
    vo2max: float | None = None
    adaptive_notes: list[str] = Field(default_factory=list)


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

    def as_markdown(self) -> str:
        return f"## Analisi\n\n{self.analysis}\n\n## Prossimo allenamento\n\n{self.next_workout}\n"


class ActivityOut(BaseModel):
    """API response model for a stored activity."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    garmin_activity_id: str | None
    strava_activity_id: str | None = None
    date: str
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


class PlanGenerateRequest(BaseModel):
    """Request body for generating a new multi-week training plan."""

    goal_type: str = "marathon"
    goal_date: str
    goal_time: str | None = None
    level: str = "intermediate"
    days_per_week: int = 4
    long_run_day: int = 6  # 0=Mon, 6=Sun (default Sunday)
