package com.runningcoach.app

import android.Manifest
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import com.runningcoach.app.notify.SyncWorker
import com.runningcoach.app.ui.navigation.AppScaffold

class MainActivity : ComponentActivity() {

    private val requestNotifications =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        maybeRequestNotificationPermission()
        val app = application as RunningCoachApp
        setContent {
            AppScaffold(app)
        }
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
}
