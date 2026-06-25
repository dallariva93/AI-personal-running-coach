package com.runningcoach.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.runningcoach.app.data.model.Overview
import com.runningcoach.app.ui.components.ActivityRow
import com.runningcoach.app.ui.components.FormStateCard
import com.runningcoach.app.ui.components.SectionTitle
import com.runningcoach.app.ui.components.PredictionCard
import com.runningcoach.app.ui.components.WeeklyChart
import com.runningcoach.app.ui.viewmodel.OverviewUiState

@Composable
fun HomeScreen(state: OverviewUiState, onSync: () -> Unit, onAnalyze: () -> Unit) {
    val ov: Overview? = state.overview
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "Oggi",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.fillMaxWidth().weight(1f))
            ov?.let {
                AssistChip(onClick = {}, label = { Text(it.mode) })
                Spacer(Modifier.height(0.dp))
                AssistChip(onClick = {}, label = { Text(it.coach) })
            }
        }
        Spacer(Modifier.height(12.dp))

        if (ov != null) {
            FormStateCard(ov.metrics)
            ov.prediction?.let {
                Spacer(Modifier.height(12.dp))
                PredictionCard(it)
            }
            Spacer(Modifier.height(12.dp))

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = onSync, enabled = !state.working, modifier = Modifier.weight(1f)) {
                    Text("Sincronizza")
                }
                OutlinedButton(
                    onClick = onAnalyze,
                    enabled = !state.working,
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Analizza")
                }
            }
            if (state.working) {
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.height(18.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.fillMaxWidth(0.04f))
                    Text("Elaboro…", style = MaterialTheme.typography.bodySmall)
                }
            }

            Spacer(Modifier.height(16.dp))
            WeeklyChart(ov.weekly)

            Spacer(Modifier.height(16.dp))
            SectionTitle("Ultime corse")
            ov.activities.take(5).forEach { ActivityRow(it) }
        }
    }
}
