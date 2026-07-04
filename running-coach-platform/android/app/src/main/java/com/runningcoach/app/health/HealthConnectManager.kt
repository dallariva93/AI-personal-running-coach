package com.runningcoach.app.health

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.aggregate.AggregationResult
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.ElevationGainedRecord
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.HeartRateVariabilityRmssdRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import com.runningcoach.app.data.model.HealthConnectImportIn
import com.runningcoach.app.data.model.HealthConnectRun
import com.runningcoach.app.data.model.HealthConnectWellness
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

/**
 * Reads running sessions and wellness (sleep, HRV) from Android Health Connect
 * (Roadmap A2) and maps them onto the backend import payload. This is the
 * no-Garmin path: any HC-compatible app (Samsung Health, adidas Running, …) that
 * writes to Health Connect becomes a data source.
 *
 * All reads are read-only and require the athlete's explicit consent
 * (see [permissions]); nothing is written back to Health Connect.
 */
class HealthConnectManager(private val context: Context) {

    /** READ permissions we request (never WRITE). */
    val permissions: Set<String> = setOf(
        HealthPermission.getReadPermission(ExerciseSessionRecord::class),
        HealthPermission.getReadPermission(DistanceRecord::class),
        HealthPermission.getReadPermission(ElevationGainedRecord::class),
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(SleepSessionRecord::class),
        HealthPermission.getReadPermission(HeartRateVariabilityRmssdRecord::class),
    )

    /** True when Health Connect is installed and usable on this device. */
    fun isAvailable(): Boolean =
        HealthConnectClient.getSdkStatus(context) == HealthConnectClient.SDK_AVAILABLE

    private fun client(): HealthConnectClient = HealthConnectClient.getOrCreate(context)

    suspend fun hasAllPermissions(): Boolean =
        client().permissionController.getGrantedPermissions().containsAll(permissions)

    /** Read every running session (and wellness) since [since], as an import payload. */
    suspend fun readSince(since: Instant): HealthConnectImportIn {
        val c = client()
        val range = TimeRangeFilter.after(since)

        val sessions = c.readRecords(
            ReadRecordsRequest(ExerciseSessionRecord::class, timeRangeFilter = range),
        ).records.filter { it.exerciseType == ExerciseSessionRecord.EXERCISE_TYPE_RUNNING }

        val runs = sessions.mapNotNull { s -> runFor(c, s) }
        val wellness = wellnessSince(c, range)
        return HealthConnectImportIn(runs = runs, wellness = wellness)
    }

    private suspend fun runFor(
        c: HealthConnectClient,
        s: ExerciseSessionRecord,
    ): HealthConnectRun? {
        val sessionRange = TimeRangeFilter.between(s.startTime, s.endTime)
        val agg: AggregationResult = c.aggregate(
            AggregateRequest(
                metrics = setOf(
                    DistanceRecord.DISTANCE_TOTAL,
                    ElevationGainedRecord.ELEVATION_GAINED_TOTAL,
                    HeartRateRecord.BPM_AVG,
                    HeartRateRecord.BPM_MAX,
                ),
                timeRangeFilter = sessionRange,
            ),
        )
        val distanceKm = agg[DistanceRecord.DISTANCE_TOTAL]?.inKilometers ?: 0.0
        val durationMin = Duration.between(s.startTime, s.endTime).seconds / 60.0
        if (distanceKm <= 0.0 || durationMin <= 0.0) return null

        val zone = s.startZoneOffset ?: ZoneOffset.UTC
        val local = s.startTime.atZone(zone)
        return HealthConnectRun(
            healthConnectId = s.metadata.id,
            date = local.toLocalDate().toString(),
            startTime = local.format(DateTimeFormatter.ofPattern("HH:mm")),
            durationMin = durationMin,
            distanceKm = distanceKm,
            avgHr = agg[HeartRateRecord.BPM_AVG]?.toInt(),
            maxHr = agg[HeartRateRecord.BPM_MAX]?.toInt(),
            elevationGainM = agg[ElevationGainedRecord.ELEVATION_GAINED_TOTAL]?.inMeters,
            name = s.title,
        )
    }

    private suspend fun wellnessSince(
        c: HealthConnectClient,
        range: TimeRangeFilter,
    ): List<HealthConnectWellness> {
        val zone = ZoneId.systemDefault()
        val sleepByDate = HashMap<String, Double>()
        c.readRecords(ReadRecordsRequest(SleepSessionRecord::class, timeRangeFilter = range))
            .records.forEach { sleep ->
                val date = sleep.endTime.atZone(zone).toLocalDate().toString()
                val hours = Duration.between(sleep.startTime, sleep.endTime).seconds / 3600.0
                sleepByDate[date] = (sleepByDate[date] ?: 0.0) + hours
            }

        val hrvByDate = HashMap<String, MutableList<Double>>()
        c.readRecords(
            ReadRecordsRequest(HeartRateVariabilityRmssdRecord::class, timeRangeFilter = range),
        ).records.forEach { hrv ->
            val date = hrv.time.atZone(zone).toLocalDate().toString()
            hrvByDate.getOrPut(date) { mutableListOf() }.add(hrv.heartRateVariabilityMillis)
        }

        val dates = sleepByDate.keys + hrvByDate.keys
        return dates.map { date ->
            val hrv = hrvByDate[date]?.let { it.sum() / it.size }
            HealthConnectWellness(
                date = date,
                sleepH = sleepByDate[date]?.let { Math.round(it * 10.0) / 10.0 },
                hrvRmssd = hrv?.let { Math.round(it * 10.0) / 10.0 },
            )
        }
    }
}
