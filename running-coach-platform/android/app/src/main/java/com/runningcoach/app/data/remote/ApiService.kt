package com.runningcoach.app.data.remote

import com.runningcoach.app.data.model.Activity
import com.runningcoach.app.data.model.ActivityPatch
import com.runningcoach.app.data.model.AthleteProfile
import com.runningcoach.app.data.model.ChatMessage
import com.runningcoach.app.data.model.ChatSendRequest
import com.runningcoach.app.data.model.ChatSendResponse
import com.runningcoach.app.data.model.ChatSession
import com.runningcoach.app.data.model.DailyCheckin
import com.runningcoach.app.data.model.HeatmapResponse
import com.runningcoach.app.data.model.Vo2maxHistory
import com.runningcoach.app.data.model.Overview
import com.runningcoach.app.data.model.PeriodStats
import com.runningcoach.app.data.model.PlanChatRequest
import com.runningcoach.app.data.model.PlanChatResponse
import com.runningcoach.app.data.model.PlanGenerateRequest
import com.runningcoach.app.data.model.PlanSession
import com.runningcoach.app.data.model.Report
import com.runningcoach.app.data.model.StravaStatus
import com.runningcoach.app.data.model.TrainingPlan
import com.runningcoach.app.data.model.WorkoutSuggestRequest
import com.runningcoach.app.data.model.WorkoutTemplate
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

/** Typed bindings to the backend REST API. */
interface ApiService {

    @GET("api/mobile/overview")
    suspend fun overview(): Overview

    @GET("api/activities")
    suspend fun activities(@Query("limit") limit: Int = 50): List<Activity>

    @GET("api/reports")
    suspend fun reports(@Query("limit") limit: Int = 20): List<Report>

    @POST("api/ingest")
    suspend fun ingest(): List<Activity>

    @POST("api/ingest/wellness")
    suspend fun ingestWellness(): Map<String, Int>

    @POST("api/analyze")
    suspend fun analyze(@Query("activity_id") activityId: Int? = null): Report

    @POST("api/plan/weekly")
    suspend fun planWeekly(): Report

    @GET("api/profile")
    suspend fun getProfile(): AthleteProfile

    @PUT("api/profile")
    suspend fun putProfile(@Body profile: AthleteProfile): AthleteProfile

    @POST("api/checkin")
    suspend fun postCheckin(@Body checkin: DailyCheckin): DailyCheckin

    @PATCH("api/activities/{id}")
    suspend fun patchActivity(@Path("id") id: Int, @Body patch: ActivityPatch): Activity

    @GET("api/stats")
    suspend fun getStats(@Query("period") period: String = "all-time"): PeriodStats

    @GET("api/strava/status")
    suspend fun stravaStatus(): StravaStatus

    @POST("api/plan/chat")
    suspend fun chatForPlan(@Body request: PlanChatRequest): PlanChatResponse

    @POST("api/plan/generate")
    suspend fun generatePlan(@Body request: PlanGenerateRequest): TrainingPlan

    @GET("api/plan/current")
    suspend fun getCurrentPlan(): TrainingPlan

    @GET("api/plan/{id}")
    suspend fun getPlan(@Path("id") id: Int): TrainingPlan

    @PATCH("api/plan/sessions/{id}/complete")
    suspend fun toggleSessionComplete(@Path("id") id: Int): PlanSession

    @DELETE("api/plan/{id}")
    suspend fun archivePlan(@Path("id") id: Int): Map<String, Boolean>

    @POST("api/workouts")
    suspend fun createWorkout(@Body workout: WorkoutTemplate): WorkoutTemplate

    @GET("api/workouts")
    suspend fun listWorkouts(): List<WorkoutTemplate>

    @GET("api/workouts/{id}")
    suspend fun getWorkout(@Path("id") id: Int): WorkoutTemplate

    @DELETE("api/workouts/{id}")
    suspend fun deleteWorkout(@Path("id") id: Int): Map<String, Boolean>

    @POST("api/workouts/suggest")
    suspend fun suggestWorkout(@Body request: WorkoutSuggestRequest): WorkoutTemplate

    @POST("api/chat/send")
    suspend fun sendChatMessage(@Body request: ChatSendRequest): ChatSendResponse

    @GET("api/chat/sessions")
    suspend fun getChatSessions(): List<ChatSession>

    @GET("api/chat/{sessionId}/messages")
    suspend fun getChatMessages(@Path("sessionId") sessionId: Int): List<ChatMessage>

    @DELETE("api/chat/{sessionId}")
    suspend fun deleteChatSession(@Path("sessionId") sessionId: Int)

    @GET("api/activities/heatmap")
    suspend fun getHeatmap(): HeatmapResponse

    @GET("api/vo2max/history")
    suspend fun getVo2maxHistory(): Vo2maxHistory
}
