package com.runningcoach.app.ui.screens

import androidx.compose.foundation.BorderStroke
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
import com.runningcoach.app.data.model.Vo2maxHistory
import com.runningcoach.app.ui.components.ChartSeries
import com.runningcoach.app.ui.components.LineChart
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

        state.vo2maxHistory?.let { history ->
            if (history.points.isNotEmpty()) {
                Spacer(Modifier.height(24.dp))
                Vo2maxCard(history)
            }
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
        // Km totali leads (handoff 1e): the one hero stat, highlighted in
        // brand green, with the rest in a neutral tone for visual hierarchy —
        // matches the mockup instead of every tile shouting the same color.
        add("Km totali" to "${stats.totalKm} km")
        add("Corse" to "${stats.totalRuns}")
        add("Ore in corsa" to "${stats.totalDurationH} h")
        add("Dislivello tot." to "${stats.totalElevationM} m")
        if (stats.avgPace != null) add("Passo medio" to stats.avgPace)
        add("Uscita più lunga" to "${stats.longestRunKm} km")
        if (stats.fastestPace != null) add("Passo migliore" to stats.fastestPace)
    }

    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        items.chunked(2).forEachIndexed { rowIndex, row ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                row.forEachIndexed { colIndex, (label, value) ->
                    StatCard(
                        label,
                        value,
                        Modifier.weight(1f),
                        highlight = rowIndex == 0 && colIndex == 0,
                    )
                }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun Vo2maxCard(history: Vo2maxHistory) {
    val trendLabel = when (history.trend) {
        "improving" -> "In miglioramento ↑"
        "declining" -> "In calo ↓"
        "stable" -> "Stabile →"
        else -> null
    }
    val trendColor = when (history.trend) {
        "improving" -> BrandGreen
        "declining" -> androidx.compose.ui.graphics.Color(0xFFE57373)
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }

    Text("VO2max nel tempo", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
    Spacer(Modifier.height(4.dp))
    if (trendLabel != null) {
        Text(trendLabel, style = MaterialTheme.typography.labelMedium, color = trendColor)
        Spacer(Modifier.height(8.dp))
    }

    val values = history.points.map { it.vo2max.toFloat() }
    LineChart(
        series = listOf(ChartSeries(values = values, color = BrandGreen, fill = true)),
        height = 140.dp,
        minValue = (values.min() - 2f).coerceAtLeast(0f),
        maxValue = values.max() + 2f,
    )

    Spacer(Modifier.height(6.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(
            history.points.first().date,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            "%.1f ml/kg/min".format(history.points.last().vo2max),
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = BrandGreen,
        )
        Text(
            history.points.last().date,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun StatCard(label: String, value: String, modifier: Modifier = Modifier, highlight: Boolean = false) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surface,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
    ) {
        Column(Modifier.padding(16.dp)) {
            Text(
                value,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = if (highlight) BrandGreen else MaterialTheme.colorScheme.onSurface,
            )
            Spacer(Modifier.height(3.dp))
            Text(
                label,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
