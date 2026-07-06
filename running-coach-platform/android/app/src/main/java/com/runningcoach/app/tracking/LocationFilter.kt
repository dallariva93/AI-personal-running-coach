package com.runningcoach.app.tracking

import kotlin.math.asin
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.sqrt

/** A filtered GPS fix the tracker actually counts. */
data class TrackPoint(
    val timeMillis: Long,
    val lat: Double,
    val lon: Double,
)

/**
 * The "light Kalman" of the brief, in its honest form: hard outlier rejection
 * (bad accuracy, teleport speeds) followed by exponential smoothing of the
 * coordinates. Urban GPS jitter is dominated by these two failure modes; a
 * full Kalman filter adds tuning surface without changing the outcome at
 * running speeds.
 */
class LocationFilter(
    private val maxAccuracyM: Float = 30f,
    private val maxSpeedMs: Double = 8.0,   // > 8 m/s while "running" = GPS jump
    private val smoothing: Double = 0.35,   // EMA weight of the new fix
) {
    private var last: TrackPoint? = null

    /** Returns the accepted (smoothed) point, or null when the fix is rejected. */
    fun accept(timeMillis: Long, lat: Double, lon: Double, accuracyM: Float): TrackPoint? {
        if (accuracyM > maxAccuracyM) return null
        val prev = last
        if (prev != null) {
            val dtSec = (timeMillis - prev.timeMillis) / 1000.0
            if (dtSec <= 0) return null
            val speed = haversineM(prev.lat, prev.lon, lat, lon) / dtSec
            if (speed > maxSpeedMs) return null
            val smLat = prev.lat + smoothing * (lat - prev.lat)
            val smLon = prev.lon + smoothing * (lon - prev.lon)
            return TrackPoint(timeMillis, smLat, smLon).also { last = it }
        }
        return TrackPoint(timeMillis, lat, lon).also { last = it }
    }

    fun reset() {
        last = null
    }

    companion object {
        private const val EARTH_RADIUS_M = 6_371_000.0

        /** Great-circle distance in metres. */
        fun haversineM(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
            val dLat = Math.toRadians(lat2 - lat1)
            val dLon = Math.toRadians(lon2 - lon1)
            val a = sin(dLat / 2).pow(2) +
                cos(Math.toRadians(lat1)) * cos(Math.toRadians(lat2)) * sin(dLon / 2).pow(2)
            return 2 * EARTH_RADIUS_M * asin(sqrt(a))
        }
    }
}

/** Standard Google encoded-polyline algorithm (the format the backend stores). */
object PolylineEncoder {

    fun encode(points: List<TrackPoint>): String {
        val sb = StringBuilder()
        var prevLat = 0
        var prevLon = 0
        for (p in points) {
            val lat = Math.round(p.lat * 1e5).toInt()
            val lon = Math.round(p.lon * 1e5).toInt()
            encodeDiff(lat - prevLat, sb)
            encodeDiff(lon - prevLon, sb)
            prevLat = lat
            prevLon = lon
        }
        return sb.toString()
    }

    private fun encodeDiff(value: Int, sb: StringBuilder) {
        var v = value shl 1
        if (value < 0) v = v.inv()
        while (v >= 0x20) {
            sb.append(((0x20 or (v and 0x1f)) + 63).toChar())
            v = v shr 5
        }
        sb.append((v + 63).toChar())
    }
}
