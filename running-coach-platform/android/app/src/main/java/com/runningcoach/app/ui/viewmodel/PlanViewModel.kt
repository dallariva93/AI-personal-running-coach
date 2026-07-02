package com.runningcoach.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.runningcoach.app.data.model.PlanChatMessage
import com.runningcoach.app.data.model.PlanGenerateRequest
import com.runningcoach.app.data.model.TrainingPlan
import com.runningcoach.app.data.repository.CoachRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

private const val WELCOME_MESSAGE =
    "Ciao! Prima di creare il tuo piano, dimmi qualcosa sul tuo allenamento attuale. " +
    "Quanti km corri in media a settimana?"

data class PlanUiState(
    val loading: Boolean = false,
    val plan: TrainingPlan? = null,
    val error: String? = null,
    val successMessage: String? = null,
    val showGenerateDialog: Boolean = false,
    // Chat state
    val chatMessages: List<PlanChatMessage> = listOf(
        PlanChatMessage(role = "assistant", content = WELCOME_MESSAGE)
    ),
    val chatLoading: Boolean = false,
    val chatComplete: Boolean = false,
    val runnerContext: String? = null,
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

    fun sendChatMessage(text: String) {
        val trimmed = text.trim().takeIf { it.isNotEmpty() } ?: return
        val userMsg = PlanChatMessage(role = "user", content = trimmed)
        val updatedMessages = _state.value.chatMessages + userMsg
        _state.update { it.copy(chatMessages = updatedMessages, chatLoading = true, error = null) }

        viewModelScope.launch {
            runCatching {
                repository.chatForPlan(updatedMessages)
            }.onSuccess { response ->
                val assistantMsg = PlanChatMessage(role = "assistant", content = response.message)
                _state.update {
                    it.copy(
                        chatMessages = updatedMessages + assistantMsg,
                        chatLoading = false,
                        chatComplete = response.isComplete,
                        runnerContext = response.runnerContext,
                    )
                }
            }.onFailure { e ->
                _state.update { it.copy(chatLoading = false, error = friendly(e)) }
            }
        }
    }

    fun resetChat() {
        _state.update {
            it.copy(
                chatMessages = listOf(PlanChatMessage(role = "assistant", content = WELCOME_MESSAGE)),
                chatLoading = false,
                chatComplete = false,
                runnerContext = null,
            )
        }
    }

    fun generatePlan(request: PlanGenerateRequest) {
        val context = _state.value.runnerContext
        val requestWithContext = request.copy(runnerContext = context)
        viewModelScope.launch {
            _state.update {
                it.copy(
                    loading = true,
                    error = null,
                    successMessage = null,
                    showGenerateDialog = false,
                )
            }
            runCatching { repository.generatePlan(requestWithContext) }
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
                    _state.update { it.copy(plan = current, error = friendly(e)) }
                }
        }
    }

    /** Move a plan session to another day (calendar editor, Roadmap #12). */
    fun moveSession(sessionId: Int, targetDate: String) {
        viewModelScope.launch {
            runCatching { repository.movePlanSession(sessionId, targetDate) }
                .onSuccess { result ->
                    val msg = if (result.warnings.isEmpty()) {
                        "Seduta spostata."
                    } else {
                        "Spostata — ⚠ " + result.warnings.joinToString(" ")
                    }
                    _state.update {
                        it.copy(plan = result.plan, successMessage = msg, error = null)
                    }
                }
                .onFailure { e ->
                    // Surface the backend's Italian reason for invalid moves
                    // (race day, completed session, past date…) instead of a
                    // generic HTTP error.
                    val detail = (e as? retrofit2.HttpException)
                        ?.response()?.errorBody()?.string()
                        ?.let { body ->
                            Regex("\"detail\"\\s*:\\s*\"([^\"]+)\"")
                                .find(body)?.groupValues?.get(1)
                        }
                    _state.update { it.copy(error = detail ?: friendly(e)) }
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

    fun dismissDialog() {
        _state.update { it.copy(showGenerateDialog = false) }
        resetChat()
    }

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
