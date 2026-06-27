package com.runningcoach.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.runningcoach.app.data.model.Activity
import com.runningcoach.app.data.repository.CoachRepository
import com.runningcoach.app.data.settings.AppSettings
import com.runningcoach.app.data.settings.SettingsStore
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ExportState(
    val working: Boolean = false,
    val file: Pair<String, ByteArray>? = null,
    val error: String? = null,
)

class SettingsViewModel(
    private val store: SettingsStore,
    private val repository: CoachRepository,
) : ViewModel() {

    val settings: StateFlow<AppSettings?> =
        store.settings.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    private val _exportState = MutableStateFlow(ExportState())
    val exportState: StateFlow<ExportState> = _exportState.asStateFlow()

    fun save(baseUrl: String, token: String, onSaved: () -> Unit = {}) {
        viewModelScope.launch {
            store.update(baseUrl, token)
            onSaved()
        }
    }

    fun saveTheme(themeMode: String) {
        viewModelScope.launch { store.updateTheme(themeMode) }
    }

    fun exportData(format: String) {
        viewModelScope.launch {
            _exportState.update { it.copy(working = true, error = null, file = null) }
            runCatching { repository.activities(limit = 10_000) }
                .onSuccess { activities ->
                    val bytes = if (format == "json") buildJson(activities)
                    else buildCsv(activities)
                    _exportState.update {
                        it.copy(working = false, file = Pair("activities.$format", bytes))
                    }
                }
                .onFailure { e ->
                    _exportState.update { it.copy(working = false, error = e.message) }
                }
        }
    }

    fun clearExport() = _exportState.update { it.copy(file = null, error = null) }

    private fun buildCsv(activities: List<Activity>): ByteArray {
        val sb = StringBuilder()
        sb.appendLine(
            "date,activity_type,distance_km,duration_min,avg_pace,avg_hr," +
                "elevation_gain_m,avg_cadence,rpe,notes"
        )
        for (a in activities) {
            val notes = (a.notes ?: "").replace("\"", "\"\"")
            sb.appendLine(
                "${a.date},${a.activityType},${a.distanceKm},${a.durationMin}," +
                    "${a.avgPace ?: ""},${a.avgHr ?: ""},${a.elevationGainM ?: ""}," +
                    "${a.avgCadence ?: ""},${a.rpe ?: ""},\"$notes\""
            )
        }
        return sb.toString().toByteArray()
    }

    private fun buildJson(activities: List<Activity>): ByteArray {
        val sb = StringBuilder("[\n")
        activities.forEachIndexed { i, a ->
            if (i > 0) sb.append(",\n")
            sb.append(
                """  {"date":"${a.date}","activity_type":"${a.activityType}",""" +
                    """"distance_km":${a.distanceKm},"duration_min":${a.durationMin},""" +
                    """"avg_pace":${a.avgPace?.let { "\"$it\"" } ?: "null"},""" +
                    """"avg_hr":${a.avgHr ?: "null"},"notes":${a.notes?.let { "\"${it.replace("\"", "\\\"")}\"" } ?: "null"}}"""
            )
        }
        sb.append("\n]")
        return sb.toString().toByteArray()
    }
}
