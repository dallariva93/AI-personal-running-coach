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
import com.google.gson.reflect.TypeToken
import com.runningcoach.app.RunningCoachApp
import com.runningcoach.app.data.local.AppDatabase
import com.runningcoach.app.data.local.RunRecordingEntity
import com.runningcoach.app.data.model.LiveLap
import com.runningcoach.app.data.model.LiveRunIn
import com.runningcoach.app.data.model.LiveSample
import java.util.concurrent.TimeUnit

/**
 * The offline upload queue for live recordings (G1, milestone M2).
 *
 * The invariant that matters: **a finished run is never lost**. It lives in
 * Room (`pending_uploads` + its `run_recordings` row) until the backend
 * answers 2xx; the worker retries with exponential backoff, only runs with
 * network, and survives reboots (WorkManager persists enqueued work). The
 * backend dedupes on `live_id`, so a retry after a half-received upload can
 * never duplicate the activity.
 */
object LiveUploadQueue {

    private const val WORK_NAME = "live-upload"

    /** Mark a finished recording for upload and make sure the worker runs. */
    suspend fun enqueueFinished(context: Context, recording: RunRecordingEntity) {
        val db = AppDatabase.get(context)
        db.runRecordingDao().upsert(
            recording.copy(state = RunRecordingEntity.STATE_FINISHED)
        )
        db.pendingUploadDao().enqueue(
            com.runningcoach.app.data.local.PendingUploadEntity(recordingId = recording.id)
        )
        kick(context)
    }

    /**
     * Ensure an upload pass is scheduled. Cheap to call at every app start:
     * with an empty queue the worker exits immediately, and KEEP collapses
     * duplicate requests into the one already scheduled/backing off.
     */
    fun kick(context: Context) {
        val request = OneTimeWorkRequestBuilder<LiveUploadWorker>()
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

/** Drains the pending-upload queue; retries (with backoff) until it is empty. */
class LiveUploadWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    private val gson = Gson()

    override suspend fun doWork(): Result {
        val app = applicationContext as? RunningCoachApp ?: return Result.success()
        val db = AppDatabase.get(applicationContext)
        val recordings = db.runRecordingDao()
        val pending = db.pendingUploadDao()

        var anyFailure = false
        for (item in pending.all()) {
            val recording = recordings.byId(item.recordingId)
            if (recording == null) {
                pending.remove(item.recordingId)  // orphan entry: nothing to send
                continue
            }
            runCatching {
                app.repository.uploadLiveRun(toPayload(recording))
            }.onSuccess {
                recordings.setState(recording.id, RunRecordingEntity.STATE_UPLOADED)
                pending.remove(recording.id)
            }.onFailure { err ->
                anyFailure = true
                pending.recordFailure(recording.id, err.message?.take(200))
            }
        }
        return if (anyFailure) Result.retry() else Result.success()
    }

    private fun toPayload(r: RunRecordingEntity): LiveRunIn {
        val samplesType = object : TypeToken<List<LiveSample>>() {}.type
        val lapsType = object : TypeToken<List<LiveLap>>() {}.type
        return LiveRunIn(
            liveId = r.id,
            date = r.date,
            startTime = r.startTime,
            durationMin = r.durationMin,
            distanceKm = r.distanceKm,
            samples = gson.fromJson(r.samplesJson, samplesType) ?: emptyList(),
            laps = gson.fromJson(r.lapsJson, lapsType) ?: emptyList(),
            routePolyline = r.routePolyline,
            name = r.name,
        )
    }
}
