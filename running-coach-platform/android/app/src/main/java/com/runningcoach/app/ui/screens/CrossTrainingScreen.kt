package com.runningcoach.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.runningcoach.app.data.model.Activity
import com.runningcoach.app.data.repository.CoachRepository
import com.runningcoach.app.ui.components.ScreenTitle
import com.runningcoach.app.ui.theme.ActivityHard
import com.runningcoach.app.ui.theme.ActivityModerate
import com.runningcoach.app.ui.theme.ActivityTempo
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

/** Visual identity (icon + accent color + label) for each cross-training sport. */
private data class SportStyle(val glyph: String, val color: Color, val label: String)

private fun sportStyle(sport: String): SportStyle = when (sport) {
    "bike" -> SportStyle("🚴", ActivityModerate, "Ciclismo")
    "swim" -> SportStyle("🏊", ActivityTempo, "Nuoto")
    "strength" -> SportStyle("🏋️", ActivityHard, "Palestra")
    else -> SportStyle("🤸", ActivityModerate, "Cross-training")
}

@Composable
fun CrossTrainingScreen(
    repository: CoachRepository,
    onBack: () -> Unit,
) {
    var activities by remember { mutableStateOf<List<Activity>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var syncing by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var reloadTrigger by remember { mutableStateOf(0) }
    val scope = rememberCoroutineScope()

    androidx.compose.runtime.LaunchedEffect(reloadTrigger) {
        loading = true
        runCatching { repository.crossTraining() }
            .onSuccess { activities = it; loading = false }
            .onFailure { error = it.localizedMessage; loading = false }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Indietro")
            }
            ScreenTitle(
                "Cross-training",
                "Bici · Nuoto · Palestra",
                Modifier.weight(1f),
            )
            Button(
                onClick = {
                    if (!syncing) {
                        syncing = true
                        scope.launch {
                            runCatching { repository.ingestCrossTraining() }
                                .onFailure { error = it.localizedMessage }
                            syncing = false
                            reloadTrigger++ // retrigger the list load
                        }
                    }
                },
                enabled = !syncing,
            ) {
                Icon(Icons.Filled.Sync, contentDescription = null, Modifier.height(18.dp))
                Spacer(Modifier.width(6.dp))
                Text(if (syncing) "Sync…" else "Garmin")
            }
        }

        when {
            loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(
                    "Errore: $error",
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(24.dp),
                )
            }
            activities.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.padding(32.dp),
                ) {
                    Text(
                        "🚴 🏊 🏋️",
                        style = MaterialTheme.typography.headlineMedium,
                        // Decorative empty-state illustration (Q7): the two
                        // Text rows right below already say what's missing.
                        modifier = Modifier.clearAndSetSemantics {},
                    )
                    Spacer(Modifier.height(12.dp))
                    Text(
                        "Nessuna attività di cross-training.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        "Le corse Strava arrivano da sole; premi Garmin per " +
                            "sincronizzare bici, nuoto e palestra.",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            else -> LazyColumn(
                Modifier
                    .fillMaxSize()
                    .padding(horizontal = 16.dp),
                contentPadding = PaddingValues(bottom = 16.dp),
            ) {
                items(activities) { act -> CrossTrainingRow(act) }
            }
        }
    }
}

@Composable
private fun CrossTrainingRow(activity: Activity) {
    val style = sportStyle(activity.sport)
    com.runningcoach.app.ui.components.SurfaceCard(Modifier.padding(vertical = 5.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(44.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(style.color.copy(alpha = 0.18f)),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    style.glyph,
                    style = MaterialTheme.typography.titleMedium,
                    // Decorative (Q7): style.label right next to it already
                    // announces the sport ("Ciclismo"/"Nuoto"/"Palestra").
                    modifier = Modifier.clearAndSetSemantics {},
                )
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.width(96.dp)) {
                Text(
                    style.label,
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.Bold,
                    color = style.color,
                )
                Text(
                    activity.date,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.width(8.dp))
            Row(Modifier.weight(1f), horizontalArrangement = Arrangement.SpaceBetween) {
                // Strength has no distance — show duration + HR only.
                if (activity.distanceKm > 0) {
                    Stat("km", fmtKm(activity.distanceKm))
                }
                Stat("min", activity.durationMin.roundToInt().toString())
                Stat("FC", activity.avgHr?.toString() ?: "–")
            }
        }
    }
}

@Composable
private fun Stat(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

private fun fmtKm(v: Double): String =
    if (v == v.roundToInt().toDouble()) v.roundToInt().toString() else "%.1f".format(v)
