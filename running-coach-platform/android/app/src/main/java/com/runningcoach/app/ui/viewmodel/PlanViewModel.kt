package com.runningcoach.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.runningcoach.app.data.model.PlanGenerateRequest
import com.runningcoach.app.data.model.TrainingPlan
import com.runningcoach.app.data.repository.CoachRepository
import java.time.LocalDate
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
    // (sessionId, sourceDateIso) of the last successful move, for the snackbar
    // "Annulla" action (Roadmap Q8) — a swap is its own inverse.
    val lastMove: Pair<Int, String>? = null,
    val showGenerateDialog: Boolean = false,
    // The §CTX§ JSON agreed in the unified plan-mode chat (A8), attached to
    // the next generate request. The interview itself lives in ChatViewModel.
    val runnerContext: String? = null,
)

class PlanViewModel(
    private val repository: CoachRepository,
    private val offlineCache: com.runningcoach.app.data.local.OfflineCache? = null,
) : ViewModel() {

    private val _state = MutableStateFlow(PlanUiState(loading = true))
    val state: StateFlow<PlanUiState> = _state.asStateFlow()

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            // Cached-first (G5): show the last known plan immediately.
            if (_state.value.plan == null) {
                offlineCache?.readPlan()?.let { cached ->
                    _state.update { it.copy(loading = false, plan = cached.value) }
                }
            }
            _state.update { it.copy(loading = it.plan == null, error = null) }
            runCatching { repository.getCurrentPlan() }
                .onSuccess { plan ->
                    offlineCache?.writePlan(plan)
                    _state.update { it.copy(loading = false, plan = plan) }
                }
                .onFailure { e ->
                    if (isNetworkError(e) && _state.value.plan != null) {
                        _state.update { it.copy(loading = false) }  // keep the cache
                    } else {
                        _state.update { it.copy(loading = false, error = friendly(e)) }
                    }
                }
        }
    }

    /** Store the §CTX§ agreed in the unified plan-mode chat (A8). */
    fun setRunnerContext(context: String?) {
        _state.update { it.copy(runnerContext = context) }
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
                        it.copy(
                            loading = false, plan = plan, successMessage = "Piano generato!",
                            lastMove = null,
                        )
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
                        st.copy(plan = patched, lastMove = null)
                    }
                }
                .onFailure { e ->
                    _state.update { it.copy(plan = current, error = friendly(e)) }
                }
        }
    }

    /** Move a plan session to another day (calendar editor, Roadmap #12). */
    fun moveSession(sessionId: Int, targetDate: String) {
        val sourceDate = _state.value.plan?.let { sourceDateOf(it, sessionId) }
        viewModelScope.launch {
            runCatching { repository.movePlanSession(sessionId, targetDate) }
                .onSuccess { result ->
                    val msg = if (result.warnings.isEmpty()) {
                        "Seduta spostata."
                    } else {
                        "Spostata — ⚠ " + result.warnings.joinToString(" ")
                    }
                    _state.update {
                        it.copy(
                            plan = result.plan, successMessage = msg, error = null,
                            // Q8: a swap is its own inverse — remembering where the
                            // session came from lets the snackbar offer "Annulla".
                            lastMove = sourceDate?.let { d -> sessionId to d },
                        )
                    }
                }
                .onFailure { e ->
                    if (isNetworkError(e) && offlineCache != null) {
                        // Offline (G5): queue the move and replay it later.
                        offlineCache.enqueuePlanMove(sessionId, targetDate)
                        _state.update {
                            it.copy(successMessage = "Sei offline: spostamento in coda, " +
                                "lo applico al ritorno della rete.", lastMove = null)
                        }
                        return@onFailure
                    }
                    // Surface the backend's Italian reason for invalid moves
                    // (race day, completed session, past date…) instead of a
                    // generic HTTP error.
                    val detail = (e as? retrofit2.HttpException)
                        ?.response()?.errorBody()?.string()
                        ?.let { body ->
                            Regex("\"detail\"\\s*:\\s*\"([^\"]+)\"")
                                .find(body)?.groupValues?.get(1)
                        }
                    _state.update { it.copy(error = detail ?: friendly(e), lastMove = null) }
                }
        }
    }

    private fun isNetworkError(e: Throwable): Boolean =
        e is java.net.ConnectException || e is java.net.UnknownHostException ||
            e is java.net.SocketTimeoutException || e is java.io.IOException

    /** The calendar date ``sessionId`` currently sits on, from its week/day-of-week. */
    private fun sourceDateOf(plan: TrainingPlan, sessionId: Int): String? {
        val start = runCatching { LocalDate.parse(plan.startDate) }.getOrNull() ?: return null
        for (week in plan.weeks) {
            val sess = week.sessions.find { it.id == sessionId } ?: continue
            return start.plusDays((week.weekNumber - 1) * 7L + sess.dayOfWeek).toString()
        }
        return null
    }

    fun archivePlan(planId: Int) {
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            runCatching { repository.archivePlan(planId) }
                .onSuccess {
                    _state.update {
                        it.copy(
                            loading = false, plan = null, successMessage = "Piano archiviato.",
                            lastMove = null,
                        )
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
    }

    fun clearMessage() =
        _state.update { it.copy(successMessage = null, error = null, lastMove = null) }

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
