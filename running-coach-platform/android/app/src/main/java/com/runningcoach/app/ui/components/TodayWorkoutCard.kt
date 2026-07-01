package com.runningcoach.app.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.DirectionsRun
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Hotel
import androidx.compose.material.icons.filled.MoveDown
import androidx.compose.material.icons.filled.Route
import androidx.compose.material.icons.filled.Sick
import androidx.compose.material.icons.filled.TrendingDown
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.WarningAmber
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.runningcoach.app.data.model.CoachDecision
import com.runningcoach.app.ui.theme.ActivityHard
import com.runningcoach.app.ui.theme.ActivityTempo
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.theme.BrandGreenDeep
import com.runningcoach.app.ui.theme.FormUnknown
import com.runningcoach.app.ui.theme.RiskModerate

private data class DecisionStyle(val icon: ImageVector, val color: Color, val verb: String)

private fun styleFor(decision: String): DecisionStyle = when (decision.lowercase()) {
    "rest" -> DecisionStyle(Icons.Filled.Hotel, FormUnknown, "RIPOSO")
    "quality" -> DecisionStyle(Icons.Filled.Bolt, ActivityTempo, "QUALITÀ")
    "long" -> DecisionStyle(Icons.Filled.Route, BrandGreenDeep, "LUNGO")
    "modify" -> DecisionStyle(Icons.Filled.Tune, RiskModerate, "ADATTA")
    "caution" -> DecisionStyle(Icons.Filled.WarningAmber, ActivityHard, "ATTENZIONE")
    else -> DecisionStyle(Icons.Filled.DirectionsRun, BrandGreen, "OGGI")
}

/**
 * The dominant home card (Roadmap #1): answers "cosa devo fare oggi?" with a
 * decision, a concrete prescription, the reason, a confidence chip and an
 * expandable "Perché?" that exposes the signals, alternatives, missing data and
 * safety flags — so the recommendation is trusted, not just displayed.
 */
@Composable
fun TodayWorkoutCard(
    decision: CoachDecision,
    modifier: Modifier = Modifier,
    onAction: (String, String?) -> Unit = { _, _ -> },
    actionsEnabled: Boolean = true,
) {
    val style = styleFor(decision.decision)
    var expanded by remember { mutableStateOf(false) }

    SurfaceCard(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(52.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(style.color.copy(alpha = 0.18f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(style.icon, contentDescription = null, tint = style.color, modifier = Modifier.size(28.dp))
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "${style.verb} · ${confidenceLabel(decision.confidence)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = style.color,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    decision.headline,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                )
            }
        }

        // Coach Daily Note (Roadmap #3): short, human, motivational.
        if (decision.dailyNote.isNotBlank()) {
            Spacer(Modifier.height(10.dp))
            Text(
                decision.dailyNote,
                style = MaterialTheme.typography.bodyMedium,
                fontStyle = FontStyle.Italic,
                fontWeight = FontWeight.Medium,
                color = style.color,
            )
        }

        Spacer(Modifier.height(12.dp))
        Text(decision.prescription, style = MaterialTheme.typography.bodyMedium)

        if (decision.rationale.isNotBlank()) {
            Spacer(Modifier.height(8.dp))
            Text(
                decision.rationale,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        // Safety flags always visible (they matter most).
        if (decision.safetyFlags.isNotEmpty()) {
            Spacer(Modifier.height(10.dp))
            decision.safetyFlags.forEach { flag ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Filled.WarningAmber,
                        contentDescription = null,
                        tint = ActivityHard,
                        modifier = Modifier.size(15.dp),
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(flag, style = MaterialTheme.typography.labelMedium, color = ActivityHard)
                }
                Spacer(Modifier.height(2.dp))
            }
        }

        // ── Actions: make the card a coaching interface, not just content ──
        if (actionsEnabled) {
            Spacer(Modifier.height(14.dp))
            val pad = PaddingValues(horizontal = 8.dp, vertical = 6.dp)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ActionButton("Fatto", Icons.Filled.CheckCircle, Modifier.weight(1f), pad) {
                    onAction("done", null)
                }
                ActionButton("Riduci", Icons.Filled.TrendingDown, Modifier.weight(1f), pad) {
                    onAction("reduce", null)
                }
            }
            Spacer(Modifier.height(8.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ActionButton("Sposta", Icons.Filled.MoveDown, Modifier.weight(1f), pad) {
                    onAction("defer", null)
                }
                ActionButton("Sto male", Icons.Filled.Sick, Modifier.weight(1f), pad) {
                    onAction("problem", "tired")
                }
            }
        }

        Spacer(Modifier.height(12.dp))
        Row(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(8.dp))
                .clickable { expanded = !expanded }
                .padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                if (expanded) "Nascondi dettagli" else "Perché questa scelta?",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.primary,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.weight(1f))
            Icon(
                if (expanded) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
            )
        }

        AnimatedVisibility(visible = expanded) {
            Column {
                Spacer(Modifier.height(4.dp))
                DetailList("Segnali usati", decision.signals)
                DetailList("Alternative", decision.alternatives)
                DetailList("Dati mancanti", decision.missingData)
            }
        }
    }
}

@Composable
private fun ActionButton(
    label: String,
    icon: ImageVector,
    modifier: Modifier,
    pad: PaddingValues,
    onClick: () -> Unit,
) {
    OutlinedButton(onClick = onClick, modifier = modifier, contentPadding = pad) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(16.dp))
        Spacer(Modifier.width(6.dp))
        Text(label, style = MaterialTheme.typography.labelMedium, maxLines = 1, softWrap = false)
    }
}

@Composable
private fun DetailList(title: String, items: List<String>) {
    if (items.isEmpty()) return
    Spacer(Modifier.height(8.dp))
    Text(
        title,
        style = MaterialTheme.typography.labelMedium,
        fontWeight = FontWeight.Bold,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Spacer(Modifier.height(4.dp))
    items.forEach {
        Row {
            Text("·  ", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private fun confidenceLabel(c: String): String = when (c.lowercase()) {
    "high" -> "confidenza alta"
    "low" -> "confidenza bassa"
    else -> "confidenza media"
}
