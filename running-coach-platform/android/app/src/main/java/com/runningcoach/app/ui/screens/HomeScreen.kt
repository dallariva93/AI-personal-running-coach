package com.runningcoach.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material.icons.outlined.Circle
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
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
import com.runningcoach.app.ui.components.TodayWorkoutCard
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
    onCoachAction: (String, String?) -> Unit = { _, _ -> },
    onOpenCoachLog: () -> Unit = {},
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

        // ── Onboarding checklist (Roadmap #4) ───────────────────────────────
        ov?.onboarding?.let { onboarding ->
            if (!onboarding.complete) {
                OnboardingCard(onboarding = onboarding)
                Spacer(Modifier.height(14.dp))
            }
        }

        if (ov != null) {
            val prIds = ov.prActivityIds.toSet()

            // ── 1. The dominant decision: what to do today ──────────────────
            if (ov.todayDecision != null) {
                TodayWorkoutCard(
                    decision = ov.todayDecision,
                    onAction = onCoachAction,
                    actionsEnabled = !state.working,
                )
            } else {
                // Fallback for an older backend without the decision engine.
                FormStateCard(ov.metrics)
            }

            Spacer(Modifier.height(14.dp))

            // ── 2. Primary actions ──────────────────────────────────────────
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

            // ── 3. Advanced metrics — progressive disclosure ────────────────
            // Front stays focused on the decision; the numbers live under a
            // single "Dettagli" toggle (Roadmap #2, home simplification).
            if (ov.todayDecision != null) {
                Spacer(Modifier.height(14.dp))
                DetailsToggle(ov, prIds)
            }

            // Coach diary entry point (Roadmap #5).
            Spacer(Modifier.height(8.dp))
            Row(
                Modifier.fillMaxWidth().clickable(onClick = onOpenCoachLog).padding(vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "Diario del coach",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.primary,
                )
                Spacer(Modifier.weight(1f))
                Icon(
                    Icons.Filled.ChevronRight,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                )
            }

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

/**
 * Collapsible "Dettagli" section holding the advanced metric cards. Keeps the
 * home focused on the decision while power users can still expand the numbers.
 */
@Composable
private fun DetailsToggle(ov: Overview, prIds: Set<Int>) {
    var expanded by remember { mutableStateOf(false) }
    Row(
        Modifier
            .fillMaxWidth()
            .clickable { expanded = !expanded }
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            if (expanded) "Nascondi dettagli" else "Mostra dettagli",
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.primary,
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
            FormStateCard(ov.metrics)

            ov.prediction?.let {
                Spacer(Modifier.height(12.dp))
                PredictionCard(it)
            }
            ov.checkin?.hrvRmssd?.let { hrv ->
                Spacer(Modifier.height(12.dp))
                HrvCard(hrv, ov.metrics.hrvStatus, ov.metrics.hrvLearning, ov.metrics.hrvDaysTracked)
            }
            ov.gamification?.let { gam ->
                if (gam.streakDays > 0 || gam.totalBadgesEarned > 0) {
                    Spacer(Modifier.height(12.dp))
                    StreakCard(gam)
                }
            }
            if (ov.personalRecords.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                PersonalRecordsCard(ov.personalRecords)
            }
            Spacer(Modifier.height(12.dp))
            WeeklyChart(ov.weekly)
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

@Composable
private fun OnboardingCard(onboarding: com.runningcoach.app.data.model.OnboardingStatus) {
    val steps = listOf(
        onboarding.connectData to "Collega i dati",
        onboarding.setGoal to "Imposta obiettivo",
        onboarding.firstCheckin to "Primo check-in",
        onboarding.generatePlan to "Genera piano",
        onboarding.firstRecommendation to "Prima raccomandazione",
    )
    val completed = steps.count { (isDone, _) -> isDone }

    androidx.compose.material3.Card(
        modifier = Modifier.fillMaxWidth(),
        colors = androidx.compose.material3.CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer,
        )
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "Configurazione in corso",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    "$completed/${steps.size}",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary
                )
            }
            Spacer(Modifier.height(12.dp))
            steps.forEach { (isDone, label) ->
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.padding(vertical = 4.dp)
                ) {
                    Icon(
                        imageVector = if (isDone) Icons.Default.CheckCircle else Icons.Outlined.Circle,
                        contentDescription = null,
                        tint = if (isDone) BrandGreen else MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.width(20.dp)
                    )
                    Spacer(Modifier.width(12.dp))
                    Text(
                        label,
                        style = MaterialTheme.typography.bodyMedium,
                        color = if (isDone) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            onboarding.nextStep?.let { next ->
                Spacer(Modifier.height(12.dp))
                val nextLabel = when (next) {
                    "connect_data" -> "Collega i dati"
                    "set_goal" -> "Imposta obiettivo"
                    "first_checkin" -> "Primo check-in"
                    "generate_plan" -> "Genera piano"
                    "first_recommendation" -> "Prima raccomandazione"
                    else -> null
                }
                nextLabel?.let {
                    Text(
                        "Prossimo passo: $it",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.SemiBold
                    )
                }
            }
        }
    }
}
