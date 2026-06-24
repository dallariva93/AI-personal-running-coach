package com.runningcoach.app.data.remote

import com.runningcoach.app.data.model.Activity
import com.runningcoach.app.data.model.Overview
import com.runningcoach.app.data.model.Report
import retrofit2.http.GET
import retrofit2.http.POST
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

    @POST("api/analyze")
    suspend fun analyze(@Query("activity_id") activityId: Int? = null): Report

    @POST("api/plan/weekly")
    suspend fun planWeekly(): Report
}
