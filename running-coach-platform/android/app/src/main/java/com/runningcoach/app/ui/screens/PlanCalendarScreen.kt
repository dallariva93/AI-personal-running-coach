package com.runningcoach.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.runningcoach.app.data.model.PlanSession
import com.runningcoach.app.data.model.TrainingPlan
import com.runningcoach.app.ui.components.Pill
import com.runningcoach.app.ui.components.ScreenTitle
import com.runningcoach.app.ui.components.SurfaceCard
import com.runningcoach.app.ui.theme.BrandGreen
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.TextStyle
import java.util.Locale

// Screen-private session palette (mirrors PlanScreen's colors).
private val CalEasy = BrandGreen
private val CalLong = Color(0xFF2196F3)
private val CalTempo = Color(0xFFFF6D00)
private val CalIntervals = Color(0xFFF43F5E)
private val CalRace = Color(0xFFFFD600)
private val CalCross = Color(0xFF26C6DA)
private val CalRest = Color(0xFF64748B)

private fun calColor(type: String): Color = when (type.lowercase()) {
    "easy", "strides" -> CalEasy
    "long" -> CalLong
    "tempo" -> CalTempo
    "intervals" -> CalIntervals
    "race" -> CalRace
    "cross" -> CalCross
    else -> CalRest
}

private fun calLabel(type: String): String = when (type.lowercase()) {
    "easy" -> "Facile"
    "long" -> "Lungo"
    "tempo" -> "Tempo"
    "intervals" -> "Ripetute"
    "race" -> "Gara"
    "cross" -> "Cross"
    "strides" -> "Allunghi"
    "rest" -> "Riposo"
    else -> type
}

/**
 * Calendar plan editor (Roadmap #12): the whole plan on a month calendar with
 * movable sessions. Tap a day to inspect its session, "Sposta" to enter move
 * mode, tap the destination day and confirm — the backend swaps the two days,
 * revalidates the week and returns safety warnings shown via snackbar.
 */
@Composable
fun PlanCalendarScreen(
    plan: TrainingPlan?,
    onMoveSession: (Int, String) -> Unit,
    onBack: () -> Unit,
) {
    if (plan == null) {
        Column(
            Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text(
                "Nessun piano attivo da modificare.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(12.dp))
            OutlinedButton(onClick = onBack) { Text("Indietro") }
        }
        return
    }

    val planStart = remember(plan.id) {
        runCatching { LocalDate.parse(plan.startDate) }.getOrElse { LocalDate.now() }
    }
    val planEnd = planStart.plusDays(plan.weeksTotal * 7L - 1)

    // date → session for the whole plan.
    val byDate: Map<LocalDate, PlanSession> = remember(plan) {
        buildMap {
            plan.weeks.forEach { week ->
                week.sessions.forEach { s ->
                    put(planStart.plusDays((week.weekNumber - 1) * 7L + s.dayOfWeek), s)
                }
            }
        }
    }

    val today = LocalDate.now()
    var month by remember(plan.id) {
        mutableStateOf(YearMonth.from(maxOf(planStart, minOf(today, planEnd))))
    }
    var selected by remember { mutableStateOf<LocalDate?>(null) }
    // Move mode: the session being moved and its source date.
    var moving by remember { mutableStateOf<Pair<PlanSession, LocalDate>?>(null) }
    var confirmTarget by remember { mutableStateOf<LocalDate?>(null) }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState()),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Indietro")
            }
            ScreenTitle(
                "Calendario piano",
                "Settimana ${plan.currentWeekNumber}/${plan.weeksTotal} · tocca e sposta",
                Modifier.weight(1f),
            )
        }

        // Move-mode banner.
        moving?.let { (sess, from) ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(MaterialTheme.colorScheme.primaryContainer)
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    Icons.Filled.SwapHoriz,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onPrimaryContainer,
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    "Sposto \"${sess.title}\" (${from.dayOfMonth}/${from.monthValue}): " +
                        "tocca il giorno di destinazione",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = { moving = null }) { Text("Annulla") }
            }
            Spacer(Modifier.height(6.dp))
        }

        // Month navigation.
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            IconButton(
                onClick = { month = month.minusMonths(1) },
                enabled = month > YearMonth.from(planStart),
            ) { Icon(Icons.Filled.ChevronLeft, contentDescription = "Mese precedente") }
            Text(
                "${month.month.getDisplayName(TextStyle.FULL, Locale.ITALIAN).replaceFirstChar { it.uppercase() }} ${month.year}",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            IconButton(
                onClick = { month = month.plusMonths(1) },
                enabled = month < YearMonth.from(planEnd),
            ) { Icon(Icons.Filled.ChevronRight, contentDescription = "Mese successivo") }
        }

        Spacer(Modifier.height(6.dp))
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp)) {
            listOf("L", "M", "M", "G", "V", "S", "D").forEach { label ->
                Text(
                    label,
                    modifier = Modifier.weight(1f),
                    textAlign = TextAlign.Center,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        Spacer(Modifier.height(4.dp))

        val firstDay = month.atDay(1)
        val leadingBlanks = firstDay.dayOfWeek.value - 1
        val daysInMonth = month.lengthOfMonth()
        val gridRows = ((leadingBlanks + daysInMonth) + 6) / 7

        LazyVerticalGrid(
            columns = GridCells.Fixed(7),
            modifier = Modifier
                .fillMaxWidth()
                .height((gridRows * 52).dp)
                // Tight 4dp (was 8dp): a 7-column week needs every spare pixel to
                // clear the 48dp touch-target minimum on narrower phones (Q7).
                .padding(horizontal = 4.dp),
            contentPadding = PaddingValues(bottom = 4.dp),
            userScrollEnabled = false,
        ) {
            items(leadingBlanks) { Box(Modifier.aspectRatio(1f)) }
            items(daysInMonth) { i ->
                val day = month.atDay(i + 1)
                val sess = byDate[day]
                PlanDayCell(
                    day = day.dayOfMonth,
                    session = sess,
                    inPlan = day in planStart..planEnd,
                    isToday = day == today,
                    isSelected = selected == day,
                    isMoveSource = moving?.second == day,
                    onClick = {
                        val mv = moving
                        if (mv != null) {
                            if (day != mv.second) confirmTarget = day
                        } else {
                            selected = if (selected == day) null else day
                        }
                    },
                )
            }
        }

        // Selected-day detail + move affordance.
        val selDay = selected
        val selSess = selDay?.let { byDate[it] }
        if (selDay != null && selSess != null && moving == null) {
            SurfaceCard(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Pill(calLabel(selSess.sessionType), calColor(selSess.sessionType))
                    Spacer(Modifier.width(8.dp))
                    Column(Modifier.weight(1f)) {
                        Text(
                            selSess.title,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                        )
                        val targets = buildList {
                            selSess.targetDistanceKm?.let { add("${it.toInt()} km") }
                            selSess.targetDurationMin?.let { add("${it.toInt()} min") }
                            selSess.targetPace?.let { add(it) }
                        }
                        Text(
                            "${selDay.dayOfMonth}/${selDay.monthValue}" +
                                (if (targets.isEmpty()) "" else " · " + targets.joinToString(" · ")) +
                                (if (selSess.completed) " · ✓ completata" else ""),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                selSess.description?.takeIf { it.isNotBlank() }?.let {
                    Spacer(Modifier.height(6.dp))
                    Text(
                        it,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                val movable = !selSess.completed &&
                    selSess.sessionType.lowercase() != "race" &&
                    !selDay.isBefore(today)
                if (movable) {
                    Spacer(Modifier.height(10.dp))
                    Button(
                        onClick = { moving = selSess to selDay; selected = null },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Icon(Icons.Filled.SwapHoriz, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text("Sposta questa seduta")
                    }
                } else {
                    Spacer(Modifier.height(6.dp))
                    Text(
                        when {
                            selSess.completed -> "Seduta completata: non si sposta."
                            selSess.sessionType.lowercase() == "race" ->
                                "La gara obiettivo non si sposta."
                            else -> "Le sedute passate non si spostano."
                        },
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        } else if (moving == null) {
            Text(
                "Tocca un giorno per vedere la seduta; da lì puoi spostarla.",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
            )
        }

        // Legend.
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            listOf("easy", "tempo", "intervals", "long", "race").forEach { t ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(8.dp).clip(CircleShape).background(calColor(t)))
                    Spacer(Modifier.width(4.dp))
                    Text(
                        calLabel(t),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        Spacer(Modifier.height(16.dp))
    }

    // Confirmation dialog for the move.
    val mv = moving
    val tgt = confirmTarget
    if (mv != null && tgt != null) {
        val destSess = byDate[tgt]
        AlertDialog(
            onDismissRequest = { confirmTarget = null },
            title = { Text("Sposta seduta") },
            text = {
                Text(
                    "Spostare \"${mv.first.title}\" a ${tgt.dayOfMonth}/${tgt.monthValue}?" +
                        (destSess?.let {
                            "\n\"${it.title}\" prenderà il posto del " +
                                "${mv.second.dayOfMonth}/${mv.second.monthValue}."
                        } ?: ""),
                )
            },
            confirmButton = {
                Button(onClick = {
                    onMoveSession(mv.first.id, tgt.toString())
                    moving = null
                    confirmTarget = null
                }) { Text("Sposta") }
            },
            dismissButton = {
                TextButton(onClick = { confirmTarget = null }) { Text("Annulla") }
            },
        )
    }
}

@Composable
private fun PlanDayCell(
    day: Int,
    session: PlanSession?,
    inPlan: Boolean,
    isToday: Boolean,
    isSelected: Boolean,
    isMoveSource: Boolean,
    onClick: () -> Unit,
) {
    val dotColor = session
        ?.takeIf { it.sessionType.lowercase() != "rest" }
        ?.let { calColor(it.sessionType) }

    Box(
        Modifier
            .aspectRatio(1f)
            // 48dp touch-target floor (Q7): a no-op on 320dp-wide phones where 7
            // fixed columns can't each reach 48dp (7*48=336dp alone), but the real
            // fix on the ~360dp+ phones that make up the overwhelming majority of
            // installs — see docs/ACCESSIBILITY.md for the narrow-device caveat.
            .sizeIn(minWidth = 48.dp, minHeight = 48.dp)
            .padding(1.dp)
            .clip(RoundedCornerShape(8.dp))
            .then(
                when {
                    isMoveSource -> Modifier.background(MaterialTheme.colorScheme.tertiaryContainer)
                    isSelected -> Modifier.background(MaterialTheme.colorScheme.primaryContainer)
                    isToday -> Modifier.border(
                        1.dp, MaterialTheme.colorScheme.primary, RoundedCornerShape(8.dp)
                    )
                    else -> Modifier
                }
            )
            .clickable(enabled = inPlan, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        // Redesign (handoff 1i): a bottom accent bar spanning most of the cell
        // width, the way the mockup marks a day's session type — reads clearer
        // at a glance across a whole month than a small centered dot.
        Column(
            Modifier.fillMaxSize().padding(vertical = 4.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                "$day",
                style = MaterialTheme.typography.bodySmall.copy(fontSize = 13.sp),
                fontWeight = if (isToday || isSelected) FontWeight.Bold else FontWeight.Normal,
                color = when {
                    !inPlan -> MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.35f)
                    isSelected -> MaterialTheme.colorScheme.onPrimaryContainer
                    else -> MaterialTheme.colorScheme.onSurface
                },
            )
            Spacer(Modifier.weight(1f))
            if (dotColor != null) {
                Box(
                    Modifier
                        .fillMaxWidth(0.6f)
                        .height(4.dp)
                        .clip(RoundedCornerShape(2.dp))
                        .background(dotColor.copy(alpha = if (session?.completed == true) 0.45f else 1f)),
                )
            }
        }
    }
}
