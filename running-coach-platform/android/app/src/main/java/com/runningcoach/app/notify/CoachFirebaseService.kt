package com.runningcoach.app.notify

import android.content.Context
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.runningcoach.app.RunningCoachApp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Receives FCM push messages (Roadmap A3) and forwards them to
 * [CoachNotifications] as system notifications. On a new token (rotation,
 * re-install) it uploads it to the backend so push delivery stays uninterrupted.
 *
 * When Firebase is not configured (no google-services.json) this service is
 * never activated by the system, so the app degrades gracefully to polling
 * via [NotificationSyncWorker].
 */
class CoachFirebaseService : FirebaseMessagingService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onMessageReceived(message: RemoteMessage) {
        val title = message.notification?.title ?: message.data["title"] ?: return
        val body = message.notification?.body ?: message.data["body"] ?: title
        val id = message.data["event_id"]?.toIntOrNull() ?: System.currentTimeMillis().toInt()
        CoachNotifications.post(
            applicationContext,
            com.runningcoach.app.data.model.AppNotification(
                id = id,
                title = title,
                body = body,
            ),
        )
    }

    override fun onNewToken(token: String) {
        uploadToken(applicationContext, token)
    }

    companion object {
        /** Upload the current FCM token to the backend (best-effort). */
        fun uploadToken(context: Context, token: String) {
            val app = context as? RunningCoachApp ?: return
            CoroutineScope(Dispatchers.IO).launch {
                runCatching { app.repository.registerDevice(token) }
            }
        }
    }
}
