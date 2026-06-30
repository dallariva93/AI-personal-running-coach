package com.runningcoach.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.material.icons.filled.Analytics
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.runningcoach.app.data.model.Overview
import com.runningcoach.app.ui.components.ActivityRow
import com.runningcoach.app.ui.components.FormStateCard
import com.runningcoach.app.ui.components.HrvCard
import com.runningcoach.app.ui.components.PersonalRecordsCard
import com.runningcoach.app.ui.components.Pill
import com.runningcoach.app.ui.components.PredictionCard
import com.runningcoach.app.ui.components.ScreenTitle
import com.runningcoach.app.ui.components.SectionTitle
import com.runningcoach.app.ui.components.StreakCard
import com.runningcoach.app.ui.components.WeeklyChart
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.theme.Coral
import com.runningcoach.app.ui.viewmodel.OverviewUiState

@Composable
fun HomeScreen(
    state: OverviewUiState,
    onSync: () -> Unit,
    onAnalyze: () -> Unit,
    onOpenActivity: (Int) -> Unit = {},
) {
    val ov: Overview? = state.overview
    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 12.dp),
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            ScreenTitle("Oggi", "Il tuo stato di forma in tempo reale", Modifier.weight(1f))
            ov?.let {
                Column(horizontalAlignment = Alignment.End) {
                    Pill(it.mode.uppercase(), BrandGreen)
                    Spacer(Modifier.height(6.dp))
                    Pill(it.coach.uppercase(), Coral)
                }
            }
        }
        Spacer(Modifier.height(16.dp))

        if (ov != null) {
            val prIds = ov.prActivityIds.toSet()

            FormStateCard(ov.metrics)

            ov.prediction?.let {
                Spacer(Modifier.height(12.dp))
                PredictionCard(it)
            }

            // HRV readiness card
            ov.checkin?.hrvRmssd?.let { hrv ->
                Spacer(Modifier.height(12.dp))
                HrvCard(hrv, ov.metrics.hrvStatus)
            }

            // Streak + badges (show only if at least one run exists).
            ov.gamification?.let { gam ->
                if (gam.streakDays > 0 || gam.totalBadgesEarned > 0) {
                    Spacer(Modifier.height(12.dp))
                    StreakCard(gam)
                }
            }

            // Personal records (show only when data is available).
            if (ov.personalRecords.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                PersonalRecordsCard(ov.personalRecords)
            }

            Spacer(Modifier.height(14.dp))

            // Tight content padding + single-line labels keep "Sincronizza"
            // on one line in a half-width button even on small phones.
            val actionPad = PaddingValues(horizontal = 12.dp, vertical = 10.dp)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = onSync,
                    enabled = !state.working,
                    modifier = Modifier.weight(1f),
                    contentPadding = actionPad,
                ) {
                    Icon(Icons.Filled.Sync, contentDescription = null, Modifier.height(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Sincronizza", maxLines = 1, softWrap = false)
                }
                OutlinedButton(
                    onClick = onAnalyze,
                    enabled = !state.working,
                    modifier = Modifier.weight(1f),
                    contentPadding = actionPad,
                ) {
                    Icon(Icons.Filled.Analytics, contentDescription = null, Modifier.height(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("Analizza", maxLines = 1, softWrap = false)
                }
            }
            if (state.working) {
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.height(18.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                    Text("Elaboro…", style = MaterialTheme.typography.bodySmall)
                }
            }

            Spacer(Modifier.height(18.dp))
            WeeklyChart(ov.weekly)

            Spacer(Modifier.height(18.dp))
            SectionTitle("Ultime corse")
            ov.activities.take(5).forEach { act ->
                ActivityRow(
                    activity = act,
                    isPr = act.id in prIds,
                    onClick = { onOpenActivity(act.id) },
                )
            }
            Spacer(Modifier.height(16.dp))
        } else {
            EmptyHint()
        }
    }
}

@Composable
private fun EmptyHint() {
    Column {
        Text(
            "Collega il backend in Impostazioni, poi premi Sincronizza.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
