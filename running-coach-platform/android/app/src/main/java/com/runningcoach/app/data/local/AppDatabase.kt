package com.runningcoach.app.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

/**
 * Room entered the project with G1/G5: v1 = the crash-safe recording store +
 * offline upload queue (M2); v2 adds the offline snapshot cache and the
 * pending-action queue (M4). Migrations are additive-only — a destructive
 * fallback could wipe a not-yet-uploaded run, which G1's core invariant
 * ("the run is never lost") forbids.
 */
@Database(
    entities = [
        RunRecordingEntity::class,
        PendingUploadEntity::class,
        CachedPayloadEntity::class,
        PendingActionEntity::class,
    ],
    version = 2,
    exportSchema = false,
)
abstract class AppDatabase : RoomDatabase() {

    abstract fun runRecordingDao(): RunRecordingDao
    abstract fun pendingUploadDao(): PendingUploadDao
    abstract fun cachedPayloadDao(): CachedPayloadDao
    abstract fun pendingActionDao(): PendingActionDao

    companion object {
        @Volatile
        private var instance: AppDatabase? = null

        /** v1 → v2 (M4): offline cache + action queue. Purely additive. */
        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS `cached_payloads` (" +
                        "`key` TEXT NOT NULL, `json` TEXT NOT NULL, " +
                        "`updatedAtMillis` INTEGER NOT NULL, PRIMARY KEY(`key`))"
                )
                db.execSQL(
                    "CREATE TABLE IF NOT EXISTS `pending_actions` (" +
                        "`id` INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, " +
                        "`kind` TEXT NOT NULL, `payloadJson` TEXT NOT NULL, " +
                        "`createdAtMillis` INTEGER NOT NULL, " +
                        "`attempts` INTEGER NOT NULL, `lastError` TEXT)"
                )
            }
        }

        fun get(context: Context): AppDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "running_coach.db",
                ).addMigrations(MIGRATION_1_2).build().also { instance = it }
            }
    }
}
