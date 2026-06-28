package com.runningcoach.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.runningcoach.app.data.model.PlanGenerateRequest
import com.runningcoach.app.data.model.TrainingPlan
import com.runningcoach.app.data.repository.CoachRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PlanUiState(
    val loading: Boolean = false,
    val plan: TrainingPlan? = null,
    val error: String? = null,
    val successMessage: String? = null,
    val showGenerateDialog: Boolean = false,
)

class PlanViewModel(private val repository: CoachRepository) : ViewModel() {

    private val _state = MutableStateFlow(PlanUiState(loading = true))
    val state: StateFlow<PlanUiState> = _state.asStateFlow()

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _state.update { it.copy(loading = it.plan == null, error = null) }
            runCatching { repository.getCurrentPlan() }
                .onSuccess { plan -> _state.update { it.copy(loading = false, plan = plan) } }
                .onFailure { e -> _state.update { it.copy(loading = false, error = friendly(e)) } }
        }
    }

    fun generatePlan(request: PlanGenerateRequest) {
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null, successMessage = null, showGenerateDialog = false) }
            runCatching { repository.generatePlan(request) }
                .onSuccess { plan ->
                    _state.update {
                        it.copy(loading = false, plan = plan, successMessage = "Piano generato!")
                    }
                }
                .onFailure { e ->
                    _state.update { it.copy(loading = false, error = friendly(e)) }
                }
        }
    }

    fun toggleSession(sessionId: Int) {
        viewModelScope.launch {
            // Optimistic update: flip the completed flag locally first.
            val current = _state.value.plan
            val optimistic = current?.let { plan ->
                plan.copy(
                    weeks = plan.weeks.map { week ->
                        week.copy(
                            sessions = week.sessions.map { s ->
                                if (s.id == sessionId) s.copy(completed = !s.completed) else s
                            },
                        )
                    },
                )
            }
            if (optimistic != null) _state.update { it.copy(plan = optimistic) }

            runCatching { repository.toggleSessionComplete(sessionId) }
                .onSuccess { updated ->
                    // Patch the single session with the server's response.
                    _state.update { st ->
                        val patched = st.plan?.copy(
                            weeks = st.plan.weeks.map { week ->
                                week.copy(
                                    sessions = week.sessions.map { s ->
                                        if (s.id == sessionId) updated else s
                                    },
                                )
                            },
                        )
                        st.copy(plan = patched)
                    }
                }
                .onFailure { e ->
                    // Rollback optimistic update on failure.
                    _state.update { it.copy(plan = current, error = friendly(e)) }
                }
        }
    }

    fun archivePlan(planId: Int) {
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            runCatching { repository.archivePlan(planId) }
                .onSuccess {
                    _state.update {
                        it.copy(loading = false, plan = null, successMessage = "Piano archiviato.")
                    }
                }
                .onFailure { e ->
                    _state.update { it.copy(loading = false, error = friendly(e)) }
                }
        }
    }

    fun showGenerateDialog() = _state.update { it.copy(showGenerateDialog = true) }

    fun dismissDialog() = _state.update { it.copy(showGenerateDialog = false) }

    fun clearMessage() = _state.update { it.copy(successMessage = null, error = null) }

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
