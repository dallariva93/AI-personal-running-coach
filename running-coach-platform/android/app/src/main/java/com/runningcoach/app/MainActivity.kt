package com.runningcoach.app

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.runningcoach.app.notify.SyncWorker
import com.runningcoach.app.ui.navigation.AppScaffold

class MainActivity : ComponentActivity() {

    private val requestNotifications =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    // A pending voice-debrief request (Roadmap A4), set when the activity is
    // (re)opened from a debrief-deep-linked notification. Compose observes it
    // to show the "Com'è andata?" bottom-sheet; cleared once handled.
    private var debriefRequest by mutableStateOf<DebriefRequest?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        maybeRequestNotificationPermission()
        debriefRequest = intent?.let(::parseDebrief)
        val app = application as RunningCoachApp
        setContent {
            AppScaffold(
                app = app,
                debriefRequest = debriefRequest,
                onDebriefHandled = { debriefRequest = null },
            )
        }
    }

    // launchMode="singleTop" means a tap while we're already running delivers
    // here instead of a fresh instance — pick up the new debrief request.
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        parseDebrief(intent)?.let { debriefRequest = it }
    }

    private fun parseDebrief(intent: Intent): DebriefRequest? {
        if (intent.getStringExtra(EXTRA_DEEP_LINK) != DEEP_LINK_DEBRIEF) return null
        val activityId = intent.getIntExtra(EXTRA_ACTIVITY_ID, -1).takeIf { it >= 0 }
        return DebriefRequest(activityId)
    }

    // Every foreground entry (cold start included, onResume always follows
    // onCreate) is a chance to pick up new Garmin activities without a tap
    // (Roadmap Q2). The backend recency guard caps the real work at 1x/10min.
    override fun onResume() {
        super.onResume()
        SyncWorker.syncNowExpedited(this)
    }

    /** Ask for POST_NOTIFICATIONS on Android 13+ so coach alerts can arrive. */
    private fun maybeRequestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            requestNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    companion object {
        const val DEEP_LINK_DEBRIEF = "debrief"
        const val EXTRA_DEEP_LINK = "deep_link"
        const val EXTRA_ACTIVITY_ID = "activity_id"
    }
}

/** A request to show the post-run voice-debrief sheet (Roadmap A4). */
data class DebriefRequest(val activityId: Int?)
