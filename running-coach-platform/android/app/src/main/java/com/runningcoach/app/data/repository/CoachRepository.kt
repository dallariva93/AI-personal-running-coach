package com.runningcoach.app.data.repository

import com.runningcoach.app.data.model.Activity
import com.runningcoach.app.data.model.AthleteProfile
import com.runningcoach.app.data.model.DailyCheckin
import com.runningcoach.app.data.model.Overview
import com.runningcoach.app.data.model.PeriodStats
import com.runningcoach.app.data.model.Report
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

    suspend fun analyze(activityId: Int? = null): Report = api().analyze(activityId)

    suspend fun planWeekly(): Report = api().planWeekly()

    suspend fun getProfile(): AthleteProfile = api().getProfile()

    suspend fun putProfile(profile: AthleteProfile): AthleteProfile = api().putProfile(profile)

    suspend fun postCheckin(checkin: DailyCheckin): DailyCheckin = api().postCheckin(checkin)

    suspend fun stats(period: String = "all-time"): PeriodStats = api().getStats(period)
}
