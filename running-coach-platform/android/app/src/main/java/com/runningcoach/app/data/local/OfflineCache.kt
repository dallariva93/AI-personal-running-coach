package com.runningcoach.app.data.local

import android.content.Context
import com.google.gson.Gson
import com.runningcoach.app.data.model.Overview
import com.runningcoach.app.data.model.TrainingPlan
import com.runningcoach.app.tracking.ActionQueue

/** A cached snapshot with its write timestamp (for the "dati di ieri" banner). */
data class CachedSnapshot<T>(val value: T, val updatedAtMillis: Long)

/**
 * The app's offline façade (G5, milestone M4): read/write the last known
 * overview and plan (cached-first rendering) and queue user actions taken
 * while offline for replay. Everything is best-effort — a cache failure must
 * never break the online path.
 */
class OfflineCache(private val context: Context) {

    private val gson = Gson()
    private val dao get() = AppDatabase.get(context).cachedPayloadDao()

    // ── Snapshot cache ───────────────────────────────────────────────────────

    suspend fun readOverview(): CachedSnapshot<Overview>? = read(KEY_OVERVIEW)

    suspend fun writeOverview(overview: Overview) = write(KEY_OVERVIEW, overview)

    suspend fun readPlan(): CachedSnapshot<TrainingPlan>? = read(KEY_PLAN)

    suspend fun writePlan(plan: TrainingPlan) = write(KEY_PLAN, plan)

    private suspend inline fun <reified T> read(key: String): CachedSnapshot<T>? =
        runCatching {
            dao.get(key)?.let {
                CachedSnapshot(gson.fromJson(it.json, T::class.java), it.updatedAtMillis)
            }
        }.getOrNull()

    private suspend fun write(key: String, value: Any) {
        runCatching {
            dao.put(
                CachedPayloadEntity(
                    key = key,
                    json = gson.toJson(value),
                    updatedAtMillis = System.currentTimeMillis(),
                )
            )
        }
    }

    // ── Offline action queue (replayed by ActionReplayWorker) ───────────────

    suspend fun enqueueCoachAction(action: String, detail: String?) {
        enqueue(ActionQueue.KIND_COACH_ACTION, mapOf("action" to action, "detail" to detail))
    }

    suspend fun enqueuePlanMove(sessionId: Int, targetDate: String) {
        enqueue(
            ActionQueue.KIND_PLAN_MOVE,
            mapOf("sessionId" to sessionId, "targetDate" to targetDate),
        )
    }

    private suspend fun enqueue(kind: String, payload: Map<String, Any?>) {
        runCatching {
            AppDatabase.get(context).pendingActionDao().enqueue(
                PendingActionEntity(kind = kind, payloadJson = gson.toJson(payload))
            )
            ActionQueue.kick(context)
        }
    }

    companion object {
        private const val KEY_OVERVIEW = "overview"
        private const val KEY_PLAN = "plan"
    }
}
