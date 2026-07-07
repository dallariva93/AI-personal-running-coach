package com.runningcoach.app.data.local

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query

/**
 * Generic JSON snapshot cache (G5): one row per surface. Keys "overview" and
 * "plan" realise the plan's CachedOverview/CachedPlan with a single table —
 * the payloads are already Gson-serializable API models.
 */
@Entity(tableName = "cached_payloads")
data class CachedPayloadEntity(
    @PrimaryKey val key: String,
    val json: String,
    val updatedAtMillis: Long,
)

/**
 * One queued user action taken while offline (G5): replayed in order when the
 * network returns. ``kind`` is "coach_action" or "plan_move"; the payload is
 * the exact arguments as JSON.
 */
@Entity(tableName = "pending_actions")
data class PendingActionEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val kind: String,
    val payloadJson: String,
    val createdAtMillis: Long = System.currentTimeMillis(),
    val attempts: Int = 0,
    val lastError: String? = null,
)

@Dao
interface CachedPayloadDao {

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun put(entry: CachedPayloadEntity)

    @Query("SELECT * FROM cached_payloads WHERE key = :key")
    suspend fun get(key: String): CachedPayloadEntity?
}

@Dao
interface PendingActionDao {

    @Insert
    suspend fun enqueue(action: PendingActionEntity)

    @Query("SELECT * FROM pending_actions ORDER BY createdAtMillis ASC")
    suspend fun all(): List<PendingActionEntity>

    @Query(
        "UPDATE pending_actions SET attempts = attempts + 1, lastError = :error " +
            "WHERE id = :id"
    )
    suspend fun recordFailure(id: Long, error: String?)

    @Query("DELETE FROM pending_actions WHERE id = :id")
    suspend fun remove(id: Long)
}
