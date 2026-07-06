package com.runningcoach.app.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

/**
 * Room enters the project with G1/G5: the crash-safe recording store and the
 * offline upload queue (this milestone); the offline caches (CachedOverview /
 * CachedPlan, milestone M4) will join as new entities with a version bump.
 */
@Database(
    entities = [RunRecordingEntity::class, PendingUploadEntity::class],
    version = 1,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {

    abstract fun runRecordingDao(): RunRecordingDao
    abstract fun pendingUploadDao(): PendingUploadDao

    companion object {
        @Volatile
        private var instance: AppDatabase? = null

        fun get(context: Context): AppDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "running_coach.db",
                ).build().also { instance = it }
            }
    }
}
