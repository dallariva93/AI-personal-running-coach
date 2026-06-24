package com.runningcoach.app.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.runningcoach.app.ui.components.ReportCard
import com.runningcoach.app.ui.viewmodel.OverviewUiState

@Composable
fun PlanScreen(state: OverviewUiState, onGeneratePlan: () -> Unit) {
    val ov = state.overview
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
    ) {
        Text(
            "Piano di allenamento",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
        )
        Text(
            "Generato dall'AI in base al tuo carico e stato di forma.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(16.dp))

        Button(
            onClick = onGeneratePlan,
            enabled = !state.working,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Genera piano settimanale")
        }
        if (state.working) {
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.height(18.dp), strokeWidth = 2.dp)
                Spacer(Modifier.fillMaxWidth(0.04f))
                Text("Il coach sta pensando…", style = MaterialTheme.typography.bodySmall)
            }
        }

        Spacer(Modifier.height(16.dp))
        ReportCard("Piano settimanale", ov?.latestPlan)

        Spacer(Modifier.height(16.dp))
        ReportCard("Analisi ultima corsa", ov?.latestAnalysis)
    }
}
