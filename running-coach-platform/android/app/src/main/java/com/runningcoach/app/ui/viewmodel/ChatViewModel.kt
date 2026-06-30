package com.runningcoach.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.runningcoach.app.data.repository.CoachRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** One renderable message in the chat UI. */
data class ChatDisplayMessage(
    val role: String,       // "user" | "assistant"
    val content: String,
    val tier: String? = null,   // "simple" | "medium" | "complex" — only on AI messages
    val modelUsed: String? = null,
)

data class ChatUiState(
    val sessionId: Int? = null,
    val sessionTitle: String = "Coach AI",
    val messages: List<ChatDisplayMessage> = emptyList(),
    val loading: Boolean = false,
    val error: String? = null,
)

class ChatViewModel(private val repo: CoachRepository) : ViewModel() {

    private val _state = MutableStateFlow(ChatUiState())
    val state: StateFlow<ChatUiState> = _state.asStateFlow()

    fun sendMessage(text: String) {
        val trimmed = text.trim()
        if (trimmed.isBlank() || _state.value.loading) return

        // Optimistically append the user bubble.
        _state.update {
            it.copy(
                messages = it.messages + ChatDisplayMessage(role = "user", content = trimmed),
                loading = true,
                error = null,
            )
        }

        viewModelScope.launch {
            runCatching {
                repo.sendChatMessage(
                    message = trimmed,
                    sessionId = _state.value.sessionId,
                )
            }.onSuccess { resp ->
                _state.update {
                    it.copy(
                        sessionId = resp.sessionId,
                        sessionTitle = resp.sessionTitle,
                        messages = it.messages + ChatDisplayMessage(
                            role = "assistant",
                            content = resp.reply,
                            tier = resp.tier,
                            modelUsed = resp.modelUsed,
                        ),
                        loading = false,
                    )
                }
            }.onFailure { err ->
                _state.update {
                    it.copy(
                        loading = false,
                        error = "Errore: ${err.localizedMessage ?: "riprova"}",
                    )
                }
            }
        }
    }

    fun newSession() {
        _state.value = ChatUiState()
    }

    fun clearError() {
        _state.update { it.copy(error = null) }
    }
}
