package com.runningcoach.app.ui.screens

import android.content.Intent
import android.net.Uri
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Fullscreen
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.google.gson.JsonParser
import com.runningcoach.app.data.model.Activity
import com.runningcoach.app.ui.components.ChartStat
import com.runningcoach.app.ui.components.GradientCard
import com.runningcoach.app.ui.components.MetricAreaChart
import com.runningcoach.app.ui.components.Pill
import com.runningcoach.app.ui.components.RouteMap
import com.runningcoach.app.ui.components.SectionTitle
import com.runningcoach.app.ui.components.StackedBar
import com.runningcoach.app.ui.components.StatItem
import com.runningcoach.app.ui.components.SurfaceCard
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.theme.BrandGreenDeep
import com.runningcoach.app.ui.theme.Coral
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
    onOpenMap: (() -> Unit)? = null,
    onSaveRpe: (Int) -> Unit = {},
    onSaveNotes: (String) -> Unit = {},
    onOpenRaceRecap: (() -> Unit)? = null,
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

        // Race recap (Roadmap A6): prediction-vs-reality card, shareable.
        if (activity.activityType.lowercase() in setOf("gara", "race") && onOpenRaceRecap != null) {
            Spacer(Modifier.height(14.dp))
            Button(onClick = onOpenRaceRecap, modifier = Modifier.fillMaxWidth()) {
                Text("Vedi recap gara")
            }
        }

        // Real OSM route map right under the hero — the signature element of a
        // Garmin/Strava activity screen.
        val routePoints = remember(activity.routePolyline) { parseRoutePoints(activity.routePolyline) }
        if (routePoints.size >= 2) {
            Spacer(Modifier.height(14.dp))
            RouteMapSection(routePoints, onOpenMap = onOpenMap)
        }

        Spacer(Modifier.height(14.dp))
        PerformanceSection(activity)

        // Garmin-style per-km profiles: pace and elevation, each its own chart
        // with a stat header, labelled axes with units, and an average line.
        val splitSeconds = remember(activity.splitsKm) {
            activity.splitsKm?.map { paceToSeconds(it) }?.takeIf { secs -> secs.all { it > 0 } }
        }
        val altitude = activity.altitudeProfile?.takeIf { it.size >= 2 }
        if (splitSeconds != null && splitSeconds.size >= 2) {
            Spacer(Modifier.height(14.dp))
            PaceProfileSection(splitSeconds, distanceKm = activity.distanceKm)
        }
        if (altitude != null) {
            Spacer(Modifier.height(14.dp))
            ElevationProfileSection(altitude, distanceKm = activity.distanceKm)
        }

        activity.splitsKm?.takeIf { it.size >= 2 }?.let {
            Spacer(Modifier.height(14.dp))
            SplitsSection(splits = it, altitude = altitude)
        }

        Spacer(Modifier.height(14.dp))
        HeartRateSection(activity)

        if (activity.aerobicTrainingEffect != null || activity.anaerobicTrainingEffect != null ||
            activity.aerobicTeMessage != null || activity.anaerobicTeMessage != null
        ) {
            Spacer(Modifier.height(14.dp))
            TrainingEffectSection(activity)
        }

        Spacer(Modifier.height(14.dp))
        EnvironmentSection(activity)

        if (activity.bodyBatteryDelta != null || activity.staminaDrop != null ||
            activity.vigorousMinutes != null || activity.moderateMinutes != null
        ) {
            Spacer(Modifier.height(14.dp))
            RecoverySection(activity)
        }

        if (goalTargetPace != null && activity.avgPace != null) {
            Spacer(Modifier.height(14.dp))
            PaceComparisonSection(actualPace = activity.avgPace, targetPace = goalTargetPace)
        }

        Spacer(Modifier.height(14.dp))
        NotesSection(activity.notes, onSaveNotes)

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

/**
 * Per-km splits as a Strava-style table: km index, a relative-speed bar
 * (longer + green = faster, red = slowest), the pace, and the per-km elevation
 * delta when an aligned altitude profile is available.
 */
@Composable
private fun SplitsSection(splits: List<String>, altitude: List<Double>?) {
    val seconds = splits.map { paceToSeconds(it) }
    val valid = seconds.all { it > 0 }
    val fastestSec = if (valid) seconds.min() else 0
    val slowestSec = if (valid) seconds.max() else 0
    val showElev = altitude != null && altitude.size == splits.size
    val track = MaterialTheme.colorScheme.surfaceVariant
    val mid = MaterialTheme.colorScheme.primary.copy(alpha = 0.55f)

    SurfaceCard {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            SectionTitle("Parziali al km")
            if (valid) fastestPace(splits, seconds)?.let { Pill("best $it", BrandGreen) }
        }
        Spacer(Modifier.height(4.dp))
        splits.forEachIndexed { i, pace ->
            val sec = seconds[i]
            val frac = if (valid && sec > 0) (fastestSec.toFloat() / sec).coerceIn(0.08f, 1f) else 0.5f
            val barColor = when {
                valid && sec == fastestSec -> BrandGreen
                valid && sec == slowestSec -> Coral
                else -> mid
            }
            Row(
                Modifier.fillMaxWidth().padding(vertical = 5.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "${i + 1}",
                    modifier = Modifier.width(22.dp),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Box(
                    Modifier
                        .weight(1f)
                        .height(18.dp)
                        .clip(RoundedCornerShape(6.dp))
                        .background(track),
                ) {
                    Box(
                        Modifier
                            .fillMaxWidth(frac)
                            .height(18.dp)
                            .clip(RoundedCornerShape(6.dp))
                            .background(barColor),
                    )
                }
                Spacer(Modifier.width(10.dp))
                Text(
                    pace,
                    modifier = Modifier.width(62.dp),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                    textAlign = TextAlign.End,
                )
                if (showElev) {
                    val delta = if (i == 0) 0.0 else altitude!![i] - altitude[i - 1]
                    Spacer(Modifier.width(8.dp))
                    Text(
                        elevDelta(delta),
                        modifier = Modifier.width(48.dp),
                        style = MaterialTheme.typography.labelSmall,
                        color = when {
                            delta > 0.5 -> Coral
                            delta < -0.5 -> BrandGreen
                            else -> MaterialTheme.colorScheme.onSurfaceVariant
                        },
                        textAlign = TextAlign.End,
                    )
                }
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

/**
 * Per-km pace profile, Garmin-style: an inverted, blue filled area (faster =
 * higher) with a Media / Migliore header, a labelled pace axis and a dashed
 * average line. Built on the reusable [MetricAreaChart].
 */
@Composable
private fun PaceProfileSection(paceSeconds: List<Int>, distanceKm: Double) {
    val avg = paceSeconds.average().toFloat()
    SurfaceCard {
        MetricAreaChart(
            title = "Passo",
            values = paceSeconds.map { it.toFloat() },
            color = Zone2,
            inverted = true,
            average = avg,
            yFormatter = { secToPace(it.roundToInt()) },
            stats = listOf(
                ChartStat(secToPace(avg.roundToInt()), "/km", "Media"),
                ChartStat(secToPace(paceSeconds.min()), "/km", "Migliore"),
            ),
            xLabels = kmAxisLabels(distanceKm),
            xCaption = "Distanza (km)",
        )
    }
}

/**
 * Per-km elevation profile, Garmin-style: a green filled area with a Min / Max
 * header and a labelled metre axis. Built on the reusable [MetricAreaChart].
 */
@Composable
private fun ElevationProfileSection(altitude: List<Double>, distanceKm: Double) {
    SurfaceCard {
        MetricAreaChart(
            title = "Elevazione",
            values = altitude.map { it.toFloat() },
            color = BrandGreen,
            yFormatter = { it.roundToInt().toString() },
            stats = listOf(
                ChartStat(altitude.min().roundToInt().toString(), "m", "Min"),
                ChartStat(altitude.max().roundToInt().toString(), "m", "Max"),
            ),
            xLabels = kmAxisLabels(distanceKm),
            xCaption = "Distanza (km)",
        )
    }
}

/** Five evenly-spaced km markers "0 … total" for a chart's X axis. */
private fun kmAxisLabels(distanceKm: Double): List<String> =
    (0..4).map { j -> (j / 4.0 * distanceKm).roundToInt().toString() }

/** Real OSM map of the route (start = green dot, finish = coral dot). */
@Composable
private fun RouteMapSection(
    points: List<Pair<Double, Double>>,
    onOpenMap: (() -> Unit)? = null,
) {
    SurfaceCard {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            SectionTitle("Mappa percorso")
            if (onOpenMap != null) {
                IconButton(onClick = onOpenMap, modifier = Modifier.size(28.dp)) {
                    Icon(
                        Icons.Filled.Fullscreen,
                        contentDescription = "Apri mappa a schermo intero",
                        modifier = Modifier.size(22.dp),
                        tint = MaterialTheme.colorScheme.primary,
                    )
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        RouteMap(
            points = points,
            lineColorArgb = BrandGreen.toArgb(),
            startColorArgb = BrandGreen.toArgb(),
            endColorArgb = Coral.toArgb(),
            modifier = Modifier.clip(RoundedCornerShape(16.dp)),
            height = 240.dp,
        )
    }
}

/** Parse the stored ``[[lat, lon], ...]`` JSON into geo points. */
internal fun parseRoutePoints(routePolyline: String?): List<Pair<Double, Double>> {
    if (routePolyline.isNullOrBlank()) return emptyList()
    return try {
        JsonParser.parseString(routePolyline).asJsonArray.mapNotNull {
            val pt = it.asJsonArray
            if (pt.size() >= 2) Pair(pt[0].asDouble, pt[1].asDouble) else null
        }
    } catch (_: Exception) {
        emptyList()
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

/** Seconds-per-km → "M:SS". */
private fun secToPace(sec: Int): String = "${sec / 60}:${(sec % 60).toString().padStart(2, '0')}"

/** Per-km elevation delta as a signed metre string ("+4 m" / "−6 m" / "0 m"). */
private fun elevDelta(d: Double): String = when {
    d > 0.5 -> "+${d.roundToInt()} m"
    d < -0.5 -> "−${(-d).roundToInt()} m"
    else -> "0 m"
}
