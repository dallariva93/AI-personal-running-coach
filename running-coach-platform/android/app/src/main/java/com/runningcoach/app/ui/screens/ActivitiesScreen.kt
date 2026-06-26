package com.runningcoach.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.runningcoach.app.ui.components.ActivityRow
import com.runningcoach.app.ui.components.ScreenTitle
import com.runningcoach.app.ui.viewmodel.OverviewUiState

@Composable
fun ActivitiesScreen(state: OverviewUiState) {
    val activities = state.overview?.activities.orEmpty()
    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(horizontal = 16.dp),
    ) {
        ScreenTitle(
            "Allenamenti",
            "${activities.size} corse sincronizzate",
            Modifier.padding(vertical = 14.dp),
        )
        if (activities.isEmpty()) {
            Text(
                "Nessuna corsa. Vai su Oggi e premi Sincronizza.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            LazyColumn(
                Modifier.fillMaxSize(),
                contentPadding = PaddingValues(bottom = 16.dp),
            ) {
                items(activities) { ActivityRow(it) }
                item { Spacer(Modifier.height(8.dp)) }
            }
        }
    }
}
