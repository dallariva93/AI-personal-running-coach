package com.runningcoach.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.runningcoach.app.ui.navigation.AppScaffold
import com.runningcoach.app.ui.theme.RunningCoachTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val app = application as RunningCoachApp
        setContent {
            RunningCoachTheme {
                AppScaffold(app)
            }
        }
    }
}
