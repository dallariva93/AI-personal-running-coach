package com.runningcoach.app.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.runningcoach.app.data.model.WhatIfResult
import com.runningcoach.app.data.repository.CoachRepository
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.theme.Coral
import kotlinx.coroutines.launch

private data class Scenario(val key: String, val label: String)

private val SCENARIOS = listOf(
    Scenario("skip_next_long", "Salto il prossimo lungo"),
    Scenario("sick_one_week", "Mi ammalo una settimana"),
    Scenario("add_training_day", "Aggiungo un giorno"),
)

/**
 * "E se…?" bottom-sheet (Roadmap A7): the athlete picks one of three what-if
 * scenarios and sees the projected before→after — race prediction delta and
 * form (TSB) at race day — with the risk notes. Read-only: the backend never
 * persists, so exploring costs nothing. Self-contained (repository-driven),
 * same pattern as DebriefSheet / HealthConnectSection.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WhatIfSheet(repository: CoachRepository, onDismiss: () -> Unit) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val scope = rememberCoroutineScope()

    var loading by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<WhatIfResult?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var selected by remember { mutableStateOf<String?>(null) }

    fun run(scenario: String) {
        selected = scenario
        loading = true
        error = null
        result = null
        scope.launch {
            runCatching { repository.planWhatIf(scenario) }
                .onSuccess { result = it; loading = false }
                .onFailure { error = it.localizedMessage ?: "Errore"; loading = false }
        }
    }

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        Column(
            Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("E se…?", style = MaterialTheme.typography.titleLarge)
            Text(
                "Simula un cambiamento sul piano. Nessuna modifica viene salvata.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            SCENARIOS.forEach { s ->
                FilledTonalButton(
                    onClick = { run(s.key) },
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !loading,
                ) { Text(if (selected == s.key && loading) "${s.label}…" else s.label) }
            }

            error?.let {
                Text("Errore: $it", color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall)
            }
            result?.let { WhatIfResultView(it) }
            Spacer(Modifier.height(8.dp))
        }
    }
}

@Composable
private fun WhatIfResultView(r: WhatIfResult) {
    // A slower prediction (positive delta) is bad → coral; faster → brand green.
    val worse = (r.raceTimeDeltaSeconds ?: 0.0) > 0.0
    val accent = if (worse) Coral else BrandGreen

    SurfaceCard {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                BeforeAfter("Previsione", r.baselineRaceTime, r.scenarioRaceTime)
            }
            r.raceTimeDeltaLabel?.let {
                Text(it, color = accent, fontWeight = FontWeight.SemiBold,
                    style = MaterialTheme.typography.labelLarge)
            }
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                BeforeAfter(
                    "Forma (TSB) alla gara",
                    "%+.0f".format(r.baselineTsbAtRace),
                    "%+.0f".format(r.scenarioTsbAtRace),
                )
            }
            if (r.riskNotes.isNotEmpty()) {
                Spacer(Modifier.height(4.dp))
                r.riskNotes.forEach { note ->
                    Text("• $note", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable
private fun BeforeAfter(label: String, before: String?, after: String?) {
    Column {
        Text(label, style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            "${before ?: "—"}  →  ${after ?: "—"}",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
        )
    }
}
