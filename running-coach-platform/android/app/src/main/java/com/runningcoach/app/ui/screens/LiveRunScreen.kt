package com.runningcoach.app.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.runningcoach.app.data.local.AppDatabase
import com.runningcoach.app.data.local.RunRecordingEntity
import com.runningcoach.app.tracking.LiveTrackingState
import com.runningcoach.app.tracking.LiveUploadQueue
import com.runningcoach.app.tracking.TrackingService
import com.runningcoach.app.tracking.TrackingSession
import com.runningcoach.app.ui.components.Pill
import com.runningcoach.app.ui.components.ScreenTitle
import com.runningcoach.app.ui.components.SurfaceCard
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.theme.Coral
import kotlinx.coroutines.launch

/**
 * Live GPS run screen (G1, milestone M3): big numbers while recording — time,
 * distance, instant (15s-smoothed) and average pace — with today's planned
 * session in view, a manual lap button, auto-pause indication, and the
 * confirm-then-upload flow (M2 queue) at the end. On open it also recovers an
 * orphan recording left by a crash/kill.
 */
@Composable
fun LiveRunScreen(
    todaySessionTitle: String?,
    onBack: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val state by TrackingSession.state.collectAsState()

    var recovered by remember { mutableStateOf<RunRecordingEntity?>(null) }
    var finishedId by remember { mutableStateOf<String?>(null) }
    var message by remember { mutableStateOf<String?>(null) }

    // Crash recovery: an orphan "recording" row with no live session behind it.
    LaunchedEffect(Unit) {
        if (state.status == LiveTrackingState.Status.IDLE) {
            recovered = AppDatabase.get(context).runRecordingDao()
                .byState(RunRecordingEntity.STATE_RECORDING).firstOrNull()
        }
    }
    // When the service flips to FINISHED, remember which recording to confirm.
    LaunchedEffect(state.status) {
        if (state.status == LiveTrackingState.Status.FINISHED) {
            finishedId = state.recordingId
        }
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> if (granted) TrackingService.start(context) }

    fun startRun() {
        val fine = ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (fine) TrackingService.start(context)
        else permissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
    }

    fun saveAndUpload(recordingId: String) {
        scope.launch {
            val dao = AppDatabase.get(context).runRecordingDao()
            dao.byId(recordingId)?.let { LiveUploadQueue.enqueueFinished(context, it) }
            message = "Corsa in coda di caricamento: parte appena c'è rete."
            finishedId = null
            recovered = null
            TrackingSession.resetToIdle()
        }
    }

    fun discard(recordingId: String) {
        scope.launch {
            AppDatabase.get(context).runRecordingDao().delete(recordingId)
            finishedId = null
            recovered = null
            TrackingSession.resetToIdle()
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = 16.dp, vertical = 12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Indietro")
            }
            ScreenTitle("Corsa live", "GPS del telefono, nessun hardware", Modifier.weight(1f))
            if (state.autoPaused) Pill("AUTO-PAUSA", Coral)
        }
        Spacer(Modifier.height(12.dp))

        todaySessionTitle?.let {
            SurfaceCard {
                Text("Seduta di oggi", style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(it, style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold)
            }
            Spacer(Modifier.height(12.dp))
        }

        when {
            finishedId != null -> ConfirmCard(
                title = "Corsa completata",
                distanceKm = state.distanceKm,
                seconds = state.activeSec,
                onSave = { saveAndUpload(finishedId!!) },
                onDiscard = { discard(finishedId!!) },
            )
            recovered != null -> ConfirmCard(
                title = "Corsa recuperata (app interrotta)",
                distanceKm = recovered!!.distanceKm,
                seconds = (recovered!!.durationMin * 60).toLong(),
                onSave = { saveAndUpload(recovered!!.id) },
                onDiscard = { discard(recovered!!.id) },
            )
            state.status == LiveTrackingState.Status.RECORDING -> {
                LiveNumbers(state)
                Spacer(Modifier.height(20.dp))
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    OutlinedButton(
                        onClick = { TrackingService.lap(context) },
                        modifier = Modifier.weight(1f),
                    ) { Text("Lap (${state.laps.size})") }
                    Button(
                        onClick = { TrackingService.stop(context) },
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = Coral),
                    ) { Text("Termina") }
                }
            }
            else -> {
                SurfaceCard {
                    Text(
                        "Registra la corsa col GPS del telefono: distanza, passo e "
                            + "traccia. Funziona anche offline — il caricamento parte "
                            + "da solo quando torna la rete.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Spacer(Modifier.height(16.dp))
                Button(onClick = { startRun() }, modifier = Modifier.fillMaxWidth()) {
                    Text("Inizia la corsa")
                }
            }
        }

        message?.let {
            Spacer(Modifier.height(12.dp))
            Text(it, color = BrandGreen, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun LiveNumbers(state: LiveTrackingState) {
    SurfaceCard {
        Column(horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.fillMaxWidth()) {
            Text(formatDuration(state.activeSec),
                style = MaterialTheme.typography.displayLarge, fontWeight = FontWeight.Bold)
            Text(String.format("%.2f km", state.distanceKm),
                style = MaterialTheme.typography.displaySmall)
            Spacer(Modifier.height(12.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                PaceStat("Passo (15s)", state.instPaceSecPerKm)
                PaceStat("Passo medio", state.avgPaceSecPerKm)
            }
        }
    }
}

@Composable
private fun PaceStat(label: String, secPerKm: Double?) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(secPerKm?.let(::formatPace) ?: "—",
            style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun ConfirmCard(
    title: String,
    distanceKm: Double,
    seconds: Long,
    onSave: () -> Unit,
    onDiscard: () -> Unit,
) {
    SurfaceCard {
        Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Text(
            String.format("%.2f km in %s", distanceKm, formatDuration(seconds)),
            style = MaterialTheme.typography.headlineSmall,
        )
        Spacer(Modifier.height(14.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(onClick = onDiscard, modifier = Modifier.weight(1f)) {
                Text("Scarta")
            }
            Button(onClick = onSave, modifier = Modifier.weight(1f)) {
                Text("Salva e carica")
            }
        }
    }
}

private fun formatDuration(totalSec: Long): String {
    val h = totalSec / 3600
    val m = (totalSec % 3600) / 60
    val s = totalSec % 60
    return if (h > 0) String.format("%d:%02d:%02d", h, m, s)
    else String.format("%d:%02d", m, s)
}

private fun formatPace(secPerKm: Double): String {
    val total = secPerKm.toInt()
    return String.format("%d:%02d/km", total / 60, total % 60)
}
