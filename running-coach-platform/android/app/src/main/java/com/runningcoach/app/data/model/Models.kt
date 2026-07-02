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
    @SerializedName("hrv_rmssd") val hrvRmssd: Double? = null,
    @SerializedName("hrv_status") val hrvStatus: String? = null,
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
    @SerializedName("sport") val sport: String = "run",
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
    // Optional shoe reference for mileage tracking (Roadmap #6).
    @SerializedName("shoe_id") val shoeId: Int? = null,
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
    // Confidence and missing data for AI report transparency (Roadmap #5).
    @SerializedName("confidence") val confidence: String = "medium",
    @SerializedName("missing_data") val missingData: List<String>? = null,
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
    @SerializedName("hrv_rmssd") val hrvRmssd: Double? = null,
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

/** One session (or rest day) in a training plan week. */
data class PlanSession(
    @SerializedName("id") val id: Int,
    @SerializedName("day_of_week") val dayOfWeek: Int,
    @SerializedName("session_type") val sessionType: String,
    @SerializedName("title") val title: String,
    @SerializedName("description") val description: String? = null,
    @SerializedName("target_distance_km") val targetDistanceKm: Double? = null,
    @SerializedName("target_pace") val targetPace: String? = null,
    @SerializedName("target_duration_min") val targetDurationMin: Double? = null,
    @SerializedName("completed") val completed: Boolean = false,
    @SerializedName("completed_at") val completedAt: String? = null,
    @SerializedName("adjustment_note") val adjustmentNote: String? = null,
    @SerializedName("execution_score") val executionScore: Double? = null,
    @SerializedName("execution_status") val executionStatus: String? = null,
    @SerializedName("execution_note") val executionNote: String? = null,
)

/** One week in a multi-week training plan. */
data class PlanWeek(
    @SerializedName("id") val id: Int,
    @SerializedName("week_number") val weekNumber: Int,
    @SerializedName("phase") val phase: String,
    @SerializedName("target_km") val targetKm: Double,
    @SerializedName("description") val description: String? = null,
    @SerializedName("sessions") val sessions: List<PlanSession> = emptyList(),
    @SerializedName("completion_pct") val completionPct: Double = 0.0,
)

/** A complete multi-week structured training plan. */
data class TrainingPlan(
    @SerializedName("id") val id: Int,
    @SerializedName("goal_type") val goalType: String,
    @SerializedName("goal_date") val goalDate: String,
    @SerializedName("goal_time") val goalTime: String? = null,
    @SerializedName("level") val level: String,
    @SerializedName("weeks_total") val weeksTotal: Int,
    @SerializedName("start_date") val startDate: String,
    @SerializedName("status") val status: String,
    @SerializedName("current_week_number") val currentWeekNumber: Int,
    @SerializedName("weeks_remaining") val weeksRemaining: Int,
    @SerializedName("overall_completion_pct") val overallCompletionPct: Double,
    @SerializedName("current_week") val currentWeek: PlanWeek? = null,
    @SerializedName("weeks") val weeks: List<PlanWeek> = emptyList(),
)

/** One message in the pre-plan AI chat. */
data class PlanChatMessage(
    @SerializedName("role") val role: String,       // "user" or "assistant"
    @SerializedName("content") val content: String,
)

/** Request body for the pre-plan chat endpoint. */
data class PlanChatRequest(
    @SerializedName("messages") val messages: List<PlanChatMessage>,
)

/** Response from the pre-plan chat endpoint. */
data class PlanChatResponse(
    @SerializedName("message") val message: String,
    @SerializedName("is_complete") val isComplete: Boolean = false,
    @SerializedName("runner_context") val runnerContext: String? = null,
)

/** Request body for generating a new multi-week training plan. */
data class PlanGenerateRequest(
    @SerializedName("goal_type") val goalType: String = "marathon",
    @SerializedName("goal_date") val goalDate: String,
    @SerializedName("goal_time") val goalTime: String? = null,
    @SerializedName("level") val level: String = "intermediate",
    @SerializedName("days_per_week") val daysPerWeek: Int = 4,
    @SerializedName("long_run_day") val longRunDay: Int = 6,
    @SerializedName("runner_context") val runnerContext: String? = null,
)

/** One segment in a workout template. */
data class WorkoutSegment(
    val id: Int = 0,
    @SerializedName("position") val position: Int,
    @SerializedName("segment_type") val segmentType: String,
    @SerializedName("repetitions") val repetitions: Int = 1,
    @SerializedName("work_duration_sec") val workDurationSec: Double? = null,
    @SerializedName("work_distance_km") val workDistanceKm: Double? = null,
    @SerializedName("work_pace") val workPace: String? = null,
    @SerializedName("rest_duration_sec") val restDurationSec: Double? = null,
    @SerializedName("rest_type") val restType: String? = null,
    val notes: String? = null,
)

/** A reusable workout template with structured segments. */
data class WorkoutTemplate(
    val id: Int = 0,
    val name: String = "",
    val description: String? = null,
    val type: String = "custom",
    @SerializedName("estimated_distance_km") val estimatedDistanceKm: Double? = null,
    @SerializedName("estimated_duration_min") val estimatedDurationMin: Double? = null,
    @SerializedName("created_at") val createdAt: String? = null,
    val segments: List<WorkoutSegment> = emptyList(),
)

/** Request body for AI workout suggestion. */
data class WorkoutSuggestRequest(
    @SerializedName("session_type") val sessionType: String,
    @SerializedName("goal_type") val goalType: String? = null,
    @SerializedName("goal_time") val goalTime: String? = null,
    val notes: String? = null,
)

/** One message in a conversational coach session. */
data class ChatMessage(
    @SerializedName("id") val id: Int = 0,
    @SerializedName("session_id") val sessionId: Int = 0,
    @SerializedName("role") val role: String,           // "user" | "assistant"
    @SerializedName("content") val content: String,
    @SerializedName("model_used") val modelUsed: String? = null,
    @SerializedName("tier") val tier: String? = null,   // "simple" | "medium" | "complex"
    @SerializedName("created_at") val createdAt: String? = null,
)

/** A persisted conversational coach session. */
data class ChatSession(
    @SerializedName("id") val id: Int,
    @SerializedName("title") val title: String,
    @SerializedName("created_at") val createdAt: String? = null,
    @SerializedName("updated_at") val updatedAt: String? = null,
    @SerializedName("message_count") val messageCount: Int = 0,
)

/** Request body for sending a chat message. */
data class ChatSendRequest(
    @SerializedName("session_id") val sessionId: Int? = null,
    @SerializedName("message") val message: String,
)

/** Response from the chat send endpoint. */
data class ChatSendResponse(
    @SerializedName("session_id") val sessionId: Int,
    @SerializedName("session_title") val sessionTitle: String,
    @SerializedName("reply") val reply: String,
    @SerializedName("model_used") val modelUsed: String,
    @SerializedName("tier") val tier: String,
)

/** Strava connection + webhook status (mirrors app/schemas.py StravaStatus). */
data class StravaStatus(
    @SerializedName("enabled") val enabled: Boolean = false,
    @SerializedName("connected") val connected: Boolean = false,
    @SerializedName("athlete_id") val athleteId: Long? = null,
    @SerializedName("athlete_name") val athleteName: String? = null,
    @SerializedName("subscription_active") val subscriptionActive: Boolean = false,
    @SerializedName("pending_events") val pendingEvents: Int = 0,
    @SerializedName("authorize_url") val authorizeUrl: String? = null,
)

/** Partial update payload for an activity (RPE and/or notes). */
data class ActivityPatch(
    @SerializedName("rpe") val rpe: Int? = null,
    @SerializedName("notes") val notes: String? = null,
)

/** Running streak and earned badges. */
data class GamificationData(
    @SerializedName("streak_days") val streakDays: Int = 0,
    @SerializedName("streak_days_best") val streakDaysBest: Int = 0,
    @SerializedName("total_badges_earned") val totalBadgesEarned: Int = 0,
    @SerializedName("badges") val badges: List<Badge> = emptyList(),
)

/** One route with GPS track for the heatmap. */
data class HeatmapRoute(
    @SerializedName("activity_id") val activityId: Int,
    @SerializedName("date") val date: String,
    @SerializedName("distance_km") val distanceKm: Double,
    @SerializedName("points") val points: List<List<Double>>,
)

/** Response for the heatmap endpoint. */
data class HeatmapResponse(
    @SerializedName("routes") val routes: List<HeatmapRoute> = emptyList(),
    @SerializedName("total_with_gps") val totalWithGps: Int = 0,
    @SerializedName("total_activities") val totalActivities: Int = 0,
)

/** One VO2max reading over time. */
data class Vo2maxPoint(
    @SerializedName("date") val date: String,
    @SerializedName("vo2max") val vo2max: Double,
)

/** VO2max history with trend direction. */
data class Vo2maxHistory(
    @SerializedName("points") val points: List<Vo2maxPoint> = emptyList(),
    @SerializedName("trend") val trend: String = "insufficient_data",
)

// ── Shoe tracking models (Roadmap #6) ───────────────────────────────────────

data class ShoeIn(
    @SerializedName("name") val name: String,
    @SerializedName("brand") val brand: String? = null,
    @SerializedName("model") val model: String? = null,
    @SerializedName("purchase_date") val purchaseDate: String? = null,
    @SerializedName("max_km") val maxKm: Double = 800.0,
    @SerializedName("retired") val retired: Boolean = false,
    @SerializedName("notes") val notes: String? = null,
)

data class Shoe(
    val id: Int = 0,
    @SerializedName("name") val name: String,
    @SerializedName("brand") val brand: String? = null,
    @SerializedName("model") val model: String? = null,
    @SerializedName("purchase_date") val purchaseDate: String? = null,
    @SerializedName("max_km") val maxKm: Double = 800.0,
    @SerializedName("retired") val retired: Boolean = false,
    @SerializedName("notes") val notes: String? = null,
    @SerializedName("total_km") val totalKm: Double = 0.0,
    @SerializedName("wear_pct") val wearPct: Double = 0.0,
    @SerializedName("replacement_due") val replacementDue: Boolean = false,
)

// ── Onboarding status model (Roadmap #4) ─────────────────────────────────────

data class OnboardingStatus(
    @SerializedName("connect_data") val connectData: Boolean = false,
    @SerializedName("set_goal") val setGoal: Boolean = false,
    @SerializedName("first_checkin") val firstCheckin: Boolean = false,
    @SerializedName("generate_plan") val generatePlan: Boolean = false,
    @SerializedName("first_recommendation") val firstRecommendation: Boolean = false,
    @SerializedName("complete") val complete: Boolean = false,
    @SerializedName("next_step") val nextStep: String? = null,
)

/** The dominant "what to do today" decision from the Coach Decision Engine. */
data class CoachDecision(
    @SerializedName("date") val date: String = "",
    @SerializedName("decision") val decision: String = "easy",
    @SerializedName("headline") val headline: String = "",
    @SerializedName("prescription") val prescription: String = "",
    @SerializedName("rationale") val rationale: String = "",
    @SerializedName("confidence") val confidence: String = "medium",
    @SerializedName("signals") val signals: List<String> = emptyList(),
    @SerializedName("missing_data") val missingData: List<String> = emptyList(),
    @SerializedName("alternatives") val alternatives: List<String> = emptyList(),
    @SerializedName("safety_flags") val safetyFlags: List<String> = emptyList(),
    @SerializedName("plan_session_id") val planSessionId: Int? = null,
    @SerializedName("session_type") val sessionType: String? = null,
    @SerializedName("target_distance_km") val targetDistanceKm: Double? = null,
    @SerializedName("target_pace") val targetPace: String? = null,
    @SerializedName("target_duration_min") val targetDurationMin: Double? = null,
    @SerializedName("daily_note") val dailyNote: String = "",
    @SerializedName("source") val source: String = "rules",
)

/** Body for a Today-card action (done | reduce | defer | problem). */
data class CoachActionRequest(
    @SerializedName("action") val action: String,
    @SerializedName("detail") val detail: String? = null,
)

/** A pending coach notification (Roadmap #6). */
data class AppNotification(
    @SerializedName("id") val id: Int,
    @SerializedName("title") val title: String,
    @SerializedName("body") val body: String,
    @SerializedName("date") val date: String = "",
    @SerializedName("event_type") val eventType: String = "",
)

/** IDs the client has delivered, to mark notifications as sent. */
data class NotificationAck(
    @SerializedName("ids") val ids: List<Int>,
)

/** One entry in the coach audit diary (Roadmap #5). */
data class CoachEvent(
    @SerializedName("id") val id: Int,
    @SerializedName("date") val date: String,
    @SerializedName("event_type") val eventType: String,
    @SerializedName("title") val title: String,
    @SerializedName("detail") val detail: String = "",
    @SerializedName("signals") val signals: List<String>? = null,
    @SerializedName("notifiable") val notifiable: Boolean = false,
    @SerializedName("created_at") val createdAt: String? = null,
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
    @SerializedName("active_plan") val activePlan: TrainingPlan? = null,
    @SerializedName("today_decision") val todayDecision: CoachDecision? = null,
    @SerializedName("notifications") val notifications: List<AppNotification> = emptyList(),
    // Onboarding checklist (Roadmap #4).
    @SerializedName("onboarding") val onboarding: OnboardingStatus? = null,
    // Shoe tracking (Roadmap #6).
    @SerializedName("shoes") val shoes: List<Shoe> = emptyList(),
)
