package com.runningcoach.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.runningcoach.app.data.model.PeriodStats
import com.runningcoach.app.data.model.Vo2maxHistory
import com.runningcoach.app.data.repository.CoachRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class StatsUiState(
    val loading: Boolean = false,
    val period: String = "all-time",
    val stats: PeriodStats? = null,
    val vo2maxHistory: Vo2maxHistory? = null,
    val error: String? = null,
)

class StatsViewModel(private val repository: CoachRepository) : ViewModel() {

    private val _state = MutableStateFlow(StatsUiState(loading = true))
    val state: StateFlow<StatsUiState> = _state.asStateFlow()

    init {
        load("all-time")
        loadVo2maxHistory()
    }

    fun load(period: String) {
        viewModelScope.launch {
            _state.update { it.copy(loading = true, period = period, error = null) }
            runCatching { repository.stats(period) }
                .onSuccess { s -> _state.update { it.copy(loading = false, stats = s) } }
                .onFailure { e -> _state.update { it.copy(loading = false, error = e.message) } }
        }
    }

    private fun loadVo2maxHistory() {
        viewModelScope.launch {
            runCatching { repository.getVo2maxHistory() }
                .onSuccess { h -> _state.update { it.copy(vo2maxHistory = h) } }
        }
    }
}
