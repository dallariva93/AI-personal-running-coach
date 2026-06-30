package com.runningcoach.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.runningcoach.app.data.model.AthleteProfile
import com.runningcoach.app.data.model.Goal
import com.runningcoach.app.data.model.Overview
import com.runningcoach.app.data.repository.CoachRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class OverviewUiState(
    val loading: Boolean = false,
    val working: Boolean = false, // a sync/analyze/plan action in progress
    val overview: Overview? = null,
    val error: String? = null,
    val message: String? = null,
)

class OverviewViewModel(private val repository: CoachRepository) : ViewModel() {

    private val _state = MutableStateFlow(OverviewUiState(loading = true))
    val state: StateFlow<OverviewUiState> = _state.asStateFlow()

    init {
        refresh()
        ingestWellness()
    }

    fun refresh() {
        viewModelScope.launch {
            _state.update { it.copy(loading = it.overview == null, error = null) }
            runCatching { repository.overview() }
                .onSuccess { ov -> _state.update { it.copy(loading = false, overview = ov) } }
                .onFailure { e -> _state.update { it.copy(loading = false, error = friendly(e)) } }
        }
    }

    fun sync() = action("Sincronizzazione completata") { repository.sync() }

    fun analyze() = action("Analisi generata") { repository.analyze() }

    fun planWeekly() = action("Piano settimanale generato") { repository.planWeekly() }

    /** Save the athlete's goal + calibration (level / risk tolerance). */
    fun saveCoach(
        goalType: String,
        targetDate: String,
        targetTime: String,
        level: String,
        risk: String,
    ) = action("Profilo aggiornato") {
        val current = state.value.overview?.profile
        val goal = if (goalType.isNotBlank() || targetDate.isNotBlank()) {
            Goal(
                goalType = goalType.ifBlank { "general" },
                targetDate = targetDate.ifBlank { null },
                targetTime = targetTime.ifBlank { null },
            )
        } else {
            null
        }
        val profile = (current ?: AthleteProfile()).copy(
            level = level.ifBlank { "intermediate" },
            riskTolerance = risk.ifBlank { "moderate" },
            goal = goal,
        )
        repository.putProfile(profile)
    }

    /** Patch RPE and/or notes on a stored activity, then refresh the overview. */
    fun updateActivity(id: Int, rpe: Int? = null, notes: String? = null) =
        action("Attività aggiornata") { repository.patchActivity(id, rpe = rpe, notes = notes) }

    /** Silently fetch Garmin wellness data for missing days (fire-and-forget). */
    fun ingestWellness() {
        viewModelScope.launch {
            runCatching { repository.ingestWellness() }
                .onSuccess { count ->
                    if (count > 0) {
                        runCatching { repository.overview() }.getOrNull()?.let { ov ->
                            _state.update { it.copy(overview = ov) }
                        }
                    }
                }
        }
    }

    private fun action(successMsg: String, block: suspend () -> Any?) {
        viewModelScope.launch {
            _state.update { it.copy(working = true, error = null, message = null) }
            runCatching { block() }
                .onSuccess {
                    val ov = runCatching { repository.overview() }.getOrNull()
                    _state.update {
                        it.copy(working = false, overview = ov ?: it.overview, message = successMsg)
                    }
                }
                .onFailure { e -> _state.update { it.copy(working = false, error = friendly(e)) } }
        }
    }

    fun clearMessage() = _state.update { it.copy(message = null, error = null) }

    private fun friendly(e: Throwable): String = when (e) {
        is retrofit2.HttpException ->
            if (e.code() == 401) "Non autorizzato: controlla il token nelle impostazioni."
            else "Errore dal server (${e.code()})."
        is java.net.ConnectException, is java.net.UnknownHostException,
        is java.net.SocketTimeoutException ->
            "Backend non raggiungibile. Verifica l'URL nelle impostazioni."
        else -> e.message ?: "Errore sconosciuto."
    }
}
