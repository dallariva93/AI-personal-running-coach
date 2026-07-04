package com.runningcoach.app.data.settings

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.runningcoach.app.BuildConfig
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "settings")

/** Persists connection settings and UI preferences. */
data class AppSettings(
    val baseUrl: String,
    val token: String,
    val themeMode: String = "system", // "system" | "dark" | "light"
)

/** Passive status line data for the home screen (Roadmap Q2: no more sync buttons). */
data class SyncStatus(
    val lastSyncAtMillis: Long? = null,
    val newActivities: Int = 0,
)

class SettingsStore(private val context: Context) {

    private val baseUrlKey = stringPreferencesKey("base_url")
    private val tokenKey = stringPreferencesKey("token")
    private val themeModeKey = stringPreferencesKey("theme_mode")
    private val lastSyncAtKey = longPreferencesKey("last_sync_at_millis")
    private val lastSyncNewCountKey = intPreferencesKey("last_sync_new_count")
    private val lastMaxActivityIdKey = intPreferencesKey("last_max_activity_id")
    // Health Connect (A2): epoch-millis of the last successful HC read, so the
    // worker only fetches sessions newer than the previous sync.
    private val healthConnectSyncedAtKey = longPreferencesKey("hc_synced_at_millis")

    val settings: Flow<AppSettings> = context.dataStore.data.map { prefs ->
        AppSettings(
            baseUrl = prefs[baseUrlKey]?.takeIf { it.isNotBlank() } ?: BuildConfig.DEFAULT_BASE_URL,
            token = prefs[tokenKey].orEmpty(),
            themeMode = prefs[themeModeKey] ?: "system",
        )
    }

    val syncStatus: Flow<SyncStatus> = context.dataStore.data.map { prefs ->
        SyncStatus(
            lastSyncAtMillis = prefs[lastSyncAtKey],
            newActivities = prefs[lastSyncNewCountKey] ?: 0,
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

    /** Record the outcome of a background/foreground sync for the passive status line. */
    suspend fun recordSync(atMillis: Long, newActivities: Int) {
        context.dataStore.edit { prefs ->
            prefs[lastSyncAtKey] = atMillis
            prefs[lastSyncNewCountKey] = newActivities
        }
    }

    /**
     * Atomically swaps in the highest activity id seen so far, returning the
     * previous value. Lets the sync worker detect how many activities in a
     * sync response are new (id monotonically increases) without a local
     * activity cache.
     */
    suspend fun swapMaxActivityId(candidate: Int): Int {
        var previous = 0
        context.dataStore.edit { prefs ->
            previous = prefs[lastMaxActivityIdKey] ?: 0
            if (candidate > previous) prefs[lastMaxActivityIdKey] = candidate
        }
        return previous
    }

    /** Epoch-millis of the last successful Health Connect read (A2), or null. */
    suspend fun healthConnectSyncedAt(): Long? =
        context.dataStore.data.map { it[healthConnectSyncedAtKey] }.first()

    /** Record a successful Health Connect read at ``atMillis`` (A2). */
    suspend fun recordHealthConnectSync(atMillis: Long) {
        context.dataStore.edit { prefs -> prefs[healthConnectSyncedAtKey] = atMillis }
    }

    private fun normalizeUrl(url: String): String {
        val trimmed = url.trim()
        if (trimmed.isEmpty()) return BuildConfig.DEFAULT_BASE_URL
        return if (trimmed.endsWith("/")) trimmed else "$trimmed/"
    }
}
