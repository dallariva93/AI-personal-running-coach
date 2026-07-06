package com.runningcoach.app

import android.app.Application
import com.runningcoach.app.data.repository.CoachRepository
import com.runningcoach.app.data.settings.SettingsStore
import com.runningcoach.app.notify.CoachFirebaseService
import com.runningcoach.app.notify.CoachNotifications
import com.runningcoach.app.notify.NotificationSyncWorker
import com.runningcoach.app.notify.SyncWorker

/** Application entry point + tiny manual dependency container. */
class RunningCoachApp : Application() {

    lateinit var settingsStore: SettingsStore
        private set

    lateinit var repository: CoachRepository
        private set

    override fun onCreate() {
        super.onCreate()
        settingsStore = SettingsStore(this)
        repository = CoachRepository(settingsStore)
        // Coach notifications (Roadmap #6): channel + recurring background check.
        CoachNotifications.ensureChannel(this)
        NotificationSyncWorker.schedule(this)
        // Background Garmin sync (Roadmap Q2): periodic + an expedited run now.
        SyncWorker.schedulePeriodic(this)
        SyncWorker.syncNowExpedited(this)
        // Live-run upload queue (G1): if a finished recording is still waiting
        // (crash, reboot, long offline stretch), resume its upload now. No-op
        // with an empty queue.
        com.runningcoach.app.tracking.LiveUploadQueue.kick(this)
        // FCM token registration (Roadmap A3): best-effort upload on boot.
        // Inert when Firebase is not configured (no google-services.json).
        runCatching {
            com.google.firebase.messaging.FirebaseMessaging.getInstance().token
                .addOnCompleteListener { task ->
                    if (task.isSuccessful) {
                        CoachFirebaseService.uploadToken(this, task.result)
                    }
                }
        }
    }
}
