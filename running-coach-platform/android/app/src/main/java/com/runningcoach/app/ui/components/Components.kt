package com.runningcoach.app.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.runningcoach.app.data.model.Activity
import com.runningcoach.app.data.model.PeriodizationPlan
import com.runningcoach.app.data.model.RacePrediction
import com.runningcoach.app.data.model.Report
import com.runningcoach.app.data.model.TrainingMetrics
import com.runningcoach.app.data.model.WeeklyBucket
import com.runningcoach.app.ui.theme.formColor
import kotlin.math.roundToInt

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.Bold,
        modifier = modifier.padding(vertical = 8.dp),
    )
}

@Composable
fun StatItem(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Text(label, style = MaterialTheme.typography.labelSmall, color = Color.Gray)
    }
}

@Composable
fun FormStateCard(metrics: TrainingMetrics, modifier: Modifier = Modifier) {
    val color = formColor(metrics.formState)
    Card(
        modifier = modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.size(14.dp).clip(RoundedCornerShape(50)).background(color),
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    metrics.formState.uppercase(),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = color,
                )
            }
            Spacer(Modifier.height(6.dp))
            Text(
                metrics.formExplanation.ifBlank { "Nessun dato sufficiente." },
                style = MaterialTheme.typography.bodySmall,
                color = Color.Gray,
            )
            Spacer(Modifier.height(14.dp))
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                StatItem("Forma TSB", metrics.tsb?.let { fmtSigned(it) } ?: "–")
                StatItem("Fitness", metrics.ctl?.let { fmt(it) } ?: "–")
                StatItem("Fatica", metrics.atl?.let { fmt(it) } ?: "–")
                StatItem("7 gg", "${fmt(metrics.acuteLoadKm)} km")
            }
            Spacer(Modifier.height(12.dp))
            // 80/20 distribution across the three real-intensity states.
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                StatItem("Facile", pct(metrics.easyRatio))
                StatItem("Medio", pct(metrics.moderateRatio))
                StatItem("Intenso", pct(metrics.hardRatio))
                StatItem("ACWR", metrics.acwr?.let { fmt(it) } ?: "–")
            }
            val extras = buildList {
                metrics.injuryLevel?.takeIf { it != "low" }?.let {
                    add("⚠️ rischio infortunio: ${it} (${metrics.injuryScore?.roundToInt() ?: 0})")
                }
                metrics.readinessState?.takeIf { it != "unknown" }?.let {
                    add("recupero: ${it} (${metrics.readiness?.roundToInt() ?: 0})")
                }
                metrics.efficiencyTrend?.takeIf { it != "unknown" }?.let {
                    add("efficienza: ${trendLabel(it)}")
                }
                metrics.vo2max?.let { add("VO2max ${fmt(it)}") }
            }
            if (extras.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                Text(
                    extras.joinToString("  ·  "),
                    style = MaterialTheme.typography.labelSmall,
                    color = Color.Gray,
                )
            }
        }
    }
}

/** Goal-race forecast: predicted finish + probability of the target time. */
@Composable
fun PredictionCard(prediction: RacePrediction, modifier: Modifier = Modifier) {
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            SectionTitle("Previsione gara — ${prediction.goalType}")
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                StatItem("Previsto", prediction.predictedTime ?: "–")
                StatItem("Obiettivo", prediction.targetTime ?: "–")
                StatItem(
                    "Probabilità",
                    prediction.probability?.let { "${(it * 100).roundToInt()}%" } ?: "–",
                )
                StatItem("Confidenza", prediction.confidence)
            }
            prediction.basis?.let {
                Spacer(Modifier.height(8.dp))
                Text(it, style = MaterialTheme.typography.labelSmall, color = Color.Gray)
            }
        }
    }
}

/** Periodization macrocycle: phase timeline with the current phase highlighted. */
@Composable
fun PhaseCard(plan: PeriodizationPlan, metrics: TrainingMetrics, modifier: Modifier = Modifier) {
    val primary = MaterialTheme.colorScheme.primary
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            SectionTitle("Periodizzazione — ${plan.weeksToRace} sett. alla gara")
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                plan.phases.forEach { phase ->
                    val current = phase.name == plan.currentPhase
                    Column(
                        Modifier.weight(phase.weeks.coerceAtLeast(1).toFloat()),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Box(
                            Modifier.fillMaxWidth().height(26.dp)
                                .clip(RoundedCornerShape(6.dp))
                                .background(if (current) primary else Color(0xFFD0D0D0)),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                phase.name.take(4).uppercase(),
                                style = MaterialTheme.typography.labelSmall,
                                color = if (current) Color.White else Color.DarkGray,
                                fontSize = 9.sp,
                            )
                        }
                        Text(
                            "${phase.weeks}w",
                            style = MaterialTheme.typography.labelSmall,
                            color = Color.Gray,
                            fontSize = 9.sp,
                        )
                    }
                }
            }
            metrics.phaseFocus?.let {
                Spacer(Modifier.height(10.dp))
                Text(
                    "Fase attuale: ${plan.currentPhase.uppercase()} — $it",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            metrics.phaseVolumeTargetKm?.let {
                Text(
                    "Volume target ~${fmt(it)} km",
                    style = MaterialTheme.typography.labelSmall,
                    color = Color.Gray,
                )
            }
            if (metrics.adaptiveNotes.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                Text(
                    "⚙️ " + metrics.adaptiveNotes.joinToString("; "),
                    style = MaterialTheme.typography.labelSmall,
                    color = Color.Gray,
                )
            }
        }
    }
}

@Composable
fun WeeklyChart(weekly: List<WeeklyBucket>, modifier: Modifier = Modifier) {
    val barColor = MaterialTheme.colorScheme.primary
    val maxKm = (weekly.maxOfOrNull { it.distanceKm } ?: 1.0).coerceAtLeast(1.0)
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            SectionTitle("Andamento carico settimanale")
            if (weekly.isEmpty()) {
                Text("Nessun dato.", style = MaterialTheme.typography.bodySmall, color = Color.Gray)
            } else {
                Canvas(Modifier.fillMaxWidth().height(140.dp)) {
                    val gap = 10.dp.toPx()
                    val barWidth = (size.width - gap * (weekly.size - 1)) / weekly.size
                    weekly.forEachIndexed { i, bucket ->
                        val h = (bucket.distanceKm / maxKm * size.height).toFloat()
                        val x = i * (barWidth + gap)
                        drawRoundRect(
                            color = barColor,
                            topLeft = Offset(x, size.height - h),
                            size = Size(barWidth, h),
                            cornerRadius = androidx.compose.ui.geometry.CornerRadius(8f, 8f),
                        )
                    }
                }
                Spacer(Modifier.height(6.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    weekly.forEach {
                        Text(
                            it.weekStart.drop(5),
                            style = MaterialTheme.typography.labelSmall,
                            color = Color.Gray,
                            fontSize = 9.sp,
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun ActivityRow(activity: Activity, modifier: Modifier = Modifier) {
    Card(modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Row(
            Modifier.fillMaxWidth().padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.width(70.dp)) {
                Text(
                    activity.activityType.replaceFirstChar { it.uppercase() },
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold,
                )
                Text(activity.date, style = MaterialTheme.typography.labelSmall, color = Color.Gray)
            }
            Spacer(Modifier.width(8.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                StatItem("km", fmt(activity.distanceKm))
                StatItem("min", activity.durationMin.roundToInt().toString())
                StatItem("passo", activity.avgPace ?: "–")
                StatItem("FC", activity.avgHr?.toString() ?: "–")
            }
        }
    }
}

@Composable
fun ReportCard(title: String, report: Report?, modifier: Modifier = Modifier) {
    Card(modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                SectionTitle(title)
                report?.model?.let {
                    Text(it, style = MaterialTheme.typography.labelSmall, color = Color.Gray)
                }
            }
            if (report == null) {
                Text(
                    "Ancora nessun report. Premi il pulsante per generarlo.",
                    style = MaterialTheme.typography.bodySmall,
                    color = Color.Gray,
                )
            } else {
                Text("Analisi", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                Text(report.analysis, style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(12.dp))
                Text(
                    "Prossimo allenamento",
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.bodyMedium,
                )
                Text(report.nextWorkout, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

private fun fmt(v: Double): String =
    if (v == v.roundToInt().toDouble()) v.roundToInt().toString() else "%.1f".format(v)

private fun fmtSigned(v: Double): String = (if (v >= 0) "+" else "") + v.roundToInt().toString()

private fun pct(v: Double?): String = v?.let { "${(it * 100).roundToInt()}%" } ?: "–"

private fun trendLabel(t: String): String = when (t) {
    "improving" -> "↑ migliora"
    "declining" -> "↓ cala"
    "stable" -> "→ stabile"
    else -> t
}
