package com.runningcoach.app.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * A live-run recording persisted locally (G1). Written every location batch
 * while recording, so a crash/kill mid-run loses at most a few seconds; the
 * same row is later serialized into the upload payload. The primary key is the
 * client-generated UUID that the backend dedupes on (``live_id``), so retrying
 * an upload can never duplicate the run.
 *
 * ``state`` lifecycle: recording → finished → uploaded.
 */
@Entity(tableName = "run_recordings")
data class RunRecordingEntity(
    @PrimaryKey val id: String,
    val startedAtMillis: Long,
    val state: String = STATE_RECORDING,
    val date: String = "",            // ISO YYYY-MM-DD (local)
    val startTime: String? = null,    // local "HH:MM"
    val durationMin: Double = 0.0,
    val distanceKm: Double = 0.0,
    // Cumulative samples/laps as JSON arrays of {t: sec, d: km[, hr]} — the
    // exact shape POST /api/activities/live expects. JSON keeps the schema
    // flexible without Room migrations for every tweak.
    val samplesJson: String = "[]",
    val lapsJson: String = "[]",
    val routePolyline: String? = null,
    val name: String? = null,
) {
    companion object {
        const val STATE_RECORDING = "recording"
        const val STATE_FINISHED = "finished"
        const val STATE_UPLOADED = "uploaded"
    }
}

/**
 * One entry in the offline upload queue (G1): a finished recording waiting to
 * reach the backend. The row survives until a 2xx — the run is never lost.
 */
@Entity(tableName = "pending_uploads")
data class PendingUploadEntity(
    @PrimaryKey val recordingId: String,
    val attempts: Int = 0,
    val lastError: String? = null,
    val createdAtMillis: Long = System.currentTimeMillis(),
)
