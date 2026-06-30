package com.runningcoach.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.runningcoach.app.data.model.Activity
import com.runningcoach.app.data.model.PeriodizationPlan
import com.runningcoach.app.data.model.RacePrediction
import com.runningcoach.app.data.model.Report
import com.runningcoach.app.data.model.TrainingMetrics
import com.runningcoach.app.data.model.WeeklyBucket
import com.runningcoach.app.data.model.GamificationData
import com.runningcoach.app.data.model.PersonalRecord
import com.runningcoach.app.ui.theme.ActivityHard
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.theme.BrandGreenDeep
import com.runningcoach.app.ui.theme.Coral
import com.runningcoach.app.ui.theme.IntensityEasy
import com.runningcoach.app.ui.theme.IntensityHard
import com.runningcoach.app.ui.theme.IntensityModerate
import com.runningcoach.app.ui.theme.activityColor
import com.runningcoach.app.ui.theme.formColor
import kotlin.math.roundToInt

/** Headline form card: a big gauge + the key load signals + intensity mix. */
@Composable
fun FormStateCard(metrics: TrainingMetrics, modifier: Modifier = Modifier) {
    val color = formColor(metrics.formState)
    val tsb = metrics.tsb ?: 0.0
    val ringProgress = (((tsb + 30.0) / 55.0).coerceIn(0.0, 1.0)).toFloat()
    SurfaceCard(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            MetricRing(
                progress = ringProgress,
                color = color,
                label = metrics.tsb?.let { fmtSigned(it) } ?: "–",
                caption = "FORMA",
            )
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Pill(metrics.formState.uppercase(), color)
                Spacer(Modifier.height(8.dp))
                Text(
                    metrics.formExplanation.ifBlank { "Sincronizza per calcolare lo stato di forma." },
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        Spacer(Modifier.height(16.dp))
        ThinDivider()
        Spacer(Modifier.height(14.dp))

        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            StatItem("Fitness", metrics.ctl?.let { fmt(it) } ?: "–")
            StatItem("Fatica", metrics.atl?.let { fmt(it) } ?: "–")
            StatItem("ACWR", metrics.acwr?.let { fmt(it) } ?: "–")
            StatItem("7 gg", "${fmt(metrics.acuteLoadKm)} km")
        }

        Spacer(Modifier.height(16.dp))
        IntensityBar(metrics)

        val extras = buildList {
            metrics.injuryLevel?.takeIf { it != "low" }?.let {
                add("⚠ infortunio: $it")
            }
            metrics.readinessState?.takeIf { it != "unknown" }?.let {
                add("recupero: $it")
            }
            metrics.vo2max?.let { add("VO₂max ${fmt(it)}") }
        }
        if (extras.isNotEmpty()) {
            Spacer(Modifier.height(12.dp))
            Text(
                extras.joinToString("   ·   "),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/** 80/20 intensity distribution as a stacked bar with a legend. */
@Composable
private fun IntensityBar(metrics: TrainingMetrics, modifier: Modifier = Modifier) {
    val easy = (metrics.easyRatio ?: 0.0).toFloat()
    val moderate = (metrics.moderateRatio ?: 0.0).toFloat()
    val hard = (metrics.hardRatio ?: 0.0).toFloat()
    Column(modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(
                "Distribuzione intensità",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                "obiettivo 80 / 20",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Spacer(Modifier.height(8.dp))
        if (easy + moderate + hard <= 0f) {
            Text("–", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            StackedBar(
                segments = listOf(
                    easy to IntensityEasy,
                    moderate to IntensityModerate,
                    hard to IntensityHard,
                ),
            )
            Spacer(Modifier.height(8.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                LegendDot("Facile ${pct(metrics.easyRatio)}", IntensityEasy)
                LegendDot("Medio ${pct(metrics.moderateRatio)}", IntensityModerate)
                LegendDot("Intenso ${pct(metrics.hardRatio)}", IntensityHard)
            }
        }
    }
}

@Composable
private fun LegendDot(text: String, color: Color) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).clip(RoundedCornerShape(50)).background(color))
        Spacer(Modifier.width(5.dp))
        Text(text, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** Goal-race forecast as a vivid gradient hero. */
@Composable
fun PredictionCard(prediction: RacePrediction, modifier: Modifier = Modifier) {
    GradientCard(colors = listOf(BrandGreenDeep, BrandGreen), modifier = modifier) {
        Text(
            "PREVISIONE GARA · ${prediction.goalType.uppercase()}",
            style = MaterialTheme.typography.labelMedium,
            color = Color.White.copy(alpha = 0.85f),
        )
        Spacer(Modifier.height(4.dp))
        Text(
            prediction.predictedTime ?: "–",
            style = MaterialTheme.typography.displaySmall,
            color = Color.White,
        )
        Spacer(Modifier.height(12.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            HeroStat("Obiettivo", prediction.targetTime ?: "–")
            HeroStat(
                "Probabilità",
                prediction.probability?.let { "${(it * 100).roundToInt()}%" } ?: "–",
            )
            HeroStat("Confidenza", prediction.confidence.replaceFirstChar { it.uppercase() })
        }
        prediction.basis?.let {
            Spacer(Modifier.height(10.dp))
            Text(it, style = MaterialTheme.typography.labelSmall, color = Color.White.copy(alpha = 0.8f))
        }
    }
}

@Composable
private fun HeroStat(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Color.White)
        Text(label, style = MaterialTheme.typography.labelSmall, color = Color.White.copy(alpha = 0.8f))
    }
}

/** Periodization macrocycle: phase timeline with the current phase highlighted. */
@Composable
fun PhaseCard(plan: PeriodizationPlan, metrics: TrainingMetrics, modifier: Modifier = Modifier) {
    val primary = MaterialTheme.colorScheme.primary
    val idle = MaterialTheme.colorScheme.surfaceVariant
    SurfaceCard(modifier) {
        SectionTitle("Periodizzazione — ${plan.weeksToRace} sett. alla gara")
        Spacer(Modifier.height(4.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            plan.phases.forEach { phase ->
                val current = phase.name == plan.currentPhase
                Column(
                    Modifier.weight(phase.weeks.coerceAtLeast(1).toFloat()),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Box(
                        Modifier
                            .fillMaxWidth()
                            .height(30.dp)
                            .clip(RoundedCornerShape(8.dp))
                            .background(if (current) primary else idle),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            phase.name.take(4).uppercase(),
                            style = MaterialTheme.typography.labelSmall,
                            color = if (current) MaterialTheme.colorScheme.onPrimary
                            else MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Spacer(Modifier.height(3.dp))
                    Text(
                        "${phase.weeks}w",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        metrics.phaseFocus?.let {
            Spacer(Modifier.height(12.dp))
            Text(
                "Fase attuale: ${plan.currentPhase.uppercase()} — $it",
                style = MaterialTheme.typography.bodyMedium,
            )
        }
        metrics.phaseVolumeTargetKm?.let {
            Text(
                "Volume target ~${fmt(it)} km",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (metrics.adaptiveNotes.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            Text(
                "⚙ " + metrics.adaptiveNotes.joinToString("; "),
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/** Weekly load as a polished bar chart with the latest week accented. */
@Composable
fun WeeklyChart(weekly: List<WeeklyBucket>, modifier: Modifier = Modifier) {
    SurfaceCard(modifier) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            SectionTitle("Carico settimanale")
            val total = weekly.sumOf { it.distanceKm }
            Text(
                "${fmt(total)} km · 8 sett.",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Spacer(Modifier.height(8.dp))
        BarChart(
            values = weekly.map { it.distanceKm.toFloat() },
            labels = weekly.map { it.weekStart.drop(5) },
            barColor = BrandGreen,
        )
    }
}

private val activityGlyphs = mapOf(
    "easy" to "🏃", "recupero" to "🚶", "medio" to "⚡", "lungo" to "🛣️",
    "tempo" to "🔥", "intervalli" to "💥", "trail" to "⛰️", "gara" to "🏁",
)

/** Activity list row with intensity color coding, type badge and key stats. */
@Composable
fun ActivityRow(
    activity: Activity,
    modifier: Modifier = Modifier,
    isPr: Boolean = false,
    onClick: (() -> Unit)? = null,
) {
    val clickable = if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier
    val typeColor = activityColor(activity.activityType)
    SurfaceCard(modifier.padding(vertical = 5.dp).then(clickable)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            // Intensity-colored icon box.
            Box(
                Modifier
                    .size(44.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(typeColor.copy(alpha = 0.18f)),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    activityGlyphs[activity.activityType.lowercase()] ?: "🏃",
                    style = MaterialTheme.typography.titleMedium,
                )
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.width(80.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        activity.activityType.replaceFirstChar { it.uppercase() },
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.Bold,
                        color = typeColor,
                    )
                    if (isPr) {
                        Spacer(Modifier.width(5.dp))
                        Box(
                            Modifier
                                .clip(RoundedCornerShape(4.dp))
                                .background(ActivityHard.copy(alpha = 0.15f))
                                .padding(horizontal = 4.dp, vertical = 1.dp),
                        ) {
                            Text(
                                "PR",
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.ExtraBold,
                                color = ActivityHard,
                            )
                        }
                    }
                }
                Text(
                    activity.date,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.width(8.dp))
            Row(Modifier.weight(1f), horizontalArrangement = Arrangement.SpaceBetween) {
                StatItem("km", fmt(activity.distanceKm))
                StatItem("min", activity.durationMin.roundToInt().toString())
                StatItem("passo", activity.avgPace ?: "–")
                StatItem("FC", activity.avgHr?.toString() ?: "–")
            }
        }
    }
}

/** Compact streak banner: current streak + badge count. */
@Composable
fun StreakCard(gamification: GamificationData, modifier: Modifier = Modifier) {
    SurfaceCard(modifier) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            // Streak flame.
            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                Text(
                    if (gamification.streakDays > 0) "${gamification.streakDays}" else "–",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.ExtraBold,
                    color = if (gamification.streakDays >= 7) Coral else BrandGreen,
                )
                Text(
                    "giorni di fila",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            // Divider.
            Box(Modifier.size(width = 1.dp, height = 40.dp).background(MaterialTheme.colorScheme.outlineVariant))
            // Best streak.
            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                Text(
                    if (gamification.streakDaysBest > 0) "${gamification.streakDaysBest}" else "–",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.ExtraBold,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Text(
                    "record streak",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            // Divider.
            Box(Modifier.size(width = 1.dp, height = 40.dp).background(MaterialTheme.colorScheme.outlineVariant))
            // Badge count.
            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.weight(1f)) {
                Text(
                    "${gamification.totalBadgesEarned}",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.ExtraBold,
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(
                    "badge",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        // Earned badges row.
        val earned = gamification.badges.filter { it.earned }
        if (earned.isNotEmpty()) {
            Spacer(Modifier.height(12.dp))
            ThinDivider()
            Spacer(Modifier.height(10.dp))
            Text(
                "Badge sbloccati",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(6.dp))
            earned.chunked(2).forEach { pair ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    pair.forEach { badge ->
                        Box(
                            Modifier
                                .weight(1f)
                                .clip(RoundedCornerShape(8.dp))
                                .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.12f))
                                .padding(horizontal = 10.dp, vertical = 6.dp),
                        ) {
                            Text(
                                badge.label,
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.SemiBold,
                                color = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                    // Fill last row if odd count.
                    if (pair.size == 1) Spacer(Modifier.weight(1f))
                }
                Spacer(Modifier.height(6.dp))
            }
        }
    }
}

/** Grid of personal records with distance and best pace. */
@Composable
fun PersonalRecordsCard(records: List<PersonalRecord>, modifier: Modifier = Modifier) {
    if (records.isEmpty()) return
    SurfaceCard(modifier) {
        SectionTitle("Record personali")
        Spacer(Modifier.height(10.dp))
        records.chunked(2).forEach { pair ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                pair.forEach { pr ->
                    Column(
                        Modifier
                            .weight(1f)
                            .clip(RoundedCornerShape(10.dp))
                            .background(ActivityHard.copy(alpha = 0.08f))
                            .padding(10.dp),
                    ) {
                        Text(
                            pr.distance,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Text(
                            pr.pace,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.ExtraBold,
                            color = ActivityHard,
                        )
                        Text(
                            pr.date,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                if (pair.size == 1) Spacer(Modifier.weight(1f))
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}

/** Coaching report (single-run analysis or weekly plan). */
@Composable
fun ReportCard(title: String, report: Report?, modifier: Modifier = Modifier) {
    SurfaceCard(modifier) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            SectionTitle(title)
            report?.model?.let {
                Pill(it, MaterialTheme.colorScheme.primary)
            }
        }
        if (report == null) {
            Text(
                "Ancora nessun report. Premi il pulsante per generarlo.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            Spacer(Modifier.height(4.dp))
            Text("Analisi", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(2.dp))
            Text(report.analysis, style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.height(14.dp))
            Text("Prossimo allenamento", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(2.dp))
            Text(report.nextWorkout, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

/** HRV RMSSD readiness card: big value + status pill + explanation. */
@Composable
fun HrvCard(hrvRmssd: Double, hrvStatus: String?, modifier: Modifier = Modifier) {
    val (color, label, explanation) = when (hrvStatus) {
        "high" -> Triple(BrandGreen, "HRV ALTO", "Ottimo recupero: il tuo sistema nervoso è riposato, puoi spingere oggi.")
        "low" -> Triple(Coral, "HRV BASSO", "Recupero insufficiente: allenamento leggero o riposo consigliato.")
        else -> Triple(IntensityModerate, "HRV NORMALE", "Recupero nella norma: allenamento moderato ok.")
    }
    SurfaceCard(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            // Big HRV value
            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.width(72.dp)) {
                Text(
                    text = "${hrvRmssd.roundToInt()}",
                    style = MaterialTheme.typography.headlineMedium,
                    color = color,
                    fontWeight = FontWeight.Bold,
                )
                Text("ms RMSSD", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Pill(label, color)
                Spacer(Modifier.height(8.dp))
                Text(explanation, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

// ── formatting helpers ───────────────────────────────────────────────────────
private fun fmt(v: Double): String =
    if (v == v.roundToInt().toDouble()) v.roundToInt().toString() else "%.1f".format(v)

private fun fmtSigned(v: Double): String = (if (v >= 0) "+" else "") + v.roundToInt().toString()

private fun pct(v: Double?): String = v?.let { "${(it * 100).roundToInt()}%" } ?: "–"
