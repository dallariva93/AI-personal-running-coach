package com.runningcoach.app.data.model

import com.google.gson.annotations.SerializedName

/** Compact training-load and form metrics computed by the backend ("brain"). */
data class TrainingMetrics(
    @SerializedName("runs_count") val runsCount: Int = 0,
    @SerializedName("total_distance_km") val totalDistanceKm: Double = 0.0,
    @SerializedName("weekly_distance_km") val weeklyDistanceKm: Double = 0.0,
    @SerializedName("acute_load_km") val acuteLoadKm: Double = 0.0,
    @SerializedName("chronic_load_km") val chronicLoadKm: Double = 0.0,
    @SerializedName("acute_load_internal") val acuteLoadInternal: Double = 0.0,
    @SerializedName("load_source") val loadSource: String? = null,
    // Fitness / Fatigue model.
    @SerializedName("ctl") val ctl: Double? = null,
    @SerializedName("atl") val atl: Double? = null,
    @SerializedName("tsb") val tsb: Double? = null,
    @SerializedName("acwr") val acwr: Double? = null,
    @SerializedName("monotony") val monotony: Double? = null,
    // Intensity distribution (three states).
    @SerializedName("easy_ratio") val easyRatio: Double? = null,
    @SerializedName("moderate_ratio") val moderateRatio: Double? = null,
    @SerializedName("hard_ratio") val hardRatio: Double? = null,
    @SerializedName("form_state") val formState: String = "unknown",
    @SerializedName("form_explanation") val formExplanation: String = "",
    @SerializedName("load_trend") val loadTrend: String = "stable",
    @SerializedName("week_start") val weekStart: String? = null,
    // Periodization.
    @SerializedName("phase") val phase: String? = null,
    @SerializedName("phase_focus") val phaseFocus: String? = null,
    @SerializedName("weeks_to_race") val weeksToRace: Int? = null,
    @SerializedName("phase_volume_target_km") val phaseVolumeTargetKm: Double? = null,
    // Injury risk + progress.
    @SerializedName("injury_score") val injuryScore: Double? = null,
    @SerializedName("injury_level") val injuryLevel: String? = null,
    @SerializedName("injury_factors") val injuryFactors: List<String> = emptyList(),
    @SerializedName("aerobic_efficiency") val aerobicEfficiency: Double? = null,
    @SerializedName("efficiency_trend") val efficiencyTrend: String? = null,
    // Recovery readiness.
    @SerializedName("readiness") val readiness: Double? = null,
    @SerializedName("readiness_state") val readinessState: String? = null,
    // Goal-race forecast.
    @SerializedName("predicted_race_time") val predictedRaceTime: String? = null,
    @SerializedName("race_probability") val raceProbability: Double? = null,
    @SerializedName("race_confidence") val raceConfidence: String? = null,
    // VO2max + adaptive plan notes.
    @SerializedName("vo2max") val vo2max: Double? = null,
    @SerializedName("adaptive_notes") val adaptiveNotes: List<String> = emptyList(),
)

/** Aggregated load for one ISO week. */
data class WeeklyBucket(
    @SerializedName("week_start") val weekStart: String,
    @SerializedName("distance_km") val distanceKm: Double = 0.0,
    @SerializedName("duration_min") val durationMin: Double = 0.0,
    @SerializedName("runs") val runs: Int = 0,
)

/** A single stored running activity. */
data class Activity(
    @SerializedName("id") val id: Int,
    @SerializedName("garmin_activity_id") val garminActivityId: String? = null,
    @SerializedName("date") val date: String,
    @SerializedName("activity_type") val activityType: String,
    @SerializedName("duration_min") val durationMin: Double,
    @SerializedName("distance_km") val distanceKm: Double,
    @SerializedName("avg_pace") val avgPace: String? = null,
    @SerializedName("avg_hr") val avgHr: Int? = null,
    @SerializedName("max_hr") val maxHr: Int? = null,
    @SerializedName("elevation_gain_m") val elevationGainM: Double? = null,
    @SerializedName("avg_cadence") val avgCadence: Int? = null,
    @SerializedName("rpe") val rpe: Int? = null,
    @SerializedName("notes") val notes: String? = null,
    // Garmin-derived rich metrics + semi-structured extras (all optional).
    @SerializedName("hr_zones") val hrZones: Map<String, Double>? = null,
    @SerializedName("splits_km") val splitsKm: List<String>? = null,
    @SerializedName("temperature_c") val temperatureC: Double? = null,
    @SerializedName("humidity_pct") val humidityPct: Double? = null,
    @SerializedName("elevation_loss_m") val elevationLossM: Double? = null,
    @SerializedName("garmin_training_load") val garminTrainingLoad: Double? = null,
    @SerializedName("vigorous_minutes") val vigorousMinutes: Double? = null,
    @SerializedName("moderate_minutes") val moderateMinutes: Double? = null,
    @SerializedName("body_battery_delta") val bodyBatteryDelta: Int? = null,
    @SerializedName("stamina_drop") val staminaDrop: Double? = null,
    @SerializedName("avg_grade_adjusted_pace") val avgGradeAdjustedPace: String? = null,
    @SerializedName("fastest_split_1k") val fastestSplit1k: String? = null,
    @SerializedName("fastest_split_5k") val fastestSplit5k: String? = null,
    @SerializedName("vo2max") val vo2max: Double? = null,
    @SerializedName("aerobic_training_effect") val aerobicTrainingEffect: Double? = null,
    @SerializedName("anaerobic_training_effect") val anaerobicTrainingEffect: Double? = null,
    @SerializedName("aerobic_te_message") val aerobicTeMessage: String? = null,
    @SerializedName("anaerobic_te_message") val anaerobicTeMessage: String? = null,
    @SerializedName("altitude_profile") val altitudeProfile: List<Double>? = null,
    @SerializedName("route_polyline") val routePolyline: String? = null,
)

/** A coaching report (single-run analysis or weekly plan). */
data class Report(
    @SerializedName("id") val id: Int,
    @SerializedName("activity_id") val activityId: Int? = null,
    @SerializedName("scope") val scope: String,
    @SerializedName("model") val model: String,
    @SerializedName("analysis") val analysis: String,
    @SerializedName("next_workout") val nextWorkout: String,
    @SerializedName("created_at") val createdAt: String? = null,
)

/** Predicted finish time and target probability for the goal race. */
data class RacePrediction(
    @SerializedName("goal_type") val goalType: String,
    @SerializedName("distance_km") val distanceKm: Double = 0.0,
    @SerializedName("predicted_time") val predictedTime: String? = null,
    @SerializedName("target_time") val targetTime: String? = null,
    @SerializedName("probability") val probability: Double? = null,
    @SerializedName("basis") val basis: String? = null,
    @SerializedName("confidence") val confidence: String = "low",
)

/** Long-horizon training memory (last 6 months). */
data class AthleteSnapshot(
    @SerializedName("runs_count") val runsCount: Int = 0,
    @SerializedName("total_distance_km") val totalDistanceKm: Double = 0.0,
    @SerializedName("avg_weekly_volume_km") val avgWeeklyVolumeKm: Double = 0.0,
    @SerializedName("longest_run_km") val longestRunKm: Double = 0.0,
    @SerializedName("best_5k") val best5k: String? = null,
    @SerializedName("best_10k") val best10k: String? = null,
    @SerializedName("best_half") val bestHalf: String? = null,
    @SerializedName("best_marathon") val bestMarathon: String? = null,
)

/** One periodization phase in the macrocycle. */
data class PhasePlan(
    @SerializedName("name") val name: String,
    @SerializedName("start_date") val startDate: String,
    @SerializedName("end_date") val endDate: String,
    @SerializedName("weeks") val weeks: Int = 0,
    @SerializedName("volume_factor") val volumeFactor: Double = 1.0,
    @SerializedName("intensity_focus") val intensityFocus: String = "",
    @SerializedName("key_workouts") val keyWorkouts: List<String> = emptyList(),
)

/** The full macrocycle from today to the goal race. */
data class PeriodizationPlan(
    @SerializedName("goal_type") val goalType: String = "",
    @SerializedName("target_date") val targetDate: String = "",
    @SerializedName("weeks_to_race") val weeksToRace: Int = 0,
    @SerializedName("current_phase") val currentPhase: String = "",
    @SerializedName("phases") val phases: List<PhasePlan> = emptyList(),
)

/** Target race the plan works towards. */
data class Goal(
    @SerializedName("goal_type") val goalType: String = "general",
    @SerializedName("target_date") val targetDate: String? = null,
    @SerializedName("target_time") val targetTime: String? = null,
    @SerializedName("priority") val priority: String = "A",
)

/** Structured athlete profile. */
data class AthleteProfile(
    @SerializedName("age") val age: Int? = null,
    @SerializedName("sex") val sex: String? = null,
    @SerializedName("max_hr") val maxHr: Int? = null,
    @SerializedName("resting_hr") val restingHr: Int? = null,
    @SerializedName("weekly_runs") val weeklyRuns: Int? = null,
    @SerializedName("level") val level: String = "intermediate",
    @SerializedName("risk_tolerance") val riskTolerance: String = "moderate",
    @SerializedName("goal") val goal: Goal? = null,
)

/** Subjective daily wellness check-in. */
data class DailyCheckin(
    @SerializedName("date") val date: String,
    @SerializedName("sleep_h") val sleepH: Double? = null,
    @SerializedName("fatigue") val fatigue: Int? = null,
    @SerializedName("soreness") val soreness: Int? = null,
    @SerializedName("motivation") val motivation: Int? = null,
)

/** Best-ever performance at a canonical distance. */
data class PersonalRecord(
    @SerializedName("distance") val distance: String,
    @SerializedName("pace") val pace: String,
    @SerializedName("date") val date: String,
    @SerializedName("activity_id") val activityId: Int? = null,
)

/** A gamification achievement (badge). */
data class Badge(
    @SerializedName("id") val id: String,
    @SerializedName("label") val label: String,
    @SerializedName("earned") val earned: Boolean = false,
    @SerializedName("earned_date") val earnedDate: String? = null,
)

/** Aggregate stats for a period (month / year / all-time). */
data class PeriodStats(
    @SerializedName("period") val period: String = "all-time",
    @SerializedName("total_runs") val totalRuns: Int = 0,
    @SerializedName("total_km") val totalKm: Double = 0.0,
    @SerializedName("total_duration_h") val totalDurationH: Double = 0.0,
    @SerializedName("total_elevation_m") val totalElevationM: Int = 0,
    @SerializedName("avg_pace") val avgPace: String? = null,
    @SerializedName("longest_run_km") val longestRunKm: Double = 0.0,
    @SerializedName("fastest_pace") val fastestPace: String? = null,
)

/** Running streak and earned badges. */
data class GamificationData(
    @SerializedName("streak_days") val streakDays: Int = 0,
    @SerializedName("streak_days_best") val streakDaysBest: Int = 0,
    @SerializedName("total_badges_earned") val totalBadgesEarned: Int = 0,
    @SerializedName("badges") val badges: List<Badge> = emptyList(),
)

/** Everything the app needs to render its main screens, in one response. */
data class Overview(
    @SerializedName("version") val version: String = "",
    @SerializedName("mode") val mode: String = "demo",
    @SerializedName("coach") val coach: String = "offline",
    @SerializedName("metrics") val metrics: TrainingMetrics = TrainingMetrics(),
    @SerializedName("weekly") val weekly: List<WeeklyBucket> = emptyList(),
    @SerializedName("activities") val activities: List<Activity> = emptyList(),
    @SerializedName("latest_analysis") val latestAnalysis: Report? = null,
    @SerializedName("latest_plan") val latestPlan: Report? = null,
    @SerializedName("profile") val profile: AthleteProfile? = null,
    @SerializedName("snapshot") val snapshot: AthleteSnapshot? = null,
    @SerializedName("prediction") val prediction: RacePrediction? = null,
    @SerializedName("plan") val plan: PeriodizationPlan? = null,
    @SerializedName("checkin") val checkin: DailyCheckin? = null,
    @SerializedName("personal_records") val personalRecords: List<PersonalRecord> = emptyList(),
    @SerializedName("pr_activity_ids") val prActivityIds: List<Int> = emptyList(),
    @SerializedName("gamification") val gamification: GamificationData? = null,
)
