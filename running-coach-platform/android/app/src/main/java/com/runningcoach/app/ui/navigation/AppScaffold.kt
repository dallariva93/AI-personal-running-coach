package com.runningcoach.app.ui.navigation

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BarChart
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.runningcoach.app.RunningCoachApp
import com.runningcoach.app.ui.screens.ActivitiesScreen
import com.runningcoach.app.ui.screens.ActivityDetailScreen
import com.runningcoach.app.ui.screens.HomeScreen
import com.runningcoach.app.ui.screens.PlanScreen
import com.runningcoach.app.ui.screens.SettingsScreen
import com.runningcoach.app.ui.screens.StatsScreen
import com.runningcoach.app.ui.theme.RunningCoachTheme
import com.runningcoach.app.ui.viewmodel.OverviewViewModel
import com.runningcoach.app.ui.viewmodel.SettingsViewModel
import com.runningcoach.app.ui.viewmodel.StatsViewModel
import com.runningcoach.app.ui.viewmodel.ViewModelFactory
import com.runningcoach.app.widget.RunningWidget
import kotlinx.coroutines.launch
import java.io.File

private enum class Dest(val route: String, val label: String, val icon: ImageVector) {
    Home("home", "Oggi", Icons.Filled.Today),
    Activities("activities", "Allenamenti", Icons.Filled.DirectionsRun),
    Plan("plan", "Piano", Icons.Filled.CalendarMonth),
    Stats("stats", "Statistiche", Icons.Filled.BarChart),
    Settings("settings", "Impostazioni", Icons.Filled.Settings),
}

@Composable
fun AppScaffold(app: RunningCoachApp) {
    val factory = remember { ViewModelFactory(app) }
    val overviewVm: OverviewViewModel = viewModel(factory = factory)
    val settingsVm: SettingsViewModel = viewModel(factory = factory)
    val statsVm: StatsViewModel = viewModel(factory = factory)

    val state by overviewVm.state.collectAsState()
    val settings by settingsVm.settings.collectAsState()
    val exportState by settingsVm.exportState.collectAsState()
    val statsState by statsVm.state.collectAsState()

    // Resolve dark/light from the stored preference.
    val darkTheme = when (settings?.themeMode) {
        "dark" -> true
        "light" -> false
        else -> isSystemInDarkTheme()
    }

    RunningCoachTheme(darkTheme = darkTheme) {
        val context = LocalContext.current
        val scope = rememberCoroutineScope()
        val navController = rememberNavController()
        val snackbar = remember { SnackbarHostState() }

        // Surface action results / errors as snackbars.
        LaunchedEffect(state.message, state.error) {
            val text = state.error ?: state.message
            if (text != null) {
                snackbar.showSnackbar(text)
                overviewVm.clearMessage()
            }
        }

        // Update home-screen widget whenever the overview changes.
        LaunchedEffect(state.overview) {
            state.overview?.let { ov ->
                scope.launch { RunningWidget.updateAll(context, ov) }
            }
        }

        // Handle export: save file and open share sheet.
        LaunchedEffect(exportState.file) {
            exportState.file?.let { (name, bytes) ->
                val file = File(context.cacheDir, name)
                file.writeBytes(bytes)
                val uri: Uri = FileProvider.getUriForFile(
                    context,
                    "${context.packageName}.fileprovider",
                    file,
                )
                val mime = if (name.endsWith("json")) "application/json" else "text/csv"
                val intent = Intent(Intent.ACTION_SEND).apply {
                    type = mime
                    putExtra(Intent.EXTRA_STREAM, uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                context.startActivity(Intent.createChooser(intent, "Esporta corse"))
                settingsVm.clearExport()
            }
        }

        // Snackbar for export errors.
        LaunchedEffect(exportState.error) {
            exportState.error?.let {
                snackbar.showSnackbar("Export fallito: $it")
                settingsVm.clearExport()
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
                val openActivity: (Int) -> Unit = { id ->
                    navController.navigate("activity/$id") { launchSingleTop = true }
                }
                composable(Dest.Home.route) {
                    HomeScreen(
                        state = state,
                        onSync = overviewVm::sync,
                        onAnalyze = overviewVm::analyze,
                        onOpenActivity = openActivity,
                    )
                }
                composable(Dest.Activities.route) {
                    ActivitiesScreen(state, onOpenActivity = openActivity)
                }
                composable(
                    route = "activity/{id}",
                    arguments = listOf(navArgument("id") { type = NavType.IntType }),
                ) { entry ->
                    val id = entry.arguments?.getInt("id")
                    val activity = state.overview?.activities?.firstOrNull { it.id == id }
                    ActivityDetailScreen(
                        activity = activity,
                        onBack = { navController.popBackStack() },
                    )
                }
                composable(Dest.Plan.route) {
                    PlanScreen(state = state, onGeneratePlan = overviewVm::planWeekly)
                }
                composable(Dest.Stats.route) {
                    StatsScreen(
                        state = statsState,
                        onPeriodChange = statsVm::load,
                        onExportCsv = { settingsVm.exportData("csv") },
                        onExportJson = { settingsVm.exportData("json") },
                    )
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
                        onSaveTheme = settingsVm::saveTheme,
                    )
                }
            }
        }
    }
}
