package com.runningcoach.app.data.settings

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.runningcoach.app.BuildConfig
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "settings")

/** Persists connection settings and UI preferences. */
data class AppSettings(
    val baseUrl: String,
    val token: String,
    val themeMode: String = "system", // "system" | "dark" | "light"
)

class SettingsStore(private val context: Context) {

    private val baseUrlKey = stringPreferencesKey("base_url")
    private val tokenKey = stringPreferencesKey("token")
    private val themeModeKey = stringPreferencesKey("theme_mode")

    val settings: Flow<AppSettings> = context.dataStore.data.map { prefs ->
        AppSettings(
            baseUrl = prefs[baseUrlKey]?.takeIf { it.isNotBlank() } ?: BuildConfig.DEFAULT_BASE_URL,
            token = prefs[tokenKey].orEmpty(),
            themeMode = prefs[themeModeKey] ?: "system",
        )
    }

    suspend fun update(baseUrl: String, token: String) {
        context.dataStore.edit { prefs ->
            prefs[baseUrlKey] = normalizeUrl(baseUrl)
            prefs[tokenKey] = token.trim()
        }
    }

    suspend fun updateTheme(themeMode: String) {
        context.dataStore.edit { prefs -> prefs[themeModeKey] = themeMode }
    }

    private fun normalizeUrl(url: String): String {
        val trimmed = url.trim()
        if (trimmed.isEmpty()) return BuildConfig.DEFAULT_BASE_URL
        return if (trimmed.endsWith("/")) trimmed else "$trimmed/"
    }
}
