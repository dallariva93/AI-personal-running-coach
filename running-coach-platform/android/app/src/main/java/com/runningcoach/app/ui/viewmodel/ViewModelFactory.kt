package com.runningcoach.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.runningcoach.app.RunningCoachApp

/** Manual ViewModel factory wiring in the app-scoped repository/settings. */
class ViewModelFactory(private val app: RunningCoachApp) : ViewModelProvider.Factory {

    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T = when {
        modelClass.isAssignableFrom(OverviewViewModel::class.java) ->
            OverviewViewModel(app.repository) as T
        modelClass.isAssignableFrom(SettingsViewModel::class.java) ->
            SettingsViewModel(app.settingsStore, app.repository) as T
        modelClass.isAssignableFrom(StatsViewModel::class.java) ->
            StatsViewModel(app.repository) as T
        modelClass.isAssignableFrom(PlanViewModel::class.java) ->
            PlanViewModel(app.repository) as T
        else -> throw IllegalArgumentException("Unknown ViewModel: ${modelClass.name}")
    }
}
