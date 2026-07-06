plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    // Room's annotation processor (G1: local recording store + upload queue).
    alias(libs.plugins.ksp)
    // Applied conditionally below — see the note before `android { }`.
    alias(libs.plugins.google.services) apply false
}

// The Google Services plugin (FCM, Roadmap A3) hard-fails the build when
// `google-services.json` is absent. That file is an installation secret and is
// intentionally NOT committed, so applying the plugin unconditionally breaks CI
// and any contributor without Firebase. Apply it only when the file is present:
// without it the app still builds and the FCM service is simply inert (polling
// covers notification delivery), exactly as CoachFirebaseService documents.
if (file("google-services.json").exists()) {
    apply(plugin = "com.google.gms.google-services")
}

android {
    namespace = "com.runningcoach.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.runningcoach.app"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"

        // Default backend used until the user changes it in Settings.
        buildConfigField("String", "DEFAULT_BASE_URL", "\"https://ai-running-coach.fly.dev/\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    composeOptions {
        kotlinCompilerExtensionVersion = libs.versions.composeCompiler.get()
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.datastore.preferences)

    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons.extended)
    debugImplementation(libs.compose.ui.tooling)

    implementation(libs.retrofit)
    implementation(libs.retrofit.gson)
    implementation(libs.okhttp.logging)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.androidx.glance.appwidget)
    implementation(libs.androidx.glance.material3)

    // Real OpenStreetMap tiles for the activity route map (free, no API key).
    implementation(libs.osmdroid.android)
    // Background job for delivering coach notifications without opening the app.
    implementation(libs.androidx.work.runtime.ktx)
    // Real push delivery via FCM (Roadmap A3). Requires google-services.json
    // in app/ when building with Firebase; without it the FCM service is inert.
    implementation(libs.firebase.messaging)
    // Health Connect (Roadmap A2): the no-Garmin path — read running sessions,
    // HR, sleep and HRV from any HC-compatible app on the device.
    implementation(libs.androidx.health.connect)
    // Room (G1/G5): crash-safe local store for live-run recordings and the
    // offline upload queue — the run must never be lost.
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    ksp(libs.androidx.room.compiler)
    // FusedLocationProvider (G1): the live GPS tracking engine.
    implementation(libs.play.services.location)
}
