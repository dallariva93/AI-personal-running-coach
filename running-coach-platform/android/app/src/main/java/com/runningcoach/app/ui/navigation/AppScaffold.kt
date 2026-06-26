package com.runningcoach.app.ui.navigation

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.DirectionsRun
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Today
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.runningcoach.app.RunningCoachApp
import com.runningcoach.app.ui.screens.ActivitiesScreen
import com.runningcoach.app.ui.screens.HomeScreen
import com.runningcoach.app.ui.screens.PlanScreen
import com.runningcoach.app.ui.screens.SettingsScreen
import com.runningcoach.app.ui.viewmodel.OverviewViewModel
import com.runningcoach.app.ui.viewmodel.SettingsViewModel
import com.runningcoach.app.ui.viewmodel.ViewModelFactory

private enum class Dest(val route: String, val label: String, val icon: ImageVector) {
    Home("home", "Oggi", Icons.Filled.Today),
    Activities("activities", "Allenamenti", Icons.Filled.DirectionsRun),
    Plan("plan", "Piano", Icons.Filled.CalendarMonth),
    Settings("settings", "Impostazioni", Icons.Filled.Settings),
}

@Composable
fun AppScaffold(app: RunningCoachApp) {
    val factory = remember { ViewModelFactory(app) }
    val overviewVm: OverviewViewModel = viewModel(factory = factory)
    val settingsVm: SettingsViewModel = viewModel(factory = factory)

    val navController = rememberNavController()
    val state by overviewVm.state.collectAsState()
    val settings by settingsVm.settings.collectAsState()
    val snackbar = remember { SnackbarHostState() }

    // Surface action results / errors as snackbars.
    LaunchedEffect(state.message, state.error) {
        val text = state.error ?: state.message
        if (text != null) {
            snackbar.showSnackbar(text)
            overviewVm.clearMessage()
        }
    }

    val backStack by navController.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                Dest.entries.forEach { dest ->
                    NavigationBarItem(
                        selected = currentRoute == dest.route,
                        onClick = {
                            navController.navigate(dest.route) {
                                popUpTo(Dest.Home.route)
                                launchSingleTop = true
                            }
                        },
                        icon = { Icon(dest.icon, contentDescription = dest.label) },
                        label = { Text(dest.label) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = MaterialTheme.colorScheme.onPrimary,
                            indicatorColor = MaterialTheme.colorScheme.primary,
                            selectedTextColor = MaterialTheme.colorScheme.primary,
                        ),
                    )
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = Dest.Home.route,
            modifier = Modifier.padding(padding),
        ) {
            composable(Dest.Home.route) {
                HomeScreen(
                    state = state,
                    onSync = overviewVm::sync,
                    onAnalyze = overviewVm::analyze,
                )
            }
            composable(Dest.Activities.route) { ActivitiesScreen(state) }
            composable(Dest.Plan.route) {
                PlanScreen(state = state, onGeneratePlan = overviewVm::planWeekly)
            }
            composable(Dest.Settings.route) {
                SettingsScreen(
                    settings = settings,
                    profile = state.overview?.profile,
                    onSave = { url, token ->
                        settingsVm.save(url, token) { overviewVm.refresh() }
                    },
                    onSaveCoach = { goalType, date, time, level, risk ->
                        overviewVm.saveCoach(goalType, date, time, level, risk)
                    },
                    onCheckin = { sleep, fatigue, soreness, motivation ->
                        overviewVm.submitCheckin(sleep, fatigue, soreness, motivation)
                    },
                )
            }
        }
    }
}
