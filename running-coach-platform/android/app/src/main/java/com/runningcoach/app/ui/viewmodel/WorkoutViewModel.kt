package com.runningcoach.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.runningcoach.app.data.model.WorkoutSegment
import com.runningcoach.app.data.model.WorkoutTemplate
import com.runningcoach.app.data.repository.CoachRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class WorkoutUiState(
    val loading: Boolean = false,
    val library: List<WorkoutTemplate> = emptyList(),
    val currentBuilder: List<WorkoutSegment> = emptyList(),
    val currentName: String = "",
    val currentType: String = "custom",
    val suggesting: Boolean = false,
    val error: String? = null,
    val successMessage: String? = null,
)

class WorkoutViewModel(private val repository: CoachRepository) : ViewModel() {

    private val _state = MutableStateFlow(WorkoutUiState(loading = true))
    val state: StateFlow<WorkoutUiState> = _state.asStateFlow()

    init {
        loadLibrary()
    }

    fun loadLibrary() {
        viewModelScope.launch {
            _state.update { it.copy(loading = true, error = null) }
            runCatching { repository.listWorkouts() }
                .onSuccess { list ->
                    _state.update { it.copy(loading = false, library = list) }
                }
                .onFailure { err ->
                    _state.update { it.copy(loading = false, error = err.message) }
                }
        }
    }

    fun setName(name: String) {
        _state.update { it.copy(currentName = name) }
    }

    fun setType(type: String) {
        _state.update { it.copy(currentType = type) }
    }

    fun addSegment(segment: WorkoutSegment) {
        _state.update { state ->
            val newSegments = state.currentBuilder + segment.copy(
                position = state.currentBuilder.size
            )
            state.copy(currentBuilder = newSegments)
        }
    }

    fun removeSegment(position: Int) {
        _state.update { state ->
            val updated = state.currentBuilder
                .filterIndexed { i, _ -> i != position }
                .mapIndexed { i, s -> s.copy(position = i) }
            state.copy(currentBuilder = updated)
        }
    }

    fun moveSegmentUp(position: Int) {
        if (position <= 0) return
        _state.update { state ->
            val list = state.currentBuilder.toMutableList()
            val tmp = list[position]
            list[position] = list[position - 1]
            list[position - 1] = tmp
            val reindexed = list.mapIndexed { i, s -> s.copy(position = i) }
            state.copy(currentBuilder = reindexed)
        }
    }

    fun moveSegmentDown(position: Int) {
        _state.update { state ->
            if (position >= state.currentBuilder.size - 1) return@update state
            val list = state.currentBuilder.toMutableList()
            val tmp = list[position]
            list[position] = list[position + 1]
            list[position + 1] = tmp
            val reindexed = list.mapIndexed { i, s -> s.copy(position = i) }
            state.copy(currentBuilder = reindexed)
        }
    }

    fun updateSegment(position: Int, segment: WorkoutSegment) {
        _state.update { state ->
            val updated = state.currentBuilder.toMutableList()
            if (position in updated.indices) {
                updated[position] = segment.copy(position = position)
            }
            state.copy(currentBuilder = updated.toList())
        }
    }

    fun clearBuilder() {
        _state.update { it.copy(currentBuilder = emptyList(), currentName = "", currentType = "custom") }
    }

    fun saveWorkout() {
        val state = _state.value
        if (state.currentName.isBlank() || state.currentBuilder.isEmpty()) {
            _state.update { it.copy(error = "Inserisci nome e almeno un segmento.") }
            return
        }
        val template = WorkoutTemplate(
            name = state.currentName.trim(),
            type = state.currentType,
            segments = state.currentBuilder,
        )
        viewModelScope.launch {
            _state.update { it.copy(loading = true) }
            runCatching { repository.createWorkout(template) }
                .onSuccess {
                    loadLibrary()
                    _state.update { it.copy(loading = false, successMessage = "Allenamento salvato!", currentBuilder = emptyList(), currentName = "", currentType = "custom") }
                }
                .onFailure { err ->
                    _state.update { it.copy(loading = false, error = err.message) }
                }
        }
    }

    fun suggestWorkout(
        sessionType: String,
        goalType: String?,
        goalTime: String?,
        notes: String?,
    ) {
        viewModelScope.launch {
            _state.update { it.copy(suggesting = true, error = null) }
            runCatching {
                repository.suggestWorkout(sessionType, goalType, goalTime, notes)
            }
                .onSuccess { template ->
                    val newLibrary = listOf(template) + _state.value.library
                    _state.update {
                        it.copy(
                            suggesting = false,
                            library = newLibrary,
                            currentBuilder = template.segments,
                            currentName = template.name,
                            currentType = template.type,
                            successMessage = "Allenamento generato dall'AI!",
                        )
                    }
                    loadLibrary()
                }
                .onFailure { err ->
                    _state.update { it.copy(suggesting = false, error = err.message) }
                }
        }
    }

    fun deleteWorkout(id: Int) {
        viewModelScope.launch {
            runCatching { repository.deleteWorkout(id) }
                .onSuccess { loadLibrary() }
                .onFailure { err ->
                    _state.update { it.copy(error = err.message) }
                }
        }
    }

    fun loadIntoBuilder(template: WorkoutTemplate) {
        _state.update {
            it.copy(
                currentBuilder = template.segments,
                currentName = template.name,
                currentType = template.type,
            )
        }
    }

    fun clearMessage() {
        _state.update { it.copy(error = null, successMessage = null) }
    }
}
