package com.runningcoach.app.ui.screens

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.Landscape
import androidx.compose.material.icons.filled.NightsStay
import androidx.compose.material.icons.filled.Park
import androidx.compose.material.icons.filled.Speed
import androidx.compose.material.icons.filled.SportsScore
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.runningcoach.app.data.model.PlanGenerateRequest
import com.runningcoach.app.data.model.PlanSession
import com.runningcoach.app.data.model.PlanWeek
import com.runningcoach.app.data.model.TrainingPlan
import com.runningcoach.app.ui.components.Pill
import com.runningcoach.app.ui.components.ScreenTitle
import com.runningcoach.app.ui.components.SurfaceCard
import com.runningcoach.app.ui.components.ThinDivider
import com.runningcoach.app.ui.theme.BrandGreen
import com.runningcoach.app.ui.theme.Coral
import com.runningcoach.app.ui.viewmodel.PlanUiState

// ─────────────────────────────────────────────────────────────────────────────
// Session-type palette
// ─────────────────────────────────────────────────────────────────────────────

private val SessionEasy = BrandGreen             // #00C16E
private val SessionLong = Color(0xFF2196F3)       // blue
private val SessionTempo = Color(0xFFFF6D00)      // deep orange
private val SessionIntervals = Coral              // coral / red
private val SessionRest = Color(0xFF9E9E9E)       // grey
private val SessionRace = Color(0xFF7C4DFF)       // purple
private val SessionCross = Color(0xFF00BCD4)      // teal
private val SessionStrides = Color(0xFFFFAB40)    // light orange

private fun sessionColor(type: String): Color = when (type.lowercase()) {
    "easy" -> SessionEasy
    "long" -> SessionLong
    "tempo" -> SessionTempo
    "intervals" -> SessionIntervals
    "rest" -> SessionRest
    "race" -> SessionRace
    "cross" -> SessionCross
    "strides" -> SessionStrides
    else -> SessionRest
}

private fun sessionIcon(type: String): ImageVector = when (type.lowercase()) {
    "easy" -> Icons.Filled.Park
    "long" -> Icons.Filled.Landscape
    "tempo" -> Icons.Filled.Speed
    "intervals" -> Icons.Filled.Timer
    "rest" -> Icons.Filled.NightsStay
    "race" -> Icons.Filled.SportsScore
    "cross" -> Icons.Filled.FitnessCenter
    "strides" -> Icons.Filled.Speed
    else -> Icons.Filled.NightsStay
}

private val ITA_DAYS = listOf("Dom", "Lun", "Mar", "Mer", "Gio", "Ven", "Sab")

private fun dayLabel(dayOfWeek: Int): String = ITA_DAYS.getOrElse(dayOfWeek) { "?" }

private fun goalTypeLabel(goalType: String): String = when (goalType.lowercase()) {
    "marathon" -> "Maratona"
    "half", "half_marathon" -> "Mezza Maratona"
    "10k" -> "10 km"
    "5k" -> "5 km"
    "general" -> "Generale"
    else -> goalType.replaceFirstChar { it.uppercase() }
}

private fun phaseLabel(phase: String): String = when (phase.lowercase()) {
    "base" -> "Base"
    "build" -> "Sviluppo"
    "specifico", "peak", "specific" -> "Specifico"
    "taper" -> "Taper"
    "race", "gara" -> "Gara"
    else -> phase.replaceFirstChar { it.uppercase() }
}

// ─────────────────────────────────────────────────────────────────────────────
// Root composable
// ─────────────────────────────────────────────────────────────────────────────

@Composable
fun PlanScreen(
    state: PlanUiState,
    onGeneratePlan: (PlanGenerateRequest) -> Unit,
    onToggleSession: (Int) -> Unit,
    onArchivePlan: (Int) -> Unit,
    onShowGenerateDialog: () -> Unit,
    onDismissDialog: () -> Unit,
) {
    Box(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        if (state.loading && state.plan == null) {
            CircularProgressIndicator(Modifier.align(Alignment.Center))
        } else {
            Column(
                Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 12.dp),
            ) {
                ScreenTitle(
                    "Piano",
                    if (state.plan != null) "Il tuo piano multi-settimana"
                    else "Nessun piano attivo",
                )
                Spacer(Modifier.height(16.dp))

                val plan = state.plan
                if (plan == null) {
                    EmptyPlanCard(onShowGenerateDialog)
                } else {
                    RaceCountdownCard(plan)
                    Spacer(Modifier.height(12.dp))
                    CurrentWeekCard(plan, onToggleSession)
                    Spacer(Modifier.height(12.dp))
                    FullPlanView(plan, onToggleSession)
                    Spacer(Modifier.height(16.dp))
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        OutlinedButton(
                            onClick = onShowGenerateDialog,
                            modifier = Modifier.weight(1f),
                        ) { Text("Nuovo piano") }
                        OutlinedButton(
                            onClick = { onArchivePlan(plan.id) },
                            modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.outlinedButtonColors(
                                contentColor = MaterialTheme.colorScheme.error,
                            ),
                        ) { Text("Archivia") }
                    }
                }
                Spacer(Modifier.height(24.dp))
            }
        }
    }

    if (state.showGenerateDialog) {
        GeneratePlanDialog(
            onGenerate = onGeneratePlan,
            onDismiss = onDismissDialog,
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Empty state
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun EmptyPlanCard(onGenerate: () -> Unit) {
    SurfaceCard {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(vertical = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(
                Icons.Filled.CalendarMonth,
                contentDescription = null,
                modifier = Modifier.size(56.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(12.dp))
            Text(
                "Nessun piano attivo",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                "Genera un piano personalizzato in base al tuo obiettivo e livello.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(20.dp))
            Button(onClick = onGenerate) {
                Icon(Icons.Filled.Add, contentDescription = null)
                Spacer(Modifier.width(6.dp))
                Text("Genera piano")
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Race countdown hero card (sticky top)
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun RaceCountdownCard(plan: TrainingPlan) {
    SurfaceCard {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Pill(text = goalTypeLabel(plan.goalType), color = BrandGreen)
                Spacer(Modifier.height(6.dp))
                Text(
                    plan.goalDate,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    "${plan.weeksRemaining} settimane alla gara",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    "Settimana ${plan.currentWeekNumber} di ${plan.weeksTotal}",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    "${(plan.overallCompletionPct * 100).toInt()}%",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = BrandGreen,
                )
            }
        }
        Spacer(Modifier.height(12.dp))
        LinearProgressIndicator(
            progress = { plan.overallCompletionPct.toFloat().coerceIn(0f, 1f) },
            modifier = Modifier
                .fillMaxWidth()
                .height(6.dp)
                .clip(RoundedCornerShape(3.dp)),
            color = BrandGreen,
            trackColor = MaterialTheme.colorScheme.surfaceVariant,
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Current week card
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun CurrentWeekCard(plan: TrainingPlan, onToggleSession: (Int) -> Unit) {
    val currentWeek = plan.currentWeek ?: return
    SurfaceCard {
        WeekHeader(currentWeek, isCurrent = true)
        Spacer(Modifier.height(10.dp))
        LinearProgressIndicator(
            progress = { currentWeek.completionPct.toFloat().coerceIn(0f, 1f) },
            modifier = Modifier
                .fillMaxWidth()
                .height(4.dp)
                .clip(RoundedCornerShape(2.dp)),
            color = BrandGreen,
            trackColor = MaterialTheme.colorScheme.surfaceVariant,
        )
        Spacer(Modifier.height(10.dp))
        currentWeek.sessions.forEachIndexed { idx, session ->
            if (idx > 0) ThinDivider()
            SessionRow(session, onToggleSession)
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Full plan (collapsible weeks)
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun FullPlanView(plan: TrainingPlan, onToggleSession: (Int) -> Unit) {
    val currentWeekNum = plan.currentWeekNumber
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            "TUTTE LE SETTIMANE",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(vertical = 4.dp),
        )
        plan.weeks.forEach { week ->
            CollapsibleWeekRow(
                week = week,
                defaultExpanded = week.weekNumber == currentWeekNum,
                onToggleSession = onToggleSession,
            )
        }
    }
}

@Composable
private fun CollapsibleWeekRow(
    week: PlanWeek,
    defaultExpanded: Boolean,
    onToggleSession: (Int) -> Unit,
) {
    var expanded by rememberSaveable { mutableStateOf(defaultExpanded) }
    SurfaceCard {
        Row(
            Modifier
                .fillMaxWidth()
                .clickable { expanded = !expanded }
                .padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                WeekHeader(week, isCurrent = false)
            }
            Icon(
                if (expanded) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore,
                contentDescription = if (expanded) "Comprimi" else "Espandi",
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        AnimatedVisibility(
            visible = expanded,
            enter = expandVertically(),
            exit = shrinkVertically(),
        ) {
            Column {
                Spacer(Modifier.height(8.dp))
                week.sessions.forEachIndexed { idx, session ->
                    if (idx > 0) ThinDivider()
                    SessionRow(session, onToggleSession)
                }
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Week header (phase badge + target km)
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun WeekHeader(week: PlanWeek, isCurrent: Boolean) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            "Settimana ${week.weekNumber}",
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.Bold,
        )
        if (isCurrent) {
            Pill("In corso", BrandGreen)
        }
        Pill(phaseLabel(week.phase), Color(0xFF7C4DFF))
        Spacer(Modifier.weight(1f))
        Text(
            "${week.targetKm.toInt()} km",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Session row
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun SessionRow(session: PlanSession, onToggleSession: (Int) -> Unit) {
    val color = sessionColor(session.sessionType)
    val isRest = session.sessionType.lowercase() == "rest"
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        // Day label
        Text(
            dayLabel(session.dayOfWeek),
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(32.dp),
        )
        Spacer(Modifier.width(8.dp))
        // Colored session-type icon circle
        Box(
            Modifier
                .size(36.dp)
                .clip(CircleShape)
                .background(color.copy(alpha = 0.16f)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                sessionIcon(session.sessionType),
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(18.dp),
            )
        }
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(
                session.title,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold,
                textDecoration = if (session.completed) TextDecoration.LineThrough else null,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (session.description != null) {
                Text(
                    session.description,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            if (!isRest) {
                val targets = buildList {
                    session.targetDistanceKm?.let { add("${it.toInt()} km") }
                    session.targetDurationMin?.let { add("${it.toInt()} min") }
                    session.targetPace?.let { add(it) }
                }
                if (targets.isNotEmpty()) {
                    Text(
                        targets.joinToString(" · "),
                        style = MaterialTheme.typography.labelSmall,
                        color = color,
                        fontWeight = FontWeight.Medium,
                    )
                }
            }
        }
        if (!isRest) {
            Checkbox(
                checked = session.completed,
                onCheckedChange = { onToggleSession(session.id) },
                colors = CheckboxDefaults.colors(
                    checkedColor = BrandGreen,
                    uncheckedColor = MaterialTheme.colorScheme.onSurfaceVariant,
                ),
            )
        } else {
            // Rest day: show a faint checkmark placeholder to maintain alignment.
            Box(Modifier.size(48.dp))
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Generate plan dialog
// ─────────────────────────────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GeneratePlanDialog(
    onGenerate: (PlanGenerateRequest) -> Unit,
    onDismiss: () -> Unit,
) {
    val goalTypes = listOf("marathon", "half", "10k", "5k", "general")
    val goalTypeLabels = listOf("Maratona", "Mezza Maratona", "10 km", "5 km", "Generale")
    val levels = listOf("beginner", "intermediate", "advanced")
    val levelLabels = listOf("Principiante", "Intermedio", "Avanzato")

    var goalTypeExpanded by remember { mutableStateOf(false) }
    var levelExpanded by remember { mutableStateOf(false) }

    var selectedGoalTypeIdx by rememberSaveable { mutableStateOf(0) }
    var goalDate by rememberSaveable { mutableStateOf("") }
    var goalTime by rememberSaveable { mutableStateOf("") }
    var selectedLevelIdx by rememberSaveable { mutableStateOf(1) }
    var daysPerWeek by rememberSaveable { mutableFloatStateOf(4f) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Genera piano", fontWeight = FontWeight.Bold) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                // Goal type picker
                ExposedDropdownMenuBox(
                    expanded = goalTypeExpanded,
                    onExpandedChange = { goalTypeExpanded = it },
                ) {
                    OutlinedTextField(
                        value = goalTypeLabels[selectedGoalTypeIdx],
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Obiettivo") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = goalTypeExpanded) },
                        modifier = Modifier
                            .menuAnchor()
                            .fillMaxWidth(),
                    )
                    ExposedDropdownMenu(
                        expanded = goalTypeExpanded,
                        onDismissRequest = { goalTypeExpanded = false },
                    ) {
                        goalTypeLabels.forEachIndexed { idx, label ->
                            DropdownMenuItem(
                                text = { Text(label) },
                                onClick = {
                                    selectedGoalTypeIdx = idx
                                    goalTypeExpanded = false
                                },
                            )
                        }
                    }
                }

                // Goal date
                OutlinedTextField(
                    value = goalDate,
                    onValueChange = { goalDate = it },
                    label = { Text("Data gara (AAAA-MM-GG)") },
                    placeholder = { Text("es. 2026-10-04") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                )

                // Goal time
                OutlinedTextField(
                    value = goalTime,
                    onValueChange = { goalTime = it },
                    label = { Text("Tempo obiettivo (opzionale)") },
                    placeholder = { Text("es. 3:45:00") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                )

                // Level picker
                ExposedDropdownMenuBox(
                    expanded = levelExpanded,
                    onExpandedChange = { levelExpanded = it },
                ) {
                    OutlinedTextField(
                        value = levelLabels[selectedLevelIdx],
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Livello") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = levelExpanded) },
                        modifier = Modifier
                            .menuAnchor()
                            .fillMaxWidth(),
                    )
                    ExposedDropdownMenu(
                        expanded = levelExpanded,
                        onDismissRequest = { levelExpanded = false },
                    ) {
                        levelLabels.forEachIndexed { idx, label ->
                            DropdownMenuItem(
                                text = { Text(label) },
                                onClick = {
                                    selectedLevelIdx = idx
                                    levelExpanded = false
                                },
                            )
                        }
                    }
                }

                // Days per week slider
                Column {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text("Allenamenti/settimana", style = MaterialTheme.typography.bodySmall)
                        Text(
                            "${daysPerWeek.toInt()}",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = BrandGreen,
                        )
                    }
                    Slider(
                        value = daysPerWeek,
                        onValueChange = { daysPerWeek = it },
                        valueRange = 3f..6f,
                        steps = 2,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    if (goalDate.isNotBlank()) {
                        onGenerate(
                            PlanGenerateRequest(
                                goalType = goalTypes[selectedGoalTypeIdx],
                                goalDate = goalDate.trim(),
                                goalTime = goalTime.trim().ifBlank { null },
                                level = levels[selectedLevelIdx],
                                daysPerWeek = daysPerWeek.toInt(),
                                longRunDay = 6,
                            ),
                        )
                    }
                },
                enabled = goalDate.isNotBlank(),
            ) {
                Icon(Icons.Filled.Check, contentDescription = null)
                Spacer(Modifier.width(6.dp))
                Text("Genera")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Annulla") }
        },
    )
}
