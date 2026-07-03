package com.runningcoach.app.data.repository

import com.runningcoach.app.data.model.Activity
import com.runningcoach.app.data.model.ActivityPatch
import com.runningcoach.app.data.model.AppNotification
import com.runningcoach.app.data.model.AthleteProfile
import com.runningcoach.app.data.model.ChatMessage
import com.runningcoach.app.data.model.ChatSendRequest
import com.runningcoach.app.data.model.ChatSendResponse
import com.runningcoach.app.data.model.ChatSession
import com.runningcoach.app.data.model.CoachActionRequest
import com.runningcoach.app.data.model.CoachDecision
import com.runningcoach.app.data.model.CoachEvent
import com.runningcoach.app.data.model.DailyCheckin
import com.runningcoach.app.data.model.DebriefIn
import com.runningcoach.app.data.model.DebriefResult
import com.runningcoach.app.data.model.DeviceIn
import com.runningcoach.app.data.model.HeatmapResponse
import com.runningcoach.app.data.model.OnboardingStatus
import com.runningcoach.app.data.model.Shoe
import com.runningcoach.app.data.model.ShoeIn
import com.runningcoach.app.data.model.NotificationAck
import com.runningcoach.app.data.model.Vo2maxHistory
import com.runningcoach.app.data.model.Overview
import com.runningcoach.app.data.model.PeriodStats
import com.runningcoach.app.data.model.PlanChatMessage
import com.runningcoach.app.data.model.PlanChatRequest
import com.runningcoach.app.data.model.PlanChatResponse
import com.runningcoach.app.data.model.PlanGenerateRequest
import com.runningcoach.app.data.model.PlanMoveResult
import com.runningcoach.app.data.model.PlanSession
import com.runningcoach.app.data.model.PlanSessionMoveRequest
import com.runningcoach.app.data.model.Report
import com.runningcoach.app.data.model.StravaStatus
import com.runningcoach.app.data.model.TrainingPlan
import com.runningcoach.app.data.model.WorkoutSuggestRequest
import com.runningcoach.app.data.model.WorkoutTemplate
import com.runningcoach.app.data.remote.ApiClient
import com.runningcoach.app.data.settings.SettingsStore
import kotlinx.coroutines.flow.first

/**
 * Single entry point for data access. Resolves the current connection settings
 * before each call so the app always targets the configured backend.
 */
class CoachRepository(private val settings: SettingsStore) {

    private suspend fun api() = settings.settings.first().let {
        ApiClient.service(it.baseUrl, it.token)
    }

    suspend fun overview(): Overview = api().overview()

    suspend fun activities(limit: Int = 50): List<Activity> = api().activities(limit)

    suspend fun reports(limit: Int = 20): List<Report> = api().reports(limit)

    suspend fun sync(): List<Activity> = api().ingest()

    suspend fun ingestWellness(): Int =
        runCatching { api().ingestWellness()["days_upserted"] ?: 0 }.getOrDefault(0)

    suspend fun ingestCrossTraining(): List<Activity> = api().ingestCrossTraining()

    suspend fun crossTraining(limit: Int = 50): List<Activity> = api().crossTraining(limit)

    suspend fun coachAction(action: String, detail: String? = null): CoachDecision =
        api().coachAction(CoachActionRequest(action = action, detail = detail))

    suspend fun notifications(): List<AppNotification> = api().notifications()

    suspend fun ackNotifications(ids: List<Int>): Int =
        runCatching { api().ackNotifications(NotificationAck(ids))["acked"] ?: 0 }.getOrDefault(0)

    // ── Push device registration (Roadmap A3) ────────────────────────────────

    suspend fun registerDevice(fcmToken: String, platform: String = "android") {
        runCatching { api().registerDevice(DeviceIn(fcmToken, platform)) }
    }

    suspend fun unregisterDevice(fcmToken: String) {
        runCatching { api().unregisterDevice(fcmToken) }
    }

    suspend fun coachEvents(days: Int = 30): List<CoachEvent> = api().coachEvents(days)

    suspend fun analyze(activityId: Int? = null): Report = api().analyze(activityId)

    suspend fun planWeekly(): Report = api().planWeekly()

    suspend fun getProfile(): AthleteProfile = api().getProfile()

    suspend fun putProfile(profile: AthleteProfile): AthleteProfile = api().putProfile(profile)

    suspend fun postCheckin(checkin: DailyCheckin): DailyCheckin = api().postCheckin(checkin)

    /** Send a post-run voice/text debrief (Roadmap A4). */
    suspend fun postDebrief(text: String, activityId: Int? = null): DebriefResult =
        api().postDebrief(DebriefIn(text = text, activityId = activityId))

    suspend fun patchActivity(id: Int, rpe: Int? = null, notes: String? = null): Activity =
        api().patchActivity(id, ActivityPatch(rpe = rpe, notes = notes))

    suspend fun stats(period: String = "all-time"): PeriodStats = api().getStats(period)

    suspend fun stravaStatus(): StravaStatus = api().stravaStatus()

    suspend fun chatForPlan(messages: List<PlanChatMessage>): PlanChatResponse =
        api().chatForPlan(PlanChatRequest(messages))

    suspend fun generatePlan(request: PlanGenerateRequest): TrainingPlan =
        api().generatePlan(request)

    suspend fun getCurrentPlan(): TrainingPlan? = runCatching { api().getCurrentPlan() }
        .getOrNull()

    suspend fun toggleSessionComplete(sessionId: Int): PlanSession =
        api().toggleSessionComplete(sessionId)

    suspend fun movePlanSession(sessionId: Int, targetDate: String): PlanMoveResult =
        api().movePlanSession(sessionId, PlanSessionMoveRequest(targetDate))

    suspend fun archivePlan(planId: Int) {
        api().archivePlan(planId)
    }

    suspend fun createWorkout(workout: WorkoutTemplate): WorkoutTemplate =
        api().createWorkout(workout)

    suspend fun listWorkouts(): List<WorkoutTemplate> = api().listWorkouts()

    suspend fun deleteWorkout(id: Int) {
        api().deleteWorkout(id)
    }

    suspend fun suggestWorkout(
        sessionType: String,
        goalType: String? = null,
        goalTime: String? = null,
        notes: String? = null,
    ): WorkoutTemplate = api().suggestWorkout(
        WorkoutSuggestRequest(
            sessionType = sessionType,
            goalType = goalType,
            goalTime = goalTime,
            notes = notes,
        )
    )

    suspend fun sendChatMessage(message: String, sessionId: Int? = null): ChatSendResponse =
        api().sendChatMessage(ChatSendRequest(sessionId = sessionId, message = message))

    suspend fun getChatSessions(): List<ChatSession> = api().getChatSessions()

    suspend fun getChatMessages(sessionId: Int): List<ChatMessage> =
        api().getChatMessages(sessionId)

    suspend fun deleteChatSession(sessionId: Int) {
        api().deleteChatSession(sessionId)
    }

    suspend fun getHeatmap(): HeatmapResponse = api().getHeatmap()

    suspend fun getVo2maxHistory(): Vo2maxHistory = api().getVo2maxHistory()

    // ── Onboarding (Roadmap #4) ───────────────────────────────────────────────

    suspend fun getOnboarding(): OnboardingStatus = api().getOnboarding()

    // ── Shoe tracking (Roadmap #6) ───────────────────────────────────────────────

    suspend fun getShoes(includeRetired: Boolean = true): List<Shoe> =
        api().getShoes(includeRetired)

    suspend fun createShoe(shoe: ShoeIn): Shoe = api().createShoe(shoe)

    suspend fun updateShoe(id: Int, shoe: ShoeIn): Shoe = api().updateShoe(id, shoe)

    suspend fun deleteShoe(id: Int) {
        api().deleteShoe(id)
    }

    suspend fun assignShoe(activityId: Int, shoeId: Int?): Activity =
        api().assignShoe(activityId, mapOf("shoe_id" to shoeId))
}
