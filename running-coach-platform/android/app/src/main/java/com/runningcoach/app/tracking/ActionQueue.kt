package com.runningcoach.app.tracking

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.runningcoach.app.RunningCoachApp
import com.runningcoach.app.data.local.AppDatabase
import java.util.concurrent.TimeUnit

/**
 * Offline action queue (G5, milestone M4): user actions taken without network
 * (Today-card actions, calendar moves) are stored in Room and replayed in
 * order when connectivity returns — same worker discipline as the M2 upload
 * queue (network constraint, exponential backoff, survives reboots).
 *
 * A replay that fails with a *server* answer (HTTP 4xx/5xx) is dropped after
 * being recorded: the backend rejected it deliberately (e.g. the move became
 * invalid) and repeating it forever would be wrong. Network errors retry.
 */
object ActionQueue {

    const val KIND_COACH_ACTION = "coach_action"
    const val KIND_PLAN_MOVE = "plan_move"
    private const val WORK_NAME = "action-replay"

    fun kick(context: Context) {
        val request = OneTimeWorkRequestBuilder<ActionReplayWorker>()
            .setConstraints(
                Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
            )
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            WORK_NAME,
            ExistingWorkPolicy.KEEP,
            request,
        )
    }
}

/** Replays queued offline actions in order. */
class ActionReplayWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    private val gson = Gson()

    override suspend fun doWork(): Result {
        val app = applicationContext as? RunningCoachApp ?: return Result.success()
        val dao = AppDatabase.get(applicationContext).pendingActionDao()

        var anyNetworkFailure = false
        for (item in dao.all()) {
            val payload = runCatching {
                gson.fromJson(item.payloadJson, JsonObject::class.java)
            }.getOrNull()
            if (payload == null) {
                dao.remove(item.id)  // unreadable entry: drop it
                continue
            }
            runCatching { replay(app, item.kind, payload) }
                .onSuccess { dao.remove(item.id) }
                .onFailure { err ->
                    if (err is retrofit2.HttpException) {
                        // Deliberate server rejection: record and drop.
                        dao.recordFailure(item.id, "HTTP ${err.code()}")
                        dao.remove(item.id)
                    } else {
                        anyNetworkFailure = true
                        dao.recordFailure(item.id, err.message?.take(200))
                    }
                }
        }
        return if (anyNetworkFailure) Result.retry() else Result.success()
    }

    private suspend fun replay(app: RunningCoachApp, kind: String, payload: JsonObject) {
        when (kind) {
            ActionQueue.KIND_COACH_ACTION -> app.repository.coachAction(
                action = payload.get("action").asString,
                detail = payload.get("detail")?.takeIf { !it.isJsonNull }?.asString,
            )
            ActionQueue.KIND_PLAN_MOVE -> app.repository.movePlanSession(
                payload.get("sessionId").asInt,
                payload.get("targetDate").asString,
            )
            else -> Unit  // unknown kind from a future version: ignore
        }
    }
}
