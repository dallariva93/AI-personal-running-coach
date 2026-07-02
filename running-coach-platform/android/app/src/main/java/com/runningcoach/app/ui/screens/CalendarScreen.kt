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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.runningcoach.app.data.model.Activity
import com.runningcoach.app.ui.components.ActivityRow
import com.runningcoach.app.ui.components.ScreenTitle
import com.runningcoach.app.ui.theme.activityColor
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.TextStyle
import java.util.Locale

@Composable
fun CalendarScreen(
    activities: List<Activity>,
    prActivityIds: Set<Int> = emptySet(),
    onOpenActivity: (Int) -> Unit = {},
    onBack: () -> Unit = {},
) {
    var currentMonth by remember { mutableStateOf(YearMonth.now()) }
    var selectedDate by remember { mutableStateOf<LocalDate?>(null) }

    // Group activities by date string for O(1) lookup.
    val byDate: Map<String, List<Activity>> = remember(activities) {
        activities.groupBy { it.date.take(10) }
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.Filled.ChevronLeft, contentDescription = "Indietro")
            }
            ScreenTitle(
                "Calendario",
                "${activities.size} corse",
                Modifier.weight(1f),
            )
        }

        // Month navigation header.
        Row(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            IconButton(onClick = { currentMonth = currentMonth.minusMonths(1); selectedDate = null }) {
                Icon(Icons.Filled.ChevronLeft, contentDescription = "Mese precedente")
            }
            Text(
                text = "${currentMonth.month.getDisplayName(TextStyle.FULL, Locale.ITALIAN).replaceFirstChar { it.uppercase() }} ${currentMonth.year}",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            IconButton(
                onClick = { currentMonth = currentMonth.plusMonths(1); selectedDate = null },
                enabled = currentMonth < YearMonth.now(),
            ) {
                Icon(Icons.Filled.ChevronRight, contentDescription = "Mese successivo")
            }
        }

        Spacer(Modifier.height(8.dp))

        // Day-of-week labels (Mon–Sun).
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

        // Calendar grid.
        val firstDay = currentMonth.atDay(1)
        val leadingBlanks = (firstDay.dayOfWeek.value - 1) // Monday = 1 → 0 blanks
        val daysInMonth = currentMonth.lengthOfMonth()
        val today = LocalDate.now()

        LazyVerticalGrid(
            columns = GridCells.Fixed(7),
            modifier = Modifier
                .fillMaxWidth()
                // Tight 4dp (was 8dp): reclaim width so a 7-column week clears the
                // 48dp touch-target minimum on more phones (Q7).
                .padding(horizontal = 4.dp),
            contentPadding = PaddingValues(bottom = 8.dp),
        ) {
            // Leading blank cells.
            items(leadingBlanks) {
                Box(Modifier.aspectRatio(1f))
            }
            // Day cells.
            items(daysInMonth) { i ->
                val day = i + 1
                val date = currentMonth.atDay(day)
                val dateStr = date.toString()
                val dayActivities = byDate[dateStr].orEmpty()
                val isSelected = selectedDate == date
                val isToday = date == today

                DayCell(
                    day = day,
                    activities = dayActivities,
                    isSelected = isSelected,
                    isToday = isToday,
                    onClick = { selectedDate = if (isSelected) null else date },
                )
            }
        }

        HorizontalDivider(Modifier.padding(horizontal = 16.dp))

        // Selected day detail panel.
        val selectedActivities = selectedDate?.let { byDate[it.toString()].orEmpty() }
        if (selectedActivities != null) {
            Text(
                text = if (selectedActivities.isEmpty()) "Nessuna corsa in questo giorno."
                else "${selectedActivities.size} corsa/e",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
            )
            LazyColumn(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
                contentPadding = PaddingValues(bottom = 16.dp),
            ) {
                items(selectedActivities) { act ->
                    ActivityRow(
                        activity = act,
                        isPr = act.id in prActivityIds,
                        onClick = { onOpenActivity(act.id) },
                    )
                }
            }
        } else {
            Text(
                "Tocca un giorno per vedere le corse.",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
            )
        }
    }
}

@Composable
private fun DayCell(
    day: Int,
    activities: List<Activity>,
    isSelected: Boolean,
    isToday: Boolean,
    onClick: () -> Unit,
) {
    val hasRun = activities.isNotEmpty()
    val dotColor = if (hasRun) activityColor(activities.first().activityType) else Color.Transparent

    Box(
        Modifier
            .aspectRatio(1f)
            // 48dp touch-target floor (Q7) — see PlanCalendarScreen for the same
            // narrow-device caveat (a 7-column week can't force this on <336dp).
            .sizeIn(minWidth = 48.dp, minHeight = 48.dp)
            .padding(1.dp)
            .clip(RoundedCornerShape(8.dp))
            .then(
                if (isSelected) Modifier.background(MaterialTheme.colorScheme.primaryContainer)
                else if (isToday) Modifier.border(1.dp, MaterialTheme.colorScheme.primary, RoundedCornerShape(8.dp))
                else Modifier
            )
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                "$day",
                style = MaterialTheme.typography.bodySmall.copy(fontSize = 13.sp),
                fontWeight = if (isToday || isSelected) FontWeight.Bold else FontWeight.Normal,
                color = if (isSelected) MaterialTheme.colorScheme.onPrimaryContainer
                else MaterialTheme.colorScheme.onSurface,
            )
            if (hasRun) {
                Spacer(Modifier.height(2.dp))
                Box(
                    Modifier
                        .size(6.dp)
                        .clip(CircleShape)
                        .background(dotColor),
                )
            }
        }
    }
}
