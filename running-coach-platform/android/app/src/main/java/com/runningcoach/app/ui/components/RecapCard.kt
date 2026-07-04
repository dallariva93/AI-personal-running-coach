package com.runningcoach.app.ui.components

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.runningcoach.app.data.model.RaceRecap
import com.runningcoach.app.data.model.WeeklyRecap
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.theme.BrandGreenDeep
import com.runningcoach.app.ui.theme.Coral
import com.runningcoach.app.ui.theme.CoralBright

/**
 * The in-app preview of a shareable recap (Roadmap A6). One template, two
 * variants — week (brand green) and race (coral) — matching the brief. The
 * actual shareable image is rendered separately by [RecapCardRenderer] onto a
 * bitmap; this composable is what the athlete sees before tapping "Condividi".
 */
@Composable
fun WeeklyRecapCard(recap: WeeklyRecap, modifier: Modifier = Modifier) {
    GradientCard(colors = listOf(BrandGreenDeep, BrandGreen), modifier = modifier) {
        RecapCardContent(
            eyebrow = "RIEPILOGO SETTIMANALE",
            headline = "${recap.distanceKm.formatKm()} km",
            subline = "${recap.runsCount} uscite" +
                (recap.adherencePct?.let { " · aderenza ${it.toInt()}%" } ?: ""),
            narrative = recap.narrative,
            footerLeft = recap.avgExecutionScore?.let { "Execution medio ${it.toInt()}/100" },
            footerRight = recap.bestMoment,
        )
    }
}

@Composable
fun RaceRecapCard(recap: RaceRecap, modifier: Modifier = Modifier) {
    GradientCard(colors = listOf(Coral, CoralBright), modifier = modifier) {
        RecapCardContent(
            eyebrow = "RECAP GARA",
            headline = recap.actualTime,
            subline = "${recap.distanceKm.formatKm()} km" +
                (recap.deltaLabel?.let { " · $it" } ?: ""),
            narrative = recap.narrative,
            footerLeft = recap.predictedTime?.let { "Previsto: $it" },
            footerRight = null,
        )
    }
}

@Composable
private fun RecapCardContent(
    eyebrow: String,
    headline: String,
    subline: String,
    narrative: String,
    footerLeft: String?,
    footerRight: String?,
) {
    Column {
        Text(
            eyebrow,
            style = MaterialTheme.typography.labelMedium,
            color = Color.White.copy(alpha = 0.85f),
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            headline,
            style = MaterialTheme.typography.displaySmall,
            color = Color.White,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(4.dp))
        Text(subline, style = MaterialTheme.typography.titleMedium, color = Color.White)
        if (narrative.isNotBlank()) {
            Spacer(Modifier.height(14.dp))
            Text(
                narrative,
                style = MaterialTheme.typography.bodyMedium,
                color = Color.White.copy(alpha = 0.95f),
            )
        }
        if (footerLeft != null || footerRight != null) {
            Spacer(Modifier.height(16.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                footerLeft?.let {
                    Text(it, style = MaterialTheme.typography.labelMedium,
                        color = Color.White.copy(alpha = 0.85f))
                }
                if (footerLeft != null && footerRight != null) {
                    Text("  ·  ", style = MaterialTheme.typography.labelMedium,
                        color = Color.White.copy(alpha = 0.6f))
                }
                footerRight?.let {
                    Text(it, style = MaterialTheme.typography.labelMedium,
                        color = Color.White.copy(alpha = 0.85f))
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        Text(
            "AI Running Coach",
            style = MaterialTheme.typography.labelSmall,
            color = Color.White.copy(alpha = 0.7f),
        )
    }
}

private fun Double.formatKm(): String =
    if (this == this.toLong().toDouble()) this.toLong().toString() else "%.1f".format(this)
