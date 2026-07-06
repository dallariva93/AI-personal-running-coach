package com.runningcoach.app.data.local

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface RunRecordingDao {

    /** Upsert: the tracker rewrites the whole row on every location batch. */
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(recording: RunRecordingEntity)

    @Query("SELECT * FROM run_recordings WHERE id = :id")
    suspend fun byId(id: String): RunRecordingEntity?

    @Query("SELECT * FROM run_recordings WHERE state = :state ORDER BY startedAtMillis DESC")
    suspend fun byState(state: String): List<RunRecordingEntity>

    @Query("UPDATE run_recordings SET state = :state WHERE id = :id")
    suspend fun setState(id: String, state: String)

    @Query("DELETE FROM run_recordings WHERE id = :id")
    suspend fun delete(id: String)
}

@Dao
interface PendingUploadDao {

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun enqueue(pending: PendingUploadEntity)

    @Query("SELECT * FROM pending_uploads ORDER BY createdAtMillis ASC")
    suspend fun all(): List<PendingUploadEntity>

    @Query(
        "UPDATE pending_uploads SET attempts = attempts + 1, lastError = :error " +
            "WHERE recordingId = :recordingId"
    )
    suspend fun recordFailure(recordingId: String, error: String?)

    @Query("DELETE FROM pending_uploads WHERE recordingId = :recordingId")
    suspend fun remove(recordingId: String)
}
