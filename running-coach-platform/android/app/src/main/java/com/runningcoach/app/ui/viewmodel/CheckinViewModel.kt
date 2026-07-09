package com.runningcoach.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.runningcoach.app.data.model.DailyCheckin
import com.runningcoach.app.data.repository.CoachRepository
import java.time.LocalDate
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class CheckinUiState(
    val sleepH: Double = 7.0,
    val fatigue: Int = 5,
    val soreness: Int = 1,
    val motivation: Int = 7,
    val submitting: Boolean = false,
    val submitted: Boolean = false,
    val error: String? = null,
)

/** Daily readiness check-in (handoff 1f): sleep/fatigue/soreness/motivation. */
class CheckinViewModel(private val repository: CoachRepository) : ViewModel() {

    private val _state = MutableStateFlow(CheckinUiState())
    val state: StateFlow<CheckinUiState> = _state.asStateFlow()

    fun setSleepH(v: Double) = _state.update { it.copy(sleepH = v) }
    fun setFatigue(v: Int) = _state.update { it.copy(fatigue = v) }
    fun setSoreness(v: Int) = _state.update { it.copy(soreness = v) }
    fun setMotivation(v: Int) = _state.update { it.copy(motivation = v) }

    fun submit() {
        val s = _state.value
        viewModelScope.launch {
            _state.update { it.copy(submitting = true, error = null) }
            runCatching {
                repository.postCheckin(
                    DailyCheckin(
                        date = LocalDate.now().toString(),
                        sleepH = s.sleepH,
                        fatigue = s.fatigue,
                        soreness = s.soreness,
                        motivation = s.motivation,
                        source = "manual",
                    ),
                )
            }.onSuccess {
                _state.update { it.copy(submitting = false, submitted = true) }
            }.onFailure { e ->
                _state.update {
                    it.copy(submitting = false, error = e.message ?: "Invio check-in fallito.")
                }
            }
        }
    }
}
