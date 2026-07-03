package com.runningcoach.app.notify

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.runningcoach.app.MainActivity
import com.runningcoach.app.R
import com.runningcoach.app.data.model.AppNotification

/**
 * Posts coach notifications (Roadmap #6) as Android system notifications.
 * Notifications are always tied to a real decision/adaptation event — never
 * generic — and each is posted once (the backend acks delivered ones).
 */
object CoachNotifications {

    const val CHANNEL_ID = "coach_decisions"
    private const val CHANNEL_NAME = "Decisioni del coach"

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_DEFAULT,
            ).apply {
                description = "Avvisi legati alle decisioni e agli adattamenti del piano."
            }
            val mgr = context.getSystemService(NotificationManager::class.java)
            mgr?.createNotificationChannel(channel)
        }
    }

    private fun canPost(context: Context): Boolean {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            return ContextCompat.checkSelfPermission(
                context, Manifest.permission.POST_NOTIFICATIONS,
            ) == PackageManager.PERMISSION_GRANTED
        }
        return NotificationManagerCompat.from(context).areNotificationsEnabled()
    }

    /** Post one notification. The stable id is the backend event id. */
    fun post(context: Context, n: AppNotification) {
        if (!canPost(context)) return
        ensureChannel(context)
        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(n.title)
            .setContentText(n.body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(n.body))
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
        contentIntent(context, n)?.let { builder.setContentIntent(it) }
        runCatching {
            NotificationManagerCompat.from(context).notify(n.id, builder.build())
        }
    }

    /**
     * Tapping a deep-linked notification (Roadmap A4) reopens the app with
     * extras that trigger the matching surface — today, the voice-debrief
     * bottom-sheet. Plain notifications get no explicit intent (default launch).
     */
    private fun contentIntent(context: Context, n: AppNotification): PendingIntent? {
        if (n.deepLink != MainActivity.DEEP_LINK_DEBRIEF) return null
        val intent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(MainActivity.EXTRA_DEEP_LINK, n.deepLink)
            n.activityId?.let { putExtra(MainActivity.EXTRA_ACTIVITY_ID, it) }
        }
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        return PendingIntent.getActivity(context, n.id, intent, flags)
    }
}
