package com.runningcoach.app

import android.app.Application
import com.runningcoach.app.data.repository.CoachRepository
import com.runningcoach.app.data.settings.SettingsStore
import com.runningcoach.app.notify.CoachNotifications
import com.runningcoach.app.notify.NotificationSyncWorker

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
    }
}
