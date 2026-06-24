package com.runningcoach.app.data.model

import com.google.gson.annotations.SerializedName

/** Compact training-load and form metrics computed by the backend. */
data class TrainingMetrics(
    @SerializedName("runs_count") val runsCount: Int = 0,
    @SerializedName("total_distance_km") val totalDistanceKm: Double = 0.0,
    @SerializedName("weekly_distance_km") val weeklyDistanceKm: Double = 0.0,
    @SerializedName("acute_load_km") val acuteLoadKm: Double = 0.0,
    @SerializedName("chronic_load_km") val chronicLoadKm: Double = 0.0,
    @SerializedName("acwr") val acwr: Double? = null,
    @SerializedName("monotony") val monotony: Double? = null,
    @SerializedName("easy_ratio") val easyRatio: Double? = null,
    @SerializedName("form_state") val formState: String = "unknown",
    @SerializedName("form_explanation") val formExplanation: String = "",
    @SerializedName("load_trend") val loadTrend: String = "stable",
    @SerializedName("week_start") val weekStart: String? = null,
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
)
