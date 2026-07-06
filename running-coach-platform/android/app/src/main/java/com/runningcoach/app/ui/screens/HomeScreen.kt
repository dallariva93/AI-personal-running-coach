package com.runningcoach.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
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
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.DirectionsRun
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material.icons.outlined.Circle
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.runningcoach.app.R
import com.runningcoach.app.data.model.Overview
import com.runningcoach.app.data.settings.SyncStatus
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
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Composable
fun HomeScreen(
    state: OverviewUiState,
    syncStatus: SyncStatus = SyncStatus(),
    onSync: () -> Unit,
    onOpenActivity: (Int) -> Unit = {},
    onCoachAction: (String, String?) -> Unit = { _, _ -> },
    onOpenCoachLog: () -> Unit = {},
    onOpenWeeklyRecap: () -> Unit = {},
    onOpenSettings: () -> Unit = {},
    onStartLiveRun: () -> Unit = {},
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
            ScreenTitle(
                stringResource(R.string.home_title),
                stringResource(R.string.home_subtitle),
                Modifier.weight(1f),
            )
            ov?.let {
                Column(horizontalAlignment = Alignment.End) {
                    Pill(it.mode.uppercase(), BrandGreen)
                    Spacer(Modifier.height(6.dp))
                    Pill(it.coach.uppercase(), Coral)
                }
            }
            // A8: Settings left the NavigationBar — it lives here as the gear.
            IconButton(onClick = onOpenSettings) {
                Icon(
                    Icons.Filled.Settings,
                    contentDescription = "Impostazioni",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        Spacer(Modifier.height(16.dp))

        // ── "Corri adesso col telefono" (G1): the no-hardware first path ────
        Button(onClick = onStartLiveRun, modifier = Modifier.fillMaxWidth()) {
            Icon(Icons.Filled.DirectionsRun, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("Corri adesso col telefono")
        }
        Spacer(Modifier.height(14.dp))

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

            // ── 2. Passive sync status ───────────────────────────────────────
            // Sync + analysis now run in the background (Roadmap Q2): no more
            // "Sincronizza"/"Analizza" buttons, just a quiet status line with a
            // small manual-sync escape hatch for when the athlete can't wait.
            SyncStatusRow(syncStatus = syncStatus, working = state.working, onSyncNow = onSync)
            if (state.working) {
                Spacer(Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.height(18.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(8.dp))
                    Text(stringResource(R.string.home_loading), style = MaterialTheme.typography.bodySmall)
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
                    stringResource(R.string.home_coach_diary),
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

            // Weekly recap entry point (Roadmap A6): shareable, verbalized summary.
            Row(
                Modifier.fillMaxWidth().clickable(onClick = onOpenWeeklyRecap).padding(vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    stringResource(R.string.home_weekly_recap),
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
            SectionTitle(stringResource(R.string.home_recent_runs))
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
 * Passive status line replacing the old Sincronizza/Analizza buttons
 * (Roadmap Q2): sync + analysis already run in the background, so this is
 * read-only except for a small icon that still lets the athlete force a sync
 * (the pull-to-refresh escape hatch) if they don't want to wait.
 */
@Composable
private fun SyncStatusRow(syncStatus: SyncStatus, working: Boolean, onSyncNow: () -> Unit) {
    val label = syncStatus.lastSyncAtMillis?.let { millis ->
        val time = Instant.ofEpochMilli(millis).atZone(ZoneId.systemDefault())
            .format(DateTimeFormatter.ofPattern("HH:mm"))
        if (syncStatus.newActivities > 0) {
            val newCount = pluralStringResource(
                R.plurals.new_activities_count, syncStatus.newActivities, syncStatus.newActivities,
            )
            stringResource(R.string.sync_last_with_new, time, newCount)
        } else {
            stringResource(R.string.sync_last, time)
        }
    } ?: stringResource(R.string.sync_waiting_first)

    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(
            label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f),
        )
        IconButton(onClick = onSyncNow, enabled = !working) {
            Icon(Icons.Filled.Sync, contentDescription = stringResource(R.string.sync_now_description))
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
            stringResource(if (expanded) R.string.details_hide else R.string.details_show),
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
            stringResource(R.string.home_empty_hint),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun OnboardingCard(onboarding: com.runningcoach.app.data.model.OnboardingStatus) {
    val steps = listOf(
        onboarding.connectData to stringResource(R.string.onboarding_step_connect_data),
        onboarding.setGoal to stringResource(R.string.onboarding_step_set_goal),
        onboarding.firstCheckin to stringResource(R.string.onboarding_step_first_checkin),
        onboarding.generatePlan to stringResource(R.string.onboarding_step_generate_plan),
        onboarding.firstRecommendation to stringResource(R.string.onboarding_step_first_recommendation),
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
                    stringResource(R.string.onboarding_title),
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
                        // Q7: this is the only visual cue for done/pending — the
                        // label text alone doesn't say which, so unlike a purely
                        // decorative icon this needs a real description.
                        contentDescription = stringResource(
                            if (isDone) R.string.onboarding_step_done_description
                            else R.string.onboarding_step_todo_description,
                        ),
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
                    "connect_data" -> stringResource(R.string.onboarding_step_connect_data)
                    "set_goal" -> stringResource(R.string.onboarding_step_set_goal)
                    "first_checkin" -> stringResource(R.string.onboarding_step_first_checkin)
                    "generate_plan" -> stringResource(R.string.onboarding_step_generate_plan)
                    "first_recommendation" -> stringResource(R.string.onboarding_step_first_recommendation)
                    else -> null
                }
                nextLabel?.let {
                    Text(
                        stringResource(R.string.onboarding_next_step, it),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.SemiBold
                    )
                }
            }
        }
    }
}
