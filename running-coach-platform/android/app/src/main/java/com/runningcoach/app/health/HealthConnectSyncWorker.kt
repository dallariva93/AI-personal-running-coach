package com.runningcoach.app.health

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.runningcoach.app.RunningCoachApp
import java.time.Instant
import java.time.temporal.ChronoUnit

/**
 * Reads new running sessions + wellness from Health Connect (Roadmap A2) since
 * the last successful read and POSTs them to the backend. No-op when Health
 * Connect is unavailable or consent hasn't been granted, so a device without HC
 * (or a user who declined) is never disturbed.
 */
class HealthConnectSyncWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val app = applicationContext as? RunningCoachApp ?: return Result.success()
        val manager = HealthConnectManager(applicationContext)
        if (!manager.isAvailable() || !manager.hasAllPermissions()) {
            return Result.success()  // nothing to do without HC + consent
        }
        return try {
            // First run: look back 30 days; afterwards only since the last read.
            val since = app.settingsStore.healthConnectSyncedAt()
                ?.let { Instant.ofEpochMilli(it) }
                ?: Instant.now().minus(30, ChronoUnit.DAYS)
            val payload = manager.readSince(since)
            if (payload.runs.isNotEmpty() || payload.wellness.isNotEmpty()) {
                app.repository.importHealthConnect(payload)
            }
            app.settingsStore.recordHealthConnectSync(System.currentTimeMillis())
            Result.success()
        } catch (_: Exception) {
            Result.retry()  // offline / backend unreachable — try again next cycle
        }
    }

    companion object {
        private const val WORK_NAME = "health-connect-sync"

        /** Kick a one-shot Health Connect import (e.g. after granting consent). */
        fun syncNow(context: Context) {
            val request = OneTimeWorkRequestBuilder<HealthConnectSyncWorker>().build()
            WorkManager.getInstance(context).enqueueUniqueWork(
                WORK_NAME,
                ExistingWorkPolicy.KEEP,
                request,
            )
        }
    }
}
