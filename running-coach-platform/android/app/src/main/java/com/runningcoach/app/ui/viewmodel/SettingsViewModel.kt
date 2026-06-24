package com.runningcoach.app.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.runningcoach.app.data.settings.AppSettings
import com.runningcoach.app.data.settings.SettingsStore
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class SettingsViewModel(private val store: SettingsStore) : ViewModel() {

    val settings: StateFlow<AppSettings?> =
        store.settings.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    fun save(baseUrl: String, token: String, onSaved: () -> Unit = {}) {
        viewModelScope.launch {
            store.update(baseUrl, token)
            onSaved()
        }
    }
}
