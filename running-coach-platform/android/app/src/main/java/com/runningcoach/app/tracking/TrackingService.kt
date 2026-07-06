package com.runningcoach.app.tracking

import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.gson.Gson
import com.runningcoach.app.MainActivity
import com.runningcoach.app.R
import com.runningcoach.app.data.local.AppDatabase
import com.runningcoach.app.data.local.RunRecordingEntity
import com.runningcoach.app.data.model.LiveLap
import com.runningcoach.app.data.model.LiveSample
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.UUID
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/** Live tracking state observed by the UI (G1). */
data class LiveTrackingState(
    val status: Status = Status.IDLE,
    val recordingId: String? = null,
    val distanceKm: Double = 0.0,
    val activeSec: Long = 0,
    val instPaceSecPerKm: Double? = null,  // smoothed over the last 15s
    val avgPaceSecPerKm: Double? = null,
    val laps: List<LiveLap> = emptyList(),
    val autoPaused: Boolean = false,
) {
    enum class Status { IDLE, RECORDING, FINISHED }
}

/** Singleton bridge between [TrackingService] and the Compose screen. */
object TrackingSession {
    internal val mutable = MutableStateFlow(LiveTrackingState())
    val state: StateFlow<LiveTrackingState> = mutable.asStateFlow()

    fun resetToIdle() {
        mutable.value = LiveTrackingState()
    }
}

/**
 * Foreground service (type=location) recording a run (G1, milestone M3).
 *
 * FusedLocationProvider at 1s; fixes pass the outlier/smoothing filter; every
 * ~5s batch the whole recording snapshot is upserted to Room — crash-safe: a
 * kill loses at most the last seconds, and the orphan row is recovered by the
 * screen on next open. Auto-pause freezes time/distance below walking speed
 * (<1.4 km/h for >10s). Stopping leaves the row for the confirm screen, which
 * either enqueues the upload (M2 queue) or discards.
 */
class TrackingService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val gson = Gson()
    private val filter = LocationFilter()

    private lateinit var fused: FusedLocationProviderClient

    private var recordingId: String = ""
    private var startedAtMillis: Long = 0
    private var distanceM = 0.0
    private var activeSec = 0L
    private var lastPoint: TrackPoint? = null
    private val points = mutableListOf<TrackPoint>()          // for the polyline
    private val samples = mutableListOf<LiveSample>()          // cumulative (t, d)
    private val laps = mutableListOf<LiveLap>()
    private val recentWindow = ArrayDeque<Pair<Long, Double>>()  // (activeSec, distM) last ~15s
    private var stillSinceSec: Long? = null
    private var autoPaused = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        fused = LocationServices.getFusedLocationProviderClient(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> start()
            ACTION_LAP -> lap()
            ACTION_STOP -> stopRecording()
        }
        return START_STICKY
    }

    @SuppressLint("MissingPermission")  // the screen gates start on FINE granted
    private fun start() {
        if (recordingId.isNotEmpty()) return  // already recording
        recordingId = UUID.randomUUID().toString()
        startedAtMillis = System.currentTimeMillis()
        filter.reset()
        TrackingSession.mutable.value = LiveTrackingState(
            status = LiveTrackingState.Status.RECORDING, recordingId = recordingId,
        )

        startForeground(NOTIFICATION_ID, buildNotification("In registrazione…"))

        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 1000L)
            .setMinUpdateIntervalMillis(1000L)
            .build()
        runCatching { fused.requestLocationUpdates(request, callback, Looper.getMainLooper()) }

        scope.launch { ticker() }
    }

    private val callback = object : LocationCallback() {
        override fun onLocationResult(result: LocationResult) {
            for (loc in result.locations) {
                val accepted = filter.accept(loc.time, loc.latitude, loc.longitude, loc.accuracy)
                    ?: continue
                val prev = lastPoint
                if (prev != null && !autoPaused) {
                    distanceM += LocationFilter.haversineM(
                        prev.lat, prev.lon, accepted.lat, accepted.lon,
                    )
                }
                lastPoint = accepted
                points.add(accepted)
            }
        }
    }

    /** 1s heartbeat: time, auto-pause, live pace, periodic crash-safe persist. */
    private suspend fun ticker() {
        var sincePersist = 0
        while (scope.isActive && recordingId.isNotEmpty()) {
            delay(1000)
            updateAutoPause()
            if (!autoPaused) {
                activeSec += 1
                recentWindow.addLast(activeSec to distanceM)
                while (recentWindow.size > 15) recentWindow.removeFirst()
            }
            publishState()
            sincePersist += 1
            if (sincePersist >= 5) {
                sincePersist = 0
                samples.add(LiveSample(t = activeSec.toDouble(), d = distanceM / 1000.0))
                persistSnapshot()
                updateNotification()
            }
        }
    }

    /** Below 1.4 km/h (0.39 m/s) for more than 10s → freeze time and distance. */
    private fun updateAutoPause() {
        val speedMs = recentSpeedMs()
        if (speedMs != null && speedMs < 1.4 / 3.6) {
            val since = stillSinceSec ?: activeSec.also { stillSinceSec = it }
            if (activeSec - since > 10) autoPaused = true
        } else {
            stillSinceSec = null
            autoPaused = false
        }
    }

    private fun recentSpeedMs(): Double? {
        val oldest = recentWindow.firstOrNull() ?: return null
        val newest = recentWindow.lastOrNull() ?: return null
        val dt = newest.first - oldest.first
        if (dt < 5) return null  // not enough window yet
        return (newest.second - oldest.second) / dt
    }

    private fun publishState() {
        val km = distanceM / 1000.0
        val inst = recentSpeedMs()?.takeIf { it > 0.4 }?.let { 1000.0 / it }
        val avg = if (km > 0.05) activeSec / km else null
        TrackingSession.mutable.value = LiveTrackingState(
            status = LiveTrackingState.Status.RECORDING,
            recordingId = recordingId,
            distanceKm = km,
            activeSec = activeSec,
            instPaceSecPerKm = inst,
            avgPaceSecPerKm = avg,
            laps = laps.toList(),
            autoPaused = autoPaused,
        )
    }

    private fun lap() {
        if (recordingId.isEmpty()) return
        laps.add(LiveLap(t = activeSec.toDouble(), d = distanceM / 1000.0))
        publishState()
    }

    private fun stopRecording() {
        if (recordingId.isEmpty()) return
        runCatching { fused.removeLocationUpdates(callback) }
        // Final snapshot; the confirm screen decides save (M2 queue) or discard.
        samples.add(LiveSample(t = activeSec.toDouble(), d = distanceM / 1000.0))
        persistSnapshot()
        TrackingSession.mutable.value = TrackingSession.mutable.value.copy(
            status = LiveTrackingState.Status.FINISHED,
        )
        recordingId = ""
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun persistSnapshot() {
        val zone = ZoneId.systemDefault()
        val started = Instant.ofEpochMilli(startedAtMillis).atZone(zone)
        val entity = RunRecordingEntity(
            id = recordingId,
            startedAtMillis = startedAtMillis,
            state = RunRecordingEntity.STATE_RECORDING,
            date = started.toLocalDate().toString(),
            startTime = started.format(DateTimeFormatter.ofPattern("HH:mm")),
            durationMin = activeSec / 60.0,
            distanceKm = distanceM / 1000.0,
            samplesJson = gson.toJson(samples),
            lapsJson = gson.toJson(laps),
            routePolyline = PolylineEncoder.encode(points).ifEmpty { null },
            name = null,
        )
        scope.launch {
            runCatching { AppDatabase.get(applicationContext).runRecordingDao().upsert(entity) }
        }
    }

    private fun buildNotification(text: String): android.app.Notification {
        val channelId = ensureChannel()
        val tap = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, channelId)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("Registrazione corsa")
            .setContentText(text)
            .setOngoing(true)
            .setContentIntent(tap)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun updateNotification() {
        val km = distanceM / 1000.0
        val m = activeSec / 60
        val s = activeSec % 60
        val text = String.format("%.2f km · %d:%02d", km, m, s)
        val mgr = getSystemService(NotificationManager::class.java) ?: return
        mgr.notify(NOTIFICATION_ID, buildNotification(text))
    }

    private fun ensureChannel(): String {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, "Registrazione corsa", NotificationManager.IMPORTANCE_LOW,
            )
            getSystemService(NotificationManager::class.java)?.createNotificationChannel(channel)
        }
        return CHANNEL_ID
    }

    override fun onDestroy() {
        runCatching { fused.removeLocationUpdates(callback) }
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        private const val CHANNEL_ID = "live_tracking"
        private const val NOTIFICATION_ID = 4242
        private const val ACTION_START = "com.runningcoach.app.tracking.START"
        private const val ACTION_LAP = "com.runningcoach.app.tracking.LAP"
        private const val ACTION_STOP = "com.runningcoach.app.tracking.STOP"

        fun start(context: Context) = send(context, ACTION_START, foreground = true)
        fun lap(context: Context) = send(context, ACTION_LAP)
        fun stop(context: Context) = send(context, ACTION_STOP)

        private fun send(context: Context, action: String, foreground: Boolean = false) {
            val intent = Intent(context, TrackingService::class.java).setAction(action)
            if (foreground) context.startForegroundService(intent)
            else context.startService(intent)
        }
    }
}
