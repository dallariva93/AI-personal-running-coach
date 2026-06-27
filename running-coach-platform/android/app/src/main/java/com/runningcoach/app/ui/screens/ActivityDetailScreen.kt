package com.runningcoach.app.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.OpenInBrowser
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.google.gson.JsonParser
import com.runningcoach.app.data.model.Activity
import com.runningcoach.app.ui.components.BarChart
import com.runningcoach.app.ui.components.GradientCard
import com.runningcoach.app.ui.components.Pill
import com.runningcoach.app.ui.components.SectionTitle
import com.runningcoach.app.ui.components.StackedBar
import com.runningcoach.app.ui.components.StatItem
import com.runningcoach.app.ui.components.SurfaceCard
import com.runningcoach.app.ui.components.ThinDivider
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.theme.BrandGreenDeep
import com.runningcoach.app.ui.theme.Zone1
import com.runningcoach.app.ui.theme.Zone2
import com.runningcoach.app.ui.theme.Zone3
import com.runningcoach.app.ui.theme.Zone4
import com.runningcoach.app.ui.theme.Zone5
import kotlin.math.roundToInt

/**
 * Full per-activity detail. Renders every metric the backend exposes for a run,
 * grouped into modular sections (performance, heart rate, training effect,
 * splits, environment, recovery). Adding a future metric is a new row/section —
 * the data already flows through [Activity].
 */
@Composable
fun ActivityDetailScreen(
    activity: Activity?,
    goalTargetPace: String? = null,
    onBack: () -> Unit,
    onSaveRpe: (Int) -> Unit = {},
    onSaveNotes: (String) -> Unit = {},
) {
    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Indietro")
            }
            Spacer(Modifier.size(4.dp))
            Text(
                "Dettaglio attività",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
            )
        }
        Spacer(Modifier.height(12.dp))

        if (activity == null) {
            Text(
                "Attività non trovata.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            return@Column
        }

        HeroHeader(activity, onSaveRpe)

        Spacer(Modifier.height(14.dp))
        PerformanceSection(activity)

        Spacer(Modifier.height(14.dp))
        HeartRateSection(activity)

        if (activity.aerobicTrainingEffect != null || activity.anaerobicTrainingEffect != null ||
            activity.aerobicTeMessage != null || activity.anaerobicTeMessage != null
        ) {
            Spacer(Modifier.height(14.dp))
            TrainingEffectSection(activity)
        }

        activity.splitsKm?.takeIf { it.size >= 2 }?.let {
            Spacer(Modifier.height(14.dp))
            SplitsSection(it)
        }

        Spacer(Modifier.height(14.dp))
        EnvironmentSection(activity)

        if (activity.bodyBatteryDelta != null || activity.staminaDrop != null ||
            activity.vigorousMinutes != null || activity.moderateMinutes != null
        ) {
            Spacer(Modifier.height(14.dp))
            RecoverySection(activity)
        }

        Spacer(Modifier.height(14.dp))
        NotesSection(activity.notes, onSaveNotes)

        if (goalTargetPace != null && activity.avgPace != null) {
            Spacer(Modifier.height(14.dp))
            PaceComparisonSection(actualPace = activity.avgPace, targetPace = goalTargetPace)
        }

        activity.altitudeProfile?.takeIf { it.size >= 2 }?.let {
            Spacer(Modifier.height(14.dp))
            ElevationProfileSection(it)
        }

        if (activity.routePolyline != null || activity.garminActivityId != null) {
            Spacer(Modifier.height(14.dp))
            GpsMapSection(
                routePolyline = activity.routePolyline,
                garminActivityId = activity.garminActivityId,
            )
        }

        activity.garminActivityId?.let { gid ->
            Spacer(Modifier.height(14.dp))
            GarminLinkSection(gid)
        }

        Spacer(Modifier.height(16.dp))
    }
}

@Composable
private fun HeroHeader(a: Activity, onSaveRpe: (Int) -> Unit) {
    var showRpeDialog by remember { mutableStateOf(false) }

    GradientCard(colors = listOf(BrandGreenDeep, BrandGreen)) {
        Text(
            "${a.activityType.uppercase()} · ${a.date}",
            style = MaterialTheme.typography.labelMedium,
            color = Color.White.copy(alpha = 0.85f),
        )
        Spacer(Modifier.height(4.dp))
        Text(
            "${fmt(a.distanceKm)} km",
            style = MaterialTheme.typography.displaySmall,
            color = Color.White,
        )
        Spacer(Modifier.height(12.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            HeroStat("Durata", "${a.durationMin.roundToInt()} min")
            HeroStat("Passo", a.avgPace ?: "–")
            HeroStat("FC media", a.avgHr?.let { "$it" } ?: "–")
            // RPE chip — tap to edit
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.padding(0.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        a.rpe?.let { "$it/10" } ?: "–",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Color.White,
                    )
                    Spacer(Modifier.size(2.dp))
                    IconButton(
                        onClick = { showRpeDialog = true },
                        modifier = Modifier.size(20.dp),
                    ) {
                        Icon(
                            Icons.Filled.Edit,
                            contentDescription = "Modifica RPE",
                            tint = Color.White.copy(alpha = 0.8f),
                            modifier = Modifier.size(14.dp),
                        )
                    }
                }
                Text("RPE", style = MaterialTheme.typography.labelSmall, color = Color.White.copy(alpha = 0.8f))
            }
        }
    }

    if (showRpeDialog) {
        RpeEditDialog(
            current = a.rpe,
            onConfirm = { rpe ->
                onSaveRpe(rpe)
                showRpeDialog = false
            },
            onDismiss = { showRpeDialog = false },
        )
    }
}

@Composable
private fun HeroStat(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Color.White)
        Text(label, style = MaterialTheme.typography.labelSmall, color = Color.White.copy(alpha = 0.8f))
    }
}

@Composable
private fun PerformanceSection(a: Activity) {
    SurfaceCard {
        SectionTitle("Performance")
        MetricGrid(
            buildList {
                a.vo2max?.let { add("VO₂max" to fmt(it)) }
                a.garminTrainingLoad?.let { add("Carico" to fmt(it)) }
                a.avgCadence?.let { add("Cadenza" to "$it spm") }
                a.maxHr?.let { add("FC max" to "$it bpm") }
                a.avgGradeAdjustedPace?.let { add("GAP" to it) }
                a.fastestSplit1k?.let { add("1 km veloce" to it) }
                a.fastestSplit5k?.let { add("5 km veloce" to it) }
                a.elevationGainM?.let { add("D+" to "${it.roundToInt()} m") }
            },
        )
    }
}

@Composable
private fun HeartRateSection(a: Activity) {
    SurfaceCard {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            SectionTitle("Frequenza cardiaca")
            Text(
                "media ${a.avgHr ?: "–"} · max ${a.maxHr ?: "–"} bpm",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        val zones = a.hrZones
        if (zones.isNullOrEmpty()) {
            Spacer(Modifier.height(4.dp))
            Text(
                "Distribuzione zone non disponibile per questa corsa.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            val colors = listOf(Zone1, Zone2, Zone3, Zone4, Zone5)
            val minutes = (1..5).map { zones["z$it"] ?: 0.0 }
            Spacer(Modifier.height(8.dp))
            StackedBar(segments = minutes.mapIndexed { i, v -> v.toFloat() to colors[i] })
            Spacer(Modifier.height(10.dp))
            minutes.forEachIndexed { i, v ->
                if (v > 0.0) ZoneRow("Z${i + 1}", v, colors[i])
            }
        }
    }
}

@Composable
private fun ZoneRow(name: String, minutes: Double, color: Color) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(10.dp).clip(RoundedCornerShape(50)).background(color))
        Spacer(Modifier.size(8.dp))
        Text(name, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.size(8.dp))
        Text(
            "${fmt(minutes)} min",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun TrainingEffectSection(a: Activity) {
    SurfaceCard {
        SectionTitle("Effetto allenante")
        a.aerobicTrainingEffect?.let {
            Spacer(Modifier.height(4.dp))
            TrainingEffectBar("Aerobico", it, humanizeTe(a.aerobicTeMessage))
        }
        a.anaerobicTrainingEffect?.let {
            Spacer(Modifier.height(12.dp))
            TrainingEffectBar("Anaerobico", it, humanizeTe(a.anaerobicTeMessage))
        }
        // If only the textual messages are present (no numeric TE), still show them.
        if (a.aerobicTrainingEffect == null && a.anaerobicTrainingEffect == null) {
            humanizeTe(a.aerobicTeMessage)?.let {
                Text("Aerobico: $it", style = MaterialTheme.typography.bodyMedium)
            }
            humanizeTe(a.anaerobicTeMessage)?.let {
                Spacer(Modifier.height(4.dp))
                Text("Anaerobico: $it", style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

/** Garmin training-effect gauge on the 0–5 scale with a colored fill. */
@Composable
private fun TrainingEffectBar(label: String, value: Double, caption: String?) {
    val v = value.coerceIn(0.0, 5.0)
    val color = teColor(v)
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
        Text("${fmt(v)} / 5", style = MaterialTheme.typography.labelLarge, color = color, fontWeight = FontWeight.Bold)
    }
    Spacer(Modifier.height(6.dp))
    Box(
        Modifier
            .fillMaxWidth()
            .height(10.dp)
            .clip(RoundedCornerShape(50))
            .background(MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Box(
            Modifier
                .fillMaxWidth((v / 5.0).toFloat())
                .height(10.dp)
                .clip(RoundedCornerShape(50))
                .background(color),
        )
    }
    caption?.let {
        Spacer(Modifier.height(4.dp))
        Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun SplitsSection(splits: List<String>) {
    val seconds = splits.map { paceToSeconds(it) }
    val valid = seconds.all { it > 0 }
    SurfaceCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            SectionTitle("Parziali al km")
            fastestPace(splits, seconds)?.let { Pill("best $it", BrandGreen) }
        }
        if (valid && splits.size >= 2) {
            val slowest = seconds.max()
            // Taller bar = faster split (slowest..fastest inverted), so the chart
            // reads like a effort profile rather than raw time.
            val values = seconds.map { (slowest - it + 1).toFloat() }
            Spacer(Modifier.height(8.dp))
            BarChart(
                values = values,
                labels = splits.indices.map { (it + 1).toString() },
                barColor = BrandGreen,
                highlightLast = false,
                height = 120.dp,
            )
            Spacer(Modifier.height(8.dp))
            ThinDivider()
            Spacer(Modifier.height(8.dp))
        }
        splits.forEachIndexed { i, pace ->
            Row(
                Modifier.fillMaxWidth().padding(vertical = 3.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("km ${i + 1}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(pace, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun EnvironmentSection(a: Activity) {
    SurfaceCard {
        SectionTitle("Ambiente & dislivello")
        MetricGrid(
            buildList {
                a.temperatureC?.let { add("Temp." to "${fmt(it)}°C") }
                a.humidityPct?.let { add("Umidità" to "${it.roundToInt()}%") }
                a.elevationGainM?.let { add("D+" to "${it.roundToInt()} m") }
                a.elevationLossM?.let { add("D−" to "${it.roundToInt()} m") }
            },
        )
    }
}

@Composable
private fun RecoverySection(a: Activity) {
    SurfaceCard {
        SectionTitle("Recupero & intensità")
        MetricGrid(
            buildList {
                a.bodyBatteryDelta?.let { add("Body Battery" to fmtSigned(it.toDouble())) }
                a.staminaDrop?.let { add("Stamina usata" to "${it.roundToInt()}%") }
                a.vigorousMinutes?.let { add("Min. intensi" to fmt(it)) }
                a.moderateMinutes?.let { add("Min. moderati" to fmt(it)) }
            },
        )
    }
}

/** Lays out (label, value) pairs in tidy rows of three. */
@Composable
private fun MetricGrid(items: List<Pair<String, String>>) {
    if (items.isEmpty()) {
        Text(
            "Nessun dato avanzato per questa attività.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        return
    }
    Column(Modifier.fillMaxWidth()) {
        items.chunked(3).forEach { row ->
            Row(
                Modifier.fillMaxWidth().padding(vertical = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                row.forEach { (label, value) ->
                    StatItem(label, value, Modifier.weight(1f))
                }
                repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
    }
}

@Composable
private fun ElevationProfileSection(profile: List<Double>) {
    SurfaceCard {
        SectionTitle("Profilo altimetrico")
        Spacer(Modifier.height(8.dp))
        val green = BrandGreen
        val greenFill = BrandGreen.copy(alpha = 0.2f)
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .height(100.dp),
        ) {
            val minAlt = profile.min().toFloat()
            val maxAlt = profile.max().toFloat()
            val range = (maxAlt - minAlt).coerceAtLeast(1f)
            val step = size.width / (profile.size - 1).coerceAtLeast(1)
            val pts = profile.mapIndexed { i, alt ->
                Offset(
                    x = i * step,
                    y = size.height - (alt.toFloat() - minAlt) / range * size.height * 0.9f,
                )
            }
            val fill = Path().apply {
                moveTo(pts.first().x, size.height)
                pts.forEach { lineTo(it.x, it.y) }
                lineTo(pts.last().x, size.height)
                close()
            }
            drawPath(fill, color = greenFill)
            for (i in 0 until pts.size - 1) {
                drawLine(green, pts[i], pts[i + 1], strokeWidth = 3f)
            }
        }
        Spacer(Modifier.height(6.dp))
        Text(
            "${profile.min().roundToInt()} m – ${profile.max().roundToInt()} m",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun GpsMapSection(routePolyline: String?, garminActivityId: String?) {
    SurfaceCard {
        SectionTitle("Mappa GPS")
        Spacer(Modifier.height(8.dp))
        if (routePolyline != null) {
            val points = try {
                val arr = JsonParser.parseString(routePolyline).asJsonArray
                arr.mapNotNull {
                    val pt = it.asJsonArray
                    if (pt.size() >= 2) Pair(pt[0].asFloat, pt[1].asFloat) else null
                }
            } catch (_: Exception) {
                emptyList()
            }
            if (points.size >= 2) {
                val green = BrandGreen
                Canvas(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(180.dp),
                ) {
                    val lats = points.map { it.first }
                    val lons = points.map { it.second }
                    val minLat = lats.min(); val maxLat = lats.max()
                    val minLon = lons.min(); val maxLon = lons.max()
                    val span = maxOf(maxLat - minLat, maxLon - minLon).coerceAtLeast(0.0001f)
                    val offsets = points.map { (lat, lon) ->
                        Offset(
                            x = (lon - minLon) / span * size.width * 0.9f + size.width * 0.05f,
                            y = size.height - (lat - minLat) / span * size.height * 0.9f - size.height * 0.05f,
                        )
                    }
                    for (i in 0 until offsets.size - 1) {
                        drawLine(green, offsets[i], offsets[i + 1], strokeWidth = 4f)
                    }
                    drawCircle(Color.Green, radius = 10f, center = offsets.first())
                    drawCircle(Color.Red, radius = 10f, center = offsets.last())
                }
                return@SurfaceCard
            }
        }
        Text(
            "Traccia GPS non disponibile per questa attività.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun GarminLinkSection(garminActivityId: String) {
    val context = LocalContext.current
    SurfaceCard {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                SectionTitle("Garmin Connect")
                Text(
                    "Apri l'attività completa su Garmin Connect.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            OutlinedButton(
                onClick = {
                    val url = "https://connect.garmin.com/modern/activity/$garminActivityId"
                    context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                },
            ) {
                Icon(Icons.Filled.OpenInBrowser, contentDescription = null, Modifier.size(16.dp))
                Spacer(Modifier.size(4.dp))
                Text("Apri")
            }
        }
    }
}

// ── editable sections ────────────────────────────────────────────────────────

@Composable
private fun RpeEditDialog(current: Int?, onConfirm: (Int) -> Unit, onDismiss: () -> Unit) {
    var sliderValue by remember { mutableFloatStateOf((current ?: 5).toFloat()) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Sforzo percepito (RPE)") },
        text = {
            Column {
                Text(
                    "RPE ${sliderValue.toInt()} / 10",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                )
                Spacer(Modifier.height(8.dp))
                Slider(
                    value = sliderValue,
                    onValueChange = { sliderValue = it },
                    valueRange = 1f..10f,
                    steps = 8, // 9 intervals → steps = 8
                )
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("1 – Facilissimo", style = MaterialTheme.typography.labelSmall)
                    Text("10 – Massimale", style = MaterialTheme.typography.labelSmall)
                }
            }
        },
        confirmButton = {
            Button(onClick = { onConfirm(sliderValue.toInt()) }) { Text("Salva") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Annulla") }
        },
    )
}

@Composable
private fun NotesSection(initialNotes: String?, onSave: (String) -> Unit) {
    var editing by remember { mutableStateOf(false) }
    var draft by remember(initialNotes) { mutableStateOf(initialNotes ?: "") }
    val focusManager = LocalFocusManager.current

    SurfaceCard {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            SectionTitle("Note")
            IconButton(onClick = { editing = !editing }, modifier = Modifier.size(24.dp)) {
                Icon(
                    Icons.Filled.Edit,
                    contentDescription = "Modifica note",
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(18.dp),
                )
            }
        }
        if (editing) {
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = draft,
                onValueChange = { draft = it },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("Aggiungi note sulla corsa…") },
                minLines = 2,
                maxLines = 6,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = { focusManager.clearFocus() }),
            )
            Spacer(Modifier.height(8.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                TextButton(onClick = {
                    draft = initialNotes ?: ""
                    editing = false
                }) { Text("Annulla") }
                Spacer(Modifier.size(8.dp))
                Button(onClick = {
                    onSave(draft)
                    editing = false
                }) { Text("Salva") }
            }
        } else if (draft.isNotBlank()) {
            Spacer(Modifier.height(4.dp))
            Text(draft, style = MaterialTheme.typography.bodyMedium)
        } else {
            Spacer(Modifier.height(4.dp))
            Text(
                "Nessuna nota. Tocca la matita per aggiungerne una.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun PaceComparisonSection(actualPace: String, targetPace: String) {
    val actualSec = paceToSeconds(actualPace)
    val targetSec = paceToSeconds(targetPace)
    val diffSec = targetSec - actualSec // positive = faster than target
    val (diffText, diffColor) = when {
        actualSec <= 0 || targetSec <= 0 -> "–" to MaterialTheme.colorScheme.onSurfaceVariant
        diffSec > 5 -> "+${diffSec}s/km più veloce" to BrandGreen
        diffSec < -5 -> "${-diffSec}s/km più lento" to MaterialTheme.colorScheme.error
        else -> "In linea con l'obiettivo" to BrandGreen
    }
    SurfaceCard {
        SectionTitle("Confronto passo obiettivo")
        Spacer(Modifier.height(8.dp))
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    actualPace,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                )
                Text("Passo effettivo", style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    targetPace,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                )
                Text("Passo gara obiettivo", style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Spacer(Modifier.height(8.dp))
        Text(diffText, style = MaterialTheme.typography.bodyMedium, color = diffColor)
    }
}

// ── helpers ──────────────────────────────────────────────────────────────────

private fun teColor(v: Double): Color = when {
    v >= 5.0 -> Zone5
    v >= 4.0 -> Zone4
    v >= 3.0 -> Zone3
    v >= 2.0 -> Zone2
    else -> Zone1
}

/** "M:SS/km" -> seconds; 0 when unparseable. */
private fun paceToSeconds(pace: String): Int {
    val core = pace.substringBefore("/").trim()
    val parts = core.split(":")
    if (parts.size != 2) return 0
    val m = parts[0].toIntOrNull() ?: return 0
    val s = parts[1].toIntOrNull() ?: return 0
    return m * 60 + s
}

private fun fastestPace(splits: List<String>, seconds: List<Int>): String? {
    val idx = seconds.indices.filter { seconds[it] > 0 }.minByOrNull { seconds[it] } ?: return null
    return splits[idx]
}

/** Turn Garmin's "IMPROVING_LACTATE_THRESHOLD_31" codes into readable Italian. */
private fun humanizeTe(raw: String?): String? {
    if (raw.isNullOrBlank()) return null
    val body = raw.trim().trimEnd('_', ' ').replace(Regex("_\\d+$"), "")
    val text = when {
        body.startsWith("NO_") -> "nessun beneficio"
        body.startsWith("RECOVERY") -> "recupero"
        body.startsWith("MAINTAINING") -> "mantenimento"
        body.startsWith("MINOR") -> "beneficio minore"
        body.startsWith("HIGHLY_IMPROVING") -> "forte miglioramento"
        body.startsWith("IMPROVING") -> "in miglioramento"
        body.startsWith("OVERREACHING") -> "sovraccarico"
        else -> body.lowercase().replace('_', ' ')
    }
    val focus = when {
        body.contains("VO2MAX") -> " VO₂max"
        body.contains("LACTATE_THRESHOLD") -> " soglia lattacida"
        body.contains("ANAEROBIC_CAPACITY") -> " capacità anaerobica"
        body.contains("BASE") -> " base aerobica"
        else -> ""
    }
    return (text + focus).trim()
}

private fun fmt(v: Double): String =
    if (v == v.roundToInt().toDouble()) v.roundToInt().toString() else "%.1f".format(v)

private fun fmtSigned(v: Double): String = (if (v >= 0) "+" else "") + v.roundToInt().toString()
