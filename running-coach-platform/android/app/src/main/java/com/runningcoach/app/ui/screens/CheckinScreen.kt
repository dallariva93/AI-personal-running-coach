package com.runningcoach.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.runningcoach.app.ui.components.SectionTitle
import com.runningcoach.app.ui.components.SurfaceCard
import com.runningcoach.app.ui.theme.ActivityHard
import com.runningcoach.app.ui.theme.ActivityTempo
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.theme.BrandGreenBright
import com.runningcoach.app.ui.viewmodel.CheckinUiState
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt

/**
 * Daily readiness check-in (handoff 1f): a 30-second morning form — sleep,
 * fatigue, soreness, motivation — that feeds the coach's readiness signal.
 *
 * Adapted from the mockup to the real [com.runningcoach.app.data.model.DailyCheckin]
 * schema: no body-part pain picker or 5-emoji energy face exist server-side
 * (only three 1-10 int levels + sleep hours), so those become labelled
 * sliders instead of chips/emoji — honest to what the backend actually
 * stores rather than UI that silently drops fields.
 */
@Composable
fun CheckinScreen(
    state: CheckinUiState,
    onBack: () -> Unit,
    onSleepChange: (Double) -> Unit,
    onFatigueChange: (Int) -> Unit,
    onSorenessChange: (Int) -> Unit,
    onMotivationChange: (Int) -> Unit,
    onSubmit: () -> Unit,
) {
    LaunchedEffect(state.submitted) {
        if (state.submitted) onBack()
    }

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
        }
        val today = LocalDate.now().format(DateTimeFormatter.ofPattern("EEE d MMM", Locale.ITALIAN))
        Text(
            today.uppercase(),
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.primary,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(2.dp))
        Text(
            "Come stai stamattina?",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
        )
        Text(
            "30 secondi per calibrare il coach sulla tua giornata.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(20.dp))

        SurfaceCard {
            SectionTitle("Sonno")
            Spacer(Modifier.height(4.dp))
            Text(
                sleepLabel(state.sleepH),
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = BrandGreen,
            )
            Slider(
                value = state.sleepH.toFloat(),
                onValueChange = { onSleepChange(it.toDouble()) },
                valueRange = 0f..12f,
                steps = 23, // quarter-hour increments
            )
        }
        Spacer(Modifier.height(12.dp))

        LevelSliderCard(
            title = "Quanto ti senti stanco/a?",
            value = state.fatigue,
            loLabel = "1 fresco",
            hiLabel = "10 esausto",
            onChange = onFatigueChange,
        )
        Spacer(Modifier.height(12.dp))

        LevelSliderCard(
            title = "Dolori muscolari",
            value = state.soreness,
            loLabel = "1 nessuno",
            hiLabel = "10 forte",
            onChange = onSorenessChange,
        )
        Spacer(Modifier.height(12.dp))

        LevelSliderCard(
            title = "Motivazione",
            value = state.motivation,
            loLabel = "1 bassa",
            hiLabel = "10 alta",
            onChange = onMotivationChange,
        )
        Spacer(Modifier.height(20.dp))

        state.error?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
            Spacer(Modifier.height(8.dp))
        }

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp)
                .clip(RoundedCornerShape(16.dp))
                .background(Brush.horizontalGradient(listOf(BrandGreen, BrandGreenBright)))
                .clickable(enabled = !state.submitting, onClick = onSubmit),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (state.submitting) {
                CircularProgressIndicator(Modifier.height(20.dp), color = Color(0xFF00210F), strokeWidth = 2.dp)
            } else {
                Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = Color(0xFF00210F))
                Spacer(Modifier.width(8.dp))
                Text("Invia check-in", color = Color(0xFF00210F), fontWeight = FontWeight.Bold)
            }
        }
        Spacer(Modifier.height(16.dp))
    }
}

/** One labelled 1-10 slider card, colored green→orange→red as the value rises. */
@Composable
private fun LevelSliderCard(
    title: String,
    value: Int,
    loLabel: String,
    hiLabel: String,
    onChange: (Int) -> Unit,
) {
    val color = when {
        value <= 3 -> BrandGreen
        value <= 6 -> ActivityTempo
        else -> ActivityHard
    }
    SurfaceCard {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            SectionTitle(title)
            Text(
                "$value/10",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = color,
            )
        }
        Slider(
            value = value.toFloat(),
            onValueChange = { onChange(it.roundToInt()) },
            valueRange = 1f..10f,
            steps = 8,
        )
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(loLabel, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(hiLabel, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** Decimal hours ("7.5") as "7h 30" for the sleep slider's headline value. */
private fun sleepLabel(hours: Double): String {
    val totalMin = (hours * 60.0).roundToInt()
    val h = totalMin / 60
    val m = totalMin % 60
    return "${h}h ${m.toString().padStart(2, '0')}"
}
