package com.runningcoach.app.notify

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.runningcoach.app.RunningCoachApp
import java.util.concurrent.TimeUnit

/**
 * Background delivery of coach notifications so they reach the athlete without
 * opening the app (Roadmap #6). Periodically pulls pending notifications, posts
 * them and acks them so they aren't shown twice.
 *
 * With FCM push (Roadmap A3) this is a fallback, not the primary channel, so
 * the interval is 6 hours — enough to catch anything FCM missed without
 * draining the battery.
 */
class NotificationSyncWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val app = applicationContext as? RunningCoachApp ?: return Result.success()
        val repo = app.repository
        return try {
            val pending = repo.notifications()
            if (pending.isNotEmpty()) {
                pending.forEach { CoachNotifications.post(applicationContext, it) }
                repo.ackNotifications(pending.map { it.id })
            }
            Result.success()
        } catch (_: Exception) {
            // Offline / backend unreachable — try again next cycle.
            Result.retry()
        }
    }

    companion object {
        private const val UNIQUE_NAME = "coach-notification-sync"

        /** Schedule the recurring background check (idempotent). */
        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<NotificationSyncWorker>(
                6, TimeUnit.HOURS,
            ).build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                UNIQUE_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }
    }
}
