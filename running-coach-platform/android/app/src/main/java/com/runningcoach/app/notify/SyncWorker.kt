package com.runningcoach.app.notify

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.runningcoach.app.RunningCoachApp
import java.util.concurrent.TimeUnit

/**
 * Background Garmin sync so the athlete never has to tap "Sincronizza"
 * (Roadmap Q2: death of the sync/analyze buttons). Runs periodically and
 * once, expedited, whenever the app comes to the foreground; the backend's
 * own 10-minute recency guard keeps the two from duplicating work.
 */
class SyncWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val app = applicationContext as? RunningCoachApp ?: return Result.success()
        return try {
            val synced = app.repository.sync()
            val maxId = synced.maxOfOrNull { it.id } ?: 0
            val previousMaxId = app.settingsStore.swapMaxActivityId(maxId)
            val newActivities = synced.count { it.id > previousMaxId }
            app.settingsStore.recordSync(System.currentTimeMillis(), newActivities)
            Result.success()
        } catch (_: Exception) {
            // Offline / backend unreachable / Garmin rate-limited — try again next cycle.
            Result.retry()
        }
    }

    companion object {
        private const val PERIODIC_NAME = "activity-sync-periodic"
        private const val EXPEDITED_NAME = "activity-sync-app-open"

        /** Recurring background sync (idempotent, ~1h cadence). */
        fun schedulePeriodic(context: Context) {
            val request = PeriodicWorkRequestBuilder<SyncWorker>(1, TimeUnit.HOURS).build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                PERIODIC_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }

        /**
         * One-shot expedited sync for app open (onCreate/onResume). ``KEEP``
         * collapses onCreate+onResume firing close together into one run; the
         * backend recency guard caps this at effectively 1x/10min regardless.
         */
        fun syncNowExpedited(context: Context) {
            val request = OneTimeWorkRequestBuilder<SyncWorker>()
                .setExpedited(androidx.work.OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(
                EXPEDITED_NAME,
                ExistingWorkPolicy.KEEP,
                request,
            )
        }
    }
}
