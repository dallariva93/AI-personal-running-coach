package com.runningcoach.app.widget

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.GlanceTheme
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetManager
import androidx.glance.appwidget.provideContent
import androidx.glance.appwidget.state.updateAppWidgetState
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.width
import androidx.glance.state.GlanceStateDefinition
import androidx.glance.state.PreferencesGlanceStateDefinition
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import com.runningcoach.app.MainActivity
import com.runningcoach.app.data.model.Overview

class RunningWidget : GlanceAppWidget() {

    override val stateDefinition: GlanceStateDefinition<*> = PreferencesGlanceStateDefinition

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        provideContent { Content() }
    }

    @Composable
    private fun Content() {
        val prefs = androidx.glance.currentState<androidx.datastore.preferences.core.Preferences>()
        val formState = prefs[KEY_FORM_STATE] ?: "—"
        val weeklyKm = prefs[KEY_WEEKLY_KM] ?: 0f
        val streakDays = prefs[KEY_STREAK] ?: 0
        val tsb = prefs[KEY_TSB]

        GlanceTheme {
            Box(
                modifier = GlanceModifier
                    .fillMaxSize()
                    .background(Color(0xFF0D1014))
                    .padding(14.dp)
                    .clickable(actionStartActivity<MainActivity>()),
                contentAlignment = Alignment.TopStart,
            ) {
                Column(modifier = GlanceModifier.fillMaxSize()) {
                    Text(
                        "AI Running Coach",
                        style = TextStyle(
                            color = ColorProvider(Color(0xFF9AA6B4)),
                            fontSize = 10.sp,
                        ),
                    )
                    Spacer(GlanceModifier.height(6.dp))
                    Text(
                        formState.uppercase(),
                        style = TextStyle(
                            color = ColorProvider(formColor(formState)),
                            fontSize = 20.sp,
                            fontWeight = FontWeight.Bold,
                        ),
                    )
                    Spacer(GlanceModifier.height(6.dp))
                    Row {
                        Text(
                            String.format("%.1f km", weeklyKm),
                            style = TextStyle(
                                color = ColorProvider(Color(0xFFE7ECF2)),
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Medium,
                            ),
                        )
                        if (tsb != null) {
                            Spacer(GlanceModifier.width(12.dp))
                            Text(
                                "TSB ${if (tsb >= 0) "+" else ""}${String.format("%.0f", tsb)}",
                                style = TextStyle(
                                    color = ColorProvider(Color(0xFF9AA6B4)),
                                    fontSize = 12.sp,
                                ),
                            )
                        }
                    }
                    if (streakDays > 0) {
                        Spacer(GlanceModifier.height(4.dp))
                        Text(
                            "$streakDays giorni streak",
                            style = TextStyle(
                                color = ColorProvider(Color(0xFFFF5A1F)),
                                fontSize = 11.sp,
                            ),
                        )
                    }
                }
            }
        }
    }

    private fun formColor(state: String): Color = when (state.lowercase()) {
        "fresh" -> Color(0xFF22C55E)
        "balanced" -> Color(0xFF38BDF8)
        "fatigued" -> Color(0xFFF43F5E)
        "detraining" -> Color(0xFFFBBF24)
        else -> Color(0xFF64748B)
    }

    companion object {
        val KEY_FORM_STATE = stringPreferencesKey("widget_form_state")
        val KEY_WEEKLY_KM = floatPreferencesKey("widget_weekly_km")
        val KEY_STREAK = intPreferencesKey("widget_streak")
        val KEY_TSB = floatPreferencesKey("widget_tsb")

        suspend fun updateAll(context: Context, overview: Overview) {
            val manager = GlanceAppWidgetManager(context)
            val ids = manager.getGlanceIds(RunningWidget::class.java)
            if (ids.isEmpty()) return
            ids.forEach { id ->
                updateAppWidgetState(context, PreferencesGlanceStateDefinition, id) { prefs ->
                    prefs.toMutablePreferences().apply {
                        this[KEY_FORM_STATE] = overview.metrics.formState
                        this[KEY_WEEKLY_KM] = overview.metrics.weeklyDistanceKm.toFloat()
                        this[KEY_STREAK] = overview.gamification?.streakDays ?: 0
                        overview.metrics.tsb?.let { this[KEY_TSB] = it.toFloat() }
                    }
                }
                RunningWidget().update(context, id)
            }
        }
    }
}
