# Keep Gson model classes (used via reflection by the converter).
-keep class com.runningcoach.app.data.model.** { *; }
-keepattributes Signature
-keepattributes *Annotation*

# Retrofit / OkHttp
-dontwarn okhttp3.**
-dontwarn retrofit2.**
-keepclasseswithmembers class * {
    @retrofit2.http.* <methods>;
}
