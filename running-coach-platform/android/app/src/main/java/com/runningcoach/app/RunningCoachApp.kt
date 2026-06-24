package com.runningcoach.app

import android.app.Application
import com.runningcoach.app.data.repository.CoachRepository
import com.runningcoach.app.data.settings.SettingsStore

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
    }
}
