package com.runningcoach.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Map
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.runningcoach.app.ui.components.ActivityRow
import com.runningcoach.app.ui.components.ScreenTitle
import com.runningcoach.app.ui.viewmodel.OverviewUiState

@Composable
fun ActivitiesScreen(
    state: OverviewUiState,
    onOpenActivity: (Int) -> Unit = {},
    onOpenHeatmap: () -> Unit = {},
    onOpenCalendar: () -> Unit = {},
) {
    val activities = state.overview?.activities.orEmpty()
    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = 16.dp),
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .padding(vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            ScreenTitle(
                "Allenamenti",
                "${activities.size} corse sincronizzate",
                Modifier.weight(1f),
            )
            OutlinedButton(onClick = onOpenCalendar) {
                Icon(Icons.Filled.CalendarMonth, contentDescription = null, Modifier.height(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Calendario")
            }
            Spacer(Modifier.width(8.dp))
            OutlinedButton(onClick = onOpenHeatmap) {
                Icon(Icons.Filled.Map, contentDescription = null, Modifier.height(18.dp))
                Spacer(Modifier.width(6.dp))
                Text("Mappa")
            }
        }
        if (activities.isEmpty()) {
            Text(
                "Nessuna corsa. Vai su Oggi e premi Sincronizza.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            val prIds = state.overview?.prActivityIds?.toSet() ?: emptySet()
            LazyColumn(
                Modifier.fillMaxSize(),
                contentPadding = PaddingValues(bottom = 16.dp),
            ) {
                items(activities) { act ->
                    ActivityRow(
                        activity = act,
                        isPr = act.id in prIds,
                        onClick = { onOpenActivity(act.id) },
                    )
                }
                item { Spacer(Modifier.height(8.dp)) }
            }
        }
    }
}
