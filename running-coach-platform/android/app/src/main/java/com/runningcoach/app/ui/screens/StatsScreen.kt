package com.runningcoach.app.ui.screens

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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.runningcoach.app.data.model.PeriodStats
import com.runningcoach.app.ui.components.ScreenTitle
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.viewmodel.StatsUiState

@Composable
fun StatsScreen(
    state: StatsUiState,
    onPeriodChange: (String) -> Unit,
    onExportCsv: () -> Unit,
    onExportJson: () -> Unit,
) {
    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 12.dp),
    ) {
        ScreenTitle("Statistiche", "I tuoi numeri nel tempo", Modifier.padding(bottom = 16.dp))

        // Period picker
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("month" to "Mese", "year" to "Anno", "all-time" to "Sempre").forEach { (key, label) ->
                if (state.period == key) {
                    Button(
                        onClick = { onPeriodChange(key) },
                        modifier = Modifier.weight(1f),
                    ) { Text(label, style = MaterialTheme.typography.labelSmall) }
                } else {
                    OutlinedButton(
                        onClick = { onPeriodChange(key) },
                        modifier = Modifier.weight(1f),
                    ) { Text(label, style = MaterialTheme.typography.labelSmall) }
                }
            }
        }

        Spacer(Modifier.height(20.dp))

        when {
            state.loading -> Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            state.error != null -> Text(
                state.error,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
            )
            state.stats != null -> StatsGrid(state.stats)
        }

        Spacer(Modifier.height(24.dp))

        Text(
            "Esporta dati",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(8.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(onClick = onExportCsv, modifier = Modifier.weight(1f)) {
                Text("CSV")
            }
            OutlinedButton(onClick = onExportJson, modifier = Modifier.weight(1f)) {
                Text("JSON")
            }
        }
        Spacer(Modifier.height(8.dp))
        Text(
            "Scarica tutte le tue corse in formato aperto.",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun StatsGrid(stats: PeriodStats) {
    val items = buildList {
        add("Corse" to "${stats.totalRuns}")
        add("Km totali" to "${stats.totalKm} km")
        add("Ore in corsa" to "${stats.totalDurationH} h")
        add("Dislivello tot." to "${stats.totalElevationM} m")
        if (stats.avgPace != null) add("Passo medio" to stats.avgPace)
        add("Uscita più lunga" to "${stats.longestRunKm} km")
        if (stats.fastestPace != null) add("Passo migliore" to stats.fastestPace)
    }

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        items.chunked(2).forEach { row ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                row.forEach { (label, value) ->
                    StatCard(label, value, Modifier.weight(1f))
                }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun StatCard(label: String, value: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        color = MaterialTheme.colorScheme.surfaceVariant,
        tonalElevation = 2.dp,
    ) {
        Column(Modifier.padding(14.dp)) {
            Text(
                value,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = BrandGreen,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                label,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
