package com.runningcoach.app.ui.navigation

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.DirectionsRun
import androidx.compose.material.icons.filled.Today
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
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
import com.runningcoach.app.data.model.AthleteProfile
import com.runningcoach.app.ui.screens.ActivitiesScreen
import com.runningcoach.app.ui.screens.ActivityDetailScreen
import com.runningcoach.app.ui.screens.CalendarScreen
import com.runningcoach.app.ui.screens.ChatScreen
import com.runningcoach.app.ui.screens.CoachLogScreen
import com.runningcoach.app.ui.screens.CrossTrainingScreen
import com.runningcoach.app.ui.screens.HeatmapScreen
import com.runningcoach.app.ui.screens.HomeScreen
import com.runningcoach.app.ui.screens.LiveRunScreen
import com.runningcoach.app.ui.screens.MapFullscreenScreen
import com.runningcoach.app.ui.screens.PlanCalendarScreen
import com.runningcoach.app.ui.screens.PlanScreen
import com.runningcoach.app.ui.screens.RecapScreen
import com.runningcoach.app.ui.screens.SettingsScreen
import com.runningcoach.app.ui.screens.ShoesScreen
import com.runningcoach.app.ui.screens.StatsScreen
import com.runningcoach.app.ui.screens.WorkoutScreen
import com.runningcoach.app.ui.screens.parseRoutePoints
import com.runningcoach.app.ui.theme.RunningCoachTheme
import com.runningcoach.app.ui.viewmodel.ChatViewModel
import com.runningcoach.app.ui.viewmodel.OverviewViewModel
import com.runningcoach.app.ui.viewmodel.PlanViewModel
import com.runningcoach.app.ui.viewmodel.SettingsViewModel
import com.runningcoach.app.ui.viewmodel.StatsViewModel
import com.runningcoach.app.ui.viewmodel.ViewModelFactory
import com.runningcoach.app.ui.viewmodel.WorkoutViewModel
import com.runningcoach.app.widget.RunningWidget
import kotlinx.coroutines.launch
import java.io.File

// Four destinations (A8: 6 tabs → 4). Stats lives inside Corse behind a
// Lista/Statistiche switch; Settings is the gear icon on the Oggi header.
// Their routes survive below as plain composables (soft migration: deep links
// and in-app navigation to "stats"/"settings" keep working).
private enum class Dest(val route: String, val label: String, val icon: ImageVector) {
    Home("home", "Oggi", Icons.Filled.Today),
    Activities("activities", "Corse", Icons.Filled.DirectionsRun),
    Plan("plan", "Piano", Icons.Filled.CalendarMonth),
    Chat("chat", "Coach", Icons.Filled.AutoAwesome),
}

@Composable
fun AppScaffold(
    app: RunningCoachApp,
    debriefRequest: com.runningcoach.app.DebriefRequest? = null,
    onDebriefHandled: () -> Unit = {},
) {
    val factory = remember { ViewModelFactory(app) }
    val overviewVm: OverviewViewModel = viewModel(factory = factory)
    val settingsVm: SettingsViewModel = viewModel(factory = factory)
    val statsVm: StatsViewModel = viewModel(factory = factory)
    val planVm: PlanViewModel = viewModel(factory = factory)
    val workoutVm: WorkoutViewModel = viewModel(factory = factory)
    val chatVm: ChatViewModel = viewModel(factory = factory)

    val state by overviewVm.state.collectAsState()
    val syncStatus by overviewVm.syncStatus.collectAsState()
    val settings by settingsVm.settings.collectAsState()
    val exportState by settingsVm.exportState.collectAsState()
    val stravaStatus by settingsVm.stravaStatus.collectAsState()
    val statsState by statsVm.state.collectAsState()
    val planState by planVm.state.collectAsState()
    val workoutState by workoutVm.state.collectAsState()
    val chatState by chatVm.state.collectAsState()

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

        // Surface plan action results / errors as snackbars. A move offers an
        // "Annulla" action (Roadmap Q8) — the swap is its own inverse.
        LaunchedEffect(planState.successMessage, planState.error) {
            val text = planState.error ?: planState.successMessage
            if (text != null) {
                val move = planState.lastMove
                val result = snackbar.showSnackbar(
                    message = text,
                    actionLabel = if (move != null) "Annulla" else null,
                )
                if (result == SnackbarResult.ActionPerformed && move != null) {
                    planVm.moveSession(move.first, move.second)
                }
                planVm.clearMessage()
            }
        }

        // Surface workout action results / errors as snackbars.
        LaunchedEffect(workoutState.successMessage, workoutState.error) {
            val text = workoutState.error ?: workoutState.successMessage
            if (text != null) {
                snackbar.showSnackbar(text)
                workoutVm.clearMessage()
            }
        }

        // Deliver coach notifications in-app whenever the overview refreshes
        // (Roadmap #6); the background worker covers the app-closed case.
        LaunchedEffect(state.overview?.notifications) {
            val notes = state.overview?.notifications.orEmpty()
            if (notes.isNotEmpty()) {
                notes.forEach { com.runningcoach.app.notify.CoachNotifications.post(context, it) }
                overviewVm.ackNotifications(notes.map { it.id })
            }
        }

        // Update home-screen widget whenever the overview changes.
        LaunchedEffect(state.overview) {
            state.overview?.let { ov ->
                scope.launch {
                    try { RunningWidget.updateAll(context, ov) }
                    catch (_: Exception) { /* widget update never crashes the app */ }
                }
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
                            label = { Text(dest.label, maxLines = 1, softWrap = false) },
                            alwaysShowLabel = true,
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
                        syncStatus = syncStatus,
                        onSync = overviewVm::sync,
                        onOpenActivity = openActivity,
                        onCoachAction = overviewVm::coachAction,
                        onOpenCoachLog = {
                            navController.navigate("coachlog") { launchSingleTop = true }
                        },
                        onOpenWeeklyRecap = {
                            navController.navigate("recap/weekly") { launchSingleTop = true }
                        },
                        // A8: Settings left the NavigationBar — gear on the header.
                        onOpenSettings = {
                            navController.navigate("settings") { launchSingleTop = true }
                        },
                        // G1: record a run with the phone, no hardware needed.
                        onStartLiveRun = {
                            navController.navigate("live-run") { launchSingleTop = true }
                        },
                    )
                }
                composable("live-run") {
                    LiveRunScreen(
                        todaySessionTitle = state.overview?.todayDecision?.headline,
                        onBack = { navController.popBackStack() },
                    )
                }
                composable("coachlog") {
                    CoachLogScreen(
                        repository = app.repository,
                        onBack = { navController.popBackStack() },
                    )
                }
                composable("recap/weekly") {
                    RecapScreen(
                        repository = app.repository,
                        activityId = null,
                        onBack = { navController.popBackStack() },
                    )
                }
                composable(
                    route = "recap/race/{id}",
                    arguments = listOf(navArgument("id") { type = NavType.IntType }),
                ) { entry ->
                    RecapScreen(
                        repository = app.repository,
                        activityId = entry.arguments?.getInt("id"),
                        onBack = { navController.popBackStack() },
                    )
                }
                composable(Dest.Activities.route) {
                    // A8: Stats merged into Corse behind a Lista/Statistiche
                    // switch. Each pane is the pre-existing full screen (it
                    // scrolls internally), so there is no nested-scroll clash.
                    var runsTab by rememberSaveable { mutableIntStateOf(0) }
                    Column(Modifier.fillMaxSize()) {
                        TabRow(selectedTabIndex = runsTab) {
                            Tab(
                                selected = runsTab == 0,
                                onClick = { runsTab = 0 },
                                text = { Text("Lista") },
                            )
                            Tab(
                                selected = runsTab == 1,
                                onClick = { runsTab = 1 },
                                text = { Text("Statistiche") },
                            )
                        }
                        Box(Modifier.weight(1f)) {
                            if (runsTab == 0) {
                                ActivitiesScreen(
                                    state,
                                    onOpenActivity = openActivity,
                                    onOpenHeatmap = {
                                        navController.navigate("heatmap") { launchSingleTop = true }
                                    },
                                    onOpenCalendar = {
                                        navController.navigate("calendar") { launchSingleTop = true }
                                    },
                                    onOpenCrossTraining = {
                                        navController.navigate("cross-training") { launchSingleTop = true }
                                    },
                                )
                            } else {
                                StatsScreen(
                                    state = statsState,
                                    onPeriodChange = statsVm::load,
                                    onExportCsv = { settingsVm.exportData("csv") },
                                    onExportJson = { settingsVm.exportData("json") },
                                )
                            }
                        }
                    }
                }
                composable("calendar") {
                    CalendarScreen(
                        activities = state.overview?.activities.orEmpty(),
                        prActivityIds = state.overview?.prActivityIds?.toSet() ?: emptySet(),
                        onOpenActivity = openActivity,
                        onBack = { navController.popBackStack() },
                    )
                }
                composable("cross-training") {
                    CrossTrainingScreen(
                        repository = app.repository,
                        onBack = { navController.popBackStack() },
                    )
                }
                composable("shoes") {
                    ShoesScreen(
                        repository = app.repository,
                        onBack = { navController.popBackStack() },
                    )
                }
                composable("heatmap") {
                    HeatmapScreen(
                        repository = app.repository,
                        onBack = { navController.popBackStack() },
                    )
                }
                composable(
                    route = "activity/{id}",
                    arguments = listOf(navArgument("id") { type = NavType.IntType }),
                ) { entry ->
                    val id = entry.arguments?.getInt("id")
                    val activity = state.overview?.activities?.firstOrNull { it.id == id }
                    ActivityDetailScreen(
                        activity = activity,
                        goalTargetPace = goalTargetPace(state.overview?.profile),
                        onBack = { navController.popBackStack() },
                        onOpenMap = {
                            id?.let { navController.navigate("map/$it") { launchSingleTop = true } }
                        },
                        onSaveRpe = { rpe -> id?.let { overviewVm.updateActivity(it, rpe = rpe) } },
                        onSaveNotes = { notes -> id?.let { overviewVm.updateActivity(it, notes = notes) } },
                        onOpenRaceRecap = {
                            id?.let { navController.navigate("recap/race/$it") { launchSingleTop = true } }
                        },
                    )
                }
                composable(
                    route = "map/{id}",
                    arguments = listOf(navArgument("id") { type = NavType.IntType }),
                ) { entry ->
                    val id = entry.arguments?.getInt("id")
                    val activity = state.overview?.activities?.firstOrNull { it.id == id }
                    val points = remember(activity?.routePolyline) {
                        parseRoutePoints(activity?.routePolyline)
                    }
                    MapFullscreenScreen(
                        points = points,
                        onBack = { navController.popBackStack() },
                    )
                }
                composable(Dest.Plan.route) {
                    PlanScreen(
                        state = planState,
                        onGeneratePlan = planVm::generatePlan,
                        onToggleSession = planVm::toggleSession,
                        onArchivePlan = planVm::archivePlan,
                        // A8: "Crea piano" opens the unified chat in plan mode.
                        onStartPlanChat = {
                            chatVm.startPlanSession()
                            navController.navigate(Dest.Chat.route) { launchSingleTop = true }
                        },
                        onDismissDialog = planVm::dismissDialog,
                        onOpenWorkouts = {
                            navController.navigate("workouts") { launchSingleTop = true }
                        },
                        onOpenCalendar = {
                            navController.navigate("plan-calendar") { launchSingleTop = true }
                        },
                        repository = app.repository,
                    )
                }
                composable("plan-calendar") {
                    PlanCalendarScreen(
                        plan = planState.plan,
                        onMoveSession = planVm::moveSession,
                        onBack = { navController.popBackStack() },
                    )
                }
                composable("workouts") {
                    WorkoutScreen(
                        state = workoutState,
                        onBack = { navController.popBackStack() },
                        onAddSegment = workoutVm::addSegment,
                        onRemoveSegment = workoutVm::removeSegment,
                        onMoveUp = workoutVm::moveSegmentUp,
                        onMoveDown = workoutVm::moveSegmentDown,
                        onUpdateSegment = workoutVm::updateSegment,
                        onSetName = workoutVm::setName,
                        onSetType = workoutVm::setType,
                        onSave = workoutVm::saveWorkout,
                        onSuggest = workoutVm::suggestWorkout,
                        onDelete = workoutVm::deleteWorkout,
                        onLoadIntoBuilder = workoutVm::loadIntoBuilder,
                        onClearBuilder = workoutVm::clearBuilder,
                    )
                }
                composable(Dest.Chat.route) {
                    ChatScreen(
                        state = chatState,
                        onSend = chatVm::sendMessage,
                        onNewSession = chatVm::newSession,
                        // Plan negotiation complete (A8): hand the §CTX§ to the
                        // plan generator and open the final-confirmation dialog.
                        onGeneratePlan = { ctx ->
                            planVm.setRunnerContext(ctx)
                            planVm.showGenerateDialog()
                            navController.navigate(Dest.Plan.route) { launchSingleTop = true }
                        },
                    )
                }
                // Legacy route (A8 soft migration): Stats left the NavigationBar
                // and lives inside Corse, but deep links keep working.
                composable("stats") {
                    StatsScreen(
                        state = statsState,
                        onPeriodChange = statsVm::load,
                        onExportCsv = { settingsVm.exportData("csv") },
                        onExportJson = { settingsVm.exportData("json") },
                    )
                }
                // Legacy route (A8): Settings is now the gear on the Oggi header.
                composable("settings") {
                    SettingsScreen(
                        settings = settings,
                        profile = state.overview?.profile,
                        onSave = { url, token ->
                            settingsVm.save(url, token) { overviewVm.refresh() }
                        },
                        onSaveCoach = { goalType, date, time, level, risk ->
                            overviewVm.saveCoach(goalType, date, time, level, risk)
                        },
                        onSaveTheme = settingsVm::saveTheme,
                        stravaStatus = stravaStatus,
                        onRefreshStrava = settingsVm::loadStravaStatus,
                        onOpenShoes = {
                            navController.navigate("shoes") { launchSingleTop = true }
                        },
                    )
                }
            }
        }

        // Post-run voice debrief (Roadmap A4): shown when the app is opened from
        // a debrief notification. Dismiss/send clears the request in the host.
        if (debriefRequest != null) {
            com.runningcoach.app.ui.components.DebriefSheet(
                activityId = debriefRequest.activityId,
                repository = app.repository,
                onDismiss = onDebriefHandled,
                onSent = { msg -> scope.launch { snackbar.showSnackbar(msg) } },
            )
        }
    }
}

/**
 * Derives a target training pace ("M:SS/km") from the athlete's goal race time
 * and distance so ActivityDetailScreen can compare actual vs. target.
 * Returns null when no goal with a target time is configured.
 */
private fun goalTargetPace(profile: AthleteProfile?): String? {
    val goal = profile?.goal ?: return null
    val targetTime = goal.targetTime?.takeIf { it.isNotBlank() } ?: return null
    val distanceKm = when (goal.goalType.lowercase()) {
        "marathon" -> 42.195
        "half", "half_marathon" -> 21.0975
        "10k" -> 10.0
        "5k" -> 5.0
        else -> return null
    }
    val parts = targetTime.split(":")
    val totalSeconds = when (parts.size) {
        3 -> parts[0].toLongOrNull()?.times(3600)?.plus(parts[1].toLongOrNull()?.times(60) ?: 0)?.plus(parts[2].toLongOrNull() ?: 0)
        2 -> parts[0].toLongOrNull()?.times(60)?.plus(parts[1].toLongOrNull() ?: 0)
        else -> null
    } ?: return null
    val secPerKm = totalSeconds / distanceKm
    val m = (secPerKm / 60).toInt()
    val s = (secPerKm % 60).toInt()
    return "$m:${s.toString().padStart(2, '0')}/km"
}
