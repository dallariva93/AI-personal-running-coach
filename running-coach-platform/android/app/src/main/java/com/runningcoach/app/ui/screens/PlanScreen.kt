package com.runningcoach.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.runningcoach.app.ui.components.PhaseCard
import com.runningcoach.app.ui.components.ReportCard
import com.runningcoach.app.ui.components.ScreenTitle
import com.runningcoach.app.ui.viewmodel.OverviewUiState

@Composable
fun PlanScreen(state: OverviewUiState, onGeneratePlan: () -> Unit) {
    val ov = state.overview
    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 12.dp),
    ) {
        ScreenTitle("Piano", "Generato dall'AI dal tuo carico e stato di forma")
        Spacer(Modifier.height(16.dp))

        Button(
            onClick = onGeneratePlan,
            enabled = !state.working,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Icon(Icons.Filled.AutoAwesome, contentDescription = null, Modifier.height(18.dp))
            Spacer(Modifier.width(8.dp))
            Text("Genera piano settimanale")
        }
        if (state.working) {
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.height(18.dp), strokeWidth = 2.dp)
                Spacer(Modifier.width(8.dp))
                Text("Il coach sta pensando…", style = MaterialTheme.typography.bodySmall)
            }
        }

        ov?.plan?.let {
            Spacer(Modifier.height(16.dp))
            PhaseCard(it, ov.metrics)
        }

        Spacer(Modifier.height(16.dp))
        ReportCard("Piano settimanale", ov?.latestPlan)

        Spacer(Modifier.height(16.dp))
        ReportCard("Analisi ultima corsa", ov?.latestAnalysis)
        Spacer(Modifier.height(16.dp))
    }
}
