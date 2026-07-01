package com.runningcoach.app.ui.screens

import androidx.compose.foundation.background
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.runningcoach.app.data.model.CoachEvent
import com.runningcoach.app.data.repository.CoachRepository
import com.runningcoach.app.ui.components.ScreenTitle
import com.runningcoach.app.ui.components.SurfaceCard
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.theme.Coral
import com.runningcoach.app.ui.theme.FormUnknown
import com.runningcoach.app.ui.theme.RiskModerate

private fun typeStyle(eventType: String): Pair<String, Color> = when (eventType) {
    "plan_adapted" -> "Adattamento" to RiskModerate
    "decision" -> "Decisione" to BrandGreen
    "action" -> "Azione" to Coral
    "execution" -> "Esecuzione" to BrandGreen
    else -> eventType to FormUnknown
}

/**
 * The coach diary (Roadmap #5): a transparent audit of every decision and
 * adaptation — what changed, when, and from which signals — for trust and debug.
 */
@Composable
fun CoachLogScreen(repository: CoachRepository, onBack: () -> Unit) {
    var events by remember { mutableStateOf<List<CoachEvent>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }

    androidx.compose.runtime.LaunchedEffect(Unit) {
        runCatching { repository.coachEvents() }
            .onSuccess { events = it; loading = false }
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
            ScreenTitle("Diario del coach", "Decisioni e adattamenti", Modifier.weight(1f))
        }

        when {
            loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                androidx.compose.material3.Text(
                    "Errore: $error",
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(24.dp),
                )
            }
            events.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                androidx.compose.material3.Text(
                    "Ancora nessuna decisione registrata. Sincronizza per iniziare.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(32.dp),
                )
            }
            else -> LazyColumn(
                Modifier.fillMaxSize().padding(horizontal = 16.dp),
                contentPadding = PaddingValues(bottom = 16.dp),
            ) {
                items(events) { ev -> EventRow(ev) }
            }
        }
    }
}

@Composable
private fun EventRow(ev: CoachEvent) {
    val (label, color) = typeStyle(ev.eventType)
    SurfaceCard(Modifier.padding(vertical = 5.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).clip(CircleShape).background(color))
            Spacer(Modifier.width(8.dp))
            androidx.compose.material3.Text(
                label.uppercase(),
                style = MaterialTheme.typography.labelSmall,
                color = color,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.weight(1f))
            androidx.compose.material3.Text(
                ev.date,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Spacer(Modifier.height(6.dp))
        androidx.compose.material3.Text(
            ev.title,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
        )
        if (ev.detail.isNotBlank() && ev.detail != ev.title) {
            Spacer(Modifier.height(2.dp))
            androidx.compose.material3.Text(
                ev.detail,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (!ev.signals.isNullOrEmpty()) {
            Spacer(Modifier.height(4.dp))
            androidx.compose.material3.Text(
                "Segnali: " + ev.signals.joinToString(", "),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
