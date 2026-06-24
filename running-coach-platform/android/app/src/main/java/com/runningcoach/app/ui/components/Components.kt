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
                StatItem("ACWR", metrics.acwr?.let { fmt(it) } ?: "–")
                StatItem("7 gg", "${fmt(metrics.acuteLoadKm)} km")
                StatItem("28 gg media", "${fmt(metrics.chronicLoadKm)} km")
                StatItem(
                    "Facile",
                    metrics.easyRatio?.let { "${(it * 100).roundToInt()}%" } ?: "–",
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
